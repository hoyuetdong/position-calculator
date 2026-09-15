import { NextResponse } from 'next/server'
export const dynamic = 'force-dynamic'
export async function GET(_: Request, {params}: {params: {symbol: string}}) {
  try {
    const response = await fetch(`${process.env.PYTHON_API_URL || 'http://backend:8000'}/api/trading-quote/${encodeURIComponent(params.symbol)}`, {
      cache:'no-store', headers:{'X-API-Key':process.env.API_SECRET || ''}, signal:AbortSignal.timeout(15000),
    })
    return NextResponse.json(await response.json(), {status:response.status})
  } catch { return NextResponse.json({detail:'未能連接富途報價服務，請稍後再試'}, {status:502}) }
}
