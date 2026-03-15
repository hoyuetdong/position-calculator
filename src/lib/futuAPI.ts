/**
 * Futu OpenD API Client
 * 連接富途 OpenD 獲取股票報價同歷史數據
 */

import protoRoot from 'futu-api/proto.js';

const QotMarket = {
  QotMarket_Unknown: 0,
  QotMarket_HK_Security: 1,
  QotMarket_HK_Future: 2,
  QotMarket_US_Security: 11,
  QotMarket_CNSH_Security: 21,
  QotMarket_CNSZ_Security: 22,
};

const KLineType = {
  KLineType_Unknown: 0,
  KLineType_1Min: 1,
  KLineType_5Min: 2,
  KLineType_15Min: 3,
  KLineType_30Min: 4,
  KLineType_1Hour: 5,
  KLineType_1Day: 6,
  KLineType_1Week: 7,
  KLineType_1Month: 8,
};

// Futu OpenD 配置
const FUTU_CONFIG = {
  ip: process.env.FUTU_HOST || '127.0.0.1',
  port: parseInt(process.env.FUTU_WS_PORT || '33333', 10),  // WebSocket port (default 33333)
  apiPort: parseInt(process.env.FUTU_PORT || '11111', 10),   // API port (11111)
};

let futuInstance: any = null;
let isConnected = false;
let loginResolve: ((value: void) => void) | null = null;
let loginReject: ((reason?: any) => void) | null = null;

/**
 * 港股代號轉換
 * 00700 -> { market: QotMarket_HK_Security, code: '00700' }
 * 700 -> { market: QotMarket_HK_Security, code: '00700' }
 * AAPL -> { market: QotMarket_US_Security, code: 'AAPL' }
 */
function toFutuSecurity(symbol: string): { market: number; code: string } {
  const upper = symbol.toUpperCase().trim()
  
  // 美股 (e.g., AAPL, TSLA, NVDA)
  if (/^[A-Z]{1,5}$/.test(upper)) {
    return {
      market: QotMarket.QotMarket_US_Security,
      code: upper,
    }
  }
  
  // 移除 .HK 後綴
  const withoutHK = upper.replace(/\.HK$/i, '')
  
  let code = withoutHK
  // 如果係4位數字，前面加0變5位 (港股)
  if (/^\d{4}$/.test(withoutHK)) {
    code = '0' + withoutHK
  }
  
  return {
    market: QotMarket.QotMarket_HK_Security,
    code,
  };
}

/**
 * 初始化 Futu OpenD 連接
 */
