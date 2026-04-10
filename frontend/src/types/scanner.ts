export interface FlowAlert {
  id: string;
  timestamp: string;
  symbol: string;
  alert_type: string;
  direction: string;
  strike: number;
  right: string;
  size: number;
  premium: number;
  avg_price: number;
  fills: number;
  side: string;
  score: number;
  repeat_count: number;
  detail: string;
}

export interface ScannerStats {
  subscribed_symbols?: string[];
  total_alerts?: number;
}
