import { type Component, For, Show, createSignal, createMemo, onCleanup } from 'solid-js';
import { market, setChartInterval, setChartRange } from '../../signals/market';
import type { ChartInterval, ChartRange } from '../../types/market';
import { searchIndicators, overlayIndicators, oscillatorIndicators, type IndicatorInfo } from '../../lib/indicatorRegistry';

const ranges: { label: string; value: ChartRange }[] = [
  { label: '1D', value: '1D' },
  { label: '1W', value: '1W' },
  { label: '1M', value: '1M' },
  { label: '3M', value: '3M' },
  { label: '1Y', value: '1Y' },
  { label: 'MAX', value: 'MAX' },
];

const intervals: { label: string; value: ChartInterval }[] = [
  { label: '1m', value: '1Min' },
  { label: '2m', value: '2Min' },
  { label: '5m', value: '5Min' },
  { label: '10m', value: '10Min' },
  { label: '15m', value: '15Min' },
  { label: '30m', value: '30Min' },
  { label: '1h', value: '1H' },
  { label: '4h', value: '4Hour' },
  { label: '1d', value: '1D' },
  { label: '1w', value: '1Week' },
];

// Assign colors to indicators deterministically
const palette = [
  '#ffb300', '#ff7043', '#42a5f5', '#00e5ff', '#ab47bc',
  '#26a69a', '#ef5350', '#66bb6a', '#ffa726', '#8d6e63',
  '#5c6bc0', '#29b6f6', '#ec407a', '#d4e157', '#78909c',
  '#7e57c2', '#00bcd4', '#ff8a65', '#aed581', '#4dd0e1',
];

export function getIndicatorColor(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = ((hash << 5) - hash + id.charCodeAt(i)) | 0;
  return palette[Math.abs(hash) % palette.length];
}

interface Props {
  indicators: Set<string>;
  onToggle: (id: string) => void;
  priceScaleMode?: number;
  onCyclePriceScale?: () => void;
}

export const ChartControls: Component<Props> = (props) => {
  const [open, setOpen] = createSignal(false);
  const [search, setSearch] = createSignal('');
  let panelRef: HTMLDivElement | undefined;
  let searchRef: HTMLInputElement | undefined;

  const activeCount = () => props.indicators.size;

  const filtered = createMemo(() => {
    const q = search();
    if (!q) return null; // Show categorized view
    return searchIndicators(q);
  });

  const handleClickOutside = (e: MouseEvent) => {
    if (panelRef && !panelRef.contains(e.target as Node)) close();
  };

  const openPanel = () => {
    setOpen(true);
    setSearch('');
    document.addEventListener('mousedown', handleClickOutside);
    setTimeout(() => searchRef?.focus(), 50);
  };

  const close = () => {
    setOpen(false);
    document.removeEventListener('mousedown', handleClickOutside);
  };

  onCleanup(() => document.removeEventListener('mousedown', handleClickOutside));

  return (
    <div class="min-h-[56px] flex flex-wrap items-center gap-2 px-4 py-2 bg-surface-1 border-b border-border-default shrink-0 font-display">
      <div class="flex items-center gap-1.5">
        <span class="text-[9px] uppercase tracking-[0.16em] text-text-muted">Range</span>
        <div class="flex items-center gap-0.5">
          <For each={ranges}>
            {(range) => (
              <button
                class={`px-2.5 py-1 text-[11px] rounded transition-colors ${
                  market.range === range.value
                    ? 'bg-accent text-white'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-3'
                }`}
                onClick={() => setChartRange(range.value)}
              >
                {range.label}
              </button>
            )}
          </For>
        </div>
      </div>

      <div class="w-px h-5 bg-border-default hidden md:block" />

      <div class="flex items-center gap-1.5">
        <span class="text-[9px] uppercase tracking-[0.16em] text-text-muted">Bars</span>
        <div class="flex items-center gap-0.5">
          <For each={intervals}>
            {(tf) => (
            <button
              class={`px-2.5 py-1 text-[11px] rounded transition-colors ${
                market.interval === tf.value
                  ? 'bg-accent text-white'
                  : 'text-text-secondary hover:text-text-primary hover:bg-surface-3'
              }`}
              onClick={() => setChartInterval(tf.value)}
            >
              {tf.label}
            </button>
          )}
          </For>
        </div>
      </div>

      <div class="w-px h-5 bg-border-default" />

      {/* Price scale mode */}
      <Show when={props.onCyclePriceScale}>
        <button
          class="px-2 py-1 text-[10px] text-text-muted hover:text-text-primary hover:bg-surface-2 rounded transition-colors"
          onClick={props.onCyclePriceScale}
          title="Toggle price scale: Linear / Logarithmic / Percentage"
        >
          {['LIN', 'LOG', '%'][props.priceScaleMode ?? 0]}
        </button>
        <div class="w-px h-5 bg-border-default" />
      </Show>

      {/* Indicator picker */}
      <div class="relative" ref={panelRef}>
        <button
          class={`flex items-center gap-1.5 px-3 py-1 text-[11px] rounded transition-colors ${
            open() ? 'bg-surface-3 text-text-primary' : 'text-text-secondary hover:text-text-primary hover:bg-surface-2'
          }`}
          onClick={() => open() ? close() : openPanel()}
        >
          <span>Indicators</span>
          <Show when={activeCount() > 0}>
            <span class="bg-accent/20 text-accent text-[9px] px-1.5 py-0.5 rounded-full">
              {activeCount()}
            </span>
          </Show>
        </button>

        <Show when={open()}>
          <div class="absolute top-full left-0 mt-1 w-[280px] bg-surface-1 border border-border-default rounded shadow-lg z-50 max-h-[420px] flex flex-col">
            {/* Search */}
            <div class="px-3 py-2 border-b border-border-default">
              <input
                ref={searchRef}
                type="text"
                value={search()}
                onInput={(e) => setSearch(e.currentTarget.value)}
                placeholder="Search 292 indicators..."
                class="w-full bg-surface-2 border border-border-default rounded px-2.5 py-1.5 text-[11px] text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none font-data"
              />
            </div>

            {/* Results */}
            <div class="flex-1 overflow-y-auto min-h-0">
              <Show when={filtered() !== null} fallback={
                /* Categorized view */
                <>
                  <CategorySection
                    title="OVERLAY"
                    count={overlayIndicators.length}
                    items={overlayIndicators}
                    active={props.indicators}
                    onToggle={props.onToggle}
                  />
                  <CategorySection
                    title="OSCILLATORS & LOWER"
                    count={oscillatorIndicators.length}
                    items={oscillatorIndicators}
                    active={props.indicators}
                    onToggle={props.onToggle}
                  />
                </>
              }>
                <div class="py-1">
                  <Show when={filtered()!.length === 0}>
                    <div class="px-3 py-4 text-text-muted text-[11px] text-center">
                      No indicators match "{search()}"
                    </div>
                  </Show>
                  <For each={filtered()!}>
                    {(ind) => (
                      <IndicatorRow
                        indicator={ind}
                        active={props.indicators.has(ind.id)}
                        onToggle={() => props.onToggle(ind.id)}
                      />
                    )}
                  </For>
                </div>
              </Show>
            </div>
          </div>
        </Show>
      </div>
    </div>
  );
};

