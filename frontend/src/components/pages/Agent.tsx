import { type Component } from 'solid-js';
import { AgentStatus } from '../agent/AgentStatus';
import { ChatPanel } from '../agent/ChatPanel';
import { ResearchFeed } from '../agent/ResearchFeed';

export const Agent: Component = () => {
  return (
    <div class="h-full flex">
      {/* Chat — primary area */}
      <div class="flex-1 flex flex-col min-w-0 border-l-2 border-l-purple/40">
        <AgentStatus />
        <div class="flex-1 min-h-0">
          <ChatPanel />
        </div>
      </div>

      {/* Research — right panel */}
      <div class="w-[320px] border-l border-border-default shrink-0">
        <ResearchFeed />
      </div>
    </div>
  );
};
