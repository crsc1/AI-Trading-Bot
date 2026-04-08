import { type Component, For, Show, createSignal, onCleanup } from 'solid-js';
import { market } from '../../signals/market';
import { flow } from '../../signals/flow';
import { findIndicator } from '../../lib/indicatorRegistry';
import { calcVWAP, calcBB } from '../../lib/indicators';
import { getIndicatorColor } from './ChartControls';

interface LegendEntry {
  id: string;
  label: string;
  color: string;
  value: string;
}

interface Props {
  indicators: Set<string>;
  onRemove: (id: string) => void;
}

export const ChartLegend: Component<Props> = (props) => {
  const [entries, setEntries] = createSignal<LegendEntry[]>([]);

  // Update legend values on a 1-second interval, NOT reactively on every tick.
  // This prevents the legend from triggering reflows during live trading.
  const timer = setInterval(() => {
    const candles = market.candles;
    if (candles.length === 0) { setEntries([]); return; }

    const result: LegendEntry[] = [];

    for (const id of props.indicators) {
      if (id === 'vwap') {
        const data = calcVWAP(candles);
        const val = data.length > 0 ? data[data.length - 1].value.toFixed(2) : '---';
        result.push({ id: 'vwap', label: 'VWAP', color: '#00e5ff', value: val });
        continue;
      }
      if (id === 'bollinger-bands') {
        const bb = calcBB(candles, 20, 2);
        const u = bb.upper.length > 0 ? bb.upper[bb.upper.length - 1].value.toFixed(2) : '---';
        const l = bb.lower.length > 0 ? bb.lower[bb.lower.length - 1].value.toFixed(2) : '---';
        result.push({ id, label: 'BB Area', color: '#42a5f5', value: `${u} / ${l}` });
        continue;
      }
      if (id === 'net-delta') {
        const clouds = flow.clouds;
        const totalDelta = clouds.reduce((sum, c) => sum + c.delta, 0);
        result.push({ id, label: 'Net Delta', color: totalDelta >= 0 ? '#00C805' : '#FF5000', value: totalDelta.toFixed(0) });
        continue;
      }

      const info = findIndicator(id);
      if (!info) continue;

      try {
        const res = info.module.calculate(candles);
        if (!res?.plots) continue;
        const plotEntries = Object.entries(res.plots);
        if (plotEntries.length === 0) continue;
        const values: string[] = [];
        for (const [, plotData] of plotEntries.slice(0, 3)) {
          const arr = (plotData as { value: number }[]).filter(d => d.value != null && isFinite(d.value));
          if (arr.length > 0) values.push(arr[arr.length - 1].value.toFixed(2));
        }
        result.push({
          id, label: info.shortTitle, color: getIndicatorColor(id),
          value: values.join(' / ') || '---',
        });
      } catch {
        result.push({ id, label: info.shortTitle, color: getIndicatorColor(id), value: 'err' });
      }
    }

    setEntries(result);
  }, 1000);

  onCleanup(() => clearInterval(timer));

  return (
    <Show when={entries().length > 0}>
      <div class="absolute top-2 left-3 z-10 flex flex-col gap-0.5" style={{ "pointer-events": "auto" }}>
        <For each={entries()}>
          {(entry) => (
            <div class="group flex items-center gap-2 px-2 py-0.5 rounded bg-surface-0/80 backdrop-blur-sm hover:bg-surface-1/90 transition-colors">
              <span
                class="w-1.5 h-1.5 rounded-full shrink-0"
                style={{ background: entry.color }}
              />
              <span class="font-display text-[10px] text-text-secondary">{entry.label}</span>
              <span class="font-data text-[10px] text-text-primary tabular-nums">{entry.value}</span>
              <button
                class="text-text-muted hover:text-negative text-[10px] opacity-0 group-hover:opacity-100 transition-opacity ml-1"
                onClick={() => props.onRemove(entry.id)}
              >
                &#215;
              </button>
            </div>
          )}
        </For>
      </div>
    </Show>
  );
};
