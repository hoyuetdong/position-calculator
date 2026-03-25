import { NextRequest, NextResponse } from 'next/server'
import { fetchWithTimeout } from '@/lib/fetchWithTimeout'

export async function GET() {
  try {
    const backendUrl = process.env.PYTHON_API_URL || 'http://127.0.0.1:8000'
    const response = await fetchWithTimeout(`${backendUrl}/api/pending-stops`)

    if (!response.ok) {
      const error = await response.json()
      return NextResponse.json(
        { success: false, message: error.detail || 'Failed to fetch pending stops' },
        { status: response.status }
      )
    }

    const result = await response.json()
    return NextResponse.json(result)
  } catch (error) {
    console.error('Pending stops API error:', error)
    const errorMessage = error instanceof Error ? error.message : String(error)
    const statusCode = errorMessage.includes('timeout') ? 504 : 500
    return NextResponse.json(
      { success: false, message: errorMessage },
      { status: statusCode }
    )
  }
}
