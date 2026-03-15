import { NextRequest, NextResponse } from 'next/server'

export async function GET() {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8000'
    const response = await fetch(`${backendUrl}/pending-stops`)
    
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
    return NextResponse.json(
      { success: false, message: 'Internal server error' },
      { status: 500 }
    )
  }
}
