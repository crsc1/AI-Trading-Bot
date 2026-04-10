import { type Component, Show, createMemo, createSignal } from 'solid-js';
import { OrderFlowChart } from '../charts/OrderFlowChart';
import { OptionsBubbleChart } from '../charts/OptionsBubbleChart';
import { OptionsFlow } from '../charts/OptionsFlow';
import { OptionsHeatmap } from '../charts/OptionsHeatmap';
import { market } from '../../signals/market';
import { optionsFlow } from '../../signals/optionsFlow';
import { WidgetFrame } from '../system/WidgetFrame';
import { StatusPill } from '../system/StatusPill';
import { Datum } from '../system/Datum';
import { SegmentedControl, type SegmentedOption } from '../system/SegmentedControl';

type FlowView = 'options' | 'equity';
const viewOptions: SegmentedOption<FlowView>[] = [
  { label: 'Options', value: 'options', testId: 'flow-view-options' },
  { label: 'Equity', value: 'equity', testId: 'flow-view-equity' },
];

export const Flow: Component = () => {
  const [view, setView] = createSignal<FlowView>('options');
  const bullPct = createMemo(() => {
    const total = optionsFlow.totalBullishPremium + optionsFlow.totalBearishPremium;
    if (total === 0) return 50;
    return Math.round((optionsFlow.totalBullishPremium / total) * 100);
  });
  const transportLabel = createMemo(() => {
    switch (market.transport) {
      case 'webtransport':
        return 'QUIC';
      case 'websocket':
        return 'WS';
      default:
        return 'Offline';
    }
  });
  const feedTone = createMemo(() => {
    if (!market.connected) return 'negative' as const;
    if (market.dataSource?.toLowerCase().includes('replay')) return 'warning' as const;
    return 'positive' as const;
  });

  return (
    <div data-testid="flow-page" class="h-full overflow-hidden bg-[linear-gradient(180deg,rgba(11,13,18,1),rgba(14,18,24,1))]">
      <div class="h-full min-h-0 p-3 flex flex-col gap-3">
        {/* Compact header bar — single row, no fat metric tiles */}
        <div class="shrink-0 flex items-center justify-between gap-3 px-4 py-2 rounded-xl border border-border-default bg-surface-1">
          <div class="flex items-center gap-3">
            <SegmentedControl options={viewOptions} value={view()} onChange={setView} />
            <span class="font-display text-[11px] text-text-secondary">
              {market.symbol}
            </span>
          </div>

          <div class="flex items-center gap-4">
            <Show when={view() === 'options'}>
              <span class="font-data text-[11px] text-text-secondary">
                {optionsFlow.tradeCount.toLocaleString()} trades
              </span>
              <span class="font-data text-[11px] text-positive">
                {formatPremium(optionsFlow.totalBullishPremium)}
              </span>
              <span class="font-data text-[11px] text-negative">
                {formatPremium(optionsFlow.totalBearishPremium)}
              </span>
              <span class="font-data text-[11px] text-accent">
                {bullPct()}% bull
              </span>
            </Show>
            <StatusPill label="Feed" value={transportLabel()} tone={market.connected ? 'accent' : 'negative'} compact />
          </div>
        </div>

        {/* Options view: bubble chart primary on top, tape underneath, sidebar for heatmap */}
        <Show when={view() === 'options'}>
          <div class="flex-1 min-h-0 grid gap-3 xl:grid-cols-[minmax(0,1fr)_320px]">
            {/* Main column: bubble chart (big) + tape (below) */}
            <div class="min-h-0 flex flex-col gap-3">
              <div class="flex-[60] min-h-0 rounded-2xl border-[1.5px] border-border-default bg-surface-1 shadow-[0_14px_32px_rgba(0,0,0,0.16)] overflow-hidden">
                <OptionsBubbleChart />
              </div>
              <div class="flex-[40] min-h-0 rounded-2xl border-[1.5px] border-border-default bg-surface-1 shadow-[0_14px_32px_rgba(0,0,0,0.16)] overflow-hidden">
                <OptionsFlow />
              </div>
            </div>

            {/* Sidebar: heatmap + flow bias */}
            <div class="min-h-0 flex flex-col gap-3">
              <div class="flex-[65] min-h-0 rounded-2xl border-[1.5px] border-border-default bg-surface-1 shadow-[0_14px_32px_rgba(0,0,0,0.16)] overflow-hidden">
                <OptionsHeatmap />
              </div>
              <WidgetFrame
                title="Flow Bias"
                subtitle="Directional pressure"
                badge={optionsFlow.tradeCount > 0 ? 'Active' : 'Waiting'}
                badgeTone={optionsFlow.tradeCount > 0 ? 'positive' : 'neutral'}
                contentClass="p-3"
              >
                <div>
                  <div class="flex items-center justify-between text-[10px] text-text-muted font-display uppercase tracking-[0.16em]">
                    <span>Bullish</span>
                    <span>Bearish</span>
                  </div>
                  <div class="mt-1.5 h-2.5 rounded-full overflow-hidden bg-surface-3 flex">
                    <div class="bg-positive/70" style={{ width: `${bullPct()}%` }} />
                    <div class="bg-negative/70" style={{ width: `${100 - bullPct()}%` }} />
                  </div>
                  <div class="mt-2 grid grid-cols-2 gap-2">
                    <Datum label="Data Source" value={(market.dataSource || 'Unknown').replace(/_/g, ' ')} />
                    <Datum label="Quote Source" value={(market.quoteSource || 'Unknown').replace(/_/g, ' ')} />
                  </div>
                </div>
              </WidgetFrame>
            </div>
          </div>
        </Show>

        {/* Equity view: order flow chart is primary */}
        <Show when={view() === 'equity'}>
          <div class="flex-1 min-h-0 flex flex-col gap-3">
            <div class="flex-1 min-h-[560px] rounded-2xl border-[1.5px] border-border-default bg-surface-1 shadow-[0_14px_32px_rgba(0,0,0,0.16)] overflow-hidden">
              <OrderFlowChart />
            </div>
            <div class="grid gap-3 xl:grid-cols-3">
              <WidgetFrame title="Equity Context" subtitle="Tape context" badge={market.connected ? 'Connected' : 'Offline'} badgeTone={feedTone()} contentClass="p-3">
                <div class="space-y-2">
                  <Datum label="Underlying" value={market.symbol} />
                  <Datum label="Transport" value={transportLabel()} />
                  <Datum label="Market Data" value={(market.dataSource || 'Unknown').replace(/_/g, ' ')} />
                </div>
              </WidgetFrame>
              <WidgetFrame title="Window" subtitle="Short-horizon tape view" badge="5min" badgeTone="positive" contentClass="p-3">
                <div class="space-y-2">
                  <Datum label="Visible Window" value="5 minutes" />
                  <Datum label="Aggregation" value="250ms buckets" />
                  <Datum label="Best With" value="Options flow + key levels" />
                </div>
              </WidgetFrame>
              <WidgetFrame title="Fallback" subtitle="REST backfill when ticks are thin" badge="REST" badgeTone="warning" contentClass="p-3">
                <div class="space-y-2">
                  <Datum label="Source" value="Recent Alpaca SIP trades" />
                  <Datum label="Behavior" value="Live socket + REST backfill" />
                </div>
              </WidgetFrame>
            </div>
          </div>
        </Show>
      </div>
    </div>
  );
};

function formatPremium(p: number): string {
  if (p >= 1_000_000) return `$${(p / 1_000_000).toFixed(1)}M`;
  if (p >= 1_000) return `$${(p / 1_000).toFixed(0)}K`;
  return `$${p.toFixed(0)}`;
}
