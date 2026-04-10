import { type Component, Show, createMemo, createSignal } from 'solid-js';
import { OrderFlowChart } from '../charts/OrderFlowChart';
import { OptionsBubbleChart } from '../charts/OptionsBubbleChart';
import { OptionsFlow } from '../charts/OptionsFlow';
import { OptionsHeatmap } from '../charts/OptionsHeatmap';
import { market } from '../../signals/market';
import { optionsFlow } from '../../signals/optionsFlow';
import { WidgetFrame } from '../system/WidgetFrame';
import { StatusPill } from '../system/StatusPill';
import { MetricTile } from '../system/MetricTile';
import { Datum } from '../system/Datum';
import { SegmentedControl, type SegmentedOption } from '../system/SegmentedControl';

type FlowView = 'options' | 'equity';
const viewOptions: SegmentedOption<FlowView>[] = [
  { label: 'Options Flow', value: 'options', testId: 'flow-view-options' },
  { label: 'Equity Flow', value: 'equity', testId: 'flow-view-equity' },
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
      <div class="h-full min-h-0 p-4 flex flex-col gap-4">
        <WidgetFrame
          title="Flow Workspace"
          subtitle={`${market.symbol} · ${view() === 'options' ? 'options executions and premium clusters' : 'equity tape and footprint context'}`}
          badge={view() === 'options' ? 'Options' : 'Equity'}
          badgeTone={view() === 'options' ? 'accent' : 'warning'}
          actions={
            <div class="flex flex-wrap items-center justify-end gap-2">
              <StatusPill label="Transport" value={transportLabel()} tone={market.connected ? 'accent' : 'negative'} compact />
              <StatusPill label="Feed" value={(market.dataSource || 'Unknown').replace(/_/g, ' ')} tone={feedTone()} compact />
            </div>
          }
          contentClass="px-5 py-4"
        >
          <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <MetricTile label="Trades" value={optionsFlow.tradeCount.toLocaleString()} />
            <MetricTile label="Bull Premium" value={formatPremium(optionsFlow.totalBullishPremium)} tone="text-positive" />
            <MetricTile label="Bear Premium" value={formatPremium(optionsFlow.totalBearishPremium)} tone="text-negative" />
            <MetricTile label="Bull Ratio" value={`${bullPct()}%`} tone="text-accent" />
            <MetricTile label="Linked Symbol" value={market.symbol} />
          </div>

          <div class="mt-4 flex flex-wrap items-center gap-2">
            <SegmentedControl options={viewOptions} value={view()} onChange={setView} />
          </div>
        </WidgetFrame>

        <Show when={view() === 'options'}>
          <div class="flex-1 min-h-0 grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
            <div class="min-h-0 flex flex-col gap-4">
              <div class="flex-[48] min-h-0 rounded-2xl border-[1.5px] border-border-default bg-surface-1 shadow-[0_14px_32px_rgba(0,0,0,0.16)] overflow-hidden">
                <OptionsBubbleChart />
              </div>
              <div class="flex-[52] min-h-0 rounded-2xl border-[1.5px] border-border-default bg-surface-1 shadow-[0_14px_32px_rgba(0,0,0,0.16)] overflow-hidden">
                <OptionsFlow />
              </div>
            </div>

            <div class="min-h-0 flex flex-col gap-4">
              <div class="flex-[58] min-h-0 rounded-2xl border-[1.5px] border-border-default bg-surface-1 shadow-[0_14px_32px_rgba(0,0,0,0.16)] overflow-hidden">
                <OptionsHeatmap />
              </div>
              <WidgetFrame
                title="Flow Bias"
                subtitle="At-a-glance directional pressure"
                badge={optionsFlow.tradeCount > 0 ? 'Active' : 'Waiting'}
                badgeTone={optionsFlow.tradeCount > 0 ? 'positive' : 'neutral'}
                contentClass="p-3"
              >
                <div class="space-y-3">
                  <div>
                    <div class="flex items-center justify-between text-[10px] text-text-muted font-display uppercase tracking-[0.16em]">
                      <span>Bullish</span>
                      <span>Bearish</span>
                    </div>
                    <div class="mt-2 h-3 rounded-full overflow-hidden bg-surface-3 flex">
                      <div class="bg-positive/70" style={{ width: `${bullPct()}%` }} />
                      <div class="bg-negative/70" style={{ width: `${100 - bullPct()}%` }} />
                    </div>
                  </div>

                  <Datum label="Data Source" value={(market.dataSource || 'Unknown').replace(/_/g, ' ')} />
                  <Datum label="Quote Source" value={(market.quoteSource || 'Unknown').replace(/_/g, ' ')} />
                  <Datum label="Trade Feed" value={optionsFlow.tradeCount > 0 ? 'Streaming' : 'Awaiting prints'} />
                </div>
              </WidgetFrame>
            </div>
          </div>
        </Show>

        <Show when={view() === 'equity'}>
          <div class="flex-1 min-h-0 flex flex-col gap-4">
            <div class="flex-1 min-h-[560px] rounded-2xl border-[1.5px] border-border-default bg-surface-1 shadow-[0_14px_32px_rgba(0,0,0,0.16)] overflow-hidden">
              <OrderFlowChart />
            </div>
            <div class="grid gap-4 xl:grid-cols-4">
              <WidgetFrame
                title="Equity Context"
                subtitle="Tape context for the linked underlying"
                badge={market.connected ? 'Connected' : 'Offline'}
                badgeTone={feedTone()}
                contentClass="p-3"
              >
                <div class="space-y-3">
                  <Datum label="Underlying" value={market.symbol} />
                  <Datum label="Transport" value={transportLabel()} />
                  <Datum label="Market Data" value={(market.dataSource || 'Unknown').replace(/_/g, ' ')} />
                </div>
              </WidgetFrame>
              <WidgetFrame
                title="Interpretation"
                subtitle="What this chart should help confirm"
                badge="Workflow"
                badgeTone="accent"
                contentClass="p-3"
              >
                <div class="space-y-3">
                  <Datum label="Use Case" value="Read aggressive tape pressure around price inflection" />
                  <Datum label="Best Paired With" value="Options flow, key levels, and the active chart" />
                </div>
              </WidgetFrame>
              <WidgetFrame
                title="Window"
                subtitle="Short-horizon tape view"
                badge="Expanded"
                badgeTone="positive"
                contentClass="p-3"
              >
                <div class="space-y-3">
                  <Datum label="Visible Window" value="5 minutes" />
                  <Datum label="Aggregation" value="250ms buckets" />
                </div>
              </WidgetFrame>
              <WidgetFrame
                title="Fallback"
                subtitle="Keeps the chart alive when engine ticks are thin"
                badge="REST"
                badgeTone="warning"
                contentClass="p-3"
              >
                <div class="space-y-3">
                  <Datum label="Source" value="Recent Alpaca SIP trades" />
                  <Datum label="Behavior" value="Live socket plus overlapping REST trade backfill" />
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
