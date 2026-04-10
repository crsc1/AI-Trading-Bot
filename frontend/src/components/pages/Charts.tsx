import { type Component, For, Show, createEffect, createMemo, createSignal, on, onMount, onCleanup } from 'solid-js';
import { market } from '../../signals/market';
import { chainState } from '../../signals/chain';
import { optionsFlow } from '../../signals/optionsFlow';
import { reference } from '../../signals/reference';
import { loadCandles, switchSymbol } from '../../lib/data';
import { fmtPrice, fmtChange, fmtChangePct } from '../../lib/format';
import { CandleChart } from '../charts/CandleChart';
import { ConnectionDot } from '../system/ConnectionDot';
import { QuickSymbols } from '../system/QuickSymbols';
import { KeyLevelGrid, type KeyLevel } from '../system/KeyLevelGrid';
import { ChainStrip, type ChainRow } from '../system/ChainStrip';
import { FlowTradeRow } from '../system/FlowTradeRow';
import { FlowSummaryBar } from '../system/FlowSummaryBar';
import { subscribeSignalFeed, unsubscribeSignalFeed } from '../../runtime/signalsRuntime';
import { refreshReferenceSymbolData, subscribeReferenceRuntime, unsubscribeReferenceRuntime } from '../../runtime/referenceRuntime';
import type { MarketStructureLevels } from '../../lib/api';

const intervalLabels: Record<string, string> = {
  '1Min': '1m', '2Min': '2m', '5Min': '5m', '10Min': '10m',
  '15Min': '15m', '30Min': '30m', '1H': '1h', '4Hour': '4h',
  '1D': '1d', '1Week': '1w',
};

