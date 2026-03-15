import { NextResponse } from 'next/server'
import { getYahooQuoteWithMA } from '@/lib/yahooFinanceData'
import { getQuoteWithMA as getFutuQuoteWithMA } from '@/lib/futuAPI'

/**
 * 報價 API - 支援多個數據源
 * 參數:
 * - source: yahoo | futu (default: yahoo)
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params
  const source = new URL(request.url).searchParams.get('source') || 'yahoo'
  
  if (!symbol?.trim()) {
    return NextResponse.json({ error: '請提供股票代號' }, { status: 400 })
  }

  try {
    let quote: any
    
    if (source === 'futu') {
      quote = await getFutuQuoteWithMA(symbol)
    } else {
      quote = await getYahooQuoteWithMA(symbol)
    }
    
    return NextResponse.json({
      symbol: quote.symbol,
      name: quote.name,
      lastPrice: quote.lastPrice,
      open: quote.open,
      high: quote.high,
      low: quote.low,
      volume: quote.volume,
      turnover: quote.turnover,
      change: quote.change,
      changePercent: quote.changePercent,
      high52w: quote.high52w,
      low52w: quote.low52w,
      currency: source === 'futu' ? 'HKD' : 'USD',
      source: source,
      ema10: quote.ema10,
      ema20: quote.ema20,
      sma50: quote.sma50,
      sma200: quote.sma200,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`[${source.toUpperCase()} API] quote error:`, msg)
    return NextResponse.json({ error: `無法獲取報價: ${msg}` }, { status: 502 })
  }
}