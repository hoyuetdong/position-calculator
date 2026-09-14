'use client'
import { useEffect, useState, useRef } from 'react'
import { BrokerPosition } from '@/lib/positionsAPI'
import { fetchWithTimeout } from '@/lib/fetchWithTimeout'

type Stop = { aux_price: number; original_qty: number }
type Preview = { token?: string; bid: number | null; bid_time: string; quote_read_at: string; warning: string;
  break_even?: number; stops?: Stop[];
  price: number | null; principal: number | null; quantity?: number; held_qty: number; keep_qty?: number; expected_gross?: number; stop: Stop | null }
type Job = { id: string; symbol: string; phase: string; quantity: number; price: number; filled_qty: number;
  kind?: string; break_even?: number;
  principal: number; gross?: number; net?: number; fee?: number; remaining_principal?: number; achieved?: boolean;
  remaining_qty?: number; error?: string; events: {timestamp: string; message: string}[] }
const phaseLabels: Record<string, string> = { PREPARE:'準備核對', RESIZING:'確認止蝕調整', READY:'準備賣出', SUBMITTING:'確認賣單結果', OPEN:'賣單已提交', SETTLE:'核對剩餘止蝕', RESTORING:'確認剩餘止蝕', FEE_PENDING:'等待費用回報', DONE:'處理完成' }
const money = (n?: number | null) => typeof n === 'number' ? `$${n.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 4})}` : '—'
async function request(action: string, body?: unknown) {
  const response = await fetchWithTimeout(`/api/zero-cost/${action}`, { cache: 'no-store', timeout: 35000,
    ...(body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}) })
  const data = await response.json()
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : '未能完成，請檢查輸入及處理紀錄')
  return data
}
export default function ZeroCostRecovery({selected, mode = 'recovery', onClose, onSync}: {selected: BrokerPosition | null; mode?: 'recovery' | 'partial'; onClose: () => void; onSync: () => void}) {
  const partial = mode === 'partial'
  const [fraction, setFraction] = useState(2)
  const lastFills = useRef<string | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [preview, setPreview] = useState<Preview | null>(null)
  const [principal, setPrincipal] = useState('')
  const [price, setPrice] = useState('')
  const [fee, setFee] = useState('0')
  const [review, setReview] = useState(false)
  const [agreed, setAgreed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [jobsError, setJobsError] = useState('')
  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try { const data = await request('jobs'); if (active) {setJobs(data.jobs);setJobsError('');const signature = JSON.stringify(data.jobs.map((j: Job) => [j.id,j.filled_qty,j.phase === 'DONE']));if(lastFills.current !== null && signature !== lastFills.current) onSync();lastFills.current = signature} }
      catch { if(active) setJobsError('處理紀錄暫時無法更新') }
      if(active) timer = setTimeout(poll, 15000)
    }
    poll(); return () => {active = false;clearTimeout(timer)}
  }, [])
  useEffect(() => {
    let active = true
    setPreview(null);setReview(false);setAgreed(false);setError('');setPrincipal('');setPrice('');setFee('0');setFraction(2)
    if (!selected) return
    setBusy(true)
    request('preview', {symbol:selected.symbol, account_id:selected.account_id || '', ...(partial ? {fraction:2} : {})}).then(data => {
      if(active) {setPreview(data);setPrincipal(data.principal == null ? '' : String(data.principal));setPrice(data.price == null ? '' : String(data.price))}
    }).catch(e => {if(active) setError(e.message)}).finally(() => {if(active) setBusy(false)})
    return () => {active = false}
  }, [selected, mode])
  async function prepare() {
    if (!selected) return
    setBusy(true);setError('')
    try {
      const data = await request('preview', {symbol:selected.symbol, account_id:selected.account_id || '', principal:Number(principal), price:Number(price), fee_buffer:Number(fee), ...(partial ? {fraction} : {})})
      if(!data.token) throw Error('請核實本金及限價')
      setPreview(data);setReview(true);setAgreed(false)
    } catch(e) {setError((e as Error).message)} finally {setBusy(false)}
  }
  async function confirm() {
    if(!preview?.token || !agreed) return
    setBusy(true);setError('')
    try {
      const job = await request('confirm', {token:preview.token, confirmed:true})
      setJobs(current => [job, ...current.filter(j => j.id !== job.id)])
      onClose();onSync()
    } catch(e) {setError((e as Error).message)} finally {setBusy(false)}
  }
  return <>
    {(jobs.length > 0 || jobsError) && <details className="mt-4 border-t border-border pt-3" open>
      <summary className="cursor-pointer text-sm font-medium">持倉賣出紀錄</summary>
      {jobsError && <p className="text-xs text-warning mt-2">{jobsError}</p>}
      <div className="max-h-72 overflow-auto divide-y divide-border text-xs">
        {jobs.map(job => <details key={job.id} className="py-3">
          <summary className="cursor-pointer">{job.symbol} · <span className={job.error ? 'text-warning' : job.achieved ? 'text-profit' : 'text-sky-400'}>{job.error ? '需要核對' : job.achieved ? '本金已收回' : phaseLabels[job.phase] || job.phase}</span> · 成交 {job.filled_qty || 0}/{job.quantity} 股</summary>
          <p className="mt-2">限價 {money(job.price)} · {job.kind === 'PARTIAL_EXIT' ? `分批賣出／保本價 ${money(job.break_even)}` : `本金 ${money(job.principal)}`}</p>
          <p className="mt-1">{job.net === undefined ? `累計成交金額 ${money(job.gross)}（未扣費用）` : `實收 ${money(job.net)} · 費用 ${money(job.fee)} · 尚未收回 ${money(job.remaining_principal)}`}</p>
          {job.remaining_qty !== undefined && <p className="mt-1">剩餘持倉 {job.remaining_qty} 股</p>}
          {['PREPARE','READY'].includes(job.phase) && <button className="mt-2 text-sky-400" onClick={async () => {try {const updated = await request('cancel', {token:job.id,confirmed:true});setJobs(current => current.map(j => j.id === updated.id ? updated : j))} catch(e) {setJobsError((e as Error).message)}}}>取消準備</button>}
          {job.phase === 'OPEN' && <p className="mt-2 text-muted-foreground">如需取消賣單，請在富途操作，系統會重新核對剩餘止蝕。</p>}
          {job.error && <p className="mt-2 text-warning">{job.error}</p>}
          <ol className="mt-2 space-y-1 text-muted-foreground">{job.events.map((e,i) => <li key={i}>{new Date(e.timestamp).toLocaleString('zh-HK', {hour12:false})} · {e.message}</li>)}</ol>
        </details>)}
      </div>
    </details>}
    {selected && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4" role="dialog" aria-modal="true" aria-labelledby="recover-title">
      <div className="w-full max-w-md max-h-[90vh] overflow-auto rounded-xl border border-border bg-card p-5 space-y-4">
        <div className="flex justify-between items-center"><h3 id="recover-title" className="font-semibold text-lg">{selected.symbol} · {partial ? '分批賣出' : '收回本金'}</h3><button disabled={busy} onClick={onClose} aria-label="關閉" className="px-2">✕</button></div>
        <p className="text-xs text-warning">真實交易 · 限價賣出 · 當日有效 · 全時段</p>
        {preview && <p className="text-xs text-muted-foreground">買一價 {money(preview.bid)} <button disabled={busy || review} className="ml-2 text-sky-400 disabled:opacity-40" onClick={() => preview.bid && setPrice(String(preview.bid))}>使用買一價</button><br/>報價讀取：{preview.quote_read_at ? new Date(preview.quote_read_at).toLocaleString('zh-HK', {hour12:false}) : '未取得'}</p>}
        {preview?.warning && <p className="text-xs text-warning">{preview.warning}</p>}
        {!review ? <>
          {partial ? <><label className="block text-sm">賣出比例<select className="ml-3 rounded bg-secondary p-2" value={fraction} onChange={e => setFraction(Number(e.target.value))}>{[2,3,4].map(n => <option key={n} value={n}>1/{n}</option>)}</select></label>
            <p className="text-xs text-muted-foreground">股數向下取整 · 成交後剩餘止蝕推至平均買入成本 {money(preview?.break_even)}（不含賣出費用）；較高的原止蝕不會下調。</p></> : <>
            <label className="block text-sm">尚未收回本金 ($)<input className="mt-1 w-full rounded bg-secondary p-2" type="number" min="0" step="0.01" value={principal} onChange={e => setPrincipal(e.target.value)} /></label>
            <p className="text-xs text-muted-foreground">預填券商攤薄成本估算，請核實過往買賣及費用後確認。</p></>}
          <div className="grid grid-cols-2 gap-3">
            <label className="text-sm">賣出限價 ($)<input className="mt-1 w-full rounded bg-secondary p-2" type="number" min="0" step="0.01" value={price} onChange={e => setPrice(e.target.value)} /></label>
            {!partial && <label className="text-sm">費用預留 ($)<input className="mt-1 w-full rounded bg-secondary p-2" type="number" min="0" step="0.01" value={fee} onChange={e => setFee(e.target.value)} /></label>}
          </div>
          <button disabled={busy || (!partial && !Number(principal)) || !Number(price)} className="w-full rounded bg-primary py-2 font-medium text-black disabled:opacity-40" onClick={prepare}>{busy ? '正在核對…' : '更新報價及預覽賣單'}</button>
        </> : preview && <>
          <div className="rounded bg-secondary p-3 space-y-2 text-sm">
            <p>賣出 <b>{preview.quantity} 股</b> × {money(Number(price))}</p>
            <p>預計收回 <b>{money(preview.expected_gross)}</b>（未扣費用）</p>
            <p>預計保留 <b>{preview.keep_qty} 股</b></p>
            {preview.stop && <p>原止蝕 {money(preview.stop.aux_price)}：{preview.stop.original_qty} → {preview.keep_qty} 股</p>}
            {partial && <p>成交後止蝕推至 {money(preview.break_even)} · 現有 {preview.stops?.length || 0} 張止蝕</p>}
          </div>
          {(preview.stop || partial) && <p className="text-xs text-warning">會先調整原止蝕股數，再提交賣單。掛單期間，待賣股數不受原止蝕保護；取消或部分成交後會重新核對。</p>}
          <label className="flex gap-2 text-sm"><input type="checkbox" checked={agreed} onChange={e => setAgreed(e.target.checked)} />我已核實{partial ? '股數、限價及保本止蝕' : `本金、股數、限價${preview.stop ? '及止蝕調整' : ''}`}，確認真實賣出。</label>
          <div className="flex gap-2"><button disabled={busy} className="rounded bg-secondary px-4 py-2" onClick={() => setReview(false)}>返回修改</button><button disabled={busy || !agreed} className="flex-1 rounded bg-primary py-2 font-medium text-black disabled:opacity-40" onClick={confirm}>{busy ? '正在確認…' : '確認賣出'}</button></div>
        </>}
        {error && <p role="alert" className="text-sm text-loss">{error}</p>}
      </div>
    </div>}
  </>
}
