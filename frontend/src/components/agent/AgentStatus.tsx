import { type Component, Show, For, onMount, onCleanup } from 'solid-js';
import { agent } from '../../signals/agent';
import { subscribeAgentSources, unsubscribeAgentSources } from '../../runtime/agentRuntime';
import { StatusPill } from '../system/StatusPill';

export const AgentStatus: Component = () => {
  const brain = () => agent.brain;

  onMount(() => {
    subscribeAgentSources();
  });

  onCleanup(() => unsubscribeAgentSources());

  const statusDot = (s: string) => {
    switch (s) {
      case 'live': return 'bg-positive';
      case 'offline': return 'bg-text-muted';
      case 'error': return 'bg-negative';
      default: return 'bg-text-muted';
    }
  };

  return (
    <div class="px-4 py-4 border-b-[1.5px] border-border-default bg-surface-1">
      {/* Header row */}
      <div class="flex items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <span class="font-display text-accent text-[11px] font-semibold tracking-[0.12em] uppercase">
            MARKET BRAIN
          </span>
          <Show when={agent.model}>
            <span class="font-data text-[11px] text-text-muted">
              {agent.model.replace('claude-', '').replace('-4-6', ' 4.6')}
            </span>
          </Show>
        </div>
        <div class="flex items-center gap-2">
          <StatusPill
            label="Cycle"
            value={brain().cycle_number > 0 ? String(brain().cycle_number) : '0'}
            tone="neutral"
            compact
          />
          <StatusPill
            label="Status"
            value={brain().status === 'idle' ? 'READY' : brain().status.toUpperCase()}
            tone={
              brain().status === 'analyzing' ? 'positive' :
              brain().status === 'trading' ? 'warning' :
              brain().status === 'error' ? 'negative' : 'neutral'
            }
            compact
          />
        </div>
      </div>

      {/* Data sources */}
      <Show when={agent.sources.length > 0}>
        <div class="flex flex-wrap items-center gap-4 mt-3">
          <For each={agent.sources}>
            {(src) => (
              <div class="flex items-center gap-1.5" title={src.detail || ''}>
                <span class={`w-1.5 h-1.5 rounded-full ${statusDot(src.status)}`} />
                <span class="font-data text-[11px] text-text-secondary">{src.name}</span>
                <Show when={src.status === 'live' && src.detail}>
                  <span class="font-data text-[11px] text-text-muted">{src.detail}</span>
                </Show>
              </div>
            )}
          </For>
        </div>
      </Show>

      {/* Last reasoning */}
      <Show when={brain().last_reasoning}>
        <div class="mt-3 rounded-xl border-[1.5px] border-border-default bg-surface-2/70 px-4 py-3 font-ai text-[11px] text-text-secondary leading-[1.5] line-clamp-2">
          {brain().last_reasoning}
        </div>
      </Show>
    </div>
  );
};
