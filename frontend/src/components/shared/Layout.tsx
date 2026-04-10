import { type ParentComponent, onMount, onCleanup } from 'solid-js';
import { Sidebar } from './Sidebar';
import { TickerSelector } from './TickerSelector';
import { market } from '../../signals/market';
import { agent } from '../../signals/agent';
import { initDataLayer, destroyDataLayer } from '../../lib/data';
import { StatusPill } from '../system/StatusPill';

export const Layout: ParentComponent = (props) => {
  onMount(() => initDataLayer());
  onCleanup(() => destroyDataLayer());

  const transportLabel = () => {
    switch (market.transport) {
      case 'webtransport':
        return 'QUIC';
      case 'websocket':
        return 'WS';
      default:
        return '--';
    }
  };

  const formatSource = (source: string | null | undefined) => {
    if (!source) return null;
    return source.replace(/_/g, ' ');
  };

  const feedLabel = () => {
    const parts: string[] = [];
    const engineSource = formatSource(market.dataSource);
    const quoteSource = formatSource(market.quoteSource);

    if (engineSource) parts.push(engineSource);
    if (quoteSource && quoteSource !== engineSource) parts.push(`Quote ${quoteSource}`);

    return parts.join(' · ');
  };

  const brainTone = () => {
    switch (agent.brain.status) {
      case 'analyzing':
        return 'positive';
      case 'trading':
        return 'warning';
      case 'error':
        return 'negative';
      default:
        return 'neutral';
    }
  };

  const feedTone = () => {
    if (!market.connected) return 'negative';
    if (market.dataSource?.toLowerCase().includes('replay')) return 'warning';
    return 'positive';
  };

  return (
    <div data-testid="app-shell" class="h-screen flex bg-[#030405] text-text-primary font-data text-[12px] overflow-hidden">
      <Sidebar />

      <div class="flex-1 flex flex-col min-w-0">
        <header data-testid="status-bar" class="min-h-[60px] px-4 py-3 bg-[#050608] border-b-[1.5px] border-border-default shrink-0">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-3 min-w-0">
              <div class="min-w-0 hidden md:block">
                <div class="font-display text-[10px] font-semibold uppercase tracking-[0.16em] text-text-muted">
                  Realtime Options Workspace
                </div>
                <div class="mt-1 font-data text-[11px] text-text-secondary">
                  Linked chart, chain, flow, and research context
                </div>
              </div>
              <TickerSelector />
            </div>

            <div class="flex flex-wrap items-center gap-2">
              <StatusPill
                label="Brain"
                value={agent.brain.cycle_number > 0 ? `${agent.brain.status.toUpperCase()} · C${agent.brain.cycle_number}` : agent.brain.status.toUpperCase()}
                tone={brainTone()}
              />
              <StatusPill
                label="Connection"
                value={market.connected ? transportLabel() : 'OFFLINE'}
                tone={market.connected ? 'accent' : 'negative'}
              />
              <StatusPill
                label="Market Data"
                value={market.connected ? (feedLabel() || 'Connected') : 'Offline'}
                tone={feedTone()}
              />
            </div>
          </div>
        </header>

        <main class="flex-1 min-h-0 overflow-hidden">
          {props.children}
        </main>
      </div>
    </div>
  );
};
