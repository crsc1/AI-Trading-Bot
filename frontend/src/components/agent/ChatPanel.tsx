import { type Component, For, Show, createSignal, onMount, onCleanup, createEffect } from 'solid-js';
import { agent, addMessage, updateBrain, setChatConnected } from '../../signals/agent';
import { WSClient } from '../../lib/ws';
import type { ChatMessage, BrainState } from '../../types/agent';

export const ChatPanel: Component = () => {
  const [input, setInput] = createSignal('');
  const [sending, setSending] = createSignal(false);
  let chatWS: WSClient | null = null;
  let messagesEndRef: HTMLDivElement | undefined;

  createEffect(() => {
    void agent.messages.length;
    messagesEndRef?.scrollIntoView({ behavior: 'smooth' });
  });

  onMount(() => {
    const wsHost = window.location.hostname || 'localhost';
    chatWS = new WSClient({
      url: `ws://${wsHost}:8000/ws/chat`,
      onMessage: (data) => {
        switch (data.type) {
          case 'chat_message': {
            const msg = data.message as ChatMessage;
            addMessage(msg);
            break;
          }
          case 'brain_state': {
            const state = data.state as BrainState;
            updateBrain(state);
            break;
          }
          case 'brain_decision': {
            const decision = data.decision;
            updateBrain({
              last_action: decision.action,
              last_confidence: decision.confidence,
              last_reasoning: decision.reasoning,
              model: decision.model,
              cycle_number: decision.cycle,
            });
            break;
          }
          case 'chat_queued': {
            addMessage({
              id: `sys-${Date.now()}`,
              role: 'system',
              content: 'Queued for next analysis cycle...',
              timestamp: new Date().toISOString(),
            });
            break;
          }
        }
      },
      onConnect: () => setChatConnected(true),
      onDisconnect: () => setChatConnected(false),
    });
    chatWS.connect();
  });

  onCleanup(() => {
    chatWS?.destroy();
    chatWS = null;
  });

  function sendMessage() {
    const text = input().trim();
    if (!text || !chatWS) return;

    setSending(true);
    chatWS.send({
      type: 'chat',
      message: text,
      immediate: true,
    });
    setInput('');
    setSending(false);
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  const roleColor = (role: string) => {
    switch (role) {
      case 'user': return 'text-accent';
      case 'brain': return 'text-purple';
      case 'system': return 'text-text-muted';
      default: return 'text-text-secondary';
    }
  };

  const roleLabel = (role: string) => {
    switch (role) {
      case 'user': return 'You';
      case 'brain': return 'Market Brain';
      case 'system': return 'System';
      default: return role;
    }
  };

  return (
    <div class="flex flex-col h-full">
      {/* Messages */}
      <div class="flex-1 overflow-y-auto px-4 py-3 space-y-4 min-h-0">
        <Show when={agent.messages.length === 0}>
          <div class="flex items-center justify-center h-full">
            <div class="text-center">
              <div class="font-ai text-[12px] text-text-secondary mb-2">
                Market Brain is ready
              </div>
              <div class="font-ai text-[11px] text-text-muted">
                Ask about market conditions, setups, or give trading instructions
              </div>
            </div>
          </div>
        </Show>

        <For each={agent.messages}>
          {(msg) => (
            <div class={`${msg.role === 'user' ? 'pl-6' : ''}`}>
              {/* Header row */}
              <div class="flex items-center gap-2 mb-1">
                <span class={`font-display text-[11px] font-medium ${roleColor(msg.role)}`}>
                  {roleLabel(msg.role)}
                </span>
                <span class="font-data text-[11px] text-text-muted">
                  {new Date(msg.timestamp).toLocaleTimeString('en-US', {
                    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
                  })}
                </span>
                <Show when={msg.metadata?.action && msg.metadata.action !== 'HOLD'}>
                  <span class={`font-data text-[11px] px-1.5 py-0.5 rounded ${
                    msg.metadata!.action === 'TRADE' ? 'bg-positive/15 text-positive' : 'bg-surface-3 text-text-secondary'
                  }`}>
                    {msg.metadata!.action}
                  </span>
                </Show>
              </div>
              {/* Content */}
              <div class={`font-ai text-[12px] leading-[1.5] ${
                msg.role === 'system'
                  ? 'text-text-muted italic'
                  : 'text-text-primary'
              }`}>
                {msg.content}
              </div>
            </div>
          )}
        </For>

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div class="px-4 py-3 border-t border-border-default bg-surface-1">
        <div class="flex items-center gap-2">
          <input
            type="text"
            value={input()}
            onInput={(e) => setInput(e.currentTarget.value)}
            onKeyDown={handleKeyDown}
            placeholder={agent.chatConnected ? 'Ask Market Brain...' : 'Connecting...'}
            disabled={!agent.chatConnected || sending()}
            class="flex-1 bg-surface-2 border border-purple/20 rounded px-3 py-2 font-ai text-[12px] text-text-primary placeholder:text-text-muted focus:border-purple/50 focus:outline-none disabled:opacity-40"
          />
          <button
            onClick={sendMessage}
            disabled={!agent.chatConnected || !input().trim() || sending()}
            class="px-4 py-2 font-display text-[11px] font-medium bg-purple/80 text-white rounded hover:bg-purple disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
        </div>
        <div class="flex items-center gap-2 mt-2 font-data text-[11px] text-text-muted">
          <span class={`w-1.5 h-1.5 rounded-full ${agent.chatConnected ? 'bg-positive' : 'bg-negative'}`} />
          <span>{agent.chatConnected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </div>
    </div>
  );
};
