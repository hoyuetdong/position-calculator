import { NextRequest, NextResponse } from 'next/server'
import { fetchWithTimeout } from '@/lib/fetchWithTimeout'
export const dynamic = 'force-dynamic'
async function proxy(request: NextRequest, action: string, method: 'GET' | 'POST') {
  if (process.env.APP_PASSWORD && request.cookies.get('auth_password')?.value !== process.env.APP_PASSWORD)
    return NextResponse.json({ detail: '請先登入' }, { status: 401 })
  const origin = request.headers.get('origin')
  if (method === 'POST' && origin && new URL(origin).host !== request.headers.get('host'))
    return NextResponse.json({ detail: '來源不符' }, { status: 403 })
  if (!(method === 'GET' ? ['jobs'] : ['preview', 'confirm', 'cancel']).includes(action))
    return NextResponse.json({ detail: '不支援的操作' }, { status: 404 })
  try {
    const response = await fetchWithTimeout(`${process.env.PYTHON_API_URL || 'http://127.0.0.1:8000'}/api/zero-cost/${action}`, {
      method, cache: 'no-store', timeout: 30000,
      headers: { 'Content-Type': 'application/json', 'X-API-Key': process.env.API_SECRET || '' },
      ...(method === 'POST' ? { body: JSON.stringify(await request.json()) } : {}),
    })
    return NextResponse.json(await response.json(), { status: response.status, headers: { 'Cache-Control': 'no-store' } })
  } catch {
    return NextResponse.json({ detail: '未能確認結果，請查看處理紀錄；重試確認會使用同一筆請求。' }, { status: 503 })
  }
}
export function GET(request: NextRequest, { params }: { params: { action: string } }) { return proxy(request, params.action, 'GET') }
export function POST(request: NextRequest, { params }: { params: { action: string } }) { return proxy(request, params.action, 'POST') }
