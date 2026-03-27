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
# 確認 FUTU_HOST=170.106.62.115（remote OpenD）

# 2. 一鍵啟動！（自動安裝依賴、殺舊進程、啟動服務）
./start-vps.sh
```

**停止服務：**

```bash
./stop-vps.sh
```

**常用命令：**

```bash
# 查看後端日誌
tail -f /tmp/position-calculator-backend.log

# 查看前端日誌
tail -f /tmp/position-calculator-frontend.log

# 測試後端健康狀態
curl http://localhost:8000/api/health

# 測試持倉 API
curl http://localhost:8000/api/positions
```

> **注意**：OpenD 必須先運行！如果 OpenD 未運行，`start-vps.sh` 會顯示後端啟動失敗。

### Step 7: Nginx 反向代理（可選）

```bash
# 創建 Nginx 配置
nano /etc/nginx/sites-available/position-calculator
```

```nginx
server {
    listen 80;
    server_name your-domain.com;  # 或 IP

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

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
netstat -tlnp | grep 11111

# 3. 測試 OpenD 連接
telnet 170.106.62.115 11111

# 4. 進入 OpenD screen 查看日誌
screen -r opend
# 按 Ctrl+A D 退出

# 5. 如果 OpenD 未運行，重新啟動
screen -S opend
cd /opt/futuopend
./FutuOpenD
# 按 Ctrl+A D 退出
```

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
| `app` | Position Calculator (Backend + Frontend) | 必運行 |
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

# 停止舊的 app screen
screen -S app -X quit

# 重建 app screen（backend + frontend）
cd /opt/vcp-calculator

# 創建新 screen，包含 backend 和 frontend 兩個 window
screen -dmS app bash -c 'echo "Starting backend..."; cd /opt/vcp-calculator && python3 backend/main.py; exec bash'
screen -S app -X screen -t frontend -md bash -c 'echo "Starting frontend..."; cd /opt/vcp-calculator/.next/standalone && PORT=3000 HOSTNAME=0.0.0.0 node server.js; exec bash'

# 確認狀態
screen -ls
```

### 更新代碼後重啟（重新 Build）

```bash
ssh root@107.173.153.41

cd /opt/vcp-calculator

# 停止舊服務
screen -S app -X quit

# Pull 最新代碼
git pull

# 重新 Build
npm run build

# 重啟服務
screen -dmS app bash -c 'cd /opt/vcp-calculator && python3 backend/main.py; exec bash'
screen -S app -X screen -t frontend -md bash -c 'cd /opt/vcp-calculator/.next/standalone && PORT=3000 HOSTNAME=0.0.0.0 node server.js; exec bash'

# 驗證
screen -ls
curl -s -o /dev/null -w 'Frontend: %{http_code}\n' http://localhost:3000/
```

---

## VPS 信息

```
VPS IP: 107.173.153.41
OpenD Remote: 170.106.62.115:11111
Frontend: 3000
Backend: 8000

代碼路徑: /opt/vcp-calculator

Screen Sessions:
- app: Position Calculator (backend + frontend)
- opend: 富途 OpenD
```

## 部署命令速查

```bash
# SSH 進入 VPS
ssh root@107.173.153.41

# === 查看 Screen ===
screen -ls

# === 進入 Screen 查看 ===
screen -r app      # Position Calculator
screen -r opend    # OpenD

# === 退出 Screen ===
# 在 screen 內按 Ctrl+A D

# === OpenD 管理 ===
# 確認 OpenD 運行
ps aux | grep FutuOpenD | grep -v grep

# 啟動 OpenD（如需）
screen -S opend
cd /opt/futuopend && ./FutuOpenD
# Ctrl+A D 退出

# === 重啟 Position Calculator ===
screen -S app -X quit
cd /opt/vcp-calculator
screen -dmS app bash -c 'cd /opt/vcp-calculator && python3 backend/main.py; exec bash'
screen -S app -X screen -t frontend -md bash -c 'cd /opt/vcp-calculator/.next/standalone && PORT=3000 HOSTNAME=0.0.0.0 node server.js; exec bash'
```
