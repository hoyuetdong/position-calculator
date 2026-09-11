import { NextRequest, NextResponse } from 'next/server'
import { fetchWithTimeout } from '@/lib/fetchWithTimeout'
export const dynamic = 'force-dynamic'
export async function GET(request: NextRequest) {
  if (process.env.APP_PASSWORD && request.cookies.get('auth_password')?.value !== process.env.APP_PASSWORD) {
    return NextResponse.json({ detail: '請先登入' }, { status: 401 })
  }
  try {
    const query = new URLSearchParams()
    query.set('symbol', request.nextUrl.searchParams.get('symbol') || '')
    query.set('offset', request.nextUrl.searchParams.get('offset') || '0')
    const response = await fetchWithTimeout(`${process.env.PYTHON_API_URL || 'http://127.0.0.1:8000'}/api/protection?${query}`, {
      cache: 'no-store', headers: { 'X-API-Key': process.env.API_SECRET || '' },
    })
    return NextResponse.json(await response.json(), { status: response.status, headers: { 'Cache-Control': 'no-store' } })
  } catch {
    return NextResponse.json({ detail: '暫時無法讀取，請稍後重試' }, { status: 503 })
  }
}
