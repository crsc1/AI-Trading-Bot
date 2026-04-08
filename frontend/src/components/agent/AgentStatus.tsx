import { type Component, Show, For, createSignal, onMount, onCleanup } from 'solid-js';
import { agent } from '../../signals/agent';
import { api } from '../../lib/api';

interface DataSource {
  name: string;
  status: 'live' | 'offline' | 'error';
  detail?: string;
  source?: string;
}

interface SourcesResponse {
  sources: DataSource[];
  model: string;
}

export const AgentStatus: Component = () => {
  const brain = () => agent.brain;
  const [sources, setSources] = createSignal<DataSource[]>([]);
  const [model, setModel] = createSignal('');
  let pollInterval: ReturnType<typeof setInterval>;

  async function loadSources() {
    try {
      const data = await api.get<SourcesResponse>('/api/brain/sources');
      if (data?.sources) setSources(data.sources);
      if (data?.model) setModel(data.model);
    } catch (_) { /* noop */ }
  }

  onMount(() => {
    loadSources();
    pollInterval = setInterval(loadSources, 15000);
  });

  onCleanup(() => clearInterval(pollInterval));

  const statusDot = (s: string) => {
    switch (s) {
      case 'live': return 'bg-positive';
      case 'offline': return 'bg-text-muted';
      case 'error': return 'bg-negative';
      default: return 'bg-text-muted';
    }
  };

  return (
    <div class="px-3 py-3 border-b border-border-default bg-surface-1">
      {/* Header row */}
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="font-display text-purple text-[11px] font-medium tracking-[0.8px]">
            MARKET BRAIN
          </span>
          <Show when={model()}>
            <span class="font-data text-[11px] text-text-muted">
              {model().replace('claude-', '').replace('-4-6', ' 4.6')}
            </span>
          </Show>
        </div>
        <div class="flex items-center gap-2">
          <Show when={brain().cycle_number > 0}>
            <span class="font-data text-[11px] text-text-secondary">
              Cycle {brain().cycle_number}
            </span>
          </Show>
          <span class={`font-data text-[11px] px-2 py-0.5 rounded ${
            brain().status === 'analyzing' ? 'bg-positive/15 text-positive' :
            brain().status === 'trading' ? 'bg-warning/15 text-warning' :
            brain().status === 'error' ? 'bg-negative/15 text-negative' :
            'bg-surface-3 text-text-muted'
          }`}>
            {brain().status === 'idle' ? 'READY' : brain().status.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Data sources */}
      <Show when={sources().length > 0}>
        <div class="flex items-center gap-4 mt-2">
          <For each={sources()}>
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
        <div class="mt-2 font-ai text-[11px] text-text-secondary leading-[1.5] line-clamp-2">
          {brain().last_reasoning}
        </div>
      </Show>
    </div>
  );
};
