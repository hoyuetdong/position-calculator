'use client'

import { useState, useEffect, useCallback } from 'react'
import { 
  Calculator, 
  TrendingUp, 
  TrendingDown, 
  AlertTriangle, 
  Save,
  Trash2,
  Settings,
  Info,
  Wifi,
  WifiOff,
  RefreshCw
} from 'lucide-react'
import { 
  getQuote, 
  getHistoricalKLines,
  initFutuAPI,
  type QuoteData 
} from '@/lib/futuAPI'
import CandlestickChart from '@/components/CandlestickChart'

interface Position {
  id: string
  ticker: string
  buyPrice: number
  stopLoss: number
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
}

// Connection status component
function ConnectionStatus({ connected }: { connected: boolean }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-card border border-border">
      {connected ? (
        <>
          <Wifi className="w-4 h-4 text-profit" />
          <span className="text-xs text-profit">已連接Yahoo</span>
        </>
      ) : (
        <>
          <WifiOff className="w-4 h-4 text-loss" />
          <span className="text-xs text-loss">未連接</span>
        </>
      )}
    </div>
  )
}

// R-multiples visualization
function RMultiplierBar({ 
  currentPrice, 
  entryPrice, 
  stopLoss
}: { 
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
  
  const stopDistance = entryPrice - stopLoss
  if (stopDistance <= 0) return null // 止蝕應該低於買入價
  
  const r1 = entryPrice + stopDistance
  const r2 = entryPrice + (stopDistance * 2)
  const r3 = entryPrice + (stopDistance * 3)
  
  const min = stopLoss * 0.95
  const max = r3 * 1.05
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
            買入: ${entryPrice.toFixed(2)}
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
        <span className="text-cyan-400 absolute transform -translate-x-1/2" style={{ left: `${getPosition(entryPrice)}%` }}>買入: ${entryPrice.toFixed(2)}</span>
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

export default function Home() {
  const [settings, setSettings] = useState<Settings>({
    accountSize: 100000,
    defaultRiskPercent: 0.3,
    atrMultiplier: 1.5
  })
  // Hydration fix: defer all client-side logic
  const [hydrated, setHydrated] = useState(false)
  
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
  const [buyPoint, setBuyPoint] = useState('')
  const [stopLoss, setStopLoss] = useState('')
  const [quoteData, setQuoteData] = useState<QuoteData | null>(null)
  const [atr, setAtr] = useState<number | null>(null)
  const [historicalData, setHistoricalData] = useState<{time: number; open: number; high: number; low: number; close: number}[]>([])
  const [loading, setLoading] = useState(false)
  // Yahoo 唔使連線，預設已連接
  const [connected, setConnected] = useState(true)
  const [positions, setPositions] = useState<Position[]>([])
  const [showSettings, setShowSettings] = useState(false)
  
  // Handle chart click - set buy price and auto-calculate stop loss
  const handleChartClick = useCallback((price: number) => {
    setBuyPoint(price.toFixed(2))
    // Auto calculate stop loss based on ATR
    if (atr) {
      const stopLossPrice = price - atr * settings.atrMultiplier
      setStopLoss(stopLossPrice.toFixed(2))
    }
  }, [atr, settings.atrMultiplier])
  
  // Initialize Futu API connection
  useEffect(() => {
    const init = async () => {
      try {
        await initFutuAPI()
        setConnected(true)
      } catch (error) {
        console.error('Futu API connection error:', error)
        setConnected(false)
      }
    }
    init()
  }, [])
  
  // Fetch quote when ticker changes
  useEffect(() => {
    const fetchData = async () => {
      if (ticker.length >= 1) {
        setLoading(true)
        try {
          const quote = await getQuote(ticker)
          setQuoteData(quote)
          
          // Get historical data for ATR calculation and chart
          const klines = await getHistoricalKLines(ticker, 500) // Get 60 days for chart
          
          // Store historical data for chart
          const histData = klines.map(k => ({
            time: k.time,
            open: parseFloat(k.open),
            high: parseFloat(k.high),
            low: parseFloat(k.low),
            close: parseFloat(k.close)
          }))
          setHistoricalData(histData)
          
          if (klines.length >= 14) {
            const atrData = klines.slice(-14).map(k => {
              const high = parseFloat(k.high)
              const low = parseFloat(k.low)
              const close = parseFloat(k.close)
              const tr = Math.max(high - low, Math.abs(high - close), Math.abs(low - close))
              return tr
            })
            const calculatedAtr = atrData.reduce((a, b) => a + b, 0) / 14
            setAtr(calculatedAtr)
            
            // Auto-fill buy point with current price if empty
            if (!buyPoint && quote.lastPrice) {
              setBuyPoint(quote.lastPrice.toFixed(2))
            }
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
  }, [ticker])
  
  // Calculations（避免 NaN：空字串當 0）
  const buyNum = parseFloat(buyPoint) || 0
  const stopNum = parseFloat(stopLoss) || 0
  const riskAmount = settings.accountSize * (settings.defaultRiskPercent / 100)
  const stopDistance = buyNum - stopNum
  const sharesToBuy = stopDistance > 0 ? Math.floor(riskAmount / stopDistance) : 0
  const positionValue = sharesToBuy * buyNum
  const portfolioPercent = settings.accountSize > 0 ? (positionValue / settings.accountSize) * 100 : 0
  const stopLossPercent = buyNum > 0 ? (stopDistance / buyNum) * 100 : 0
  
  // Suggested stop loss from ATR - based on buy price if available, otherwise last price
  const basePrice = parseFloat(buyPoint) || quoteData?.lastPrice || 0
  const suggestedStopLoss = (atr && basePrice) 
    ? basePrice - (atr * settings.atrMultiplier)
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
    if (sharesToBuy > 0 && ticker && buyPoint && stopLoss) {
      const newPosition: Position = {
        id: Date.now().toString(),
        ticker: ticker.toUpperCase(),
        buyPrice: parseFloat(buyPoint),
        stopLoss: parseFloat(stopLoss),
        shares: sharesToBuy,
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
      await initFutuAPI()
      setConnected(true)
    } catch {
      setConnected(false)
    }
    setLoading(false)
  }
  
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Calculator className="w-6 h-6 text-primary" />
            <h1 className="text-xl font-bold">VCP Position Calculator</h1>
            <span className="text-xs text-muted-foreground">(Yahoo Finance)</span>
          </div>
          <div className="flex items-center gap-3">
            <ConnectionStatus connected={connected} />
            {!connected && (
              <button 
                type="button"
                onClick={reconnect}
                className="p-2 rounded-lg hover:bg-secondary transition-colors cursor-pointer"
              >
                <RefreshCw className="w-5 h-5" />
              </button>
            )}
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
              <label className="text-sm text-muted-foreground">Account Size ($)</label>
              <input
                type="number"
                value={settings.accountSize}
                onChange={(e) => setSettings({ ...settings, accountSize: parseFloat(e.target.value) || 0 })}
                className="w-full mt-1 px-4 py-2 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">Default Risk %</label>
              <input
                type="text"
                value={settings.defaultRiskPercent || ''}
                onChange={(e) => {
                  const val = e.target.value;
                  if (val === '' || /^\d*\.?\d*$/.test(val)) {
                    setSettings({ ...settings, defaultRiskPercent: val === '' ? 0.3 : parseFloat(val) || 0.3 })
                  }
                }}
                className="w-full mt-1 px-4 py-2 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                placeholder="0.3"
              />
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
          </div>
        </div>
      )}
      
      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Input Section */}
          <div className="lg:col-span-2 space-y-6">
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
                    <span className="text-muted-foreground">ATR (14): </span>
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
                        onClick={() => { const v = quoteData.ema10; if (v != null) { setBuyPoint(v.toFixed(2)); if (atr) setStopLoss((v - atr * settings.atrMultiplier).toFixed(2)); } }}
                        className="font-mono text-cyan-400 hover:underline cursor-pointer"
                        title="Set as buy price with ATR stop"
                      >${quoteData.ema10?.toFixed(2) || 'N/A'}</button>
                    </div>
                    <div>
                      <span className="text-muted-foreground">EMA20: </span>
                      <button 
                        type="button"
                        onClick={() => { const v = quoteData.ema20; if (v != null) { setBuyPoint(v.toFixed(2)); if (atr) setStopLoss((v - atr * settings.atrMultiplier).toFixed(2)); } }}
                        className="font-mono text-cyan-400 hover:underline cursor-pointer"
                        title="Set as buy price with ATR stop"
                      >${quoteData.ema20?.toFixed(2) || 'N/A'}</button>
                    </div>
                    <div>
                      <span className="text-muted-foreground">SMA50: </span>
                      <button 
                        type="button"
                        onClick={() => { const v = quoteData.sma50; if (v != null) { setBuyPoint(v.toFixed(2)); if (atr) setStopLoss((v - atr * settings.atrMultiplier).toFixed(2)); } }}
                        className="font-mono text-yellow-400 hover:underline cursor-pointer"
                        title="Set as buy price with ATR stop"
                      >${quoteData.sma50?.toFixed(2) || 'N/A'}</button>
                    </div>
                    <div>
                      <span className="text-muted-foreground">SMA200: </span>
                      <button 
                        type="button"
                        onClick={() => { const v = quoteData.sma200; if (v != null) { setBuyPoint(v.toFixed(2)); if (atr) setStopLoss((v - atr * settings.atrMultiplier).toFixed(2)); } }}
                        className="font-mono text-orange-400 hover:underline cursor-pointer"
                        title="Set as buy price with ATR stop"
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
                      buyPrice={buyPoint ? parseFloat(buyPoint) : undefined}
                      stopLoss={stopLoss ? parseFloat(stopLoss) : undefined}
                      atr={atr}
                      atrMultiplier={settings.atrMultiplier}
                      onBuyPriceChange={handleChartClick}
                      onStopLossChange={(price) => setStopLoss(price.toFixed(2))}
                    />
                  </div>
                )}
              </div>
            )}
            
            {/* Input Form */}
            <div className="bg-card border border-border rounded-xl p-6 space-y-4">
              <h3 className="text-lg font-semibold mb-4">倉位設定</h3>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-sm text-muted-foreground">股票代號</label>
                  <input
                    type="text"
                    value={ticker}
                    onChange={(e) => setTicker(e.target.value.toUpperCase())}
                    placeholder="例如: NVDA, 00700, 9888"
                    className="w-full mt-1 px-4 py-3 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-lg font-mono"
                  />
                </div>
                
                <div>
                  <label className="text-sm text-muted-foreground">買入價 ($)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={buyPoint}
                    onChange={(e) => setBuyPoint(e.target.value)}
                    placeholder="買入價"
                    className="w-full mt-1 px-4 py-3 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-lg font-mono"
                  />
                </div>
                
                <div>
                  <label className="text-sm text-muted-foreground">止蝕價 ($)</label>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      step="0.01"
                      value={stopLoss}
                      onChange={(e) => setStopLoss(e.target.value)}
                      placeholder="止蝕價"
                      className="w-full mt-1 px-4 py-3 bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-lg font-mono"
                    />
                    {suggestedStopLoss && (
                      <button 
                        type="button"
                        onClick={applySuggestedStopLoss}
                        className="mt-1 px-3 py-2 bg-primary/20 text-primary rounded-lg hover:bg-primary/30 transition-colors text-sm cursor-pointer"
                        title={`建議: $${suggestedStopLoss.toFixed(2)} (${settings.atrMultiplier}x ATR)`}
                      >
                        <Info className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                  {suggestedStopLoss && (
                    <p className="text-xs text-muted-foreground mt-1">
                      建議止蝕 (${settings.atrMultiplier}×ATR): ${suggestedStopLoss.toFixed(2)}
                    </p>
                  )}
                </div>
              </div>
              
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
              {buyPoint && stopLoss && quoteData && (
                <div className="mt-6">
                  <h4 className="text-sm text-muted-foreground mb-2">R倍數可視化</h4>
                  <RMultiplierBar 
                    currentPrice={quoteData.lastPrice || 0}
                    entryPrice={parseFloat(buyPoint)}
                    stopLoss={parseFloat(stopLoss)}
                  />
                </div>
              )}
            </div>
          </div>
          
          {/* Results Section */}
          <div className="space-y-6">
            {/* Main Result */}
            <div className="bg-card border border-border rounded-xl p-6 text-center">
              <p className="text-muted-foreground mb-2">應買股數</p>
              <p className="text-6xl font-bold text-primary glow-green">{sharesToBuy.toLocaleString()}</p>
              <p className="text-muted-foreground mt-4">總持倉價值</p>
              <p className="text-2xl font-mono">${positionValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
              <p className={`text-lg mt-2 ${portfolioPercent > 20 ? 'text-loss' : 'text-muted-foreground'}`}>
                {portfolioPercent.toFixed(1)}% 組合
              </p>
              
              <div className="flex gap-2 mt-6">
                <button
                  type="button"
                  onClick={savePosition}
                  disabled={sharesToBuy <= 0}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer"
                >
                  <Save className="w-4 h-4" />
                  儲存
                </button>
                <button
                  type="button"
                  onClick={() => { setTicker(''); setBuyPoint(''); setStopLoss(''); setQuoteData(null); setAtr(null); setHistoricalData([]); }}
                  className="px-4 py-3 bg-secondary border border-border rounded-lg hover:bg-secondary/80 transition-colors cursor-pointer"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>
            </div>
            
            {/* Targets */}
            {buyPoint && stopLoss && (
              <div className="bg-card border border-border rounded-xl p-6">
                <h3 className="text-lg font-semibold mb-4">目標價位</h3>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">買入價</span>
                    <span className="font-mono text-primary">${parseFloat(buyPoint).toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">1R 目標</span>
                    <span className="font-mono text-profit">${(parseFloat(buyPoint) + stopDistance).toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">2R 目標</span>
                    <span className="font-mono text-profit">${(parseFloat(buyPoint) + stopDistance * 2).toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">3R 目標</span>
                    <span className="font-mono text-profit">${(parseFloat(buyPoint) + stopDistance * 3).toFixed(2)}</span>
                  </div>
                  <div className="border-t border-border pt-3 mt-3 flex justify-between items-center">
                    <span className="text-loss">止蝕位</span>
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
      </main>
    </div>
  )
}
