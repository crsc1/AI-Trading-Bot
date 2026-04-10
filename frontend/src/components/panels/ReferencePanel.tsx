/**
 * Reference panels — 9 options-first data panels.
 * Shared polling now lives in the Reference workspace runtime; panels read cached state.
 */
import { type Component, For, Show, createMemo } from 'solid-js';
import { type MarketStructureLevels } from '../../lib/api';
import { market } from '../../signals/market';
import { optionsFlow } from '../../signals/optionsFlow';
import { chainState } from '../../signals/chain';
import { reference } from '../../signals/reference';
import { signals } from '../../signals/signals';
import { Panel, DataRow, fmtPct, fmtPrice, fmtPremium, fmtDelta, fmtGex, fmtNum } from '../shared/Panel';
import { EmptyState } from '../system/EmptyState';
import { TableShell, type TableColumn } from '../system/TableShell';

const chainColumns: TableColumn[] = [
  { label: 'IV', width: '10.5%', align: 'right' },
  { label: 'Delta', width: '10.5%', align: 'right' },
  { label: 'Last', width: '11%', align: 'right' },
  { label: 'Vol', width: '10%', align: 'right' },
  { label: 'Strike', width: '16%', align: 'center', class: 'text-text-primary' },
  { label: 'Last', width: '11%', align: 'right' },
  { label: 'Delta', width: '10.5%', align: 'right' },
  { label: 'IV', width: '10.5%', align: 'right' },
  { label: 'Vol', width: '10%', align: 'right' },
];

const denseTableHeaderClass = 'flex items-center px-4 py-3 border-b-[1.5px] border-border-default text-text-secondary font-display font-semibold tracking-[0.14em] sticky top-0 bg-surface-1 z-10';
const denseTableRowClass = 'flex items-center px-4 py-2.5 border-b border-border-subtle font-data min-h-[42px]';

// ═══════════════════════════════════════════════════════════════════════════
// 1. OPTIONS CHAIN
// ═══════════════════════════════════════════════════════════════════════════

