/**
 * API route to fetch positions from Python Futu backend
 */
import { NextResponse } from 'next/server'
import { fetchWithTimeout } from '@/lib/fetchWithTimeout'

const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:8000'

// Disable caching - always fetch fresh data
export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const response = await fetchWithTimeout(`${PYTHON_API_URL}/api/positions`, {
      headers: {
        'Content-Type': 'application/json',
      },
      cache: 'no-store',
    })

    if (!response.ok) {
      const error = await response.text()
      return NextResponse.json(
        { error: 'Failed to fetch positions', details: error },
        { status: response.status }
      )
    }

    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('[API /positions] Error:', error)
    const errorMessage = error instanceof Error ? error.message : String(error)
    const statusCode = errorMessage.includes('timeout') ? 504 : 500
    return NextResponse.json(
      { error: 'Failed to connect to Python backend', details: errorMessage },
      { status: statusCode }
    )
  }
}
