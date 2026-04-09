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

/**
 * Bollinger Bands (Robinhood variant) — uses Typical Price (hlc3) as source
 * instead of Close. TP = (High + Low + Close) / 3, which smooths out wicks.
 */
export function calcBB_RH(candles: Candle[], length = 20, mult = 2): BBData {
  const result = calculateBB(candles, { length, src: 'hlc3', mult, maType: 'SMA', offset: 0 });
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
 * Auto-Anchored VWAP (AAVWAP) with ±1σ, ±2σ, ±3σ bands.
 *
 * Matches Robinhood Legend config:
 * - Starting point: Highest High (auto-detected pivot)
 * - Starting point length: configurable (default 1000 bars lookback for anchor)
 * - Price: Close (TP = HLC/3)
 * - Bands: Standard deviation, multipliers 1, 2, 3
 *
 * Detects the highest high in the lookback window as the anchor point.
 * VWAP + bands accumulate from that anchor forward.
 * Resets at each trading day if anchor is in a previous day.
 */
export function calcAAVWAP(candles: Candle[], lookback = 1000): {
  vwap: IndicatorData[];
  upper1: IndicatorData[];
  lower1: IndicatorData[];
  upper2: IndicatorData[];
  lower2: IndicatorData[];
  upper3: IndicatorData[];
  lower3: IndicatorData[];
} {
  const empty = { vwap: [] as IndicatorData[], upper1: [] as IndicatorData[], lower1: [] as IndicatorData[], upper2: [] as IndicatorData[], lower2: [] as IndicatorData[], upper3: [] as IndicatorData[], lower3: [] as IndicatorData[] };
  if (candles.length === 0) return empty;

  // Find highest high in lookback window as anchor
  const start = Math.max(0, candles.length - lookback);
  let anchorIdx = start;
  let anchorHigh = candles[start].high;
  for (let i = start + 1; i < candles.length; i++) {
    if (candles[i].high > anchorHigh) {
      anchorHigh = candles[i].high;
      anchorIdx = i;
    }
  }

  const vwap: IndicatorData[] = [];
  const upper1: IndicatorData[] = [];
  const lower1: IndicatorData[] = [];
  const upper2: IndicatorData[] = [];
  const lower2: IndicatorData[] = [];
  const upper3: IndicatorData[] = [];
  const lower3: IndicatorData[] = [];

  let cumTPV = 0;
  let cumVol = 0;
  let cumTPV2 = 0;

  for (let i = anchorIdx; i < candles.length; i++) {
    const bar = candles[i];

    if (bar.volume <= 0) {
      if (vwap.length > 0) {
        const last = vwap.length - 1;
        vwap.push({ time: bar.time, value: vwap[last].value });
        upper1.push({ time: bar.time, value: upper1[last].value });
        lower1.push({ time: bar.time, value: lower1[last].value });
        upper2.push({ time: bar.time, value: upper2[last].value });
        lower2.push({ time: bar.time, value: lower2[last].value });
        upper3.push({ time: bar.time, value: upper3[last].value });
        lower3.push({ time: bar.time, value: lower3[last].value });
      }
      continue;
    }

    const tp = (bar.high + bar.low + bar.close) / 3;
    cumTPV += tp * bar.volume;
    cumTPV2 += tp * tp * bar.volume;
    cumVol += bar.volume;

    const v = cumTPV / cumVol;
    const variance = (cumTPV2 / cumVol) - (v * v);
    const sd = Math.sqrt(Math.max(0, variance));

    vwap.push({ time: bar.time, value: v });
    upper1.push({ time: bar.time, value: v + sd });
    lower1.push({ time: bar.time, value: v - sd });
    upper2.push({ time: bar.time, value: v + 2 * sd });
    lower2.push({ time: bar.time, value: v - 2 * sd });
    upper3.push({ time: bar.time, value: v + 3 * sd });
    lower3.push({ time: bar.time, value: v - 3 * sd });
  }

  return { vwap, upper1, lower1, upper2, lower2, upper3, lower3 };
}

/**
 * Williams Alligator (Robinhood variant) — uses SMA instead of SMMA/RMA.
 * Jaw: SMA(13) shifted 8, Teeth: SMA(8) shifted 5, Lips: SMA(5) shifted 3.
 * Source: (high + low) / 2 (median price).
 */
export interface AlligatorData {
  jaw: IndicatorData[];
  teeth: IndicatorData[];
  lips: IndicatorData[];
}

export function calcAlligator_RH(candles: Candle[]): AlligatorData {
  const jaw: IndicatorData[] = [];
  const teeth: IndicatorData[] = [];
  const lips: IndicatorData[] = [];

  if (candles.length < 13) return { jaw, teeth, lips };

  const median = candles.map(c => (c.high + c.low) / 2);

  // SMA helper
  const sma = (data: number[], period: number, idx: number): number | null => {
    if (idx < period - 1) return null;
    let sum = 0;
    for (let i = idx - period + 1; i <= idx; i++) sum += data[i];
    return sum / period;
  };

  // Compute SMA values and shift forward
  const jawShift = 8, teethShift = 5, lipsShift = 3;

  for (let i = 0; i < candles.length; i++) {
    const jawVal = sma(median, 13, i);
    const teethVal = sma(median, 8, i);
    const lipsVal = sma(median, 5, i);

    // Shift forward: the value at index i gets placed at candle i+shift
    if (jawVal !== null && i + jawShift < candles.length) {
      jaw.push({ time: candles[i + jawShift].time, value: jawVal });
    }
    if (teethVal !== null && i + teethShift < candles.length) {
      teeth.push({ time: candles[i + teethShift].time, value: teethVal });
    }
    if (lipsVal !== null && i + lipsShift < candles.length) {
      lips.push({ time: candles[i + lipsShift].time, value: lipsVal });
    }
  }

  return { jaw, teeth, lips };
}

/**
 * Forecast Oscillator (Robinhood variant) — absolute difference: Close − TSF.
 * Standard version normalizes as percentage; Robinhood uses raw dollar difference.
 * TSF = linear regression value projected forward 1 bar.
 */
export function calcFOSC_RH(candles: Candle[], length = 14): IndicatorData[] {
  if (candles.length < length) return [];

  const result: IndicatorData[] = [];

  for (let i = length - 1; i < candles.length; i++) {
    // Linear regression over the window
    let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
    for (let j = 0; j < length; j++) {
      const x = j;
      const y = candles[i - length + 1 + j].close;
      sumX += x;
      sumY += y;
      sumXY += x * y;
      sumX2 += x * x;
    }
    const n = length;
    const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
    const intercept = (sumY - slope * sumX) / n;
    // TSF = regression projected to x = length (one bar ahead of the window)
    const tsf = intercept + slope * n;

    result.push({ time: candles[i].time, value: candles[i].close - tsf });
  }

  return result;
}

/**
 * Historical Volatility (Robinhood variant) — 20-period default, annualized with 252 trading days.
 * HV = StdDev(ln(close/prev_close), period) × √252 × 100
 */
export function calcHV_RH(candles: Candle[], period = 20): IndicatorData[] {
  if (candles.length < period + 1) return [];

  const result: IndicatorData[] = [];
  const logReturns: number[] = [];

  for (let i = 1; i < candles.length; i++) {
    logReturns.push(Math.log(candles[i].close / candles[i - 1].close));
  }

  for (let i = period - 1; i < logReturns.length; i++) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += logReturns[j];
    const mean = sum / period;

    let variance = 0;
    for (let j = i - period + 1; j <= i; j++) variance += (logReturns[j] - mean) ** 2;
    variance /= period - 1; // sample variance

    const hv = Math.sqrt(variance) * Math.sqrt(252) * 100;
    result.push({ time: candles[i + 1].time, value: hv }); // +1 because logReturns is offset by 1
  }

  return result;
}

