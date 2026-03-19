# VCP Position Calculator

專業交易倉位計算器

## 功能

- ATR 自動計算及建議止蝕位
- 1R/2R/3R 目標價
- 風險警告
- 支援港股、美股、A股
- ## 富途功能

需要啟動 OpenD（富途行情網關）：
- Windows/Mac: [下載 FutuOpenD](https://www.futuhk.com/support/courseDetail/1140)
- Docker: `futuopend` container 已自動啟動

配置好 `.env` 後訪問 `http://localhost:8081` 完成 SMS 驗證。

## 運行

### Docker (推薦)

```bash
docker-compose up -d
```

訪問 `http://localhost:3000`

### 本地開發

```bash
npm run dev
```

## 配置 (.env)

```env
FUTU_LOGIN_ACCOUNT=富途ID
FUTU_LOGIN_PWD_MD5=密碼MD5
FUTU_TRADE_PWD=交易密碼
```

## 股票代碼

| 市場 | 格式 | 例子 |
|------|------|------|
| 美股 | 直接輸入 | NVDA |
| 港股 | 純數字 | 00700 |
| A股 | 純數字 | 600519 |
