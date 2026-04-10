import { type Component, Show } from 'solid-js';

interface MetricTileProps {
  label: string;
  value: string;
  subvalue?: string;
  tone?: string;
  class?: string;
}

export const MetricTile: Component<MetricTileProps> = (props) => (
  <div class={`rounded-xl border-[1.5px] border-border-default bg-surface-2/72 px-4 py-3 ${props.class || ''}`}>
    <div class="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted">{props.label}</div>
    <div class={`mt-1.5 font-data text-[16px] font-semibold leading-tight ${props.tone || 'text-text-primary'}`}>{props.value}</div>
    <Show when={props.subvalue}>
      <div class="mt-1 font-data text-[11px] text-text-muted">{props.subvalue}</div>
    </Show>
  </div>
);
