import { type Component, For } from 'solid-js';
import { market, setTimeframe } from '../../signals/market';
import type { Timeframe } from '../../types/market';

const timeframes: { label: string; value: Timeframe }[] = [
  { label: '1m', value: '1Min' },
  { label: '5m', value: '5Min' },
  { label: '15m', value: '15Min' },
  { label: '1h', value: '1H' },
  { label: '1d', value: '1D' },
];

const indicatorDefs = [
  { id: 'ema9', label: 'EMA 9', color: '#ffb300' },
  { id: 'ema21', label: 'EMA 21', color: '#ff7043' },
  { id: 'sma50', label: 'SMA 50', color: '#42a5f5' },
  { id: 'vwap', label: 'VWAP', color: '#00e5ff' },
  { id: 'bb', label: 'BB', color: '#42a5f5' },
  { id: 'rsi', label: 'RSI', color: '#ab47bc' },
];

interface Props {
  indicators: Set<string>;
  onToggle: (id: string) => void;
}

export const ChartControls: Component<Props> = (props) => {
  return (
    <div class="h-[26px] flex items-center gap-1 px-2 bg-surface-2 border-b border-border-default shrink-0 overflow-x-auto">
      {/* Timeframe selector */}
      <div class="flex items-center gap-px mr-2">
        <For each={timeframes}>
          {(tf) => (
            <button
              class={`px-2 py-0.5 text-[9px] rounded transition-colors ${
                market.timeframe === tf.value
                  ? 'bg-accent text-white'
                  : 'text-text-secondary hover:text-text-primary hover:bg-surface-3'
              }`}
              onClick={() => setTimeframe(tf.value)}
            >
              {tf.label}
            </button>
          )}
        </For>
      </div>

      <div class="w-px h-3 bg-border-default" />

      {/* Indicator toggles */}
      <div class="flex items-center gap-1 ml-2">
        <For each={indicatorDefs}>
          {(ind) => (
            <button
              class={`px-1.5 py-0.5 text-[8px] rounded border transition-colors ${
                props.indicators.has(ind.id)
                  ? 'border-current opacity-100'
                  : 'border-transparent opacity-40 hover:opacity-70'
              }`}
              style={{ color: ind.color }}
              onClick={() => props.onToggle(ind.id)}
            >
              {ind.label}
            </button>
          )}
        </For>
      </div>
    </div>
  );
};
