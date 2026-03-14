import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  const url = new URL(request.url)
  const symbol = url.pathname.split('/').pop() || url.searchParams.get('symbol')
  const range = url.searchParams.get('range') || '5d'

  if (!symbol) {
    return NextResponse.json({ error: 'No symbol provided' }, { status: 400 })
  }

  try {
    let ticker = symbol.toUpperCase().trim()
    if (!ticker.includes('.') && !ticker.startsWith('^')) {
      if (/^\d+$/.test(ticker)) {
        ticker = `${ticker}.HK`
      }
    }

    const yahooUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?interval=1d&range=${range}`
    const response = await fetch(yahooUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    })

    if (!response.ok) {
      return NextResponse.json({ error: `Yahoo error: ${response.status}` }, { status: response.status })
    }

    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 })
  }
}