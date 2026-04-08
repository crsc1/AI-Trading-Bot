import { createStore } from 'solid-js/store';
import type { MarketState, Candle, Tick, Quote, Timeframe } from '../types/market';

function loadPref<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v ? JSON.parse(v) : fallback;
  } catch { return fallback; }
}

const initialState: MarketState = {
  symbol: loadPref('chart-symbol', 'SPY'),
  lastPrice: 0,
  lastTick: null,
  candles: [],
  currentCandle: null,
  quote: null,
  timeframe: loadPref('chart-timeframe', '5Min'),
  connected: false,
};

const [market, setMarket] = createStore(initialState);

export { market, setMarket };

export function updateFromTick(tick: Tick) {
  setMarket('lastPrice', tick.price);
  setMarket('lastTick', tick);

  // Update current candle with new tick
  const current = market.currentCandle;
  if (current) {
    setMarket('currentCandle', {
      ...current,
      high: Math.max(current.high, tick.price),
      low: Math.min(current.low, tick.price),
      close: tick.price,
      volume: current.volume + tick.size,
    });
  }
}

export function setCandles(candles: Candle[]) {
  setMarket('candles', candles);
  if (candles.length > 0) {
    setMarket('currentCandle', { ...candles[candles.length - 1] });
    setMarket('lastPrice', candles[candles.length - 1].close);
  }
}

export function appendCandle(candle: Candle) {
  setMarket('candles', (prev) => [...prev, candle]);
  setMarket('currentCandle', { ...candle });
}

export function updateQuote(quote: Quote) {
  setMarket('quote', quote);
}

export function setTimeframe(tf: Timeframe) {
  setMarket('timeframe', tf);
  try { localStorage.setItem('chart-timeframe', JSON.stringify(tf)); } catch {}
}

export function setSymbol(symbol: string) {
  setMarket('symbol', symbol);
  try { localStorage.setItem('chart-symbol', JSON.stringify(symbol)); } catch {}
}

export function setConnected(connected: boolean) {
  setMarket('connected', connected);
}
