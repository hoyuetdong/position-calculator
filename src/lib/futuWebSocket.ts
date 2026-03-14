/**
 * 富途 OpenD API Client
 * 通過 WebSocket 連接 FutuOpenD 獲取行情同落單
 */

const FUTU_OPEND_HOST = '127.0.0.1'
const FUTU_OPEND_PORT = 11111

// FutuOpenD API 編號
const ProtoID = {
  // 行情相關
  QOT_SUB: 1001,           // 訂閱行情
  QOT_UNSUB: 1002,         // 取消訂閱
  QOT_GET_QUOTE: 1003,    // 獲取報價
  QOT_GET_HISTORY: 1005,  // 獲取歷史K線
  QOT_GET_TICKER: 1008,   // 獲取分時
  
  // 交易相關
  TRADE_PLACE_ORDER: 2001,    // 下單
  TRADE_MODIFY_ORDER: 2002,  // 修改訂單
  TRADE_CANCEL_ORDER: 2003,  // 取消訂單
  TRADE_GET_ORDER_LIST: 2005, // 獲取訂單列表
}

interface FutuOrder {
  ticker: string
  name?: string
  lastPrice?: number
  open?: number
  high?: number
  low?: number
  volume?: number
  turnover?: number
  change?: number
  changePercent?: number
  pe?: number
  high52w?: number
  low52w?: number
  marketCap?: number
  ema10?: number | null
  ema20?: number | null
  sma50?: number | null
  sma200?: number | null
}

interface FutuKLine {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

/**
 * 連接富途 WebSocket
 */
let ws: WebSocket | null = null
let wsResolve: ((value: void) => void) | null = null
let wsReject: ((reason?: any) => void) | null = null

export async function initFutuWebSocket(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      resolve()
      return
    }

    try {
      ws = new WebSocket(`ws://${FUTU_OPEND_HOST}:${FUTU_OPEND_PORT}`)

      ws.onopen = () => {
        console.log('[Futu] WebSocket connected')
        resolve()
      }

      ws.onerror = (error) => {
        console.error('[Futu] WebSocket error:', error)
        reject(new Error('FutuOpenD 連接失敗，請確保 FutuOpenD 正在運行'))
      }

      ws.onclose = () => {
        console.log('[Futu] WebSocket closed')
        ws = null
      }
    } catch (error) {
      reject(error)
    }
  })
}

/**
 * 發送請求到富途 OpenD
 */
function sendRequest(protoId: number, data: any): Promise<any> {
  return new Promise((resolve, reject) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      reject(new Error('WebSocket 未連接'))
      return
    }

    const request = {
      protoId,
      data: JSON.stringify(data)
    }

    const timeout = setTimeout(() => {
      reject(new Error('請求超時'))
    }, 10000)

    // 處理 response
    const originalOnMessage = ws.onmessage
    ws.onmessage = (event) => {
      try {
        const response = JSON.parse(event.data)
        if (response.protoId === protoId + 10000) { // response protoId 通常 = request + 10000
          clearTimeout(timeout)
          if (response.data?.retType === 0) {
            resolve(response.data)
          } else {
            reject(new Error(response.data?.retMsg || '請求失敗'))
          }
        }
      } catch {
        // 繼續監聽
      }
    }

    ws.send(JSON.stringify(request))
  })
}

/**
 * 標準化股票代碼 (轉為富途格式)
 */
function normalizeSymbolForFutu(symbol: string): string {
  const upper = symbol.toUpperCase().trim()
  
  // 如果已經有市場後綴，保持不變
  if (upper.includes('.')) {
    return upper
  }
  
  // 數字既係港股
  if (/^\d+$/.test(upper)) {
    return `${upper}.HK`
  }
  
  // 其他當作港股
  return `${upper}.HK`
}

/**
 * 計算移動平均線
 */
function calculateSMA(data: number[], period: number): number | null {
  if (data.length < period) return null
  const slice = data.slice(-period)
  return slice.reduce((a, b) => a + b, 0) / period
}

function calculateEMA(data: number[], period: number): number | null {
  if (data.length < period) return null
  const multiplier = 2 / (period + 1)
  let ema = data[0]
  for (let i = 1; i < data.length; i++) {
    ema = (data[i] - ema) * multiplier + ema
  }
  return ema
}

/**
 * 獲取報價 (富途)
 */