// ── Shared helpers for custom indicator calculations ─────────────────────

/** Simple Moving Average over raw numbers */
function _sma(data: number[], period: number, idx: number): number | null {
  if (idx < period - 1) return null;
  let sum = 0;
  for (let i = idx - period + 1; i <= idx; i++) sum += data[i];
  return sum / period;
}

/** EMA over raw numbers (returns full array) */
function _ema(data: number[], period: number): number[] {
  const k = 2 / (period + 1);
  const result: number[] = [];
  let prev = data[0];
  result.push(prev);
  for (let i = 1; i < data.length; i++) {
    prev = data[i] * k + prev * (1 - k);
    result.push(prev);
  }
  return result;
}

/** RMA / Wilder's smoothing over raw numbers */
function _rma(data: number[], period: number): number[] {
  const result: number[] = [];
  let sum = 0;
  for (let i = 0; i < data.length; i++) {
    if (i < period) {
      sum += data[i];
      result.push(sum / (i + 1));
    } else {
      const prev = result[i - 1];
      result.push((prev * (period - 1) + data[i]) / period);
    }
  }
  return result;
}

/** Linear regression: returns { slope, intercept } for data[start..end] */
function _linreg(data: number[], start: number, len: number): { slope: number; intercept: number } {
  let sx = 0, sy = 0, sxy = 0, sx2 = 0;
  for (let j = 0; j < len; j++) {
    sx += j; sy += data[start + j]; sxy += j * data[start + j]; sx2 += j * j;
  }
  const slope = (len * sxy - sx * sy) / (len * sx2 - sx * sx);
  const intercept = (sy - slope * sx) / len;
  return { slope, intercept };
}

/** True Range for a candle */
function _tr(c: Candle, prev: Candle): number {
  return Math.max(c.high - c.low, Math.abs(c.high - prev.close), Math.abs(c.low - prev.close));
}

// ── Module-format type (matches generic chart/legend branches) ───────────
export type ModuleResult = { plots: Record<string, IndicatorData[]> };

// ══════════════════════════════════════════════════════════════════════════
// 27 Missing Robinhood Indicators
// Each returns ModuleResult so the generic rendering branch handles them.
// ══════════════════════════════════════════════════════════════════════════

/** 1. Acceleration Bands (AB) — volatility breakout bands
 *  Upper = High × (1 + 4×(H−L)/(H+L)), smoothed with SMA
 *  Lower = Low × (1 − 4×(H−L)/(H+L)), smoothed with SMA
 *  Middle = SMA(close) */
export function calcAccelerationBands(candles: Candle[], period = 20): ModuleResult {
  const upper: IndicatorData[] = [], middle: IndicatorData[] = [], lower: IndicatorData[] = [];
  if (candles.length < period) return { plots: { Upper: upper, Middle: middle, Lower: lower } };

  const rawUpper = candles.map(c => c.high * (1 + 4 * (c.high - c.low) / (c.high + c.low)));
  const rawLower = candles.map(c => c.low * (1 - 4 * (c.high - c.low) / (c.high + c.low)));
  const closes = candles.map(c => c.close);

  for (let i = period - 1; i < candles.length; i++) {
    const u = _sma(rawUpper, period, i)!;
    const m = _sma(closes, period, i)!;
    const l = _sma(rawLower, period, i)!;
    upper.push({ time: candles[i].time, value: u });
    middle.push({ time: candles[i].time, value: m });
    lower.push({ time: candles[i].time, value: l });
  }
  return { plots: { Upper: upper, Middle: middle, Lower: lower } };
}

/** 2. Acceleration/Deceleration (AC) — momentum change
 *  AO = SMA(median,5) − SMA(median,34)
 *  AC = AO − SMA(AO,5) */
