import { type Component, For, Show, onMount, onCleanup, createSignal } from 'solid-js';
import { agent, setFindings } from '../../signals/agent';
import { api } from '../../lib/api';
import type { ResearchFinding } from '../../types/agent';

const typeIcons: Record<string, string> = {
  sentiment: 'S',
  pattern: 'P',
  suggestion: '!',
};

const typeColors: Record<string, string> = {
  sentiment: 'bg-accent/15 text-accent',
  pattern: 'bg-purple/15 text-purple',
  suggestion: 'bg-warning/15 text-warning',
};

export const ResearchFeed: Component = () => {
  const [loading, setLoading] = createSignal(true);
  let pollInterval: ReturnType<typeof setInterval>;

  async function loadFindings() {
    try {
      const data = await (api.get<{ findings: ResearchFinding[] }>('/api/research/findings?limit=10'));
      if (data?.findings) {
        setFindings(data.findings);
      }
    } catch (_) { /* noop */ }
    setLoading(false);
  }

  onMount(() => {
    loadFindings();
    pollInterval = setInterval(loadFindings, 60000); // Every minute
  });

  onCleanup(() => clearInterval(pollInterval));

  const formatTime = (ts: string) => {
    try {
      const d = new Date(ts);
      const now = new Date();
      const diffMin = Math.floor((now.getTime() - d.getTime()) / 60000);
      if (diffMin < 1) return 'just now';
      if (diffMin < 60) return `${diffMin}m ago`;
      if (diffMin < 1440) return `${Math.floor(diffMin / 60)}h ago`;
      return d.toLocaleDateString();
    } catch { return ''; }
  };

  return (
    <div class="flex flex-col h-full">
      <div class="px-2 py-1.5 font-display text-text-secondary text-[9px] font-medium tracking-wider border-b border-border-default flex items-center justify-between">
        <span>RESEARCH</span>
        <Show when={agent.findings.length > 0}>
          <span class="text-[7px] text-text-muted">{agent.findings.length} findings</span>
        </Show>
      </div>

      <div class="flex-1 overflow-y-auto min-h-0">
        <Show when={loading()}>
          <div class="p-2 text-text-muted text-[9px]">Loading research data...</div>
        </Show>

        <Show when={!loading() && agent.findings.length === 0}>
          <div class="p-2 text-text-muted text-[9px]">
            No research findings yet. Agent runs every 30 minutes.
          </div>
        </Show>

        <For each={agent.findings}>
          {(finding) => (
            <div class="p-2 border-b border-border-subtle hover:bg-surface-2/30">
              <div class="flex items-start gap-1.5">
                <span class={`text-[7px] w-4 h-4 flex items-center justify-center rounded shrink-0 mt-0.5 ${typeColors[finding.type] || 'bg-surface-3 text-text-muted'}`}>
                  {typeIcons[finding.type] || '?'}
                </span>
                <div class="flex-1 min-w-0">
                  <div class="text-[8px] font-semibold text-text-primary leading-tight">
                    {finding.title}
                  </div>
                  <div class="text-[7px] text-text-muted mt-0.5 leading-relaxed line-clamp-3">
                    {finding.content}
                  </div>
                  <div class="flex items-center gap-2 mt-1 text-[7px] text-text-muted">
                    <span>{finding.source}</span>
                    <span>{formatTime(finding.timestamp)}</span>
                    <Show when={finding.confidence > 0}>
                      <span class="opacity-50">{(finding.confidence * 100).toFixed(0)}%</span>
                    </Show>
                  </div>
                </div>
              </div>
            </div>
          )}
        </For>
      </div>
    </div>
  );
};
