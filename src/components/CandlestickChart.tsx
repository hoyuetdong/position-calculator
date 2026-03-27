'use client'

import { useEffect, useRef } from 'react'
import { createChart, ColorType, CrosshairMode, CandlestickSeries, LineSeries, IChartApi, ISeriesApi, MouseEventParams } from 'lightweight-charts'

interface ChartProps {
  data: {
    time: number
    open: number
    high: number
    low: number
    close: number
  }[]
  direction?: 'LONG' | 'SHORT'  // 持倉方向
  entryPrice?: number  // 改名：通用於 LONG/SHORT
  stopLoss?: number
  atr?: number | null
  atrMultiplier?: number
  onEntryPriceChange?: (price: number) => void  // 改名
  onStopLossChange?: (price: number) => void
}

// Calculate EMA for entire array
function calculateEMAData(data: number[], period: number): (number | null)[] {
  if (data.length < period) return data.map(() => null)
  
  const result: (number | null)[] = []
  const multiplier = 2 / (period + 1)
  
  let sum = 0
  for (let i = 0; i < period; i++) {
    sum += data[i]
    result.push(null)
  }
  let ema = sum / period
  result[period - 1] = ema
  
  for (let i = period; i < data.length; i++) {
    ema = (data[i] - ema) * multiplier + ema
    result.push(ema)
  }
  
  return result
}

// Calculate SMA for entire array
function calculateSMAData(data: number[], period: number): (number | null)[] {
  if (data.length < period) return data.map(() => null)
  
  const result: (number | null)[] = []
  
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(null)
    } else {
      const slice = data.slice(i - period + 1, i + 1)
      const sma = slice.reduce((a, b) => a + b, 0) / period
      result.push(sma)
    }
  }
  
  return result
}

