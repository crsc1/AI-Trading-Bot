import { type Component, Show, For, createEffect, on, onMount, onCleanup } from 'solid-js';
import { market } from '../../signals/market';
import { agent } from '../../signals/agent';
import { signals } from '../../signals/signals';
import { loadCandles } from '../../lib/data';
import { subscribePositionSummary, subscribeSignalFeed, unsubscribePositionSummary, unsubscribeSignalFeed } from '../../runtime/signalsRuntime';
import { WidgetFrame } from '../system/WidgetFrame';
import { MetricTile } from '../system/MetricTile';
import { StatusPill } from '../system/StatusPill';
import { EmptyState } from '../system/EmptyState';

const actionColors: Record<string, string> = {
  BUY_CALL: 'text-positive',
  BUY_PUT: 'text-negative',
  NO_TRADE: 'text-text-muted',
};

const tierColors: Record<string, string> = {
  TEXTBOOK: 'bg-positive/20 text-positive border-positive/30',
  HIGH: 'bg-accent/20 text-accent border-accent/30',
  VALID: 'bg-warning/20 text-warning border-warning/30',
  DEVELOPING: 'bg-surface-3 text-text-muted border-border-default',
};

export const Dashboard: Component = () => {
  onMount(() => {
    subscribeSignalFeed();
    subscribePositionSummary();
  });

  onCleanup(() => {
    unsubscribeSignalFeed();
    unsubscribePositionSummary();
  });

  createEffect(
    on(() => `${market.interval}|${market.range}`, () => loadCandles(), { defer: true })
  );

  const pnlColor = (v: number) => (v >= 0 ? 'text-positive' : 'text-negative');
  const pnlSign = (v: number) => (v >= 0 ? '+' : '');
  const marketStatusTone = () => {
    if (!market.connected) return 'negative' as const;
    if (market.dataSource?.toLowerCase().includes('replay')) return 'warning' as const;
    return 'positive' as const;
  };

  return (
    <div data-testid="dashboard-page" class="h-full overflow-y-auto bg-[linear-gradient(180deg,rgba(11,13,18,1),rgba(14,18,24,1))]">
      <div class="max-w-[1380px] mx-auto p-4 flex flex-col gap-4">
        <WidgetFrame
          title="Dashboard"
          subtitle="Session performance, open exposure, and latest signal context"
          badge={market.connected ? 'Online' : 'Offline'}
          badgeTone={marketStatusTone()}
          actions={
            <div class="flex flex-wrap items-center gap-2">
              <StatusPill label="Symbol" value={market.symbol} tone="accent" compact />
              <StatusPill label="Brain" value={agent.brain.status.toUpperCase()} tone={agent.brain.status === 'analyzing' ? 'positive' : agent.brain.status === 'error' ? 'negative' : 'neutral'} compact />
              <StatusPill label="Feed" value={market.dataSource?.replace(/_/g, ' ') || 'Waiting'} tone={marketStatusTone()} compact />
            </div>
          }
          contentClass="px-5 py-4"
        >
          <h1 data-testid="dashboard-title" class="sr-only">Dashboard</h1>
          <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricTile
              label="Daily P&L"
              value={`${pnlSign(signals.daily.total_pnl)}$${signals.daily.total_pnl.toFixed(2)}`}
              tone={pnlColor(signals.daily.total_pnl)}
            />
            <MetricTile
              label="Win Rate"
              value={signals.daily.trades_today > 0
                ? `${(signals.daily.win_rate * 100).toFixed(0)}%`
                : '—'
              }
              subvalue={signals.daily.trades_today > 0
                ? `${signals.daily.win_count}W / ${signals.daily.loss_count}L`
                : 'No trades today'
              }
            />
            <MetricTile
              label="Trades Today"
              value={`${signals.daily.trades_today}`}
              subvalue={signals.daily.trades_today > 0 ? `${signals.daily.win_count} wins / ${signals.daily.loss_count} losses` : 'No fills yet'}
            />
            <MetricTile
              label="Brain Status"
              value={agent.brain.status.toUpperCase()}
              tone={agent.brain.status === 'analyzing' ? 'text-positive' : 'text-text-primary'}
              subvalue={agent.brain.cycle_number > 0 ? `Cycle ${agent.brain.cycle_number}` : 'Awaiting cycle'}
            />
          </div>
        </WidgetFrame>

        <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <WidgetFrame title="Open Positions" subtitle="Live option exposure and current P&L" badge={signals.positions.length > 0 ? `${signals.positions.length}` : 'Flat'} badgeTone={signals.positions.length > 0 ? 'accent' : 'neutral'} contentClass="p-0">
            <Show when={signals.positions.length === 0} fallback={
              <div class="p-5 space-y-0">
                <For each={signals.positions}>
                  {(pos) => {
                    const pnl = pos.unrealized_pnl || 0;
                    const pnlPct = pos.unrealized_pnl_pct || 0;
                    return (
                      <div class="flex items-center justify-between gap-4 px-5 py-3 border-b border-border-subtle last:border-0 min-h-[56px]">
                        <div class="min-w-0">
                          <div class={`text-[13px] font-semibold ${pos.option_type === 'call' ? 'text-positive' : 'text-negative'}`}>
                            {pos.strike} {pos.option_type?.toUpperCase()}
                          </div>
                          <div class="mt-1 text-[11px] text-text-muted font-data">
                            {pos.symbol || market.symbol} · {pos.contracts} contracts
                          </div>
                        </div>
                        <div class="text-right shrink-0">
                          <div class={`text-[13px] font-semibold ${pnlColor(pnl)}`}>
                            {pnlSign(pnl)}${pnl.toFixed(2)}
                          </div>
                          <div class={`mt-1 text-[11px] font-data ${pnlColor(pnlPct)}`}>
                            {pnlSign(pnlPct)}{pnlPct.toFixed(1)}%
                          </div>
                        </div>
                      </div>
                    );
                  }}
                </For>
              </div>
            }>
              <EmptyState
                eyebrow="Positions"
                title="No open positions"
                description="The portfolio is flat right now, so there is no live exposure to monitor here."
              />
            </Show>
          </WidgetFrame>

          <WidgetFrame title="Latest Signal" subtitle="Most recent setup and confidence summary" badge={signals.latest ? signals.latest.tier : 'Waiting'} badgeTone={signals.latest ? (signals.latest.tier === 'TEXTBOOK' ? 'positive' : signals.latest.tier === 'VALID' ? 'warning' : 'accent') : 'neutral'} contentClass="p-5">
            <Show when={signals.latest} fallback={
              <EmptyState
                eyebrow="Signals"
                title="No signals yet"
                description="The signal engine has not published a trade setup in the current session."
              />
            }>
              {(sig) => (
                <div class="space-y-4">
                  <div class="flex items-center justify-between gap-4">
                    <span class={`text-[14px] font-semibold ${actionColors[sig().action] || 'text-text-primary'}`}>
                      {sig().action.replace('_', ' ')}
                    </span>
                    <span class={`text-[10px] px-2.5 py-1 rounded-full border font-display font-semibold uppercase tracking-[0.14em] ${tierColors[sig().tier] || tierColors.DEVELOPING}`}>
                      {sig().tier}
                    </span>
                  </div>
                  <div class="grid grid-cols-3 gap-3">
                    <MetricTile label="Confidence" value={`${(sig().confidence * 100).toFixed(0)}%`} />
                    <MetricTile label="Strike" value={sig().strike ? `$${sig().strike}` : '—'} />
                    <MetricTile label="Entry" value={sig().entry_price ? `$${sig().entry_price.toFixed(2)}` : '—'} />
                  </div>
                  <Show when={sig().reasoning}>
                    <div class="rounded-xl border-[1.5px] border-border-default bg-surface-2/72 px-4 py-3 text-[12px] text-text-secondary leading-relaxed">
                      {sig().reasoning}
                    </div>
                  </Show>
                </div>
              )}
            </Show>
          </WidgetFrame>
        </div>

        <WidgetFrame title="Signal History" subtitle="Recent signal decisions and realized outcomes" badge={signals.history.length > 0 ? `${Math.min(signals.history.length, 20)} rows` : 'Quiet'} badgeTone={signals.history.length > 0 ? 'accent' : 'neutral'} contentClass="p-0">
          <Show when={signals.history.length > 0} fallback={
            <EmptyState
              eyebrow="Signal History"
              title="No recent signal history"
              description="Recent signal decisions will appear here once the engine has logged them."
            />
          }>
            <div class="overflow-y-auto max-h-[320px]">
              <For each={signals.history.slice(0, 20)}>
                {(sig) => (
                  <div class="flex items-center justify-between gap-4 px-5 py-3 border-b border-border-subtle hover:bg-surface-2/30 min-h-[56px]">
                    <div class="flex items-center gap-3 min-w-0">
                      <span class={`text-[11px] font-semibold w-14 ${actionColors[sig.action] || 'text-text-muted'}`}>
                        {sig.action === 'NO_TRADE' ? 'HOLD' : sig.action.replace('BUY_', '')}
                      </span>
                      <Show when={sig.tier && sig.action !== 'NO_TRADE'}>
                        <span class={`text-[10px] px-2 py-1 rounded-full border font-display font-semibold uppercase tracking-[0.14em] ${tierColors[sig.tier] || ''}`}>
                          {sig.tier}
                        </span>
                      </Show>
                    </div>
                    <div class="flex items-center gap-4 text-[11px] shrink-0">
                      <Show when={sig.pnl_dollars !== undefined && sig.pnl_dollars !== null}>
                        <span class={`font-semibold ${pnlColor(sig.pnl_dollars!)}`}>
                          {pnlSign(sig.pnl_dollars!)}${sig.pnl_dollars!.toFixed(2)}
                        </span>
                      </Show>
                      <span class="text-text-muted font-data w-20 text-right">
                        {formatTime(sig.timestamp)}
                      </span>
                    </div>
                  </div>
                )}
              </For>
            </div>
          </Show>
        </WidgetFrame>
      </div>
    </div>
  );
};

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    });
  } catch { return ''; }
}
