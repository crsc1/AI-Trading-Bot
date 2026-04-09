/**
 * Live options chain store — builds from theta_trade WS events.
 *
 * Each theta_trade carries: strike, right, price, iv, delta, gamma, side, size.
 * We maintain a live map of strike → { call, put } with latest trade data.
 * Initial bid/ask/OI comes from a REST fetch, then trades update prices + Greeks in real-time.
 */
import { createStore } from 'solid-js/store';

export interface ChainStrike {
  bid: number;
  ask: number;
  last: number;
  iv: number | null;
  delta: number | null;
  gamma: number | null;
  volume: number;
  oi: number;
}

interface ChainState {
  strikes: Map<number, { call: ChainStrike; put: ChainStrike }>;
  atmIv: number | null;       // latest ATM IV from trades
  spotPrice: number;
  lastUpdate: number;
}

const emptyStrike = (): ChainStrike => ({
  bid: 0, ask: 0, last: 0, iv: null, delta: null, gamma: null, volume: 0, oi: 0,
});

const [chainState, setChainState] = createStore<ChainState>({
  strikes: new Map(),
  atmIv: null,
  spotPrice: 0,
  lastUpdate: 0,
});

export { chainState };

/** Load initial chain data from REST (bid/ask/OI) */
export function loadChainSnapshot(data: any) {
  const strikes = new Map<number, { call: ChainStrike; put: ChainStrike }>();

  for (const c of (data.calls || [])) {
    const entry = strikes.get(c.strike) || { call: emptyStrike(), put: emptyStrike() };
    entry.call = {
      bid: c.bid ?? 0, ask: c.ask ?? 0, last: c.last ?? c.mid ?? 0,
      iv: c.iv ?? null, delta: c.delta ?? null, gamma: c.gamma ?? null,
      volume: c.volume ?? 0, oi: c.open_interest ?? c.oi ?? 0,
    };
    strikes.set(c.strike, entry);
  }

  for (const p of (data.puts || [])) {
    const entry = strikes.get(p.strike) || { call: emptyStrike(), put: emptyStrike() };
    entry.put = {
      bid: p.bid ?? 0, ask: p.ask ?? 0, last: p.last ?? p.mid ?? 0,
      iv: p.iv ?? null, delta: p.delta ?? null, gamma: p.gamma ?? null,
      volume: p.volume ?? 0, oi: p.open_interest ?? p.oi ?? 0,
    };
    strikes.set(p.strike, entry);
  }

  setChainState('strikes', strikes);
  setChainState('spotPrice', data.spot_price ?? 0);
  setChainState('lastUpdate', Date.now());
}

/** Update chain from a live theta_trade WS event */
export function updateChainFromTrade(trade: {
  strike: number;
  right: 'C' | 'P';
  price: number;
  size: number;
  iv: number | null;
  delta: number | null;
  gamma: number | null;
}) {
  const strikes = chainState.strikes;
  const entry = strikes.get(trade.strike) || { call: emptyStrike(), put: emptyStrike() };
  const side = trade.right === 'C' ? entry.call : entry.put;

  side.last = trade.price;
  side.volume += trade.size;
  if (trade.iv != null) side.iv = trade.iv;
  if (trade.delta != null) side.delta = trade.delta;
  if (trade.gamma != null) side.gamma = trade.gamma;

  const newStrikes = new Map(strikes);
  newStrikes.set(trade.strike, { ...entry });
  setChainState('strikes', newStrikes);
  setChainState('lastUpdate', Date.now());

  // Update ATM IV — use the trade closest to spot price
  if (trade.iv != null && chainState.spotPrice > 0) {
    if (Math.abs(trade.strike - chainState.spotPrice) <= 1) {
      setChainState('atmIv', trade.iv);
    }
  }
}

/** Reset chain (on symbol switch) */
export function resetChain() {
  setChainState({
    strikes: new Map(),
    atmIv: null,
    spotPrice: 0,
    lastUpdate: 0,
  });
}
