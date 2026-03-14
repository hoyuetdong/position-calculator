/**
 * Yahoo Finance API Client
 * 通過本地 proxy server 攞數據，避免 CORS
 */

export interface QuoteData {
  symbol?: string
  ticker?: string
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

/**
 * 標準化股票代碼
 */
function normalizeSymbol(symbol: string): string {
  const upper = symbol.toUpperCase().trim()
  
  if (upper.includes('.') || upper.startsWith('^')) {
    return upper
  }
  
  if (/^\d+$/.test(upper)) {
    return `${upper}.HK`
  }
  
  return upper
}

/**
 * 計算 SMA (Simple Moving Average)
 */
function calculateSMA(data: number[], period: number): number | null {
  if (data.length < period) return null
  const slice = data.slice(-period)
  return slice.reduce((a, b) => a + b, 0) / period
}

/**
 * 計算 EMA (Exponential Moving Average)
 */
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
 * 通過本地 API proxy 獲取數據
 */
async function fetchLocal(symbol: string, range: string = '1y'): Promise<any> {
  const response = await fetch(`/api/quote/${symbol}?range=${range}`)
  if (!response.ok) {
    throw new Error(`API error: ${response.status}`)
  }
  return response.json()
}

/**
 * 初始化
 */
export async function initFutuAPI(): Promise<void> {
  // Proxy 已喺度
}

/**
 * 獲取報價
 */
export async function getQuote(symbol: string): Promise<QuoteData> {
  const normalized = normalizeSymbol(symbol)
  
  try {
    const data = await fetchLocal(normalized)
    
    const result = data?.chart?.result?.[0]
    if (!result) {
      throw new Error(`No data for ${symbol}`)
    }
    
    const meta = result.meta
    
    // 計算移動平均線
    const quote = result.indicators?.quote?.[0] || {}
    const closes = (quote.close || []).filter((c: number) => c > 0)
    
    const ema10 = calculateEMA(closes, 10)
    const ema20 = calculateEMA(closes, 20)
    const sma50 = calculateSMA(closes, 50)
    const sma200 = calculateSMA(closes, 200)
    
    return {
      symbol: normalized,
      name: meta.shortName || meta.symbol || normalized,
      lastPrice: meta.regularMarketPrice || 0,
      open: meta.chartPreviousClose || meta.regularMarketPreviousClose || 0,
      high: meta.regularMarketDayHigh || 0,
      low: meta.regularMarketDayLow || 0,
      volume: meta.regularMarketVolume || 0,
      change: meta.regularMarketChange || 0,
      changePercent: meta.regularMarketChangePercent || 0,
      high52w: meta.fiftyTwoWeekHigh || 0,
      low52w: meta.fiftyTwoWeekLow || 0,
      ema10,
      ema20,
      sma50,
      sma200
    }
  } catch (error) {
    console.error('[API] Error:', error)
    throw error
  }
}

/**
 * 獲取歷史K線數據
 */
export async function getHistoricalKLines(symbol: string, days: number = 30): Promise<any[]> {
  const normalized = normalizeSymbol(symbol)
  
  // 需要更長時間既數據俾圖表同移動平均線 (最少 250 日)
  const range = days >= 300 ? '3y' : (days >= 250 ? '2y' : (days >= 60 ? '1y' : '3mo'))
  
  try {
    const data = await fetchLocal(normalized, range)
    const result = data?.chart?.result?.[0]
    
    if (!result) {
      return []
    }
    
    const timestamps = result.timestamp || []
    const quote = result.indicators?.quote?.[0] || {}
    
    return timestamps.map((time: number, i: number) => ({
      time,
      open: quote.open?.[i] || 0,
      high: quote.high?.[i] || 0,
      low: quote.low?.[i] || 0,
      close: quote.close?.[i] || 0,
      volume: quote.volume?.[i] || 0
    }))
  } catch (error) {
    console.error('[API] K-line error:', error)
    return []
  }
}

/**
 * 獲取ATR數據
 */
export async function getATR(symbol: string, period: number = 14): Promise<number | null> {
  try {
    const klines = await getHistoricalKLines(symbol, period + 10)
    
    if (klines.length < period) {
      return null
    }
    
    const atrData = klines.slice(-period).map(k => {
      const high = parseFloat(k.high)
      const low = parseFloat(k.low)
      const close = parseFloat(k.close)
      const tr = Math.max(high - low, Math.abs(high - close), Math.abs(low - close))
      return tr
    })
    
    return atrData.reduce((a, b) => a + b, 0) / period
  } catch (error) {
    return null
  }
}

/**
 * 關閉連接
 */
export async function closeFutuAPI(): Promise<void> {
  // 冇野要做
}