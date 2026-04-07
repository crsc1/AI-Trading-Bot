export interface Signal {
  id: string;
  action: 'BUY_CALL' | 'BUY_PUT' | 'NO_TRADE';
  confidence: number;
  tier: 'TEXTBOOK' | 'HIGH' | 'VALID' | 'DEVELOPING';
  strike: number;
  entry_price: number;
  target_price: number;
  stop_price: number;
  max_contracts: number;
  reasoning: string;
  key_factors: string[];
  setup_name?: string;
  timestamp: string;
  status: 'OPEN' | 'TARGET_HIT' | 'STOPPED' | 'EXPIRED' | 'CLOSED';
  pnl_dollars?: number;
  pnl_percent?: number;
}

export interface Position {
  id: string;
  symbol: string;
  strike: number;
  option_type: 'call' | 'put';
  expiry: string;
  contracts: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  greeks: Greeks;
  entry_time: string;
  exit_triggers: ExitTriggers;
}

export interface Greeks {
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  rho: number;
}

export interface ExitTriggers {
  stop_loss: number;
  profit_target: number;
  trailing_stop?: number;
  max_hold_time: string;
  theta_decay_exit: boolean;
}

export interface DailyPerformance {
  total_pnl: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  trades_today: number;
}
