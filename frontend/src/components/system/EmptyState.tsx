import { type Component, Show } from 'solid-js';

interface EmptyStateProps {
  title: string;
  description?: string;
  eyebrow?: string;
  class?: string;
}

export const EmptyState: Component<EmptyStateProps> = (props) => (
  <div class={`flex items-center justify-center h-full px-6 py-8 text-center ${props.class || ''}`}>
    <div class="max-w-[320px]">
      <Show when={props.eyebrow}>
        <div class="font-display text-[9px] uppercase tracking-[0.16em] text-text-muted">{props.eyebrow}</div>
      </Show>
      <div class="mt-2 text-[18px] text-text-secondary font-display font-medium">
        {props.title}
      </div>
      <Show when={props.description}>
        <div class="mt-2 text-[12px] leading-relaxed text-text-muted font-sans">
          {props.description}
        </div>
      </Show>
    </div>
  </div>
);
