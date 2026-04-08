import { type Component, For, Show, onMount, onCleanup } from 'solid-js';
import { signals, setLatestSignal, setSignalHistory } from '../../signals/signals';
import { api } from '../../lib/api';
import type { Signal } from '../../types/signal';

const tierColors: Record<string, string> = {
  TEXTBOOK: 'bg-positive/20 text-positive border-positive/30',
  HIGH: 'bg-accent/20 text-accent border-accent/30',
  VALID: 'bg-warning/20 text-warning border-warning/30',
  DEVELOPING: 'bg-surface-3 text-text-muted border-border-default',
};

const actionColors: Record<string, string> = {
  BUY_CALL: 'text-positive',
  BUY_PUT: 'text-negative',
  NO_TRADE: 'text-text-muted',
};

export const SignalPanel: Component = () => {
  let pollInterval: ReturnType<typeof setInterval>;

  async function loadSignals() {
    try {
      const [latest, history] = await Promise.all([
        api.getLatestSignal().catch(() => null),
        api.getSignalHistory().catch(() => ({ signals: [] })),
      ]);
      if (latest && latest.signal) setLatestSignal(latest as Signal);
      if (history?.signals) setSignalHistory(history.signals as Signal[]);
    } catch (_) { /* noop */ }
  }

  onMount(() => {
    loadSignals();
    pollInterval = setInterval(loadSignals, 10000);
  });

  onCleanup(() => clearInterval(pollInterval));

  const formatTime = (ts: string) => {
    try {
      return new Date(ts).toLocaleTimeString('en-US', {
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
      });
    } catch { return ''; }
  };

  return (
    <div class="flex flex-col h-full">
      <div class="px-2 py-1.5 font-display text-text-secondary text-[9px] font-medium tracking-wider border-b border-border-default">
        SIGNALS
      </div>

      {/* Latest signal */}
      <Show when={signals.latest}>
        {(sig) => (
          <div class="p-2 border-b border-border-default bg-surface-2/50">
            <div class="flex items-center justify-between mb-1">
              <span class={`text-[10px] font-bold ${actionColors[sig().action] || 'text-text-primary'}`}>
                {sig().action.replace('_', ' ')}
              </span>
              <span class={`text-[7px] px-1.5 py-0.5 rounded border ${tierColors[sig().tier] || tierColors.DEVELOPING}`}>
                {sig().tier}
              </span>
            </div>
            <div class="flex items-center gap-2 text-[8px] text-text-secondary">
              <span>Conf: {(sig().confidence * 100).toFixed(0)}%</span>
              <Show when={sig().strike}>
                <span>${sig().strike}</span>
              </Show>
              <Show when={sig().entry_price}>
                <span>Entry ${sig().entry_price.toFixed(2)}</span>
              </Show>
            </div>
            <Show when={sig().reasoning}>
              <div class="mt-1 text-[8px] text-text-muted leading-tight line-clamp-2">
                {sig().reasoning}
              </div>
            </Show>
          </div>
        )}
      </Show>

      <Show when={!signals.latest}>
        <div class="p-2 text-text-muted text-[9px]">No signals yet</div>
      </Show>

      {/* Signal history */}
      <div class="flex-1 overflow-y-auto min-h-0">
        <For each={signals.history.slice(0, 15)}>
          {(sig) => (
            <div class="px-2 py-1 border-b border-border-subtle flex items-center justify-between hover:bg-surface-2/30">
              <div class="flex items-center gap-1.5">
                <span class={`text-[8px] font-semibold ${actionColors[sig.action] || 'text-text-muted'}`}>
                  {sig.action === 'NO_TRADE' ? 'HOLD' : sig.action.replace('BUY_', '')}
                </span>
                <Show when={sig.tier && sig.action !== 'NO_TRADE'}>
                  <span class={`text-[7px] px-1 rounded ${tierColors[sig.tier] || ''}`}>
                    {sig.tier}
                  </span>
                </Show>
              </div>
              <div class="flex items-center gap-1.5 text-[7px] text-text-muted">
                <Show when={sig.pnl_dollars !== undefined && sig.pnl_dollars !== null}>
                  <span class={sig.pnl_dollars! >= 0 ? 'text-positive' : 'text-negative'}>
                    {sig.pnl_dollars! >= 0 ? '+' : ''}{sig.pnl_dollars!.toFixed(2)}
                  </span>
                </Show>
                <span>{formatTime(sig.timestamp)}</span>
              </div>
            </div>
          )}
        </For>
      </div>
    </div>
  );
};
