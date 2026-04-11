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
  atrPeriod?: number
  onEntryPriceChange?: (price: number) => void  // 改名
  onStopLossChange?: (price: number) => void
  onAtrMultiplierChange?: (multiplier: number) => void  // 拖曳止蝕線後自動計算新 ATR 倍數
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
  direction,
  entryPrice,
  stopLoss,
  atr, 
  atrMultiplier = 1.5,
  atrPeriod = 14,
  onEntryPriceChange, 
  onStopLossChange,
  onAtrMultiplierChange
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
  const atrPeriodRef = useRef(atrPeriod)
  const directionRef = useRef(direction)
  const onAtrMultiplierChangeRef = useRef(onAtrMultiplierChange)
  const entryPriceRef = useRef(entryPrice)
  const onStopLossChangeRef = useRef(onStopLossChange)
  
  // 拖曳狀態
  const isDraggingRef = useRef(false)
  const dragLineRef = useRef<'stopLine' | null>(null)
  const stopLossRef = useRef(stopLoss)
  
  useEffect(() => {
    atrRef.current = atr
  }, [atr])
  
  useEffect(() => {
    atrMultiplierRef.current = atrMultiplier
  }, [atrMultiplier])
  
  useEffect(() => {
    directionRef.current = direction
  }, [direction])

  useEffect(() => {
    atrPeriodRef.current = atrPeriod
  }, [atrPeriod])

  useEffect(() => {
    onAtrMultiplierChangeRef.current = onAtrMultiplierChange
  }, [onAtrMultiplierChange])

  useEffect(() => {
    entryPriceRef.current = entryPrice
  }, [entryPrice])

  useEffect(() => {
    onStopLossChangeRef.current = onStopLossChange
  }, [onStopLossChange])

  useEffect(() => {
    stopLossRef.current = stopLoss
  }, [stopLoss])

  // Initialize chart 同 setup event listeners（只运行一次）
  useEffect(() => {
    if (!chartContainerRef.current || !data || data.length === 0) return

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

    const closes = data.map(d => d.close)
    const ema20Data = calculateEMAData(closes, 20)
    const sma50Data = calculateSMAData(closes, 50)
    const sma200Data = calculateSMAData(closes, 200)

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

    chart.subscribeClick((param: MouseEventParams) => {
      if (!param.point || !onEntryPriceChange || !candlestickSeriesRef.current) return;
      
      const priceAtClick = candlestickSeriesRef.current.coordinateToPrice(param.point.y);
      
      if (priceAtClick !== null && !isNaN(priceAtClick)) {
        onEntryPriceChange(priceAtClick);
        
        if (atrRef.current && onStopLossChangeRef.current) {
          if (directionRef.current === 'LONG') {
            const stopLossPrice = priceAtClick - (atrRef.current * atrMultiplierRef.current);
            onStopLossChangeRef.current(stopLossPrice);
          } else {
            const stopLossPrice = priceAtClick + (atrRef.current * atrMultiplierRef.current);
            onStopLossChangeRef.current(stopLossPrice);
          }
        }
      }
    })

    const container = chartContainerRef.current;

    const handleMouseDown = (e: MouseEvent) => {
      if (!candlestickSeriesRef.current) return;
      
      const rect = container.getBoundingClientRect();
      const y = e.clientY - rect.top;
      
      if (seriesRef.current.stopLine && stopLossRef.current) {
        const stopYCoordinate = seriesRef.current.stopLine.priceToCoordinate(stopLossRef.current);
        if (stopYCoordinate !== null && Math.abs(y - stopYCoordinate) < 10) {
          isDraggingRef.current = true;
          dragLineRef.current = 'stopLine';
          container.style.cursor = 'ns-resize';
          e.preventDefault();
        }
      }
    };

    const handleMouseMove = (e: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      const y = e.clientY - rect.top;
      
      if (isDraggingRef.current && candlestickSeriesRef.current) {
        const newPrice = candlestickSeriesRef.current.coordinateToPrice(y);
        if (newPrice !== null && !isNaN(newPrice) && onStopLossChangeRef.current) {
          onStopLossChangeRef.current(newPrice);
        }
        return;
      }
      
      if (seriesRef.current.stopLine && stopLossRef.current) {
        const stopY = seriesRef.current.stopLine.priceToCoordinate(stopLossRef.current);
        if (stopY !== null && Math.abs(y - stopY) < 10) {
          container.style.cursor = 'ns-resize';
        } else {
          container.style.cursor = 'crosshair';
        }
      } else {
        container.style.cursor = 'crosshair';
      }
    };

    const handleMouseUp = () => {
      if (isDraggingRef.current && dragLineRef.current === 'stopLine' && atrRef.current && entryPriceRef.current && onAtrMultiplierChangeRef.current) {
        const currentStopLoss = stopLossRef.current;
        if (currentStopLoss && atrRef.current > 0) {
          let newMultiplier: number;
          if (directionRef.current === 'LONG') {
            newMultiplier = (entryPriceRef.current - currentStopLoss) / atrRef.current;
          } else {
            newMultiplier = (currentStopLoss - entryPriceRef.current) / atrRef.current;
          }
          newMultiplier = Math.round(newMultiplier * 10) / 10;
          newMultiplier = Math.max(0.1, Math.min(10, newMultiplier));
          onAtrMultiplierChangeRef.current(newMultiplier);
        }
      }
      isDraggingRef.current = false;
      dragLineRef.current = null;
      container.style.cursor = 'crosshair';
    };

    container.addEventListener('mousedown', handleMouseDown);
    container.addEventListener('mousemove', handleMouseMove);
    container.addEventListener('mouseup', handleMouseUp);
    container.addEventListener('mouseleave', handleMouseUp);

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      container.removeEventListener('mousedown', handleMouseDown);
      container.removeEventListener('mousemove', handleMouseMove);
      container.removeEventListener('mouseup', handleMouseUp);
      container.removeEventListener('mouseleave', handleMouseUp);
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
    if (!chartRef.current || !candlestickSeriesRef.current || !data || data.length === 0) return

    if (seriesRef.current.entryLine) {
      try { chartRef.current.removeSeries(seriesRef.current.entryLine) } catch (e) {}
      seriesRef.current.entryLine = undefined
    }

    if (seriesRef.current.stopLine) {
      try { chartRef.current.removeSeries(seriesRef.current.stopLine) } catch (e) {}
      seriesRef.current.stopLine = undefined
    }

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
        lineWidth: 3,
        lineStyle: 0,
        priceLineVisible: false,
        lastValueVisible: true,
        title: '止蝕',
      })
      stopLine.setData(data.map(d => ({ time: d.time as any, value: stopLoss })))
      seriesRef.current.stopLine = stopLine
    }
  }, [entryPrice, stopLoss, direction, data])

  return <div ref={chartContainerRef} className="w-full h-[300px]" />
}