# VCP Position Calculator

專業交易倉位計算器

## 功能

- ATR 自動計算及建議止蝕位
- 1R/2R/3R 目標價
- 風險警告
- 支援港股、美股、A股
- 富途持倉同步（可選）

## 運行

### 方式一：Docker 部署（推薦）

一次過運行前端 + 後端，自動連接本地 FutuOpenD。

```bash
cd position-calculator
docker-compose up -d
```

### 方式二：本地開發

需要同時運行前端和後端。

**Terminal 1 - 前端 + 後端：**
```bash
cd position-calculator
npm run dev & python3 backend/main.py
```

訪問 `http://localhost:3000`

### 運行方式對比

| 方式 | 前端 (Port 3000) | 後端 (Port 8000) | 富途 OpenD 連接 |
|------|-----------------|-----------------|----------------|
| Docker | ✅ | ✅ | host.docker.internal |
| 本地 | ✅ (同一 Terminal) | ✅ | 127.0.0.1 |

兩種方式都可以同時連接富途拎 data。

## 配置

```bash
cp .env.example .env  # 如果冇 .env 檔
```

編輯 `.env`：

```env
# 富途登入
FUTU_LOGIN_ACCOUNT=你的牛牛ID
FUTU_LOGIN_PWD_MD5=密碼MD5

# OpenD 連接（留空則自動檢測：Docker 用 host.docker.internal，本地用 127.0.0.1）
FUTU_HOST=
FUTU_PORT=11111
FUTU_WS_PORT=8081

# 交易密碼（富途功能需要）
FUTU_TRADE_PWD=你的交易密碼
```

> 提示：FUTU_HOST 留空即可，系統會自動檢測運行環境選擇正確嘅連接方式。

## 富途功能（可選）

**需要本地安裝 FutuOpenD**，docker-compose 會透過 `host.docker.internal` 連接本機既 OpenD。

1. [下載並安裝 FutuOpenD](https://www.futuhk.com/support/courseDetail/1140)
2. 啟動 OpenD 並登入
3. 首次使用需配置 `.env` 並訪問 `http://localhost:8081` 完成 SMS 驗證
4. OpenD 設定中開啟 WebSocket（`websocket_port=33333`）

## 停止

### Docker 部署

```bash
docker-compose stop    # 停止（唔刪除 container）
docker-compose down    # 停止並刪除 container
```

### 本地開發

喺 Terminal 按 `Ctrl + C` 停止（會同時停止前端和後端）。

## 更新

更新專案代碼後，需重新 build：

```bash
docker-compose up --build -d
```

---

## 股票代碼

| 市場 | 格式 | 例子 |
|------|------|------|
| 美股 | 直接輸入 | NVDA |
| 港股 | 純數字 | 00700 |
| A股 | 純數字 | 600519 |

---

## 疑難排解

### 富途 API 連接失敗 / 日誌權限問題

如果你遇到以下錯誤：
```
[Errno 1] Operation not permitted: '/Users/xxx/.com.futunn.FutuOpenD/Log/py_2026_03_25.log'
```

**解決方法**：

1. 喺 `.env` 入面設置 `FUTU_DISABLE_LOG=1`
2. 然後重啟服務

或者手動創建日誌目錄：
```bash
mkdir -p ~/.com.futunn.FutuOpenD/Log
chmod 755 ~/.com.futunn.FutuOpenD
chmod 755 ~/.com.futunn.FutuOpenD/Log
```

詳細說明請睇 [VPS_DEPLOYMENT_GUIDE.md](VPS_DEPLOYMENT_GUIDE.md)
