/**
 * Indicator calculation layer using lightweight-charts-indicators.
 * Each function takes our Candle[] (which matches oakscriptjs Bar[]) and returns
 * plot data in LWC-compatible format: { time, value }[]
 */
import {
  calculateEMA,
  calculateSMA,
  calculateBB,
  calculateRSI,
  calculateMACD,
  calculateATR,
  calculateStochastic,
} from 'lightweight-charts-indicators';
import type { Candle } from '../types/market';

// Our Candle type matches oakscriptjs Bar: { time, open, high, low, close, volume }

export interface IndicatorData {
  time: number;
  value: number;
  color?: string;
}

export function calcEMA(candles: Candle[], length: number): IndicatorData[] {
  const result = calculateEMA(candles, { length, src: 'close', offset: 0, maType: 'None', maLength: 14, bbMult: 2 });
  return (result.plots['EMA'] ?? []).filter((d) => d.value != null) as IndicatorData[];
}

export function calcSMA(candles: Candle[], len: number): IndicatorData[] {
  const result = calculateSMA(candles, { len, src: 'close', offset: 0, maType: 'None', maLength: 14, bbMult: 2 });
  return (result.plots['SMA'] ?? []).filter((d) => d.value != null) as IndicatorData[];
}

export interface BBData {
  basis: IndicatorData[];
  upper: IndicatorData[];
  lower: IndicatorData[];
}

export function calcBB(candles: Candle[], length = 20, mult = 2): BBData {
  const result = calculateBB(candles, { length, src: 'close', mult, maType: 'SMA', offset: 0 });
  return {
    basis: (result.plots['Basis'] ?? []).filter((d) => d.value != null) as IndicatorData[],
    upper: (result.plots['Upper'] ?? []).filter((d) => d.value != null) as IndicatorData[],
    lower: (result.plots['Lower'] ?? []).filter((d) => d.value != null) as IndicatorData[],
  };
}

export function calcRSI(candles: Candle[], length = 14): IndicatorData[] {
  const result = calculateRSI(candles, { length, src: 'close', calculateDivergence: false, maType: 'None', maLength: 14, bbMult: 2 });
  return (result.plots['RSI'] ?? []).filter((d) => d.value != null) as IndicatorData[];
}

export interface MACDData {
  macd: IndicatorData[];
  signal: IndicatorData[];
  histogram: IndicatorData[];
}

export function calcMACD(candles: Candle[], fast = 12, slow = 26, signal = 9): MACDData {
  const result = calculateMACD(candles, { fastLength: fast, slowLength: slow, signalSmoothing: signal, src: 'close', oscillatorMA: 'EMA', signalMA: 'EMA' } as any);
  return {
    macd: (result.plots['MACD'] ?? result.plots['Histogram'] ?? []).filter((d) => d.value != null) as IndicatorData[],
    signal: (result.plots['Signal'] ?? []).filter((d) => d.value != null) as IndicatorData[],
    histogram: (result.plots['Histogram'] ?? result.plots['MACD'] ?? []).filter((d) => d.value != null) as IndicatorData[],
  };
}

export function calcATR(candles: Candle[], length = 14): IndicatorData[] {
  const result = calculateATR(candles, { length, smoothing: 'RMA' } as any);
  return (result.plots['ATR'] ?? []).filter((d) => d.value != null) as IndicatorData[];
}

export function calcStochastic(candles: Candle[], kPeriod = 14, dPeriod = 3): { k: IndicatorData[]; d: IndicatorData[] } {
  const result = calculateStochastic(candles, { kPeriod, dPeriod, kSmoothing: 1 } as any);
  return {
    k: (result.plots['%K'] ?? []).filter((d) => d.value != null) as IndicatorData[],
    d: (result.plots['%D'] ?? []).filter((d) => d.value != null) as IndicatorData[],
  };
}

/**
 * Calculate VWAP from candle data.
 */