export const Charts: Component = () => {
  const [switchingSymbol, setSwitchingSymbol] = createSignal<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = createSignal(false);

  onMount(() => {
    subscribeSignalFeed();
    subscribeReferenceRuntime();
  });

  onCleanup(() => {
    unsubscribeSignalFeed();
    unsubscribeReferenceRuntime();
  });

  createEffect(
    on(() => `${market.interval}|${market.range}`, () => loadCandles(), { defer: true })
  );

  createEffect(
    on(() => market.symbol, () => {
      void refreshReferenceSymbolData(true);
    }, { defer: true })
  );

  const firstCandle = createMemo(() => market.candles[0] ?? null);
  const priceChange = createMemo(() => {
    const first = firstCandle();
    if (!first || market.lastPrice <= 0) return null;
    return market.lastPrice - first.open;
  });
  const priceChangePct = createMemo(() => {
    const first = firstCandle();
    const change = priceChange();
    if (!first || !change || first.open === 0) return null;
    return (change / first.open) * 100;
  });

  const keyLevels = createMemo((): KeyLevel[] => {
    const structure: MarketStructureLevels = reference.levels.data?.levels || {};
    return [
      { label: 'VWAP', value: structure.vwap, tone: 'text-accent' },
      { label: 'POC', value: structure.poc, tone: 'text-warning' },
      { label: 'HOD', value: structure.hod, tone: 'text-positive' },
      { label: 'LOD', value: structure.lod, tone: 'text-negative' },
      { label: 'ORB H', value: structure.orb_5_high, tone: 'text-positive' },
      { label: 'ORB L', value: structure.orb_5_low, tone: 'text-negative' },
    ];
  });

  const chainRows = createMemo((): ChainRow[] => {
    const spot = chainState.spotPrice || market.lastPrice;
    const rows = [...chainState.strikes.entries()].sort(([a], [b]) => a - b);
    if (rows.length === 0) return [];
    const atmIdx = Math.max(0, rows.findIndex(([strike]) => strike >= spot));
    const start = Math.max(0, atmIdx - 3);
    return rows.slice(start, start + 7).map(([strike, row]) => ({
      strike,
      call: row.call,
      put: row.put,
    }));
  });

  const flowTrades = createMemo(() => optionsFlow.trades.slice(0, 5));

  const handleQuickSymbol = async (symbol: string) => {
    if (symbol === market.symbol || switchingSymbol()) return;
    setSwitchingSymbol(symbol);
    try {
      await switchSymbol(symbol);
    } finally {
      setSwitchingSymbol(null);
    }
  };

  return (
    <div data-testid="charts-page" class="h-full overflow-hidden bg-[#050608] flex flex-col">
      {/* ── Top bar ── */}
      <div class="shrink-0 flex items-center gap-4 border-b border-border-subtle bg-surface-1/60 px-4 py-2">
        <div class="flex items-center gap-3">
          <span class="font-display text-[15px] font-semibold text-text-primary">{market.symbol}</span>
          <span class="font-data text-[15px] font-semibold text-text-primary">
            {market.lastPrice > 0 ? fmtPrice(market.lastPrice) : '—'}
          </span>
          <Show when={priceChange() != null}>
            <span class={`font-data text-[12px] font-semibold ${priceChange()! >= 0 ? 'text-positive' : 'text-negative'}`}>
              {fmtChange(priceChange())}
              <span class="ml-1 text-[11px] opacity-70">({fmtChangePct(priceChangePct())})</span>
            </span>
          </Show>
          <Show when={market.quote}>
            <span class="font-data text-[11px] text-text-muted ml-1">
              {market.quote!.bid.toFixed(2)}/{market.quote!.ask.toFixed(2)}
            </span>
          </Show>
        </div>

        <QuickSymbols
          active={market.symbol}
          loading={switchingSymbol()}
          onSelect={(s) => void handleQuickSymbol(s)}
        />

        <div class="flex items-center gap-2 ml-auto">
          <span class="font-display text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">
            {intervalLabels[market.interval] || market.interval} · {market.range}
          </span>
          <ConnectionDot tone={market.connected ? 'positive' : 'negative'} />
          <button
            type="button"
            onClick={() => setSidebarOpen(p => !p)}
            class={`rounded-lg px-2.5 py-1 font-display text-[10px] font-semibold uppercase tracking-[0.1em] transition-colors ${
              sidebarOpen() ? 'bg-accent/14 text-accent' : 'text-text-muted hover:text-text-secondary hover:bg-surface-2'
            }`}
          >
            {sidebarOpen() ? 'Hide Panel' : 'Panel'}
          </button>
        </div>
      </div>

      {/* ── Chart + sidebar ── */}
      <div class="flex-1 min-h-0 flex">
        <div class="flex-1 min-w-0 min-h-0">
          <CandleChart />
        </div>

        <Show when={sidebarOpen()}>
          <aside class="w-[300px] shrink-0 min-h-0 overflow-y-auto border-l border-border-subtle bg-surface-1/40">
            {/* Key Levels */}
            <div class="border-b border-border-subtle px-3 py-2.5">
              <div class="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted mb-2">Key Levels</div>
              <KeyLevelGrid levels={keyLevels()} />
            </div>

            {/* ATM Chain */}
            <div class="border-b border-border-subtle">
              <ChainStrip
                rows={chainRows()}
                spotPrice={chainState.spotPrice || market.lastPrice}
                title="ATM Chain"
              />
            </div>

            {/* Live Flow */}
            <div>
              <div class="px-3 py-2.5 flex items-baseline justify-between">
                <div class="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted">Live Flow</div>
                <Show when={optionsFlow.tradeCount > 0}>
                  <span class="font-data text-[10px] text-text-muted">{optionsFlow.tradeCount} trades</span>
                </Show>
              </div>
              <FlowSummaryBar
                bullPremium={optionsFlow.totalBullishPremium}
                bearPremium={optionsFlow.totalBearishPremium}
              />
              <Show when={flowTrades().length > 0} fallback={
                <div class="px-3 py-3 text-[10px] text-text-muted">Waiting for trades...</div>
              }>
                <For each={flowTrades()}>
                  {(trade) => <FlowTradeRow trade={trade} />}
                </For>
              </Show>
            </div>
          </aside>
        </Show>
      </div>
    </div>
  );
};
