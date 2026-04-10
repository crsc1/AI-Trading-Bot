import { type Component, Show } from 'solid-js';

type Tone = 'neutral' | 'positive' | 'negative' | 'warning' | 'accent';

interface StatusPillProps {
  label: string;
  value?: string | null;
  tone?: Tone;
  compact?: boolean;
}

const toneClasses: Record<Tone, string> = {
  neutral: 'border-border-default bg-surface-2 text-text-secondary',
  positive: 'border-positive/45 bg-positive/12 text-positive',
  negative: 'border-negative/45 bg-negative/12 text-negative',
  warning: 'border-warning/45 bg-warning/12 text-warning',
  accent: 'border-accent/45 bg-accent/12 text-accent',
};

export const StatusPill: Component<StatusPillProps> = (props) => {
  const tone = () => props.tone || 'neutral';

  return (
    <div class={`rounded-full border-[1.5px] px-3 ${props.compact ? 'py-1.5' : 'py-2'} leading-none ${toneClasses[tone()]}`}>
      <div class="flex items-center gap-1.5">
        <span class="font-display text-[9px] font-semibold uppercase tracking-[0.16em] opacity-80">{props.label}</span>
        <Show when={props.value}>
          <span class="font-data text-[11px] font-semibold text-current">{props.value}</span>
        </Show>
      </div>
    </div>
  );
};