export async function getFutuQuote(symbol: string): Promise<FutuOrder> {
  await initFutuWebSocket()
  
  const futuSymbol = normalizeSymbolForFutu(symbol)
  
  // 使用本地 API 調用富途 OpenD 的 HTTP 接口
  // FutuOpenD 都會提供 HTTP API (端口 11111)
  try {
    const response = await fetch(`http://${FUTU_OPEND_HOST}:${FUTU_OPEND_PORT}/qot/get_quote`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker: futuSymbol,
        fields: ['last', 'open', 'high', 'low', 'volume', 'turnover', 'change', 'change_pct', 'pe', 'high_52w', 'low_52w', 'market_cap']
      })
    })
    
    if (!response.ok) {
      throw new Error(`Futu API error: ${response.status}`)
    }
    
    const result = await response.json()
    
    if (result.retType !== 0) {
      throw new Error(result.retMsg || '獲取報價失敗')
    }
    
    const data = result.data.tickerData[0]
    
    // 需要另行獲取移動平均線
    const closes = await getFutuHistoryPrices(futuSymbol, 200)
    const ema10 = calculateEMA(closes, 10)
    const ema20 = calculateEMA(closes, 20)
    const sma50 = calculateSMA(closes, 50)
    const sma200 = calculateSMA(closes, 200)
    
    return {
      ticker: data.ticker,
      name: data.name,
      lastPrice: data.last,
      open: data.open,
      high: data.high,
      low: data.low,
      volume: data.volume,
      turnover: data.turnover,
      change: data.change,
      changePercent: data.change_pct,
      pe: data.pe,
      high52w: data.high_52w,
      low52w: data.low_52w,
      marketCap: data.market_cap,
      ema10,
      ema20,
      sma50,
      sma200
    }
  } catch (error) {
    console.error('[Futu] Quote error:', error)
    throw error
  }
}

/**
 * 獲取歷史價格 (用於計算移動平均線)
 */
async function getFutuHistoryPrices(symbol: string, days: number): Promise<number[]> {
  try {
    const response = await fetch(`http://${FUTU_OPEND_HOST}:${FUTU_OPEND_PORT}/qot/get_history_kline`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker: symbol,
        type: 'K_DAY',
        count: days,
        fields: ['close']
      })
    })
    
    if (!response.ok) {
      return []
    }
    
    const result = await response.json()
    
    if (result.retType !== 0) {
      return []
    }
    
    return result.data.klines.map((k: any) => parseFloat(k.close))
  } catch {
    return []
  }
}

/**
 * 獲取歷史K線 (富途)
 */
export async function getFutuKLines(symbol: string, days: number = 30): Promise<FutuKLine[]> {
  await initFutuWebSocket()
  
  const futuSymbol = normalizeSymbolForFutu(symbol)
  
  try {
    const response = await fetch(`http://${FUTU_OPEND_HOST}:${FUTU_OPEND_PORT}/qot/get_history_kline`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker: futuSymbol,
        type: 'K_DAY',
        count: days
      })
    })
    
    if (!response.ok) {
      throw new Error(`Futu API error: ${response.status}`)
    }
    
    const result = await response.json()
    
    if (result.retType !== 0) {
      throw new Error(result.retMsg || '獲取K線失敗')
    }
    
    return result.data.klines.map((k: any) => ({
      time: k.time,
      open: parseFloat(k.open),
      high: parseFloat(k.high),
      low: parseFloat(k.low),
      close: parseFloat(k.close),
      volume: parseFloat(k.volume)
    }))
  } catch (error) {
    console.error('[Futu] K-line error:', error)
    throw error
  }
}

/**
 * 獲取ATR (富途)
 */
export async function getFutuATR(symbol: string, period: number = 14): Promise<number | null> {
  try {
    const klines = await getFutuKLines(symbol, period + 10)
    
    if (klines.length < period) {
      return null
    }
    
    const atrData = klines.slice(-period).map(k => {
      const high = k.high
      const low = k.low
      const close = k.close
      const tr = Math.max(high - low, Math.abs(high - close), Math.abs(low - close))
      return tr
    })
    
    return atrData.reduce((a, b) => a + b, 0) / period
  } catch {
    return null
  }
}

/**
 * 下單 (富途)
 */
export interface FutuOrderRequest {
  ticker: string
  price: number
  qty: number
  side: 'Buy' | 'Sell'
  orderType: 'Limit' | 'Market'
}

export interface FutuOrderResult {
  success: boolean
  orderId?: string
  message: string
}

export async function placeFutuOrder(order: FutuOrderRequest): Promise<FutuOrderResult> {
  await initFutuWebSocket()
  
  const futuSymbol = normalizeSymbolForFutu(order.ticker)
  
  try {
    const response = await fetch(`http://${FUTU_OPEND_HOST}:${FUTU_OPEND_PORT}/trade/place_order`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker: futuSymbol,
        price: order.price,
        qty: order.qty,
        side: order.side,
        orderType: order.orderType,
        // 市場別 (港股)
        market: 'HK'
      })
    })
    
    if (!response.ok) {
      return { success: false, message: `HTTP error: ${response.status}` }
    }
    
    const result = await response.json()
    
    if (result.retType === 0) {
      return {
        success: true,
        orderId: result.data.orderId,
        message: '訂單已提交'
      }
    } else {
      return {
        success: false,
        message: result.retMsg || '下單失敗'
      }
    }
  } catch (error) {
    return {
      success: false,
      message: String(error)
    }
  }
}

/**
 * 關閉連接
 */
export async function closeFutuWebSocket(): Promise<void> {
  if (ws) {
    ws.close()
    ws = null
  }
}
