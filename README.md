# VCP Position Calculator - 專業交易倉位計算器

## 功能特點

- ✅ **雙數據源**：Yahoo Finance (默認) + 富途 (可選)
- ✅ 自動 ATR (14日) 計算及建議止蝕位
- ✅ 1R/2R/3R 目標價計算
- ✅ 風險警告 (>20% 組合 / >8% 止蝕)
- ✅ R倍數可視化
- ✅ 支援港股、美股、A股

## 快速開始

### 1. 安裝 Node.js 22

```bash
# macOS
brew install node@22

# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### 2. 安裝依賴

```bash
npm install
```

### 3. 啟動服務

```bash
npm run dev
```

打開瀏覽器訪問：`http://localhost:3000`

---

## Docker 部署 (VPS / 伺服器)

### 準備環境

```bash
# 確保 Docker 同 docker-compose 已安裝
docker --version
docker-compose --version
```

### 配置 .env

```bash
cp .env.example .env
nano .env
```

填入以下必要變數：
```
FUTU_LOGIN_ACCOUNT=你的富途ID
FUTU_LOGIN_PWD_MD5=密碼既MD5
FUTU_TRADE_PWD=你的交易密碼
```

### 啟動所有服務

```bash
# 構建並啟動所有 containers
docker-compose up -d

# 查看所有 services 狀態
docker-compose ps

# 查看日誌
docker-compose logs -f
```

### 服務架構

| Service | Port | Description |
|---------|------|-------------|
| futuopend | 11111, 11112, 8081 | 富途行情網關 |
| backend | 8000 | Python FastAPI (止蝕邏輯) |
| vcp-calculator | 3000 | Next.js 前端 |

### 驗證部署

```bash
# 1. 檢查 futuopend 連線
curl http://localhost:8081/status

# 2. 檢查 backend API
curl http://localhost:8000/positions

# 3. 訪問網頁
# http://你的VPS-IP:3000
```

### 停止服務

```bash
docker-compose down
```

---

## 使用教學

### 基本操作

1. **輸入股票代碼**：例如 `NVDA` (美股)、`00700` (港股)、`600519` (A股)
2. **設置止蝕位**：系統會自動計算 ATR 並建議止蝕位
3. **輸入買入價**：系統會計算應買股數同目標價
4. **加入倉位**：點擊「加入倉位」記錄交易

### 數據源切換

- **Yahoo Finance** (默認)：無需設置，直接可用
- **富途**：需要配置 API (可選)

詳見下文「富途 API 設置」

---

## 富途 API 設置 (可選)

如果你想用富途數據，需要以下設置：

### 1. 準備富途帳戶

1. 前往 [富途開放平台](https://open.futuhk.com/) 註冊帳戶
2. 記住你嘅富途登入 ID / Email / 手機號碼
3. 生成登入密碼嘅 MD5 (睇下面教學)

### 2. 生成 MD5 密碼

```bash
# Linux / Mac 都可以用呢個 command
echo -n '你既富途登入密碼' | md5sum | cut -d' ' -f1
# 或者
echo -n '你既富途登入密碼' | md5
```

複製輸出嘅 32 位小寫 MD5 值。

### 3. 創建 `.env` 文件

```bash
# 複製範例
cp .env.example .env

# 編輯 .env，填入你既資料
nano .env
```

確保以下變數已經設定：
```
FUTU_LOGIN_ACCOUNT=你既富途ID (email/手機號/用戶ID)
FUTU_LOGIN_PWD_MD5=上面生成既32位MD5
```

### 4. Docker 部署 (本地 / VPS)

#### 使用 docker-compose 啟動

```bash
# 啟動服務
docker-compose up -d

# 查看日誌
docker-compose logs -f futuopend
```

#### 開放遠端訪問 (VPS)

如果係 VPS 要畀外網訪問，修改 `docker-compose.yml`：

```yaml
ports:
  - "0.0.0.0:11111:11111"  # 改為 0.0.0.0
  - "0.0.0.0:11112:11112"
  - "0.0.0.0:8081:8081"
```

### 5. 第一次登入 / SMS 驗證 (非常重要！)

**第一次啟動 OpenD 時，如果富途要求 SMS 驗證：**

1. 訪問 `http://你的VPS-IP:8081`
2. 輸入你手機收到既 SMS 驗證碼
3. 點擊 Submit

**驗證成功後既效果：**
- OpenD 會記錄設備，以後重啟唔使再驗證
- 確保用 `-v` volume mapping 持久化 `/root/.com.futunn.FutuOpenD` 目錄

### 6. 驗證連線

```bash
# 查看 OpenD 狀態
curl http://localhost:8081/status

# 或者睇日誌
docker-compose logs futuopend
```

如果見到「行情連接成功」就代表 OK 喇！

---

## 股票代碼格式

| 市場 | 格式 | 例子 |
|------|------|------|
| 美股 | 直接輸入 | NVDA, AAPL, MSFT |
| 港股 | 純數字 | 00700, 9888, 9999 |
| A股 | 純數字 | 600519, 000001 |

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

## 技術棧

- Next.js 14 + TypeScript
- Tailwind CSS (Dark Mode)
- Yahoo Finance API / 富途 Open API