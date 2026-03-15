/**
 * Technical Indicators Utility Functions
 * 技術指標計算模組
 */

/**
 * 計算 SMA (Simple Moving Average)
 */
export function calculateSMA(data: number[], period: number): number | null {
  if (data.length < period) return null
  const slice = data.slice(-period)
  return slice.reduce((a, b) => a + b, 0) / period
}

/**
 * 計算 EMA (Exponential Moving Average)
 */
export function calculateEMA(data: number[], period: number): number | null {
  if (data.length < period) return null

  const initialSlice = data.slice(0, period)
  let ema = initialSlice.reduce((a, b) => a + b, 0) / period

  const multiplier = 2 / (period + 1)

  for (let i = period; i < data.length; i++) {
    ema = (data[i] - ema) * multiplier + ema
  }
  return ema
}

/**
 * 計算 ATR (Average True Range)
 */
export function calculateATR(highs: number[], lows: number[], closes: number[], period: number = 14): number | null {
  if (highs.length < period + 1 || lows.length < period + 1 || closes.length < period + 1) {
    return null
  }

  const trValues: number[] = []

  for (let i = 1; i < closes.length; i++) {
    const high = highs[i]
    const low = lows[i]
    const close = closes[i - 1]

    const tr = Math.max(
      high - low,
      Math.abs(high - close),
      Math.abs(low - close)
    )
    trValues.push(tr)
  }

  if (trValues.length < period) {
    return null
  }

  const lastTRValues = trValues.slice(-period)
  return lastTRValues.reduce((a, b) => a + b, 0) / period
}

/**
 * 從 K 線數據計算移動平均線
 */
export function calculateMAFromKLines(
  klines: Array<{ high: number; low: number; close: number }>,
  period: number
): number | null {
  if (klines.length < period) return null

  const closes = klines.map(k => parseFloat(String(k.close))).filter(c => c > 0)
  return calculateSMA(closes, period)
}

/**
 * 從 K 線數據計算 EMA
 */
export function calculateEMAFromKLines(
  klines: Array<{ close: number }>,
  period: number
): number | null {
  if (klines.length < period) return null

  const closes = klines.map(k => parseFloat(String(k.close))).filter(c => c > 0)
  return calculateEMA(closes, period)
}

/**
 * 從 K 線數據計算 ATR
 */
export function calculateATRFromKLines(
  klines: Array<{ high: number; low: number; close: number }>,
  period: number = 14
): number | null {
  if (klines.length < period + 1) return null

  const highs = klines.map(k => parseFloat(String(k.high)))
  const lows = klines.map(k => parseFloat(String(k.low)))
  const closes = klines.map(k => parseFloat(String(k.close)))

  return calculateATR(highs, lows, closes, period)
}
