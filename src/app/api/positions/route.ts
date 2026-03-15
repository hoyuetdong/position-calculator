/**
 * API route to fetch positions from Python Futu backend
 */
import { NextResponse } from 'next/server'

const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:8000'

export async function GET() {
  try {
    const response = await fetch(`${PYTHON_API_URL}/positions`, {
      headers: {
        'Content-Type': 'application/json',
      },
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
    return NextResponse.json(
      { error: 'Failed to connect to Python backend', details: String(error) },
      { status: 500 }
    )
  }
}
