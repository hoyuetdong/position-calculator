import { NextResponse } from 'next/server'
import { getYahooQuoteWithMA } from '@/lib/yahooFinanceData'

/**
 * 報價 API - 支援多個數據源
 * 參數:
 * - source: yahoo | futu (default: yahoo)
 *
 * 注意：當 source=futu 時，通過 backend API 嚟拎行情
 *       咁樣可以避免喺 Next.js server 直接用 futu-api
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params
  const url = new URL(request.url)
  const source = url.searchParams.get('source') || 'yahoo'

  if (!symbol?.trim()) {
    return NextResponse.json({ error: '請提供股票代號' }, { status: 400 })
  }

  try {
    let quote: any

    if (source === 'futu') {
      // 通過 backend API 嚟拎行情
      const backendUrl = process.env.PYTHON_API_URL || 'http://backend:8000'

      // 轉換代碼格式
      const normalizedSymbol = symbol.toUpperCase().trim()
      let futuCode: string
      if (normalizedSymbol.includes('.')) {
        // 已經有 market prefix，直接用
        futuCode = normalizedSymbol
      } else if (/^\d+$/.test(normalizedSymbol)) {
        // 港股：去除 leading zeros，再 pad to 5 digits
        const stripped = normalizedSymbol.replace(/^0+/, '') || '0'
        futuCode = `HK.${stripped.padStart(5, '0')}`
      } else {
        // 美股：加 US. 前綴
        futuCode = `US.${normalizedSymbol}`
      }

      console.log(`[Quote API] Fetching futu quote for: ${futuCode}`)
      console.log(`[Quote API] Backend URL: ${backendUrl}`)

      try {
        const futuResponse = await fetch(`${backendUrl}/api/quote/${futuCode}`, {
          signal: AbortSignal.timeout(15000),  // 增加 timeout，因為要拎 K 線數據
        })

        console.log(`[Quote API] Backend response status: ${futuResponse.status}`)

        if (!futuResponse.ok) {
          const errData = await futuResponse.json().catch(() => ({}))
          console.error(`[Quote API] Backend error:`, errData)
          throw new Error(errData.detail || `Backend API error: ${futuResponse.status}`)
        }

        const futuData = await futuResponse.json()
        console.log(`[Quote API] Futu response:`, JSON.stringify(futuData))

        // 新格式：{ success, quotes: [{ code, name, last_price, ema10, ema20, sma50, sma200, atr14, ... }] }
        if (futuData.quotes && Array.isArray(futuData.quotes) && futuData.quotes.length > 0) {
          const stockQuote = futuData.quotes[0]
          quote = {
            symbol: stockQuote.code || futuCode,
            name: stockQuote.name || symbol,
            lastPrice: stockQuote.last_price || 0,
            open: stockQuote.open_price || 0,
            high: stockQuote.high_price || 0,
            low: stockQuote.low_price || 0,
            volume: stockQuote.volume || 0,
            turnover: 0,
            change: stockQuote.change || 0,
            changePercent: stockQuote.change_percent || 0,
            high52w: 0,
            low52w: 0,
            ema10: stockQuote.ema10,
            ema20: stockQuote.ema20,
            sma50: stockQuote.sma50,
            sma200: stockQuote.sma200,
            atr14: stockQuote.atr14,
          }
        } else {
          throw new Error(`No quote data returned for ${futuCode}`)
        }
      } catch (fetchErr) {
        console.error(`[Quote API] Fetch error:`, fetchErr)
        throw fetchErr
      }
    } else {
      // Yahoo Finance
      quote = await getYahooQuoteWithMA(symbol)
      quote.atr14 = null  // Yahoo 暫時未有 ATR
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
      atr14: quote.atr14,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`[${source.toUpperCase()} API] quote error:`, msg)
    return NextResponse.json({ error: `無法獲取報價: ${msg}` }, { status: 502 })
  }
}