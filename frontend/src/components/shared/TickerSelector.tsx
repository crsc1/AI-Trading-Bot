import { type Component, createSignal, Show, For, onCleanup } from 'solid-js';
import { market } from '../../signals/market';
import { switchSymbol } from '../../lib/data';

const QUICK_SYMBOLS = ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA', 'AMZN', 'META', 'MSFT', 'GOOGL', 'AMD'];

export const TickerSelector: Component = () => {
  const [open, setOpen] = createSignal(false);
  const [input, setInput] = createSignal('');
  let inputRef: HTMLInputElement | undefined;
  let containerRef: HTMLDivElement | undefined;

  const filtered = () => {
    const q = input().toUpperCase();
    if (!q) return QUICK_SYMBOLS;
    return QUICK_SYMBOLS.filter(s => s.includes(q));
  };

  const select = (sym: string) => {
    const s = sym.toUpperCase().trim();
    if (s && s !== market.symbol) switchSymbol(s);
    setOpen(false);
    setInput('');
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      const val = input().toUpperCase().trim();
      if (val) select(val);
      else if (filtered().length > 0) select(filtered()[0]);
    } else if (e.key === 'Escape') {
      setOpen(false);
      setInput('');
    }
  };

  // Close on outside click
  const handleClickOutside = (e: MouseEvent) => {
    if (containerRef && !containerRef.contains(e.target as Node)) {
      setOpen(false);
      setInput('');
    }
  };

  if (typeof document !== 'undefined') {
    document.addEventListener('mousedown', handleClickOutside);
    onCleanup(() => document.removeEventListener('mousedown', handleClickOutside));
  }

  return (
    <div ref={containerRef} class="relative">
      <button
        class="font-display text-[14px] font-medium px-2 py-0.5 rounded hover:bg-surface-2 transition-colors cursor-pointer"
        onClick={() => { setOpen(!open()); setTimeout(() => inputRef?.focus(), 10); }}
      >
        {market.symbol}
        <span class="text-text-muted text-[10px] ml-1">▾</span>
      </button>

      <Show when={open()}>
        <div class="absolute top-full left-0 mt-1 z-50 bg-surface-1 border border-border-default rounded-lg shadow-xl min-w-[280px]">
          {/* Search input */}
          <div class="p-2 border-b border-border-default">
            <input
              ref={inputRef}
              type="text"
              placeholder="Type symbol..."
              maxLength={5}
              value={input()}
              onInput={(e) => setInput(e.currentTarget.value.toUpperCase())}
              onKeyDown={onKeyDown}
              class="w-full bg-surface-2 border border-border-default rounded px-2 py-1.5 text-[12px] font-display text-text-primary placeholder:text-text-muted outline-none focus:border-border-strong"
            />
          </div>

          {/* Quick-access symbols */}
          <div class="p-2 flex flex-wrap gap-1">
            <For each={filtered()}>
              {(sym) => (
                <button
                  class={`px-2.5 py-1 rounded text-[11px] font-display font-medium transition-colors cursor-pointer ${
                    sym === market.symbol
                      ? 'bg-accent/20 text-accent border border-accent/30'
                      : 'bg-surface-2 text-text-secondary hover:bg-surface-3 hover:text-text-primary border border-transparent'
                  }`}
                  onClick={() => select(sym)}
                >
                  {sym}
                </button>
              )}
            </For>
          </div>

          {/* Hint */}
          <Show when={input() && !QUICK_SYMBOLS.includes(input().toUpperCase())}>
            <div class="px-2 pb-2">
              <button
                class="w-full px-2 py-1.5 rounded bg-surface-2 hover:bg-surface-3 text-[11px] font-display text-text-secondary hover:text-text-primary transition-colors text-left cursor-pointer"
                onClick={() => select(input())}
              >
                Switch to <span class="font-medium text-text-primary">{input().toUpperCase()}</span> ↵
              </button>
            </div>
          </Show>
        </div>
      </Show>
    </div>
  );
};
