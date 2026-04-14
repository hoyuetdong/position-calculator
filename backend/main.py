"""
Futu/Moomoo broker service - FastAPI backend.
Runs locally to serve position data to Next.js frontend.

OpenD must be running locally before syncing. Download from:
https://openapi.futunn.com

Environment variables:
  FUTU_HOST — OpenD host (default: 127.0.0.1)
  FUTU_PORT — OpenD port (default: 11111)
  FUTU_TRADE_PWD — Trading password (optional)
  PORT — API server port (default: 8000)
  FUTU_DISABLE_LOG — Set to 1 to disable futu-api log file writing (avoids permission issues)
"""
import os
import sys
import json
import httpx
import threading
import time
import logging
from io import StringIO
from dotenv import load_dotenv

# 自動加載專案根目錄的 .env 檔案
load_dotenv()
from typing import List, Dict, Tuple, Optional
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from functools import wraps
from datetime import datetime, timezone

_HKD_USD_FALLBACK = 1 / 7.78

# API Key authentication
_API_SECRET = os.getenv("API_SECRET", "")


def verify_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """
    Verify API key for all protected endpoints.
    If API_SECRET is not set, skip authentication (for local dev).
    """
    if not _API_SECRET:
        return  # Skip auth if not configured
    if x_api_key != _API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ============================================================================
# 停用 futu-api 日誌寫入（避免權限問題）
# ============================================================================
def _disable_futu_logging():
    """
    如果 FUTU_DISABLE_LOG=1，將 futu-api 的日誌輸出重定向到 /dev/null
    或者使用可寫入的位置，避免權限問題。
    呢個一定要喺 import futu 之前調用。
    """
    if os.getenv("FUTU_DISABLE_LOG", "0") == "1":
        print("[Config] FUTU_DISABLE_LOG=1, disabling futu-api file logging")

        # 嘗試創建日誌目錄（如果唔存在）
        log_dir = os.path.expanduser("~/.com.futunn.FutuOpenD/Log")
        try:
            os.makedirs(log_dir, exist_ok=True)
        except PermissionError:
            # 如果創建失敗，使用 /tmp
            log_dir = "/tmp/futu_logs"
            os.makedirs(log_dir, exist_ok=True)
            os.environ["FUTU_LOG_DIR"] = log_dir

        # 替換 ft_logger 的 FileHandler 為 NullHandler
        try:
            import futu.common.ft_logger as ft_logger_module

            # 保存原來的 logger 類
            original_ftlog = ft_logger_module.FTLog

            class SilentFTLog:
                """抑制日誌文件輸出的 FTLog 替代類"""

                def __init__(self):
                    # 設置 NullHandler，避免寫入文件
                    self.logger = logging.getLogger("futu")
                    self.logger.setLevel(logging.CRITICAL)
                    # 清除所有現有的 handlers
                    self.logger.handlers = []
                    # 添加 NullHandler
                    self.logger.addHandler(logging.NullHandler())

                def debug(self, *args, **kwargs):
                    pass

                def info(self, *args, **kwargs):
                    pass

                def warning(self, *args, **kwargs):
                    pass

                def error(self, *args, **kwargs):
                    pass

                def critical(self, *args, **kwargs):
                    pass

            # 替換原始類
            ft_logger_module.FTLog = SilentFTLog
            print(f"[Config] Futu logging redirected to null handler (log dir: {log_dir})")
        except ImportError:
            # futu 未安裝，繼續
            pass
        except Exception as e:
            print(f"[Config] Warning: Could not patch futu logging: {e}")


# 盡早調用，喺 import futu 之前
_disable_futu_logging()


# ============================================================================
# 獲取 OpenD 主機地址
# ============================================================================
def _get_futu_host() -> str:
    """
    返回 OpenD 主機地址。
    
    優先級：
    1. 如果環境變數 FUTU_HOST 已設置，直接使用
    2. 否則使用 127.0.0.1（本地運行）
    """
    env_host = os.getenv("FUTU_HOST")
    if env_host:
        return env_host
    return "127.0.0.1"


# ============================================================================
# 非同步止蝕單管理系統 (持久化版本)
# ============================================================================
from pathlib import Path

# 定義數據儲存檔案路徑
_PENDING_STOPS_FILE = Path(__file__).parent / "pending_stops.json"
_ORDER_HISTORY_FILE = Path(__file__).parent / "order_history.json"

# 呢度用嚟存儲有待觸發止蝕單嘅訂單
# Key: order_id (entry order)
# Value: dict with stop_loss_price, quantity, symbol, stop_loss_placed_qty, filled_qty, etc.
_pending_stop_orders: Dict[str, Dict] = {}
_pending_stop_lock = threading.RLock()  # 用 RLock 避免同一 thread 內重入死鎖

# Background monitor thread (singleton)
_monitor_thread: Optional[threading.Thread] = None
_monitor_running = threading.Event()

# ================================================================================
# OpenD Watchdog - 自動重啟卡住嘅 OpenD
# ================================================================================
_watchdog_thread: Optional[threading.Thread] = None
_watchdog_running = threading.Event()
_WATCHDOG_CHECK_INTERVAL = 30  # 每30秒檢查一次
_WATCHDOG_MAX_FAILURES = 3  # 連續3次失敗先重啟


def _test_opend_connection(host: str, port: int, timeout: float = 3.0) -> bool:
    """
    測試 OpenD 連接是否正常。
    使用 socket 測試，避免創建完整嘅 futu context。
    Returns True if connection successful, False otherwise.
    """
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def _restart_opend():
    """
    重啟 OpenD 進程。
    使用 subprocess 調用 shell 腳本重啟，避免喺同一個 process 殺自己。
    """
    import subprocess
    print("[Watchdog] Restarting OpenD...")
    
    restart_script = "/tmp/restart_opend.sh"
    
    # 創建重啟腳本
    script_content = """#!/bin/bash
# 停止舊 OpenD
pkill -9 FutuOpenD 2>/dev/null
sleep 2

# 重啟 OpenD
screen -dmS opend bash -c 'cd /opt/futuopend && ./FutuOpenD -cfg_file=/opt/futuopend/FutuOpenD.xml; exec bash'

# 等 OpenD 啟動
sleep 10

# 驗證
if timeout 3 bash -c 'cat < /dev/null > /dev/tcp/127.0.0.1/11111' 2>/dev/null; then
    echo "OpenD restarted successfully"
    exit 0
else
    echo "OpenD restart failed"
    exit 1
fi
"""
    
    try:
        with open(restart_script, 'w') as f:
            f.write(script_content)
        os.chmod(restart_script, 0o755)
        
        # 執行重啟腳本
        result = subprocess.run(
            ['/bin/bash', restart_script],
            capture_output=True,
            text=True,
            timeout=60
        )
        print(f"[Watchdog] Restart result: {result.returncode}")
        if result.stdout:
            print(f"[Watchdog] stdout: {result.stdout}")
        if result.stderr:
            print(f"[Watchdog] stderr: {result.stderr}")
        
        return result.returncode == 0
    except Exception as e:
        print(f"[Watchdog] Failed to restart OpenD: {e}")
        return False


def _restart_backend():
    """
    重啟 Backend 進程。
    呢個函數會打印警告，因為我哋唔可以喺同一個 process 重啟自己。
    實際重啟需要外部工具或者 cron。
    """
    print("[Watchdog] Backend restart needed. Please restart the backend manually or via systemd.")
    print("[Watchdog] Hint: screen -S app -X quit && screen -dmS app bash -c 'cd /opt/vcp-calculator && source venv/bin/activate && python3 backend/main.py; exec bash'")


def _watchdog_loop(check_interval: int = _WATCHDOG_CHECK_INTERVAL, max_failures: int = _WATCHDOG_MAX_FAILURES):
    """
    Watchdog 監控線程。
    定期檢測 OpenD 連接，如果連續失敗 N 次，自動重啟 OpenD。
    """
    print(f"[Watchdog] Starting OpenD watchdog (interval: {check_interval}s, max_failures: {max_failures})")
    
    failure_count = 0
    last_restart = 0
    
    while _watchdog_running.is_set():
        try:
            host = _get_futu_host()
            port = int(os.getenv("FUTU_PORT", "11111"))
            
            is_connected = _test_opend_connection(host, port)
            
            if is_connected:
                if failure_count > 0:
                    print(f"[Watchdog] OpenD connection restored (was {failure_count} failures)")
                failure_count = 0
            else:
                failure_count += 1
                print(f"[Watchdog] OpenD connection failed ({failure_count}/{max_failures})")
                
                # 避免太頻繁重啟（上次重啟後起碼等5分鐘）
                current_time = time.time()
                if failure_count >= max_failures and (current_time - last_restart) > 300:
                    print(f"[Watchdog] OpenD appears stuck, attempting restart...")
                    
                    if _restart_opend():
                        failure_count = 0
                        last_restart = current_time
                        print(f"[Watchdog] OpenD restart successful")
                    else:
                        print(f"[Watchdog] OpenD restart failed, will retry later")
                
        except Exception as e:
            print(f"[Watchdog] Error in watchdog loop: {e}")
        
        time.sleep(check_interval)
    
    print("[Watchdog] OpenD watchdog stopped")


