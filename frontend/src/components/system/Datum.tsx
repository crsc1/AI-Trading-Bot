import { type Component } from 'solid-js';

interface DatumProps {
  label: string;
  value: string;
  class?: string;
}

export const Datum: Component<DatumProps> = (props) => (
  <div class={props.class || ''}>
    <div class="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted">{props.label}</div>
    <div class="mt-1.5 font-data text-[12px] font-semibold text-text-primary leading-snug">{props.value}</div>
  </div>
);
