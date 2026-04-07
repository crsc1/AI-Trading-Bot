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
  timeframe: Timeframe;
  connected: boolean;
}

export type Timeframe = '1Min' | '5Min' | '15Min' | '1H' | '1D';

export interface Level {
  price: number;
  label: string;
  type: 'vwap' | 'hod' | 'lod' | 'poc' | 'orb_high' | 'orb_low' | 'pivot' | 'gex';
  color?: string;
}