export function calcAC(candles: Candle[]): ModuleResult {
  const ac: IndicatorData[] = [];
  if (candles.length < 39) return { plots: { AC: ac } }; // need 34+5

  const median = candles.map(c => (c.high + c.low) / 2);
  const ao: number[] = [];

  for (let i = 33; i < candles.length; i++) {
    const fast = _sma(median, 5, i)!;
    const slow = _sma(median, 34, i)!;
    ao.push(fast - slow);
  }

  for (let i = 4; i < ao.length; i++) {
    let sum = 0;
    for (let j = i - 4; j <= i; j++) sum += ao[j];
    const smaAO = sum / 5;
    ac.push({ time: candles[33 + i].time, value: ao[i] - smaAO });
  }
  return { plots: { AC: ac } };
}

/** 3. Accumulation/Distribution (A/D) line — cumulative CLV × volume
 *  CLV = ((close−low) − (high−close)) / (high−low)
 *  A/D = cumulative(CLV × volume) */
export function calcAD(candles: Candle[]): ModuleResult {
  const ad: IndicatorData[] = [];
  let cum = 0;
  for (const c of candles) {
    const hl = c.high - c.low;
    const clv = hl > 0 ? ((c.close - c.low) - (c.high - c.close)) / hl : 0;
    cum += clv * c.volume;
    ad.push({ time: c.time, value: cum });
  }
  return { plots: { 'A/D': ad } };
}

/** 4. Average Directional Movement Index Rating (ADXR)
 *  ADXR = (ADX_today + ADX_n_periods_ago) / 2
 *  Uses RMA-smoothed ADX internally */
export function calcADXR(candles: Candle[], period = 14): ModuleResult {
  const adxr: IndicatorData[] = [];
  if (candles.length < period * 3) return { plots: { ADXR: adxr } };

  // Compute +DM, -DM, TR
  const plusDM: number[] = [0], minusDM: number[] = [0], tr: number[] = [0];
  for (let i = 1; i < candles.length; i++) {
    const upMove = candles[i].high - candles[i - 1].high;
    const downMove = candles[i - 1].low - candles[i].low;
    plusDM.push(upMove > downMove && upMove > 0 ? upMove : 0);
    minusDM.push(downMove > upMove && downMove > 0 ? downMove : 0);
    tr.push(_tr(candles[i], candles[i - 1]));
  }

  const smoothPDM = _rma(plusDM, period);
  const smoothMDM = _rma(minusDM, period);
  const smoothTR = _rma(tr, period);

  const dx: number[] = [];
  for (let i = 0; i < candles.length; i++) {
    const pdi = smoothTR[i] > 0 ? (smoothPDM[i] / smoothTR[i]) * 100 : 0;
    const mdi = smoothTR[i] > 0 ? (smoothMDM[i] / smoothTR[i]) * 100 : 0;
    const sum = pdi + mdi;
    dx.push(sum > 0 ? (Math.abs(pdi - mdi) / sum) * 100 : 0);
  }

  const adxVals = _rma(dx, period);

  for (let i = period; i < candles.length; i++) {
    const prev = i - period >= 0 ? adxVals[i - period] : adxVals[0];
    adxr.push({ time: candles[i].time, value: (adxVals[i] + prev) / 2 });
  }
  return { plots: { ADXR: adxr } };
}

/** 5. Chaikin Volatility — rate of change of EMA(H−L)
 *  CHV = (EMA(H-L,n) − EMA(H-L,n)[m periods ago]) / EMA(H-L,n)[m periods ago] × 100 */
export function calcChaikinVolatility(candles: Candle[], emaPeriod = 10, rocPeriod = 10): ModuleResult {
  const chv: IndicatorData[] = [];
  if (candles.length < emaPeriod + rocPeriod) return { plots: { CHV: chv } };

  const hlRange = candles.map(c => c.high - c.low);
  const emaHL = _ema(hlRange, emaPeriod);

  for (let i = rocPeriod; i < emaHL.length; i++) {
    const prev = emaHL[i - rocPeriod];
    const val = prev !== 0 ? ((emaHL[i] - prev) / prev) * 100 : 0;
    chv.push({ time: candles[i].time, value: val });
  }
  return { plots: { CHV: chv } };
}

/** 6. Daily Open-Close — horizontal lines at today's open and yesterday's close */
export function calcDailyOpenClose(candles: Candle[]): ModuleResult {
  const openLine: IndicatorData[] = [], closeLine: IndicatorData[] = [];
  if (candles.length === 0) return { plots: { Open: openLine, 'Prev Close': closeLine } };

  const lastBar = candles[candles.length - 1];
  const lastDate = new Date(lastBar.time * 1000).toLocaleDateString('en-US', { timeZone: 'America/New_York' });

  let todayOpen: number | null = null;
  let prevClose: number | null = null;
  let prevDate = '';

  for (let i = candles.length - 1; i >= 0; i--) {
    const d = new Date(candles[i].time * 1000).toLocaleDateString('en-US', { timeZone: 'America/New_York' });
    if (d === lastDate) {
      todayOpen = candles[i].open; // keeps overwriting to first bar of today
    } else {
      if (!prevDate) { prevDate = d; prevClose = candles[i].close; }
      if (d !== prevDate) break;
      prevClose = candles[i].close; // last bar of prev day
    }
  }
  // Find actual first bar of today for todayOpen
  for (let i = 0; i < candles.length; i++) {
    const d = new Date(candles[i].time * 1000).toLocaleDateString('en-US', { timeZone: 'America/New_York' });
    if (d === lastDate) { todayOpen = candles[i].open; break; }
  }

  // Draw as horizontal lines across today's bars
  for (const c of candles) {
    const d = new Date(c.time * 1000).toLocaleDateString('en-US', { timeZone: 'America/New_York' });
    if (d === lastDate) {
      if (todayOpen !== null) openLine.push({ time: c.time, value: todayOpen });
      if (prevClose !== null) closeLine.push({ time: c.time, value: prevClose });
    }
  }
  return { plots: { Open: openLine, 'Prev Close': closeLine } };
}

