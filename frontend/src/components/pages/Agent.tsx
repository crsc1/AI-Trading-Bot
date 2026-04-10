import { type Component, Show } from 'solid-js';
import { agent, setActiveTab } from '../../signals/agent';
import { AgentStatus } from '../agent/AgentStatus';
import { BrainFeed } from '../agent/BrainFeed';
import { ChatPanel } from '../agent/ChatPanel';
import { ResearchFeed } from '../agent/ResearchFeed';
import { SegmentedControl, type SegmentedOption } from '../system/SegmentedControl';

const agentTabOptions: SegmentedOption<'brain' | 'chat'>[] = [
  { label: 'Market Brain', value: 'brain', testId: 'agent-tab-brain' },
  { label: 'Claude Code', value: 'chat', testId: 'agent-tab-chat' },
];

export const Agent: Component = () => {
  return (
    <div data-testid="agent-page" class="h-full flex flex-col bg-[linear-gradient(180deg,rgba(11,13,18,1),rgba(14,18,24,1))]">
      {/* Status bar */}
      <AgentStatus />

      {/* Tab bar */}
      <div class="min-h-[56px] flex items-center justify-between gap-3 px-4 bg-surface-1 border-b-[1.5px] border-border-default shrink-0">
        <div class="min-w-0">
          <div class="font-display text-[10px] font-semibold uppercase tracking-[0.16em] text-text-muted">Research Workspace</div>
          <div class="mt-1 text-[11px] text-text-secondary">Live market reasoning, research findings, and collaborative chat</div>
        </div>
        <SegmentedControl options={agentTabOptions} value={agent.activeTab} onChange={setActiveTab} />
      </div>

      {/* Content */}
      <div class="flex-1 min-h-0 flex">
        {/* Main panel */}
        <div class="flex-1 min-w-0 border-l-[1.5px] border-l-border-default">
          <Show when={agent.activeTab === 'brain'}>
            <BrainFeed />
          </Show>
          <Show when={agent.activeTab === 'chat'}>
            <ChatPanel />
          </Show>
        </div>

        {/* Research sidebar */}
        <div class="w-[360px] border-l-[1.5px] border-border-default shrink-0 bg-surface-1">
          <ResearchFeed />
        </div>
      </div>
    </div>
  );
};
