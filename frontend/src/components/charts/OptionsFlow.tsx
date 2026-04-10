/**
 * Options Flow Tape — Real-time 0DTE option trade feed.
 *
 * Professional tape format matching Unusual Whales / FlowAlgo:
 * - Time, Type (C/P), Strike, Size, Price, Premium, Exchange
 * - Color: calls green, puts red
 * - Tags: SWEEP (multi-exchange fill), BLOCK (100+ contracts), WHALE ($100K+ premium)
 * - Premium-weighted: larger trades are visually prominent
 * - Running call/put premium ratio bar at top
 */
import { type Component, For, Show } from 'solid-js';
import { optionsFlow, getCluster } from '../../signals/optionsFlow';
import { EmptyState } from '../system/EmptyState';

function formatPremium(p: number): string {
  if (p >= 1_000_000) return `$${(p / 1_000_000).toFixed(1)}M`;
  if (p >= 1_000) return `$${(p / 1_000).toFixed(0)}K`;
  return `$${p.toFixed(0)}`;
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
}

const TAG_STYLES = {
  sweep: 'bg-purple/20 text-purple border-purple/30',
  block: 'bg-accent/20 text-accent border-accent/30',
  whale: 'bg-warning/20 text-warning border-warning/30',
  normal: '',
};

const TAG_LABELS = {
  sweep: 'SWEEP',
  block: 'BLOCK',
  whale: 'WHALE',
  normal: '',
};