/** 7. Dynamic Momentum Index (DYMI) — variable-period RSI
 *  Period = clamp(INT(14 / (StdDev5 / SMA10(StdDev5))), 5, 30)
 *  Then standard RSI with that dynamic period */
export function calcDYMI(candles: Candle[]): ModuleResult {
  const dymi: IndicatorData[] = [];
  if (candles.length < 30) return { plots: { DYMI: dymi } };

  const closes = candles.map(c => c.close);

  // Compute 5-period StdDev of closes
  const std5: number[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < 4) { std5.push(0); continue; }
    let sum = 0;
    for (let j = i - 4; j <= i; j++) sum += closes[j];
    const mean = sum / 5;
    let var_ = 0;
    for (let j = i - 4; j <= i; j++) var_ += (closes[j] - mean) ** 2;
    std5.push(Math.sqrt(var_ / 5));
  }

  // 10-period SMA of StdDev5
  const smaStd = std5.map((_, i) => _sma(std5, 10, i));

  for (let i = 13; i < candles.length; i++) {
    const vi = smaStd[i] && smaStd[i]! > 0 ? std5[i] / smaStd[i]! : 1;
    const dynPeriod = Math.max(5, Math.min(30, Math.floor(14 / vi)));

    // RSI with dynamic period
    let gains = 0, losses = 0;
    const lookback = Math.min(dynPeriod, i);
    for (let j = i - lookback + 1; j <= i; j++) {
      const delta = closes[j] - closes[j - 1];
      if (delta > 0) gains += delta; else losses -= delta;
    }
    const avgGain = gains / lookback;
    const avgLoss = losses / lookback;
    const rs = avgLoss > 0 ? avgGain / avgLoss : 100;
    dymi.push({ time: candles[i].time, value: 100 - 100 / (1 + rs) });
  }
  return { plots: { DYMI: dymi } };
}

/** 8. High-Low Oscillator — Close − (High + Low) / 2 */
export function calcHLO(candles: Candle[]): ModuleResult {
  const hlo: IndicatorData[] = candles.map(c => ({
    time: c.time, value: c.close - (c.high + c.low) / 2,
  }));
  return { plots: { HLO: hlo } };
}

/** 9. High-Low Volatility — EMA((H−L)/C × 100, period) */
export function calcHLVolatility(candles: Candle[], period = 14): ModuleResult {
  const hlv: IndicatorData[] = [];
  if (candles.length < period) return { plots: { HLV: hlv } };

  const raw = candles.map(c => c.close > 0 ? ((c.high - c.low) / c.close) * 100 : 0);
  const emaVals = _ema(raw, period);

  for (let i = period - 1; i < candles.length; i++) {
    hlv.push({ time: candles[i].time, value: emaVals[i] });
  }
  return { plots: { HLV: hlv } };
}

/** 10. Inertia — Linear regression of RVI over period
 *  RVI uses StdDev direction, Inertia smooths it with regression */
export function calcInertia(candles: Candle[], rviPeriod = 14, regPeriod = 20): ModuleResult {
  const inertia: IndicatorData[] = [];
  if (candles.length < rviPeriod + regPeriod) return { plots: { Inertia: inertia } };

  // Compute RVI values
  const closes = candles.map(c => c.close);
  const std5: number[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < 4) { std5.push(0); continue; }
    let sum = 0;
    for (let j = i - 4; j <= i; j++) sum += closes[j];
    const mean = sum / 5;
    let var_ = 0;
    for (let j = i - 4; j <= i; j++) var_ += (closes[j] - mean) ** 2;
    std5.push(Math.sqrt(var_ / 5));
  }

  const upStd: number[] = [], downStd: number[] = [];
  for (let i = 1; i < closes.length; i++) {
    if (closes[i] > closes[i - 1]) { upStd.push(std5[i]); downStd.push(0); }
    else { upStd.push(0); downStd.push(std5[i]); }
  }
  // Pad index 0
  upStd.unshift(0); downStd.unshift(0);

  const emaUp = _rma(upStd, rviPeriod);
  const emaDown = _rma(downStd, rviPeriod);
  const rvi: number[] = [];
  for (let i = 0; i < candles.length; i++) {
    const sum = emaUp[i] + emaDown[i];
    rvi.push(sum > 0 ? (emaUp[i] / sum) * 100 : 50);
  }

  // Linear regression of RVI
  for (let i = regPeriod - 1; i < rvi.length; i++) {
    const { slope, intercept } = _linreg(rvi, i - regPeriod + 1, regPeriod);
    inertia.push({ time: candles[i].time, value: intercept + slope * (regPeriod - 1) });
  }
  return { plots: { Inertia: inertia } };
}

/** 11. Intraday Momentum Index (IMI) — candle-body RSI
 *  IMI = 100 × ΣUpCloses / (ΣUpCloses + ΣDownCloses) over period */
export function calcIMI(candles: Candle[], period = 14): ModuleResult {
  const imi: IndicatorData[] = [];
  if (candles.length < period) return { plots: { IMI: imi } };

  for (let i = period - 1; i < candles.length; i++) {
    let upSum = 0, downSum = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const body = candles[j].close - candles[j].open;
      if (body > 0) upSum += body; else downSum += Math.abs(body);
    }
    const total = upSum + downSum;
    imi.push({ time: candles[i].time, value: total > 0 ? (upSum / total) * 100 : 50 });
  }
  return { plots: { IMI: imi } };
}

