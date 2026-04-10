const BASE_URL = '';

export interface MarketStructureLevels {
  vwap?: number;
  bb_upper?: number;
  bb_lower?: number;
  orb_5_high?: number;
  orb_5_low?: number;
  hod?: number;
  lod?: number;
  pivot?: number;
  r1?: number;
  s1?: number;
  r2?: number;
  s2?: number;
  prev_high?: number;
  prev_low?: number;
  poc?: number;
}

export interface MarketLevelsResponse {
  levels: MarketStructureLevels;
  session?: Record<string, unknown>;
  timestamp?: string;
}

export interface RecentOrderFlowTrade {
  t: string;
  p: number;
  s: number;
  side: 'buy' | 'sell' | 'neutral' | string;
  x?: string;
}

const FLOW_ENGINE_URL = `http://${window.location.hostname || 'localhost'}:8081`;

async function flowEngineRequest<T>(path: string): Promise<T> {
  const res = await fetch(`${FLOW_ENGINE_URL}${path}`);
  if (!res.ok) throw new Error(`Flow engine ${path}: ${res.status}`);
  return res.json();
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),

  // Market data
  getBars: (symbol: string, timeframe: string, limit = 1000) =>
    request<{ bars: Array<{ time: number; open: number; high: number; low: number; close: number; volume: number }> }>(
      `/api/bars?symbol=${symbol}&timeframe=${timeframe}&limit=${limit}`
    ),

  getQuote: (symbol: string) =>
    request<{ bid: number; ask: number; last: number; source?: string }>(`/api/quote?symbol=${symbol}`),

  getLevels: (symbol: string) =>
    request<MarketLevelsResponse>(
      `/api/signals/levels?symbol=${symbol}`
    ),

  // Signals
  getLatestSignal: () => request<any>('/api/signals/latest'),
  getSignalHistory: () => request<any>('/api/signals/history'),

  // Positions
  getPositions: () => request<any>('/api/pm/positions'),
  getStatus: () => request<any>('/api/pm/status'),
  exitPosition: (id: string) => request<any>(`/api/pm/exit`, { method: 'POST', body: JSON.stringify({ id }) }),

  // Order flow
  getFlowClouds: (symbol: string, minutes = 1) => {
    const today = new Date().toISOString().split('T')[0];
    return request<{ clouds: any[]; bars_summary: any[]; meta: any }>(
      `/api/orderflow/clouds?symbol=${symbol}&bar_minutes=${minutes}&date=${today}`
    );
  },
  getRecentOrderFlowTrades: (symbol: string, limit = 500, minutes = 5) =>
    request<{ trades: RecentOrderFlowTrade[]; count: number; symbol: string; feed: string; live: boolean }>(
      `/api/orderflow/trades/recent?symbol=${symbol}&limit=${limit}&minutes=${minutes}`
    ),

  // Recent options theta_trade events from Rust engine (for hydration on refresh)
  getRecentThetaTrades: (limit = 500) =>
    flowEngineRequest<any[]>(`/theta/trades/recent?limit=${limit}`),

  // GEX
  getGex: () => request<any>('/api/signals/gex'),

  // Options chain + snapshot
  getOptionsChain: (symbol: string, expiration?: string) =>
    request<any>(`/api/options/chain?root=${symbol}${expiration ? `&exp=${expiration}` : ''}`),
  getOptionsSnapshot: (symbol: string, expiration?: string) =>
    request<any>(`/api/options/snapshot?root=${symbol}${expiration ? `&exp=${expiration}` : ''}`),

  getExpirations: (symbol: string) =>
    request<any>(`/api/options/expirations?root=${symbol}`),

  // Volatility
  getVolatilityAdvisor: (symbol: string) =>
    request<any>(`/api/signals/volatility-advisor?symbol=${symbol}`),

  // Flow intelligence
  getSweeps: () => request<any>('/api/signals/sweeps'),

  // Sector rotation
  getSectors: () => request<any>('/api/signals/sectors'),

  // Events calendar
  getEvents: () => request<any>('/api/signals/events'),
};
