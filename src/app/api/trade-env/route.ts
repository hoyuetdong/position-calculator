import { NextRequest, NextResponse } from 'next/server'

export async function GET() {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8000'
    const response = await fetch(`${backendUrl}/env`)
    
    if (!response.ok) {
      const error = await response.json()
      return NextResponse.json(
        { success: false, message: error.detail || 'Failed to fetch env' },
        { status: response.status }
      )
    }
    
    const result = await response.json()
    return NextResponse.json(result)
  } catch (error) {
    console.error('Env API error:', error)
    return NextResponse.json(
      { success: false, message: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    
    const backendUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8000'
    const response = await fetch(`${backendUrl}/env`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })
    
    if (!response.ok) {
      const error = await response.json()
      return NextResponse.json(
        { success: false, message: error.detail || 'Failed to set env' },
        { status: response.status }
      )
    }
    
    const result = await response.json()
    return NextResponse.json(result)
  } catch (error) {
    console.error('Env API error:', error)
    return NextResponse.json(
      { success: false, message: 'Internal server error' },
      { status: 500 }
    )
  }
}
