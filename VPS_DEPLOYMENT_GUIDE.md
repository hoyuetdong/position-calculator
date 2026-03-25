# =============================================================================
# VPS 部署完整指南
# Position Calculator (OpenD 獨立安裝)
# =============================================================================

## 架構説明

```
┌─────────────────────────────────────────────────────────┐
│                        VPS Server                        │
│                                                          │
│  ┌──────────┐    ┌──────────────┐                       │
│  │ OpenD    │◄───│   Backend    │  Docker Network       │
│  │ (主機)   │    │   :8000      │                       │
│  │ :11111   │    └──────┬───────┘                       │
│  └──────────┘           │                               │
│                          │                               │
│         ┌────────────────▼───┐                         │
│         │     Nginx           │                         │
│         │  + SSL + 密碼認證    │  ◄── 用戶瀏覽器 (HTTPS) │
│         │     :443            │                         │
│         └─────────────────────┘                         │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**特點：** OpenD 跑喺主機，唔喺 Docker。入面咁做係因為：
- 唔需要配置 RSA 加密（localhost 交易接口允許唔加密）
- 方便直接睇日誌、調試
-唔需要重複 SMS 驗證

---

## 目錄結構

```
position-calculator/
├── docker-compose.yml          # 本地版本（唔改）
├── docker-compose.vps.yml      # VPS 版本
├── .env.example                # 環境變量模板
├── backend/
│   └── Dockerfile              # Backend Docker 鏡像
├── docker/
│   └── nginx.conf.example       # Nginx 配置模板
└── Dockerfile                  # Frontend Docker 鏡像
```

> **注意**：OpenD 係獨立安裝官方版，唔喺呢個 repo 入面。請去 [富途官網](https://openapi.futunn.com/futu-api-doc/en/opend/opend-install.html) 下載。

---

## 部署流程（VPS）

### Step 1: 基礎安全設定

```bash
# 登入 VPS
ssh root@your-vps-ip

# 安裝必要軟件
apt update && apt upgrade -y
apt install -y docker.io docker-compose nginx certbot python3-certbot-nginx apache2-utils ufw

# 設定 UFW Firewall（只開放必要 port）
ufw default deny incoming    # 預設拒絕所有入站
ufw allow 22/tcp             # SSH（你自己用）
ufw allow 443/tcp            # HTTPS
ufw enable

# SSH 強化：禁用密碼登入，改用 Key（如果未設定）
nano /etc/ssh/sshd_config
# 確保以下設定：
#   PasswordAuthentication no
#   PubkeyAuthentication yes
systemctl restart sshd

# 創建應用目錄
mkdir -p /opt/vcp-calculator
```

### Step 2: 安裝 FutuOpenD Linux CLI

OpenD 跑喺主機，唔喺 Docker 入面。

```bash
cd /opt/vcp-calculator

# 下載 FutuOpenD Linux CLI
# 去呢度下載：https://openapi.futunn.com/futu-api-doc/en/opend/opend-install.html
# 選擇 "Linux CLI" 版本

# 方法 A: 如果有 direct download link
wget https://example.com/FutuOpenD_Linux_CLI.tar.gz  # 替換為實際連結

# 方法 B: 從本地 scp 過來
# scp /path/to/FutuOpenD_Linux_CLI.tar.gz root@your-vps-ip:/opt/vcp-calculator/