/** 12. Kairi Relative Index (KRI) — % deviation from SMA
 *  KRI = ((Close − SMA) / SMA) × 100 */
export function calcKRI(candles: Candle[], period = 10): ModuleResult {
  const kri: IndicatorData[] = [];
  if (candles.length < period) return { plots: { KRI: kri } };

  const closes = candles.map(c => c.close);
  for (let i = period - 1; i < candles.length; i++) {
    const avg = _sma(closes, period, i)!;
    kri.push({ time: candles[i].time, value: avg > 0 ? ((candles[i].close - avg) / avg) * 100 : 0 });
  }
  return { plots: { KRI: kri } };
}

/** 13. Linear Regression Curve — regression value at each bar */
export function calcLinRegCurve(candles: Candle[], period = 20): ModuleResult {
  const curve: IndicatorData[] = [];
  if (candles.length < period) return { plots: { LinReg: curve } };

  const closes = candles.map(c => c.close);
  for (let i = period - 1; i < candles.length; i++) {
    const { slope, intercept } = _linreg(closes, i - period + 1, period);
    curve.push({ time: candles[i].time, value: intercept + slope * (period - 1) });
  }
  return { plots: { LinReg: curve } };
}

/** 14. Linear Regression Slope — slope value as oscillator */
export function calcLinRegSlope(candles: Candle[], period = 20): ModuleResult {
  const slope: IndicatorData[] = [];
  if (candles.length < period) return { plots: { Slope: slope } };

  const closes = candles.map(c => c.close);
  for (let i = period - 1; i < candles.length; i++) {
    const reg = _linreg(closes, i - period + 1, period);
    slope.push({ time: candles[i].time, value: reg.slope });
  }
  return { plots: { Slope: slope } };
}

/** 15. Market Facilitation Index — (High − Low) / Volume
 *  Measures price movement per unit of volume */
export function calcMarketFacIdx(candles: Candle[]): ModuleResult {
  const mfi: IndicatorData[] = candles.map(c => ({
    time: c.time, value: c.volume > 0 ? (c.high - c.low) / c.volume * 1e6 : 0,
  }));
  return { plots: { MFIdx: mfi } };
}

/** 16. Negative Volume Index (NVI) — tracks price on down-volume days
 *  NVI += (close−prev)/prev when volume < prev_volume */
export function calcNVI(candles: Candle[]): ModuleResult {
  const nvi: IndicatorData[] = [];
  if (candles.length === 0) return { plots: { NVI: nvi } };

  let val = 1000; // start at 1000
  nvi.push({ time: candles[0].time, value: val });

  for (let i = 1; i < candles.length; i++) {
    if (candles[i].volume < candles[i - 1].volume && candles[i - 1].close > 0) {
      val *= 1 + (candles[i].close - candles[i - 1].close) / candles[i - 1].close;
    }
    nvi.push({ time: candles[i].time, value: val });
  }
  return { plots: { NVI: nvi } };
}

/** 17. Percent Change — ((Close − Prev Close) / Prev Close) × 100 */
export function calcPercentChange(candles: Candle[]): ModuleResult {
  const pct: IndicatorData[] = [];
  for (let i = 1; i < candles.length; i++) {
    const prev = candles[i - 1].close;
    pct.push({ time: candles[i].time, value: prev > 0 ? ((candles[i].close - prev) / prev) * 100 : 0 });
  }
  return { plots: { '%Chg': pct } };
}

/** 18. Price Channel — Highest High / Lowest Low over period
 *  Similar to Donchian but commonly uses separate high/low lookbacks */
export function calcPriceChannel(candles: Candle[], period = 20): ModuleResult {
  const upper: IndicatorData[] = [], lower: IndicatorData[] = [];
  if (candles.length < period) return { plots: { Upper: upper, Lower: lower } };

  for (let i = period - 1; i < candles.length; i++) {
    let hi = -Infinity, lo = Infinity;
    for (let j = i - period + 1; j <= i; j++) {
      if (candles[j].high > hi) hi = candles[j].high;
      if (candles[j].low < lo) lo = candles[j].low;
    }
    upper.push({ time: candles[i].time, value: hi });
    lower.push({ time: candles[i].time, value: lo });
  }
  return { plots: { Upper: upper, Lower: lower } };
}

/** 19. SMMA Envelope — SMMA ± percentage band */
export function calcSMMAEnvelope(candles: Candle[], period = 20, pct = 2.5): ModuleResult {
  const upper: IndicatorData[] = [], basis: IndicatorData[] = [], lower: IndicatorData[] = [];
  if (candles.length < period) return { plots: { Upper: upper, Basis: basis, Lower: lower } };

  const closes = candles.map(c => c.close);
  const smma = _rma(closes, period);

  for (let i = period - 1; i < candles.length; i++) {
    const v = smma[i];
    upper.push({ time: candles[i].time, value: v * (1 + pct / 100) });
    basis.push({ time: candles[i].time, value: v });
    lower.push({ time: candles[i].time, value: v * (1 - pct / 100) });
  }
  return { plots: { Upper: upper, Basis: basis, Lower: lower } };
}

/** 20. Smoothed Rate of Change (SROC) — EMA of ROC
 *  SROC = EMA(ROC(close, rocPeriod), emaPeriod) */
export function calcSROC(candles: Candle[], rocPeriod = 12, emaPeriod = 7): ModuleResult {
  const sroc: IndicatorData[] = [];
  if (candles.length < rocPeriod + emaPeriod) return { plots: { SROC: sroc } };

  const roc: number[] = [];
  for (let i = rocPeriod; i < candles.length; i++) {
    const prev = candles[i - rocPeriod].close;
    roc.push(prev > 0 ? ((candles[i].close - prev) / prev) * 100 : 0);
  }

  const emaVals = _ema(roc, emaPeriod);
  for (let i = emaPeriod - 1; i < roc.length; i++) {
    sroc.push({ time: candles[rocPeriod + i].time, value: emaVals[i] });
  }
  return { plots: { SROC: sroc } };
}

