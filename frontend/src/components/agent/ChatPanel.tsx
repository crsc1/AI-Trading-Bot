import { type Component, For, Show, createSignal, onMount, onCleanup, createEffect } from 'solid-js';
import { marked } from 'marked';
import { agent, addMessage, addDecision, setPatternRecall, updateBrain, setChatConnected } from '../../signals/agent';
import { WSClient } from '../../lib/ws';
import type { ChatMessage, BrainState, BrainDecision, PatternRecall } from '../../types/agent';

// Configure marked for clean output
marked.setOptions({
  breaks: true,
  gfm: true,
});

function renderMarkdown(text: string): string {
  try {
    return marked.parse(text) as string;
  } catch {
    return text;
  }
}

export const ChatPanel: Component = () => {
  const [input, setInput] = createSignal('');
  const [sending, setSending] = createSignal(false);
  const [waiting, setWaiting] = createSignal(false);
  let chatWS: WSClient | null = null;
  let messagesEndRef: HTMLDivElement | undefined;
  let inputRef: HTMLTextAreaElement | undefined;

  createEffect(() => {
    void agent.messages.length;
    messagesEndRef?.scrollIntoView({ behavior: 'smooth' });
  });

  onMount(() => {
    const wsHost = window.location.hostname || 'localhost';
    chatWS = new WSClient({
      name: 'Chat',
      url: `ws://${wsHost}:8000/ws/chat`,
      onMessage: (data) => {
        switch (data.type) {
          case 'chat_message': {
            const msg = data.message as ChatMessage;
            addMessage(msg);
            if (msg.role === 'brain') setWaiting(false);
            break;
          }
          case 'thinking': {
            setWaiting(data.active === true);
            break;
          }
          case 'brain_state': {
            const state = data.state as BrainState;
            updateBrain(state);
            break;
          }
          case 'brain_decision': {
            const decision = data.decision as BrainDecision;
            updateBrain({
              last_action: decision.action,
              last_confidence: decision.confidence,
              last_reasoning: decision.reasoning,
              model: decision.model || '',
              cycle_number: decision.cycle || 0,
            });
            addDecision(decision);
            break;
          }
          case 'pattern_recall': {
            setPatternRecall(data as PatternRecall);
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
    setWaiting(true);
    chatWS.send({
      type: 'chat',
      message: text,
    });
    setInput('');
    setSending(false);
    // Resize textarea back
    if (inputRef) inputRef.style.height = '44px';
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function autoResize(el: HTMLTextAreaElement) {
    el.style.height = '44px';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  }

  return (
    <div class="flex flex-col h-full">
      {/* Messages */}
      <div class="flex-1 overflow-y-auto min-h-0">
        <Show when={agent.messages.length === 0}>
          <div class="flex items-center justify-center h-full">
            <div class="text-center px-6">
              <div class="text-[20px] text-text-secondary mb-3" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-weight: 500;">
                Market Brain
              </div>
              <div class="text-[14px] text-text-muted leading-relaxed" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                Ask about market conditions, chart analysis, setups, or anything about the platform.
                <br />Full Claude Code powers: file access, web search, codebase context.
              </div>
            </div>
          </div>
        </Show>

        <div class="max-w-[800px] mx-auto px-4 py-4 space-y-5">
          <For each={agent.messages}>
            {(msg) => (
              <div class={msg.role === 'user' ? 'flex justify-end' : ''}>
                <div class={`${msg.role === 'user' ? 'max-w-[85%]' : 'w-full'}`}>
                  {/* User bubble */}
                  <Show when={msg.role === 'user'}>
                    <div class="bg-accent/10 border border-accent/20 rounded-lg px-4 py-3">
                      <div class="chat-content text-[14px] text-text-primary leading-[1.6]"
                           style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;"
                           innerHTML={renderMarkdown(msg.content)} />
                    </div>
                  </Show>

                  {/* Brain response */}
                  <Show when={msg.role === 'brain'}>
                    <div class="py-1">
                      <div class="flex items-center gap-2 mb-2">
                        <span class="w-5 h-5 rounded-full bg-purple/20 flex items-center justify-center">
                          <span class="text-purple text-[10px] font-bold">AI</span>
                        </span>
                        <span class="text-[12px] text-text-muted" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                          {new Date(msg.timestamp).toLocaleTimeString('en-US', {
                            hour: '2-digit', minute: '2-digit', hour12: true,
                          })}
                        </span>
                      </div>
                      <div class="chat-content text-[14px] text-text-primary leading-[1.7] pl-7"
                           style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;"
                           innerHTML={renderMarkdown(msg.content)} />
                      {/* Token & timing stats */}
                      <Show when={msg.metadata?.duration_ms}>
                        <div class="pl-7 mt-2 flex items-center gap-3 text-[11px] text-text-muted font-data">
                          <span title="Time to respond">
                            {((msg.metadata!.duration_ms! / 1000)).toFixed(1)}s
                          </span>
                          <span class="w-px h-3 bg-border-default" />
                          <span title="Input tokens (including cache)">
                            {(msg.metadata!.input_tokens! || 0).toLocaleString()} in
                          </span>
                          <span title="Output tokens">
                            {(msg.metadata!.output_tokens! || 0).toLocaleString()} out
                          </span>
                          <span class="w-px h-3 bg-border-default" />
                          <span title="Cost for this message">
                            ${(msg.metadata!.cost_usd! || 0).toFixed(4)}
                          </span>
                        </div>
                      </Show>
                    </div>
                  </Show>

                  {/* System message */}
                  <Show when={msg.role === 'system'}>
                    <div class="text-center py-2">
                      <span class="text-[13px] text-text-muted italic"
                            style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                        {msg.content}
                      </span>
                    </div>
                  </Show>
                </div>
              </div>
            )}
          </For>

          {/* Thinking indicator */}
          <Show when={waiting()}>
            <div class="flex items-center gap-2 pl-7 py-2">
              <span class="w-5 h-5 rounded-full bg-purple/20 flex items-center justify-center">
                <span class="text-purple text-[10px] font-bold">AI</span>
              </span>
              <div class="flex items-center gap-1">
                <span class="w-1.5 h-1.5 rounded-full bg-purple/50 animate-pulse" />
                <span class="w-1.5 h-1.5 rounded-full bg-purple/50 animate-pulse" style="animation-delay: 0.2s" />
                <span class="w-1.5 h-1.5 rounded-full bg-purple/50 animate-pulse" style="animation-delay: 0.4s" />
              </div>
              <span class="text-[13px] text-text-muted" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                Thinking...
              </span>
            </div>
          </Show>
        </div>

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div class="border-t border-border-default bg-surface-1">
        <div class="max-w-[800px] mx-auto px-4 py-3">
          <div class="flex items-end gap-2 bg-surface-2 border border-purple/20 rounded-lg px-3 py-2 focus-within:border-purple/50 transition-colors">
            <textarea
              ref={inputRef}
              value={input()}
              onInput={(e) => {
                setInput(e.currentTarget.value);
                autoResize(e.currentTarget);
              }}
              onKeyDown={handleKeyDown}
              placeholder={agent.chatConnected ? 'Message Market Brain...' : 'Connecting...'}
              disabled={!agent.chatConnected || sending()}
              rows={1}
              class="flex-1 bg-transparent text-[14px] text-text-primary placeholder:text-text-muted focus:outline-none disabled:opacity-40 resize-none"
              style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; height: 44px; max-height: 120px; line-height: 1.5;"
            />
            <button
              onClick={sendMessage}
              disabled={!agent.chatConnected || !input().trim() || sending()}
              class="shrink-0 w-8 h-8 flex items-center justify-center bg-purple/80 text-white rounded-lg hover:bg-purple disabled:opacity-30 disabled:cursor-not-allowed transition-colors mb-0.5"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
          <div class="flex items-center gap-2 mt-1.5 px-1">
            <span class={`w-1.5 h-1.5 rounded-full ${agent.chatConnected ? 'bg-positive' : 'bg-negative'}`} />
            <span class="text-[12px] text-text-muted" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
              {agent.chatConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
