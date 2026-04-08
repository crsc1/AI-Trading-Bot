import { type Component, Show, For, createEffect, on } from 'solid-js';
import { market } from '../../signals/market';
import { agent } from '../../signals/agent';
import { signals } from '../../signals/signals';
import { loadCandles } from '../../lib/data';

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
  createEffect(
    on(() => market.timeframe, () => loadCandles(), { defer: true })
  );

  const pnlColor = (v: number) => (v >= 0 ? 'text-positive' : 'text-negative');
  const pnlSign = (v: number) => (v >= 0 ? '+' : '');

  return (
    <div class="h-full overflow-y-auto p-6">
      <div class="max-w-[1200px] mx-auto">
        {/* Page Title */}
        <h1 class="font-display text-[18px] font-medium mb-6">Dashboard</h1>

        {/* Stats Row */}
        <div class="grid grid-cols-4 gap-4 mb-6">
          <StatCard
            label="Daily P&L"
            value={`${pnlSign(signals.daily.total_pnl)}$${signals.daily.total_pnl.toFixed(2)}`}
            valueClass={pnlColor(signals.daily.total_pnl)}
            large
          />
          <StatCard
            label="Win Rate"
            value={signals.daily.trades_today > 0
              ? `${(signals.daily.win_rate * 100).toFixed(0)}%`
              : '---'
            }
            subtitle={signals.daily.trades_today > 0
              ? `${signals.daily.win_count}W / ${signals.daily.loss_count}L`
              : 'No trades today'
            }
          />
          <StatCard
            label="Trades Today"
            value={`${signals.daily.trades_today}`}
          />
          <StatCard
            label="Brain Status"
            value={agent.brain.status.toUpperCase()}
            valueClass={agent.brain.status === 'analyzing' ? 'text-positive' : 'text-text-secondary'}
            subtitle={agent.brain.cycle_number > 0 ? `Cycle ${agent.brain.cycle_number}` : undefined}
          />
        </div>

        <div class="grid grid-cols-2 gap-4">
          {/* Open Positions */}
          <div class="bg-surface-1 border border-border-default rounded-sm">
            <div class="px-4 py-3 border-b border-border-default">
              <span class="font-display text-[11px] font-medium text-text-secondary tracking-wider">
                OPEN POSITIONS
              </span>
            </div>
            <div class="p-4">
              <Show when={signals.positions.length === 0}>
                <div class="text-text-muted text-[11px] py-4 text-center">No open positions</div>
              </Show>
              <For each={signals.positions}>
                {(pos) => {
                  const pnl = pos.unrealized_pnl || 0;
                  const pnlPct = pos.unrealized_pnl_pct || 0;
                  return (
                    <div class="flex items-center justify-between py-2 border-b border-border-subtle last:border-0">
                      <div>
                        <span class={`text-[12px] font-medium ${pos.option_type === 'call' ? 'text-positive' : 'text-negative'}`}>
                          {pos.strike} {pos.option_type?.toUpperCase()}
                        </span>
                        <span class="text-text-muted text-[10px] ml-2">x{pos.contracts}</span>
                      </div>
                      <div class="text-right">
                        <span class={`text-[12px] font-medium ${pnlColor(pnl)}`}>
                          {pnlSign(pnl)}${pnl.toFixed(2)}
                        </span>
                        <span class={`text-[10px] ml-1.5 ${pnlColor(pnlPct)}`}>
                          ({pnlSign(pnlPct)}{pnlPct.toFixed(1)}%)
                        </span>
                      </div>
                    </div>
                  );
                }}
              </For>
            </div>
          </div>

          {/* Latest Signal */}
          <div class="bg-surface-1 border border-border-default rounded-sm">
            <div class="px-4 py-3 border-b border-border-default">
              <span class="font-display text-[11px] font-medium text-text-secondary tracking-wider">
                LATEST SIGNAL
              </span>
            </div>
            <div class="p-4">
              <Show when={signals.latest} fallback={
                <div class="text-text-muted text-[11px] py-4 text-center">No signals yet</div>
              }>
                {(sig) => (
                  <div>
                    <div class="flex items-center justify-between mb-3">
                      <span class={`text-[13px] font-medium ${actionColors[sig().action] || 'text-text-primary'}`}>
                        {sig().action.replace('_', ' ')}
                      </span>
                      <span class={`text-[10px] px-2 py-1 rounded border ${tierColors[sig().tier] || tierColors.DEVELOPING}`}>
                        {sig().tier}
                      </span>
                    </div>
                    <div class="grid grid-cols-3 gap-3 mb-3">
                      <div>
                        <div class="font-display text-[9px] text-text-muted tracking-wider mb-1">CONFIDENCE</div>
                        <div class="text-[13px]">{(sig().confidence * 100).toFixed(0)}%</div>
                      </div>
                      <Show when={sig().strike}>
                        <div>
                          <div class="font-display text-[9px] text-text-muted tracking-wider mb-1">STRIKE</div>
                          <div class="text-[13px]">${sig().strike}</div>
                        </div>
                      </Show>
                      <Show when={sig().entry_price}>
                        <div>
                          <div class="font-display text-[9px] text-text-muted tracking-wider mb-1">ENTRY</div>
                          <div class="text-[13px]">${sig().entry_price.toFixed(2)}</div>
                        </div>
                      </Show>
                    </div>
                    <Show when={sig().reasoning}>
                      <div class="text-[11px] text-text-secondary leading-relaxed">
                        {sig().reasoning}
                      </div>
                    </Show>
                  </div>
                )}
              </Show>
            </div>
          </div>

          {/* Signal History */}
          <div class="bg-surface-1 border border-border-default rounded-sm col-span-2">
            <div class="px-4 py-3 border-b border-border-default">
              <span class="font-display text-[11px] font-medium text-text-secondary tracking-wider">
                SIGNAL HISTORY
              </span>
            </div>
            <div class="overflow-y-auto max-h-[240px]">
              <For each={signals.history.slice(0, 20)}>
                {(sig) => (
                  <div class="flex items-center justify-between px-4 py-2 border-b border-border-subtle hover:bg-surface-2/30">
                    <div class="flex items-center gap-3">
                      <span class={`text-[11px] font-medium w-12 ${actionColors[sig.action] || 'text-text-muted'}`}>
                        {sig.action === 'NO_TRADE' ? 'HOLD' : sig.action.replace('BUY_', '')}
                      </span>
                      <Show when={sig.tier && sig.action !== 'NO_TRADE'}>
                        <span class={`text-[9px] px-1.5 py-0.5 rounded ${tierColors[sig.tier] || ''}`}>
                          {sig.tier}
                        </span>
                      </Show>
                    </div>
                    <div class="flex items-center gap-4 text-[10px]">
                      <Show when={sig.pnl_dollars !== undefined && sig.pnl_dollars !== null}>
                        <span class={pnlColor(sig.pnl_dollars!)}>
                          {pnlSign(sig.pnl_dollars!)}${sig.pnl_dollars!.toFixed(2)}
                        </span>
                      </Show>
                      <span class="text-text-muted w-16 text-right">
                        {formatTime(sig.timestamp)}
                      </span>
                    </div>
                  </div>
                )}
              </For>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Helper Components ──────────────────────────────────────────────────────

const StatCard: Component<{
  label: string;
  value: string;
  valueClass?: string;
  subtitle?: string;
  large?: boolean;
}> = (props) => (
  <div class="bg-surface-1 border border-border-default rounded-sm p-4">
    <div class="font-display text-[9px] font-medium text-text-muted tracking-wider mb-2">
      {props.label}
    </div>
    <div class={`${props.large ? 'text-[22px]' : 'text-[16px]'} font-medium ${props.valueClass || 'text-text-primary'}`}>
      {props.value}
    </div>
    {props.subtitle && (
      <div class="text-[10px] text-text-muted mt-1">{props.subtitle}</div>
    )}
  </div>
);

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    });
  } catch { return ''; }
}
