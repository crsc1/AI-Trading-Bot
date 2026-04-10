import { For } from 'solid-js';

export interface SegmentedOption<T extends string> {
  label: string;
  value: T;
  testId?: string;
}

interface SegmentedControlProps<T extends string> {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
}

export const SegmentedControl = <T extends string>(props: SegmentedControlProps<T>) => (
  <div class="flex flex-wrap items-center gap-2">
    <For each={props.options}>
      {(option) => (
        <button
          data-testid={option.testId}
          class={`px-3 py-1.5 text-[11px] rounded-lg border transition-colors ${
            props.value === option.value
              ? 'border-accent bg-accent/90 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]'
              : 'border-border-default text-text-secondary hover:text-text-primary hover:bg-surface-3'
          }`}
          onClick={() => props.onChange(option.value)}
        >
          {option.label}
        </button>
      )}
    </For>
  </div>
);
