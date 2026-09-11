'use client'
import { useEffect, useState } from 'react'
import { fetchWithTimeout } from '@/lib/fetchWithTimeout'

const labels: Record<string, string> = {
  OK: '運作正常', DISCONNECTED: '連線中斷', COOLDOWN: 'API 冷卻中', DEGRADED: '核對未完成', STALE: '資料未更新', STARTING: '正在核對',
  WAITING_STOP: '止蝕待提交', COVERED: '股數相符', UNDER_PROTECTED: '止蝕不足', EXCESS_STOP: '止蝕股數過多', NO_POSITION: '已無持倉',
  SUBMITTED: '已提交', pending: '待成交', partial: '部分成交／已補止蝕', PROTECTED: '止蝕已掛出',
  QUERY_RETRY: '查詢重試', RETRY: '補單重試', SUBMISSION_UNKNOWN: '提交待確認', SUBMITTING_STOP: '正在提交止蝕',
  FAILED_NEED_MANUAL: '需要人工處理', LEGACY_NEED_MANUAL: '舊紀錄待核對', POSITION_REVIEW: '持倉待核對',
  CLOSED_BY_USER: '已確認取消', CLOSED_UNFILLED: '已取消／失效', FILLED_ALL: '全部成交', FILLED_PART: '部分成交',
  CANCELLED_ALL: '全部取消', CANCELLED_PART: '部分取消', DISABLED: '已失效', FAILED: '提交失敗', DELETED: '紀錄已刪除',
  UNKNOWN: '無法確認', WAITING_SUBMIT: '等待提交', SUBMITTING: '提交中', WAITING_QUERY: '等待券商更新', RECHECK_QUEUED: '已排入核對',
}
const label = (s: string) => labels[s] || s
const date = (s?: string) => s ? new Date(s).toLocaleString('zh-HK', { hour12: false }) : '尚未完成'
const price = (n?: number) => typeof n === 'number' ? `$${n.toFixed(2)}` : '未記錄'
type Event = { timestamp: string; kind: string; changes: Record<string, any> }
type Order = { entry_order_id: string; symbol: string; created_at?: string; entry_price?: number; stop_loss_price?: number; quantity: number; status: string; events?: Event[] }
type Snapshot = {
  system_status: string; last_success_at?: string;
  active_alerts: { message: string }[];
  notifications: { id: string; message: string; kind: string; timestamp: string }[];
  checks: { symbol: string; direction: string; status: string; held_qty: number; protected_qty: number; waiting_qty?: number; checked_at: string }[];
}
function eventText(event: Event) {
  const c = event.changes
  if (event.kind === 'ENTRY_CHECK') return `入場單：${label(c.status)} · 累計成交 ${c.filled_qty} 股`
  if (event.kind === 'STOP_CHECK') return Object.entries(c.statuses || {}).map(([id, status]) =>
    `止蝕單 …${id.slice(-6)}：${label(String(status))}${c.quantities?.[id] !== undefined ? `，成交 ${c.filled?.[id] || 0}／${c.quantities[id]} 股` : ''}${c.prices?.[id] && c.prices[id] !== 'N/A' ? `，觸發價 $${c.prices[id]}` : ''}`).join('；')
  const parts = []
  if (c.status) parts.push(label(c.status))
  if (c.filled_qty !== undefined) parts.push(`累計成交 ${c.filled_qty} 股`)
  if (c.stop_loss_placed_qty !== undefined) parts.push(`已掛止蝕 ${c.stop_loss_placed_qty} 股`)
  if (c.entry_price != null) parts.push(`入場價 ${price(c.entry_price)}`)
  if (c.stop_loss_price != null) parts.push(`原定止蝕 ${price(c.stop_loss_price)}`)
  if (c.last_error) parts.push(c.last_error)
  if (c.completed) parts.push('補單追蹤已完成')
  return parts.join(' · ') || '紀錄已更新'
}

