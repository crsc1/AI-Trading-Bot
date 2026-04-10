import { type Component, createEffect, createMemo, on, onMount, onCleanup } from 'solid-js';
import { market } from '../../signals/market';
import { chainState } from '../../signals/chain';
import { reference } from '../../signals/reference';
import { signals } from '../../signals/signals';
import { subscribePositionSummary, unsubscribePositionSummary } from '../../runtime/signalsRuntime';
import { refreshReferenceSymbolData, subscribeReferenceRuntime, unsubscribeReferenceRuntime } from '../../runtime/referenceRuntime';
import {
  OptionsChainPanel,
  IVDashboardPanel,
  OptionsSnapshotPanel,
  GexPanel,
  ExpectedMovePanel,
  UnusualActivityPanel,
  PortfolioGreeksPanel,
  SectorRotationPanel,
  KeyLevelsPanel,
} from '../panels/ReferencePanel';
import { WidgetFrame } from '../system/WidgetFrame';
import { StatusPill } from '../system/StatusPill';
import { MetricTile } from '../system/MetricTile';

const tile = 'rounded-2xl border-[1.5px] border-border-default bg-surface-1 overflow-hidden shadow-[0_14px_32px_rgba(0,0,0,0.16)] min-h-[300px]';
const tallTile = `${tile} min-h-[624px]`;

export const Reference: Component = () => {
  onMount(() => {
    subscribeReferenceRuntime();
    subscribePositionSummary();
  });

  onCleanup(() => {
    unsubscribeReferenceRuntime();
    unsubscribePositionSummary();
  });

  createEffect(
    on(() => market.symbol, () => {
      void refreshReferenceSymbolData(true);
    }, { defer: true })
  );

  const levelsReady = createMemo(() => !reference.levels.loading && !reference.levels.error && !!reference.levels.data);
  const atmIv = createMemo(() => chainState.atmIv != null ? `${(chainState.atmIv * 100).toFixed(1)}%` : '—');
  const maxPain = createMemo(() => {
    const value = reference.snapshot.data?.max_pain;
    return value != null && isFinite(value) ? `$${value.toFixed(2)}` : '—';
  });
  const flipLevel = createMemo(() => {
    const value = reference.gex.data?.flip_level;
    return value != null && isFinite(value) ? `$${value.toFixed(2)}` : '—';
  });
  const dailyMove = createMemo(() => {
    const iv = chainState.atmIv;
    if (!iv || market.lastPrice <= 0) return '—';
    const move = market.lastPrice * iv * Math.sqrt(1 / 365);
    return `$${move.toFixed(2)}`;
  });
  const expiryLabel = createMemo(() => reference.expiration || 'Nearest pending');

  return (
    <div data-testid="reference-page" class="h-full overflow-y-auto bg-[linear-gradient(180deg,rgba(11,13,18,1),rgba(14,18,24,1))]">
      <div class="p-4 flex flex-col gap-4 min-h-full">
        <WidgetFrame
          title="Reference Workspace"
          subtitle={`${market.symbol} · options chain, levels, volatility, and positioning references`}
          badge={reference.chainLoading ? 'Refreshing' : 'Ready'}
          badgeTone={reference.chainLoading ? 'warning' : 'positive'}
          actions={
            <div class="flex flex-wrap items-center justify-end gap-2">
              <StatusPill label="Symbol" value={market.symbol} tone="accent" compact />
              <StatusPill label="Expiry" value={expiryLabel()} tone="neutral" compact />
              <StatusPill label="Levels" value={levelsReady() ? 'Loaded' : reference.levels.loading ? 'Loading' : 'Check'} tone={levelsReady() ? 'positive' : reference.levels.loading ? 'warning' : 'negative'} compact />
            </div>
          }
          contentClass="px-5 py-4"
        >
          <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricTile label="ATM IV" value={atmIv()} />
            <MetricTile label="Gamma Flip" value={flipLevel()} tone="text-accent" />
            <MetricTile label="Max Pain" value={maxPain()} tone="text-warning" />
            <MetricTile label="Open Positions" value={String(signals.positions.length)} subvalue={`Daily move ${dailyMove()}`} />
          </div>
        </WidgetFrame>

        <div class="grid gap-4 2xl:grid-cols-[minmax(0,1.65fr)_minmax(340px,1fr)] xl:grid-cols-1">
          <div class="min-h-0">
            <div class={tallTile}><OptionsChainPanel /></div>
          </div>

          <div class="grid gap-4 md:grid-cols-2 2xl:grid-cols-1 2xl:auto-rows-[304px]">
            <div class={tile}><KeyLevelsPanel /></div>
            <div class={tile}><IVDashboardPanel /></div>
          </div>
        </div>

        <div class="grid gap-4 2xl:grid-cols-4 xl:grid-cols-2 auto-rows-[320px]">
          <div class={tile}><OptionsSnapshotPanel /></div>
          <div class={tile}><ExpectedMovePanel /></div>
          <div class={tile}><GexPanel /></div>
          <div class={tile}><PortfolioGreeksPanel /></div>
          <div class={`${tile} 2xl:col-span-2`}><UnusualActivityPanel /></div>
          <div class={`${tile} 2xl:col-span-2`}><SectorRotationPanel /></div>
        </div>
      </div>
    </div>
  );
};
