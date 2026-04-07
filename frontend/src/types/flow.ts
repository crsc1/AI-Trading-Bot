export interface FlowCloud {
  price: number;
  time: number;
  buy_vol: number;
  sell_vol: number;
  delta: number;
}

export interface FlowBubble {
  x: number;
  y: number;
  radius: number;
  color: number; // 0xRRGGBB
  alpha: number;
  volume: number;
  delta: number;
}

export interface FlowMeta {
  trade_count: number;
  date: string;
  feed: string;
}

export interface FlowState {
  clouds: FlowCloud[];
  bubbles: FlowBubble[];
  meta: FlowMeta | null;
  connected: boolean;
}

export interface FlowEvent {
  type: 'tick' | 'sweep' | 'absorption' | 'cvd_spike' | 'delta_flip';
  tick?: {
    price: number;
    size: number;
    side: 'buy' | 'sell';
    timestamp_ms: number;
  };
  sweep?: {
    direction: 'bullish' | 'bearish';
    notional: number;
    strikes: number[];
  };
  absorption?: {
    price: number;
    direction: 'buy' | 'sell';
    volume: number;
  };
}
