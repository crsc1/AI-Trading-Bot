export type MarketTransport = 'webtransport' | 'websocket' | 'disconnected';

export interface Tick {
  price: number;
  size: number;
  side: 'buy' | 'sell' | 'unknown';
  timestamp_ms: number;
}

export interface Candle {
  time: number; // Unix timestamp in seconds (LWC format)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Quote {
  bid: number;
  ask: number;
  bid_size: number;
  ask_size: number;
  timestamp_ms: number;
}

export interface MarketState {
  symbol: string;
  lastPrice: number;
  lastTick: Tick | null;
  candles: Candle[];
  currentCandle: Candle | null;
  quote: Quote | null;
  dataSource: string | null;
  quoteSource: string | null;
  lastEngineMessageAt: number | null;
  lastQuoteUpdateAt: number | null;
  interval: ChartInterval;
  range: ChartRange;
  connected: boolean;
  transport: MarketTransport;
}

export type ChartInterval = '1Min' | '2Min' | '5Min' | '10Min' | '15Min' | '30Min' | '1H' | '4Hour' | '1D' | '1Week';
export type ChartRange = '1D' | '1W' | '1M' | '3M' | '1Y' | 'MAX';

export interface Level {
  price: number;
  label: string;
  type: 'vwap' | 'hod' | 'lod' | 'poc' | 'orb_high' | 'orb_low' | 'pivot' | 'gex';
  color?: string;
}
