import { type Component, For } from 'solid-js';

const DEFAULT_SYMBOLS = ['SPY', 'QQQ', 'IWM', 'NVDA', 'AAPL', 'TSLA'];

export const QuickSymbols: Component<{
  symbols?: string[];
  active: string;
  loading?: string | null;
  onSelect: (symbol: string) => void;
}> = (props) => {
  const symbols = () => props.symbols ?? DEFAULT_SYMBOLS;

  return (
    <div class="flex items-center gap-1">
      <For each={symbols()}>
        {(symbol) => (
          <button
            class={`rounded-lg px-2.5 py-1 font-display text-[10px] font-semibold uppercase tracking-[0.1em] transition-colors ${
              props.active === symbol
                ? 'bg-accent/14 text-accent'
                : 'text-text-muted hover:text-text-secondary hover:bg-surface-2'
            }`}
            onClick={() => props.onSelect(symbol)}
            disabled={!!props.loading}
          >
            {props.loading === symbol ? '...' : symbol}
          </button>
        )}
      </For>
    </div>
  );
};
