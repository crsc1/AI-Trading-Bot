/**
 * Reference panels — 9 options-first data panels.
 * Each fetches its own data, renders inside <Panel>.
 */
import { type Component, For, Show, createSignal, createMemo, onMount, onCleanup } from 'solid-js';
import { api } from '../../lib/api';
import { market } from '../../signals/market';
import { optionsFlow } from '../../signals/optionsFlow';
import { chainState, loadChainSnapshot } from '../../signals/chain';
import { Panel, DataRow, fmtPct, fmtPrice, fmtPremium, fmtDelta, fmtGex, fmtNum } from '../shared/Panel';

// ── Polling helper ──────────────────────────────────────────────────────────

function usePoll<T>(fetcher: () => Promise<T>, intervalMs: number) {
  const [data, setData] = createSignal<T | null>(null);
  const [loading, setLoading] = createSignal(true);
  const [error, setError] = createSignal<string | null>(null);

  let timer: ReturnType<typeof setInterval> | null = null;

  const load = async () => {
    try {
      const result = await fetcher();
      setData(() => result);
      setError(null);
    } catch (e: any) {
      setError(e?.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  };

  onMount(() => {
    load();
    timer = setInterval(load, intervalMs);
  });
  onCleanup(() => { if (timer) clearInterval(timer); });

  return { data, loading, error };
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. OPTIONS CHAIN
// ═══════════════════════════════════════════════════════════════════════════

export const OptionsChainPanel: Component = () => {
  const [initialLoaded, setInitialLoaded] = createSignal(false);

  // One-time REST fetch for bid/ask/OI, then WS updates in real-time
  onMount(async () => {
    try {
      const data = await api.getOptionsChain(market.symbol);
      loadChainSnapshot(data);
    } catch {}
    setInitialLoaded(true);
  });

  const spot = () => chainState.spotPrice || market.lastPrice;

  const visible = createMemo(() => {
    const strikes = chainState.strikes;
    if (strikes.size === 0) return [];
    const sorted = [...strikes.entries()].sort(([a], [b]) => a - b);
    const atmIdx = sorted.findIndex(([s]) => s >= spot());
    const start = Math.max(0, atmIdx - 10);
    return sorted.slice(start, start + 21);
  });

  return (
    <Panel title="Options Chain" badge="LIVE" badgeColor="positive" loading={!initialLoaded()}>
      <div class="text-[9px]">
        <div class="flex items-center px-2 py-1 border-b border-border-default text-text-secondary font-display tracking-wider sticky top-0 bg-surface-1 z-10">
          <span class="w-10 text-right">IV</span>
          <span class="w-10 text-right">Delta</span>
          <span class="w-12 text-right">Last</span>
          <span class="w-10 text-right">Vol</span>
          <span class="w-14 text-center font-medium text-text-primary">STRIKE</span>
          <span class="w-12 text-right">Last</span>
          <span class="w-10 text-right">Delta</span>
          <span class="w-10 text-right">IV</span>
          <span class="w-10 text-right">Vol</span>
        </div>

        <For each={visible()}>
          {([strike, row]) => {
            const isATM = () => Math.abs(strike - spot()) < 0.5;
            return (
              <div class={`flex items-center px-2 py-0.5 border-b border-border-subtle font-data ${isATM() ? 'bg-accent/8' : ''}`}>
                <span class="w-10 text-right text-text-secondary">{row.call.iv != null ? fmtPct(row.call.iv * 100) : '—'}</span>
                <span class="w-10 text-right text-positive">{row.call.delta != null ? fmtDelta(row.call.delta) : '—'}</span>
                <span class="w-12 text-right text-text-primary">{row.call.last > 0 ? row.call.last.toFixed(2) : '—'}</span>
                <span class="w-10 text-right text-text-secondary">{row.call.volume > 0 ? fmtNum(row.call.volume) : '—'}</span>

                <span class={`w-14 text-center font-medium ${isATM() ? 'text-accent' : 'text-text-primary'}`}>
                  {strike}
                </span>

                <span class="w-12 text-right text-text-primary">{row.put.last > 0 ? row.put.last.toFixed(2) : '—'}</span>
                <span class="w-10 text-right text-negative">{row.put.delta != null ? fmtDelta(row.put.delta) : '—'}</span>
                <span class="w-10 text-right text-text-secondary">{row.put.iv != null ? fmtPct(row.put.iv * 100) : '—'}</span>
                <span class="w-10 text-right text-text-secondary">{row.put.volume > 0 ? fmtNum(row.put.volume) : '—'}</span>
              </div>
            );
          }}
        </For>

        <Show when={visible().length === 0 && initialLoaded()}>
          <div class="text-center text-text-secondary py-4">No chain data available</div>
        </Show>
      </div>
    </Panel>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// 2. IV DASHBOARD
// ═══════════════════════════════════════════════════════════════════════════

export const IVDashboardPanel: Component = () => {
  // REST for IV Rank/Percentile (historical — doesn't need real-time)
  const { data, loading, error } = usePoll(
    () => api.getVolatilityAdvisor(market.symbol),
    30_000,
  );

  // Live ATM IV from chain store (WS-driven)
  const liveIv = () => chainState.atmIv;

  return (
    <Panel title="IV Dashboard" badge="LIVE" badgeColor="positive" loading={loading()} error={error() ?? undefined}>
      <Show when={data()}>
        {(d) => {
          const v = d();
          const ivRank = v.iv_rank ?? v.ivRank;
          const ivPct = v.iv_percentile ?? v.ivPercentile;
          const atmIv = liveIv() ?? v.atm_iv ?? v.atmIv;
          const regime = v.regime ?? v.vol_regime ?? '';

          const rankColor = ivRank != null
            ? (ivRank > 50 ? 'text-warning' : ivRank > 25 ? 'text-text-primary' : 'text-positive')
            : 'text-text-primary';

          return (
            <div class="p-3 space-y-1">
              <DataRow label="ATM IV" value={fmtPct(atmIv != null ? atmIv * 100 : null)} large />
              <DataRow label="IV Rank" value={fmtPct(ivRank)} color={rankColor} large />
              <DataRow label="IV Percentile" value={fmtPct(ivPct)} />
              <DataRow label="Vol Regime" value={regime || '—'} color={
                regime === 'high' ? 'text-warning' : regime === 'low' ? 'text-positive' : 'text-text-primary'
              } />
              <Show when={v['52w_high'] || v['52w_low']}>
                <div class="mt-2 pt-2 border-t border-border-subtle">
                  <DataRow label="52w High IV" value={fmtPct(v['52w_high'] != null ? v['52w_high'] * 100 : null)} />
                  <DataRow label="52w Low IV" value={fmtPct(v['52w_low'] != null ? v['52w_low'] * 100 : null)} />
                </div>
              </Show>
            </div>
          );
        }}
      </Show>
    </Panel>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// 3. OPTIONS SNAPSHOT
// ═══════════════════════════════════════════════════════════════════════════

export const OptionsSnapshotPanel: Component = () => {
  const { data, loading, error } = usePoll(
    () => api.getOptionsSnapshot(market.symbol),
    30_000,
  );

  return (
    <Panel title="Options Snapshot" badge="30s" loading={loading()} error={error() ?? undefined}>
      <Show when={data()}>
        {(d) => {
          const s = d();
          const pcrVol = s.pcr_vol ?? s.pcr_volume;
          const pcrOI = s.pcr_oi;

          return (
            <div class="p-3 space-y-1">
              <DataRow label="Max Pain" value={fmtPrice(s.max_pain)} large color="text-warning" />
              <DataRow label="PCR (Volume)" value={pcrVol != null ? pcrVol.toFixed(2) : '—'} color={
                pcrVol != null ? (pcrVol > 1 ? 'text-negative' : pcrVol < 0.7 ? 'text-positive' : 'text-text-primary') : 'text-text-primary'
              } />
              <DataRow label="PCR (OI)" value={pcrOI != null ? pcrOI.toFixed(2) : '—'} />
              <div class="mt-2 pt-2 border-t border-border-subtle">
                <DataRow label="Call Volume" value={fmtNum(s.call_volume)} color="text-positive" />
                <DataRow label="Put Volume" value={fmtNum(s.put_volume)} color="text-negative" />
                <DataRow label="Call OI" value={fmtNum(s.call_oi)} />
                <DataRow label="Put OI" value={fmtNum(s.put_oi)} />
              </div>
            </div>
          );
        }}
      </Show>
    </Panel>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// 4. GEX LEVELS
// ═══════════════════════════════════════════════════════════════════════════

export const GexPanel: Component = () => {
  const { data, loading, error } = usePoll(() => api.getGex(), 30_000);

  return (
    <Panel title="GEX Levels" badge="30s" loading={loading()} error={error() ?? undefined}>
      <Show when={data()}>
        {(d) => {
          const g = d();
          return (
            <div class="p-3 space-y-1">
              <DataRow label="Regime" value={g.regime || '—'} large color={
                g.regime === 'bullish' ? 'text-positive' : g.regime === 'bearish' ? 'text-negative' : 'text-text-primary'
              } />
              <DataRow label="Flip Level" value={fmtPrice(g.flip_level)} color="text-warning" />
              <DataRow label="Max Gamma" value={fmtPrice(g.max_gamma_strike)} color="text-accent" />
              <DataRow label="Net GEX" value={fmtGex(g.current_gex)} color={
                g.current_gex > 0 ? 'text-positive' : 'text-negative'
              } />

              <Show when={g.strike_gex}>
                <div class="mt-2 pt-2 border-t border-border-subtle">
                  <span class="font-display text-[8px] text-text-secondary uppercase tracking-wider">Top Strikes</span>
                  <div class="mt-1 space-y-0.5">
                    <For each={Object.entries(g.strike_gex || {}).sort(([, a]: any, [, b]: any) => Math.abs(b as number) - Math.abs(a as number)).slice(0, 6)}>
                      {([strike, val]) => (
                        <div class="flex items-center justify-between text-[9px] font-data">
                          <span class="text-text-primary">${strike}</span>
                          <span class={Number(val) >= 0 ? 'text-positive' : 'text-negative'}>
                            {fmtGex(Number(val))}
                          </span>
                        </div>
                      )}
                    </For>
                  </div>
                </div>
              </Show>
            </div>
          );
        }}
      </Show>
    </Panel>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// 5. EXPECTED MOVE
// ═══════════════════════════════════════════════════════════════════════════

export const ExpectedMovePanel: Component = () => {
  // Live IV from chain store (WS-driven), no polling needed
  const atmIv = () => chainState.atmIv ?? 0;
  const price = () => market.lastPrice;

  // Expected move = price × IV × √(DTE/365)
  const dailyMove = () => price() * atmIv() * Math.sqrt(1 / 365);
  const weeklyMove = () => price() * atmIv() * Math.sqrt(5 / 365);

  return (
    <Panel title="Expected Move" badge="LIVE" badgeColor="positive" loading={price() <= 0}>
      <div class="p-3 space-y-1">
        <DataRow label="Current Price" value={fmtPrice(price())} large />
        <DataRow label="ATM IV" value={fmtPct(atmIv() * 100)} />
        <div class="mt-2 pt-2 border-t border-border-subtle">
          <DataRow label="Daily ±" value={fmtPrice(dailyMove())} large color="text-accent" />
          <DataRow label="Daily Range" value={`${fmtPrice(price() - dailyMove())} — ${fmtPrice(price() + dailyMove())}`} />
        </div>
        <div class="mt-2 pt-2 border-t border-border-subtle">
          <DataRow label="Weekly ±" value={fmtPrice(weeklyMove())} large color="text-warning" />
          <DataRow label="Weekly Range" value={`${fmtPrice(price() - weeklyMove())} — ${fmtPrice(price() + weeklyMove())}`} />
        </div>
      </div>
    </Panel>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// 6. UNUSUAL ACTIVITY
// ═══════════════════════════════════════════════════════════════════════════

export const UnusualActivityPanel: Component = () => {
  // Use live optionsFlow store for real-time data
  const notable = () => {
    return optionsFlow.trades
      .filter(t => t.tag !== 'normal')
      .slice(0, 12);
  };

  return (
    <Panel title="Unusual Activity" badge="LIVE" badgeColor="positive">
      <Show when={notable().length > 0} fallback={
        <div class="flex items-center justify-center h-full text-text-secondary text-[10px]">
          No sweeps, blocks, or whales detected yet
        </div>
      }>
        <div class="text-[9px]">
          <div class="flex items-center px-2 py-1 border-b border-border-default text-text-secondary font-display tracking-wider sticky top-0 bg-surface-1 z-10">
            <span class="w-14">TIME</span>
            <span class="w-10">TYPE</span>
            <span class="w-7">C/P</span>
            <span class="w-10 text-right">STRIKE</span>
            <span class="w-10 text-right">SIZE</span>
            <span class="flex-1 text-right">PREMIUM</span>
          </div>
          <For each={notable()}>
            {(t) => {
              const sideColor = t.side === 'buy' ? 'text-positive' : t.side === 'sell' ? 'text-negative' : 'text-text-secondary';
              return (
                <div class={`flex items-center px-2 py-0.5 border-b border-border-subtle font-data ${
                  t.side === 'buy' ? 'bg-positive/5' : t.side === 'sell' ? 'bg-negative/5' : ''
                }`}>
                  <span class="w-14 text-text-secondary text-[8px]">
                    {new Date(t.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
                  </span>
                  <span class={`w-10 text-[8px] font-medium ${
                    t.tag === 'sweep' ? 'text-purple' : t.tag === 'whale' ? 'text-warning' : 'text-accent'
                  }`}>
                    {t.tag.toUpperCase()}
                  </span>
                  <span class={`w-7 ${t.right === 'C' ? 'text-positive' : 'text-negative'}`}>{t.right}</span>
                  <span class="w-10 text-right text-text-primary">{t.strike}</span>
                  <span class={`w-10 text-right ${sideColor}`}>{t.size}</span>
                  <span class={`flex-1 text-right font-medium ${sideColor}`}>{fmtPremium(t.premium)}</span>
                </div>
              );
            }}
          </For>
        </div>
      </Show>
    </Panel>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// 7. PORTFOLIO GREEKS
// ═══════════════════════════════════════════════════════════════════════════

export const PortfolioGreeksPanel: Component = () => {
  const { data, loading, error } = usePoll(() => api.getPositions(), 15_000);

  return (
    <Panel title="Portfolio Greeks" badge="15s" loading={loading()} error={error() ?? undefined}>
      <Show when={data()}>
        {(d) => {
          const positions = d().positions || [];
          if (positions.length === 0) {
            return <div class="flex items-center justify-center h-full text-text-secondary text-[10px]">No open positions</div>;
          }

          // Aggregate Greeks across all positions
          let netDelta = 0, netGamma = 0, netTheta = 0, netVega = 0;
          for (const p of positions) {
            const qty = p.quantity ?? p.qty ?? 1;
            const g = p.greeks || {};
            netDelta += (g.delta ?? 0) * qty * 100;
            netGamma += (g.gamma ?? 0) * qty * 100;
            netTheta += (g.theta ?? 0) * qty * 100;
            netVega += (g.vega ?? 0) * qty * 100;
          }

          return (
            <div class="p-3 space-y-1">
              <DataRow label="Positions" value={positions.length} />
              <div class="mt-2 pt-2 border-t border-border-subtle">
                <DataRow label="Net Delta" value={fmtDelta(netDelta)} large color={netDelta >= 0 ? 'text-positive' : 'text-negative'} />
                <DataRow label="Net Gamma" value={netGamma.toFixed(2)} color="text-accent" />
                <DataRow label="Net Theta" value={`$${netTheta.toFixed(0)}/day`} color="text-negative" />
                <DataRow label="Net Vega" value={`$${netVega.toFixed(0)}`} />
              </div>

              <div class="mt-2 pt-2 border-t border-border-subtle">
                <span class="font-display text-[8px] text-text-secondary uppercase tracking-wider">Positions</span>
                <div class="mt-1 space-y-0.5">
                  <For each={positions.slice(0, 6)}>
                    {(p) => (
                      <div class="flex items-center justify-between text-[9px] font-data">
                        <span class="text-text-primary">
                          {p.strike} {p.option_type || p.right} {p.quantity ?? p.qty}x
                        </span>
                        <span class={p.pnl >= 0 ? 'text-positive' : 'text-negative'}>
                          {p.pnl != null ? `${p.pnl >= 0 ? '+' : ''}$${p.pnl.toFixed(0)}` : '—'}
                        </span>
                      </div>
                    )}
                  </For>
                </div>
              </div>
            </div>
          );
        }}
      </Show>
    </Panel>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// 8. SECTOR ROTATION
// ═══════════════════════════════════════════════════════════════════════════

export const SectorRotationPanel: Component = () => {
  const { data, loading, error } = usePoll(() => api.getSectors(), 60_000);

  return (
    <Panel title="Sector Rotation" badge="60s" loading={loading()} error={error() ?? undefined}>
      <Show when={data()}>
        {(d) => {
          const analysis = d().sectors || d();
          const sectors = (analysis.sectors || []).sort(
            (a: any, b: any) => (b.relative_strength ?? 0) - (a.relative_strength ?? 0)
          );

          return (
            <div class="text-[9px]">
              <div class="flex items-center px-2 py-1 border-b border-border-default text-text-secondary font-display tracking-wider sticky top-0 bg-surface-1 z-10">
                <span class="w-10">ETF</span>
                <span class="flex-1">SECTOR</span>
                <span class="w-14 text-right">RETURN</span>
                <span class="w-14 text-right">vs SPY</span>
                <span class="w-16 text-right">SIGNAL</span>
              </div>

              <For each={sectors}>
                {(s: any) => {
                  const rs = s.relative_strength ?? 0;
                  const ret = s.sector_return_pct ?? 0;
                  const dir = s.divergence_direction || 'none';

                  return (
                    <div class="flex items-center px-2 py-1 border-b border-border-subtle font-data">
                      <span class="w-10 text-text-primary font-medium">{s.symbol}</span>
                      <span class="flex-1 text-text-secondary">{s.name}</span>
                      <span class={`w-14 text-right ${ret >= 0 ? 'text-positive' : 'text-negative'}`}>
                        {ret >= 0 ? '+' : ''}{ret.toFixed(2)}%
                      </span>
                      <span class={`w-14 text-right ${rs >= 0 ? 'text-positive' : 'text-negative'}`}>
                        {rs >= 0 ? '+' : ''}{rs.toFixed(2)}%
                      </span>
                      <span class={`w-16 text-right text-[8px] font-medium ${
                        dir === 'leading_up' ? 'text-positive' :
                        dir === 'leading_down' ? 'text-negative' :
                        'text-text-secondary'
                      }`}>
                        {dir === 'leading_up' ? 'LEADING ↑' :
                         dir === 'leading_down' ? 'LEADING ↓' :
                         dir === 'lagging' ? 'LAGGING' : '—'}
                      </span>
                    </div>
                  );
                }}
              </For>

              <Show when={analysis.bond_signal && analysis.bond_signal !== 'neutral'}>
                <div class="px-2 py-1.5 border-t border-border-default">
                  <DataRow label="TLT (Bond)" value={`${(analysis.tlt_return_pct ?? 0).toFixed(2)}% — ${analysis.bond_signal}`} color={
                    analysis.bond_signal === 'risk_off' ? 'text-negative' : 'text-positive'
                  } />
                </div>
              </Show>
            </div>
          );
        }}
      </Show>
    </Panel>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// 9. KEY LEVELS
// ═══════════════════════════════════════════════════════════════════════════

export const KeyLevelsPanel: Component = () => {
  const { data, loading, error } = usePoll(
    () => api.getLevels(market.symbol),
    15_000,
  );

  return (
    <Panel title="Key Levels" badge="15s" loading={loading()} error={error() ?? undefined}>
      <Show when={data()}>
        {(d) => {
          const lvl = d();
          const levels = lvl.levels || [];

          return (
            <div class="p-3 space-y-1">
              <Show when={lvl.vwap}>
                <DataRow label="VWAP" value={fmtPrice(lvl.vwap)} color="text-cyan" />
              </Show>
              <Show when={lvl.bollinger}>
                <DataRow label="BB Upper" value={fmtPrice(lvl.bollinger?.upper)} />
                <DataRow label="BB Lower" value={fmtPrice(lvl.bollinger?.lower)} />
              </Show>
              <Show when={lvl.opening_range}>
                <DataRow label="OR High" value={fmtPrice(lvl.opening_range?.high)} color="text-positive" />
                <DataRow label="OR Low" value={fmtPrice(lvl.opening_range?.low)} color="text-negative" />
              </Show>

              <Show when={levels.length > 0}>
                <div class="mt-2 pt-2 border-t border-border-subtle">
                  <span class="font-display text-[8px] text-text-secondary uppercase tracking-wider">Support / Resistance</span>
                  <div class="mt-1 space-y-0.5">
                    <For each={levels.slice(0, 8)}>
                      {(l: any) => (
                        <div class="flex items-center justify-between text-[9px] font-data">
                          <span class="text-text-secondary">{l.label || l.type}</span>
                          <span class={`font-medium ${
                            l.type === 'resistance' ? 'text-negative' :
                            l.type === 'support' ? 'text-positive' : 'text-text-primary'
                          }`}>
                            {fmtPrice(l.price)}
                          </span>
                        </div>
                      )}
                    </For>
                  </div>
                </div>
              </Show>
            </div>
          );
        }}
      </Show>
    </Panel>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// EXPORTS
// ═══════════════════════════════════════════════════════════════════════════

export {
  // Re-export Panel utilities for external use
  Panel, DataRow, fmtPct, fmtPrice, fmtPremium, fmtDelta, fmtGex, fmtNum,
};
