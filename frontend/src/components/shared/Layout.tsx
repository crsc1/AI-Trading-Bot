import { type Component, type JSX, onMount, onCleanup } from 'solid-js';
import { useLocation } from '@solidjs/router';
import { Sidebar } from './Sidebar';
import { market } from '../../signals/market';
import { agent } from '../../signals/agent';
import { initDataLayer, destroyDataLayer } from '../../lib/data';

// Import all pages so they stay mounted
import { Dashboard } from '../pages/Dashboard';
import { Charts } from '../pages/Charts';
import { Flow } from '../pages/Flow';
import { Agent } from '../pages/Agent';
import { Reference } from '../pages/Reference';
import { Scanner } from '../pages/Scanner';

interface Props {
  children?: JSX.Element;
}

export const Layout: Component<Props> = (props) => {
  onMount(() => initDataLayer());
  onCleanup(() => destroyDataLayer());

  const location = useLocation();
  const path = () => location.pathname;

  const priceColor = () => {
    if (market.lastPrice <= 0) return 'text-text-muted';
    if (market.candles.length > 1) {
      const prev = market.candles[market.candles.length - 2]?.close;
      if (prev) return market.lastPrice >= prev ? 'text-positive' : 'text-negative';
    }
    return 'text-text-primary';
  };

  return (
    <div class="h-screen flex bg-surface-0 text-text-primary font-data text-[11px] overflow-hidden">
      <Sidebar />

      <div class="flex-1 flex flex-col min-w-0">
        {/* Status Bar */}
        <header class="h-10 flex items-center justify-between px-4 bg-surface-1 border-b border-border-default shrink-0">
          <div class="flex items-center gap-4">
            <span class="font-display text-[14px] font-medium">{market.symbol}</span>
            <span class={`text-[16px] font-medium ${priceColor()}`}>
              {market.lastPrice > 0 ? `$${market.lastPrice.toFixed(2)}` : '---'}
            </span>
            {market.quote && (
              <span class="text-text-secondary text-[10px]">
                {market.quote.bid.toFixed(2)} / {market.quote.ask.toFixed(2)}
              </span>
            )}
          </div>
          <div class="flex items-center gap-4">
            <span
              class={`font-display text-[10px] ${
                agent.brain.status === 'analyzing' ? 'text-positive' : 'text-text-secondary'
              }`}
            >
              Brain: {agent.brain.status.toUpperCase()}
            </span>
            <div class="flex items-center gap-1.5">
              <span class={`w-2 h-2 rounded-full ${market.connected ? 'bg-positive' : 'bg-negative'}`} />
              <span class="text-text-muted text-[10px]">
                {market.connected ? 'LIVE' : 'OFFLINE'}
              </span>
            </div>
          </div>
        </header>

        {/* All pages rendered permanently, visibility toggled by CSS */}
        <main class="flex-1 min-h-0 overflow-hidden relative">
          <div class="absolute inset-0" style={{ display: path() === '/' ? 'block' : 'none' }}>
            <Dashboard />
          </div>
          <div class="absolute inset-0" style={{ display: path() === '/charts' ? 'block' : 'none' }}>
            <Charts />
          </div>
          <div class="absolute inset-0" style={{ display: path() === '/flow' ? 'block' : 'none' }}>
            <Flow />
          </div>
          <div class="absolute inset-0" style={{ display: path() === '/agent' ? 'block' : 'none' }}>
            <Agent />
          </div>
          <div class="absolute inset-0" style={{ display: path() === '/reference' ? 'block' : 'none' }}>
            <Reference />
          </div>
          <div class="absolute inset-0" style={{ display: path() === '/scanner' ? 'block' : 'none' }}>
            <Scanner />
          </div>
        </main>
      </div>
    </div>
  );
};