export const OptionsChainPanel: Component = () => {
  const spot = () => chainState.spotPrice || market.lastPrice;

  const visible = createMemo(() => {
    const strikes = chainState.strikes;
    if (strikes.size === 0) return [];
    const sorted = [...strikes.entries()].sort(([a], [b]) => a - b);
    const atmIdx = sorted.findIndex(([s]) => s >= spot());
    const start = Math.max(0, atmIdx - 6);
    return sorted.slice(start, start + 13);
  });

  return (
    <Panel title="Options Chain" badge="LIVE" badgeColor="positive" loading={reference.chainLoading} error={reference.chainError ?? undefined}>
      <Show when={visible().length > 0} fallback={
        <Show when={!reference.chainLoading}>
          <EmptyState
            eyebrow="Options Chain"
            title="No chain data available"
            description={reference.expiration
              ? `The ${reference.expiration} snapshot returned no usable strikes around the active symbol yet.`
              : 'No expiration was resolved for the active symbol, so the chain could not be built.'}
          />
        </Show>
      }>
        <TableShell columns={chainColumns} tableClass="text-[10px]">
          <For each={visible()}>
            {([strike, row]) => {
              const isATM = () => Math.abs(strike - spot()) < 0.5;
              return (
                <tr class={`border-b border-border-subtle font-data min-h-[42px] ${isATM() ? 'bg-accent/6' : ''}`}>
                  <td class="text-right px-4 py-2.5 text-text-secondary">{row.call.iv != null ? fmtPct(row.call.iv * 100) : '—'}</td>
                  <td class="text-right px-4 py-2.5 text-positive">{row.call.delta != null ? fmtDelta(row.call.delta) : '—'}</td>
                  <td class="text-right px-4 py-2.5 text-text-primary font-semibold">{row.call.last > 0 ? row.call.last.toFixed(2) : '—'}</td>
                  <td class="text-right px-4 py-2.5 text-text-secondary">{row.call.volume > 0 ? fmtNum(row.call.volume) : '—'}</td>

                  <td class={`text-center px-4 py-2.5 font-semibold ${isATM() ? 'text-accent' : 'text-text-primary'}`}>
                    {strike}
                  </td>

                  <td class="text-right px-4 py-2.5 text-text-primary font-semibold">{row.put.last > 0 ? row.put.last.toFixed(2) : '—'}</td>
                  <td class="text-right px-4 py-2.5 text-negative">{row.put.delta != null ? fmtDelta(row.put.delta) : '—'}</td>
                  <td class="text-right px-4 py-2.5 text-text-secondary">{row.put.iv != null ? fmtPct(row.put.iv * 100) : '—'}</td>
                  <td class="text-right px-4 py-2.5 text-text-secondary">{row.put.volume > 0 ? fmtNum(row.put.volume) : '—'}</td>
                </tr>
              );
            }}
          </For>
        </TableShell>
      </Show>
    </Panel>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// 2. IV DASHBOARD
// ═══════════════════════════════════════════════════════════════════════════

export const IVDashboardPanel: Component = () => {
  // Live ATM IV from chain store (WS-driven)
  const liveIv = () => chainState.atmIv;

  return (
    <Panel title="IV Dashboard" badge="LIVE" badgeColor="positive" loading={reference.volatility.loading} error={reference.volatility.error ?? undefined}>
      <Show when={reference.volatility.data}>
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
            <div class="p-5 space-y-1">
              <DataRow label="ATM IV" value={fmtPct(atmIv != null ? atmIv * 100 : null)} large />
              <DataRow label="IV Rank" value={fmtPct(ivRank)} color={rankColor} large />
              <DataRow label="IV Percentile" value={fmtPct(ivPct)} />
              <DataRow label="Vol Regime" value={regime || '—'} color={
                regime === 'high' ? 'text-warning' : regime === 'low' ? 'text-positive' : 'text-text-primary'
              } />
              <Show when={v['52w_high'] || v['52w_low']}>
                <div class="mt-3 pt-3 border-t border-border-subtle">
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
  return (
    <Panel title="Options Snapshot" badge="30s" loading={reference.snapshot.loading} error={reference.snapshot.error ?? undefined}>
      <Show when={reference.snapshot.data}>
        {(d) => {
          const s = d();
          const pcrVol = s.pcr_vol ?? s.pcr_volume;
          const pcrOI = s.pcr_oi;

          return (
            <div class="p-5 space-y-1">
              <DataRow label="Max Pain" value={fmtPrice(s.max_pain)} large color="text-warning" />
              <DataRow label="PCR (Volume)" value={pcrVol != null ? pcrVol.toFixed(2) : '—'} color={
                pcrVol != null ? (pcrVol > 1 ? 'text-negative' : pcrVol < 0.7 ? 'text-positive' : 'text-text-primary') : 'text-text-primary'
              } />
              <DataRow label="PCR (OI)" value={pcrOI != null ? pcrOI.toFixed(2) : '—'} />
              <div class="mt-3 pt-3 border-t border-border-subtle">
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
  const topStrikeEntries = createMemo(() =>
    Object.entries(reference.gex.data?.strike_gex || {})
      .sort(([, a]: any, [, b]: any) => Math.abs(b as number) - Math.abs(a as number))
      .slice(0, 6)
  );

  return (
    <Panel title="GEX Levels" badge="30s" loading={reference.gex.loading} error={reference.gex.error ?? undefined}>
      <Show when={reference.gex.data}>
        {(d) => {
          const g = d();
          return (
            <div class="p-5 space-y-1">
              <DataRow label="Regime" value={g.regime || '—'} large color={
                g.regime === 'bullish' ? 'text-positive' : g.regime === 'bearish' ? 'text-negative' : 'text-text-primary'
              } />
              <DataRow label="Flip Level" value={fmtPrice(g.flip_level)} color="text-warning" />
              <DataRow label="Max Gamma" value={fmtPrice(g.max_gamma_strike)} color="text-accent" />
              <DataRow label="Net GEX" value={fmtGex(g.current_gex)} color={
                g.current_gex > 0 ? 'text-positive' : 'text-negative'
              } />

              <Show when={topStrikeEntries().length > 0} fallback={
                <div class="mt-3 pt-3 border-t border-border-subtle">
                  <div class="text-[11px] text-text-muted">
                    No strike-level gamma concentrations were returned by the backend for this refresh.
                  </div>
                </div>
              }>
                <div class="mt-3 pt-3 border-t border-border-subtle">
                  <span class="font-display text-[9px] font-semibold text-text-secondary uppercase tracking-[0.14em]">Top Strikes</span>
                  <div class="mt-2 space-y-1">
                    <For each={topStrikeEntries()}>
                      {([strike, val]) => (
                        <div class="flex items-center justify-between text-[10px] font-data">
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
      <div class="p-5 space-y-1">
        <DataRow label="Current Price" value={fmtPrice(price())} large />
        <DataRow label="ATM IV" value={fmtPct(atmIv() * 100)} />
        <div class="mt-3 pt-3 border-t border-border-subtle">
          <DataRow label="Daily ±" value={fmtPrice(dailyMove())} large color="text-accent" />
          <DataRow label="Daily Range" value={`${fmtPrice(price() - dailyMove())} — ${fmtPrice(price() + dailyMove())}`} />
        </div>
        <div class="mt-3 pt-3 border-t border-border-subtle">
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
  const emptyMessage = createMemo(() => {
    if (optionsFlow.tradeCount === 0) {
      return `No live option prints for ${market.symbol} have been classified yet. Waiting for ThetaDataDx trade flow.`;
    }
    return `Live trades are flowing for ${market.symbol}, but none in the current buffer were tagged as sweeps, blocks, or whales.`;
  });

  return (
    <Panel title="Unusual Activity" badge="LIVE" badgeColor="positive">
      <Show when={notable().length > 0} fallback={
        <EmptyState
          eyebrow="Unusual Activity"
          title="No tagged flow right now"
          description={emptyMessage()}
        />
      }>
        <div class="text-[10px]">
          <div class={denseTableHeaderClass}>
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
                <div class={`${denseTableRowClass} ${
                  t.side === 'buy' ? 'bg-positive/5' : t.side === 'sell' ? 'bg-negative/5' : 'bg-transparent'
                }`}>
                  <span class="w-14 text-text-secondary text-[9px]">
                    {new Date(t.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
                  </span>
                  <span class={`w-10 text-[9px] font-semibold ${
                    t.tag === 'whale' ? 'text-warning' : t.tag === 'sweep' ? 'text-accent' : 'text-text-secondary'
                  }`}>
                    {t.tag.toUpperCase()}
                  </span>
                  <span class={`w-7 font-semibold ${t.right === 'C' ? 'text-positive' : 'text-negative'}`}>{t.right}</span>
                  <span class="w-10 text-right text-text-primary">{t.strike}</span>
                  <span class={`w-10 text-right ${sideColor}`}>{t.size}</span>
                  <span class={`flex-1 text-right font-semibold ${sideColor}`}>{fmtPremium(t.premium)}</span>
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
  const positions = () => (signals.positions as any[]) || [];

  return (
    <Panel title="Portfolio Greeks" badge="LIVE" badgeColor="positive" loading={signals.positionsLoading}>
      <Show when={positions()}>
        {(d) => {
          const currentPositions = d() as any[];
          if (currentPositions.length === 0) {
            return (
              <EmptyState
                eyebrow="Portfolio Greeks"
                title="No open positions"
                description="The portfolio service returned zero open contracts, so there are no portfolio Greeks to aggregate."
              />
            );
          }

          // Aggregate Greeks across all positions
          let netDelta = 0, netGamma = 0, netTheta = 0, netVega = 0;
          for (const p of currentPositions) {
            const qty = p.quantity ?? p.qty ?? 1;
            const g = p.greeks || {};
            netDelta += (g.delta ?? 0) * qty * 100;
            netGamma += (g.gamma ?? 0) * qty * 100;
            netTheta += (g.theta ?? 0) * qty * 100;
            netVega += (g.vega ?? 0) * qty * 100;
          }

          return (
            <div class="p-5 space-y-1">
              <DataRow label="Positions" value={currentPositions.length} />
              <div class="mt-3 pt-3 border-t border-border-subtle">
                <DataRow label="Net Delta" value={fmtDelta(netDelta)} large color={netDelta >= 0 ? 'text-positive' : 'text-negative'} />
                <DataRow label="Net Gamma" value={netGamma.toFixed(2)} color="text-accent" />
                <DataRow label="Net Theta" value={`$${netTheta.toFixed(0)}/day`} color="text-negative" />
                <DataRow label="Net Vega" value={`$${netVega.toFixed(0)}`} />
              </div>

              <div class="mt-3 pt-3 border-t border-border-subtle">
                <span class="font-display text-[9px] font-semibold text-text-secondary uppercase tracking-[0.14em]">Positions</span>
                <div class="mt-2 space-y-1">
                  <For each={currentPositions.slice(0, 6)}>
                    {(p) => (
                      <div class="flex items-center justify-between text-[10px] font-data">
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
  return (
    <Panel title="Sector Rotation" badge="60s" loading={reference.sectors.loading} error={reference.sectors.error ?? undefined}>
      <Show when={reference.sectors.data}>
        {(d) => {
          const analysis = d().sectors || d();
          const sectors = (analysis.sectors || []).sort(
            (a: any, b: any) => (b.relative_strength ?? 0) - (a.relative_strength ?? 0)
          );

          if (sectors.length === 0) {
            return (
              <EmptyState
                eyebrow="Sector Rotation"
                title="No sector rows available"
                description="The backend returned an empty sector list for this refresh, so there is no rotation table to rank right now."
              />
            );
          }

          return (
            <div class="text-[10px]">
              <div class={denseTableHeaderClass}>
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
                    <div class={denseTableRowClass}>
                      <span class="w-10 text-text-primary font-semibold">{s.symbol}</span>
                      <span class="flex-1 text-text-secondary">{s.name}</span>
                      <span class={`w-14 text-right ${ret >= 0 ? 'text-positive' : 'text-negative'}`}>
                        {ret >= 0 ? '+' : ''}{ret.toFixed(2)}%
                      </span>
                      <span class={`w-14 text-right ${rs >= 0 ? 'text-positive' : 'text-negative'}`}>
                        {rs >= 0 ? '+' : ''}{rs.toFixed(2)}%
                      </span>
                      <span class={`w-16 text-right text-[9px] font-semibold ${
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
                <div class="px-4 py-3 border-t border-border-default">
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
  return (
    <Panel title="Key Levels" badge="15s" loading={reference.levels.loading} error={reference.levels.error ?? undefined}>
      <Show when={reference.levels.data}>
        {(d) => {
          const lvl = d();
          const structure: MarketStructureLevels = lvl.levels || {};
          const levels = [
            { label: 'HOD', price: structure.hod, type: 'resistance' },
            { label: 'LOD', price: structure.lod, type: 'support' },
            { label: 'Pivot', price: structure.pivot, type: 'reference' },
            { label: 'R1', price: structure.r1, type: 'resistance' },
            { label: 'S1', price: structure.s1, type: 'support' },
            { label: 'R2', price: structure.r2, type: 'resistance' },
            { label: 'S2', price: structure.s2, type: 'support' },
            { label: 'POC', price: structure.poc, type: 'reference' },
            { label: 'Prev High', price: structure.prev_high, type: 'resistance' },
            { label: 'Prev Low', price: structure.prev_low, type: 'support' },
          ].filter((level): level is { label: string; price: number; type: string } =>
            typeof level.price === 'number' && level.price > 0
          );

          return (
            <div class="p-5 space-y-1">
              <Show when={structure.vwap}>
                <DataRow label="VWAP" value={fmtPrice(structure.vwap)} color="text-accent" />
              </Show>
              <Show when={structure.bb_upper || structure.bb_lower}>
                <DataRow label="BB Upper" value={fmtPrice(structure.bb_upper)} />
                <DataRow label="BB Lower" value={fmtPrice(structure.bb_lower)} />
              </Show>
              <Show when={structure.orb_5_high || structure.orb_5_low}>
                <DataRow label="OR High" value={fmtPrice(structure.orb_5_high)} color="text-positive" />
                <DataRow label="OR Low" value={fmtPrice(structure.orb_5_low)} color="text-negative" />
              </Show>

              <Show when={levels.length > 0}>
                <div class="mt-3 pt-3 border-t border-border-subtle">
                  <span class="font-display text-[9px] font-semibold text-text-secondary uppercase tracking-[0.14em]">Support / Resistance</span>
                  <div class="mt-2 space-y-1">
                    <For each={levels.slice(0, 8)}>
                      {(l: any) => (
                        <div class="flex items-center justify-between text-[10px] font-data">
                          <span class="text-text-secondary">{l.label || l.type}</span>
                          <span class={`font-semibold ${
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
