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
    pollInterval = setInterval(loadFindings, 60000);
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
      {/* Header */}
      <div class="px-3 py-3 border-b border-border-default flex items-center justify-between">
        <span class="font-display text-text-secondary text-[11px] font-medium tracking-[0.8px]">
          RESEARCH
        </span>
        <Show when={agent.findings.length > 0}>
          <span class="font-data text-[11px] text-text-muted">
            {agent.findings.length} findings
          </span>
        </Show>
      </div>

      {/* Feed */}
      <div class="flex-1 overflow-y-auto min-h-0">
        <Show when={loading()}>
          <div class="px-3 py-4 font-ai text-[11px] text-text-muted">
            Loading research data...
          </div>
        </Show>

        <Show when={!loading() && agent.findings.length === 0}>
          <div class="px-3 py-4 font-ai text-[11px] text-text-muted">
            No research findings yet. Agent runs every 30 minutes.
          </div>
        </Show>

        <For each={agent.findings}>
          {(finding) => (
            <div class="px-3 py-3 border-b border-border-subtle hover:bg-surface-2/30 transition-colors">
              <div class="flex items-start gap-2.5">
                {/* Type badge */}
                <span class={`font-display text-[11px] font-medium w-5 h-5 flex items-center justify-center rounded shrink-0 mt-0.5 ${typeColors[finding.type] || 'bg-surface-3 text-text-muted'}`}>
                  {typeIcons[finding.type] || '?'}
                </span>

                <div class="flex-1 min-w-0">
                  {/* Title */}
                  <div class="font-display text-[12px] font-medium text-text-primary leading-tight">
                    {finding.title}
                  </div>

                  {/* Content */}
                  <div class="font-ai text-[11px] text-text-secondary mt-1 leading-[1.5] line-clamp-3">
                    {finding.content}
                  </div>

                  {/* Meta */}
                  <div class="flex items-center gap-3 mt-2 font-data text-[11px] text-text-muted">
                    <span>{finding.source}</span>
                    <span>{formatTime(finding.timestamp)}</span>
                    <Show when={finding.confidence > 0}>
                      <span>{(finding.confidence * 100).toFixed(0)}%</span>
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
