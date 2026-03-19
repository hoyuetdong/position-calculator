# VCP Position Calculator

專業交易倉位計算器

## 功能

- ATR 自動計算及建議止蝕位
- 1R/2R/3R 目標價
- 風險警告
- 支援港股、美股、A股
- 富途持倉同步（可選）

## 運行

Docker 部署：

```bash
cd position-calculator
docker-compose up -d
```

本地開發：

```bash
cd position-calculator
npm install
npm run dev
```

訪問 `http://localhost:3000`

## 配置

```bash
cp .env.example .env
```

編輯 `.env`：

```env
FUTU_HOST=host.docker.internal
FUTU_PORT=11111
FUTU_TRADE_PWD=你的交易密碼
```

## 富途功能（可選）

**需要本地安裝 FutuOpenD**，docker-compose 會透過 `host.docker.internal` 連接本機既 OpenD。

1. [下載並安裝 FutuOpenD](https://www.futuhk.com/support/courseDetail/1140)
2. 啟動 OpenD 並登入
3. 首次使用需配置 `.env` 並訪問 `http://localhost:8081` 完成 SMS 驗證
4. OpenD 設定中開啟 WebSocket（`websocket_port=33333`）

## 停止

Docker 部署：

```bash
docker-compose stop    # 停止（唔刪除 container）
docker-compose down    # 停止並刪除 container
```

本地開發：

喺 terminal 按 `Ctrl + C` 停止 dev server。

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
