import type { Component } from 'solid-js';
import { fmtTime, fmtPremium } from '../../lib/format';

export interface FlowTradeData {
  timestamp: number;
  right: 'C' | 'P';
  strike: number;
  size: number;
  premium: number;
  side: 'buy' | 'sell' | 'mid';
  tag?: 'normal' | 'sweep' | 'block' | 'whale';
}

const tagLabel: Record<string, string> = {
  sweep: 'SWP',
  block: 'BLK',
  whale: 'WHL',
};

const tagColor: Record<string, string> = {
  sweep: 'text-warning',
  block: 'text-accent',
  whale: 'text-purple',
};

export const FlowTradeRow: Component<{
  trade: FlowTradeData;
  compact?: boolean;
}> = (props) => {
  const t = () => props.trade;
  const sideColor = () =>
    t().side === 'buy' ? 'text-positive' : t().side === 'sell' ? 'text-negative' : 'text-text-primary';

  return (
    <div class="flex items-center gap-2 px-3 py-1.5 border-t border-border-subtle">
      <span class="font-data text-[10px] text-text-muted shrink-0">{fmtTime(t().timestamp)}</span>
      <span class={`font-data text-[11px] font-semibold ${t().right === 'C' ? 'text-positive' : 'text-negative'}`}>
        {t().right} {t().strike}
      </span>
      <span class="font-data text-[10px] text-text-secondary">{t().size}x</span>
      {t().tag && t().tag !== 'normal' && (
        <span class={`font-display text-[9px] font-semibold uppercase tracking-[0.1em] ${tagColor[t().tag!] ?? 'text-text-muted'}`}>
          {tagLabel[t().tag!] ?? ''}
        </span>
      )}
      <span class={`font-data text-[11px] font-semibold ml-auto ${sideColor()}`}>
        {fmtPremium(t().premium)}
      </span>
    </div>
  );
};
