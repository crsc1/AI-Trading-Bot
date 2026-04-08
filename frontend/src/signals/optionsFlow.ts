import { createStore } from 'solid-js/store';

export interface OptionTrade {
  strike: number;
  right: 'C' | 'P';
  price: number;
  size: number;
  premium: number;       // price * size * 100
  exchange: string;
  timestamp: number;     // epoch ms
  expiration: number;    // YYYYMMDD
  root: string;
  condition: number;     // ThetaData trade condition code
  side: 'buy' | 'sell' | 'mid'; // Lee-Ready: buy=at ask, sell=at bid, mid=between
  iv: number | null;     // implied volatility (decimal, e.g. 0.25 = 25%)
  delta: number | null;  // option delta
  gamma: number | null;  // option gamma (used for Smart Money Score)
  vpin: number | null;   // options flow VPIN (0-1, >0.7 = toxic)
  sms: number;           // Smart Money Score (0-100)
  tag: 'normal' | 'sweep' | 'block' | 'whale'; // classified after ingestion
  clusterId: number | null;  // parent-order cluster ID (null = unclustered)
}

export interface FlowCluster {
  id: number;
  strike: number;
  right: 'C' | 'P';
  side: 'buy' | 'sell' | 'mid';
  avgPrice: number;
  totalSize: number;
  totalPremium: number;
  tradeCount: number;
  firstTs: number;
  lastTs: number;
}

interface OptionsFlowState {
  trades: OptionTrade[];
  totalCallPremium: number;
  totalPutPremium: number;
  tradeCount: number;
}

const MAX_TRADES = 1000;

const [optionsFlow, setOptionsFlow] = createStore<OptionsFlowState>({
  trades: [],
  totalCallPremium: 0,
  totalPutPremium: 0,
  tradeCount: 0,
});

export { optionsFlow };

// Recent trades buffer for sweep detection (same strike+right within 2 seconds)
let recentBuffer: { strike: number; right: string; ts: number; size: number; exchanges: Set<string> }[] = [];

// ── Flow cluster detection ──────────────────────────────────────────────
// Detects parent orders split across multiple trades.
// Same strike+right+side, similar price, within 30 seconds = one cluster.
const CLUSTER_WINDOW_MS = 30_000;
const CLUSTER_PRICE_TOLERANCE = 0.20; // 20% of avg price

let nextClusterId = 1;
let activeClusters: FlowCluster[] = [];

function assignCluster(trade: OptionTrade): number | null {
  const now = trade.timestamp;

  // Expire old clusters
  activeClusters = activeClusters.filter(c => now - c.lastTs < CLUSTER_WINDOW_MS);

  // Find matching cluster: same strike+right+side, price within tolerance
  const match = activeClusters.find(c =>
    c.strike === trade.strike &&
    c.right === trade.right &&
    c.side === trade.side &&
    c.avgPrice > 0 &&
    Math.abs(trade.price - c.avgPrice) / c.avgPrice <= CLUSTER_PRICE_TOLERANCE
  );

  if (match) {
    // Join existing cluster
    const totalValue = match.avgPrice * match.totalSize + trade.price * trade.size;
    match.totalSize += trade.size;
    match.avgPrice = totalValue / match.totalSize;
    match.totalPremium += trade.premium;
    match.tradeCount++;
    match.lastTs = now;
    return match.id;
  }

  // Only start a new cluster for trades worth tracking (5+ contracts or $5K+ premium)
  if (trade.size >= 5 || trade.premium >= 5_000) {
    const id = nextClusterId++;
    activeClusters.push({
      id,
      strike: trade.strike,
      right: trade.right,
      side: trade.side,
      avgPrice: trade.price,
      totalSize: trade.size,
      totalPremium: trade.premium,
      tradeCount: 1,
      firstTs: now,
      lastTs: now,
    });
    return id;
  }

  return null; // Too small to cluster
}

export function getActiveClusters(): FlowCluster[] {
  const now = Date.now();
  activeClusters = activeClusters.filter(c => now - c.lastTs < CLUSTER_WINDOW_MS);
  // Only return clusters with 2+ trades (single-trade clusters aren't interesting)
  return activeClusters.filter(c => c.tradeCount >= 2);
}

export function getCluster(id: number): FlowCluster | undefined {
  return activeClusters.find(c => c.id === id);
}

function classifyTrade(trade: OptionTrade): OptionTrade['tag'] {
  const now = trade.timestamp;

  // Whale: $100K+ premium in a single print
  if (trade.premium >= 100_000) return 'whale';

  // Block: 100+ contracts in a single print
  if (trade.size >= 100) return 'block';

  // Sweep: same strike+right across multiple exchanges within 2 seconds
  // (institutions sweep the book to fill large orders across venues)
  const cutoff = now - 2000;
  recentBuffer = recentBuffer.filter(r => r.ts > cutoff);

  const existing = recentBuffer.find(
    r => r.strike === trade.strike && r.right === trade.right
  );
  if (existing) {
    existing.exchanges.add(String(trade.exchange));
    existing.size += trade.size;
    // 3+ exchanges in 2 seconds = sweep
    if (existing.exchanges.size >= 3) return 'sweep';
  } else {
    recentBuffer.push({
      strike: trade.strike,
      right: trade.right,
      ts: now,
      size: trade.size,
      exchanges: new Set([String(trade.exchange)]),
    });
  }

  return 'normal';
}

export function addOptionTrade(trade: OptionTrade) {
  // Classify the trade
  trade.tag = classifyTrade(trade);

  // Assign to parent-order cluster
  trade.clusterId = assignCluster(trade);

  setOptionsFlow('trades', (prev) => {
    const next = [trade, ...prev];
    if (next.length > MAX_TRADES) return next.slice(0, MAX_TRADES);
    return next;
  });
  setOptionsFlow('tradeCount', (c) => c + 1);
  if (trade.right === 'C') {
    setOptionsFlow('totalCallPremium', (p) => p + trade.premium);
  } else {
    setOptionsFlow('totalPutPremium', (p) => p + trade.premium);
  }
}

export function clearOptionsFlow() {
  setOptionsFlow({ trades: [], totalCallPremium: 0, totalPutPremium: 0, tradeCount: 0 });
  recentBuffer = [];
  activeClusters = [];
  nextClusterId = 1;
}
