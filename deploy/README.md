# VPS 更新及長期運行

`start-vps.sh` 保留 VPS 原本清理及重啟 OpenD 嘅流程；安裝 systemd 後會透過 systemd 起前後端。`stop-vps.sh` 同樣支援 systemd。

初次安裝（喺 `/opt/vcp-calculator` 執行）：

```sh
npm run build
mkdir -p .next/standalone/.next
ln -sfn /opt/vcp-calculator/.next/static .next/standalone/.next/static
cp -a public .next/standalone/
install -m 644 deploy/vcp-*.service deploy/vcp-cache-clean.timer /etc/systemd/system/
install -m 644 deploy/journald-vcp.conf /etc/systemd/journald@vcp.conf
install -m 644 deploy/vcp-logrotate /etc/logrotate.d/vcp-calculator
systemctl daemon-reload
# 先停止舊 screen 前後端，再啟動，避免兩個止蝕監控同時運行。
systemctl enable --now vcp-backend vcp-frontend vcp-cache-clean.timer
```

日常檢查：

```sh
systemctl status vcp-backend vcp-frontend vcp-cache-clean.timer
journalctl --namespace=vcp -u vcp-backend -n 80
```

- 前後端異常退出會自動重啟；止蝕監控用檔案鎖防止同一資料目錄開兩個 worker。唔好開多個 uvicorn workers。
- 後端 `/api/health` 受 API key 保護，會檢查監控 thread 有冇停頓超過 180 秒。畫面每 30 秒更新止蝕追蹤及失敗訊息。
- 每小時只清超過 24 小時嘅 Next 行情 fetch cache；新行情請求用 no-store，同時有 15 秒逾時。
- 應用程式獨立 journal 上限 100MB／7 日；舊 logs 保留 7 份壓縮輪替。
- `backend/pending_stops.json`、`backend/order_history.json` 永久保留，唔會畀清理程序刪走，亦唔提交 Git。
- JSON 用 atomic replace；落止蝕前持久寫入意圖及唯一 remark。提交結果唔明確時只核對，唔重送，避免重複止蝕。
- `SUBMISSION_UNKNOWN`：請喺富途核對。`FAILED_NEED_MANUAL`：失敗仍保留喺畫面。舊版本冇 remark 嘅已成交紀錄會標成 `LEGACY_NEED_MANUAL`，唔自動再掛止蝕。
- 新單使用原本帳戶及交易環境監控，切換畫面 REAL/SIMULATE 唔會改變舊單監控帳戶。查當日清單冇結果會查歷史，查詢失敗保留追蹤。
- 美股實盤限價單使用 Session.ALL；股票及帳戶必須支援。原生 STOP／市價／突破單仍然只支援盤中；冇聲稱全時段止蝕。GTD 喺目前 SDK 未支援，會明確拒絕。
- 百分比 hard stop 計觸發價，唔保證實際虧損上限；成交會受滑價／跳空影響。

核對資料：https://openapi.futunn.com/futu-api-doc/en/trade/place-order.html ，https://www.futuhk.com/en/support/topic2_1532

測試：`python -m unittest discover -s backend/tests -v`（假券商，唔連 OpenD），`npm run build`。
