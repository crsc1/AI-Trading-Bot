import { type Component, For, Show } from 'solid-js';
import { fmtPrice } from '../../lib/format';

export interface ChainRow {
  strike: number;
  call: { last: number; delta: number | null; iv?: number | null; volume?: number };
  put: { last: number; delta: number | null; iv?: number | null; volume?: number };
}

export const ChainStrip: Component<{
  rows: ChainRow[];
  spotPrice: number;
  title?: string;
}> = (props) => (
  <div>
    <Show when={props.title}>
      <div class="px-3 py-2.5">
        <div class="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted">
          {props.title}
          <Show when={props.spotPrice > 0}>
            <span class="ml-2 normal-case tracking-normal font-data text-text-secondary">
              {fmtPrice(props.spotPrice)}
            </span>
          </Show>
        </div>
      </div>
    </Show>
    <Show when={props.rows.length > 0} fallback={
      <div class="px-3 pb-3 text-[10px] text-text-muted">Waiting for chain...</div>
    }>
      <div class="text-[10px] font-display font-semibold uppercase tracking-[0.12em] text-text-muted grid grid-cols-[1fr_56px_1fr] gap-1 px-3 pb-1">
        <span class="text-right">Calls</span>
        <span class="text-center">Strike</span>
        <span>Puts</span>
      </div>
      <For each={props.rows}>
        {(row) => (
          <div class={`grid grid-cols-[1fr_56px_1fr] gap-1 px-3 py-1.5 border-t border-border-subtle ${
            Math.abs(row.strike - props.spotPrice) < 0.5 ? 'bg-accent/6' : ''
          }`}>
            <div class="text-right">
              <span class="font-data text-[11px] font-semibold text-positive">
                {row.call.last > 0 ? row.call.last.toFixed(2) : '—'}
              </span>
              <span class="font-data text-[9px] text-text-muted ml-1">
                {row.call.delta != null ? row.call.delta.toFixed(2) : ''}
              </span>
            </div>
            <div class="text-center font-display text-[11px] font-semibold text-text-primary">
              {row.strike}
            </div>
            <div>
              <span class="font-data text-[11px] font-semibold text-negative">
                {row.put.last > 0 ? row.put.last.toFixed(2) : '—'}
              </span>
              <span class="font-data text-[9px] text-text-muted ml-1">
                {row.put.delta != null ? row.put.delta.toFixed(2) : ''}
              </span>
            </div>
          </div>
        )}
      </For>
    </Show>
  </div>
);
