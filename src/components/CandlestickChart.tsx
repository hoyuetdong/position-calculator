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
  onEntryPriceChange?: (price: number, fromChartComponent?: boolean) => void  // 支持第二個參數
  onStopLossChange?: (price: number) => void
  onResetStopLoss?: () => void  // 新增：當重新設定 buy point 時重置止蝕位
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
  onResetStopLoss
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
  const entryPriceRef = useRef(entryPrice)
  const onStopLossChangeRef = useRef(onStopLossChange)
  const onResetStopLossRef = useRef<(() => void) | undefined>(undefined)
  const lastEntryPriceRef = useRef<number | undefined>(undefined)
  
  // 追蹤手動拖動狀態（用於自動重置）
  const manualStopLossOffsetRef = useRef<number | null>(null)
  
  // 止蝕線拖曳狀態
  const dragStateRef = useRef<{
    isDragging: boolean
    dragLine: 'stopLine' | null
  }>({ isDragging: false, dragLine: null })
  
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
    entryPriceRef.current = entryPrice
  }, [entryPrice])

  useEffect(() => {
    onStopLossChangeRef.current = onStopLossChange
  }, [onStopLossChange])

  useEffect(() => {
    onResetStopLossRef.current = onResetStopLoss
  }, [onResetStopLoss])

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

    // 用 stopLine.data() 獲取止蝕價（止蝕線係水平線，所有點值都一樣）
    const getStopLossPrice = (): number | undefined => {
      const data = seriesRef.current.stopLine?.data();
      if (data && data.length > 0) {
        const lastPoint = data[data.length - 1];
        return (lastPoint as { value?: number })?.value ?? undefined;
      }
      return undefined;
    }

    chart.subscribeClick((param: MouseEventParams) => {
      if (!param.point || !onEntryPriceChange || !candlestickSeriesRef.current) return;
      // 如果係拖緊止蝕線，唔處理 click
      if (dragStateRef.current.isDragging && dragStateRef.current.dragLine === 'stopLine') return;
      
      const priceAtClick = candlestickSeriesRef.current.coordinateToPrice(param.point.y);
      
      if (priceAtClick !== null && !isNaN(priceAtClick)) {
        onEntryPriceChange(priceAtClick, true);
      }
    })

    const container = chartContainerRef.current;

    const handleMouseDown = (e: MouseEvent) => {
      if (!candlestickSeriesRef.current || !chartRef.current) return;
      
      const rect = container.getBoundingClientRect();
      const y = e.clientY - rect.top;
      
      // 先檢查止蝕線拖曳
      if (seriesRef.current.stopLine && stopLossRef.current) {
        const stopYCoordinate = seriesRef.current.stopLine.priceToCoordinate(stopLossRef.current);
        if (stopYCoordinate !== null && Math.abs(y - stopYCoordinate) < 15) {
          isDraggingRef.current = true;
          dragLineRef.current = 'stopLine';
          container.style.cursor = 'ns-resize';
          
          // 禁用手勢，防止觸發整個圖表的垂直位移
          chartRef.current.applyOptions({
            handleScroll: {
              mouseWheel: false,
              pressedMouseMove: false,
              vertTouchDrag: false
            },
            handleScale: {
              axisPressedMouseMove: false,
              mouseWheel: false,
              pinch: false
            }
          });
          
          e.preventDefault();
          e.stopPropagation();
          return;
        }
      }
    };

    const handleMouseMove = (e: MouseEvent) => {
      // 呢度唔用 e.stopPropagation()，因為 lightweight-charts 需要接收 mouse events 嚟處理 crosshair
      // 但係我哋需要確保止蝕線拖動時坐標計算係正確嘅

      const rect = container.getBoundingClientRect();
      const y = e.clientY - rect.top;

      // 如果係拖緊止蝕線，直接用 actual 鼠標 Y 座標更新
      if (isDraggingRef.current && dragLineRef.current === 'stopLine' && seriesRef.current.stopLine) {
        const newPrice = seriesRef.current.stopLine.coordinateToPrice(y);
        if (newPrice !== null && !isNaN(newPrice) && onStopLossChangeRef.current) {
          onStopLossChangeRef.current(newPrice);
        }
        return;
      }

      // 顯示 cursor 變化 - 根據當前顯示的價格範圍動態計算感應範圍
      // 重要：用 candlestickSeries 而唔用 stopLine，因為 zoom 之後 stopLine.priceToCoordinate 可能唔準確
      if (stopLoss && candlestickSeriesRef.current) {
        const stopY = candlestickSeriesRef.current.priceToCoordinate(stopLoss);
        if (stopY !== null) {
          const chartHeight = rect.height;
          const hitThreshold = Math.max(20, Math.min(50, chartHeight / 8));

          if (Math.abs(y - stopY) < hitThreshold) {
            container.style.cursor = 'ns-resize';
          } else {
            container.style.cursor = 'crosshair';
          }
        } else {
          container.style.cursor = 'crosshair';
        }
      } else {
        container.style.cursor = 'crosshair';
      }
    };

    const handleMouseUp = () => {
      // 記低今次係咪有拖過止蝕線
      const wasDragging = isDraggingRef.current && dragLineRef.current === 'stopLine';
      wasDraggingRef.current = wasDragging;
      
      if (wasDragging && atrRef.current && entryPriceRef.current) {
        const currentStopLoss = stopLossRef.current;
        if (currentStopLoss && atrRef.current > 0) {
          // 計算並記錄偏移量（作為獨立的 overlay 狀態）
          let offset: number;
          if (directionRef.current === 'LONG') {
            offset = entryPriceRef.current - currentStopLoss;
          } else {
            offset = currentStopLoss - entryPriceRef.current;
          }
          manualStopLossOffsetRef.current = offset;
        }
      }
      
      // 恢復圖表手勢
      if (chartRef.current) {
        chartRef.current.applyOptions({
          handleScroll: {
            mouseWheel: true,
            pressedMouseMove: true,
            vertTouchDrag: true
          },
          handleScale: {
            axisPressedMouseMove: true,
            mouseWheel: true,
            pinch: true
          }
        });
      }
      
      isDraggingRef.current = false;
      dragLineRef.current = null;
      container.style.cursor = 'crosshair';
    };

    // 使用 window 監聽 mouseup，防止黏手問題
    window.addEventListener('mouseup', handleMouseUp);
    
    container.addEventListener('mousedown', handleMouseDown);
    container.addEventListener('mousemove', handleMouseMove);
    // 移除 container 的 mouseup/mouseleave，確保拖動時跟手
    // container.addEventListener('mouseup', handleMouseUp);
    // container.addEventListener('mouseleave', handleMouseUp);

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('mouseup', handleMouseUp);
      container.removeEventListener('mousedown', handleMouseDown);
      container.removeEventListener('mousemove', handleMouseMove);
      // container.removeEventListener('mouseup', handleMouseUp);
      // container.removeEventListener('mouseleave', handleMouseUp);
      try {
        if (chartRef.current) {
          chartRef.current.remove()
          chartRef.current = null
          candlestickSeriesRef.current = null
        }
      } catch (e) {}
    }
  }, [data])

  // 當 entryPrice prop 改變時，清除手動拖動狀態（自動重置邏輯）
  useEffect(() => {
    manualStopLossOffsetRef.current = null;
  }, [entryPrice])

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

  // 微調止蝕價（每次 1%）
  const adjustStopLoss = (deltaPercent: number) => {
    if (!stopLoss || !onStopLossChange) return;
    const newPrice = stopLoss * (1 + deltaPercent / 100);
    onStopLossChange(newPrice);
  };

  return (
    <div className="w-full h-[300px] relative">
      <div ref={chartContainerRef} className="w-full h-full" />
    </div>
  )
}