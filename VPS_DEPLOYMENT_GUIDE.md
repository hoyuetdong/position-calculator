# =============================================================================
# Position Calculator 部署指南
# 直接在主機運行（唔使用 Docker）
# =============================================================================

## 架構説明

```
┌─────────────────────────────────────────────────────────┐
│                        主機 Server                        │
│                                                          │
│  ┌──────────┐    ┌──────────────┐    ┌─────────────┐  │
│  │ OpenD    │◄───│   Backend    │◄───│   Frontend  │  │
│  │ :11111   │    │   :8000      │    │   :3000     │  │
│  └──────────┘    └──────────────┘    └──────┬──────┘  │
│                                              │          │
│                          ◄── 用戶瀏覽器 (HTTP/HTTPS)   │
└─────────────────────────────────────────────────────────┘
```

---

## 目錄結構

```
position-calculator/
├── .env                      # 環境變量（包含敏感信息）
├── .env.example              # 環境變量模板
├── README.md                  # 項目説明
├── requirements.txt           # Python 依賴
├── package.json               # Node.js 依賴
├── start.sh                   # 啟動腳本（本地用）
├── start-vps.sh               # VPS 啟動腳本
├── stop-vps.sh                # VPS 停止腳本
├── src/                       # Next.js 前端源碼
└── backend/                   # Python FastAPI 後端
    └── main.py                # 後端主程序
```

