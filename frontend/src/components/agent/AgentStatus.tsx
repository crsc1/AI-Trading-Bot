import { type Component, Show } from 'solid-js';
import { agent } from '../../signals/agent';

const statusLabels: Record<string, string> = {
  idle: 'IDLE',
  analyzing: 'ANALYZING',
  trading: 'TRADING',
  error: 'ERROR',
};

const statusStyle: Record<string, string> = {
  analyzing: 'bg-positive/15 text-positive',
  trading: 'bg-warning/15 text-warning',
  error: 'bg-negative/15 text-negative',
};

export const AgentStatus: Component = () => {
  const brain = () => agent.brain;

  return (
    <div class="px-3 py-3 border-b border-border-default bg-surface-1">
      <div class="flex items-center justify-between">
        <span class="font-display text-purple text-[11px] font-medium tracking-[0.8px]">
          MARKET BRAIN
        </span>
        <span class={`font-data text-[11px] px-2 py-0.5 rounded ${
          statusStyle[brain().status] || 'bg-surface-3 text-text-muted'
        }`}>
          {statusLabels[brain().status] || brain().status.toUpperCase()}
        </span>
      </div>

      <Show when={brain().cycle_number > 0 || brain().last_confidence > 0 || (brain().last_action && brain().last_action !== 'HOLD')}>
        <div class="flex items-center gap-3 mt-2 font-data text-[11px]">
          <Show when={brain().cycle_number > 0}>
            <span class="text-text-secondary">Cycle {brain().cycle_number}</span>
          </Show>

          <Show when={brain().last_confidence > 0}>
            <span class={brain().last_confidence >= 0.6 ? 'text-positive' : brain().last_confidence >= 0.45 ? 'text-warning' : 'text-text-secondary'}>
              {(brain().last_confidence * 100).toFixed(0)}%
            </span>
          </Show>

          <Show when={brain().last_action && brain().last_action !== 'HOLD'}>
            <span class={brain().last_action === 'TRADE' ? 'text-positive font-semibold' : 'text-text-secondary'}>
              {brain().last_action}
            </span>
          </Show>
        </div>
      </Show>

      <Show when={brain().last_reasoning}>
        <div class="mt-2 font-ai text-[11px] text-text-secondary leading-[1.5] line-clamp-2">
          {brain().last_reasoning}
        </div>
      </Show>

      <Show when={brain().model}>
        <div class="mt-1 font-data text-[11px] text-text-muted">
          {brain().model}
        </div>
      </Show>
    </div>
  );
};
