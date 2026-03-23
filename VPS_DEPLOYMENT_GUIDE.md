# =============================================================================
# VPS 部署完整指南
# Position Calculator + OpenD
# =============================================================================

## 目錄結構

```
position-calculator/
├── docker-compose.yml          # 本地版本（唔改）
├── docker-compose.vps.yml      # VPS 版本（新加）
├── .env.example                # 本地 .env（唔改）
├── .env.vps.example            # VPS .env 模板（新加）
├── backend/
│   └── Dockerfile               # Backend Docker 鏡像
├── docker/
│   ├── Dockerfile.opend        # OpenD CLI Dockerfile（新加）
│   ├── opend_config.ini         # OpenD 配置模板（新加）
│   └── nginx.conf.example       # Nginx 配置模板（新加）
└── Dockerfile                  # Frontend Docker 鏡像
```

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
mkdir -p /opt/futuopend/keys
```

### Step 2: 下載 FutuOpenD Linux CLI

喺 VPS 上直接下載：

```bash
cd /opt/vcp-calculator

# 下載 FutuOpenD Linux CLI
# 去呢度下載：https://openapi.futunn.com/futu-api-doc/en/opend/opend-install.html
# 選擇 "Linux CLI" 版本，然後上傳到 VPS

# 方法 A: 如果有 direct download link
wget https://example.com/FutuOpenD_Linux_CLI.tar.gz  # 替換為實際連結

# 方法 B: 從本地 scp 過來
# scp /path/to/FutuOpenD_Linux_CLI.tar.gz root@your-vps-ip:/opt/vcp-calculator/

