import { NextResponse } from 'next/server'
import { getYahooKLines } from '@/lib/yahooFinanceData'
import { getHistoricalKLines as getFutuKLines } from '@/lib/futuAPI'

/**
 * 歷史 K 線 API - 支援多個數據源
 * 參數:
 * - source: yahoo | futu (default: yahoo)
 * - days: 天數 (default: 30)
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params
  const url = new URL(request.url)
  const source = url.searchParams.get('source') || 'yahoo'
  const days = Math.min(3000, Math.max(1, parseInt(url.searchParams.get('days') || '30', 10)))

  if (!symbol?.trim()) {
    return NextResponse.json({ error: '請提供股票代號' }, { status: 400 })
  }

  try {
    let klines
    
    if (source === 'futu') {
      klines = await getFutuKLines(symbol, days)
    } else {
      klines = await getYahooKLines(symbol, days)
    }
    
    return NextResponse.json(klines)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`[${source.toUpperCase()} API] klines error:`, msg)
    return NextResponse.json({ error: `無法獲取K線: ${msg}` }, { status: 502 })
  }
}