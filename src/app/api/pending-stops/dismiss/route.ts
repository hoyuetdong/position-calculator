import { NextRequest, NextResponse } from 'next/server'
import { fetchWithTimeout } from '@/lib/fetchWithTimeout'
export const dynamic = 'force-dynamic'

export async function POST(request: NextRequest) {
  const password = process.env.APP_PASSWORD
  if (password && request.cookies.get('auth_password')?.value !== password) {
    return NextResponse.json({ message: '請先登入' }, { status: 401 })
  }
  const origin = request.headers.get('origin')
  if (origin && new URL(origin).host !== request.headers.get('host')) {
    return NextResponse.json({ message: '來源不符' }, { status: 403 })
  }
  try {
    const body = await request.json()
    const response = await fetchWithTimeout(`${process.env.PYTHON_API_URL || 'http://127.0.0.1:8000'}/api/pending-stops/dismiss`, {
      method: 'POST', cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': process.env.API_SECRET || '' },
      body: JSON.stringify({ entry_order_id: body.entry_order_id, confirmed_cancelled_unfilled: body.confirmed_cancelled_unfilled }),
    })
    return NextResponse.json(await response.json(), { status: response.status, headers: { 'Cache-Control': 'no-store' } })
  } catch {
    return NextResponse.json({ message: '未能確認重試請求，請更新狀態' }, { status: 502 })
  }
}
