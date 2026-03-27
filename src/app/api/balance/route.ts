import { NextResponse } from 'next/server'
import { fetchWithTimeout } from '@/lib/fetchWithTimeout'

export async function GET() {
  try {
    const backendUrl = process.env.PYTHON_API_URL || 'http://localhost:8000'
    const apiKey = process.env.API_SECRET || ''
    const response = await fetchWithTimeout(`${backendUrl}/api/balance`, {
      headers: apiKey ? { 'X-API-Key': apiKey } : {},
    })

    if (!response.ok) {
      const error = await response.json()
      return NextResponse.json(
        { success: false, account_balance: null, message: error.detail || 'Failed to fetch balance', timestamp: new Date().toISOString() },
        { status: response.status }
      )
    }

    const data = await response.json()
    return NextResponse.json(data)
  } catch (error: unknown) {
    console.error('Balance API error:', error)
    const errorMessage = error instanceof Error ? error.message : String(error)
    const statusCode = errorMessage.includes('timeout') ? 504 : 500
    return NextResponse.json(
      { success: false, account_balance: null, message: errorMessage, timestamp: new Date().toISOString() },
      { status: statusCode }
    )
  }
}
