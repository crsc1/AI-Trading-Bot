import type { Component } from 'solid-js';
import { fmtPremium } from '../../lib/format';

export const FlowSummaryBar: Component<{
  bullPremium: number;
  bearPremium: number;
}> = (props) => (
  <div class="flex border-b border-border-subtle">
    <div class="flex-1 px-3 py-2">
      <div class="font-display text-[9px] font-semibold uppercase tracking-[0.12em] text-text-muted">Bull</div>
      <div class="font-data text-[13px] font-semibold text-positive">{fmtPremium(props.bullPremium)}</div>
    </div>
    <div class="flex-1 px-3 py-2 border-l border-border-subtle">
      <div class="font-display text-[9px] font-semibold uppercase tracking-[0.12em] text-text-muted">Bear</div>
      <div class="font-data text-[13px] font-semibold text-negative">{fmtPremium(props.bearPremium)}</div>
    </div>
  </div>
);
