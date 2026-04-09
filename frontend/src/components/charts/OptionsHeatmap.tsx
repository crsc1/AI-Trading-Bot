/**
 * Options Strike Heatmap — Shows premium concentration by strike price.
 *
 * Y-axis: strike prices (sorted, ATM in center)
 * Each row: horizontal bar showing call premium (green, left) vs put premium (red, right)
 * Brightness: relative to max premium at any strike
 * Updates from optionsFlow store in real-time.
 *
 * This answers: "Where is the money positioned right now?"
 */
import { type Component, For, Show, createMemo } from 'solid-js';
import { optionsFlow } from '../../signals/optionsFlow';
import { market } from '../../signals/market';

function formatPremium(p: number): string {
  if (p >= 1_000_000) return `$${(p / 1_000_000).toFixed(1)}M`;
  if (p >= 1_000) return `$${(p / 1_000).toFixed(0)}K`;
  if (p > 0) return `$${p.toFixed(0)}`;
  return '';
}

interface StrikeRow {
  strike: number;
  callBuyP: number;   // call premium bought at ask (bullish)
  callSellP: number;  // call premium sold at bid (bearish)
  putBuyP: number;    // put premium bought at ask (bearish)
  putSellP: number;   // put premium sold at bid (bullish)
  callContracts: number;
  putContracts: number;
  bullishP: number;   // call buys + put sells
  bearishP: number;   // put buys + call sells
}

