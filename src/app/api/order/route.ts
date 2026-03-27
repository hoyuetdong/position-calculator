import { NextRequest, NextResponse } from 'next/server'
import { fetchWithTimeout } from '@/lib/fetchWithTimeout'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()

    // Forward to Python backend
    const backendUrl = process.env.PYTHON_API_URL || 'http://127.0.0.1:8000'
    const apiKey = process.env.API_SECRET || ''
    const response = await fetchWithTimeout(`${backendUrl}/api/order`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(apiKey && { 'X-API-Key': apiKey }),
      },
      body: JSON.stringify(body),
    })
    
    if (!response.ok) {
      const error = await response.json()
      return NextResponse.json(
        { success: false, message: error.detail || 'Failed to place order' },
        { status: response.status }
      )
    }
    
    const result = await response.json()
    return NextResponse.json(result)
  } catch (error) {
    console.error('Order API error:', error)
    const errorMessage = error instanceof Error ? error.message : String(error)
    const statusCode = errorMessage.includes('timeout') ? 504 : 500
    return NextResponse.json(
      { success: false, message: errorMessage },
      { status: statusCode }
    )
  }
}