export default function CandlestickChart({ 
  data, 
  buyPrice, 
  stopLoss, 
  atr, 
  atrMultiplier = 1.5,
  onBuyPriceChange, 
  onStopLossChange 
}: ChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null)
  const seriesRef = useRef<{
    ema20?: ISeriesApi<"Line">
    sma50?: ISeriesApi<"Line">
    sma200?: ISeriesApi<"Line">
    entryLine?: ISeriesApi<"Line">  // 改名：entryLine 通用於 LONG/SHORT
    stopLine?: ISeriesApi<"Line">
  }>({})
  
  // 用ref去store latest atr同atrMultiplier，等click handler可以access到最新值
  const atrRef = useRef(atr)
  const atrMultiplierRef = useRef(atrMultiplier)
  const directionRef = useRef(direction)
  
  useEffect(() => {
    atrRef.current = atr
  }, [atr])
  
  useEffect(() => {
    atrMultiplierRef.current = atrMultiplier
  }, [atrMultiplier])
  
  useEffect(() => {
    directionRef.current = direction
  }, [direction])

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current || !data || data.length === 0) return

    // 如果已經有chart，就update data唔好re-zoom
    if (chartRef.current && candlestickSeriesRef.current) {
      const chartData = data.map(d => ({
        time: d.time as any,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      }))
      candlestickSeriesRef.current.setData(chartData)
      
      // Fit content to show all data
      chartRef.current.timeScale().fitContent()
      
      // Update MA lines
      const closes = data.map(d => d.close)
      
      // EMA20
      if (seriesRef.current.ema20) {
        try { chartRef.current.removeSeries(seriesRef.current.ema20) } catch (e) {}
      }
      if (data.length >= 20) {
        const ema20Data = calculateEMAData(closes, 20)
        const ema20Line = chartRef.current.addSeries(LineSeries, {
          color: '#ff9900',
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: true,
        })
        const ema20ChartData = data
          .map((d, i) => ({ time: d.time as any, value: ema20Data[i] }))
          .filter(d => d.value !== null && d.value !== undefined) as { time: any; value: number }[]
        if (ema20ChartData.length > 0) {
          ema20Line.setData(ema20ChartData)
          seriesRef.current.ema20 = ema20Line
        }
      }
      
      // SMA50
      if (seriesRef.current.sma50) {
        try { chartRef.current.removeSeries(seriesRef.current.sma50) } catch (e) {}
      }
      if (data.length >= 50) {
        const sma50Data = calculateSMAData(closes, 50)
        const sma50Line = chartRef.current.addSeries(LineSeries, {
          color: '#0088ff',
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: true,
        })
        const sma50ChartData = data
          .map((d, i) => ({ time: d.time as any, value: sma50Data[i] }))
          .filter(d => d.value !== null && d.value !== undefined) as { time: any; value: number }[]
        if (sma50ChartData.length > 0) {
          sma50Line.setData(sma50ChartData)
          seriesRef.current.sma50 = sma50Line
        }
      }
      
      // SMA200
      if (seriesRef.current.sma200) {
        try { chartRef.current.removeSeries(seriesRef.current.sma200) } catch (e) {}
      }
      if (data.length >= 200) {
        const sma200Data = calculateSMAData(closes, 200)
        const sma200Line = chartRef.current.addSeries(LineSeries, {
          color: '#aa00ff',
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: true,
        })
        const sma200ChartData = data
          .map((d, i) => ({ time: d.time as any, value: sma200Data[i] }))
          .filter(d => d.value !== null && d.value !== undefined) as { time: any; value: number }[]
        if (sma200ChartData.length > 0) {
          sma200Line.setData(sma200ChartData)
          seriesRef.current.sma200 = sma200Line
        }
      }
      
      return
    }

    // 第一次創建chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#1a1a1a' },
        textColor: '#888',
      },
      grid: {
        vertLines: { color: '#333' },
        horzLines: { color: '#333' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 300,
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      timeScale: {
        borderColor: '#555',
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: '#555',
      },
    })

    chartRef.current = chart

    // Candlestick series
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#00ff88',
      downColor: '#ff4d4d',
      borderUpColor: '#00ff88',
      borderDownColor: '#ff4d4d',
      wickUpColor: '#00ff88',
      wickDownColor: '#ff4d4d',
    })
    candlestickSeriesRef.current = candlestickSeries

    const chartData = data.map(d => ({
      time: d.time as any,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }))

    candlestickSeries.setData(chartData)

    // MA lines
    const closes = data.map(d => d.close)
    const ema20Data = calculateEMAData(closes, 20)
    const sma50Data = calculateSMAData(closes, 50)
    const sma200Data = calculateSMAData(closes, 200)

    // EMA20 (橙色)
    if (data.length >= 20) {
      const ema20Line = chart.addSeries(LineSeries, {
        color: '#ff9900',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: true,
      })
      const ema20ChartData = data
        .map((d, i) => ({ time: d.time as any, value: ema20Data[i] }))
        .filter(d => d.value !== null && d.value !== undefined) as { time: any; value: number }[]
      if (ema20ChartData.length > 0) {
        ema20Line.setData(ema20ChartData)
        seriesRef.current.ema20 = ema20Line
      }
    }

    // SMA50 (藍色)
    if (data.length >= 50) {
      const sma50Line = chart.addSeries(LineSeries, {
        color: '#0088ff',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: true,
      })
      const sma50ChartData = data
        .map((d, i) => ({ time: d.time as any, value: sma50Data[i] }))
        .filter(d => d.value !== null && d.value !== undefined) as { time: any; value: number }[]
      if (sma50ChartData.length > 0) {
        sma50Line.setData(sma50ChartData)
        seriesRef.current.sma50 = sma50Line
      }
    }

    // SMA200 (紫色)
    if (data.length >= 200) {
      const sma200Line = chart.addSeries(LineSeries, {
        color: '#aa00ff',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: true,
      })
      const sma200ChartData = data
        .map((d, i) => ({ time: d.time as any, value: sma200Data[i] }))
        .filter(d => d.value !== null && d.value !== undefined) as { time: any; value: number }[]
      if (sma200ChartData.length > 0) {
        sma200Line.setData(sma200ChartData)
        seriesRef.current.sma200 = sma200Line
      }
    }

    // Add click handler
    chart.subscribeClick((param: MouseEventParams) => {
      if (!param.point || !onEntryPriceChange || !candlestickSeriesRef.current) return;
      
      const priceAtClick = candlestickSeriesRef.current.coordinateToPrice(param.point.y);
      
      if (priceAtClick !== null && !isNaN(priceAtClick)) {
        onEntryPriceChange(priceAtClick);
        
        if (atrRef.current && onStopLossChange) {
          if (directionRef.current === 'LONG') {
            // Long: 止蝕喺下面
            const stopLossPrice = priceAtClick - (atrRef.current * atrMultiplierRef.current);
            onStopLossChange(stopLossPrice);
          } else {
            // Short: 止蝕喺上面
            const stopLossPrice = priceAtClick + (atrRef.current * atrMultiplierRef.current);
            onStopLossChange(stopLossPrice);
          }
        }
      }
    })

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      try {
        if (chartRef.current) {
          chartRef.current.remove()
          chartRef.current = null
          candlestickSeriesRef.current = null
        }
      } catch (e) {}
    }
  }, [data])

  // Update entry/stop lines
  useEffect(() => {
    if (!chartRef.current || !data || data.length === 0) return

    // Remove old entry line
    if (seriesRef.current.entryLine) {
      try { chartRef.current.removeSeries(seriesRef.current.entryLine) } catch (e) {}
      seriesRef.current.entryLine = undefined
    }
    // Remove old stop line
    if (seriesRef.current.stopLine) {
      try { chartRef.current.removeSeries(seriesRef.current.stopLine) } catch (e) {}
      seriesRef.current.stopLine = undefined
    }

    // Entry line color based on direction
    const entryColor = direction === 'SHORT' ? '#ff4d4d' : '#00ffff'
    
    if (entryPrice) {
      const entryLine = chartRef.current.addSeries(LineSeries, {
        color: entryColor,
        lineWidth: 2,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      entryLine.setData(data.map(d => ({ time: d.time as any, value: entryPrice })))
      seriesRef.current.entryLine = entryLine
    }

    if (stopLoss) {
      const stopLine = chartRef.current.addSeries(LineSeries, {
        color: '#ffaa00',
        lineWidth: 2,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      stopLine.setData(data.map(d => ({ time: d.time as any, value: stopLoss })))
      seriesRef.current.stopLine = stopLine
    }
  }, [entryPrice, stopLoss, direction, data])

  return <div ref={chartContainerRef} className="w-full h-[300px]" />
}