def start_watchdog(check_interval: int = _WATCHDOG_CHECK_INTERVAL, max_failures: int = _WATCHDOG_MAX_FAILURES):
    """啟動 OpenD Watchdog 線程。"""
    global _watchdog_thread
    
    if _watchdog_thread is not None and _watchdog_thread.is_alive():
        print("[Watchdog] Watchdog already running")
        return
    
    # 允許環境變數覆蓋
    env_interval = os.getenv("WATCHDOG_CHECK_INTERVAL")
    env_failures = os.getenv("WATCHDOG_MAX_FAILURES")
    
    if env_interval:
        try:
            check_interval = int(env_interval)
        except ValueError:
            pass
    
    if env_failures:
        try:
            max_failures = int(env_failures)
        except ValueError:
            pass
    
    _watchdog_running.set()
    _watchdog_thread = threading.Thread(
        target=_watchdog_loop,
        args=(check_interval, max_failures),
        daemon=True,
        name="OpenDWatchdog"
    )
    _watchdog_thread.start()
    print(f"[Watchdog] OpenD watchdog thread started (interval: {check_interval}s, max_failures: {max_failures})")


def stop_watchdog():
    """停止 OpenD Watchdog 線程。"""
    global _watchdog_thread
    
    _watchdog_running.clear()
    if _watchdog_thread is not None:
        _watchdog_thread.join(timeout=5)
        _watchdog_thread = None
    print("[Watchdog] OpenD watchdog stopped")


# 重試限制常量
MAX_STOP_LOSS_RETRIES = 5  # 最多重試5次
RETRY_BACKOFF_BASE = 2  # 基礎等待秒數
RETRY_BACKOFF_MAX = 60  # 最長等待60秒

# 動態交易環境變數
_current_trade_env: str = "SIMULATE"  # 預設SIMULATE，啟動時會從環境變數讀取


def _get_trade_env() -> str:
    """取得當前交易環境."""
    return _current_trade_env


def _set_trade_env(env: str) -> None:
    """設定當前交易環境 (SIMULATE 或 REAL)."""
    global _current_trade_env
    if env.upper() not in ["SIMULATE", "REAL"]:
        raise ValueError(f"Invalid trade env: {env}. Must be SIMULATE or REAL")
    _current_trade_env = env.upper()
    print(f"[Env] Trade environment changed to: {_current_trade_env}")


def _load_pending_stops_from_file() -> Dict[str, Dict]:
    """從 JSON file 讀取 pending stop orders (線程安全)."""
    if not _PENDING_STOPS_FILE.exists():
        return {}
    
    # 讀取時都加鎖，確保併發安全
    with _pending_stop_lock:
        try:
            with open(_PENDING_STOPS_FILE, 'r') as f:
                data = json.load(f)
                print(f"[StopMonitor] Loaded {len(data)} pending stop orders from file")
                return data
        except Exception as e:
            print(f"[StopMonitor] Failed to load pending stops file: {e}")
            return {}


def _save_pending_stops_to_file() -> None:
    """將 pending stop orders 寫入 JSON file."""
    try:
        with open(_PENDING_STOPS_FILE, 'w') as f:
            json.dump(_pending_stop_orders, f, indent=2)
    except Exception as e:
        print(f"[StopMonitor] Failed to save pending stops file: {e}")


def _query_futu_open_orders(host: str, port: int, trd_env: str) -> Dict[str, Dict]:
    """
    查詢富途 API 拎所有未成交的 open orders.
    返回 dict: {order_id: {status, fill_qty, order_qty, code, side, ...}}
    """
    try:
        import futu
    except ImportError:
        return {}

    trd_env_enum = futu.TrdEnv.SIMULATE if trd_env.upper() == "SIMULATE" else futu.TrdEnv.REAL
    open_orders: Dict[str, Dict] = {}

    # 遍歷 HK 和 US 市場
    for market in [futu.TrdMarket.US, futu.TrdMarket.HK]:
        ctx = futu.OpenSecTradeContext(filter_trdmarket=market, host=host, port=port)
        try:
            ret_acc, acc_list = ctx.get_acc_list()
            if ret_acc != futu.RET_OK:
                continue

            # 搵符合環境的帳戶
            acc_ids = [
                int(row["acc_id"])
                for _, row in acc_list.iterrows()
                if str(row.get("trd_env", "")).upper() == trd_env.upper()
                and str(row.get("acc_status", "")).upper() == "ACTIVE"
            ]

            for acc_id in acc_ids:
                # 查詢所有訂單 (包括未成交的)
                ret, data = ctx.order_list_query(
                    trd_env=trd_env_enum,
                    acc_id=acc_id,
                )

                if ret == futu.RET_OK and data is not None and not data.empty:
                    for _, row in data.iterrows():
                        order_id = str(row.get("order_id", ""))
                        status = str(row.get("order_status", "")).upper()
                        # 只保留未成交的訂單
                        if status in ["SUBMITTED", "ACTIVE", "PARTIAL_FILLED", "FILLED_ALL"]:
                            open_orders[order_id] = {
                                "status": status,
                                "fill_qty": int(float(row.get("dealt_qty", 0) or 0)),
                                "order_qty": int(float(row.get("qty", 0) or 0)),
                                "code": str(row.get("code", "")),
                                "side": str(row.get("trd_side", "")),
                                "acc_id": acc_id,
                            }
        finally:
            ctx.close()

    return open_orders


def _restore_pending_stops_from_history(host: str, port: int, trd_env: str) -> int:
    """
    Startup 時自動恢復未成交訂單嘅止蝕資訊.
    邏輯：
    1. 查詢富途 API 拎所有未成交的 open orders
    2. 比對 order_history.json，找出邊啲未成交訂單有設置止蝕價
    3. 自動恢復到 pending_stops.json

    返回：恢復的訂單數量
    """
    print("[StopMonitor] Starting pending stops restoration from order history...")

    # 1. 查詢富途 API 拎所有未成交的 open orders
    futu_open_orders = _query_futu_open_orders(host, port, trd_env)
    if not futu_open_orders:
        print("[StopMonitor] No open orders found in Futu, nothing to restore")
        return 0

    print(f"[StopMonitor] Found {len(futu_open_orders)} open orders in Futu")

    # 2. 讀取 order_history.json
    history = _load_order_history_from_file()
    if not history:
        print("[StopMonitor] No order history found, nothing to restore")
        return 0

    print(f"[StopMonitor] Loaded {len(history)} records from order history")

    # 3. 遍歷歷史記錄，找出未成交但有止蝕價的訂單
    restored_count = 0
    for record in history:
        entry_order_id = record.get("entry_order_id")
        if not entry_order_id:
            continue

        # 檢查訂單是否在富途的 open orders 入面
        if entry_order_id in futu_open_orders:
            order_data = futu_open_orders[entry_order_id]
            status = order_data.get("status", "")
            fill_qty = order_data.get("fill_qty", 0)
            stop_loss_price = record.get("stop_loss_price")

            if stop_loss_price:
                # 檢查是否已經恢復過 (避免重複)
                with _pending_stop_lock:
                    if entry_order_id in _pending_stop_orders:
                        print(f"[StopMonitor] Order {entry_order_id} already in pending, skipping")
                        continue

                # 計算需要掛止蝕既股數
                stop_loss_placed_qty = record.get("stop_loss_placed_qty", 0)
                total_qty = record.get("quantity", 0)
                new_filled_qty = fill_qty - stop_loss_placed_qty

                # 恢復到 pending_stops.json
                restored_order = {
                    "symbol": record.get("symbol"),
                    "quantity": total_qty,
                    "stop_loss_price": stop_loss_price,
                    "futu_code": record.get("futu_code"),
                    "acc_id": record.get("acc_id") or order_data.get("acc_id"),
                    "trd_env": record.get("trd_env") or trd_env,
                    "direction": record.get("direction", "LONG"),
                    "filled_qty": fill_qty,
                    "stop_loss_placed_qty": stop_loss_placed_qty,
                    "restored_from_history": True,  # 標記係從歷史恢復的
                    "restored_at": datetime.now(timezone.utc).isoformat(),
                }

                with _pending_stop_lock:
                    _pending_stop_orders[entry_order_id] = restored_order

                _save_pending_stops_to_file()
                restored_count += 1
                print(f"[StopMonitor] RESTORED order {entry_order_id}: {record.get('symbol')} fill_qty={fill_qty}/{total_qty}, stop_price=${stop_loss_price}, status={status}")
            else:
                print(f"[StopMonitor] Order {entry_order_id} in history but no stop_loss_price, skipping")
        else:
            # 訂單不在 open orders 入面，可能已經完全成交或取消咗
            # 呢個唔需要恢復，因為或者已經處理過
            pass

    print(f"[StopMonitor] Restoration complete: {restored_count} orders restored")
    return restored_count


def _load_order_history_from_file() -> List[Dict]:
    """從 order_history.json 讀取所有歷史記錄 (線程安全)."""
    if not _ORDER_HISTORY_FILE.exists():
        return []

    try:
        with open(_ORDER_HISTORY_FILE, 'r') as f:
            data = json.load(f)
            if not isinstance(data, list):
                return []
            print(f"[StopMonitor] Loaded {len(data)} order history records from file")
            return data
    except Exception as e:
        print(f"[StopMonitor] Failed to load order history file: {e}")
        return []