/** 21. Standard Deviation Channel — Linear regression ± StdDev bands */
export function calcStdDevChannel(candles: Candle[], period = 20, mult = 2): ModuleResult {
  const upper: IndicatorData[] = [], middle: IndicatorData[] = [], lower: IndicatorData[] = [];
  if (candles.length < period) return { plots: { Upper: upper, Middle: middle, Lower: lower } };

  const closes = candles.map(c => c.close);
  for (let i = period - 1; i < candles.length; i++) {
    const { slope, intercept } = _linreg(closes, i - period + 1, period);
    const regVal = intercept + slope * (period - 1);

    // StdDev of residuals
    let sumSq = 0;
    for (let j = 0; j < period; j++) {
      const predicted = intercept + slope * j;
      sumSq += (closes[i - period + 1 + j] - predicted) ** 2;
    }
    const stdErr = Math.sqrt(sumSq / period);

    upper.push({ time: candles[i].time, value: regVal + mult * stdErr });
    middle.push({ time: candles[i].time, value: regVal });
    lower.push({ time: candles[i].time, value: regVal - mult * stdErr });
  }
  return { plots: { Upper: upper, Middle: middle, Lower: lower } };
}

/** 22. Standard Deviation Volatility — StdDev of log returns */
export function calcStdDevVolatility(candles: Candle[], period = 20): ModuleResult {
  const sdv: IndicatorData[] = [];
  if (candles.length < period + 1) return { plots: { StdDevVol: sdv } };

  const logRet: number[] = [];
  for (let i = 1; i < candles.length; i++) {
    logRet.push(Math.log(candles[i].close / candles[i - 1].close));
  }

  for (let i = period - 1; i < logRet.length; i++) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += logRet[j];
    const mean = sum / period;
    let var_ = 0;
    for (let j = i - period + 1; j <= i; j++) var_ += (logRet[j] - mean) ** 2;
    sdv.push({ time: candles[i + 1].time, value: Math.sqrt(var_ / (period - 1)) * 100 });
  }
  return { plots: { StdDevVol: sdv } };
}

/** 23. Standard Error Bands — Linear regression ± Standard Error × mult */
export function calcStdErrorBands(candles: Candle[], period = 20, mult = 2): ModuleResult {
  const upper: IndicatorData[] = [], middle: IndicatorData[] = [], lower: IndicatorData[] = [];
  if (candles.length < period) return { plots: { Upper: upper, Middle: middle, Lower: lower } };

  const closes = candles.map(c => c.close);
  for (let i = period - 1; i < candles.length; i++) {
    const { slope, intercept } = _linreg(closes, i - period + 1, period);
    const regVal = intercept + slope * (period - 1);

    let sumSq = 0;
    for (let j = 0; j < period; j++) {
      const predicted = intercept + slope * j;
      sumSq += (closes[i - period + 1 + j] - predicted) ** 2;
    }
    const se = Math.sqrt(sumSq / (period - 2)); // standard error uses n-2 for regression

    upper.push({ time: candles[i].time, value: regVal + mult * se });
    middle.push({ time: candles[i].time, value: regVal });
    lower.push({ time: candles[i].time, value: regVal - mult * se });
  }
  return { plots: { Upper: upper, Middle: middle, Lower: lower } };
}

/** 24. STARC Bands — SMA ± ATR × multiplier
 *  Upper = SMA + (ATR × mult), Lower = SMA − (ATR × mult) */
export function calcSTARC(candles: Candle[], smaPeriod = 5, atrPeriod = 15, mult = 2): ModuleResult {
  const upper: IndicatorData[] = [], middle: IndicatorData[] = [], lower: IndicatorData[] = [];
  const minBars = Math.max(smaPeriod, atrPeriod);
  if (candles.length < minBars) return { plots: { Upper: upper, Middle: middle, Lower: lower } };

  const closes = candles.map(c => c.close);
  const trVals: number[] = [0];
  for (let i = 1; i < candles.length; i++) trVals.push(_tr(candles[i], candles[i - 1]));
  const atr = _rma(trVals, atrPeriod);

  for (let i = minBars - 1; i < candles.length; i++) {
    const smaVal = _sma(closes, smaPeriod, i)!;
    upper.push({ time: candles[i].time, value: smaVal + mult * atr[i] });
    middle.push({ time: candles[i].time, value: smaVal });
    lower.push({ time: candles[i].time, value: smaVal - mult * atr[i] });
  }
  return { plots: { Upper: upper, Middle: middle, Lower: lower } };
}

/** 25. Time Series Forecast (TSF) — regression projected 1 bar ahead */
export function calcTSF(candles: Candle[], period = 20): ModuleResult {
  const tsf: IndicatorData[] = [];
  if (candles.length < period) return { plots: { TSF: tsf } };

  const closes = candles.map(c => c.close);
  for (let i = period - 1; i < candles.length; i++) {
    const { slope, intercept } = _linreg(closes, i - period + 1, period);
    tsf.push({ time: candles[i].time, value: intercept + slope * period }); // projected 1 bar ahead
  }
  return { plots: { TSF: tsf } };
}

/** 26. Williams Accumulation/Distribution
 *  WAD = cumulative True Range Direction
 *  If close > prev_close: WAD += close − TrueRangeLow
 *  If close < prev_close: WAD += close − TrueRangeHigh */