export default function ProtectionPanel() {
  const [data, setData] = useState<Snapshot | null>(null)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const [orders, setOrders] = useState<Order[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [historyError, setHistoryError] = useState('')
  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout>
    const refresh = async () => {
      try {
        const r = await fetchWithTimeout('/api/protection', { cache: 'no-store' })
        if (!r.ok) throw Error()
        const result = await r.json()
        if (active) { setData(result); setError('') }
      } catch { if (active) setError('無法連接監控服務') }
      if (active) timer = setTimeout(refresh, 30000)
    }
    refresh()
    return () => { active = false; clearTimeout(timer) }
  }, [])
  useEffect(() => {
    if (!historyOpen) return
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      try {
        const r = await fetch(`/api/order-history?symbol=${encodeURIComponent(search)}&offset=${offset}`, { cache: 'no-store', signal: controller.signal })
        if (!r.ok) throw Error()
        const result = await r.json()
        setOrders(result.orders); setTotal(result.total); setHistoryError('')
      } catch { if (!controller.signal.aborted) setHistoryError('無法讀取訂單紀錄') }
    }, 250)
    return () => { clearTimeout(timer); controller.abort() }
  }, [historyOpen, search, offset])
  const status = error ? 'DISCONNECTED' : data?.system_status || 'STARTING'
  return <section className="rounded-xl border border-border bg-card p-4 text-xs space-y-3" aria-label="交易保護與紀錄">
    <div className="flex flex-wrap justify-between gap-2">
      <span className={`font-medium ${status === 'OK' ? 'text-emerald-400' : 'text-amber-400'}`}>● {label(status)}</span>
      <span className="text-muted-foreground">最後成功核對：{date(data?.last_success_at)}</span>
    </div>
    {error && <p role="status" className="text-amber-400">{error}</p>}
    {(data?.active_alerts || []).map((alert, i) => <p key={i} className="border-l-2 border-amber-400 pl-2 text-amber-400">{alert.message}</p>)}
    <details>
      <summary className="cursor-pointer">持倉止蝕核對</summary>
      <div className="mt-2 max-h-48 overflow-auto divide-y divide-border">
        {(data?.checks || []).filter(c => c.held_qty || c.protected_qty || c.waiting_qty).map((c, i) => <div key={i} className="py-2">
          <div className="flex justify-between gap-2"><span>{c.symbol} · {c.direction === 'SHORT' ? '做空' : '做多'}</span>
            <span className={c.status === 'COVERED' && status === 'OK' ? 'text-emerald-400' : 'text-amber-400'}>{status === 'OK' ? '' : '上次：'}{label(c.status)}</span></div>
          <p className="mt-1 text-muted-foreground">持倉 {c.held_qty}／已確認止蝕 {c.protected_qty} 股{c.waiting_qty ? `／待提交 ${c.waiting_qty} 股` : ''} · {date(c.checked_at)}</p>
        </div>)}
        {!data?.checks.some(c => c.held_qty || c.protected_qty || c.waiting_qty) && <p className="py-2 text-muted-foreground">目前沒有需顯示的持倉紀錄</p>}
      </div>
    </details>
    <details>
      <summary className="cursor-pointer">通知紀錄（{data?.notifications.length || 0}）</summary>
      <div className="mt-2 max-h-48 overflow-auto space-y-2">
        {data?.notifications.map(n => <div key={n.id}>
          <p className={n.kind === 'recovered' ? 'text-emerald-400' : 'text-amber-400'}>{n.message}</p>
          <time className="text-[11px] text-muted-foreground">{date(n.timestamp)}</time>
        </div>)}
        {!data?.notifications.length && <p className="text-muted-foreground">目前沒有通知</p>}
      </div>
    </details>
    <details onToggle={e => setHistoryOpen(e.currentTarget.open)}>
      <summary className="cursor-pointer">完整訂單紀錄</summary>
      <input aria-label="搜尋訂單股票代號" placeholder="搜尋股票代號" value={search}
        onChange={e => { setSearch(e.target.value.toUpperCase()); setOffset(0) }}
        className="mt-3 w-full rounded border border-border bg-secondary px-3 py-2" />
      {historyError && <p className="mt-2 text-amber-400">{historyError}</p>}
      <div className="max-h-80 overflow-auto divide-y divide-border">
        {orders.map(order => <details key={order.entry_order_id} className="py-3">
          <summary className="cursor-pointer">{order.symbol} · {order.quantity} 股 · {label(order.status)}</summary>
          <p className="mt-2 text-muted-foreground">{date(order.created_at)} · 訂單 …{order.entry_order_id.slice(-6)}</p>
          <p className="mt-1">入場 {price(order.entry_price)} · 原定止蝕 {price(order.stop_loss_price)}</p>
          {!order.events?.length && <p className="mt-2 text-muted-foreground">舊紀錄未保存逐步時間線</p>}
          <ol className="mt-2 space-y-2 border-l border-border pl-3">
            {order.events?.map((event, i) => <li key={i}><time className="text-[11px] text-muted-foreground">{date(event.timestamp)}</time><p>{eventText(event)}</p></li>)}
          </ol>
        </details>)}
      </div>
      <div className="mt-2 flex justify-between items-center text-muted-foreground">
        <button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 25))} className="disabled:opacity-30">上一頁</button>
        <span>{total} 筆</span>
        <button disabled={offset + 25 >= total} onClick={() => setOffset(offset + 25)} className="disabled:opacity-30">下一頁</button>
      </div>
    </details>
  </section>
}
