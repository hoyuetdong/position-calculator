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

export interface AccountBalance {
  currency: string
  cash: number
  market_value: number
  total_assets: number
  buying_power: number
  withdrawable: number
}

export interface BalanceResponse {
  success: boolean
  account_balance: AccountBalance | null
  message: string
  timestamp: string
}

export async function fetchPositions(): Promise<PositionsResponse> {
  const response = await fetch(`/api/positions?t=${Date.now()}`, {
    cache: 'no-store',
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.details || 'Failed to fetch positions')
  }
  return response.json()
}

export async function fetchAccountBalance(): Promise<BalanceResponse> {
  const response = await fetch('/api/balance')
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.details || 'Failed to fetch account balance')
  }
  return response.json()
}
