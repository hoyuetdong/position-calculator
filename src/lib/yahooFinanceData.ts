/**
 * Yahoo Finance Data Engine
 * 直接用 HTTP API 獲取股票報價同歷史數據
 */

import { calculateSMA, calculateEMA } from './indicators'

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
 * 港股代碼喺 Yahoo Finance 係 4 位數字 (e.g., 0700.HK for 騰訊)
 */
function normalizeSymbol(symbol: string): string {
  const upper = symbol.toUpperCase().trim()

  if (upper.includes('.') || upper.startsWith('^')) {
    return upper
  }

  if (/^\d+$/.test(upper)) {
    // 港股：去除所有 leading zeros，再取最後4位（Yahoo 用 4 位數字）
    const stripped = upper.replace(/^0+/, '') || '0'
    // 如果係 5 位或更多，只取最後 4 位
    const last4 = stripped.slice(-4)
    // 不足 4 位嘅前面補 0
    const padded = last4.padStart(4, '0')
    return `${padded}.HK`
  }

  return upper
}

/**
 * 獲取股票報價 - 用 Yahoo Finance v8 API
 */
export async function getYahooQuote(symbol: string): Promise<YahooQuote> {
  const normalized = normalizeSymbol(symbol)
  console.log('[YahooAPI] Fetching quote for:', normalized)

  try {
    const response = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${normalized}?interval=1d&range=1d`,
      {
        headers: {
          'User-Agent': 'Mozilla/5.0',
        },
      }
    )

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    const data = await response.json()
    const result = data?.chart?.result?.[0]

    if (!result) {
      throw new Error(`No data found for symbol: ${normalized}`)
    }

    const meta = result.meta
    const quote = result.indicators?.quote?.[0] || {}

    // 計算 change 從 previous close
    const regularMarketPrice = meta.regularMarketPrice || 0
    const previousClose = meta.chartPreviousClose || meta.previousClose || 0
    const change = regularMarketPrice - previousClose
    const changePercent = previousClose > 0 ? (change / previousClose) * 100 : 0

    return {
      symbol: normalized,
      name: meta.shortName || meta.symbol || normalized,
      lastPrice: regularMarketPrice,
      open: meta.chartOpening || 0,
      high: meta.regularMarketDayHigh || 0,
      low: meta.regularMarketDayLow || 0,
      volume: meta.regularMarketVolume || 0,
      turnover: 0,
      change: change,
      changePercent: changePercent,
      high52w: meta.fiftyTwoWeekHigh || 0,
      low52w: meta.fiftyTwoWeekLow || 0,
    }
  } catch (error) {
    console.error('[YahooAPI] Quote error:', error)
    throw error
  }
}

/**
 * 獲取歷史K線數據 - 用 Yahoo Finance v8 API
 */
export async function getYahooKLines(
  symbol: string,
  days: number = 30
): Promise<YahooKLine[]> {
  const normalized = normalizeSymbol(symbol)
  console.log('[YahooAPI] Fetching K-lines for:', normalized, 'days:', days)

  try {
    const range = days <= 7 ? '5d' :
                  days <= 30 ? '1mo' :
                  days <= 90 ? '3mo' :
                  days <= 180 ? '6mo' :
                  days <= 365 ? '1y' :
                  days <= 730 ? '2y' : '5y'

    const response = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${normalized}?interval=1d&range=${range}`,
      {
        headers: {
          'User-Agent': 'Mozilla/5.0',
        },
      }
    )

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    const data = await response.json()
    const result = data?.chart?.result?.[0]

    if (!result || !result.timestamp || result.timestamp.length === 0) {
      return []
    }

    const timestamps = result.timestamp
    const quotes = result.indicators?.quote?.[0] || {}

    const klines: YahooKLine[] = timestamps.map((time: number, i: number) => ({
      time,
      open: quotes.open?.[i] || 0,
      high: quotes.high?.[i] || 0,
      low: quotes.low?.[i] || 0,
      close: quotes.close?.[i] || 0,
      volume: quotes.volume?.[i] || 0,
    }))

    // Filter out invalid entries
    return klines.filter(k => k.close > 0)
  } catch (error) {
    console.error('[YahooAPI] KLines error:', error)
    throw error
  }
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
