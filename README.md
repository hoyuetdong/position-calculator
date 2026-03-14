# VCP Position Calculator - 富途版

專業交易倉位計算器，使用富途 Open API 獲取實時行情數據。

## 功能特點

- ✅ 富途實時報價 API 整合
- ✅ 自動 ATR (14日) 計算及建議止蝕位
- ✅ 1R/2R/3R 目標價計算
- ✅ 風險警告 (>20% 組合 / >8% 止蝕)
- ✅ 連接狀態指示燈
- ✅ R倍數可視化
- ✅ Session 記錄

## 技術棧

- Next.js 14 + TypeScript
- Tailwind CSS (Dark Mode)
- 富途 Open API (futu-api)
- Docker + PM2

---

## 富途 API 設置教學

### 第一步：申請富途開放平台帳戶

1. 前往 [富途開放平台](https://open.futuhk.com/)
2. 註冊帳戶並完成實名認證
3. 創建應用程式，獲取 `AppID` 和 `AppKey`

### 第二步：獲取登入 Token

1. 登入富途開放平台
2. 進入「我的應用」→ 選擇你的應用
3. 點擊「獲取Token」
4. 記下你的 `解鎖密碼` (Unlock Password)

### 第三步：設置市場權限

在富途開放平台設置你需要訪問的市場：
- 港股 (HK)
- 美股 (US)
- A股 (CN) - 如需要

---

## 部署方法

### 方法一：Docker Compose (推薦)

#### 1. 準備環境變量

創建 `.env` 文件：

```bash
# 富途 API 設置
FUTU_UNLOCK_PASSWORD=你的解鎖密碼
FUTU_TRADE_PASSWORD=你的交易密碼(可選)
```

#### 2. 啟動服務

```bash
# 构建並啟動
docker-compose up -d

# 查看日誌
docker-compose logs -f

# 停止服務
docker-compose down
```

#### 3. 訪問應用

打開瀏覽器訪問：`http://your-server-ip:3000`

---

### 方法二：直接部署 (不使用 Docker)

#### 1. 安裝 Node.js 22

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
```

#### 2. 安裝 FutuOpenD

**選項 A：使用 Docker 運行 FutuOpenD**

```bash
# 只運行 FutuOpenD
docker run -d \
  --name futuopend \
  -p 11111:11111 \
  -p 11112:11112 \
  -e UNLOCK_PASSWORD=你的解鎖密碼 \
  adrianhu/futuopend:latest
```

**選項 B：直接安裝**

```bash
# 下載 FutuOpenD
wget https://www.futuhk.com/openapi/linux/FutuOpenD_linux.tar.gz
tar -xzf FutuOpenD_linux.tar.gz
cd FutuOpenD

# 編輯配置
nano app.config
# 設置:
#   "UnlockPasswd": "你的解鎖密碼"
#   "EnableHK": 1
#   "EnableUS": 1

# 啟動
./FutuOpenD
```

#### 3. 部署 Web 應用

```bash
# Clone 項目
cd /var/www
git clone <your-repo> vcp-position-calculator
cd vcp-position-calculator

# 安裝依賴
npm install

# 設置環境變量
export FUTU_HOST=127.0.0.1
export FUTU_PORT=11111
export FUTU_UNLOCK_PASSWORD=你的解鎖密碼

# 構建
npm run build

# 使用 PM2 啟動
pm2 start ecosystem.config.js
pm2 save
pm2 startup
```

---

## 配置說明

### 環境變量

| 變量 | 說明 | 默認值 |
|------|------|--------|
| `FUTU_HOST` | FutuOpenD IP | 127.0.0.1 |
| `FUTU_PORT` | FutuOpenD 端口 | 11111 |
| `FUTU_UNLOCK_PASSWORD` | 富途解鎖密碼 | (必填) |
| `FUTU_TRADE_PASSWORD` | 富途交易密碼 | (可選) |

### docker-compose.yml 說明

```yaml
services:
  futuopend:
    image: adrianhu/futuopend:latest  # 富途行情網關
    ports:
      - "11111:11111"  # TCP 行情端口
      - "11112:11112"  # WebSocket 端口
    environment:
      - UNLOCK_PWD=${FUTU_UNLOCK_PASSWORD}  # 解鎖密碼
      - MARKET_HK=1   # 港股權限
      - MARKET_US=1   # 美股權限
      - MARKET_CN=0   # A股權限

  vcp-calculator:
    build: .          # Web 應用
    ports:
      - "3000:3000"
    environment:
      - FUTU_HOST=futuopend  # 連接網關容器
      - FUTU_PORT=11111
      - FUTU_UNLOCK_PASSWORD=${FUTU_UNLOCK_PASSWORD}
```

---

## 股票代碼格式

富途使用以下格式：

| 市場 | 格式 | 例子 |
|------|------|------|
| 港股 | `代碼.HK` | 00700.HK, 9888.HK |
| 美股 | `代碼.US` | NVDA.US, AAPL.US |
| A股 | `代碼.SH` 或 `代碼.SZ` | 600519.SH, 000001.SZ |

---

## 計算公式

```
1R 風險額 = 帳戶規模 × R%
止蝕空間 = 買入價 - 止蝕價
應買股數 = 1R風險額 / 止蝕空間
持倉價值 = 股數 × 買入價
組合% = 持倉價值 / 帳戶規模

1R目標 = 買入價 + 止蝕空間
2R目標 = 買入價 + (止蝕空間 × 2)
3R目標 = 買入價 + (止蝕空間 × 3)
```

---

## 常見問題

### Q: 連接狀態顯示「未連接」

A: 檢查以下項目：
1. FutuOpenD 是否正在運行
2. 環境變量 `FUTU_UNLOCK_PASSWORD` 是否正確
3. 防火牆是否允許 11111 端口

### Q: 獲取報價失敗

A: 
1. 確認股票代碼格式正確 (如 NVDA.US)
2. 確認該市場權限已在富途開放平台開通
3. 檢查日誌: `docker-compose logs futuopend`

### Q: 如何更新富途 Token

A: 
1. 停止服務
2. 更新 `.env` 文件中的密碼
3. 重啟 FutuOpenD 容器
4. 重啟 Web 應用

---

## 技術支持

如有問題，請查看：
- [富途開放平台文檔](https://open.futuhk.com/)
- [Futu API Node.js SDK](https://www.npmjs.com/package/futu-api)