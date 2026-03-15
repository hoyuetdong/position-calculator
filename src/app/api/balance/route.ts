import { NextResponse } from 'next/server'

export async function GET() {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
    const response = await fetch(`${backendUrl}/balance`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
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
  } catch (error: any) {
    console.error('Balance API error:', error)
    return NextResponse.json(
      { success: false, account_balance: null, message: error.message || 'Internal server error', timestamp: new Date().toISOString() },
      { status: 500 }
    )
  }
}
