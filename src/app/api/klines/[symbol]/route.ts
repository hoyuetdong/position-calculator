import { NextResponse } from 'next/server'
import { getYahooKLines } from '@/lib/yahooFinanceData'

/**
 * 歷史 K 線 API - 支援多個數據源
 * 參數:
 * - source: yahoo | futu (default: yahoo)
 * - days: 天數 (default: yahoo=2000, futu=365)
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params
  const url = new URL(request.url)
  const source = url.searchParams.get('source') || 'yahoo'
  const maxDays = source === 'futu' ? 365 : 2000
  const days = Math.min(maxDays, Math.max(1, parseInt(url.searchParams.get('days') || String(maxDays), 10)))

  if (!symbol?.trim()) {
    return NextResponse.json({ error: '請提供股票代號' }, { status: 400 })
  }

  try {
    let klines: any[]

    if (source === 'futu') {
      // 通過 backend API 嚟拎 K 線（避免前端直接連接 OpenD）
      const backendUrl = process.env.PYTHON_API_URL || 'http://backend:8000'

      // 轉換代碼格式
      const normalizedSymbol = symbol.toUpperCase().trim()
      let futuCode: string
      if (normalizedSymbol.includes('.')) {
        futuCode = normalizedSymbol
      } else if (/^\d+$/.test(normalizedSymbol)) {
        const stripped = normalizedSymbol.replace(/^0+/, '') || '0'
        futuCode = `HK.${stripped.padStart(5, '0')}`
      } else {
        futuCode = `US.${normalizedSymbol}`
      }

      console.log(`[KLines API] Fetching futu klines for: ${futuCode}`)

      const futuResponse = await fetch(
        `${backendUrl}/api/kline/${futuCode}?days=${days}&ktype=DAY`,
        { signal: AbortSignal.timeout(15000) }
      )

      if (!futuResponse.ok) {
        const errData = await futuResponse.json().catch(() => ({}))
        throw new Error(errData.detail || `Backend API error: ${futuResponse.status}`)
      }

      const futuData = await futuResponse.json()
      console.log(`[KLines API] Futu response: ${futuData.klines?.length || 0} klines`)

      // 轉換格式以匹配前端預期
      klines = (futuData.klines || []).map((k: any) => ({
        time: k.time,
        open: k.open,
        high: k.high,
        low: k.low,
        close: k.close,
        volume: k.volume,
      }))
    } else {
      // Yahoo Finance
      klines = await getYahooKLines(symbol, days)
    }

    return NextResponse.json(klines)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`[${source.toUpperCase()} API] klines error:`, msg)
    return NextResponse.json({ error: `無法獲取K線: ${msg}` }, { status: 502 })
  }
}