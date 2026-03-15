/**
 * Yahoo Finance Data Engine
 * 使用 yahoo-finance2 獲取股票報價同歷史數據
 */

import YahooFinance from 'yahoo-finance2'

const yahooFinance = new YahooFinance()

export interface YahooQuote {
  symbol: string
  name?: string
  lastPrice: number
  open: number
  high: number
  low: number
  volume: number
  turnover: number
  change: number
  changePercent: number
  high52w: number
  low52w: number
}

export interface YahooKLine {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
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
 * 獲取股票報價
 */
export async function getYahooQuote(symbol: string): Promise<YahooQuote> {
  const normalized = normalizeSymbol(symbol)
  
  try {
    const quote: any = await yahooFinance.quote(normalized)
    
    return {
      symbol: normalized,
      name: quote.shortName || quote.longName || normalized,
      lastPrice: quote.regularMarketPrice || 0,
      open: quote.regularMarketOpen || 0,
      high: quote.regularMarketDayHigh || 0,
      low: quote.regularMarketDayLow || 0,
      volume: quote.regularMarketVolume || 0,
      turnover: 0,
      change: quote.regularMarketChange || 0,
      changePercent: (quote.regularMarketChangePercent || 0),
      high52w: quote.fiftyTwoWeekHigh || 0,
      low52w: quote.fiftyTwoWeekLow || 0,
    }
  } catch (error) {
    console.error('[YahooAPI] Quote error:', error)
    throw error
  }
}

/**
 * 獲取歷史K線數據
 */
export async function getYahooKLines(
  symbol: string,
  days: number = 30
): Promise<YahooKLine[]> {
  const normalized = normalizeSymbol(symbol)
  
  try {
    const endDate = new Date()
    const startDate = new Date()
    startDate.setDate(startDate.getDate() - days)
    
    const history: any = await yahooFinance.historical(normalized, {
      period1: startDate,
      period2: endDate,
      interval: '1d',
    })
    
    if (!Array.isArray(history) || history.length === 0) {
      return []
    }
    
    return history.map((item) => ({
      time: Math.floor(item.date.getTime() / 1000),
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
      volume: item.volume,
    }))
  } catch (error) {
    console.error('[YahooAPI] KLines error:', error)
    throw error
  }
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
  
  const initialSlice = data.slice(0, period)
  let ema = initialSlice.reduce((a, b) => a + b, 0) / period
  
  const multiplier = 2 / (period + 1)
  
  for (let i = period; i < data.length; i++) {
    ema = (data[i] - ema) * multiplier + ema
  }
  return ema
}

/**
 * 獲取報價連埋移動平均線
 */
export async function getYahooQuoteWithMA(symbol: string): Promise<YahooQuote & {
  ema10: number | null
  ema20: number | null
  sma50: number | null
  sma200: number | null
}> {
  const quote = await getYahooQuote(symbol)
  
  let ema10: number | null = null
  let ema20: number | null = null
  let sma50: number | null = null
  let sma200: number | null = null
  
  try {
    const klines = await getYahooKLines(symbol, 2000)
    
    if (klines.length > 0) {
      const closes = klines.map((k) => k.close).filter((c) => c > 0)
      ema10 = calculateEMA(closes, 10)
      ema20 = calculateEMA(closes, 20)
      sma50 = calculateSMA(closes, 50)
      sma200 = calculateSMA(closes, 200)
    }
  } catch (err) {
    console.error('[YahooAPI] MA calculation error:', err)
  }
  
  return {
    ...quote,
    ema10,
    ema20,
    sma50,
    sma200,
  }
}