def _append_order_to_history(order_record: Dict) -> None:
    """
    追加訂單記錄到 order_history.json (永久保存，永不刪除).
    呢個係雙重持久化嘅第二層，確保即使 pending_stops.json 被清空，
    都可以從歷史恢復未成交訂單嘅止蝕資訊。
    """
    try:
        history = _load_order_history_from_file()
        history.append(order_record)
        with open(_ORDER_HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
        print(f"[StopMonitor] Appended order to history: {order_record.get('entry_order_id', 'N/A')}")
    except Exception as e:
        print(f"[StopMonitor] Failed to append order to history: {e}")


def _init_pending_stops_from_file() -> None:
    """初始化時由 file load pending stops 到 memory (線程安全)."""
    global _pending_stop_orders

    # 將 load 同 assign 包喺同一個 lock 入面，避免 race condition
    with _pending_stop_lock:
        loaded = _load_pending_stops_from_file()
        _pending_stop_orders = loaded

        if loaded:
            print(f"[StopMonitor] Restored {len(loaded)} pending stop orders from disk")


def _get_pending_stop_orders() -> Dict[str, Dict]:
    """取得所有有待觸發止蝕單."""
    with _pending_stop_lock:
        return _pending_stop_orders.copy()


def _add_pending_stop_order(entry_order_id: str, order_info: Dict) -> None:
    """加入有待觸發止蝕單到隊列，同時寫入 file 和 order_history."""
    with _pending_stop_lock:
        order_info['created_at'] = datetime.now(timezone.utc).isoformat()
        order_info['filled_qty'] = 0
        order_info['stop_loss_placed_qty'] = 0  # 防重複：已掛止蝕單既股數
        # 重試追蹤
        if 'stop_loss_retry_count' not in order_info:
            order_info['stop_loss_retry_count'] = 0
        if 'last_retry_at' not in order_info:
            order_info['last_retry_at'] = None
        _pending_stop_orders[entry_order_id] = order_info
        _save_pending_stops_to_file()
        
        # 雙重持久化：同時寫入 order_history.json (永不刪除)
        _append_order_to_history({
            "entry_order_id": entry_order_id,
            **order_info
        })
        
        print(f"[StopMonitor] Added pending stop order: entry_id={entry_order_id}, stop_price={order_info.get('stop_loss_price')}, total_qty={order_info.get('quantity')}")


def _update_pending_stop_order(entry_order_id: str, updates: Dict) -> None:
    """更新 pending stop order 資料 (例如 filled_qty, stop_loss_placed_qty)."""
    with _pending_stop_lock:
        if entry_order_id in _pending_stop_orders:
            _pending_stop_orders[entry_order_id].update(updates)
            _save_pending_stops_to_file()


def _remove_pending_stop_order(entry_order_id: str) -> None:
    """從隊列移除已完成觸發止蝕單，同時更新 file."""
    with _pending_stop_lock:
        if entry_order_id in _pending_stop_orders:
            del _pending_stop_orders[entry_order_id]
            _save_pending_stops_to_file()
            print(f"[StopMonitor] Removed pending stop order: entry_id={entry_order_id}")


def _query_order_status_and_fill(host: str, port: int, order_id: str, acc_id: int, trd_env: str) -> Optional[Dict]:
    """
    查詢訂單狀態，返回包含狀態同成交股數既 dict.
    Return: {"status": "FILLED"/"PARTIAL_FILLED"/"SUBMITTED"/etc, "fill_qty": int, "order_qty": int}
    
    注意：呢個函數會嘗試喺 REAL 環境入面查找訂單，
    如果 acc_id 唔正確，會遍歷所有 REAL 帳戶直到搵到為止。
    """
    try:
        import futu
        
        trd_env_enum = futu.TrdEnv.SIMULATE if trd_env.upper() == "SIMULATE" else futu.TrdEnv.REAL
        
        # 如果係 REAL 環境，我哋需要嘗試所有 REAL 帳戶，因為 acc_id 可能已經過時
        if trd_env.upper() == "REAL":
            print(f"[StopMonitor] Querying order {order_id} in REAL environment (acc_id hint: {acc_id})")
            # 首先創建一個 context 嚟獲取帳戶列表
            ctx_list = futu.OpenSecTradeContext(filter_trdmarket=futu.TrdMarket.US, host=host, port=port)
            try:
                ret_acc, acc_list = ctx_list.get_acc_list()
                if ret_acc != futu.RET_OK:
                    print(f"[StopMonitor] Failed to get acc_list: {acc_list}")
                    return None
                
                # 獲取所有 REAL + ACTIVE 帳戶
                real_acc_ids = [
                    int(row["acc_id"])
                    for _, row in acc_list.iterrows()
                    if str(row.get("trd_env", "")).upper() == "REAL"
                    and str(row.get("acc_status", "")).upper() == "ACTIVE"
                ]
                
                if not real_acc_ids:
                    print(f"[StopMonitor] No REAL+ACTIVE accounts found!")
                    return None
                
                print(f"[StopMonitor] Trying {len(real_acc_ids)} REAL accounts: {real_acc_ids}")
                
                # 嘗試每個帳戶直到搵到訂單
                for try_acc_id in real_acc_ids:
                    for market in [futu.TrdMarket.US, futu.TrdMarket.HK]:
                        ctx = futu.OpenSecTradeContext(filter_trdmarket=market, host=host, port=port)
                        try:
                            ret, data = ctx.order_list_query(
                                trd_env=futu.TrdEnv.REAL,
                                acc_id=try_acc_id,
                                order_id=order_id,
                            )
                            
                            if ret == futu.RET_OK and data is not None and not data.empty:
                                # Find the order with matching order_id
                                for _, row in data.iterrows():
                                    if str(row.get("order_id", "")) == str(order_id):
                                        status = str(row.get("order_status", "")).upper()
                                        fill_qty = int(float(row.get("dealt_qty", 0) or 0))
                                        order_qty = int(float(row.get("qty", 0) or 0))
                                        code = str(row.get("code", ""))
                                        
                                        print(f"[StopMonitor] Found order {order_id} in acc {try_acc_id} ({code}): {status}, fill_qty: {fill_qty}/{order_qty}")
                                        
                                        return {
                                            "status": status,
                                            "fill_qty": fill_qty,
                                            "order_qty": order_qty,
                                            "acc_id": try_acc_id,  # 返回正確嘅 acc_id
                                        }
                        finally:
                            ctx.close()
                
                # 搵唔到訂單
                print(f"[StopMonitor] Order {order_id} not found in any REAL account")
                return None
            finally:
                ctx_list.close()
        
        # SIMULATE 環境：使用原始邏輯
        for market in [futu.TrdMarket.US, futu.TrdMarket.HK]:
            ctx = futu.OpenSecTradeContext(filter_trdmarket=market, host=host, port=port)
            try:
                ret, data = ctx.order_list_query(
                    trd_env=trd_env_enum,
                    acc_id=acc_id,
                    order_id=order_id,
                )
                
                if ret == futu.RET_OK and data is not None and not data.empty:
                    # Find the order with matching order_id
                    for _, row in data.iterrows():
                        if str(row.get("order_id", "")) == str(order_id):
                            status = str(row.get("order_status", "")).upper()
                            # Futu API column is dealt_qty, not fill_qty
                            fill_qty = int(float(row.get("dealt_qty", 0) or 0))
                            order_qty = int(float(row.get("qty", 0) or 0))
                            
                            print(f"[StopMonitor] Order {order_id} status: {status}, fill_qty: {fill_qty}/{order_qty}")
                            
                            return {
                                "status": status,
                                "fill_qty": fill_qty,
                                "order_qty": order_qty
                            }
            finally:
                ctx.close()
        
        return None
    except Exception as e:
        print(f"[StopMonitor] Error querying order status: {e}")
        return None


def _place_stop_order(
    host: str,
    port: int,
    symbol: str,
    quantity: int,
    stop_loss_price: float,
    acc_id: int,
    trd_env: str,
    trade_pwd: str = "",
    direction: str = "LONG"  # 新增：LONG 或 SHORT
) -> Dict:
    """
    觸發並落STOP止損單.
    只會喺Entry Order完全成交或部分成交後先會調用呢個function.
    
    - LONG: SELL STOP (跌到止蝕價止蝕)
    - SHORT: BUY STOP (升到止蝕價止蝕)
    """
    try:
        import futu
    except ImportError:
        raise ImportError("futu-api not installed. Run: pip install futu-api")
    
    futu_code = _to_futu_code(symbol)
    side_str = "BUY" if direction == "SHORT" else "SELL"
    print(f"[StopMonitor] Triggering STOP order: {side_str} {quantity} {symbol} @ ${stop_loss_price} (direction={direction})")
    
    # Determine market
    if futu_code.startswith("HK."):
        market = futu.TrdMarket.HK
    else:
        market = futu.TrdMarket.US
    
    ctx = futu.OpenSecTradeContext(filter_trdmarket=market, host=host, port=port)
    try:
        # Unlock trade
        if trade_pwd:
            ret_unlock, _ = ctx.unlock_trade(trade_pwd)
            if ret_unlock != futu.RET_OK:
                print(f"[StopMonitor] Failed to unlock trade")
                return {"success": False, "error": "Failed to unlock trade"}
        
        trd_env_enum = futu.TrdEnv.SIMULATE if trd_env.upper() == "SIMULATE" else futu.TrdEnv.REAL
        
        # 止損單方向
        trd_side = futu.TrdSide.BUY if direction == "SHORT" else futu.TrdSide.SELL
        
        # Place STOP order (GTC = Good Till Cancelled, 撤單前有效)
        ret, data = ctx.place_order(
            price=0,  # STOP orders don't use price, use aux_price as trigger
            qty=quantity,
            code=futu_code,
            trd_side=trd_side,
            order_type=futu.OrderType.STOP,
            trd_env=trd_env_enum,
            acc_id=acc_id,
            aux_price=stop_loss_price,  # Trigger price
            time_in_force=futu.TimeInForce.GTC,  # 撤單前有效
        )
        
        print(f"[StopMonitor] STOP order result: ret={ret}, data={data}")
        
        if ret != futu.RET_OK:
            return {"success": False, "error": str(data)}
        
        stop_order_id = None
        if data is not None and not data.empty:
            stop_order_id = str(data.iloc[0].get("order_id", ""))
        
        return {
            "success": True,
            "stop_order_id": stop_order_id,
            "message": f"STOP order placed: {side_str} {quantity} @ ${stop_loss_price}"
        }
    finally:
        ctx.close()


def _monitor_loop(host: str, port: int, check_interval: float = 2.0):
    """
    Background thread loop - monitor pending orders.
    定期檢查所有有待觸發止蝕單嘅 Entry Order，
    如果變成 FILLED 或 PARTIAL_FILLED 狀態，就自動觸發止損單。

    對於部分成交既情況：
    - 只對已成交既數量落 STOP order
    - 繼續監控剩餘既數量
    """
    print(f"[StopMonitor] Background monitor started (interval: {check_interval}s)")
    
    trade_pwd = os.getenv("FUTU_TRADE_PWD", "")
    
    while _monitor_running.is_set():
        try:
            # Get copy of pending orders
            pending = _get_pending_stop_orders()
            
            if not pending:
                time.sleep(check_interval)
                continue
            
            # Get account info for querying
            import futu
            ctx = futu.OpenSecTradeContext(filter_trdmarket=futu.TrdMarket.US, host=host, port=port)
            try:
                ret_acc, acc_list = ctx.get_acc_list()
                if ret_acc != futu.RET_OK:
                    time.sleep(check_interval)
                    continue
                
                # Get first active account (使用動態環境)
                trd_env = _get_trade_env()
                active_acc_ids = [
                    int(row["acc_id"])
                    for _, row in acc_list.iterrows()
                    if str(row.get("trd_env", "")).upper() == trd_env.upper()
                    and str(row.get("acc_status", "")).upper() == "ACTIVE"
                ]
                
                if not active_acc_ids:
                    time.sleep(check_interval)
                    continue
                
                acc_id = active_acc_ids[0]
                
                # Check each pending order
                for entry_order_id, order_info in pending.items():
                    # Get order status AND fill quantity in one call
                    order_data = _query_order_status_and_fill(host, port, entry_order_id, acc_id, trd_env)
                    
                    if not order_data:
                        # Order not found - might have been deleted or expired
                        print(f"[StopMonitor] Order {entry_order_id} not found in order list, removing from pending")
                        _remove_pending_stop_order(entry_order_id)
                        continue
                    
                    status = order_data["status"]
                    fill_qty = order_data["fill_qty"]
                    total_qty = order_info["quantity"]
                    stop_loss_placed_qty = order_info.get("stop_loss_placed_qty", 0)
                    
                    # 如果 _query_order_status_and_fill 返回了正確的 acc_id，使用佢
                    # 否則使用原始的 acc_id
                    effective_acc_id = order_data.get("acc_id", acc_id)
                    
                    # Handle FILLED or PARTIAL_FILLED - Futu uses FILLED_ALL
                    if status == "FILLED" or status == "PARTIAL_FILLED" or status == "FILLED_ALL":
                        if fill_qty > 0:
                            # 計算有幾多新股數需要掛止蝕 (防止重複)
                            new_filled_qty = fill_qty - stop_loss_placed_qty
                            
                            if new_filled_qty > 0:
                                print(f"[StopMonitor] Entry order {entry_order_id} {status}! New fill: {new_filled_qty} shares (total filled: {fill_qty}/{total_qty}, already placed stop: {stop_loss_placed_qty}). Triggering stop order with acc_id={effective_acc_id}...")
                                
                                # 只為「新增成交股數」落 STOP order
                                result = _place_stop_order(
                                    host=host,
                                    port=port,
                                    symbol=order_info["symbol"],
                                    quantity=new_filled_qty,
                                    stop_loss_price=order_info["stop_loss_price"],
                                    acc_id=effective_acc_id,  # 使用動態獲取的 acc_id
                                    trd_env=trd_env,
                                    trade_pwd=trade_pwd,
                                    direction=order_info.get("direction", "LONG"),  # 傳入方向
                                )
                                
                                if result.get("success"):
                                    print(f"[StopMonitor] STOP order triggered successfully for {new_filled_qty} shares: {result.get('stop_order_id')}")
                                    
                                    # 只喺成功發送之後，先可以更新 stop_loss_placed_qty
                                    new_stop_placed_qty = stop_loss_placed_qty + new_filled_qty
                                    _update_pending_stop_order(entry_order_id, {
                                        "stop_loss_placed_qty": new_stop_placed_qty,
                                        "filled_qty": fill_qty
                                    })
                                    
                                    # 如果完全成交咗 (fill_qty >= total_qty)，移除 pending
                                    if fill_qty >= total_qty:
                                        _remove_pending_stop_order(entry_order_id)
                                        print(f"[StopMonitor] Order {entry_order_id} fully filled and stopped, removed from pending")
                                    else:
                                        print(f"[StopMonitor] Partial fill - filled: {fill_qty}/{total_qty}, stop placed: {new_stop_placed_qty}, will continue monitoring")
                                else:
                                    # 失敗！更新重試次數，等下一個 loop 重試
                                    retry_count = order_info.get("stop_loss_retry_count", 0)
                                    new_retry_count = retry_count + 1
                                    
                                    if new_retry_count >= MAX_STOP_LOSS_RETRIES:
                                        # 超過最大重試次數，標記為需要人工處理
                                        print(f"[StopMonitor] STOP order failed {new_retry_count} times. Marking as FAILED_NEED_MANUAL.")
                                        _update_pending_stop_order(entry_order_id, {
                                            "stop_loss_retry_count": new_retry_count,
                                            "status": "FAILED_NEED_MANUAL",
                                            "last_error": result.get('error'),
                                            "failed_at": datetime.now(timezone.utc).isoformat()
                                        })
                                        _remove_pending_stop_order(entry_order_id)
                                    else:
                                        # 未超限，等下一個 loop 重試
                                        print(f"[StopMonitor] Failed to trigger STOP order: {result.get('error')}. Retry {new_retry_count}/{MAX_STOP_LOSS_RETRIES}")
                                        _update_pending_stop_order(entry_order_id, {
                                            "stop_loss_retry_count": new_retry_count,
                                            "last_retry_at": datetime.now(timezone.utc).isoformat()
                                        })
                            else:
                                # 無新成交股數需要掛止蝕
                                if fill_qty >= total_qty:
                                    _remove_pending_stop_order(entry_order_id)
                                    print(f"[StopMonitor] Order {entry_order_id} fully filled, stop already placed for all, removing")
                                else:
                                    print(f"[StopMonitor] Order {entry_order_id} fill_qty={fill_qty}, stop already placed for {stop_loss_placed_qty}, waiting for more fills")
                        else:
                            # fill_qty = 0 but status is FILLED/PARTIAL - error state
                            print(f"[StopMonitor] Order {entry_order_id} status={status} but fill_qty=0, removing from pending")
                            _remove_pending_stop_order(entry_order_id)
                    
                    elif status in ["CANCELLED", "CANCELLED_PART", "FAILED", "REJECTED"]:
                        # Entry order failed/cancelled
                        if fill_qty == 0:
                            # 完全冇成交，取消咗就取消，移除 pending
                            print(f"[StopMonitor] Entry order {entry_order_id} status: {status}, no fills, removing from pending")
                            _remove_pending_stop_order(entry_order_id)
                        elif fill_qty == stop_loss_placed_qty:
                            # 所有已成交股數都已經掛好止蝕單，可以移除
                            print(f"[StopMonitor] Entry order {entry_order_id} status: {status}, all filled shares ({fill_qty}) have stop orders placed, removing from pending")
                            _remove_pending_stop_order(entry_order_id)
                        else:
                            # 部分成交但未全部掛好止蝕單，標記為需要人工處理
                            print(f"[StopMonitor] Entry order {entry_order_id} status: {status}, filled: {fill_qty}, stop placed: {stop_loss_placed_qty}. Marking as NEED_MANUAL.")
                            _update_pending_stop_order(entry_order_id, {
                                "status": "CANCELLED_NEED_MANUAL",
                                "cancelled_at": datetime.now(timezone.utc).isoformat()
                            })
                            _remove_pending_stop_order(entry_order_id)
                    
                    # Else: SUBMITTED, etc - keep monitoring
            
            finally:
                ctx.close()
        
        except Exception as e:
            print(f"[StopMonitor] Error in monitor loop: {e}")
        
        time.sleep(check_interval)
    
    print(f"[StopMonitor] Background monitor stopped")


def start_background_monitor(host: str, port: int):
    """啟動 background monitor thread."""
    global _monitor_thread
    
    if _monitor_thread is not None and _monitor_thread.is_alive():
        print("[StopMonitor] Monitor already running")
        return
    
    _monitor_running.set()
    _monitor_thread = threading.Thread(
        target=_monitor_loop,
        args=(host, port),
        daemon=True,
        name="StopOrderMonitor"
    )
    _monitor_thread.start()
    print("[StopMonitor] Background monitor thread started")


def stop_background_monitor():
    """停止 background monitor thread."""
    global _monitor_thread
    
    _monitor_running.clear()
    if _monitor_thread is not None:
        _monitor_thread.join(timeout=5)
        _monitor_thread = None
    print("[StopMonitor] Background monitor stopped")


def _fetch_hkdusd_rate() -> float:
    """Fetch live HKD/USD rate from Yahoo Finance. Falls back to 1/7.78."""
    try:
        with httpx.Client(timeout=8, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = client.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/HKDUSD=X",
                params={"interval": "1d", "range": "1d"},
            )
            resp.raise_for_status()
            data = resp.json()

            # 強化 error handling：檢查 response structure
            if not data:
                print("[Futu] Empty response from Yahoo, using fallback")
                return _HKD_USD_FALLBACK

            chart_result = data.get("chart", {}).get("result")
            if not chart_result or not isinstance(chart_result, list) or len(chart_result) == 0:
                print("[Futu] No chart result in Yahoo response, using fallback")
                return _HKD_USD_FALLBACK

            meta = chart_result[0].get("meta")
            if not meta:
                print("[Futu] No meta in Yahoo chart result, using fallback")
                return _HKD_USD_FALLBACK

            price = meta.get("regularMarketPrice")
            if price is None:
                print("[Futu] No regularMarketPrice in Yahoo meta, using fallback")
                return _HKD_USD_FALLBACK

            rate = float(price)
            print(f"[Futu] HKDUSD rate: {rate}")
            return rate

    except httpx.TimeoutException:
        print(f"[Futu] Timeout fetching HKDUSD rate, using fallback {_HKD_USD_FALLBACK:.4f}")
        return _HKD_USD_FALLBACK
    except httpx.HTTPStatusError as e:
        print(f"[Futu] HTTP error fetching HKDUSD rate: {e.response.status_code}, using fallback")
        return _HKD_USD_FALLBACK
    except (KeyError, TypeError, ValueError) as e:
        print(f"[Futu] Data parsing error for HKDUSD rate ({e}), using fallback")
        return _HKD_USD_FALLBACK
    except Exception as e:
        print(f"[Futu] Failed to fetch HKDUSD rate ({e}), using fallback {_HKD_USD_FALLBACK:.4f}")
        return _HKD_USD_FALLBACK


def _parse_futu_code(code: str) -> Tuple[str, str]:
    """
    Convert Futu code to (symbol, asset_type).
      HK.00700 → ('700.HK', 'STOCK')
      US.AAPL  → ('AAPL',   'STOCK')
    """
    parts = code.split(".", 1)
    if len(parts) != 2:
        return code, "STOCK"

    market, ticker = parts
    if market == "HK":
        stripped = ticker.lstrip("0") or ticker
        return f"{stripped}.HK", "STOCK"
    elif market == "US":
        return ticker, "STOCK"
    else:
        return f"{ticker}.{market}", "STOCK"


def _to_futu_code(symbol: str) -> str:
    """
    Convert our symbol format to Futu code format.
      AAPL → US.AAPL
      00700 → HK.00700 or HK.700
      700.HK → HK.00700
    """
    symbol = symbol.upper().strip()
    
    # Already has market suffix
    if symbol.endswith(".HK"):
        code = symbol.replace(".HK", "")
        # Pad to 5 digits
        if len(code) < 5:
            code = code.zfill(5)
        return f"HK.{code}"
    
    # US stock (no suffix, all letters)
    if symbol.isalpha():
        return f"US.{symbol}"
    
    # HK stock (numeric)
    if symbol.isdigit():
        code = symbol.zfill(5)
        return f"HK.{code}"
    
    # Fallback
    return f"US.{symbol}"


def _unlock_trade(ctx, trade_pwd: str) -> bool:
    """
    解鎖交易功能，需要輸入交易密碼
    """
    import futu
    
    if not trade_pwd:
        print("[Order] No trade password configured, skipping unlock")
        return True  # No password means no unlock needed
    
    ret_unlock, _ = ctx.unlock_trade(trade_pwd)
    if ret_unlock != futu.RET_OK:
        print(f"[Order] unlock_trade failed with code: {ret_unlock}")
        return False
    print("[Order] Trade unlocked successfully")
    return True


def _place_order(
    symbol: str,
    price: float,
    quantity: int,
    order_type: str,
    side: str,
    host: str,
    port: int,
    trade_pwd: str = "",
    trd_env: Optional[str] = None,  # 如果為None，會自動使用動態環境
    stop_loss_price: Optional[float] = None,
    time_in_force: str = "DAY",  # DAY / GTC / GTD
    expire_date: Optional[str] = None,  # YYYY-MM-DD, only for GTD
    trigger_price: Optional[float] = None,  # Stop Entry觸發價
) -> Dict:
    """
    Place an order via Futu OpenD.

    Args:
        symbol: Stock symbol (e.g., AAPL, 00700, 700.HK)
        price: Order price (for LIMIT orders)
        quantity: Number of shares
        order_type: "LIMIT" or "MARKET"
        side: "BUY" or "SELL"
        host: OpenD host
        port: OpenD port
        trade_pwd: Trading password
        trd_env: "SIMULATE" or "REAL". 如果為None，會使用動態環境變數
        stop_loss_price: Optional stop loss price to place automatic STOP order (only for BUY orders)
        time_in_force: "DAY" (當日有效) / "GTC" (撤單前有效) / "GTD" (指定日期前有效)
        expire_date: Format "YYYY-MM-DD", only used when time_in_force="GTD"

    Returns:
        Dict with order_id, stop_order_id, status and message
    """
    # 使用動態環境 (如果無傳入參數)
    if trd_env is None:
        trd_env = _get_trade_env()
    try:
        import futu
    except ImportError:
        raise ImportError("futu-api not installed. Run: pip install futu-api")
    
    # Convert symbol to Futu format
    futu_code = _to_futu_code(symbol)
    print(f"[Order] Placing order: {symbol} -> {futu_code}")
    
    # Determine market from symbol
    if futu_code.startswith("HK."):
        market = futu.TrdMarket.HK
    else:  # US
        market = futu.TrdMarket.US
    
    # Create trade context
    ctx = futu.OpenSecTradeContext(filter_trdmarket=market, host=host, port=port)
    try:
        # Unlock trade first
        if not _unlock_trade(ctx, trade_pwd):
            raise ValueError("Failed to unlock trade - check your trading password")
        
        # Determine trade environment
        trd_env_enum = futu.TrdEnv.SIMULATE if trd_env.upper() == "SIMULATE" else futu.TrdEnv.REAL
        
        # Get account list
        ret_acc, acc_list = ctx.get_acc_list()
        if ret_acc != futu.RET_OK:
            raise ValueError(f"get_acc_list failed: {acc_list}")
        
        # Find appropriate account (SIMULATE or REAL based on trd_env)
        acc_ids = [
            int(row["acc_id"])
            for _, row in acc_list.iterrows()
            if str(row.get("trd_env", "")).upper() == trd_env.upper()
            and str(row.get("acc_status", "")).upper() == "ACTIVE"
        ]
        
        if not acc_ids:
            raise ValueError(f"No {trd_env} ACTIVE accounts found for market {market}")
        
        acc_id = acc_ids[0]
        
        # Determine order type
        # STOP order: 使用 trigger_price (Stop Entry 單)
        # 如果有 trigger_price，即使 order_type 是 MARKET 也用 STOP 類型
        if trigger_price:
            order_type_enum = futu.OrderType.STOP
            # Stop Entry 單: aux_price = 觸發價, price = 執行價
            # 如果是 MARKET，執行價設為 0（以市價成交）
            if order_type.upper() == "MARKET":
                price = 0  # 市價成交
            else:
                pass  # 用戶指定的執行價（保持 price 不變）
            print(f"[Order] Using STOP order type with trigger_price=${trigger_price}, price=${price}")
        elif order_type.upper() == "MARKET":
            order_type_enum = futu.OrderType.MARKET
            # Market order uses 0 as price
            price = 0
        else:
            # 根據市場同交易環境選擇限價單類型
            if market == futu.TrdMarket.US:
                # 美股不支持 ABSOLUTE_LIMIT，LIMIT 單改為 MARKET
                order_type_enum = futu.OrderType.MARKET
                price = 0
                print(f"[Order] US stock LIMIT -> MARKET (US stocks don't support LIMIT orders)")
            else:
                # 港股：SIMULATE 用 NORMAL，REAL 用 ABSOLUTE_LIMIT
                if trd_env_enum == futu.TrdEnv.SIMULATE:
                    order_type_enum = futu.OrderType.NORMAL
                    print(f"[Order] SIMULATE environment: using NORMAL order type")
                else:
                    order_type_enum = futu.OrderType.ABSOLUTE_LIMIT
                    print(f"[Order] REAL environment: using ABSOLUTE_LIMIT order type")
                # price 保持不變（已在前面設定）

        # Determine time_in_force
        if time_in_force.upper() == "GTC":
            time_in_force_enum = futu.TimeInForce.GTC
        elif time_in_force.upper() == "GTD" and expire_date and expire_date.strip():
            time_in_force_enum = futu.TimeInForce.GTD
        else:
            time_in_force_enum = futu.TimeInForce.DAY
        
        # Determine side
        if side.upper() == "BUY":
            side_enum = futu.TrdSide.BUY
        else:
            side_enum = futu.TrdSide.SELL
        
        # Place the order
        place_order_kwargs = {
            "price": price,
            "qty": quantity,
            "code": futu_code,
            "trd_side": side_enum,
            "order_type": order_type_enum,
            "trd_env": trd_env_enum,
            "acc_id": acc_id,
            "time_in_force": time_in_force_enum,
        }

        # 對於有 trigger_price 的訂單（Stop Entry / 突破單）：
        # - aux_price = 觸發價 (triggerPrice)
        # - price = 執行價（如果是 MARKET 則為 0）
        if trigger_price:
            place_order_kwargs["price"] = price  # 執行價（MARKET=0, 否則用戶指定）
            place_order_kwargs["aux_price"] = trigger_price  # 觸發價
            print(f"[Order] STOP order: price=${price}, aux_price=${trigger_price}")

        # For GTD orders, set expire date
        if time_in_force.upper() == "GTD" and expire_date and expire_date.strip():
            # expire_date format should be YYYY-MM-DD HH:MM:SS
            expire_date_str = expire_date.strip()
            place_order_kwargs["expire_date"] = f"{expire_date_str} 23:59:59"

        ret, data = ctx.place_order(**place_order_kwargs)
        
        print(f"[Order] place_order ret={ret}, data={data}")
        
        if ret != futu.RET_OK:
            raise ValueError(f"Place order failed: {data}")
        
        # Extract order ID from response
        order_id = None
        stop_order_id = None
        if data is not None and not data.empty:
            order_id = str(data.iloc[0].get("order_id", ""))

        # If stop_loss_price is provided,
        # add to pending list for background monitor to trigger after FILLED
        if stop_loss_price and order_id:
            print(f"[Order] Adding stop loss to pending queue: order_id={order_id}, stop_price=${stop_loss_price}, side={side}")
            
            # Determine direction from side
            order_direction = "SHORT" if side.upper() == "SELL" else "LONG"
            
            # Add to pending stop orders - background monitor will trigger when entry order FILLED
            _add_pending_stop_order(
                entry_order_id=order_id,
                order_info={
                    "symbol": symbol,
                    "quantity": quantity,
                    "stop_loss_price": stop_loss_price,
                    "futu_code": futu_code,
                    "acc_id": acc_id,
                    "trd_env": trd_env,
                    "direction": order_direction,  # 保存方向
                }
            )
            
            return {
                "order_id": order_id,
                "status": "submitted_pending_stop",
                "message": f"Entry order submitted ({side} {quantity} {symbol} @ ${price}). Stop loss order ({'BUY' if side.upper() == 'SELL' else 'SELL'} {quantity} @ ${stop_loss_price}) will be triggered automatically when entry order is FILLED.",
            }
        
        return {
            "order_id": order_id,
            "status": "submitted",
            "message": f"Order submitted successfully ({side} {quantity} {symbol} @ ${price})"
        }
        
    finally:
        ctx.close()


def _fetch_account_balance(host: str, port: int, trade_pwd: str = "") -> Optional[Dict]:
    """
    Fetch account balance from Futu OpenD.
    Returns balance in USD for US stocks account.
    """
    try:
        import futu
    except ImportError:
        raise ImportError("futu-api not installed. Run: pip install futu-api")

    # Use US market to get USD account
    ctx = futu.OpenSecTradeContext(filter_trdmarket=futu.TrdMarket.US, host=host, port=port)
    try:
        if trade_pwd:
            ret_unlock, _ = ctx.unlock_trade(trade_pwd)
            if ret_unlock != futu.RET_OK:
                raise ValueError("unlock_trade failed — check your trading password")

        ret_acc, acc_list = ctx.get_acc_list()
        if ret_acc != futu.RET_OK:
            raise ValueError(f"get_acc_list failed: {acc_list}")

        # Find REAL + ACTIVE US account
        active_us_acc_ids = [
            int(row["acc_id"])
            for _, row in acc_list.iterrows()
            if str(row.get("trd_env", "")).upper() == "REAL"
            and str(row.get("acc_status", "")).upper() == "ACTIVE"
            and row.get("acc_type") in [2, "2"]  # US account type
        ]

        # If no US account, try first active account
        if not active_us_acc_ids:
            active_us_acc_ids = [
                int(row["acc_id"])
                for _, row in acc_list.iterrows()
                if str(row.get("trd_env", "")).upper() == "REAL"
                and str(row.get("acc_status", "")).upper() == "ACTIVE"
            ]

        print(f"[Futu] Looking for account balance, acc_ids: {active_us_acc_ids}")

        if not active_us_acc_ids:
            raise ValueError("No REAL+ACTIVE accounts found")

        # Try to get USD balance from first account
        for acc_id in active_us_acc_ids:
            ret, data = ctx.accinfo_query(
                trd_env=futu.TrdEnv.REAL,
                acc_id=acc_id,
                currency=futu.Currency.USD,
                refresh_cache=True,
            )
            print(f"[Futu] acc_id={acc_id} accinfo_query ret={ret}")
            if ret == futu.RET_OK and not data.empty:
                row = data.iloc[0]
                return {
                    "currency": "USD",
                    "cash": float(row.get("cash", 0) or 0),
                    "market_value": float(row.get("market_value", 0) or 0),
                    "total_assets": float(row.get("total_assets", 0) or 0),
                    "buying_power": float(row.get("buying_power", 0) or 0),
                    "withdrawable": float(row.get("withdrawable", 0) or 0),
                }

        return None
    finally:
        ctx.close()


# Pydantic models
class Position(BaseModel):
    symbol: str
    name: str
    quantity: float
    cost_price: Optional[float] = None
    current_price: Optional[float] = None
    asset_type: str = "STOCK"


class OrderRequest(BaseModel):
    symbol: str
    price: float
    quantity: int
    order_type: str = "LIMIT"  # "LIMIT" / "STOP" / "MARKET"
    side: str = "BUY"  # "BUY" or "SELL"
    time_in_force: str = "DAY"  # "DAY" (當日有效) / "GTC" (撤單前有效) / "GTD" (指定日期前有效)
    expire_date: Optional[str] = None  # Format: "YYYY-MM-DD", only used when time_in_force="GTD"
    stop_loss_price: Optional[float] = None  # 止蝕價（倉位成交後自動觸發止蝕單）
    trigger_price: Optional[float] = None  # 觸發價（Stop Entry單用：突破呢個價自動成交）
    remark: Optional[str] = None


class OrderResponse(BaseModel):
    success: bool
    order_id: Optional[str] = None
    stop_order_id: Optional[str] = None
    status: Optional[str] = None
    message: str
    timestamp: str


class PendingStopOrder(BaseModel):
    entry_order_id: str
    symbol: str
    quantity: int
    filled_qty: Optional[int] = 0  # 已成交既數量
    stop_loss_price: float
    status: str  # "pending", "partial", "triggered", "failed", "cancelled"
    created_at: str


class PendingStopOrdersResponse(BaseModel):
    success: bool
    pending_orders: List[PendingStopOrder]
    timestamp: str


class SyncResponse(BaseModel):
    success: bool
    positions: List[Position]
    message: str
    timestamp: str


class AccountBalance(BaseModel):
    currency: str
    cash: float
    market_value: float
    total_assets: float
    buying_power: float
    withdrawable: float


class BalanceResponse(BaseModel):
    success: bool
    account_balance: Optional[AccountBalance]
    message: str
    timestamp: str


# FastAPI app
app = FastAPI(title="Futu Broker API", version="1.0.0")


@app.on_event("startup")
async def startup_event():
    """App啟動時 load 舊有 pending stops 並啟動 background monitor."""
    print("[Startup] Step 1: Loading pending stops...")
    # 從 file load 舊有既 pending stop orders
    _init_pending_stops_from_file()
    
    print("[Startup] Step 2: Setting trade env...")
    # 初始化交易環境 (從環境變數讀取，預設SIMULATE)
    env_from_env = os.getenv("TRADE_ENV", "SIMULATE").upper()
    _set_trade_env(env_from_env)
    
    print("[Startup] Step 3: Restoring pending stops from order history...")
    # 雙重保險：Startup 時從 order_history.json 恢復未成交訂單
    host = _get_futu_host()
    port = int(os.getenv("FUTU_PORT", "11111"))
    restored_count = _restore_pending_stops_from_history(host, port, env_from_env)
    if restored_count > 0:
        print(f"[Startup] RESTORED {restored_count} pending stop orders from history!")
    
    print("[Startup] Step 4: Starting background monitor...")
    start_background_monitor(host, port)
    
    print("[Startup] Step 5: Starting OpenD watchdog...")
    start_watchdog()
    
    print("[Startup] Done!")


@app.on_event("shutdown")
async def shutdown_event():
    """App關閉時停止background monitor 和 watchdog."""
    stop_background_monitor()
    stop_watchdog()


def _fetch_positions(host: str, port: int, trade_pwd: str = "") -> List[Dict]:
    """
    Fetch all open positions from OpenD via OpenSecTradeContext (supports HK + US in one call).
    Always queries REAL + ACTIVE accounts (ignores SIMULATE/REAL environment setting).
    Returns list of position dicts.
    """
    try:
        import futu
    except ImportError:
        raise ImportError("futu-api not installed. Run: pip install futu-api")

    # Try both HK and US markets to get all positions
    all_positions = []
    
    for market in [futu.TrdMarket.HK, futu.TrdMarket.US]:
        market_name = "HK" if market == futu.TrdMarket.HK else "US"
        print(f"[Futu] Trying {market_name} market...")
        try:
            ctx = futu.OpenSecTradeContext(filter_trdmarket=market, host=host, port=port)
            try:
                if trade_pwd:
                    ret_unlock, _ = ctx.unlock_trade(trade_pwd)
                    if ret_unlock != futu.RET_OK:
                        print(f"[Futu] unlock_trade failed for {market_name}, skipping market")
                        continue

                ret_acc, acc_list = ctx.get_acc_list()
                if ret_acc != futu.RET_OK:
                    print(f"[Futu] get_acc_list failed for {market_name}: {acc_list}")
                    continue
                print(f"[Futu] {market_name} acc_list: {acc_list.to_dict()}")

                # Only use REAL + ACTIVE accounts
                active_acc_ids = [
                    int(row["acc_id"])
                    for _, row in acc_list.iterrows()
                    if str(row.get("trd_env", "")).upper() == "REAL"
                    and str(row.get("acc_status", "")).upper() == "ACTIVE"
                ]
                print(f"[Futu] {market_name} REAL+ACTIVE acc_ids: {active_acc_ids}")

                if not active_acc_ids:
                    print(f"[Futu] No REAL+ACTIVE accounts for {market_name}")
                    continue

                for acc_id in active_acc_ids:
                    ret, data = ctx.position_list_query(
                        trd_env=futu.TrdEnv.REAL,
                        acc_id=acc_id,
                        refresh_cache=True,
                    )
                    print(f"[Futu] acc_id={acc_id} positions ret={ret}, rows={len(data) if ret == futu.RET_OK else 'ERR'}")
                    if ret != futu.RET_OK or data.empty:
                        continue
                    for _, row in data.iterrows():
                        qty = float(row.get("qty", 0))
                        if qty <= 0:
                            continue
                        code = str(row.get("code", ""))
                        symbol, asset_type = _parse_futu_code(code)
                        cost_price = float(row.get("cost_price", 0) or 0)
                        nominal_price = float(row.get("nominal_price", 0) or 0)
                        print(f"[Futu] Position found: {symbol} qty={qty}")
                        all_positions.append({
                            "symbol": symbol,
                            "name": str(row.get("stock_name", symbol)),
                            "quantity": qty,
                            "cost_price": cost_price if cost_price > 0 else None,
                            "current_price": nominal_price if nominal_price > 0 else None,
                            "asset_type": asset_type,
                        })
            finally:
                ctx.close()
        except Exception as e:
            print(f"[Futu] Error fetching {market_name} positions: {e}")
            continue
    
    return all_positions


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ============================================================================
# 交易環境 API
# ============================================================================
class EnvResponse(BaseModel):
    success: bool
    trade_env: str
    timestamp: str


class SetEnvRequest(BaseModel):
    trade_env: str


@app.get("/api/env", response_model=EnvResponse)
def get_env():
    """取得當前交易環境."""
    return EnvResponse(
        success=True,
        trade_env=_get_trade_env(),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/api/env", response_model=EnvResponse, dependencies=[Depends(verify_api_key)])
def set_env(request: SetEnvRequest):
    """設定當前交易環境 (SIMULATE 或 REAL)."""
    try:
        _set_trade_env(request.trade_env)
        return EnvResponse(
            success=True,
            trade_env=_get_trade_env(),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/positions", response_model=SyncResponse, dependencies=[Depends(verify_api_key)])
def get_positions():
    """
    Get all stock/ETF positions from Futu/Moomoo.
    Converts HKD prices to USD.
    """
    # Get config from environment
    host = _get_futu_host()
    port = int(os.getenv("FUTU_PORT", "11111"))
    trade_pwd = os.getenv("FUTU_TRADE_PWD", "")

    try:
        assets = _fetch_positions(host, port, trade_pwd)
        
        # Convert HKD-priced holdings to USD
        if any(a["symbol"].endswith(".HK") for a in assets):
            hkdusd = _fetch_hkdusd_rate()
            for a in assets:
                if a["symbol"].endswith(".HK"):
                    if a["current_price"] is not None:
                        a["current_price"] = a["current_price"] * hkdusd
                    if a["cost_price"] is not None:
                        a["cost_price"] = a["cost_price"] * hkdusd

        positions = [Position(**a) for a in assets]
        
        return SyncResponse(
            success=True,
            positions=positions,
            message=f"Synced {len(positions)} positions",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except ImportError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to OpenD at {host}:{port}. Make sure OpenD is running. Error: {e}"
        )


@app.get("/api/balance", response_model=BalanceResponse, dependencies=[Depends(verify_api_key)])
def get_account_balance():
    """
    Get account balance in USD from Futu/Moomoo US account.
    """
    # Get config from environment
    host = _get_futu_host()
    port = int(os.getenv("FUTU_PORT", "11111"))
    trade_pwd = os.getenv("FUTU_TRADE_PWD", "")

    try:
        balance = _fetch_account_balance(host, port, trade_pwd)
        
        if balance:
            return BalanceResponse(
                success=True,
                account_balance=AccountBalance(**balance),
                message=f"Account balance fetched",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        else:
            return BalanceResponse(
                success=False,
                account_balance=None,
                message="No account balance found",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
    except ImportError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to OpenD at {host}:{port}. Make sure OpenD is running. Error: {e}"
        )


@app.post("/api/order", response_model=OrderResponse, dependencies=[Depends(verify_api_key)])
def place_order(order: OrderRequest):
    """
    Place a buy/sell order via Futu OpenD.

    IMPORTANT: This endpoint uses SIMULATE (paper trading) environment by default.
    To switch to REAL trading, set the environment variable TRADE_ENV=REAL.

    Required fields:
    - symbol: Stock symbol (e.g., AAPL, 00700, 700.HK)
    - price: Order price (ignored for MARKET/STOP orders)
    - quantity: Number of shares

    Optional fields:
    - order_type: "LIMIT" (default) / "MARKET" / "STOP" (Stop Entry)
    - side: "BUY" (default) / "SELL"
    - time_in_force: "DAY" (當日有效) / "GTC" (撤單前有效) / "GTD" (指定日期前有效)
    - expire_date: "YYYY-MM-DD", only used when time_in_force="GTD"
    - stop_loss_price: Optional stop loss price (entry成交後自動觸發止蝕單)
    - trigger_price: Only for order_type="STOP" (Stop Entry)，當現價觸及呢個價自動成交
    """
    # Get config from environment
    host = _get_futu_host()
    port = int(os.getenv("FUTU_PORT", "11111"))
    trade_pwd = os.getenv("FUTU_TRADE_PWD", "")
    
    # 使用動態交易環境 (而非環境變數)
    trd_env = _get_trade_env()
    
    # Warn if using REAL trading
    if trd_env.upper() == "REAL":
        print(f"[WARNING] REAL trading enabled! Order will use real money!")
    
    print(f"[Order] Request: {order.model_dump_json()}")
    print(f"[Order] Trade environment: {trd_env}")
    print(f"[Order] Time in force: {order.time_in_force}, expire_date: {order.expire_date}")
    print(f"[Order] Order type: {order.order_type}, trigger_price: {order.trigger_price}, price: {order.price}")

    try:
        result = _place_order(
            symbol=order.symbol,
            price=order.price,
            quantity=order.quantity,
            order_type=order.order_type,
            side=order.side,
            host=host,
            port=port,
            trade_pwd=trade_pwd,
            trd_env=trd_env,
            stop_loss_price=order.stop_loss_price,
            time_in_force=order.time_in_force,
            expire_date=order.expire_date,
            trigger_price=order.trigger_price,
        )
        
        return OrderResponse(
            success=True,
            order_id=result.get("order_id"),
            stop_order_id=result.get("stop_order_id"),
            status=result.get("status"),
            message=result.get("message", "Order placed successfully"),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except ImportError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to place order: {str(e)}"
        )


@app.get("/api/pending-stops", response_model=PendingStopOrdersResponse, dependencies=[Depends(verify_api_key)])
def get_pending_stop_orders():
    """
    取得所有有待觸發止蝕單狀態.
    返回所有處於 pending 狀態既 entry orders，等 Frontend 可以顯示俾用戶睇。
    """
    pending = _get_pending_stop_orders()
    
    pending_list = [
        PendingStopOrder(
            entry_order_id=order_id,
            symbol=info["symbol"],
            quantity=info["quantity"],
            filled_qty=info.get("filled_qty", 0),
            stop_loss_price=info["stop_loss_price"],
            status="pending" if info.get("filled_qty", 0) == 0 else "partial"
        )
        for order_id, info in pending.items()
    ]
    
    return PendingStopOrdersResponse(
        success=True,
        pending_orders=pending_list,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ============================================================================
# 行情查詢 API (使用行情接口，唔需要加密)
# ============================================================================
class StockQuote(BaseModel):
    code: str
    name: str
    last_price: float
    open_price: float
    high_price: float
    low_price: float
    volume: int
    # 技術指標
    ema10: Optional[float] = None
    ema20: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    atr14: Optional[float] = None
    change: Optional[float] = None
    change_percent: Optional[float] = None


class KLine(BaseModel):
    time: int  # Unix timestamp
    open: float
    high: float
    low: float
    close: float
    volume: int


class QuoteResponse(BaseModel):
    success: bool
    quotes: List[StockQuote]
    timestamp: str


class KLineResponse(BaseModel):
    success: bool
    klines: List[KLine]
    timestamp: str


@app.get("/api/quote/{codes}", response_model=QuoteResponse)
def get_stock_quote(codes: str):
    """
    查詢股票報價 (使用行情接口，不需要加密).
    codes: 逗號分隔嘅股票代碼，例如 "HK.00700,HK.00700,US.AAPL"
    
    注意：某些市場需要先 subscribe 先可以拎到行情
    """
    host = _get_futu_host()
    port = int(os.getenv("FUTU_PORT", "11111"))
    
    import sys
    print(f"[Quote] === START ===", flush=True)
    print(f"[Quote] codes='{codes}'", flush=True)
    print(f"[Quote] host={host}, port={port}", flush=True)
    sys.stdout.flush()

    try:
        import futu

        # 分割代碼並清理
        code_list = [c.strip() for c in codes.split(",") if c.strip()]
        print(f"[Quote] code_list={code_list}", flush=True)

        print(f"[Quote] Creating OpenQuoteContext...", flush=True)
        sys.stdout.flush()
        ctx = futu.OpenQuoteContext(host=host, port=port)
        try:
            # 先 subscribe 股票行情（某些市場需要）
            print(f"[Quote] Subscribing to {len(code_list)} securities...", flush=True)
            sys.stdout.flush()
            
            # 確定市場類型
            market_list = set()
            for code in code_list:
                if code.startswith("HK."):
                    market_list.add(futu.Market.HK)
                elif code.startswith("US."):
                    market_list.add(futu.Market.US)
                elif code.startswith("SH."):
                    market_list.add(futu.Market.SH)
                elif code.startswith("SZ."):
                    market_list.add(futu.Market.SZ)
            
            # Subscribe 每個市場
            for market in market_list:
                ret_sub, _ = ctx.subscribe(code_list, market)
                print(f"[Quote] Subscribe ret={ret_sub}", flush=True)
                sys.stdout.flush()
            
            # 等一下俾 OpenD 推送數據
            import time
            time.sleep(0.5)
            
            # 用 get_market_snapshot 拎行情
            print(f"[Quote] Calling get_market_snapshot...", flush=True)
            sys.stdout.flush()
            ret, data = ctx.get_market_snapshot(code_list)
            print(f"[Quote] ret={ret}, data={data}", flush=True)
            sys.stdout.flush()
            
            if ret != futu.RET_OK:
                error_msg = f"Market snapshot failed (ret={ret}): {data}"
                print(f"[Quote] ERROR: {error_msg}", flush=True)
                raise HTTPException(status_code=400, detail=error_msg)
            
            if data is None or (hasattr(data, 'empty') and data.empty):
                error_msg = f"No snapshot data returned for {code_list}"
                print(f"[Quote] ERROR: {error_msg}", flush=True)
                raise HTTPException(status_code=400, detail=error_msg)

            # 為每個股票計算技術指標
            quotes = []
            for _, row in data.iterrows():
                code = str(row.get("code", ""))
                
                # 計算技術指標
                ema10, ema20, sma50, sma200, atr14 = _calculate_technical_indicators(ctx, code)
                
                # 計算 change
                last_price = float(row.get("last_price", 0) or 0)
                prev_close = float(row.get("prev_close_price", 0) or 0)
                change = last_price - prev_close if prev_close > 0 else 0
                change_percent = (change / prev_close * 100) if prev_close > 0 else 0
                
                quotes.append(StockQuote(
                    code=code,
                    name=str(row.get("name", "")),
                    last_price=last_price,
                    open_price=float(row.get("open_price", 0) or 0),
                    high_price=float(row.get("high_price", 0) or 0),
                    low_price=float(row.get("low_price", 0) or 0),
                    volume=int(row.get("volume", 0) or 0),
                    ema10=ema10,
                    ema20=ema20,
                    sma50=sma50,
                    sma200=sma200,
                    atr14=atr14,
                    change=change,
                    change_percent=change_percent,
                ))

            print(f"[Quote] Success, returning {len(quotes)} quotes", flush=True)
            sys.stdout.flush()
            return QuoteResponse(
                success=True,
                quotes=quotes,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        finally:
            ctx.close()
            print(f"[Quote] Context closed", flush=True)
            sys.stdout.flush()

    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=500, detail="futu-api not installed")
    except Exception as e:
        import traceback
        error_detail = f"[Quote] Exception: {e}"
        print(error_detail, flush=True)
        print(traceback.format_exc(), flush=True)
        sys.stdout.flush()
        raise HTTPException(status_code=500, detail=str(e))


def _calculate_technical_indicators(ctx, code: str) -> Tuple:
    """
    從 K 線數據計算技術指標 (EMA, SMA, ATR)
    返回: (ema10, ema20, sma50, sma200, atr14)
    """
    import futu
    
    try:
        # 拎 K 線數據（預設365日）
        ret, data, page_key = ctx.request_history_kline(
            code=code,
            start=None,  # 自動計算起始日期
            end=None,
            ktype=futu.KLType.K_DAY,
            autype='qfq',  # 前復權
        )
        
        if ret != futu.RET_OK or data is None or data.empty:
            print(f"[Quote] Failed to get kline for {code}: {data}")
            return (None, None, None, None, None)
        
        print(f"[Quote] Got {len(data)} klines for {code}")
        
        # 提取數據 - futu 用 time_key 欄位
        time_col = 'time_key'
        closes = data['close'].tolist() if 'close' in data.columns else []
        highs = data['high'].tolist() if 'high' in data.columns else []
        lows = data['low'].tolist() if 'low' in data.columns else []
        
        # 轉換時間為 timestamp
        from datetime import datetime
        def to_timestamp(time_str):
            if not time_str:
                return 0
            try:
                dt = datetime.strptime(str(time_str), '%Y-%m-%d %H:%M:%S')
                return int(dt.timestamp())
            except:
                return 0
        
        data['_timestamp'] = data[time_col].apply(to_timestamp)
        
        if len(closes) < 10:
            return (None, None, None, None, None)
        
        # 計算 EMA
        ema10 = _calculate_ema(closes, 10) if len(closes) >= 10 else None
        ema20 = _calculate_ema(closes, 20) if len(closes) >= 20 else None
        sma50 = _calculate_sma(closes, 50) if len(closes) >= 50 else None
        sma200 = _calculate_sma(closes, 200) if len(closes) >= 200 else None
        
        # 計算 ATR
        atr14 = _calculate_atr(highs, lows, closes, 14) if len(closes) >= 15 else None
        
        return (ema10, ema20, sma50, sma200, atr14)
        
    except Exception as e:
        print(f"[Quote] Error calculating indicators for {code}: {e}")
        return (None, None, None, None, None)


def _calculate_sma(data: list, period: int) -> Optional[float]:
    """計算簡單移動平均線"""
    if len(data) < period:
        return None
    return sum(data[-period:]) / period


def _calculate_ema(data: list, period: int) -> Optional[float]:
    """計算指數移動平均線"""
    if len(data) < period:
        return None
    
    # 初始 EMA 係頭 period 日的平均
    ema = sum(data[:period]) / period
    multiplier = 2 / (period + 1)
    
    for price in data[period:]:
        ema = (price - ema) * multiplier + ema
    
    return ema


def _calculate_atr(highs: list, lows: list, closes: list, period: int) -> Optional[float]:
    """計算平均真實波幅 (ATR)"""
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return None
    
    tr_values = []
    for i in range(1, len(closes)):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]
        
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        tr_values.append(tr)
    
    if len(tr_values) < period:
        return None
    
    return sum(tr_values[-period:]) / period


@app.get("/api/kline/{code}", response_model=KLineResponse)
def get_stock_kline(
    code: str,
    days: int = 365,
    ktype: str = "DAY"
):
    """
    獲取股票 K 線數據
    code: 股票代碼，例如 "HK.00700"
    days: 天數 (默認 365，最大 2000)
    ktype: K線類型 DAY / WEEK / MONTH (默認 DAY)
    """
    host = _get_futu_host()
    port = int(os.getenv("FUTU_PORT", "11111"))
    
    import sys
    from datetime import datetime, timedelta
    
    # 限制最大日數
    max_days = min(days, 2000)
    start_date = (datetime.now() - timedelta(days=max_days)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    print(f"[KLine] === START === code={code}, days={days}, start={start_date}, end={end_date}", flush=True)
    sys.stdout.flush()

    try:
        import futu
        
        # 確定 K 線類型
        kt = futu.KLType.K_DAY
        if ktype.upper() == "WEEK":
            kt = futu.KLType.K_WEEK
        elif ktype.upper() == "MONTH":
            kt = futu.KLType.K_MON
        
        ctx = futu.OpenQuoteContext(host=host, port=port)
        try:
            print(f"[KLine] Calling request_history_kline...", flush=True)
            sys.stdout.flush()
            
            ret, data, page_key = ctx.request_history_kline(
                code=code,
                start=start_date,
                end=end_date,
                ktype=kt,
                autype='qfq',
            )
            
            print(f"[KLine] ret={ret}, data.rows={data.shape[0] if hasattr(data, 'shape') else 'N/A'}", flush=True)
            sys.stdout.flush()
            
            if ret != futu.RET_OK:
                error_msg = f"History kline failed (ret={ret}): {data}"
                print(f"[KLine] ERROR: {error_msg}", flush=True)
                raise HTTPException(status_code=400, detail=error_msg)
            
            if data is None or (hasattr(data, 'empty') and data.empty):
                print(f"[KLine] No kline data for {code}", flush=True)
                return KLineResponse(
                    success=True,
                    klines=[],
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            
            # 轉換數據格式 - futu 用 time_key 欄位
            klines = []
            from datetime import datetime
            def to_timestamp(time_str):
                if not time_str:
                    return 0
                try:
                    dt = datetime.strptime(str(time_str), '%Y-%m-%d %H:%M:%S')
                    return int(dt.timestamp())
                except:
                    return 0
            
            # 第一頁數據
            for _, row in data.iterrows():
                klines.append(KLine(
                    time=to_timestamp(row.get('time_key', 0)),
                    open=float(row.get('open', 0) or 0),
                    high=float(row.get('high', 0) or 0),
                    low=float(row.get('low', 0) or 0),
                    close=float(row.get('close', 0) or 0),
                    volume=int(row.get('volume', 0) or 0),
                ))
            
            # 如果有分頁，繼續拎下一頁
            total_pages = 1
            while page_key and total_pages < 20:  # 最多20頁 (2000條)
                total_pages += 1
                print(f"[KLine] Fetching page {total_pages}...", flush=True)
                
                ret, page_data, page_key = ctx.request_history_kline(
                    code=code,
                    start=start_date,
                    end=end_date,
                    ktype=kt,
                    autype='qfq',
                    page_req_key=page_key,
                )
                
                if ret != futu.RET_OK or page_data is None or page_data.empty:
                    break
                
                for _, row in page_data.iterrows():
                    klines.append(KLine(
                        time=to_timestamp(row.get('time_key', 0)),
                        open=float(row.get('open', 0) or 0),
                        high=float(row.get('high', 0) or 0),
                        low=float(row.get('low', 0) or 0),
                        close=float(row.get('close', 0) or 0),
                        volume=int(row.get('volume', 0) or 0),
                    ))
            
            print(f"[KLine] Success, returning {len(klines)} klines ({total_pages} pages)", flush=True)
            sys.stdout.flush()
            
            return KLineResponse(
                success=True,
                klines=klines,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        finally:
            ctx.close()
            print(f"[KLine] Context closed", flush=True)
            sys.stdout.flush()
            
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=500, detail="futu-api not installed")
    except Exception as e:
        import traceback
        error_detail = f"[KLine] Exception: {e}"
        print(error_detail, flush=True)
        print(traceback.format_exc(), flush=True)
        sys.stdout.flush()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