export function calcVWAP(candles: Candle[]): IndicatorData[] {
  if (candles.length === 0) return [];

  let cumTPV = 0;
  let cumVol = 0;
  const result: IndicatorData[] = [];

  for (const bar of candles) {
    const tp = (bar.high + bar.low + bar.close) / 3;
    cumTPV += tp * bar.volume;
    cumVol += bar.volume;
    if (cumVol > 0) {
      result.push({ time: bar.time, value: cumTPV / cumVol });
    }
  }

  return result;
}

/**
 * Calculate VWAP with standard deviation bands (±1σ, ±2σ).
 * Variance = cumulative(volume × (price - VWAP)²) / cumulative(volume)
 * Band = VWAP ± multiplier × √variance
 */
export function calcVWAPBands(candles: Candle[]): {
  vwap: IndicatorData[];
  upper1: IndicatorData[];
  lower1: IndicatorData[];
  upper2: IndicatorData[];
  lower2: IndicatorData[];
} {
  const vwap: IndicatorData[] = [];
  const upper1: IndicatorData[] = [];
  const lower1: IndicatorData[] = [];
  const upper2: IndicatorData[] = [];
  const lower2: IndicatorData[] = [];

  if (candles.length === 0) return { vwap, upper1, lower1, upper2, lower2 };

  let cumTPV = 0;
  let cumVol = 0;
  let cumTPV2 = 0; // cumulative(volume × tp²) for variance

  for (const bar of candles) {
    const tp = (bar.high + bar.low + bar.close) / 3;
    cumTPV += tp * bar.volume;
    cumTPV2 += tp * tp * bar.volume;
    cumVol += bar.volume;

    if (cumVol > 0) {
      const v = cumTPV / cumVol;
      const variance = (cumTPV2 / cumVol) - (v * v);
      const sd = Math.sqrt(Math.max(0, variance));

      vwap.push({ time: bar.time, value: v });
      upper1.push({ time: bar.time, value: v + sd });
      lower1.push({ time: bar.time, value: v - sd });
      upper2.push({ time: bar.time, value: v + 2 * sd });
      lower2.push({ time: bar.time, value: v - 2 * sd });
    }
  }

  return { vwap, upper1, lower1, upper2, lower2 };
}

/**
 * Get previous day's final VWAP value as a horizontal line.
 * Finds the last bar from a different day and returns that day's closing VWAP.
 */
export function calcPrevDayVWAP(candles: Candle[]): { value: number; startTime: number } | null {
  if (candles.length < 20) return null;

  // Find today's date boundary
  const lastBar = candles[candles.length - 1];
  const lastDate = new Date(lastBar.time * 1000).toLocaleDateString('en-US', { timeZone: 'America/New_York' });

  // Walk backwards to find previous day's bars
  let prevDayBars: Candle[] = [];
  let prevDate = '';
  for (let i = candles.length - 1; i >= 0; i--) {
    const d = new Date(candles[i].time * 1000).toLocaleDateString('en-US', { timeZone: 'America/New_York' });
    if (d !== lastDate) {
      if (!prevDate) prevDate = d;
      if (d === prevDate) {
        prevDayBars.unshift(candles[i]);
      } else {
        break; // Went past prev day
      }
    }
  }

  if (prevDayBars.length === 0) return null;

  // Compute prev day's final VWAP
  let cumTPV = 0;
  let cumVol = 0;
  for (const bar of prevDayBars) {
    const tp = (bar.high + bar.low + bar.close) / 3;
    cumTPV += tp * bar.volume;
    cumVol += bar.volume;
  }

  if (cumVol <= 0) return null;

  // Return the value and today's first bar time for horizontal line start
  const todayStart = candles.find(c => {
    const d = new Date(c.time * 1000).toLocaleDateString('en-US', { timeZone: 'America/New_York' });
    return d === lastDate;
  });

  return {
    value: cumTPV / cumVol,
    startTime: todayStart?.time || candles[0].time,
  };
}
