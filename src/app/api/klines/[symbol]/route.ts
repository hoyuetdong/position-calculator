import { NextResponse } from 'next/server'

/**
 * 代號轉換：港股代號 -> Yahoo Finance 格式
 * 00700 -> 0700.HK
 * 0700 -> 0700.HK
 * 9988 -> 9988.HK
 */
function toYahooSymbol(symbol: string): string {
  const upper = symbol.toUpperCase().trim().replace(/\.HK$/i, '')
  if (/^\d{5}$/.test(upper)) {
    return upper.slice(-4) + '.HK'
  }
  if (/^\d{4}$/.test(upper)) {
    return upper + '.HK'
  }
  return upper
}

/**
 * Yahoo Finance 歷史 K 線 API - 免費數據
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params
  const days = Math.min(3000, Math.max(1, parseInt(new URL(request.url).searchParams.get('days') || '30', 10)))

  if (!symbol?.trim()) {
    return NextResponse.json({ error: '請提供股票代號' }, { status: 400 })
  }

  const yahooSymbol = toYahooSymbol(symbol)

  try {
    const YahooFinance = (await import('yahoo-finance2')).default
    const yahoo = new YahooFinance({ suppressNotices: ['yahooSurvey'] })
    
    const endDate = new Date()
    const startDate = new Date()
    startDate.setDate(startDate.getDate() - days)
    
    const history = await yahoo.historical(yahooSymbol, {
      period1: startDate,
      period2: endDate,
    })
    
    // 轉換為 K 線格式，並確保按時間升序排列
    const klines = history.map(k => ({
      time: Math.floor(new Date(k.date).getTime() / 1000),
      open: k.open,
      high: k.high,
      low: k.low,
      close: k.close,
      volume: k.volume,
    })).sort((a, b) => a.time - b.time)

    return NextResponse.json(klines)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error('[Yahoo API] klines error:', msg)
    return NextResponse.json({ error: `無法獲取K線: ${msg}` }, { status: 502 })
  }
}