export async function initFutuAPI(): Promise<void> {
  if (futuInstance && isConnected) {
    return;
  }

  return new Promise(async (resolve, reject) => {
    loginResolve = resolve;
    loginReject = reject;
    
    try {
      const Futu = (await import('futu-api')).default;
      console.log('[FutuAPI] Futu class loaded');
      
      futuInstance = new Futu();
      console.log('[FutuAPI] Instance created');
      
      // Override start method to add logging
      const originalStart = futuInstance.start;
      futuInstance.start = function(ip: string, port: number, ssl: boolean, key: string) {
        console.log('[FutuAPI] start() called with:', ip, port, ssl);
        
        // Call original
        originalStart.call(this, ip, port, ssl, key);
        
        // Try to hook into websock events after a short delay
        setTimeout(() => {
          if (this.websock) {
            console.log('[FutuAPI] websock readyState:', this.websock.readyState);
            this.websock.onopen = () => {
              console.log('[FutuAPI] Websocket onopen fired!');
            };
            this.websock.onerror = (e: any) => {
              console.log('[FutuAPI] Websocket onerror:', e);
            };
            this.websock.onclose = (e: any) => {
              console.log('[FutuAPI] Websocket onclose:', e);
            };
          } else {
            console.log('[FutuAPI] websock still not created after timeout');
          }
        }, 2000);
      };
      
      // 設定登錄 callback
      futuInstance.onlogin = (ret: any, msg: any) => {
        console.log('[FutuAPI] Login callback triggered:', ret, typeof msg);
        // ret 可以係 boolean true 或者 number 0
        if (ret === 0 || ret === true) {
          console.log('[FutuAPI] Connected to Futu OpenD');
          isConnected = true;
          if (loginResolve) loginResolve();
        } else {
          console.error('[FutuAPI] Login failed:', msg);
          if (loginReject) loginReject(new Error(`登入失敗: ${msg}`));
        }
      };

      // Add error handler
      futuInstance.onerror = (err: any) => {
        console.error('[FutuAPI] Error:', err);
      };

      // 啟動連接 (localhost 唔需要 SSL)
      console.log('[FutuAPI] Calling start with:', FUTU_CONFIG.ip, FUTU_CONFIG.port, false);
      futuInstance.start(FUTU_CONFIG.ip, FUTU_CONFIG.port, false, null);
      console.log('[FutuAPI] Start called');
      
      // 設定連接 timeout (30秒)
      setTimeout(() => {
        if (!isConnected) {
          console.error('[FutuAPI] Connection timeout - was never connected');
          if (loginReject) loginReject(new Error('Futu OpenD 連接超時'));
        }
      }, 30000);
      
    } catch (err) {
      console.error('[FutuAPI] Init error:', err);
      reject(err);
    }
  });
}

/**
 * 獲取股票報價
 */
export async function getQuote(symbol: string): Promise<{
  symbol: string;
  name?: string;
  lastPrice: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  turnover: number;
  change: number;
  changePercent: number;
  high52w: number;
  low52w: number;
}> {
  await initFutuAPI();

  const security = toFutuSecurity(symbol);

  try {
    const response: any = await futuInstance.GetSecuritySnapshot({
      c2s: {
        securityList: [security],
      }
    });

    const snapshot = response.s2c.snapshotList[0];
    const basic = snapshot.basic || snapshot;

    const lastPrice = basic.curPrice || basic.price || 0;
    const open = basic.openPrice || basic.open || 0;
    const high = basic.highPrice || basic.high || 0;
    const low = basic.lowPrice || basic.low || 0;
    // Futu 返回既 volume 可能係 Long object，需要轉換
    const volume = (basic.volume?.low || basic.volume?.toNumber?.() || basic.volume || 0);
    const turnover = (basic.turnover?.low || basic.turnover?.toNumber?.() || basic.turnover || 0);
    
    // change 同 changePercent 要自己計，或者用 changeRate (if exists)
    const lastClosePrice = basic.lastClosePrice || basic.close || 0;
    const change = lastClosePrice > 0 ? lastPrice - lastClosePrice : 0;
    const changePercent = lastClosePrice > 0 ? (change / lastClosePrice) * 100 : 0;
    
    const high52w = basic.highest52WeeksPrice || basic.high52w || 0;
    const low52w = basic.lowest52WeeksPrice || basic.low52w || 0;

    return {
      symbol: security.market === QotMarket.QotMarket_US_Security 
        ? security.code 
        : `${security.code}.HK`,
      name: basic.name || security.code,
      lastPrice,
      open,
      high,
      low,
      volume,
      turnover,
      change,
      changePercent,
      high52w,
      low52w,
    };
  } catch (err: any) {
    console.error('[FutuAPI] getQuote error:', err);
    // 打印詳細既 retMsg
    if (err.retMsg) {
      console.error('[FutuAPI] Error details:', err.retMsg);
    }
    throw err;
  }
}

/**
 * 獲取歷史K線數據
 */