> **注意**：OpenD 係獨立安裝官方版，唔喺呢個 repo 入面。請去 [富途官網](https://openapi.futunn.com/futu-api-doc/en/opend/opend-install.html) 下載。

---

## 環境變量 (.env)

```bash
# 富途 OpenD 配置
FUTU_HOST=127.0.0.1                    # OpenD 主機 IP (本地: 127.0.0.1, VPS remote: 170.106.62.115)
FUTU_PORT=11111                        # OpenD 端口
FUTU_LOGIN_ACCOUNT=7202895              # 富途帳號
FUTU_LOGIN_PWD_MD5=eeef0f684aa5e2e5c1d1a51b4bf5643b  # 登入密碼 MD5
FUTU_TRADE_PWD=442398                  # 交易密碼（解鎖交易功能）

# 後端配置
PORT=8000
FUTU_DISABLE_LOG=1                      # 禁用日誌寫入（避免權限問題）

# 前端配置
PYTHON_API_URL=http://localhost:8000    # 後端 API 地址
APP_PASSWORD=Yy442398!!                 # 訪問 App 密碼
```

---

## 部署流程（VPS）

### Step 1: 基礎設定

```bash
# 登入 VPS
ssh root@your-vps-ip

# 安裝必要軟件
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

# 設定 Firewall
ufw default deny incoming
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

### Step 2: 安裝 FutuOpenD Linux CLI

OpenD 跑喺主機，唔喺 Docker 入面。

```bash
cd /opt

# 下載 FutuOpenD Linux CLI
# 去呢度下載：https://openapi.futunn.com/futu-api-doc/en/opend/opend-install.html
# 選擇 "Linux CLI" 版本

# 解壓
tar -xzf FutuOpenD_Linux_CLI.tar.gz
mv FutuOpenD /opt/futuopend
```

### Step 3: 配置並啟動 OpenD

```bash
# 創建 OpenD 配置目錄
mkdir -p /opt/futuopend/data

# 複製並編輯配置
cp /opt/futuopend/config/FutuOpenD_linux.json /opt/futuopend/data/
nano /opt/futuopend/data/FutuOpenD_linux.json
```

**FutuOpenD_linux.json 關鍵配置：**

```json
{
    "ip": "0.0.0.0",
    "port": 11111,
    "enable_crypto": false,
    "enable_market_snapshot_push": true
}
```

**啟動 OpenD：**

```bash
# 使用 screen 運行 OpenD
screen -S opend
cd /opt/futuopend
./FutuOpenD
# 按 Ctrl+A D 退出 screen
```

### Step 4: 從 Git 拉取項目

```bash
# SSH 進入 VPS
ssh root@107.173.153.41

# Clone 或 Pull 項目（首次需要）
cd /opt
git clone https://github.com/你的username/position-calculator.git vcp-calculator
# 或如果已存在：
# cd /opt/vcp-calculator && git pull
```

### Step 5: 配置並啟動服務（懶人方式）

**全部用一個命令搞掂！**

```bash
cd /opt/vcp-calculator

# 1. 確保 .env 設定正確
nano .env
# 確認以下內容存在：
# - APP_PASSWORD=Yy442398!!
# - API_SECRET=vjItBPUlggAEJPZRoZ3xbNinDbfL0XdoiNqL2GBp66A=
# - FUTU_TRADE_PWD=442398
# - FUTU_LOGIN_PWD_MD5=eeef0f684aa5e2e5c1d1a51b4bf5643b

# 2. 拉取最新代碼
git pull origin main

# 3. 一鍵啟動！（自動安裝依賴、殺舊進程、啟動服務）
./start-vps.sh
```

**停止服務：**

```bash
./stop-vps.sh
```

**重要：每次 git pull 後需要重新 build！**

```bash
git pull
npm run build
./start-vps.sh
```

**常用命令：**

```bash
# 查看後端日誌
tail -f /tmp/position-calculator-backend.log

# 查看前端日誌
tail -f /tmp/position-calculator-frontend.log

# 測試後端健康狀態
curl http://localhost:8000/api/health

# 測試持倉 API（需要 API key）
curl http://localhost:8000/api/positions -H 'X-API-Key: vjItBPUlggAEJPZRoZ3xbNinDbfL0XdoiNqL2GBp66A='
```

> **注意**：OpenD 必須先運行！如果 OpenD 未運行，`start-vps.sh` 會顯示後端啟動失敗。

### Step 7: Nginx 反向代理

```bash
# 創建 Nginx 配置
nano /etc/nginx/sites-available/position-calculator
```

```nginx
# VPS Position Calculator - Nginx Configuration
# 所有 /api/* 必須走 Next.js → Backend（Next.js 會自動加 API Key）

upstream frontend {
    server 127.0.0.1:3000;
    keepalive 64;
}

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    # 重要：所有 /api/* 走 Next.js（Next.js 會自動加 X-API-Key）
    location /api/ {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Frontend (Next.js)
    location / {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

> **⚠️ 重要**：`/api/*` 必須走 Next.js，唔可以直接去 Backend！
> 如果直接去 Backend，會因為冇 API Key 而 401 Unauthorized。
> Next.js API Route 會自動從環境變量讀取 `API_SECRET` 並加到 Header。

```bash
# 啟用配置
ln -s /etc/nginx/sites-available/position-calculator /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# SSL（可選）
certbot --nginx -d your-domain.com
```

---

## 本地運行

```bash
cd position-calculator

# 安裝依賴
npm install
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 啟動（需要 OpenD 運行）
./start.sh
# 或手動：
# source venv/bin/activate
# python backend/main.py &
# npm run dev
```

---

## 常見問題排查

| 問題 | 原因 | 解決方法 |
|------|------|----------|
| `ECONNREFUSED` | 後端未運行 | 檢查進程：`ps aux \| grep main.py` |
| `Not Found` | API 路徑缺少 `/api` | 檢查 `src/app/api/*/route.ts` |
| 右上角紅燈 | 富途連接失敗 | 見下方 OpenD 排查 |
| 富途持倉同步失敗 | OpenD 未登入 | 確認 OpenD 已啟動並登入 |

### OpenD 排查

```bash
# 1. 確認 OpenD 進程運行中
ps aux | grep FutuOpenD | grep -v grep

# 2. 確認端口監聽
ss -tlnp | grep 11111

# 3. 測試 OpenD 連接
timeout 3 bash -c 'cat < /dev/null > /dev/tcp/127.0.0.1/11111' && echo 'OK' || echo 'FAIL'

# 4. 進入 OpenD screen 查看日誌
screen -r opend
# 按 Ctrl+A D 退出

# 5. 如果 OpenD 未運行，重新啟動
screen -S opend
cd /opt/futuopend
./FutuOpenD
# 按 Ctrl+A D 退出
```

### OpenD API 連接超時 (Connect Timeout)

**症狀:**
- Backend logs 顯示大量 `_connect_sync: Connect fail: conn=0(N); msg=Timeout`
- OpenD screen 顯示已登入，但 API 全部 timeout
- Port 看似監聽中但實際連接失敗

**原因:**
- OpenD 進程存在但內部連接有問題（常見於長時間運行後）
- 需要完全重啟 OpenD

**解決:**
```bash
# 殺掉舊 OpenD 進程
pkill -9 FutuOpenD
screen -S opend -X quit 2>/dev/null
sleep 2

# 重新啟動 OpenD
screen -dmS opend bash -c 'cd /opt/futuopend && ./FutuOpenD -cfg_file=/opt/futuopend/FutuOpenD.xml; exec bash'

# 等待登入（約10秒）
sleep 10

# 驗證連接
timeout 3 bash -c 'cat < /dev/null > /dev/tcp/127.0.0.1/11111' && echo 'OK' || echo 'FAIL'

# 然後重啟 Backend
screen -S app -X quit
sleep 2
screen -dmS app bash -c 'cd /opt/vcp-calculator && source venv/bin/activate && python3 backend/main.py; exec bash'
sleep 5
curl -s http://localhost:8000/api/health
```

### 富途代碼格式

**注意:** 富途 API 需要正確嘅市場前綴：

| 市場 | 格式 | 例子 |
|------|------|------|
| 港股 | `HK.` | `HK.00700` |
| A股滬深 | `SZ.` / `SH.` | `SZ.000001` |
| 美股 | `US.` | `US.AAPL` |

**錯誤格式:** `00700` → `ERROR. format of code 00700 is wrong`
**正確格式:** `HK.00700` → 成功返回報價

### 驗證命令

```bash
# 測試後端 API
curl http://localhost:8000/api/positions

# 測試前端
curl http://localhost:3000

# 檢查進程
ps aux | grep -E '(next|main.py)' | grep -v grep

# 檢查 screen
screen -ls

# 查看日誌
tail -f /tmp/position-calculator-backend.log
tail -f /tmp/position-calculator-frontend.log
```

## VPS Screen 管理

### Screen 結構

| Screen 名 | 用途 | 狀態 |
|-----------|------|------|
| `app` | Python Backend (FastAPI) | 必運行 |
| `frontend` | Next.js Frontend | 必運行 |
| `opend` | 富途 OpenD | 必運行 |

### 常用命令

```bash
# 查看所有 screen
screen -ls

# 進入 app screen（查看/調試）
screen -r app
# 切換 window: Ctrl+A n (下一個) / Ctrl+A p (上一個)
# 退出 screen: Ctrl+A D

# 進入 opend screen（查看 OpenD 狀態）
screen -r opend
# 退出 screen: Ctrl+A D
```

### 重啟 Position Calculator

```bash
# 進入 VPS
ssh root@107.173.153.41

# 停止舊的 app screen 和 frontend
screen -S app -X quit 2>/dev/null
pkill -f 'node' 2>/dev/null

cd /opt/vcp-calculator

# 創建 wrapper script 俾 frontend
cat > /tmp/start-frontend.sh << 'EOFWRAPPER'
#!/bin/bash
export APP_PASSWORD='Yy442398!!'
cd /opt/vcp-calculator/.next/standalone
exec node server.js
EOFWRAPPER
chmod +x /tmp/start-frontend.sh

# 創建 backend screen
screen -dmS app bash -c 'cd /opt/vcp-calculator && python3 backend/main.py; exec bash'

sleep 3

# 創建 frontend screen
screen -dmS frontend bash -c '/tmp/start-frontend.sh; exec bash'

# 確認狀態
screen -ls
```

### 更新代碼後重啟（重新 Build）

> **注意**：呢個流程唔會 kill OpenD，保持 OpenD 運行。

```bash
ssh root@107.173.153.41

cd /opt/vcp-calculator

# 停止舊服務（唔好 kill opend！）
screen -S app -X quit 2>/dev/null
screen -S frontend -X quit 2>/dev/null
pkill -f 'node' 2>/dev/null
pkill -f 'main.py' 2>/dev/null

# Pull 最新代碼
git pull origin main

# 重新 Build（這個會把 API_SECRET 打包進去）
npm run build

# 確保 .next/standalone/.env 有 API_SECRET（重要！）
cat > .next/standalone/.env << 'EOF'
APP_PASSWORD=Yy442398!!
PYTHON_API_URL=http://localhost:8000
API_SECRET=vjItBPUlggAEJPZRoZ3xbNinDbfL0XdoiNqL2GBp66A=
HOSTNAME=127.0.0.1
EOF

# 創建 static files symlink（重要！否則 CSS/JS 會 404）
cd .next/standalone/.next
ln -sf ../../static static

# 返回主目錄
cd /opt/vcp-calculator

# 創建 wrapper script 俾 frontend（bind 127.0.0.1）
cat > /tmp/start-frontend.sh << 'EOFWRAPPER'
#!/bin/bash
export HOSTNAME='127.0.0.1'
export PORT='3000'
export APP_PASSWORD='Yy442398!!'
export PYTHON_API_URL='http://localhost:8000'
export API_SECRET='vjItBPUlggAEJPZRoZ3xbNinDbfL0XdoiNqL2GBp66A='
cd /opt/vcp-calculator/.next/standalone
exec node server.js
EOFWRAPPER
chmod +x /tmp/start-frontend.sh

# 啟動 backend
screen -dmS app bash -c 'cd /opt/vcp-calculator && python3 backend/main.py; exec bash'

sleep 3

# 啟動 frontend
screen -dmS frontend bash -c '/tmp/start-frontend.sh; exec bash'

sleep 5

# 驗證
screen -ls
curl -s -o /dev/null -w 'Frontend: %{http_code}\n' http://localhost:3000/
curl -s http://localhost:8000/api/health
```

---

## VPS 信息

```
VPS IP: 107.173.153.41
OpenD: 170.106.62.115:11111 (Remote) / 127.0.0.1:11111 (Local)
代碼: /opt/vcp-calculator

Screen: app (Backend:8000) | frontend (:3000) | opend (:11111)
API Key: vjItBPUlggAEJPZRoZ3xbNinDbfL0XdoiNqL2GBp66A=
密碼: Yy442398!!
```

## 系統架構

```
Yahoo Finance ──▶ Backend ──▶ Frontend (:3000)
富途 OpenD ─────▶ │         (美股期貨報價)
                  │         (港股報價/持倉/落單)
```

## 快速部署

> **注意**：呢個流程唔會 kill OpenD，保持 OpenD 運行。

```bash
ssh root@107.173.153.41
cd /opt/vcp-calculator

# 停止舊服務（唔好 kill opend！）
screen -S app -X quit 2>/dev/null
screen -S frontend -X quit 2>/dev/null
pkill -f 'node' 2>/dev/null
pkill -f 'main.py' 2>/dev/null

# 拉取代碼
git pull origin main

# Build
npm run build

# 配置環境（HOSTNAME=127.0.0.1 綁定本地）
cat > .next/standalone/.env << EOF
APP_PASSWORD=Yy442398!!
PYTHON_API_URL=http://localhost:8000
API_SECRET=vjItBPUlggAEJPZRoZ3xbNinDbfL0XdoiNqL2GBp66A=
HOSTNAME=127.0.0.1
EOF

mkdir -p .next/standalone/.next
ln -sf ../../static .next/standalone/.next/static

# 創建 wrapper script（bind 127.0.0.1）
cat > /tmp/start-frontend.sh << 'EOFWRAPPER'
#!/bin/bash
export HOSTNAME='127.0.0.1'
export PORT='3000'
export APP_PASSWORD='Yy442398!!'
export PYTHON_API_URL='http://localhost:8000'
export API_SECRET='vjItBPUlggAEJPZRoZ3xbNinDbfL0XdoiNqL2GBp66A='
cd /opt/vcp-calculator/.next/standalone
exec node server.js
EOFWRAPPER
chmod +x /tmp/start-frontend.sh

# 啟動 backend
screen -dmS app bash -c 'cd /opt/vcp-calculator && python3 backend/main.py; exec bash'
sleep 3

# 啟動 frontend
screen -dmS frontend bash -c '/tmp/start-frontend.sh; exec bash'
```

## 部署後驗證

```bash
# 檢查 Screen
screen -ls
# 預期: app, frontend, opend

# 檢查 Port
ss -tlnp | grep -E "3000|8000|11111"

# 測試 API
curl http://localhost:8000/api/health                    # Backend 健康
curl "http://localhost:8000/api/quote/ES"                 # Yahoo 期貨報價
curl "http://localhost:8000/api/quote/00700"               # 富途港股報價
curl http://localhost:8000/api/positions -H "X-API-Key: vjItBPUlggAEJPZRoZ3xbNinDbfL0XdoiNqL2GBp66A="  # 美股持倉

# 查看 Log
screen -r app      # Backend
screen -r frontend # Frontend
screen -r opend    # 富途 OpenD
```

## 常見問題排查

| 問題 | 原因 | 解決 |
|------|------|------|
| Backend 401 | Frontend 密碼錯 | 重設 `APP_PASSWORD` |
| 富途報價失敗 | OpenD 未運行/未登入 | `screen -r opend` 確認已登入 |
| 美股持倉空 | OpenD 未解鎖交易 | 確認 `FUTU_TRADE_PWD` 正確 |
| Yahoo 報價失敗 | 網絡問題 | 測試 `curl finance.yahoo.com` |
| Port 被佔用 | 舊進程未殺 | `pkill -9 -f node; pkill -9 -f main.py` |

### 重啟 OpenD
```bash
pkill -9 FutuOpenD
screen -S opend
cd /opt/futuopend && ./FutuOpenD -cfg_file=/opt/futuopend/FutuOpenD.xml
# Ctrl+A D 退出
```

### 重啟 Backend/Frontend
```bash
screen -S app -X quit; pkill -f "node"
screen -dmS app bash -c "cd /opt/vcp-calculator && source venv/bin/activate && python3 backend/main.py; exec bash"
screen -dmS frontend bash -c "export APP_PASSWORD='Yy442398!!'; cd /opt/vcp-calculator/.next/standalone && exec node server.js; exec bash"
```

## Screen 管理

```bash
screen -ls           # 查看所有
screen -r app        # 進入 Backend
screen -r frontend   # 進入 Frontend
screen -r opend      # 進入 OpenD
# 退出: Ctrl+A D
```

## 環境變量 (VPS)

```bash
# 富途 OpenD (VPS 本地)
FUTU_HOST=127.0.0.1
FUTU_PORT=11111

# 富途登入
FUTU_LOGIN_ACCOUNT=7202895
FUTU_LOGIN_PWD_MD5=eeef0f684aa5e2e5c1d1a51b4bf5643b
FUTU_TRADE_PWD=442398

# Backend
PYTHON_API_URL=http://localhost:8000
API_SECRET=vjItBPUlggAEJPZRoZ3xbNinDbfL0XdoiNqL2GBp66A=
FUTU_DISABLE_LOG=1

# OpenD Watchdog (自動重啟卡住嘅 OpenD)
WATCHDOG_CHECK_INTERVAL=30    # 檢查間隔（秒），預設30
WATCHDOG_MAX_FAILURES=3        # 連續失敗次數後重啟，預設3
```

## OpenD Watchdog 自動修復

Backend 內置 OpenD Watchdog，自動檢測並修復 OpenD 連接問題。

**工作原理:**
1. 每 30 秒檢查一次 OpenD 連接（使用 socket 測試）
2. 如果連續 3 次失敗，自動重啟 OpenD
3. 重啟後等待 10 秒驗證連接恢復

**特點:**
- 後台線程運行，唔影響正常交易
- 避免 OpenD 長期運行後卡住嘅問題
- 上次重啟後起碼等 5 分鐘先會再次重啟（防止連續重啟）

**日誌範例:**
```
[Watchdog] OpenD connection failed (1/3)
[Watchdog] OpenD connection failed (2/3)
[Watchdog] OpenD appears stuck, attempting restart...
[Watchdog] Restarting OpenD...
[Watchdog] OpenD restart successful
[Watchdog] OpenD connection restored
```

**手動測試 watchdog:**
```bash
# 查看 backend 日誌確認 watchdog 運行
screen -r app
# 應該看到: [Watchdog] Starting OpenD watchdog...

# 手動測試連接
timeout 3 bash -c 'cat < /dev/null > /dev/tcp/127.0.0.1/11111' && echo 'OK'
```