export const OptionsFlow: Component = () => {
  const bullPct = () => {
    const total = optionsFlow.totalBullishPremium + optionsFlow.totalBearishPremium;
    if (total === 0) return 50;
    return Math.round((optionsFlow.totalBullishPremium / total) * 100);
  };

  // Latest VPIN from most recent trade
  const latestVpin = () => {
    const trades = optionsFlow.trades;
    if (trades.length === 0) return null;
    return trades[0].vpin;
  };

  const vpinColor = () => {
    const v = latestVpin();
    if (v == null) return 'text-text-muted';
    if (v >= 0.7) return 'text-warning';
    if (v >= 0.5) return 'text-accent';
    return 'text-text-secondary';
  };

  const vpinLabel = () => {
    const v = latestVpin();
    if (v == null) return '—';
    if (v >= 0.7) return 'TOXIC';
    if (v >= 0.5) return 'ELEVATED';
    return 'NORMAL';
  };

  return (
    <div class="flex flex-col h-full">
      {/* Header with running totals — h-[72px] matched with OptionsHeatmap */}
      <div class="px-4 py-2 h-[72px] border-b border-border-default shrink-0 flex flex-col justify-between">
        <div class="flex items-center justify-between">
          <span class="font-display text-[13px] font-medium text-text-primary">
            Options Flow
          </span>
          <div class="flex items-center gap-3">
            <Show when={latestVpin() != null}>
              <span class={`font-data text-[10px] ${vpinColor()}`}>
                VPIN {((latestVpin() ?? 0) * 100).toFixed(0)}% {vpinLabel()}
              </span>
            </Show>
            <span class="font-data text-[10px] text-text-secondary">
              {optionsFlow.tradeCount} trades
            </span>
          </div>
        </div>

        {/* Bullish/Bearish premium bar */}
        <div class="flex items-center gap-3">
          <span class="font-data text-[11px] text-positive w-20">
            {formatPremium(optionsFlow.totalBullishPremium)}
          </span>
          <div class="flex-1 h-2 bg-surface-3 rounded-sm overflow-hidden flex">
            <div
              class="h-full bg-positive/60 transition-all duration-300"
              style={{ width: `${bullPct()}%` }}
            />
            <div
              class="h-full bg-negative/60 transition-all duration-300"
              style={{ width: `${100 - bullPct()}%` }}
            />
          </div>
          <span class="font-data text-[11px] text-negative w-20 text-right">
            {formatPremium(optionsFlow.totalBearishPremium)}
          </span>
        </div>
        <div class="flex items-center justify-between">
          <span class="font-display text-[9px] text-text-secondary">BULL {bullPct()}%</span>
          <span class="font-display text-[9px] text-text-secondary">BEAR {100 - bullPct()}%</span>
        </div>
      </div>

      {/* Column headers */}
      <div class="flex items-center px-3 py-1.5 text-[8px] font-display text-text-secondary tracking-wider border-b border-border-default shrink-0">
        <span class="w-14">TIME</span>
        <span class="w-8">SIDE</span>
        <span class="w-7">C/P</span>
        <span class="w-11 text-right">STRIKE</span>
        <span class="w-10 text-right">SIZE</span>
        <span class="w-12 text-right">PRICE</span>
        <span class="w-10 text-right">IV</span>
        <span class="flex-1 text-right">PREMIUM</span>
        <span class="w-8 text-right">SMS</span>
        <span class="w-14 text-right">TAG</span>
      </div>

      {/* Trade list */}
      <div class="flex-1 overflow-y-auto min-h-0">
        <Show when={optionsFlow.trades.length === 0}>
          <EmptyState
            eyebrow="Options Flow"
            title="Waiting for option trades"
            description="ThetaData streams 0DTE option executions here as soon as the next linked prints arrive."
          />
        </Show>

        <For each={optionsFlow.trades.slice(0, 50)}>
          {(trade) => {
            const isCall = trade.right === 'C';
            // Lee-Ready colors: buy=green (bought at ask), sell=red (sold at bid), mid=gray
            const sideColor = trade.side === 'buy' ? 'text-positive'
              : trade.side === 'sell' ? 'text-negative' : 'text-text-muted';
            const cpColor = isCall ? 'text-positive' : 'text-negative';
            const isNotable = trade.tag !== 'normal';

            // Visual weight based on premium
            let rowClass = 'text-[10px]';
            if (trade.premium >= 50_000) rowClass = 'text-[12px] font-medium';
            else if (trade.premium >= 10_000) rowClass = 'text-[11px]';

            const bgClass = isNotable
              ? (trade.side === 'buy' ? 'bg-positive/5' : trade.side === 'sell' ? 'bg-negative/5' : 'bg-surface-2/5')
              : 'hover:bg-surface-2/30';

            return (
              <div class={`flex items-center px-3 py-1 border-b border-border-subtle transition-colors ${rowClass} ${bgClass}`}>
                <span class="w-14 font-data text-text-muted text-[9px]">
                  {formatTime(trade.timestamp)}
                </span>
                <span class={`w-8 font-medium text-[9px] ${sideColor}`}>
                  {trade.side === 'buy' ? 'BUY' : trade.side === 'sell' ? 'SELL' : 'MID'}
                </span>
                <span class={`w-7 font-medium ${cpColor}`}>
                  {trade.right}
                </span>
                <span class="w-11 font-data text-text-primary text-right">
                  {trade.strike}
                </span>
                <span class={`w-10 font-data text-right ${sideColor}`}>
                  {trade.size}
                </span>
                <span class="w-12 font-data text-text-primary text-right">
                  ${trade.price.toFixed(2)}
                </span>
                <span class="w-10 font-data text-text-secondary text-right text-[9px]">
                  {trade.iv != null ? `${(trade.iv * 100).toFixed(0)}%` : '—'}
                </span>
                <span class={`flex-1 font-data text-right ${sideColor} ${trade.premium >= 25_000 ? 'font-medium' : ''}`}>
                  {formatPremium(trade.premium)}
                </span>
                <span class={`w-8 font-data text-right text-[9px] ${
                  trade.sms >= 70 ? 'text-warning font-medium' :
                  trade.sms >= 50 ? 'text-accent' : 'text-text-muted'
                }`}>
                  {trade.sms}
                </span>
                <span class="w-14 text-right flex items-center justify-end gap-1">
                  <Show when={trade.clusterId != null}>
                    {(() => {
                      const cluster = getCluster(trade.clusterId!);
                      return cluster && cluster.tradeCount >= 2 ? (
                        <span class="text-[7px] px-1 py-0.5 rounded bg-accent/15 text-accent border border-accent/25" title={`Cluster: ${cluster.tradeCount} trades, ${cluster.totalSize} contracts`}>
                          {cluster.tradeCount}x
                        </span>
                      ) : null;
                    })()}
                  </Show>
                  <Show when={isNotable}>
                    <span class={`text-[7px] px-1.5 py-0.5 rounded border ${TAG_STYLES[trade.tag]}`}>
                      {TAG_LABELS[trade.tag]}
                    </span>
                  </Show>
                </span>
              </div>
            );
          }}
        </For>
      </div>
    </div>
  );
};
