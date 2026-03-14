import { NextResponse } from 'next/server'

/**
 * 代號轉換：港股代號 -> Yahoo Finance 格式
 * 00700 -> 0700.HK
 * 0700 -> 0700.HK
 * 9988 -> 9988.HK
 */
function toYahooSymbol(symbol: string): string {
  const upper = symbol.toUpperCase().trim().replace(/\.HK$/i, '')
  // 如果係 5 位數既港股代號 (如 00700)，保留 4 位
  if (/^\d{5}$/.test(upper)) {
    return upper.slice(-4) + '.HK'
  }
  // 如果係 4 位數 (如 0700)
  if (/^\d{4}$/.test(upper)) {
    return upper + '.HK'
  }
  // 如果係 3 位或以下，直接用
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
 * Yahoo Finance 報價 API - 免費既股票報價服務
 * 支援港股 (0700.HK)、美股 (AAPL)、A股 (600519.SS)
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params
  
  if (!symbol?.trim()) {
    return NextResponse.json({ error: '請提供股票代號' }, { status: 400 })
  }

  const yahooSymbol = toYahooSymbol(symbol)
  
  try {
    const YahooFinance = (await import('yahoo-finance2')).default
    const yahoo = new YahooFinance({ suppressNotices: ['yahooSurvey'] })
    
    const quote = await yahoo.quote(yahooSymbol)
    
    const curPrice = quote.regularMarketPrice ?? 0
    const lastClose = quote.regularMarketPreviousClose ?? 0
    const change = lastClose ? curPrice - lastClose : 0
    const changePercent = lastClose ? (change / lastClose) * 100 : 0
    
      // 計算移動平均線
    let ema10: number | null = null
    let ema20: number | null = null
    let sma50: number | null = null
    let sma200: number | null = null
    
    try {
      const endDate = new Date()
      const startDate = new Date()
      // Yahoo Finance最多可以攞大約7年既歷史數據
      startDate.setFullYear(startDate.getFullYear() - 10)
      
      const history = await yahoo.historical(yahooSymbol, {
        period1: startDate,
        period2: endDate,
      })
      
      if (history && history.length > 0) {
        const closes = history.map(k => parseFloat(String(k.close))).filter((c: number) => c > 0)
        ema10 = calculateEMA(closes, 10)
        ema20 = calculateEMA(closes, 20)
        sma50 = calculateSMA(closes, 50)
        sma200 = calculateSMA(closes, 200)
      }
    } catch (histErr) {
      console.error('[Yahoo API] Historical data error:', histErr)
    }
    
    return NextResponse.json({
      symbol: yahooSymbol,
      name: quote.shortName || quote.longName || yahooSymbol,
      lastPrice: curPrice,
      open: quote.regularMarketOpen ?? 0,
      high: quote.regularMarketDayHigh ?? 0,
      low: quote.regularMarketDayLow ?? 0,
      volume: quote.regularMarketVolume ?? 0,
      turnover: 0,
      change,
      changePercent,
      high52w: quote.fiftyTwoWeekHigh ?? 0,
      low52w: quote.fiftyTwoWeekLow ?? 0,
      currency: quote.currency || 'HKD',
      source: 'yahoo',
      ema10,
      ema20,
      sma50,
      sma200,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error('[Yahoo API] quote error:', msg)
    return NextResponse.json({ error: `無法獲取報價: ${msg}` }, { status: 502 })
  }
}
