const BASE_URL = '';

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
    request<{ bid: number; ask: number; last: number }>(`/api/quote?symbol=${symbol}`),

  getLevels: (symbol: string) =>
    request<{ levels: Array<{ price: number; label: string; type: string }> }>(
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

  // GEX
  getGex: () => request<any>('/api/signals/gex'),
};