export function calcWilliamsAD(candles: Candle[]): ModuleResult {
  const wad: IndicatorData[] = [];
  if (candles.length < 2) return { plots: { WAD: wad } };

  let cum = 0;
  wad.push({ time: candles[0].time, value: 0 });

  for (let i = 1; i < candles.length; i++) {
    const prev = candles[i - 1];
    const trh = Math.max(candles[i].high, prev.close); // True Range High
    const trl = Math.min(candles[i].low, prev.close);  // True Range Low

    if (candles[i].close > prev.close) {
      cum += candles[i].close - trl;
    } else if (candles[i].close < prev.close) {
      cum += candles[i].close - trh;
    }
    wad.push({ time: candles[i].time, value: cum });
  }
  return { plots: { WAD: wad } };
}

/** 27. WMA Envelope — WMA ± percentage band */
export function calcWMAEnvelope(candles: Candle[], period = 20, pct = 2.5): ModuleResult {
  const upper: IndicatorData[] = [], basis: IndicatorData[] = [], lower: IndicatorData[] = [];
  if (candles.length < period) return { plots: { Upper: upper, Basis: basis, Lower: lower } };

  // WMA: weights 1,2,3,...,period
  const closes = candles.map(c => c.close);
  const denom = (period * (period + 1)) / 2;

  for (let i = period - 1; i < candles.length; i++) {
    let wsum = 0;
    for (let j = 0; j < period; j++) {
      wsum += closes[i - period + 1 + j] * (j + 1);
    }
    const wma = wsum / denom;
    upper.push({ time: candles[i].time, value: wma * (1 + pct / 100) });
    basis.push({ time: candles[i].time, value: wma });
    lower.push({ time: candles[i].time, value: wma * (1 - pct / 100) });
  }
  return { plots: { Upper: upper, Basis: basis, Lower: lower } };
}

/** 28. Volume Profile — distributes volume across price buckets
 *  Returns POC (Point of Control), Value Area High, Value Area Low.
 *  POC = price level with highest volume.
 *  Value Area = price range containing 70% of total volume (centered on POC).
 *  Works for Session VP (today's bars), Visible Range VP, or full profile. */
export interface VolumeProfileResult {
  poc: number;       // Point of Control price
  vah: number;       // Value Area High
  val: number;       // Value Area Low
  startTime: number; // first bar time (for drawing horizontal lines)
}

export function calcVolumeProfile(candles: Candle[], bucketCount = 50): VolumeProfileResult | null {
  if (candles.length === 0) return null;

  // Find price range
  let hi = -Infinity, lo = Infinity;
  for (const c of candles) {
    if (c.high > hi) hi = c.high;
    if (c.low < lo) lo = c.low;
  }
  if (hi === lo) return null;

  const bucketSize = (hi - lo) / bucketCount;
  const buckets = new Array(bucketCount).fill(0);

  // Distribute volume across price buckets
  // Each candle's volume is split proportionally across its high-low range
  for (const c of candles) {
    const cLow = Math.max(0, Math.floor((c.low - lo) / bucketSize));
    const cHigh = Math.min(bucketCount - 1, Math.floor((c.high - lo) / bucketSize));
    const span = cHigh - cLow + 1;
    const volPerBucket = c.volume / span;
    for (let b = cLow; b <= cHigh; b++) {
      buckets[b] += volPerBucket;
    }
  }

  // Find POC (bucket with max volume)
  let pocIdx = 0;
  for (let i = 1; i < bucketCount; i++) {
    if (buckets[i] > buckets[pocIdx]) pocIdx = i;
  }

  // Compute Value Area (70% of total volume, expanding outward from POC)
  const totalVol = buckets.reduce((a, b) => a + b, 0);
  const targetVol = totalVol * 0.7;
  let vaVol = buckets[pocIdx];
  let vaLow = pocIdx, vaHigh = pocIdx;

  while (vaVol < targetVol && (vaLow > 0 || vaHigh < bucketCount - 1)) {
    const addLow = vaLow > 0 ? buckets[vaLow - 1] : 0;
    const addHigh = vaHigh < bucketCount - 1 ? buckets[vaHigh + 1] : 0;

    if (addLow >= addHigh && vaLow > 0) {
      vaLow--;
      vaVol += buckets[vaLow];
    } else if (vaHigh < bucketCount - 1) {
      vaHigh++;
      vaVol += buckets[vaHigh];
    } else {
      vaLow--;
      vaVol += buckets[vaLow];
    }
  }

  return {
    poc: lo + (pocIdx + 0.5) * bucketSize,
    vah: lo + (vaHigh + 1) * bucketSize,
    val: lo + vaLow * bucketSize,
    startTime: candles[0].time,
  };
}

/** Session Volume Profile — only today's bars */
export function calcSessionVolumeProfile(candles: Candle[]): VolumeProfileResult | null {
  if (candles.length === 0) return null;

  const lastBar = candles[candles.length - 1];
  const today = new Date(lastBar.time * 1000).toLocaleDateString('en-US', { timeZone: 'America/New_York' });

  const todayBars = candles.filter(c => {
    const d = new Date(c.time * 1000).toLocaleDateString('en-US', { timeZone: 'America/New_York' });
    return d === today;
  });

  return calcVolumeProfile(todayBars);
}

/** 29. Implied Volatility (IV) — volume-weighted average IV from options flow
 *  Aggregates per-trade IV from ThetaData into candle-aligned time series.
 *  Uses volume-weighted average of trades with valid IV within each candle's window.
 *  Displayed as percentage (e.g., 25 = 25% IV). */
