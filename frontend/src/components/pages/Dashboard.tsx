import { type Component, onMount, onCleanup, createEffect, on } from 'solid-js';
import { market } from '../../signals/market';
import { agent } from '../../signals/agent';
import { initDataLayer, destroyDataLayer, loadCandles } from '../../lib/data';
import { CandleChart } from '../charts/CandleChart';
import { OrderFlowChart } from '../charts/OrderFlowChart';
import { AgentStatus } from '../agent/AgentStatus';
import { ChatPanel } from '../agent/ChatPanel';
import { SignalPanel } from '../panels/SignalPanel';
import { PositionPanel } from '../panels/PositionPanel';
import { ResearchFeed } from '../agent/ResearchFeed';

export const Dashboard: Component = () => {
  onMount(() => {
    initDataLayer();
  });

  onCleanup(() => {
    destroyDataLayer();
  });

  // Reload candles when timeframe changes
  createEffect(
    on(
      () => market.timeframe,
      () => {
        loadCandles();
      },
      { defer: true }
    )
  );

  const priceColor = () =>
    market.lastPrice > 0
      ? market.candles.length > 1 && market.candles[market.candles.length - 2]?.close
        ? market.lastPrice >= market.candles[market.candles.length - 2].close
          ? 'text-positive'
          : 'text-negative'
        : 'text-text-primary'
      : 'text-text-muted';

  return (
    <div class="h-screen flex flex-col bg-surface-0 text-text-primary font-mono text-[11px]">
      {/* Top Bar */}
      <header class="h-9 flex items-center justify-between px-3 bg-surface-1 border-b border-border-default shrink-0">
        <div class="flex items-center gap-3">
          <span class="text-[13px] font-semibold">{market.symbol}</span>
          <span class={`text-[15px] font-bold ${priceColor()}`}>
            {market.lastPrice > 0 ? `$${market.lastPrice.toFixed(2)}` : '---'}
          </span>
          {market.quote && (
            <span class="text-text-secondary text-[9px]">
              {market.quote.bid.toFixed(2)} / {market.quote.ask.toFixed(2)}
            </span>
          )}
        </div>
        <div class="flex items-center gap-3">
          <span
            class={`text-[9px] ${agent.brain.status === 'analyzing' ? 'text-positive' : 'text-text-secondary'}`}
          >
            Brain: {agent.brain.status.toUpperCase()}
          </span>
          <span class={`w-2 h-2 rounded-full ${market.connected ? 'bg-positive' : 'bg-negative'}`} />
          <a href="/reference" class="text-accent hover:text-accent-hover text-[9px]">
            Reference
          </a>
        </div>
      </header>

      {/* Main Content */}
      <div class="flex-1 flex min-h-0">
        {/* Charts Area */}
        <div class="flex-1 flex flex-col min-w-0">
          {/* Candle Chart — 45% of available space */}
          <div class="flex-[45] min-h-[180px] border-b border-border-default">
            <CandleChart />
          </div>

          {/* Order Flow Chart — 35% of available space */}
          <div class="flex-[35] min-h-[140px] border-b border-border-default">
            <OrderFlowChart />
          </div>

          {/* Bottom Panels — compact, grows only if space allows */}
          <div class="flex-[20] min-h-[100px] max-h-[160px] flex shrink-0">
            <div class="flex-1 border-r border-border-default overflow-hidden">
              <SignalPanel />
            </div>
            <div class="flex-1 overflow-hidden">
              <PositionPanel />
            </div>
          </div>
        </div>

        {/* Right Sidebar — Chat + Agent + Research */}
        <div class="w-[260px] border-l border-border-default flex flex-col bg-surface-1 shrink-0">
          <AgentStatus />
          <div class="flex-[3] min-h-0">
            <ChatPanel />
          </div>
          <div class="flex-1 min-h-0 border-t border-border-default">
            <ResearchFeed />
          </div>
        </div>
      </div>
    </div>
  );
};
