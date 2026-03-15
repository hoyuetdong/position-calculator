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

### 4. (可選) 啟動 Backend

如果要用富途數據，需要同時啟動 backend：

```bash
# 停咗兩個 service
kill $(lsof -t -i:3000) 2>/dev/null
kill $(lsof -t -i:8000) 2>/dev/null

# 啟動 backend (放後台)
cd /Users/mac/Desktop/hoyuetdong/algo/position-calculator/backend && python3 main.py &

# 啟動 frontend
cd /Users/mac/Desktop/hoyuetdong/algo/position-calculator && npm run dev
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

### 1. 申請富途開放平台帳戶

1. 前往 [富途開放平台](https://open.futuhk.com/)
2. 註冊並完成實名認證
3. 創建應用程式，獲取 `AppID` 和 `AppKey`

### 2. 創建 `.env` 文件

```bash
FUTU_UNLOCK_PASSWORD=你的解鎖密碼
```

### 3. 運行 FutuOpenD

```bash
docker run -d \
  --name futuopend \
  -p 11111:11111 \
  -p 11112:11112 \
  -e UNLOCK_PASSWORD=你的解鎖密碼 \
  adrianhu/futuopend:latest
```

### 4. 啟動應用

```bash
npm run dev
```

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