export async function getHistoricalKLines(
  symbol: string,
  days: number = 30
): Promise<Array<{
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}>> {
  await initFutuAPI();

  const security = toFutuSecurity(symbol);

  // 計算時間範圍
  const endTime = new Date();
  const startTime = new Date();
  startTime.setDate(startTime.getDate() - days);

  const formatTime = (d: Date) => {
    return d.toISOString().replace('T', ' ').substring(0, 19);
  };

  try {
    const response: any = await futuInstance.RequestHistoryKL({
      c2s: {
        security,
        rehabType: 1,  // 前復權
        klType: 6,     // 日K
        beginTime: formatTime(startTime),
        endTime: formatTime(endTime),
        maxAckKLNum: days,
      }
    });

    // console.log('[FutuAPI] KLines response:', JSON.stringify(response, null, 2));

    const klineList = response.s2c.klList;
    
    if (!klineList || klineList.length === 0) {
      return [];
    }

    // 轉換為標準格式，按時間升序排列
    // Futu K-line 返回既字段名同其他系統唔同
    const toNumber = (v: any) => {
      if (v === null || v === undefined) return 0;
      if (typeof v === 'number') return v;
      if (typeof v === 'string') return parseFloat(v) || 0;
      if (typeof v === 'object' && v.low !== undefined) return v.low;
      if (typeof v === 'object' && v.toNumber) return v.toNumber();
      return Number(v) || 0;
    };

    const klines = klineList
      .map((k: any) => ({
        // timestamp 係 unix timestamp (秒)
        time: k.timestamp || 0,
        open: toNumber(k.openPrice || k.open),
        high: toNumber(k.highPrice || k.high),
        low: toNumber(k.lowPrice || k.low),
        close: toNumber(k.closePrice || k.close),
        volume: toNumber(k.volume),
      }))
      .sort((a: any, b: any) => a.time - b.time);

    return klines;
  } catch (err) {
    console.error('[FutuAPI] getHistoricalKLines error:', err);
    throw err;
  }
}

/**
 * 計算 SMA
 */
function calculateSMA(data: number[], period: number): number | null {
  if (data.length < period) return null;
  const slice = data.slice(-period);
  return slice.reduce((a, b) => a + b, 0) / period;
}

/**
 * 計算 EMA
 */
function calculateEMA(data: number[], period: number): number | null {
  if (data.length < period) return null;

  const initialSlice = data.slice(0, period);
  let ema = initialSlice.reduce((a, b) => a + b, 0) / period;

  const multiplier = 2 / (period + 1);

  for (let i = period; i < data.length; i++) {
    ema = (data[i] - ema) * multiplier + ema;
  }
  return ema;
}

/**
 * 獲取報價連埋移動平均線
 */
export async function getQuoteWithMA(symbol: string): Promise<{
  symbol: string;
  name?: string;
  lastPrice: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  turnover: number;
  change: number;
  changePercent: number;
  high52w: number;
  low52w: number;
  ema10: number | null;
  ema20: number | null;
  sma50: number | null;
  sma200: number | null;
}> {
  const quote = await getQuote(symbol);

  let ema10: number | null = null;
  let ema20: number | null = null;
  let sma50: number | null = null;
  let sma200: number | null = null;

  try {
    const klines = await getHistoricalKLines(symbol, 2000);

    if (klines.length > 0) {
      const closes = klines.map((k) => k.close).filter((c) => c > 0);
      ema10 = calculateEMA(closes, 10);
      ema20 = calculateEMA(closes, 20);
      sma50 = calculateSMA(closes, 50);
      sma200 = calculateSMA(closes, 200);
    }
  } catch (err) {
    console.error('[FutuAPI] MA calculation error:', err);
  }

  return {
    ...quote,
    ema10,
    ema20,
    sma50,
    sma200,
  };
}

/**
 * 關閉連接
 */
export async function closeFutuAPI(): Promise<void> {
  if (futuInstance) {
    futuInstance.close();
    futuInstance = null;
    isConnected = false;
  }
}

/**
 * 檢查連接狀態
 */
export function isFutuConnected(): boolean {
  return isConnected;
}