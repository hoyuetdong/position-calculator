/**
 * Yahoo Finance API Client
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
 * 計算 SMA
 */
function calculateSMA(data: number[], period: number): number | null {
  if (data.length < period) return null
  const slice = data.slice(-period)
  return slice.reduce((a, b) => a + b, 0) / period
}

/**
 * 計算 EMA
 */
function calculateEMA(data: number[], period: number): number | null {
  if (data.length < period) return null
  
  // 初始 EMA = SMA of first 'period' values
  const initialSlice = data.slice(0, period)
  let ema = initialSlice.reduce((a, b) => a + b, 0) / period
  
  const multiplier = 2 / (period + 1)
  
  // 由第period個數據開始計
  for (let i = period; i < data.length; i++) {
    ema = (data[i] - ema) * multiplier + ema
  }
  return ema
}

/**
 * 初始化
 */
export async function initFutuAPI(): Promise<void> {
  // 冇野要做
}

/**
 * 獲取報價 - 直接用本地 proxy
 */
export async function getQuote(symbol: string): Promise<QuoteData> {
  const normalized = normalizeSymbol(symbol)
  
  try {
    const response = await fetch(`/api/quote/${symbol}`)
    const data = await response.json()
    
    if (data.error) {
      throw new Error(data.error)
    }
    
    // 計算移動平均線需要歷史數據
    let ema10: number | null = null
    let ema20: number | null = null
    let sma50: number | null = null
    let sma200: number | null = null
    
    try {
      const histResponse = await fetch(`/api/klines/${symbol}?days=2000`)
      const histData = await histResponse.json()
      
      if (Array.isArray(histData) && histData.length > 0) {
        const closes = histData.map((k: any) => parseFloat(k.close)).filter((c: number) => c > 0)
        ema10 = calculateEMA(closes, 10)
        ema20 = calculateEMA(closes, 20)
        sma50 = calculateSMA(closes, 50)
        sma200 = calculateSMA(closes, 200)
      }
    } catch {
      // 移動平均線 optional，fail咗都唔理
    }
    
    return {
      symbol: data.symbol || normalized,
      name: data.name || normalized,
      lastPrice: data.lastPrice,
      open: data.open,
      high: data.high,
      low: data.low,
      volume: data.volume,
      turnover: data.turnover,
      change: data.change,
      changePercent: data.changePercent,
      high52w: data.high52w,
      low52w: data.low52w,
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
  
  try {
    const response = await fetch(`/api/klines/${symbol}?days=${Math.min(3000, days)}`)
    const data = await response.json()
    
    if (Array.isArray(data)) {
      return data
    }
    return []
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
