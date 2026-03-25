# VCP Position Calculator

專業交易倉位計算器

## 功能

- ATR 自動計算及建議止蝕位
- 1R/2R/3R 目標價
- 風險警告
- 支援港股、美股、A股
- 富途持倉同步（可選）

## 快速啟動

```bash
./start.sh
```

訪問 `http://localhost:3000`

按 `Ctrl+C` 停止所有服務。

## 本地開發

### 1. 安裝依賴（只需做一次）

```bash
# Node.js 依賴
npm install

# Python 依賴
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

### 2. 配置

```bash
cp .env.example .env
```

編輯 `.env`：

```env
# 富途登入
FUTU_LOGIN_ACCOUNT=你的牛牛ID
FUTU_LOGIN_PWD_MD5=密碼MD5

# OpenD 連接
FUTU_HOST=127.0.0.1
FUTU_PORT=11111

# 交易密碼（富途功能需要）
FUTU_TRADE_PWD=你的交易密碼

# 禁用日誌（避免權限問題）
FUTU_DISABLE_LOG=1
```

### 3. 手動啟動

```bash
source venv/bin/activate
python backend/main.py &   # 啟動後端
npm run dev               # 啟動前端
```

## 富途功能（可選）

**需要本地安裝 FutuOpenD**：

1. [下載並安裝 FutuOpenD](https://www.futuhk.com/support/courseDetail/1140)
2. 啟動 OpenD 並登入
3. 首次使用需配置 `.env` 並訪問 `http://localhost:8081` 完成 SMS 驗證
4. OpenD 設定中開啟 WebSocket（`websocket_port=33333`）

## 停止

```bash
pkill -f "python backend/main.py"  # 停止後端
pkill -f "next dev"                 # 停止前端
```

## 更新

```bash
git pull
npm install
source venv/bin/activate
pip install -r requirements.txt
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

---

## VPS 部署

詳細部署指南請睇 [VPS_DEPLOYMENT_GUIDE.md](VPS_DEPLOYMENT_GUIDE.md)