// ── Category Section ───────────────────────────────────────────────────────

const CategorySection: Component<{
  title: string;
  count: number;
  items: IndicatorInfo[];
  active: Set<string>;
  onToggle: (id: string) => void;
}> = (props) => {
  const [expanded, setExpanded] = createSignal(true);

  return (
    <div class="border-b border-border-default last:border-0">
      <button
        class="w-full flex items-center justify-between px-3 py-2 hover:bg-surface-2/30"
        onClick={() => setExpanded(!expanded())}
      >
        <span class="text-[9px] font-medium text-text-muted tracking-wider">{props.title}</span>
        <span class="text-[9px] text-text-muted">{props.count}</span>
      </button>
      <Show when={expanded()}>
        <div class="pb-1">
          <For each={props.items}>
            {(ind) => (
              <IndicatorRow
                indicator={ind}
                active={props.active.has(ind.id)}
                onToggle={() => props.onToggle(ind.id)}
              />
            )}
          </For>
        </div>
      </Show>
    </div>
  );
};

// ── Indicator Row ──────────────────────────────────────────────────────────

const IndicatorRow: Component<{
  indicator: IndicatorInfo;
  active: boolean;
  onToggle: () => void;
}> = (props) => {
  const color = () => getIndicatorColor(props.indicator.id);

  return (
    <button
      class={`flex items-center gap-2.5 w-full px-3 py-1.5 text-left transition-colors ${
        props.active
          ? 'bg-surface-2 text-text-primary'
          : 'text-text-secondary hover:bg-surface-2/50 hover:text-text-primary'
      }`}
      onClick={props.onToggle}
    >
      <span
        class="w-2 h-2 rounded-full shrink-0"
        style={{
          background: props.active ? color() : 'transparent',
          border: props.active ? 'none' : `1.5px solid ${color()}`,
        }}
      />
      <div class="flex-1 min-w-0">
        <div class="text-[11px] font-medium truncate">{props.indicator.shortTitle}</div>
        <Show when={props.indicator.title !== props.indicator.shortTitle}>
          <div class="text-[9px] text-text-muted truncate">{props.indicator.title}</div>
        </Show>
      </div>
      <span class="text-[8px] text-text-muted shrink-0">
        {props.indicator.overlay ? 'overlay' : 'pane'}
      </span>
      <Show when={props.active}>
        <span class="text-accent text-[11px] shrink-0">&#10003;</span>
      </Show>
    </button>
  );
};
