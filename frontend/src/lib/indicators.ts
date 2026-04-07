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
 * Not in the indicators library, but straightforward cumulative calculation.
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