# 解壓到 /opt/futuopend
mkdir -p /opt/futuopend
tar -xzf FutuOpenD_Linux_CLI.tar.gz
mv FutuOpenD_Linux_CLI/* /opt/futuopend/
rm -rf FutuOpenD_Linux_CLI

# 確認
ls /opt/futuopend/
```

### Step 3: Clone 項目到 VPS

```bash
cd /opt/vcp-calculator

# Clone 項目
git clone https://github.com/hoyuetdong/position-calculator.git .

# 切換到最新版本
git pull
```

### Step 4: 配置環境變量

```bash
cd /opt/vcp-calculator

# 複製環境變量模板
cp .env.example .env

# 編輯配置
nano .env
```

填入以下內容：
```env
FUTU_TRADE_PWD=你的富途交易密碼
APP_PASSWORD=你的訪問密碼（防黑客）
```

### Step 5: 配置並啟動 OpenD

下載並安裝完成後，啟動 OpenD：
```bash
cd /opt/futuopend
./futuopend
```

#### 首次配置

OpenD 啟動後會引導你進行首次配置：

1. **登入方式**：選擇「帳號密碼登入」（唔需要 RSA）
2. **填入富途 App ID / Secret Key**：喺富途後台申請
3. **API Listening Address**：**必須設為 `0.0.0.0`**
   - ⚠️ **唔可以設為 `127.0.0.1`**，因為 Docker container 係用 `172.17.0.1` 連接主機，唔係 `127.0.0.1`
4. **API Port**：保持 `11111`
5. **交易密碼**：設定你嘅富途交易密碼

#### 首次登入（SMS 驗證）

如果係首次登入，OpenD 會輸出類似：
```
[INFO] Please visit: https://nnn.futunn.com/xxx/verify?code=xxxxx
```

1. 複製呢個連結
2. 喺你本地瀏覽器打開
3. 完成 SMS 驗證
4. OpenD 會自動連接成功

成功後會見到：
```
[INFO] Connect to Futu OpenD success
```

**之後改為 background 運行：**
```bash
# 停止前景進程 (Ctrl+C)
# 改用 systemd 服務或 nohup 後台運行

# 方法 A: nohup
nohup ./futuopend > opend.log 2>&1 &

# 方法 B: systemd service (推薦)
cat > /etc/systemd/system/futuopend.service << 'EOF'
[Unit]
Description=Futu OpenD
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/futuopend
ExecStart=/opt/futuopend/futuopend
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable futuopend
systemctl start futuopend

# 確認狀態
systemctl status futuopend
```

### Step 6: 啟動 Docker 服務（Backend + Frontend）

```bash
cd /opt/vcp-calculator

# 啟動服務
docker compose -f docker-compose.vps.yml up -d

# 確認所有服務運行正常
docker compose -f docker-compose.vps.yml ps
```

你應該會見到：
```
NAME           STATUS
vcp-backend    Up
vcp-calculator Up
```

### Step 7: 配置 Nginx + SSL

```bash
cd /opt/vcp-calculator

# 複製 Nginx 配置
cp docker/nginx.conf.example /etc/nginx/sites-available/vcp-calculator
nano /etc/nginx/sites-available/vcp-calculator
# 將 your-domain.com 改為你的域名

# 啟用站點
ln -sf /etc/nginx/sites-available/vcp-calculator /etc/nginx/sites-enabled/vcp-calculator
rm -f /etc/nginx/sites-enabled/default

# 測試配置
nginx -t

# 重新載入
systemctl reload nginx
```

### Step 8: 申請 SSL 證書

```bash
# 確認 DNS 已解析到 VPS IP
# A record: your-domain.com -> VPS_IP

# 申請 Let's Encrypt 免費 SSL
certbot --nginx -d your-domain.com

# 自動續期測試
certbot renew --dry-run
```

### Step 9: 創建密碼認證

```bash
# 創建密碼檔
htpasswd -c /etc/nginx/.htpasswd admin

# 之後添加其他用戶
htpasswd /etc/nginx/.htpasswd another_user
```

確認 Nginx 配置已啟用密碼認證：

```nginx
server {
    # ... 其他配置 ...

    auth_basic "VCP Position Calculator - Login Required";
    auth_basic_user_file /etc/nginx/.htpasswd;

    # ... 其他配置 ...
}
```

如果冇呢兩行，就算 set 好密碼檔都唔會彈登入框。

```bash
# 確認後重新載入
systemctl reload nginx
```

---

## 安全檢查清單

### 網絡安全
- [x] UFW Firewall 只開放 22 (SSH) + 443 (HTTPS)
- [x] SSH 禁用密碼登入，改用 Key
- [x] OpenD 只監聽本地（唔暴露俾公網）
- [x] Backend/Frontend 只監聽 127.0.0.1
- [x] Nginx 配置 Basic Auth
- [x] 使用 HTTPS (Let's Encrypt)

### ⚠️ Docker 與 UFW 衝突警告

Docker 預設會直接修改 iptables，**繞過 UFW** 暴露端口！

喺 `docker-compose.vps.yml` 入面，所有暴露俾 Nginx 嘅 port mapping **必須寫死 127.0.0.1**：

```yaml
services:
  backend:
    ports:
      - "127.0.0.1:8000:8000"  # ✅ 正確，街外人直擊 IP 都入唔到
      # - "8000:8000"          # ❌ 危險，Docker 會穿透 UFW 暴露出去
```

### Nginx 安全強化（可選但推薦）

喺 `/etc/nginx/sites-available/vcp-calculator` 加入以下 header：

```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
autoindex off;
```

```bash
systemctl reload nginx
```

---

## 日常維護

### 睇日誌

```bash
# OpenD 日誌（主機）
journalctl -u futuopend -f
# 或者
tail -f /opt/futuopend/opend.log

# Docker 服務日誌
docker compose -f docker-compose.vps.yml logs -f

# 指定服務
docker compose -f docker-compose.vps.yml logs -f backend
docker compose -f docker-compose.vps.yml logs -f vcp-calculator
```

### 更新代碼

```bash
cd /opt/vcp-calculator
git pull
docker compose -f docker-compose.vps.yml up --build -d
```

### 重啟服務

```bash
# 重啟 OpenD
systemctl restart futuopend

# 重啟 Docker 服務
docker compose -f docker-compose.vps.yml restart
```

### 停止服務

```bash
# Docker 服務
docker compose -f docker-compose.vps.yml down

# OpenD
systemctl stop futuopend
```

---

## 故障排除

### Backend 連唔到 OpenD

```bash
# 確認 OpenD 正常運行
systemctl status futuopend

# 測試 OpenD port
nc -zv 127.0.0.1 11111

# 確認 Docker 能夠連接主機
docker exec -it vcp-backend nc -zv 172.17.0.1 11111
```

如果連接有問題，檢查 OpenD 配置入面 `API Listening Address` **係咪 `0.0.0.0`**。

### Docker network 問題

```bash
# 確認 Docker network 存在
docker network inspect position-calculator_vcp-network

# 確認 backend 網絡設定
docker inspect vcp-backend | grep Networks -A5
```

### SSL 證書過期

```bash
certbot renew
systemctl reload nginx
```

### 富途 API 連接失敗 / 日誌權限問題

如果你遇到以下錯誤：
```
[Errno 1] Operation not permitted: '/Users/xxx/.com.futunn.FutuOpenD/Log/py_2026_03_25.log'
```

**原因**：`futu-api` 嘗試寫入日誌檔案但被權限阻止。

**解決方法**（任選其一）：

1. **設置環境變數（推薦）**
   ```bash
   # 喺 .env 或啟動命令入面加：
   FUTU_DISABLE_LOG=1
   ```

2. **手動創建日誌目錄**
   ```bash
   mkdir -p ~/.com.futunn.FutuOpenD/Log
   chmod 755 ~/.com.futunn.FutuOpenD
   chmod 755 ~/.com.futunn.FutuOpenD/Log
   ```

3. **VPS / Docker 部署**
   - 確保 `docker-compose.vps.yml` 入面有 `FUTU_DISABLE_LOG=1`
   - 或者確保主機上有 `/root/.com.futunn.FutuOpenD/Log` 目錄

**驗證修復**：
```bash
curl http://localhost:8000/positions
# 應該返回 JSON，唔再係 error

---

## 資源需求

| 組件 | RAM | CPU |
|------|-----|-----|
| OpenD CLI (主機) | ~200MB | 1 core |
| Backend (Docker) | ~300MB | 1 core |
| Frontend (Docker) | ~400MB | 1 core |
| Nginx | ~50MB | 1 core |
| **Total** | **~1GB** | 2 cores |

建議 VPS 配置：
- 最低：1 CPU / 1GB RAM（可能會 swap）
- 推薦：2 CPU / 2GB RAM（流暢運行）

---

## ⚠️ 安全提醒

### 一定要做（防被hack）
1. **UFW Firewall** - 只開 22 + 443 port
2. **SSH Key 登入** - 禁用密碼login
3. **強密碼** - APP_PASSWORD 起碼 16 位

### 敏感資訊（唔好 commit）

確保以下檔案 **唔會** commit 到 GitHub：
- `.env` - 包含交易密碼

檢查你的 `.gitignore` 包含晒呢啲。

---

## 本地版本（macOS / Linux）

### 快速啟動（推薦）

```bash
./start.sh
```

### 手動啟動

1. **設置 Python 環境（只需做一次）：**
```bash
pip3 install -r requirements.txt
```

2. **啟動服務：**
```bash
source venv/bin/activate
python backend/main.py &   # 啟動後端
npm run dev               # 啟動前端
```

訪問 http://localhost:3000

> 注意：本地版本使用 `127.0.0.1` 連接富途 OpenD，確保 OpenD 已運行。
