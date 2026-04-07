import { type Component, For, Show, onMount, onCleanup } from 'solid-js';
import { signals, setPositions, setDailyPerformance } from '../../signals/signals';
import { api } from '../../lib/api';

export const PositionPanel: Component = () => {
  let pollInterval: ReturnType<typeof setInterval>;

  async function loadPositions() {
    try {
      const [posData, statusData] = await Promise.all([
        api.getPositions().catch(() => ({ positions: [] })),
        api.getStatus().catch(() => null),
      ]);
      if (posData?.positions) setPositions(posData.positions);
      if (statusData) {
        setDailyPerformance({
          total_pnl: statusData.daily_pnl || 0,
          win_count: statusData.wins || 0,
          loss_count: statusData.losses || 0,
          win_rate: statusData.win_rate || 0,
          trades_today: statusData.trades_today || 0,
        });
      }
    } catch (_) { /* noop */ }
  }

  onMount(() => {
    loadPositions();
    pollInterval = setInterval(loadPositions, 5000);
  });

  onCleanup(() => clearInterval(pollInterval));

  const pnlColor = (v: number) => v >= 0 ? 'text-positive' : 'text-negative';
  const pnlSign = (v: number) => v >= 0 ? '+' : '';

  return (
    <div class="flex flex-col h-full">
      <div class="px-2 py-1.5 flex items-center justify-between border-b border-border-default">
        <span class="text-text-secondary text-[9px] font-semibold tracking-wider">POSITIONS</span>
        <div class="flex items-center gap-2 text-[8px]">
          <span class={pnlColor(signals.daily.total_pnl)}>
            {pnlSign(signals.daily.total_pnl)}${signals.daily.total_pnl.toFixed(2)}
          </span>
          <Show when={signals.daily.trades_today > 0}>
            <span class="text-text-muted">
              {signals.daily.win_count}W/{signals.daily.loss_count}L
            </span>
          </Show>
        </div>
      </div>

      <div class="flex-1 overflow-y-auto min-h-0">
        <Show when={signals.positions.length === 0}>
          <div class="p-2 text-text-muted text-[9px]">No open positions</div>
        </Show>

        <For each={signals.positions}>
          {(pos) => {
            const pnl = pos.unrealized_pnl || 0;
            const pnlPct = pos.unrealized_pnl_pct || 0;

            return (
              <div class="p-2 border-b border-border-subtle">
                <div class="flex items-center justify-between mb-0.5">
                  <div class="flex items-center gap-1.5">
                    <span class={`text-[9px] font-bold ${pos.option_type === 'call' ? 'text-positive' : 'text-negative'}`}>
                      {pos.strike} {pos.option_type?.toUpperCase()}
                    </span>
                    <span class="text-[7px] text-text-muted">
                      x{pos.contracts}
                    </span>
                  </div>
                  <span class={`text-[9px] font-bold ${pnlColor(pnl)}`}>
                    {pnlSign(pnl)}${pnl.toFixed(2)} ({pnlSign(pnlPct)}{pnlPct.toFixed(1)}%)
                  </span>
                </div>

                <div class="flex items-center gap-2 text-[7px] text-text-muted">
                  <span>Entry ${pos.entry_price?.toFixed(2)}</span>
                  <span>Now ${pos.current_price?.toFixed(2)}</span>
                  <Show when={pos.greeks}>
                    <span>D:{pos.greeks.delta?.toFixed(2)}</span>
                    <span>T:{pos.greeks.theta?.toFixed(2)}</span>
                  </Show>
                </div>

                <Show when={pos.exit_triggers}>
                  <div class="flex items-center gap-2 mt-0.5 text-[7px]">
                    <span class="text-negative">Stop ${pos.exit_triggers.stop_loss?.toFixed(2)}</span>
                    <span class="text-positive">Target ${pos.exit_triggers.profit_target?.toFixed(2)}</span>
                  </div>
                </Show>
              </div>
            );
          }}
        </For>
      </div>
    </div>
  );
};
