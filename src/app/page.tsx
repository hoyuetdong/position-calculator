'use client'

import { useState, useEffect, useCallback } from 'react'
import { 
  Calculator, 
  TrendingUp, 
  TrendingDown, 
  AlertTriangle, 
  Trash2,
  Settings,
  Info,
  RefreshCw,
  Database,
  Wallet
} from 'lucide-react'
import { 
  getQuote, 
  getHistoricalKLines,
  type QuoteData,
  type DataSource
} from '@/lib/yahooAPI'
import { fetchPositions, fetchAccountBalance, placeOrder, fetchEnv, setEnv, type BrokerPosition } from '@/lib/positionsAPI'
import CandlestickChart from '@/components/CandlestickChart'
import DataSourceControl from '@/components/DataSourceControl'

interface Position {
  id: string
  ticker: string
  direction: 'LONG' | 'SHORT'  // 新增：持倉方向
  buyPrice: number  // Long: 買入價, Short: 賣出價 (做空價)
  stopLoss: number  // Long: 止蝕喺下面, Short: 止蝕喺上面
  shares: number
  positionValue: number
  portfolioPercent: number
  riskPercent: number
  date: string
}

interface Settings {
  accountSize: number
  defaultRiskPercent: number
  atrMultiplier: number
  atrPeriod: number
}

// Data source switcher component
// R-multiples visualization
function RMultiplierBar({ 
  direction,
  currentPrice, 
  entryPrice, 
  stopLoss
}: { 
  direction: 'LONG' | 'SHORT'
  currentPrice: number
  entryPrice: number
  stopLoss: number
}) {
  // 檢查數值是否有效
  if (!currentPrice || !entryPrice || !stopLoss || 
      isNaN(currentPrice) || isNaN(entryPrice) || isNaN(stopLoss) ||
      entryPrice <= 0 || stopLoss <= 0) {
    return null
  }
  
  const stopDistance = direction === 'LONG' 
    ? entryPrice - stopLoss  // Long: 止蝕喺下面
    : stopLoss - entryPrice   // Short: 止蝕喺上面
  
  if (stopDistance <= 0) return null // 止蝕距離應該係正數
  
  // 根據方向計算目標價
  const r1 = direction === 'LONG' 
    ? entryPrice + stopDistance 
    : entryPrice - stopDistance
  const r2 = direction === 'LONG' 
    ? entryPrice + (stopDistance * 2) 
    : entryPrice - (stopDistance * 2)
  const r3 = direction === 'LONG' 
    ? entryPrice + (stopDistance * 3) 
    : entryPrice - (stopDistance * 3)
  
  // 計算顯示範圍
  let min, max
  if (direction === 'LONG') {
    min = stopLoss * 0.95
    max = r3 * 1.05
  } else {
    min = r3 * 0.95
    max = stopLoss * 1.05
  }
  const range = max - min
  
  const getPosition = (price: number) => ((price - min) / range) * 100
  
  return (
    <div className="w-full">
      <div className="relative h-8 bg-gradient-to-r from-loss/30 via-background to-profit/30 rounded-lg overflow-visible">
        {/* Stop Loss - Red */}
        <div className="absolute top-0 bottom-0 w-0.5 bg-loss group cursor-pointer" style={{ left: `${getPosition(stopLoss)}%` }}>
          <div className="absolute -top-6 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-loss text-white text-xs px-1 py-0.5 rounded whitespace-nowrap z-20">
            SL: ${stopLoss.toFixed(2)}
          </div>
        </div>
        
        {/* Entry Price - Cyan */}
        <div className="absolute top-0 bottom-0 w-0.5 bg-cyan-400 group cursor-pointer" style={{ left: `${getPosition(entryPrice)}%` }}>
          <div className="absolute -top-6 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-cyan-400 text-black text-xs px-1 py-0.5 rounded whitespace-nowrap z-20">
            {direction === 'LONG' ? '買入' : '賣出'}: ${entryPrice.toFixed(2)}
          </div>
        </div>
        
        {/* R1 */}
        <div className="absolute top-0 bottom-0 w-0.5 bg-profit/50 group cursor-pointer" style={{ left: `${getPosition(r1)}%` }}>
          <div className="absolute -top-6 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-profit/50 text-black text-xs px-1 py-0.5 rounded whitespace-nowrap z-20">
            R1: ${r1.toFixed(2)}
          </div>
        </div>
        
        {/* R2 */}
        <div className="absolute top-0 bottom-0 w-0.5 bg-profit/70 group cursor-pointer" style={{ left: `${getPosition(r2)}%` }}>
          <div className="absolute -top-6 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-profit/70 text-black text-xs px-1 py-0.5 rounded whitespace-nowrap z-20">
            R2: ${r2.toFixed(2)}
          </div>
        </div>
        
        {/* R3 */}
        <div className="absolute top-0 bottom-0 w-0.5 bg-profit group cursor-pointer" style={{ left: `${getPosition(r3)}%` }}>
          <div className="absolute -top-6 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-profit text-black text-xs px-1 py-0.5 rounded whitespace-nowrap z-20">
            R3: ${r3.toFixed(2)}
          </div>
        </div>
        
        {/* Current Price - Yellow */}
        <div className="absolute top-0 bottom-0 w-1 bg-yellow-400 z-10 group cursor-pointer" style={{ left: `${getPosition(currentPrice)}%` }}>
          <div className="absolute -top-6 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-yellow-400 text-black text-xs px-1 py-0.5 rounded whitespace-nowrap z-20">
            現價: ${currentPrice.toFixed(2)}
          </div>
        </div>
      </div>
      
      <div className="flex justify-between text-xs text-muted-foreground mt-1" style={{ position: 'relative', height: '20px' }}>
        <span className="text-loss absolute transform -translate-x-1/2" style={{ left: `${getPosition(stopLoss)}%` }}>SL: ${stopLoss.toFixed(2)}</span>
        <span className="text-cyan-400 absolute transform -translate-x-1/2" style={{ left: `${getPosition(entryPrice)}%` }}>{direction === 'LONG' ? '買入' : '賣出'}: ${entryPrice.toFixed(2)}</span>
        <span className="text-profit/50 absolute transform -translate-x-1/2" style={{ left: `${getPosition(r1)}%` }}>R1: ${r1.toFixed(2)}</span>
        <span className="text-profit/70 absolute transform -translate-x-1/2" style={{ left: `${getPosition(r2)}%` }}>R2: ${r2.toFixed(2)}</span>
        <span className="text-profit absolute transform -translate-x-1/2" style={{ left: `${getPosition(r3)}%` }}>R3: ${r3.toFixed(2)}</span>
      </div>
      {/* 現價放喺下面一行，但跟條線既位置 */}
      <div className="flex justify-between text-xs text-muted-foreground mt-1" style={{ position: 'relative', height: '20px' }}>
        <span className="text-yellow-400 absolute transform -translate-x-1/2 font-bold" style={{ left: `${getPosition(currentPrice)}%` }}>
          現價: ${currentPrice.toFixed(2)}
        </span>
      </div>
    </div>
  )
}