export const OptionsHeatmap: Component = () => {
  const strikeData = createMemo((): StrikeRow[] => {
    const trades = optionsFlow.trades;
    if (trades.length === 0) return [];

    // Aggregate premium by strike, split by direction
    const map = new Map<number, {
      callBuyP: number; callSellP: number; putBuyP: number; putSellP: number;
      callC: number; putC: number;
    }>();

    for (const t of trades) {
      let entry = map.get(t.strike);
      if (!entry) {
        entry = { callBuyP: 0, callSellP: 0, putBuyP: 0, putSellP: 0, callC: 0, putC: 0 };
        map.set(t.strike, entry);
      }
      if (t.right === 'C') {
        if (t.side === 'buy') entry.callBuyP += t.premium;
        else if (t.side === 'sell') entry.callSellP += t.premium;
        else { entry.callBuyP += t.premium / 2; entry.callSellP += t.premium / 2; }
        entry.callC += t.size;
      } else {
        if (t.side === 'buy') entry.putBuyP += t.premium;
        else if (t.side === 'sell') entry.putSellP += t.premium;
        else { entry.putBuyP += t.premium / 2; entry.putSellP += t.premium / 2; }
        entry.putC += t.size;
      }
    }

    return Array.from(map.entries())
      .map(([strike, d]) => ({
        strike,
        callBuyP: d.callBuyP,
        callSellP: d.callSellP,
        putBuyP: d.putBuyP,
        putSellP: d.putSellP,
        callContracts: d.callC,
        putContracts: d.putC,
        bullishP: d.callBuyP + d.putSellP,   // buying calls + selling puts = bullish
        bearishP: d.putBuyP + d.callSellP,    // buying puts + selling calls = bearish
      }))
      .sort((a, b) => b.strike - a.strike);
  });

  const maxPremium = createMemo(() => {
    let max = 1;
    for (const row of strikeData()) {
      max = Math.max(max, row.bullishP, row.bearishP);
    }
    return max;
  });

  const currentPrice = () => market.lastPrice;

  return (
    <div class="flex flex-col h-full">
      {/* Header — h-[72px] matched with OptionsFlow header */}
      <div class="px-4 py-2 h-[72px] border-b border-border-default shrink-0 flex flex-col justify-between">
        <div class="flex items-center justify-between">
          <span class="font-display text-[13px] font-medium text-text-primary">
            Strike Heatmap
          </span>
          <span class="font-data text-[10px] text-text-secondary">
            {strikeData().length} strikes
          </span>
        </div>
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-sm bg-positive/60" />
            <span class="font-display text-[9px] text-text-secondary">Bullish (call buys + put sells)</span>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-sm bg-negative/60" />
            <span class="font-display text-[9px] text-text-secondary">Bearish (put buys + call sells)</span>
          </div>
        </div>
        <div class="flex items-center justify-between">
          <span class="font-display text-[9px] text-text-secondary">← BULLISH $</span>
          <span class="font-display text-[9px] text-accent">{market.symbol}</span>
          <span class="font-display text-[9px] text-text-secondary">BEARISH $ →</span>
        </div>
      </div>

      {/* Column headers */}
      <div class="flex items-center px-3 py-1.5 text-[8px] font-display text-text-secondary tracking-wider border-b border-border-default shrink-0">
        <span class="w-10 text-right">SIZE</span>
        <span class="flex-1 text-center">BULL $</span>
        <span class="w-12 text-center">STRIKE</span>
        <span class="flex-1 text-center">BEAR $</span>
        <span class="w-10">SIZE</span>
      </div>

      {/* Strike rows */}
      <div class="flex-1 overflow-y-auto min-h-0">
        <Show when={strikeData().length === 0}>
          <div class="flex items-center justify-center h-full text-text-muted text-[11px]">
            <div class="text-center">
              <div class="mb-1">Waiting for option trades...</div>
              <div class="text-[9px] opacity-50">Heatmap builds as trades stream in</div>
            </div>
          </div>
        </Show>

        <For each={strikeData()}>
          {(row) => {
            const bullWidth = () => Math.min(100, (row.bullishP / maxPremium()) * 100);
            const bearWidth = () => Math.min(100, (row.bearishP / maxPremium()) * 100);
            const isATM = () => Math.abs(row.strike - currentPrice()) < 0.5;
            const isNearMoney = () => Math.abs(row.strike - currentPrice()) <= 3;
            const totalContracts = row.callContracts + row.putContracts;

            return (
              <div
                class={`flex items-center px-3 py-0.5 border-b border-border-subtle ${
                  isATM() ? 'bg-accent/10 border-accent/20' : ''
                }`}
                style={{ "min-height": "22px" }}
              >
                {/* Left size (call + put contracts at this strike) */}
                <span class={`w-10 text-right font-data text-[9px] ${
                  row.callContracts > 0 ? 'text-positive' : 'text-text-muted'
                }`}>
                  {row.callContracts > 0 ? row.callContracts : ''}
                </span>

                {/* Bullish premium bar (right-aligned, grows left) */}
                <div class="flex-1 flex justify-end px-1">
                  <div class="relative w-full h-3 flex justify-end items-center">
                    <div
                      class="h-full rounded-sm transition-all duration-300"
                      style={{
                        width: `${bullWidth()}%`,
                        background: `rgba(0, 200, 5, ${0.15 + (bullWidth() / 100) * 0.45})`,
                      }}
                    />
                    <Show when={row.bullishP >= 1000}>
                      <span class="absolute right-1 font-data text-[8px] text-positive/80">
                        {formatPremium(row.bullishP)}
                      </span>
                    </Show>
                  </div>
                </div>

                {/* Strike price */}
                <span class={`w-12 text-center font-data text-[10px] ${
                  isATM() ? 'text-accent font-medium' :
                  isNearMoney() ? 'text-text-primary' : 'text-text-secondary'
                }`}>
                  {row.strike}
                </span>

                {/* Bearish premium bar (left-aligned, grows right) */}
                <div class="flex-1 flex justify-start px-1">
                  <div class="relative w-full h-3 flex justify-start items-center">
                    <div
                      class="h-full rounded-sm transition-all duration-300"
                      style={{
                        width: `${bearWidth()}%`,
                        background: `rgba(255, 80, 0, ${0.15 + (bearWidth() / 100) * 0.45})`,
                      }}
                    />
                    <Show when={row.bearishP >= 1000}>
                      <span class="absolute left-1 font-data text-[8px] text-negative/80">
                        {formatPremium(row.bearishP)}
                      </span>
                    </Show>
                  </div>
                </div>

                {/* Right size (put contracts) */}
                <span class={`w-10 font-data text-[9px] ${
                  row.putContracts > 0 ? 'text-negative' : 'text-text-muted'
                }`}>
                  {row.putContracts > 0 ? row.putContracts : ''}
                </span>
              </div>
            );
          }}
        </For>
      </div>
    </div>
  );
};
