import { type Component, Show } from 'solid-js';
import { agent } from '../../signals/agent';

const statusLabels: Record<string, string> = {
  idle: 'IDLE',
  analyzing: 'ANALYZING',
  trading: 'TRADING',
  error: 'ERROR',
};

export const AgentStatus: Component = () => {
  const brain = () => agent.brain;

  return (
    <div class="p-2 border-b border-border-default">
      <div class="flex items-center justify-between mb-1">
        <span class="text-text-secondary text-[9px] font-semibold tracking-wider">MARKET BRAIN</span>
        <span class={`text-[8px] px-1.5 py-0.5 rounded ${
          brain().status === 'analyzing' ? 'bg-positive/15 text-positive' :
          brain().status === 'trading' ? 'bg-warning/15 text-warning' :
          brain().status === 'error' ? 'bg-negative/15 text-negative' :
          'bg-surface-3 text-text-muted'
        }`}>
          {statusLabels[brain().status] || brain().status.toUpperCase()}
        </span>
      </div>

      <div class="flex items-center gap-2 text-[9px]">
        <Show when={brain().cycle_number > 0}>
          <span class="text-text-muted">Cycle {brain().cycle_number}</span>
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

      <Show when={brain().last_reasoning}>
        <div class="mt-1 text-[8px] text-text-muted leading-tight line-clamp-2">
          {brain().last_reasoning}
        </div>
      </Show>

      <Show when={brain().model}>
        <div class="mt-1 text-[8px] text-text-muted opacity-50">
          {brain().model}
        </div>
      </Show>
    </div>
  );
};