// Zero-Cost Position Calculator Component
function ZeroCostCalculator({
  brokerPositions,
  syncError,
  syncing,
  onSync,
  onSelectPosition,
  profitPercent,
  setProfitPercent,
  shares,
  setShares,
  accountSize
}: { 
  brokerPositions: BrokerPosition[]
  syncError: string | null
  syncing: boolean
  onSync: () => void
  onSelectPosition?: (profitPercent: number, shares: number) => void
  profitPercent: number
  setProfitPercent: (value: number) => void
  shares: string
  setShares: (value: string) => void
  accountSize: number
}) {
  // Filter for US stocks only (not HK stocks)
  const usPositions = brokerPositions.filter(pos => !pos.symbol.endsWith('.HK'))

  // 計算總持倉市值
  const totalPositionValue = usPositions.reduce((sum, p) => {
    return sum + (p.current_price ? p.current_price * p.quantity : 0)
  }, 0)

  // 計算持倉佔比
  const portfolioPercent = accountSize > 0 ? (totalPositionValue / accountSize) * 100 : 0

  // 計算邏輯
  // Sell Ratio = 1 / (1 + P) where P is profit percentage as decimal
  // Keep Ratio = 1 - Sell Ratio
  const profitDecimal = profitPercent / 100
  const sellRatio = profitDecimal > 0 ? 1 / (1 + profitDecimal) : 1
  const keepRatio = 1 - sellRatio

  // 如果有輸入持股數
  const sharesNum = parseInt(shares) || 0
  const sharesToSell = sharesNum > 0 ? Math.round(sharesNum * sellRatio) : 0
  const zeroCostShares = sharesNum > 0 ? sharesNum - sharesToSell : 0

  // 格式化數字
  const formatNumber = (num: number) => num.toLocaleString()

  return (
    <div className="max-w-6xl mx-auto">
      {/* Main Content - Two independent Cards side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
        
        {/* Left Column - Calculator Card */}
        <div className="bg-card border border-border rounded-xl p-6 md:p-8 flex flex-col">
          <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
            <Wallet className="w-7 h-7 text-primary" />
            零成本持倉計算器
          </h2>

          {/* 輸入區 */}
          <div className="space-y-6 mb-8">
            {/* 盈利百分比輸入 */}
            <div>
              <label className="text-sm text-muted-foreground mb-2 block">盈利百分比 (Profit %)</label>
              <div className="flex items-center gap-4">
                <input
                  type="number"
                  value={profitPercent}
                  onChange={(e) => setProfitPercent(Math.min(500, Math.max(0, parseFloat(e.target.value) || 0)))}
                  className="w-24 px-4 py-3 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-xl font-mono text-center"
                  min="0"
                  max="500"
                />
                <span className="text-xl text-muted-foreground">%</span>
              </div>
              {/* Slider */}
              <input
                type="range"
                min="0"
                max="500"
                value={profitPercent}
                onChange={(e) => setProfitPercent(parseInt(e.target.value))}
                className="w-full mt-4 h-2 bg-secondary rounded-lg appearance-none cursor-pointer accent-primary"
              />
            </div>

            {/* 持股數量輸入 */}
            <div>
              <label className="text-sm text-muted-foreground mb-2 block">持股數量 (選填)</label>
              <input
                type="number"
                value={shares}
                onChange={(e) => setShares(e.target.value)}
                placeholder="例如: 1000"
                className="w-full px-4 py-3 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-lg font-mono"
                min="0"
              />
            </div>
          </div>

          {/* 輸出區 - 大字展示 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            {/* Card 1: 賣出比例 */}
            <div className="bg-card border-2 border-warning/50 rounded-xl p-6 text-center">
              <p className="text-muted-foreground mb-2">需要賣出比例</p>
              <p className="text-5xl font-bold text-warning glow-warning">{(sellRatio * 100).toFixed(2)}%</p>
              <p className="text-sm text-muted-foreground mt-2">收回本金</p>
            </div>

            {/* Card 2: 保留比例 */}
            <div className="bg-card border-2 border-profit/50 rounded-xl p-6 text-center">
              <p className="text-muted-foreground mb-2">零成本持股比例</p>
              <p className="text-5xl font-bold text-profit glow-green">{(keepRatio * 100).toFixed(2)}%</p>
              <p className="text-sm text-muted-foreground mt-2">純利潤倉位</p>
            </div>
          </div>

          {/* 進度條 */}
          <div className="mb-6">
            <div className="flex justify-between text-sm mb-2">
              <span className="text-warning font-medium">賣出 {(sellRatio * 100).toFixed(1)}%</span>
              <span className="text-profit font-medium">保留 {(keepRatio * 100).toFixed(1)}%</span>
            </div>
            <div className="h-4 bg-secondary rounded-full overflow-hidden flex">
              <div 
                className="h-full bg-warning transition-all duration-300"
                style={{ width: `${sellRatio * 100}%` }}
              />
              <div 
                className="h-full bg-profit transition-all duration-300"
                style={{ width: `${keepRatio * 100}%` }}
              />
            </div>
          </div>

          {/* 動態文字提示 */}
          {sharesNum > 0 && (
            <div className="bg-secondary/50 rounded-lg p-4 text-center">
              <p className="text-lg">
                假設你持有 <span className="text-primary font-bold">{formatNumber(sharesNum)}</span> 股，
                你需要賣出約 <span className="text-warning font-bold">{formatNumber(sharesToSell)}</span> 股來收回全部本金，
                剩下的 <span className="text-profit font-bold">{formatNumber(zeroCostShares)}</span> 股就係你嘅零成本持股。
              </p>
            </div>
          )}

          {/* 計算公式說明 */}
          <div className="mt-6 pt-6 border-t border-border">
            <p className="text-xs text-muted-foreground text-center">
              公式：賣出比例 = 1 ÷ (1 + 盈利%) · 保留比例 = 1 - 賣出比例
            </p>
          </div>
        </div>

        {/* Right Column - US Positions Card */}
        <div className="bg-card border border-border rounded-xl p-6 flex flex-col h-full">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Database className="w-5 h-5 text-primary" />
              富途美股持倉
            </h3>
          </div>
          
          {usPositions.length > 0 ? (
            <div className="flex-1 overflow-y-auto pr-2 space-y-3">
              {/* 按盈亏百分比由高至低排序 */}
              {usPositions
                .map((pos, idx) => {
                  // Calculate profit/loss if we have both cost and current price
                  const hasPL = pos.cost_price && pos.current_price
                  const plPercent = hasPL 
                    ? ((pos.current_price! - pos.cost_price!) / pos.cost_price! * 100)
                    : -999 // 没有价格数据排最后
                  const isProfit = plPercent >= 0
                  
                  // 计算零成本需卖出股数 (只对盈利股票计算)
                  const sharesToSell = isProfit && hasPL 
                    ? Math.round(pos.quantity * (1 / (1 + plPercent / 100)))
                    : 0
                  const zeroCostShares = isProfit && hasPL 
                    ? pos.quantity - sharesToSell
                    : 0
                  
                  return { pos, idx, hasPL, plPercent, isProfit, sharesToSell, zeroCostShares }
                })
                .sort((a, b) => b.plPercent - a.plPercent)
                .map(({ pos, idx, hasPL, plPercent, isProfit, sharesToSell, zeroCostShares }) => {
                  return (
                    <div 
                      key={idx} 
                      className="flex items-center justify-between px-4 py-3 mb-2 bg-secondary/30 hover:bg-secondary/50 rounded-lg cursor-pointer transition-colors"
                      onClick={() => {
                        // 点击填充到左边计算器
                        if (hasPL && plPercent > 0 && onSelectPosition) {
                          onSelectPosition(Math.round(plPercent * 10) / 10, pos.quantity)
                        }
                      }}
                    >
                      {/* 左侧：股票代号 + 持股数量 */}
                      <div className="flex items-center gap-3">
                        <span className="font-bold text-white text-base">{pos.symbol}</span>
                        <span className="text-sm text-gray-500">{pos.quantity} 股</span>
                      </div>
                      
                      {/* 右侧：零成本信息 + 盈亏 */}
                      {hasPL && (
                        <div className="flex items-center gap-4">
                          {/* 盈利且有正数才显示零成本信息 */}
                          {isProfit && plPercent > 0 && (
                            <span className="text-xs text-warning">
                              零成本需賣出: <span className="font-bold">{sharesToSell.toLocaleString()}</span> 股
                              <span className="text-muted-foreground ml-1">(剩: <span className="text-profit font-bold">{zeroCostShares.toLocaleString()}</span>)</span>
                            </span>
                          )}
                          {/* 亏损股票只显示红色盈亏 */}
                          <span className={`text-base font-bold ${isProfit ? 'text-profit' : 'text-loss'}`}>
                            {isProfit ? '+' : ''}{plPercent.toFixed(1)}%
                          </span>
                        </div>
                      )}
                    </div>
                  )
                })}
              
              {/* Total summary - 持倉佔比 */}
              <div className="mt-4 pt-4 border-t border-border">
                <div className="flex justify-between items-center text-sm">
                  <span className="text-muted-foreground">持倉佔比:</span>
                  <span className="font-mono font-bold">
                    {portfolioPercent.toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              {syncError ? (
                <>
                  <p className="text-loss">同步失敗</p>
                  <p className="text-xs mt-1 text-loss/70">{syncError}</p>
                  <button
                    type="button"
                    onClick={() => { 
                      console.log('Sync button clicked, calling onSync'); 
                      onSync(); 
                    }}
                    disabled={syncing}
                    className="mt-3 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 text-sm cursor-pointer"
                  >
                    {syncing ? '同步緊...' : '同步券商持倉'}
                  </button>
                </>
              ) : (
                <>
                  <Database className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>暫時未有美股持倉</p>
                  <button
                    type="button"
                    onClick={() => { console.log('Sync button clicked'); onSync(); }}
                    disabled={syncing}
                    className="mt-3 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 text-sm cursor-pointer"
                  >
                    {syncing ? '同步緊...' : '同步券商持倉'}
                  </button>
                </>
              )}
            </div>
          )}
        </div>
        
      </div>
    </div>
  )
}

export default function Home() {
  // Force dark mode on client to prevent flash
  useEffect(() => {
    document.documentElement.classList.add('dark')
  }, [])

  const [settings, setSettings] = useState<Settings>({
    accountSize: 100000,
    defaultRiskPercent: 0.3,
    atrMultiplier: 1.5,
    atrPeriod: 14
  })
  // Hydration fix: defer all client-side logic
  const [hydrated, setHydrated] = useState(false)
  
  // Data source 切換
  const [dataSource, setDataSource] = useState<DataSource>('yahoo')
  const [futuConnected, setFutuConnected] = useState(false)
  
  // 交易環境狀態
  const [tradeEnv, setTradeEnv] = useState<'SIMULATE' | 'REAL'>('SIMULATE')
  const [showEnvConfirm, setShowEnvConfirm] = useState(false)
  const [pendingEnvSwitch, setPendingEnvSwitch] = useState<'SIMULATE' | 'REAL' | null>(null)
  
  // 合併 load + save 係同一個 effect，避免 race condition
  useEffect(() => {
    // Client only: load from localStorage
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('vcp-settings')
      if (saved) {
        try {
          setSettings(JSON.parse(saved))
        } catch (e) {}
      }
      setHydrated(true)
    }
  }, [])
  
  // Save when settings change (only after hydration)
  useEffect(() => {
    if (hydrated && typeof window !== 'undefined') {
      localStorage.setItem('vcp-settings', JSON.stringify(settings))
    }
  }, [settings, hydrated])
  
  const [ticker, setTicker] = useState('')
  const [direction, setDirection] = useState<'LONG' | 'SHORT'>('LONG')  // 持倉方向
  const [entryPrice, setEntryPrice] = useState('')  // 改名：entryPrice 通用於 LONG/SHORT
  const [stopLoss, setStopLoss] = useState('')
  const [timeInForce, setTimeInForce] = useState<'DAY' | 'GTC'>('GTC')
  const [orderType, setOrderType] = useState<'LIMIT' | 'MARKET' | 'STOP'>('LIMIT')  // 新增：訂單類型
  const [triggerPrice, setTriggerPrice] = useState('')  // 新增：Stop Entry 觸發價
  const [quoteData, setQuoteData] = useState<QuoteData | null>(null)
  const [atr, setAtr] = useState<number | null>(null)
  const [historicalData, setHistoricalData] = useState<{time: number; open: number; high: number; low: number; close: number}[]>([])
  const [loading, setLoading] = useState(false)
  // Yahoo 唔使連線，預設已連接
  const [connected, setConnected] = useState(true)
  const [positions, setPositions] = useState<Position[]>([])
  const [showSettings, setShowSettings] = useState(false)
  
  // Broker sync state
  const [brokerPositions, setBrokerPositions] = useState<BrokerPosition[]>([])
  const [syncing, setSyncing] = useState(false)
  const [lastSyncTime, setLastSyncTime] = useState<string | null>(null)
  const [syncError, setSyncError] = useState<string | null>(null)
  
  // Account balance state
  const [balanceLastUpdated, setBalanceLastUpdated] = useState<string | null>(null)
  const [syncingBalance, setSyncingBalance] = useState(false)
  
  // Order dialog state
  const [showOrderConfirm, setShowOrderConfirm] = useState(false)
  const [ordering, setOrdering] = useState(false)
  const [orderResult, setOrderResult] = useState<{success: boolean; message: string; orderId?: string} | null>(null)
  
  // Tab navigation state
  const [activeTab, setActiveTab] = useState<'position' | 'zerocost'>('position')
  
  // Zero-Cost Calculator state (controlled by parent)
  const [profitPercentLocal, setProfitPercentLocal] = useState<number>(35)
  const [sharesLocal, setSharesLocal] = useState<string>('')
  
  // Sync positions from broker
  const syncBrokerPositions = useCallback(async () => {
    console.log('[Sync] Starting broker sync...')
    setSyncing(true)
    setSyncError(null)
    try {
      const response = await fetchPositions()
      console.log('[Sync] Response:', response)
      if (response.success) {
        setBrokerPositions(response.positions)
        setLastSyncTime(response.timestamp)
      } else {
        console.error('Sync failed:', response.message)
        setSyncError(response.message)
      }
    } catch (error) {
      console.error('Failed to sync positions:', error)
      setSyncError(String(error))
    }
    setSyncing(false)
  }, [])
  
  // Auto-sync broker positions on page load
  useEffect(() => {
    if (hydrated && brokerPositions.length === 0 && !syncing) {
      syncBrokerPositions()
    }
  }, [hydrated, syncBrokerPositions])
  
  // Fetch trade environment on page load
  useEffect(() => {
    const fetchEnvStatus = async () => {
      try {
        const envData = await fetchEnv()
        setTradeEnv(envData.trade_env as 'SIMULATE' | 'REAL')
      } catch (error) {
        console.error('Failed to fetch env:', error)
      }
    }
    fetchEnvStatus()
  }, [])
  
  // Handle chart click - set entry price and auto-calculate stop loss
  const handleChartClick = useCallback((price: number) => {
    setEntryPrice(price.toFixed(2))
    // Auto calculate stop loss based on ATR and direction
    if (atr) {
      if (direction === 'LONG') {
        // Long: 止蝕喺下面
        const stopLossPrice = price - atr * settings.atrMultiplier
        setStopLoss(stopLossPrice.toFixed(2))
      } else {
        // Short: 止蝕喺上面
        const stopLossPrice = price + atr * settings.atrMultiplier
        setStopLoss(stopLossPrice.toFixed(2))
      }
    }
  }, [atr, settings.atrMultiplier, direction])
  
  // Initialize API connection
  useEffect(() => {
    const init = async () => {
      // Yahoo 唔使連線，永遠 connected
      setConnected(true)
      
      // 富途要試吓 connect
      if (dataSource === 'futu') {
        try {
          // 用港股00700測試連線（美股暫時未support）
          const response = await fetch('/api/quote/00700?source=futu')
          if (response.ok) {
            const data = await response.json()
            // 如果有error field 或者 price=0，就當fail
            if (data.error || data.lastPrice === 0) {
              setFutuConnected(false)
            } else {
              setFutuConnected(true)
            }
          } else {
            setFutuConnected(false)
          }
        } catch {
          setFutuConnected(false)
        }
      }
    }
    init()
  }, [dataSource])
  
  // Fetch quote when ticker changes
  useEffect(() => {
    const fetchData = async () => {
      if (ticker.length >= 1) {
        setLoading(true)
        
        // Reset entry price and stop loss when ticker changes
        setEntryPrice('')
        setStopLoss('')
        
        try {
          const quote = await getQuote(ticker, dataSource)
          // Yahoo 最多 2000 日，富途最多 365 日
          const maxDays = dataSource === 'futu' ? 365 : 2000
          const klines = await getHistoricalKLines(ticker, maxDays, dataSource)
          
          setQuoteData(quote)
          
          // Store historical data for chart
          const histData = klines.map((k: any) => ({
            time: k.time,
            open: parseFloat(k.open),
            high: parseFloat(k.high),
            low: parseFloat(k.low),
            close: parseFloat(k.close)
          }))
          setHistoricalData(histData)
          
          // Calculate ATR
          let calculatedAtr: number | null = null
          const atrPeriod = settings.atrPeriod || 14
          if (klines.length >= atrPeriod) {
            const atrData = klines.slice(-atrPeriod).map((k: any) => {
              const high = parseFloat(k.high)
              const low = parseFloat(k.low)
              const close = parseFloat(k.close)
              const tr = Math.max(high - low, Math.abs(high - close), Math.abs(low - close))
              return tr
            })
            calculatedAtr = atrData.reduce((a: number, b: number) => a + b, 0) / atrPeriod
          }
          setAtr(calculatedAtr)
          
          // Auto-fill entry price with current price
          if (quote.lastPrice) {
            setEntryPrice(quote.lastPrice.toFixed(2))
          }
        } catch (error) {
          console.error('Error fetching quote:', error)
          setQuoteData(null)
          setAtr(null)
        }
      }
      setLoading(false)
    }
    
    const timer = setTimeout(fetchData, 500)
    return () => clearTimeout(timer)
  }, [ticker, dataSource, settings.atrPeriod])

  // 當 ATR 週期改變時，重新計算 ATR（如果有歷史數據）
  useEffect(() => {
    if (historicalData.length > 0 && settings.atrPeriod) {
      const atrPeriod = settings.atrPeriod
      if (historicalData.length >= atrPeriod) {
        const lastKlines = historicalData.slice(-atrPeriod)
        const atrData = lastKlines.map((k) => {
          const tr = Math.max(k.high - k.low, Math.abs(k.high - k.close), Math.abs(k.low - k.close))
          return tr
        })
        const calculatedAtr = atrData.reduce((a, b) => a + b, 0) / atrPeriod
        setAtr(calculatedAtr)
      }
    }
  }, [settings.atrPeriod])
  
  // Calculations（避免 NaN：空字串當 0）
  const entryNum = parseFloat(entryPrice) || 0
  const stopNum = parseFloat(stopLoss) || 0
  const riskAmount = settings.accountSize * (settings.defaultRiskPercent / 100)
  
  // 根據方向計算止蝕距離
  let stopDistance = 0
  let shares = 0
  if (direction === 'LONG') {
    // Long: 止蝕喺 entry 下面
    stopDistance = entryNum - stopNum
    shares = stopDistance > 0 ? Math.floor(riskAmount / stopDistance) : 0
  } else {
    // Short: 止蝕喺 entry 上面
    stopDistance = stopNum - entryNum
    shares = stopDistance > 0 ? Math.floor(riskAmount / stopDistance) : 0
  }
  
  const positionValue = shares * entryNum
  const portfolioPercent = settings.accountSize > 0 ? (positionValue / settings.accountSize) * 100 : 0
  const stopLossPercent = entryNum > 0 ? (stopDistance / entryNum) * 100 : 0
  
  // Suggested stop loss from ATR - based on entry price if available, otherwise last price
  const basePrice = parseFloat(entryPrice) || quoteData?.lastPrice || 0
  const suggestedStopLoss = (atr && basePrice) 
    ? direction === 'LONG'
      ? basePrice - (atr * settings.atrMultiplier)  // Long: 止蝕喺下面
      : basePrice + (atr * settings.atrMultiplier)  // Short: 止蝕喺上面
    : null
  
  // Warnings
  const portfolioWarning = portfolioPercent > 20
  const stopLossWarning = stopLossPercent > 8
  
  const applySuggestedStopLoss = () => {
    if (suggestedStopLoss) {
      setStopLoss(suggestedStopLoss.toFixed(2))
    }
  }
  
  const savePosition = () => {
    if (shares > 0 && ticker && entryPrice && stopLoss) {
      const newPosition: Position = {
        id: Date.now().toString(),
        ticker: ticker.toUpperCase(),
        direction: direction,
        buyPrice: parseFloat(entryPrice),
        stopLoss: parseFloat(stopLoss),
        shares: shares,
        positionValue,
        portfolioPercent,
        riskPercent: settings.defaultRiskPercent,
        date: new Date().toLocaleDateString()
      }
      setPositions([newPosition, ...positions])
    }
  }
  
  const deletePosition = (id: string) => {
    setPositions(positions.filter(p => p.id !== id))
  }
  
  const reconnect = async () => {
    setLoading(true)
    try {
      setConnected(true)
    } catch {
      setConnected(false)
    }
    setLoading(false)
  }
  
  // Sync account balance from broker
  const syncAccountBalance = useCallback(async () => {
    setSyncingBalance(true)
    try {
      const response = await fetchAccountBalance()
      if (response.success && response.account_balance) {
        const balance = response.account_balance
        // Update settings with the balance
        setSettings(prev => {
          const newSettings = {
            ...prev,
            accountSize: balance.total_assets || balance.cash || prev.accountSize
          }
          // Save to localStorage
          if (typeof window !== 'undefined') {
            localStorage.setItem('vcp-settings', JSON.stringify(newSettings))
            // Also save balance update timestamp
            localStorage.setItem('vcp-balance-last-updated', new Date().toISOString())
          }
          return newSettings
        })
        setBalanceLastUpdated(response.timestamp)
      } else {
        console.error('Balance sync failed:', response.message)
      }
    } catch (error) {
      console.error('Failed to sync account balance:', error)
    }
    setSyncingBalance(false)
  }, [])
  
  // Place order function
  const handlePlaceOrder = useCallback(async () => {
    if (!ticker || !entryPrice || shares <= 0) return

    setOrdering(true)
    setOrderResult(null)

    try {
      // 自動判斷 order_type：根據 entryPrice 與現價比較
      const currentPrice = quoteData?.lastPrice || 0
      const entryNum = parseFloat(entryPrice)
      let effectiveOrderType: 'LIMIT' | 'MARKET' | 'STOP' = 'LIMIT'
      let triggerPriceToUse: number | undefined

      if (entryNum > 0 && currentPrice > 0) {
        if (direction === 'LONG') {
          // Long: entryPrice > 現價 = BUY STOP (突破買入)
          if (entryNum > currentPrice) {
            effectiveOrderType = 'STOP'
            triggerPriceToUse = entryNum
          }
        } else {
          // Short: entryPrice < 現價 = SELL STOP (突破賣出)
          if (entryNum < currentPrice) {
            effectiveOrderType = 'STOP'
            triggerPriceToUse = entryNum
          }
        }
      }

      // 突破單觸發後以市價成交
      const finalOrderType = effectiveOrderType === 'STOP' ? 'MARKET' : effectiveOrderType
      let finalPrice = parseFloat(entryPrice)

      const response = await placeOrder({
        symbol: ticker.toUpperCase(),
        price: finalPrice,
        quantity: shares,
        order_type: finalOrderType,
        side: direction === 'LONG' ? 'BUY' : 'SELL',
        stop_loss_price: stopLoss ? parseFloat(stopLoss) : undefined,
        time_in_force: timeInForce,
        trigger_price: triggerPriceToUse,
      })

      setOrderResult({
        success: response.success,
        message: response.message,
        orderId: response.order_id || undefined,
      })
      
      if (response.success) {
        // Refresh positions after successful order
        setTimeout(() => {
          syncBrokerPositions()
        }, 2000)
      }
    } catch (error) {
      setOrderResult({
        success: false,
        message: error instanceof Error ? error.message : '落單失敗',
      })
    }
    
    setOrdering(false)
  }, [ticker, entryPrice, shares, direction, stopLoss, timeInForce, syncBrokerPositions, quoteData, triggerPrice])
  
  // Handle environment switch
  const handleEnvSwitch = useCallback(async (newEnv: 'SIMULATE' | 'REAL') => {
    try {
      await setEnv(newEnv)
      setTradeEnv(newEnv)
      setShowEnvConfirm(false)
      setPendingEnvSwitch(null)
    } catch (error) {
      console.error('Failed to switch env:', error)
      alert('切換環境失敗，請重試')
    }
  }, [])
  
  // Check if balance needs update (once per day, after 4:30 PM EST = 9:30 PM UTC = 21:30 UTC)
  // Or if never updated before
  useEffect(() => {
    if (!hydrated) return
    
    const lastUpdated = localStorage.getItem('vcp-balance-last-updated')
    const now = new Date()
    
    // Check if we need to update: 
    // 1. Never updated
    // 2. Last update was yesterday or earlier
    if (!lastUpdated) {
      syncAccountBalance()
      return
    }
    
    const lastDate = new Date(lastUpdated)
    const isDifferentDay = lastDate.toDateString() !== now.toDateString()
    
    // Also check if market is closed (after 9:30 PM UTC = 4:30 PM EST)
    const marketClosedHour = 21 // 9:30 PM UTC
    const isMarketClosed = now.getUTCHours() >= marketClosedHour
    
    if (isDifferentDay && isMarketClosed) {
      // Today's market is closed, fetch new balance
      syncAccountBalance()
    }
  }, [hydrated, syncAccountBalance])
  
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          {/* Tab Navigation */}
          <div className="flex items-center gap-1 bg-secondary rounded-lg p-1">
            <button
              type="button"
              onClick={() => setActiveTab('position')}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer flex items-center gap-2 ${
                activeTab === 'position' 
                  ? 'bg-primary text-primary-foreground' 
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Calculator className="w-4 h-4" />
              Position Calculator
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('zerocost')}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer flex items-center gap-2 ${
                activeTab === 'zerocost' 
                  ? 'bg-primary text-primary-foreground' 
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Wallet className="w-4 h-4" />
              Zero-Cost Calculator
            </button>
          </div>
          
          {/* Right side controls */}
          <div className="flex items-center gap-3">
            {/* Data Source Control - 統一控制列 */}
            <DataSourceControl
              dataSource={dataSource}
              futuConnected={futuConnected}
              onDataSourceChange={(source) => {
                if (source === 'yahoo') {
                  setDataSource('yahoo')
                  setConnected(true)
                } else {
                  setDataSource('futu')
                }
              }}
              onReconnect={reconnect}
            />
            
            {/* Connection Status / Trade Environment Toggle */}
            {connected && (
              <div className="flex items-center gap-2">
                {/* Trade Environment Badge */}
                <button
                  type="button"
                  onClick={() => {
                    if (tradeEnv === 'SIMULATE') {
                      setPendingEnvSwitch('REAL')
                      setShowEnvConfirm(true)
                    } else {
                      handleEnvSwitch('SIMULATE')
                    }
                  }}
                  className={`text-xs px-2 py-1 rounded-full font-medium transition-colors cursor-pointer ${
                    tradeEnv === 'SIMULATE' 
                      ? 'bg-yellow-500/20 text-yellow-600 dark:text-yellow-400 hover:bg-yellow-500/30'
                      : 'bg-red-500/20 text-red-600 dark:text-red-400 hover:bg-red-500/30'
                  }`}
                  title="Click to switch environment"
                >
                  {tradeEnv === 'SIMULATE' ? '🟢 模擬倉' : '🔴 真實環境'}
                </button>
              </div>
            )}
            {/* Broker Sync Button */}
            <button
              type="button"
              onClick={() => { 
                console.log('Header sync button clicked!'); 
                alert('Click detect!');
                syncBrokerPositions(); 
              }}
              disabled={syncing}
              className="p-2 rounded-lg hover:bg-secondary transition-colors cursor-pointer disabled:opacity-50"
              title="同步持倉"
            >
              <RefreshCw className={`w-5 h-5 ${syncing ? 'animate-spin' : ''}`} />
            </button>
            <button 
              type="button"
              onClick={() => setShowSettings(!showSettings)}
              className="p-2 rounded-lg hover:bg-secondary transition-colors cursor-pointer"
            >
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>
      
      {/* Settings Panel */}
      {showSettings && (
        <div className="border-b border-border bg-card/30">
          <div className="max-w-6xl mx-auto px-4 py-4 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-sm text-muted-foreground flex items-center gap-2">
                Account Size ($)
                <button 
                  type="button"
                  onClick={syncAccountBalance}
                  disabled={syncingBalance}
                  className="p-1 rounded hover:bg-secondary/50 transition-colors cursor-pointer disabled:opacity-50"
                  title="從富途同步美元帳戶餘額"
                >
                  <RefreshCw className={`w-3 h-3 ${syncingBalance ? 'animate-spin' : ''}`} />
                </button>
              </label>
              <div className="flex gap-2 items-center">
                <input
                  type="number"
                  value={settings.accountSize}
                  onChange={(e) => setSettings({ ...settings, accountSize: parseFloat(e.target.value) || 0 })}
                  className="w-full mt-1 px-4 py-2 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              {balanceLastUpdated && (
                <p className="text-xs text-muted-foreground mt-1">
                  餘額更新: {new Date(balanceLastUpdated).toLocaleString()}
                </p>
              )}
              <p className="text-xs text-muted-foreground mt-1">
                每日美股收市後自動更新
              </p>
            </div>
            <div>
              <label className="text-sm text-muted-foreground flex items-center gap-2">
                Default Risk %
                <span className="text-xs text-muted-foreground/50">(每筆交易風險額)</span>
              </label>
              <div className="flex items-center gap-3 mt-1">
                <input
                  type="number"
                  step="0.1"
                  min="0.1"
                  max="5"
                  value={settings.defaultRiskPercent}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    if (!isNaN(val) && val > 0) {
                      setSettings({ ...settings, defaultRiskPercent: Math.min(5, Math.max(0.1, val)) })
                    }
                  }}
                  className="w-24 px-4 py-2 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-center font-mono"
                />
                <span className="text-muted-foreground">%</span>
                <span className="text-xs text-muted-foreground">
                  (帳戶 ${settings.accountSize.toLocaleString()} × {settings.defaultRiskPercent}% = ${(settings.accountSize * settings.defaultRiskPercent / 100).toFixed(0)} 每筆風險)
                </span>
              </div>
              {/* Quick presets */}
              <div className="flex gap-2 mt-2">
                {[0.3, 0.5, 1, 2].map(val => (
                  <button
                    key={val}
                    type="button"
                    onClick={() => setSettings({ ...settings, defaultRiskPercent: val })}
                    className={`px-3 py-1 text-xs rounded-full border transition-colors cursor-pointer ${
                      settings.defaultRiskPercent === val 
                        ? 'bg-primary text-primary-foreground border-primary' 
                        : 'border-border hover:border-primary/50'
                    }`}
                  >
                    {val}%
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-sm text-muted-foreground">ATR 倍數 (止蝕)</label>
              <select
                value={settings.atrMultiplier}
                onChange={(e) => setSettings({ ...settings, atrMultiplier: parseFloat(e.target.value) })}
                className="w-full mt-1 px-4 py-2 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="1">1</option>
                <option value="1.5">1.5</option>
                <option value="2">2</option>
                <option value="2.5">2.5</option>
                <option value="3">3</option>
              </select>
            </div>
            <div>
              <label className="text-sm text-muted-foreground">ATR 週期</label>
              <input
                type="number"
                min="1"
                max="100"
                value={settings.atrPeriod}
                onChange={(e) => setSettings({ ...settings, atrPeriod: Math.max(1, Math.min(100, parseInt(e.target.value) || 14)) })}
                className="w-full mt-1 px-4 py-2 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>
        </div>
      )}
      
      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Tab Content */}
        {activeTab === 'position' ? (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-stretch">
          {/* Input Section */}
          <div className="lg:col-span-2 space-y-6 flex flex-col">
            {/* Quote Info Card */}
            {quoteData && (
              <div className="bg-card border border-border rounded-xl p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-2xl font-bold">{ticker.toUpperCase()}</h2>
                    <p className="text-muted-foreground">{quoteData.name || quoteData.symbol}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-bold">${quoteData.lastPrice?.toFixed(2)}</p>
                    <p className={`flex items-center gap-1 ${(quoteData.change ?? 0) >= 0 ? 'text-profit' : 'text-loss'}`}>
                      {(quoteData.change ?? 0) >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                      {(quoteData.change ?? 0) >= 0 ? '+' : ''}{quoteData.changePercent?.toFixed(2)}%
                    </p>
                  </div>
                </div>
                <div className="mt-4 flex gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">ATR ({settings.atrPeriod}): </span>
                    <span className="text-primary font-mono">${atr?.toFixed(2) || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Volume: </span>
                    <span className="font-mono">{quoteData.volume?.toLocaleString() || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">High: </span>
                    <span className="font-mono">${quoteData.high?.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Low: </span>
                    <span className="font-mono">${quoteData.low?.toFixed(2)}</span>
                  </div>
                </div>
                
                    {/* Moving Averages */}
                <div className="mt-4 pt-4 border-t border-border">
                  <div className="flex gap-4 text-sm flex-wrap">
                    <div>
                      <span className="text-muted-foreground">EMA10: </span>
                      <button 
                        type="button"
                        onClick={() => { const v = quoteData.ema10; if (v != null) { setEntryPrice(v.toFixed(2)); if (atr) setStopLoss(direction === 'LONG' ? (v - atr * settings.atrMultiplier).toFixed(2) : (v + atr * settings.atrMultiplier).toFixed(2)); } }}
                        className="font-mono text-cyan-400 hover:underline cursor-pointer"
                        title="Set as entry price with ATR stop"
                      >${quoteData.ema10?.toFixed(2) || 'N/A'}</button>
                    </div>
                    <div>
                      <span className="text-muted-foreground">EMA20: </span>
                      <button 
                        type="button"
                        onClick={() => { const v = quoteData.ema20; if (v != null) { setEntryPrice(v.toFixed(2)); if (atr) setStopLoss(direction === 'LONG' ? (v - atr * settings.atrMultiplier).toFixed(2) : (v + atr * settings.atrMultiplier).toFixed(2)); } }}
                        className="font-mono text-orange-400 hover:underline cursor-pointer"
                        title="Set as entry price with ATR stop"
                      >${quoteData.ema20?.toFixed(2) || 'N/A'}</button>
                    </div>
                    <div>
                      <span className="text-muted-foreground">SMA50: </span>
                      <button 
                        type="button"
                        onClick={() => { const v = quoteData.sma50; if (v != null) { setEntryPrice(v.toFixed(2)); if (atr) setStopLoss(direction === 'LONG' ? (v - atr * settings.atrMultiplier).toFixed(2) : (v + atr * settings.atrMultiplier).toFixed(2)); } }}
                        className="font-mono text-blue-400 hover:underline cursor-pointer"
                        title="Set as entry price with ATR stop"
                      >${quoteData.sma50?.toFixed(2) || 'N/A'}</button>
                    </div>
                    <div>
                      <span className="text-muted-foreground">SMA200: </span>
                      <button 
                        type="button"
                        onClick={() => { const v = quoteData.sma200; if (v != null) { setEntryPrice(v.toFixed(2)); if (atr) setStopLoss(direction === 'LONG' ? (v - atr * settings.atrMultiplier).toFixed(2) : (v + atr * settings.atrMultiplier).toFixed(2)); } }}
                        className="font-mono text-purple-400 hover:underline cursor-pointer"
                        title="Set as entry price with ATR stop"
                      >${quoteData.sma200?.toFixed(2) || 'N/A'}</button>
                    </div>
                  </div>
                </div>
                
                {/* Candlestick Chart */}
                {historicalData.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-border">
                    <h4 className="text-sm text-muted-foreground mb-2">價格圖表</h4>
                    <CandlestickChart 
                      data={historicalData} 
                      direction={direction}
                      entryPrice={entryPrice ? parseFloat(entryPrice) : undefined}
                      stopLoss={stopLoss ? parseFloat(stopLoss) : undefined}
                      atr={atr}
                      atrMultiplier={settings.atrMultiplier}
                      atrPeriod={settings.atrPeriod}
                      onEntryPriceChange={handleChartClick}
                      onStopLossChange={(price) => setStopLoss(price.toFixed(2))}
                      onAtrMultiplierChange={(multiplier) => setSettings(prev => ({ ...prev, atrMultiplier: multiplier }))}
                    />
                  </div>
                )}
              </div>
            )}
            
            {/* Input Form */}
            <div className="bg-card border border-border rounded-xl p-6 space-y-4">
              <h3 className="text-lg font-semibold mb-4">倉位設定</h3>
              
              {/* LONG/SHORT Toggle */}
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setDirection('LONG')
                    // 切換方向時重新計算止蝕
                    if (atr && entryPrice) {
                      const price = parseFloat(entryPrice)
                      setStopLoss((price - atr * settings.atrMultiplier).toFixed(2))
                    }
                  }}
                  className={`flex-1 py-3 rounded-lg font-medium transition-all cursor-pointer ${
                    direction === 'LONG'
                      ? 'bg-profit text-black shadow-lg'
                      : 'bg-secondary text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <TrendingUp className="w-5 h-5 mx-auto mb-1" />
                  Long (做多)
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setDirection('SHORT')
                    // 切換方向時重新計算止蝕
                    if (atr && entryPrice) {
                      const price = parseFloat(entryPrice)
                      setStopLoss((price + atr * settings.atrMultiplier).toFixed(2))
                    }
                  }}
                  className={`flex-1 py-3 rounded-lg font-medium transition-all cursor-pointer ${
                    direction === 'SHORT'
                      ? 'bg-loss text-white shadow-lg'
                      : 'bg-secondary text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <TrendingDown className="w-5 h-5 mx-auto mb-1" />
                  Short (做空)
                </button>
              </div>
              
              {/* 第一行：股票代號 | 買入價 & 止蝕價 */}
              <div className="grid grid-cols-2 gap-4">
                {/* 左邊：股票代號 */}
                <div>
                  <label className="text-sm text-muted-foreground">股票代號</label>
                  <input
                    type="text"
                    value={ticker}
                    onChange={(e) => setTicker(e.target.value.toUpperCase())}
                    placeholder="例如: NVDA, 00700, 9888"
                    className="w-full mt-1 px-4 py-2 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary font-mono"
                  />
                </div>

                {/* 右邊：買入價 & 止蝕價 */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm text-muted-foreground">觸發/限價 ($)</label>
                    <input
                      type="number"
                      step="0.01"
                      value={entryPrice}
                      onChange={(e) => setEntryPrice(e.target.value)}
                      placeholder={direction === 'LONG' ? '買入' : '賣出'}
                      className="w-full mt-1 px-4 py-2 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary font-mono"
                    />
                    {quoteData?.lastPrice && entryPrice && (
                      <p className={`text-xs mt-1 ${parseFloat(entryPrice) > quoteData.lastPrice ? 'text-orange-400' : 'text-muted-foreground'}`}>
                        {parseFloat(entryPrice) > quoteData.lastPrice
                          ? '⬆ 突破價'
                          : parseFloat(entryPrice) < quoteData.lastPrice
                            ? '⬇ 限價'
                            : '= 現價'}
                      </p>
                    )}
                  </div>

                  <div>
                    <label className="text-sm text-muted-foreground">止蝕價 ($)</label>
                    <div className="flex gap-1">
                      <input
                        type="number"
                        step="0.01"
                        value={stopLoss}
                        onChange={(e) => setStopLoss(e.target.value)}
                        placeholder="止蝕"
                        className="w-full mt-1 px-4 py-2 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary font-mono"
                      />
                      {suggestedStopLoss && (
                        <button
                          type="button"
                          onClick={applySuggestedStopLoss}
                          className="mt-1 px-2 py-2 bg-primary/20 text-primary rounded-lg hover:bg-primary/30 transition-colors text-sm cursor-pointer"
                          title={`建議: $${suggestedStopLoss.toFixed(2)}`}
                        >
                          <Info className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* 訂單期限 */}
              <div>
                <label className="text-sm text-muted-foreground">訂單期限</label>
                <div className="flex gap-4 mt-1">
                    <button
                      type="button"
                      onClick={() => setTimeInForce('DAY')}
                      className={`flex-1 px-3 py-2 rounded-lg text-sm transition-colors cursor-pointer ${
                        timeInForce === 'DAY'
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-secondary border border-border hover:border-primary/50'
                      }`}
                    >
                      當日有效
                    </button>
                    <button
                      type="button"
                      onClick={() => setTimeInForce('GTC')}
                      className={`flex-1 px-3 py-2 rounded-lg text-sm transition-colors cursor-pointer ${
                        timeInForce === 'GTC'
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-secondary border border-border hover:border-primary/50'
                      }`}
                    >
                      撤單前有效
                    </button>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {timeInForce === 'DAY' && '今日收市前有效'}
                    {timeInForce === 'GTC' && '直至主動撤單'}
                  </p>
                </div>
                {suggestedStopLoss && (
                  <p className="text-xs text-muted-foreground">
                    建議止蝕 (${settings.atrMultiplier}×ATR): ${suggestedStopLoss.toFixed(2)}
                    {direction === 'SHORT' && <span className="text-loss ml-2">(止蝕喺上面)</span>}
                  </p>
                )}
              
              {/* Risk Info */}
              <div className="bg-secondary/50 rounded-lg p-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">1R 風險額:</span>
                  <span className="font-mono text-warning">${riskAmount.toFixed(2)}</span>
                </div>
                <div className="flex items-center justify-between text-sm mt-2">
                  <span className="text-muted-foreground">止蝕空間:</span>
                  <span className={`font-mono ${stopDistance > 0 ? 'text-loss' : 'text-muted-foreground'}`}>
                    ${stopDistance.toFixed(2)} ({stopLossPercent.toFixed(2)}%)
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm mt-2">
                  <span className="text-muted-foreground">方向:</span>
                  <span className={`font-mono ${direction === 'LONG' ? 'text-profit' : 'text-loss'}`}>
                    {direction === 'LONG' ? 'Long (做多)' : 'Short (做空)'}
                  </span>
                </div>
              </div>
              
              {/* Warnings */}
              {portfolioWarning && (
                <div className="flex items-center gap-2 p-4 bg-destructive/20 border border-destructive rounded-lg text-loss">
                  <AlertTriangle className="w-5 h-5" />
                  <span>組合風險超過20% - 建議減少倉位</span>
                </div>
              )}
              
              {stopLossWarning && (
                <div className="flex items-center gap-2 p-4 bg-warning/20 border border-warning rounded-lg text-warning">
                  <AlertTriangle className="w-5 h-5" />
                  <span>止蝕超過8% - 建議使用更嚴格止蝕 (VCP/CANSLIM原則)</span>
                </div>
              )}
              
              {/* R/R Visualization */}
              {entryPrice && stopLoss && quoteData && (
                <div className="mt-6">
                  <h4 className="text-sm text-muted-foreground mb-2">R倍數可視化</h4>
                  <RMultiplierBar 
                    direction={direction}
                    currentPrice={quoteData.lastPrice || 0}
                    entryPrice={parseFloat(entryPrice)}
                    stopLoss={parseFloat(stopLoss)}
                  />
                </div>
              )}
            </div>
          </div>
          
          {/* Results Section */}
          <div className="space-y-6 flex flex-col h-full">
            {/* Main Result */}
            <div className="bg-card border border-border rounded-xl p-6 text-center">
              <p className="text-muted-foreground mb-2">{direction === 'LONG' ? '應買股數' : '應借入股數'}</p>
              <p className="text-6xl font-bold text-primary glow-green">{shares.toLocaleString()}</p>
              <p className="text-muted-foreground mt-4">總持倉價值</p>
              <p className="text-2xl font-mono">${positionValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
              <p className={`text-lg mt-2 ${portfolioPercent > 20 ? 'text-loss' : 'text-muted-foreground'}`}>
                {portfolioPercent.toFixed(1)}% 組合
              </p>
              
              <div className="flex gap-2 mt-6">
                <button
                  type="button"
                  onClick={() => setShowOrderConfirm(true)}
                  disabled={shares <= 0}
                  className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-lg hover:bg-opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer ${
                    direction === 'SHORT'
                      ? 'bg-loss text-white'
                      : tradeEnv === 'REAL' 
                        ? 'bg-red-500 text-white' 
                        : 'bg-profit text-black'
                  }`}
                >
                  {direction === 'LONG' ? (
                    <TrendingUp className="w-4 h-4" />
                  ) : (
                    <TrendingDown className="w-4 h-4" />
                  )}
                  {tradeEnv === 'REAL' ? '一鍵落單 (真金白銀)' : '一鍵落單 (模擬)'}
                </button>
                <button
                  type="button"
                  onClick={() => { setTicker(''); setEntryPrice(''); setStopLoss(''); setTimeInForce('GTC'); setQuoteData(null); setAtr(null); setHistoricalData([]); setDirection('LONG'); setOrderType('LIMIT'); setTriggerPrice(''); }}
                  className="px-4 py-3 bg-secondary border border-border rounded-lg hover:bg-secondary/80 transition-colors cursor-pointer"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>
            </div>
            
            {/* Targets */}
            {entryPrice && stopLoss && (
              <div className="bg-card border border-border rounded-xl p-6">
                <h3 className="text-lg font-semibold mb-4">目標價位</h3>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">{direction === 'LONG' ? '買入價' : '賣出價'}</span>
                    <span className={`font-mono ${direction === 'LONG' ? 'text-primary' : 'text-loss'}`}>${parseFloat(entryPrice).toFixed(2)}</span>
                  </div>
                  {direction === 'LONG' ? (
                    <>
                      <div className="flex justify-between items-center">
                        <span className="text-muted-foreground">1R 目標</span>
                        <span className="font-mono text-profit">${(parseFloat(entryPrice) + stopDistance).toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-muted-foreground">2R 目標</span>
                        <span className="font-mono text-profit">${(parseFloat(entryPrice) + stopDistance * 2).toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-muted-foreground">3R 目標</span>
                        <span className="font-mono text-profit">${(parseFloat(entryPrice) + stopDistance * 3).toFixed(2)}</span>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="flex justify-between items-center">
                        <span className="text-muted-foreground">1R 目標</span>
                        <span className="font-mono text-loss">${(parseFloat(entryPrice) - stopDistance).toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-muted-foreground">2R 目標</span>
                        <span className="font-mono text-loss">${(parseFloat(entryPrice) - stopDistance * 2).toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-muted-foreground">3R 目標</span>
                        <span className="font-mono text-loss">${(parseFloat(entryPrice) - stopDistance * 3).toFixed(2)}</span>
                      </div>
                    </>
                  )}
                  <div className="border-t border-border pt-3 mt-3 flex justify-between items-center">
                    <span className="text-warning">止蝕位</span>
                    <span className="font-mono text-loss">${parseFloat(stopLoss).toFixed(2)}</span>
                  </div>
                </div>
              </div>
            )}
            
            {/* History */}
            {positions.length > 0 && (
              <div className="bg-card border border-border rounded-xl p-6">
                <h3 className="text-lg font-semibold mb-4">本次記錄</h3>
                <div className="space-y-3 max-h-64 overflow-y-auto">
                  {positions.map((pos) => (
                    <div key={pos.id} className="flex items-center justify-between p-3 bg-secondary/50 rounded-lg">
                      <div>
                        <span className="font-bold text-primary">{pos.ticker}</span>
                        <span className="text-xs text-muted-foreground ml-2">{pos.date}</span>
                        <p className="text-xs text-muted-foreground">
                          {pos.shares} 股 @ ${pos.buyPrice}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-mono">${pos.positionValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                        <button type="button" onClick={() => deletePosition(pos.id)} className="p-1 text-muted-foreground hover:text-loss transition-colors cursor-pointer">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

          </div>
        </div>
        ) : (
          /* Zero-Cost Calculator Tab */
          <ZeroCostCalculator 
            brokerPositions={brokerPositions} 
            syncError={syncError}
            syncing={syncing}
            onSync={syncBrokerPositions}
            onSelectPosition={(profitPercent, shares) => {
              // 填充到左边计算器
              setProfitPercentLocal(profitPercent)
              setSharesLocal(shares.toString())
            }}
            profitPercent={profitPercentLocal}
            setProfitPercent={setProfitPercentLocal}
            shares={sharesLocal}
            setShares={setSharesLocal}
            accountSize={settings.accountSize}
          />
        )}
      </main>
      
      {/* Environment Switch Confirmation Dialog */}
      {showEnvConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-card border border-red-500 rounded-xl p-6 max-w-md w-full">
            <div className="text-center">
              <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <AlertTriangle className="w-8 h-8 text-red-500" />
              </div>
              <h3 className="text-xl font-bold text-red-500 mb-2">⚠️ 警告：你即將切換至真實交易環境</h3>
              <p className="text-muted-foreground mb-4">
                切換後，所有落單將會扣除真實資金！<br/>
                請確保你已經了解風險，先繼續操作。
              </p>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setShowEnvConfirm(false)
                    setPendingEnvSwitch(null)
                  }}
                  className="flex-1 px-4 py-3 bg-secondary border border-border rounded-lg hover:bg-secondary/80 transition-colors cursor-pointer"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => handleEnvSwitch('REAL')}
                  className="flex-1 px-4 py-3 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors cursor-pointer"
                >
                  確認切換至真倉
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Order Confirmation Dialog */}
      {showOrderConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-card border border-border rounded-xl p-6 max-w-md w-full">
            {orderResult ? (
              /* Order Result */
              <div className="text-center">
                {orderResult.success ? (
                  <>
                    <div className="w-16 h-16 bg-profit/20 rounded-full flex items-center justify-center mx-auto mb-4">
                      <TrendingUp className="w-8 h-8 text-profit" />
                    </div>
                    <h3 className="text-xl font-bold text-profit mb-2">落單成功！</h3>
                    <p className="text-muted-foreground mb-2">{orderResult.message}</p>
                    {orderResult.orderId && (
                      <p className="text-sm text-muted-foreground">Order ID: {orderResult.orderId}</p>
                    )}
                  </>
                ) : (
                  <>
                    <div className="w-16 h-16 bg-loss/20 rounded-full flex items-center justify-center mx-auto mb-4">
                      <AlertTriangle className="w-8 h-8 text-loss" />
                    </div>
                    <h3 className="text-xl font-bold text-loss mb-2">落單失敗</h3>
                    <p className="text-muted-foreground">{orderResult.message}</p>
                  </>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setShowOrderConfirm(false)
                    setOrderResult(null)
                  }}
                  className="mt-6 w-full px-4 py-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors cursor-pointer"
                >
                  關閉
                </button>
              </div>
            ) : (
              /* Order Confirmation */
              <>
                <h3 className="text-xl font-bold mb-4 flex items-center gap-2">
                  {direction === 'LONG' ? (
                    <>
                      <TrendingUp className="w-6 h-6 text-profit" />
                      <span>確認買入 (Long)</span>
                    </>
                  ) : (
                    <>
                      <TrendingDown className="w-6 h-6 text-loss" />
                      <span>確認借入 (Short)</span>
                    </>
                  )}
                </h3>
                
                <div className="bg-secondary/50 rounded-lg p-4 mb-6">
                  <div className="flex justify-between mb-2">
                    <span className="text-muted-foreground">股票:</span>
                    <span className="font-bold">{ticker.toUpperCase()}</span>
                  </div>
                  <div className="flex justify-between mb-2">
                    <span className="text-muted-foreground">訂單類型:</span>
                    <span className={`font-mono ${quoteData?.lastPrice && entryPrice && parseFloat(entryPrice) > quoteData.lastPrice ? 'text-orange-400' : ''}`}>
                      {quoteData?.lastPrice && entryPrice && parseFloat(entryPrice) > quoteData.lastPrice ? '突破單' : '限價單'}
                    </span>
                  </div>
                  <div className="flex justify-between mb-2">
                    <span className="text-muted-foreground">{direction === 'LONG' ? '買入' : '賣出'}價:</span>
                    <span className={`font-mono ${quoteData?.lastPrice && entryPrice && parseFloat(entryPrice) > quoteData.lastPrice ? 'text-orange-400' : ''}`}>
                      ${parseFloat(entryPrice).toFixed(2)}
                      {quoteData?.lastPrice && entryPrice && (
                        <span className="text-xs ml-1">
                          ({parseFloat(entryPrice) > quoteData.lastPrice ? '突破' : parseFloat(entryPrice) < quoteData.lastPrice ? '限價' : '='})
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="flex justify-between mb-2">
                    <span className="text-muted-foreground">股數:</span>
                    <span className={`font-mono ${direction === 'LONG' ? 'text-profit' : 'text-loss'}`}>{shares.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between mb-2">
                    <span className="text-muted-foreground">期限:</span>
                    <span className="font-mono">
                      {timeInForce === 'DAY' ? '當日有效' : '撤單前有效'}
                    </span>
                  </div>
                  {stopLoss && (
                  <>
                    <div className="flex justify-between mb-2">
                      <span className="text-muted-foreground">止蝕位:</span>
                      <span className="font-mono text-warning">${parseFloat(stopLoss).toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between mb-2">
                      <span className="text-muted-foreground">止蝕觸發:</span>
                      <span className="font-mono text-warning">
                        {direction === 'LONG'
                          ? `SELL ${shares} @ $${parseFloat(stopLoss).toFixed(2)}`
                          : `BUY ${shares} @ $${parseFloat(stopLoss).toFixed(2)}`
                        }
                      </span>
                    </div>
                  </>
                )}
                  <div className="border-t border-border pt-2 mt-2 flex justify-between">
                    <span className="text-muted-foreground">總額:</span>
                    <span className="font-bold">${(shares * parseFloat(entryPrice)).toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                  </div>
                </div>

                {stopLoss && (
                  <div className={`${direction === 'LONG' ? 'bg-profit/20 border-profit' : 'bg-loss/20 border-loss'} border rounded-lg p-3 mb-6`}>
                    <p className={`text-sm flex items-center gap-2 ${direction === 'LONG' ? 'text-profit' : 'text-loss'}`}>
                      <AlertTriangle className="w-4 h-4" />
                      {direction === 'LONG' 
                        ? `當買入單成交後，將自動觸發止蝕單 (SELL ${shares} @ $${parseFloat(stopLoss).toFixed(2)})`
                        : `當借入單成交後，將自動觸發止蝕單 (BUY ${shares} @ $${parseFloat(stopLoss).toFixed(2)})`
                      }
                    </p>
                  </div>
                )}
                
                {tradeEnv === 'REAL' ? (
                  <div className="bg-red-500/20 border border-red-500 rounded-lg p-3 mb-6">
                    <p className="text-sm text-red-400 flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4" />
                      警告：真實交易環境 (REAL) - 落單將扣除真實資金！
                    </p>
                  </div>
                ) : (
                  <div className="bg-warning/20 border border-warning rounded-lg p-3 mb-6">
                    <p className="text-sm text-warning flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4" />
                      模擬交易環境 (SIMULATE)
                    </p>
                  </div>
                )}
                
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => setShowOrderConfirm(false)}
                    disabled={ordering}
                    className="flex-1 px-4 py-3 bg-secondary border border-border rounded-lg hover:bg-secondary/80 transition-colors cursor-pointer disabled:opacity-50"
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    onClick={handlePlaceOrder}
                    disabled={ordering}
                    className="flex-1 px-4 py-3 bg-profit text-black rounded-lg hover:bg-profit/90 transition-colors cursor-pointer disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {ordering ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        落單緊...
                      </>
                    ) : (
                      <>
                        <TrendingUp className="w-4 h-4" />
                        確認落單
                      </>
                    )}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
