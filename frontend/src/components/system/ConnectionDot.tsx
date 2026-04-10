import type { Component } from 'solid-js';

export type DotTone = 'positive' | 'negative' | 'warning' | 'muted';

const toneClasses: Record<DotTone, string> = {
  positive: 'bg-positive',
  negative: 'bg-negative',
  warning: 'bg-warning',
  muted: 'bg-text-muted',
};

export const ConnectionDot: Component<{
  tone: DotTone;
  class?: string;
}> = (props) => (
  <div
    class={`w-1.5 h-1.5 rounded-full shrink-0 ${toneClasses[props.tone]} ${props.class ?? ''}`}
  />
);
