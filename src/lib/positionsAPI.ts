/**
 * Client library for fetching positions from Python backend
 */

export interface Position {
  symbol: string
  name: string
  quantity: number
  cost_price: number | null
  current_price: number | null
  asset_type: string
}

export interface PositionsResponse {
  success: boolean
  positions: Position[]
  message: string
  timestamp: string
}

export async function fetchPositions(): Promise<PositionsResponse> {
  const response = await fetch('/api/positions')
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.details || 'Failed to fetch positions')
  }
  return response.json()
}
