# 美股時段報價

`session_quote.py` 以富途 `get_market_state` 選擇快照欄位：
OVERNIGHT → overnight_price；PRE_MARKET_BEGIN → pre_price；
AFTER_HOURS_BEGIN → after_price；MORNING／AFTERNOON → last_price。
不要以最高價、非零欄位優先序或收市價判定当前交易時段。

快照 update_time 按 America/New_York（包含夏令時間）解析。
未知／休市、缺價、非有限值、超過三分鐘或異常未來時間均不得作自動下單依據。
仍可顯示標示清楚的參考價，使用者亦可明確選擇限價模式。

前端日線及 ATR 沿用既有資料來源；美股顯示價格改用富途時段報價。
可見頁面每三十秒只更新價格，不修改入場價、止蝕價或 ATR。
自動模式下單前再次查價；單種類別改變須重新確認，後端也會在任何交易寫入前核對。
明確限價／突破模式不再依照報價改變單種。原生 STOP 的券商時段限制未改變。

所有查詢共用 BrokerIO 快取與限頻；市場狀態快取十秒、每三十秒最多六次，
快照沿用兩秒快取及原有限頻。沒有建立新的常駐訂閱或交易監價服務。
