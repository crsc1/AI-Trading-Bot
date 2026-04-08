import { type Component, Show } from 'solid-js';
import { agent, setActiveTab } from '../../signals/agent';
import { AgentStatus } from '../agent/AgentStatus';
import { BrainFeed } from '../agent/BrainFeed';
import { ChatPanel } from '../agent/ChatPanel';
import { ResearchFeed } from '../agent/ResearchFeed';

export const Agent: Component = () => {
  return (
    <div class="h-full flex flex-col">
      {/* Status bar */}
      <AgentStatus />

      {/* Tab bar */}
      <div class="h-9 flex items-center gap-1 px-3 bg-surface-1 border-b border-border-default shrink-0">
        <button
          class={`px-3 py-1 text-[12px] rounded transition-colors ${
            agent.activeTab === 'brain'
              ? 'bg-purple/15 text-purple font-medium'
              : 'text-text-secondary hover:text-text-primary hover:bg-surface-3'
          }`}
          style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;"
          onClick={() => setActiveTab('brain')}
        >
          Market Brain
        </button>
        <button
          class={`px-3 py-1 text-[12px] rounded transition-colors ${
            agent.activeTab === 'chat'
              ? 'bg-accent/15 text-accent font-medium'
              : 'text-text-secondary hover:text-text-primary hover:bg-surface-3'
          }`}
          style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;"
          onClick={() => setActiveTab('chat')}
        >
          Claude Code
        </button>
      </div>

      {/* Content */}
      <div class="flex-1 min-h-0 flex">
        {/* Main panel */}
        <div class="flex-1 min-w-0 border-l-2 border-l-purple/40">
          <Show when={agent.activeTab === 'brain'}>
            <BrainFeed />
          </Show>
          <Show when={agent.activeTab === 'chat'}>
            <ChatPanel />
          </Show>
        </div>

        {/* Research sidebar */}
        <div class="w-[340px] border-l border-border-default shrink-0 bg-surface-1">
          <ResearchFeed />
        </div>
      </div>
    </div>
  );
};
