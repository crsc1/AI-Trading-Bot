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
  callPremium: number;
  putPremium: number;
  callContracts: number;
  putContracts: number;
  netPremium: number; // positive = call heavy, negative = put heavy
}

export const OptionsHeatmap: Component = () => {
  const strikeData = createMemo((): StrikeRow[] => {
    const trades = optionsFlow.trades;
    if (trades.length === 0) return [];

    // Aggregate premium by strike
    const map = new Map<number, { callP: number; putP: number; callC: number; putC: number }>();

    for (const t of trades) {
      let entry = map.get(t.strike);
      if (!entry) {
        entry = { callP: 0, putP: 0, callC: 0, putC: 0 };
        map.set(t.strike, entry);
      }
      if (t.right === 'C') {
        entry.callP += t.premium;
        entry.callC += t.size;
      } else {
        entry.putP += t.premium;
        entry.putC += t.size;
      }
    }

    return Array.from(map.entries())
      .map(([strike, d]) => ({
        strike,
        callPremium: d.callP,
        putPremium: d.putP,
        callContracts: d.callC,
        putContracts: d.putC,
        netPremium: d.callP - d.putP,
      }))
      .sort((a, b) => b.strike - a.strike); // Highest strike on top
  });

  const maxPremium = createMemo(() => {
    let max = 1;
    for (const row of strikeData()) {
      max = Math.max(max, row.callPremium, row.putPremium);
    }
    return max;
  });

  const currentPrice = () => market.lastPrice;

  return (
    <div class="flex flex-col h-full bg-surface-0">
      {/* Header */}
      <div class="px-4 py-3 bg-surface-1 border-b border-border-default shrink-0">
        <div class="flex items-center justify-between">
          <span class="font-display text-[13px] font-medium text-text-primary">
            Strike Heatmap
          </span>
          <span class="font-data text-[10px] text-text-muted">
            {strikeData().length} strikes
          </span>
        </div>
        <div class="flex items-center gap-4 mt-1.5">
          <div class="flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-sm bg-positive/60" />
            <span class="font-display text-[9px] text-text-muted">Call $</span>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-sm bg-negative/60" />
            <span class="font-display text-[9px] text-text-muted">Put $</span>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="w-3 h-0.5 bg-accent" />
            <span class="font-display text-[9px] text-text-muted">SPY</span>
          </div>
        </div>
      </div>

      {/* Column headers */}
      <div class="flex items-center px-3 py-1 text-[8px] font-display text-text-muted tracking-wider border-b border-border-default bg-surface-1/50 shrink-0">
        <span class="w-10 text-right">CALLS</span>
        <span class="flex-1 text-center">PREMIUM</span>
        <span class="w-12 text-center">STRIKE</span>
        <span class="flex-1 text-center">PREMIUM</span>
        <span class="w-10">PUTS</span>
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
            const callWidth = () => Math.min(100, (row.callPremium / maxPremium()) * 100);
            const putWidth = () => Math.min(100, (row.putPremium / maxPremium()) * 100);
            const isATM = () => Math.abs(row.strike - currentPrice()) < 0.5;
            const isNearMoney = () => Math.abs(row.strike - currentPrice()) <= 3;

            return (
              <div
                class={`flex items-center px-3 py-0.5 border-b border-border-subtle ${
                  isATM() ? 'bg-accent/10 border-accent/20' : ''
                }`}
                style={{ "min-height": "22px" }}
              >
                {/* Call contracts */}
                <span class={`w-10 text-right font-data text-[9px] ${
                  row.callContracts > 0 ? 'text-positive' : 'text-text-muted'
                }`}>
                  {row.callContracts > 0 ? row.callContracts : ''}
                </span>

                {/* Call premium bar (right-aligned, grows left) */}
                <div class="flex-1 flex justify-end px-1">
                  <div class="relative w-full h-3 flex justify-end items-center">
                    <div
                      class="h-full rounded-sm transition-all duration-300"
                      style={{
                        width: `${callWidth()}%`,
                        background: `rgba(0, 200, 5, ${0.15 + (callWidth() / 100) * 0.45})`,
                      }}
                    />
                    <Show when={row.callPremium >= 1000}>
                      <span class="absolute right-1 font-data text-[8px] text-positive/80">
                        {formatPremium(row.callPremium)}
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

                {/* Put premium bar (left-aligned, grows right) */}
                <div class="flex-1 flex justify-start px-1">
                  <div class="relative w-full h-3 flex justify-start items-center">
                    <div
                      class="h-full rounded-sm transition-all duration-300"
                      style={{
                        width: `${putWidth()}%`,
                        background: `rgba(255, 80, 0, ${0.15 + (putWidth() / 100) * 0.45})`,
                      }}
                    />
                    <Show when={row.putPremium >= 1000}>
                      <span class="absolute left-1 font-data text-[8px] text-negative/80">
                        {formatPremium(row.putPremium)}
                      </span>
                    </Show>
                  </div>
                </div>

                {/* Put contracts */}
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
