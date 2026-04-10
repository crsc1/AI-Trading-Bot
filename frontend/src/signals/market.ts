import { createStore } from 'solid-js/store';
import { batch } from 'solid-js';
import type { MarketState, Candle, Tick, Quote, ChartInterval, ChartRange, MarketTransport } from '../types/market';

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
  dataSource: null,
  quoteSource: null,
  lastEngineMessageAt: null,
  lastQuoteUpdateAt: null,
  interval: loadPref('chart-interval', loadPref('chart-timeframe', '5Min')),
  range: loadPref('chart-range', '1D'),
  connected: false,
  transport: 'disconnected',
};

const [market, setMarket] = createStore(initialState);

export { market, setMarket };

function syncLatestCandle(candle: Candle) {
  const lastIndex = market.candles.length - 1;
  if (lastIndex < 0) {
    setMarket('candles', [candle]);
    return;
  }

  const last = market.candles[lastIndex];
  if (last.time === candle.time) {
    setMarket('candles', lastIndex, candle);
  } else if (candle.time > last.time) {
    setMarket('candles', (prev) => [...prev, candle]);
  }
}

export function updateFromTick(tick: Tick) {
  batch(() => {
    setMarket('lastPrice', tick.price);
    setMarket('lastTick', tick);

    const current = market.currentCandle;
    if (current) {
      const next = {
        ...current,
        high: Math.max(current.high, tick.price),
        low: Math.min(current.low, tick.price),
        close: tick.price,
        volume: current.volume + tick.size,
      };
      setMarket('currentCandle', next);
      syncLatestCandle(next);
    }
  });
}

export function setCandles(candles: Candle[]) {
  setMarket('candles', candles);
  if (candles.length > 0) {
    setMarket('currentCandle', { ...candles[candles.length - 1] });
    setMarket('lastPrice', candles[candles.length - 1].close);
  } else {
    setMarket('currentCandle', null);
  }
}

export function appendCandle(candle: Candle) {
  setMarket('candles', (prev) => [...prev, candle]);
  setMarket('currentCandle', { ...candle });
}

export function replaceCurrentCandle(candle: Candle) {
  setMarket('currentCandle', { ...candle });
  syncLatestCandle(candle);
}

export function updateQuote(quote: Quote) {
  batch(() => {
    setMarket('quote', quote);
    setMarket('lastQuoteUpdateAt', quote.timestamp_ms || Date.now());
  });
}

export function setDataSource(source: string | null) {
  setMarket('dataSource', source);
}

export function setQuoteSource(source: string | null) {
  setMarket('quoteSource', source);
}

export function setLastEngineMessageAt(timestamp: number | null) {
  setMarket('lastEngineMessageAt', timestamp);
}

export function setLastQuoteUpdateAt(timestamp: number | null) {
  setMarket('lastQuoteUpdateAt', timestamp);
}

function intervalSeconds(interval: ChartInterval): number {
  switch (interval) {
    case '1Min': return 60;
    case '2Min': return 120;
    case '5Min': return 300;
    case '10Min': return 600;
    case '15Min': return 900;
    case '30Min': return 1800;
    case '1H': return 3600;
    case '4Hour': return 14400;
    case '1D': return 86400;
    case '1Week': return 604800;
  }
}

function rangeTradingDays(range: ChartRange): number {
  switch (range) {
    case '1D': return 1;
    case '1W': return 5;
    case '1M': return 21;
    case '3M': return 63;
    case '1Y': return 252;
    case 'MAX': return 520;
  }
}

function approximateBars(range: ChartRange, interval: ChartInterval): number {
  const seconds = intervalSeconds(interval);
  if (seconds >= 604800) {
    return Math.max(1, Math.round(rangeTradingDays(range) / 5));
  }
  if (seconds >= 86400) {
    return rangeTradingDays(range);
  }
  const tradingSeconds = rangeTradingDays(range) * 6.5 * 3600;
  return Math.max(1, Math.round(tradingSeconds / seconds));
}

function minimumRangeForInterval(interval: ChartInterval): ChartRange {
  switch (interval) {
    case '1Min':
    case '2Min':
    case '5Min':
      return '1D';
    case '10Min':
    case '15Min':
    case '30Min':
    case '1H':
      return '1W';
    case '4Hour':
      return '1M';
    case '1D':
      return '3M';
    case '1Week':
      return '1Y';
  }
}

function ensureUsefulRange(range: ChartRange, interval: ChartInterval): ChartRange {
  if (approximateBars(range, interval) >= 8) return range;
  return minimumRangeForInterval(interval);
}

export function setChartInterval(interval: ChartInterval) {
  const nextRange = ensureUsefulRange(market.range, interval);
  batch(() => {
    setMarket('interval', interval);
    setMarket('range', nextRange);
    setMarket('candles', []);
    setMarket('currentCandle', null);
  });
  try {
    localStorage.setItem('chart-interval', JSON.stringify(interval));
    localStorage.setItem('chart-range', JSON.stringify(nextRange));
    localStorage.removeItem('chart-timeframe');
  } catch {}
}

export function setChartRange(range: ChartRange) {
  const nextRange = ensureUsefulRange(range, market.interval);
  setMarket('range', nextRange);
  try { localStorage.setItem('chart-range', JSON.stringify(nextRange)); } catch {}
}

export function setSymbol(symbol: string) {
  setMarket('symbol', symbol);
  try { localStorage.setItem('chart-symbol', JSON.stringify(symbol)); } catch {}
}

export function setConnected(connected: boolean) {
  setMarket('connected', connected);
}

export function setTransport(transport: MarketTransport) {
  setMarket('transport', transport);
}
