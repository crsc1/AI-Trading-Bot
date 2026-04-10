import { type Component, For, Show } from 'solid-js';
import { fmtPrice } from '../../lib/format';

export interface KeyLevel {
  label: string;
  value: number | null | undefined;
  tone?: string;
}

export const KeyLevelGrid: Component<{
  levels: KeyLevel[];
  cols?: number;
}> = (props) => {
  const visible = () => props.levels.filter(l => l.value != null && isFinite(l.value as number));

  return (
    <Show when={visible().length > 0} fallback={
      <div class="text-[10px] text-text-muted">No levels</div>
    }>
      <div class={`grid gap-x-3 gap-y-1.5 ${props.cols === 1 ? 'grid-cols-1' : 'grid-cols-2'}`}>
        <For each={visible()}>
          {(level) => (
            <div class="flex items-baseline justify-between">
              <span class="font-display text-[10px] text-text-muted">{level.label}</span>
              <span class={`font-data text-[11px] font-semibold ${level.tone ?? 'text-text-primary'}`}>
                {fmtPrice(level.value as number)}
              </span>
            </div>
          )}
        </For>
      </div>
    </Show>
  );
};
