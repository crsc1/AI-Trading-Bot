import { type Component, For, Show, onMount, onCleanup } from 'solid-js';
import { agent } from '../../signals/agent';
import { subscribeResearchFindings, unsubscribeResearchFindings } from '../../runtime/agentRuntime';
import { EmptyState } from '../system/EmptyState';

const typeIcons: Record<string, string> = {
  sentiment: 'S',
  pattern: 'P',
  suggestion: '!',
};

const typeColors: Record<string, string> = {
  sentiment: 'bg-accent/14 text-accent border border-accent/30',
  pattern: 'bg-surface-3 text-text-primary border border-border-default',
  suggestion: 'bg-warning/12 text-warning border border-warning/30',
};

export const ResearchFeed: Component = () => {
  onMount(() => {
    subscribeResearchFindings();
  });

  onCleanup(() => unsubscribeResearchFindings());

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
      <div class="px-4 py-4 border-b-[1.5px] border-border-default flex items-center justify-between">
        <span class="font-display text-text-secondary text-[11px] font-semibold tracking-[0.12em] uppercase">
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
        <Show when={agent.findingsLoading}>
          <EmptyState eyebrow="Research" title="Loading research" description="Pulling the latest structured findings into the workspace." />
        </Show>

        <Show when={!agent.findingsLoading && agent.findings.length === 0}>
          <EmptyState eyebrow="Research" title="No findings yet" description="Research findings will appear here when the agent publishes a new observation." />
        </Show>

        <For each={agent.findings}>
          {(finding) => (
            <div class="px-4 py-4 border-b border-border-subtle hover:bg-surface-2/30 transition-colors">
              <div class="flex items-start gap-2.5">
                {/* Type badge */}
                <span class={`font-display text-[11px] font-semibold w-6 h-6 flex items-center justify-center rounded-lg shrink-0 mt-0.5 ${typeColors[finding.type] || 'bg-surface-3 text-text-muted border border-border-default'}`}>
                  {typeIcons[finding.type] || '?'}
                </span>

                <div class="flex-1 min-w-0">
                  {/* Title */}
                  <div class="font-display text-[12px] font-semibold text-text-primary leading-tight">
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
