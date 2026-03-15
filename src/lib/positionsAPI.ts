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

export interface OrderRequest {
  symbol: string
  price: number
  quantity: number
  order_type?: string
  side?: string
  stop_loss_price?: number
  remark?: string
}

export interface OrderResponse {
  success: boolean
  order_id: string | null
  stop_order_id?: string | null
  status?: string
  message: string
  timestamp: string
}

export interface PendingStopOrder {
  entry_order_id: string
  symbol: string
  quantity: number
  stop_loss_price: number
  status: string
}

export interface PendingStopOrdersResponse {
  success: boolean
  pending_orders: PendingStopOrder[]
  timestamp: string
}

export interface EnvResponse {
  success: boolean
  trade_env: string
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

export async function placeOrder(order: OrderRequest): Promise<OrderResponse> {
  const response = await fetch('/api/order', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(order),
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to place order')
  }
  return response.json()
}

export async function fetchPendingStopOrders(): Promise<PendingStopOrdersResponse> {
  const response = await fetch('/api/pending-stops')
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.details || 'Failed to fetch pending stop orders')
  }
  return response.json()
}

export async function fetchEnv(): Promise<EnvResponse> {
  const response = await fetch('/api/trade-env')
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.details || 'Failed to fetch env')
  }
  return response.json()
}

export async function setEnv(tradeEnv: string): Promise<EnvResponse> {
  const response = await fetch('/api/trade-env', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ trade_env: tradeEnv }),
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to set env')
  }
  return response.json()
}