# 解壓到正確位置
tar -xzf FutuOpenD_Linux_CLI.tar.gz
mkdir -p /opt/futuopend
mv FutuOpenD_Linux_CLI/* /opt/futuopend/
```

### Step 3: Clone 项目到 VPS

```bash
cd /opt/vcp-calculator

# Clone 项目
git clone https://github.com/hoyuetdong/position-calculator.git .
```

### Step 4: 生成 RSA 密鑰對

```bash
cd /opt/futuopend/keys

# 生成私鑰 (2048-bit)
openssl genrsa -out private_key.pem 2048

# 生成公鑰
openssl rsa -in private_key.pem -pubout -out public_key.pem

# 設置權限（私鑰必須只有 owner 可以讀寫）
chmod 600 private_key.pem
chmod 644 public_key.pem

# ⚠️ 重要：設置 folder owner 為 1000（Docker 內 opend 用戶的 UID）
# 否則 Docker container 內會出現 "Permission Denied" 讀取私鑰
chown -R 1000:1000 /opt/futuopend/keys

# 上傳公鑰到富途後台
# https://openapi.futunn.com -> 開放接口 -> RSA 密鑰管理 -> 上傳 public_key.pem
```

### Step 5: 配置環境變量

```bash
cd /opt/vcp-calculator

# 複製環境變量模板
cp .env.vps.example .env.vps

# 編輯配置
nano .env.vps
```

填入以下內容：
```env
FUTU_TRADE_PWD=你的富途交易密碼
OPEN_D_KEY_PATH=/opt/futuopend/keys
APP_PASSWORD=你的訪問密碼（防黑客）

# ⚠️ 安全建議：
# - APP_PASSWORD 起碼 16 位，包含大小寫+數字+特殊符號
# - 可以用密碼管理器生成：https://bitwarden.com/
# - 例如：Kj9#mNp$2xLq@7wBz
```

### Step 6: 配置 OpenD

```bash
cd /opt/vcp-calculator

# 複製並編輯 OpenD 配置
cp docker/opend_config.ini docker/opend_config.ini.bak
nano docker/opend_config.ini
```

填入你的富途 App ID 同 Secret Key。

### Step 7: 啟動服務

```bash
cd /opt/vcp-calculator

# 首次啟動（只啟動 OpenD）
docker compose -f docker-compose.vps.yml up -d futuopend

# 睇日誌，等待 SMS 驗證連結
docker compose -f docker-compose.vps.yml logs -f futuopend
```

#### 首次登入（SMS 驗證）

```bash
# 睇日誌輸出，搵到類似呢個：
# [INFO] Please visit: https://nnn.futunn.com/xxx/verify?code=xxxxx

# 複製呢個連結，喺你本地瀏覽器打開
# 完成 SMS 驗證後，OpenD 會自動登入
```

驗證成功後：
```bash
# 繼續啟動其他服務
docker compose -f docker-compose.vps.yml up -d

# 確認所有服務運行正常
docker compose -f docker-compose.vps.yml ps
```

### Step 8: 配置 Nginx + SSL

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

### Step 9: 申請 SSL 證書

```bash
# 確認 DNS 已解析到 VPS IP
# A record: your-domain.com -> VPS_IP

# 申請 Let's Encrypt 免費 SSL
certbot --nginx -d your-domain.com

# 自動續期測試
certbot renew --dry-run
```

### Step 10: 創建密碼認證

```bash
# 創建密碼檔
htpasswd -c /etc/nginx/.htpasswd admin

# 之後添加其他用戶
htpasswd /etc/nginx/.htpasswd another_user
```

⚠️ **重要：確認 Nginx 配置已啟用密碼認證**

編輯 Nginx 配置，確保有以下兩行：

```nginx
server {
    # ... 其他配置 ...

    auth_basic "VCP Position Calculator - Login Required";
    auth_basic_user_file /etc/nginx/.htpasswd;

    # ... 其他配置 ...
}
```

如果冇呢兩行，就算set好密碼檔都唔會彈登入框。

```bash
# 確認後重新載入
systemctl reload nginx
```

---

## 安全檢查清單

### 網絡安全
- [x] UFW Firewall 只開放 22 (SSH) + 443 (HTTPS)
- [x] SSH 禁用密碼登入，改用 Key
- [x] OpenD 只監聽 Docker 內部網絡（唔暴露 port）
- [x] Backend/Frontend 只監聽 127.0.0.1
- [x] Nginx 配置 Basic Auth
- [x] 使用 HTTPS (Let's Encrypt)

### 密鑰安全
- [x] RSA 密鑰通過 volume mount（唔打包進 image）
- [x] .env.vps 加入 .gitignore
- [x] RSA 私鑰權限設定 600（只有 owner 可讀）

### ⚠️ Docker 與 UFW 衝突警告

Docker 預設會直接修改 iptables，**繞過 UFW** 暴露端口！

喺 `docker-compose.vps.yml` 入面，所有暴露俾 Nginx 嘅 port mapping **必須寫死 127.0.0.1**：

```yaml
services:
  backend:
    ports:
      - "127.0.0.1:3000:3000"  # ✅ 正確，街外人直擊 IP 都入唔到
      # - "3000:3000"          # ❌ 危險，Docker 會穿透 UFW 暴露出去

  frontend:
    ports:
      - "127.0.0.1:3001:3001"  # ✅ 正確
```

如果唔寫死 `127.0.0.1`，就算 UFW 設定晒 `default deny incoming`，外面嘅人都可以直接 `curl http://VPS_IP:3000` 訪問到你嘅服務。

### Nginx 安全強化（可選但推薦）
```bash
# 在 /etc/nginx/sites-available/vcp-calculator 加入以下 header：
nano /etc/nginx/sites-available/vcp-calculator

# 在 server block 內加入：
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

# 禁用目錄列出
autoindex off;

systemctl reload nginx
```

---

## 日常維護

### 睇日誌
```bash
# 所有服務
docker compose -f docker-compose.vps.yml logs -f

# 指定服務
docker compose -f docker-compose.vps.yml logs -f backend
docker compose -f docker-compose.vps.yml logs -f futuopend
```

### 更新代碼
```bash
cd /opt/vcp-calculator
git pull
docker compose -f docker-compose.vps.yml up --build -d
```

### 重啟服務
```bash
docker compose -f docker-compose.vps.yml restart
```

### 停止服務
```bash
docker compose -f docker-compose.vps.yml down
```

---

## 故障排除

### OpenD 啟動失敗："error while loading shared libraries"

如果你見到呢個 error：
```
error while loading shared libraries: libxxx.so
```

解決方法：確認 `docker/Dockerfile.opend` 用緊 `FROM ubuntu:22.04` 而唔係 `python:slim`，並且安裝咗 `ca-certificates libstdc++6 libgcc-s1`。

### OpenD 讀取不到 RSA Key："Permission Denied"

如果你見到呢個 error：
```
Permission Denied: ./keys/private_key.pem
```

解決方法：喺 VPS 執行：
```bash
chown -R 1000:1000 /opt/futuopend/keys
chmod 600 /opt/futuopend/keys/private_key.pem
```

### OpenD 連接失敗
```bash
# 檢查 OpenD 是否正常啟動
docker compose -f docker-compose.vps.yml logs futuopend

# 檢查 healthcheck
docker inspect futuopend | grep -A5 Health
```

### Backend 連唔到 OpenD
```bash
# 確認在同一個網絡
docker network inspect position-calculator_vcp-network

# 測試連接
docker exec -it vcp-backend ping futuopend
docker exec -it vcp-backend nc -zv futuopend 11111
```

### SSL 證書過期
```bash
certbot renew
systemctl reload nginx
```

---

## 本地版本（保持不變）

```bash
# 本地運行（繼續用你本地電腦嘅 OpenD）
cd position-calculator
docker compose up -d

# 訪問 http://localhost:3000
```

---

## 資源需求

| 組件 | RAM | CPU |
|------|-----|-----|
| OpenD CLI | ~200MB | 1 core |
| Backend | ~300MB | 1 core |
| Frontend | ~400MB | 1 core |
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
- `.env.vps` - 包含交易密碼
- `docker/opend_config.ini` - 包含 App ID/Secret
- `docker/*.tar.gz` - OpenD binary

檢查你的 `.gitignore` 包含曉呢啲。
