import { type Component, type JSX, Show } from 'solid-js';

interface WidgetFrameProps {
  title: string;
  subtitle?: string;
  badge?: string;
  badgeTone?: 'neutral' | 'positive' | 'warning' | 'negative' | 'accent';
  actions?: JSX.Element;
  class?: string;
  contentClass?: string;
  children: JSX.Element;
}

const badgeToneClasses = {
  neutral: 'border-border-default bg-surface-2 text-text-secondary',
  positive: 'border-positive/45 bg-positive/12 text-positive',
  warning: 'border-warning/45 bg-warning/12 text-warning',
  negative: 'border-negative/45 bg-negative/12 text-negative',
  accent: 'border-accent/45 bg-accent/12 text-accent',
};

export const WidgetFrame: Component<WidgetFrameProps> = (props) => {
  const badgeTone = () => props.badgeTone || 'neutral';

  return (
    <section class={`rounded-2xl border-[1.5px] border-border-default bg-[#06080b] shadow-[0_18px_40px_rgba(0,0,0,0.28)] ${props.class || ''}`}>
      <div class="flex items-start justify-between gap-4 px-5 py-4 border-b-[1.5px] border-border-default bg-[#050608]">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <h2 class="font-display text-[12px] font-semibold tracking-[0.08em] uppercase text-text-primary">
              {props.title}
            </h2>
            <Show when={props.badge}>
              <span class={`rounded-full border-[1.5px] px-2.5 py-1 font-display text-[9px] font-semibold uppercase tracking-[0.16em] ${badgeToneClasses[badgeTone()]}`}>
                {props.badge}
              </span>
            </Show>
          </div>
          <Show when={props.subtitle}>
            <div class="mt-1.5 text-[11px] text-text-secondary font-data truncate">
              {props.subtitle}
            </div>
          </Show>
        </div>

        <Show when={props.actions}>
          <div class="shrink-0">
            {props.actions}
          </div>
        </Show>
      </div>

      <div class={props.contentClass || 'p-5'}>
        {props.children}
      </div>
    </section>
  );
};