export function calcIV(candles: Candle[], trades: { timestamp: number; iv: number | null; size: number }[]): ModuleResult {
  const iv: IndicatorData[] = [];
  if (candles.length === 0 || trades.length === 0) return { plots: { IV: iv } };

  // Filter trades with valid IV
  const validTrades = trades.filter(t => t.iv !== null && t.iv > 0 && isFinite(t.iv));
  if (validTrades.length === 0) return { plots: { IV: iv } };

  // Determine candle interval (approximate from first two candles)
  const interval = candles.length > 1 ? (candles[1].time - candles[0].time) : 60;

  // For each candle, find trades within its time window and compute volume-weighted IV
  let tradeIdx = 0;
  for (const candle of candles) {
    const candleStartMs = candle.time * 1000;
    const candleEndMs = (candle.time + interval) * 1000;

    let weightedIV = 0;
    let totalSize = 0;

    // Advance trade index to start of this candle
    while (tradeIdx < validTrades.length && validTrades[tradeIdx].timestamp < candleStartMs) tradeIdx++;

    // Collect trades within this candle's window
    let j = tradeIdx;
    while (j < validTrades.length && validTrades[j].timestamp < candleEndMs) {
      const t = validTrades[j];
      weightedIV += t.iv! * t.size;
      totalSize += t.size;
      j++;
    }

    if (totalSize > 0) {
      iv.push({ time: candle.time, value: (weightedIV / totalSize) * 100 }); // decimal to %
    } else if (iv.length > 0) {
      // Carry forward last known IV for continuity
      iv.push({ time: candle.time, value: iv[iv.length - 1].value });
    }
  }
  return { plots: { IV: iv } };
}

/**
 * Calculate VWAP from candle data.
 */
/**
 * Get the ET trading date string for a unix timestamp.
 * Used to detect session boundaries for daily VWAP reset.
 */
function _getETDate(unixSec: number): string {
  return new Date(unixSec * 1000).toLocaleDateString('en-US', { timeZone: 'America/New_York' });
}

/**
 * VWAP — resets at each trading day's open.
 * Skips bars with 0 volume (pre-market/post-market with no trades).
 */
export function calcVWAP(candles: Candle[]): IndicatorData[] {
  if (candles.length === 0) return [];

  let cumTPV = 0;
  let cumVol = 0;
  let currentDate = '';
  const result: IndicatorData[] = [];

  for (const bar of candles) {
    // Reset at session boundary (new trading day)
    const barDate = _getETDate(bar.time);
    if (barDate !== currentDate) {
      cumTPV = 0;
      cumVol = 0;
      currentDate = barDate;
    }

    // Skip zero-volume bars (no trades = no VWAP contribution)
    if (bar.volume <= 0) {
      if (result.length > 0) {
        // Carry forward last value for continuity
        result.push({ time: bar.time, value: result[result.length - 1].value });
      }
      continue;
    }

    const tp = (bar.high + bar.low + bar.close) / 3;
    cumTPV += tp * bar.volume;
    cumVol += bar.volume;
    result.push({ time: bar.time, value: cumTPV / cumVol });
  }

  return result;
}

/**
 * VWAP with 3 standard deviation bands (±1σ, ±2σ, ±3σ).
 * Resets at each trading day's open. Matches Robinhood Legend config:
 * Band 1 = ±1σ, Band 2 = ±2σ, Band 3 = ±3σ.
 */
export function calcVWAPBands(candles: Candle[]): {
  vwap: IndicatorData[];
  upper1: IndicatorData[];
  lower1: IndicatorData[];
  upper2: IndicatorData[];
  lower2: IndicatorData[];
  upper3: IndicatorData[];
  lower3: IndicatorData[];
} {
  const vwap: IndicatorData[] = [];
  const upper1: IndicatorData[] = [];
  const lower1: IndicatorData[] = [];
  const upper2: IndicatorData[] = [];
  const lower2: IndicatorData[] = [];
  const upper3: IndicatorData[] = [];
  const lower3: IndicatorData[] = [];

  if (candles.length === 0) return { vwap, upper1, lower1, upper2, lower2, upper3, lower3 };

  let cumTPV = 0;
  let cumVol = 0;
  let cumTPV2 = 0;
  let currentDate = '';

  for (const bar of candles) {
    // Reset at session boundary
    const barDate = _getETDate(bar.time);
    if (barDate !== currentDate) {
      cumTPV = 0;
      cumVol = 0;
      cumTPV2 = 0;
      currentDate = barDate;
    }

    if (bar.volume <= 0) {
      // Carry forward for continuity
      if (vwap.length > 0) {
        const last = vwap.length - 1;
        vwap.push({ time: bar.time, value: vwap[last].value });
        upper1.push({ time: bar.time, value: upper1[last].value });
        lower1.push({ time: bar.time, value: lower1[last].value });
        upper2.push({ time: bar.time, value: upper2[last].value });
        lower2.push({ time: bar.time, value: lower2[last].value });
        upper3.push({ time: bar.time, value: upper3[last].value });
        lower3.push({ time: bar.time, value: lower3[last].value });
      }
      continue;
    }

    const tp = (bar.high + bar.low + bar.close) / 3;
    cumTPV += tp * bar.volume;
    cumTPV2 += tp * tp * bar.volume;
    cumVol += bar.volume;

    const v = cumTPV / cumVol;
    const variance = (cumTPV2 / cumVol) - (v * v);
    const sd = Math.sqrt(Math.max(0, variance));

    vwap.push({ time: bar.time, value: v });
    upper1.push({ time: bar.time, value: v + sd });
    lower1.push({ time: bar.time, value: v - sd });
    upper2.push({ time: bar.time, value: v + 2 * sd });
    lower2.push({ time: bar.time, value: v - 2 * sd });
    upper3.push({ time: bar.time, value: v + 3 * sd });
    lower3.push({ time: bar.time, value: v - 3 * sd });
  }

  return { vwap, upper1, lower1, upper2, lower2, upper3, lower3 };
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
