import { createStore } from 'solid-js/store';
import type { MarketState, Candle, Tick, Quote, Timeframe } from '../types/market';

const initialState: MarketState = {
  symbol: 'SPY',
  lastPrice: 0,
  lastTick: null,
  candles: [],
  currentCandle: null,
  quote: null,
  timeframe: '5Min',
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
}

export function setConnected(connected: boolean) {
  setMarket('connected', connected);
}
