/**
 * Options Bubble Chart — Reuses the same Canvas 2D + PixiJS flow engine
 * as the equity OrderFlowChart, but fed with option trades.
 *
 * Y-axis: strike price (instead of equity price)
 * X-axis: time
 * Bubble color: green = buy (Lee-Ready: at ask), red = sell (at bid), gray = mid
 * Bubble size: premium-weighted (contracts × price × 100)
 *
 * Same architecture as OrderFlowChart: accumulate raw ticks, aggregate
 * at 250ms intervals, render via flowCanvas + flowRenderer.
 */
import { type Component, onMount, onCleanup } from 'solid-js';
import { FlowBubbleRenderer } from '../../lib/flowRenderer';
import {
  computeLayout,
  drawFlowCanvas,
  computeBubblePoints,
  drawTrail,
  tToX,
  pToY,
  type FlowCloudCell,
  type FlowLayout,
} from '../../lib/flowCanvas';
import { optionsFlow } from '../../signals/optionsFlow';
import { market } from '../../signals/market';
import { cvd } from '../../signals/flow';

const PRICE_TICK = 0.05;  // $0.05 resolution — matches SPY equity tick size

interface OptionTick {
  price: number;      // SPY underlying price when the trade happened (Y-axis)
  size: number;       // contracts (used as volume)
  side: 'buy' | 'sell';  // call = buy, put = sell (for green/red mapping)
  ts: number;         // arrival timestamp ms
}

// Notable trades get separate rendering (rings, glows) — not aggregated
interface NotableTrade {
  price: number;      // SPY price (Y-axis)
  ts: number;         // arrival timestamp
  tag: 'sweep' | 'block' | 'whale';
  side: 'buy' | 'sell';
  size: number;       // raw contracts for ring sizing
  sms: number;        // Smart Money Score
}

export const OptionsBubbleChart: Component = () => {
  let containerRef: HTMLDivElement | undefined;
  let canvas: HTMLCanvasElement | undefined;
  let ctx: CanvasRenderingContext2D | null = null;
  let bubbleRenderer: FlowBubbleRenderer | null = null;
  let animTimer: ReturnType<typeof setTimeout> | null = null;
  let resizeObs: ResizeObserver | null = null;

  // Tick buffer — same pattern as equity OrderFlowChart
  let ticks: OptionTick[] = [];
  let notables: NotableTrade[] = [];
  let lastTradeCount = 0;
  const MAX_TICKS = 10000;
  const MAX_NOTABLES = 500;

  // Config — same as equity flow defaults
  let aggSeconds = 0.5;
  let visibleWindowMs = 5 * 60 * 1000;  // 5 min visible window, scrolls with new trades
  let renderInterval = 100;

  function ensureCanvas(): boolean {
    if (!containerRef) return false;
    const rect = containerRef.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) return false;
    if (!canvas) {
      canvas = document.createElement('canvas');
      canvas.style.cssText = 'width:100%;height:100%;display:block;position:absolute;top:0;left:0;z-index:1;';
      containerRef.appendChild(canvas);
      ctx = canvas.getContext('2d');
    }
    const dpr = window.devicePixelRatio || 1;
    const w = Math.round(rect.width * dpr);
    const h = Math.round(rect.height * dpr);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    return true;
  }

  // Sync new trades from the store into our tick buffer
  function syncTrades() {
    const storeCount = optionsFlow.tradeCount;
    if (storeCount <= lastTradeCount) return;

    const newCount = storeCount - lastTradeCount;
    const newTrades = optionsFlow.trades.slice(0, newCount);

    for (const t of newTrades) {
      // Use stored SPY price (set at ingestion time) for correct Y-axis on replay
      const spyPrice = t.spyPrice || market.lastPrice;
      if (spyPrice <= 0) continue;

      // Use the trade's actual timestamp so bubbles replay at correct X position
      const tradeTs = t.timestamp || Date.now();

      // Weight size by Smart Money Score, cap to prevent giant bubbles
      const smsWeight = 0.5 + (t.sms / 100) * 1.0;  // 0.5 at SMS=0, 1.5 at SMS=100
      const weightedSize = Math.min(200, t.size * smsWeight);  // Cap at 200 contracts visual
      const side = t.side === 'sell' ? 'sell' as const : 'buy' as const;
      ticks.push({
        price: spyPrice,
        size: weightedSize,
        side,
        ts: tradeTs,
      });

      // Track notable trades for ring/glow overlays
      if (t.tag !== 'normal') {
        notables.push({
          price: spyPrice,
          ts: tradeTs,
          tag: t.tag,
          side,
          size: t.size,
          sms: t.sms,
        });
      }
    }

    lastTradeCount = storeCount;

    if (ticks.length > MAX_TICKS) {
      ticks = ticks.slice(-Math.floor(MAX_TICKS * 0.8));
    }
    if (notables.length > MAX_NOTABLES) {
      notables = notables.slice(-Math.floor(MAX_NOTABLES * 0.8));
    }
  }

  // Aggregate ticks into FlowCloudCells — same logic as equity flow
  function ticksToCells(): FlowCloudCell[] {
    if (ticks.length === 0) return [];

    const now = Date.now();
    const cutoff = now - visibleWindowMs;
    const aggMs = aggSeconds * 1000;

    const grid = new Map<string, { price: number; time: number; buy: number; sell: number }>();

    for (let i = ticks.length - 1; i >= 0; i--) {
      const t = ticks[i];
      if (t.ts < cutoff) break;

      const timeBucket = Math.floor(t.ts / aggMs) * aggMs;
      const priceBucket = Math.round(t.price / PRICE_TICK) * PRICE_TICK;
      const key = `${timeBucket}:${priceBucket.toFixed(2)}`;

      let cell = grid.get(key);
      if (!cell) {
        cell = { price: priceBucket, time: timeBucket, buy: 0, sell: 0 };
        grid.set(key, cell);
      }

      if (t.side === 'buy') cell.buy += t.size;
      else cell.sell += t.size;
    }

    return Array.from(grid.values()).map(c => ({
      price: c.price,
      time: new Date(c.time).toISOString(),
      buy_vol: c.buy,
      sell_vol: c.sell,
      delta: c.buy - c.sell,
      total_vol: c.buy + c.sell,
    }));
  }

  /**
   * Draw CVD velocity gradient behind the plot area.
   * Green gradient = buying pressure accelerating (bullish flow).
   * Red gradient = selling pressure accelerating (bearish flow).
   * Intensity scales with velocity magnitude. Fades when CVD is stale (>5s).
   */
  function drawCvdGradient(
    ctx: CanvasRenderingContext2D,
    layout: FlowLayout,
    dpr: number,
  ): void {
    const vel = cvd.velocity;
    const accel = cvd.acceleration;
    const staleness = Date.now() - cvd.lastUpdate;

    // Fade out if no CVD updates in 5 seconds
    if (staleness > 5000 || (vel === 0 && accel === 0)) return;

    const staleFade = staleness < 2000 ? 1.0 : Math.max(0, 1 - (staleness - 2000) / 3000);

    // Intensity from velocity magnitude (clamped 0-1)
    const intensity = Math.min(1, Math.abs(vel) * 1.5);
    // Acceleration boosts or dampens the gradient
    const accelBoost = 1 + Math.min(0.5, Math.abs(accel) * 2) * Math.sign(accel) * Math.sign(vel);
    const alpha = Math.min(0.12, intensity * 0.12 * Math.max(0.3, accelBoost)) * staleFade;

    if (alpha < 0.005) return;

    const isBuying = vel > 0;
    const color = isBuying ? '0, 200, 5' : '255, 80, 0';

    // Gradient from right edge (strongest = most recent) fading left
    const grad = ctx.createLinearGradient(
      layout.marginL, 0,
      layout.marginL + layout.plotW, 0,
    );
    grad.addColorStop(0, `rgba(${color}, 0)`);
    grad.addColorStop(0.6, `rgba(${color}, ${alpha * 0.3})`);
    grad.addColorStop(1, `rgba(${color}, ${alpha})`);

    ctx.save();
    ctx.fillStyle = grad;
    ctx.fillRect(layout.marginL, layout.marginT, layout.plotW, layout.plotH);
    ctx.restore();
  }

  /**
   * Draw sweep rings, block borders, and whale glows for notable trades.
   * Rendered on Canvas 2D layer (below PixiJS bubbles) so rings frame the bubbles.
   */
  function drawNotableOverlays(
    ctx: CanvasRenderingContext2D,
    layout: FlowLayout,
    dpr: number,
  ): void {
    const now = Date.now();
    const cutoff = now - visibleWindowMs;

    for (const n of notables) {
      if (n.ts < cutoff) continue;

      const x = tToX(n.ts, layout);
      const y = pToY(n.price, layout);

      // Skip if outside plot area
      if (x < layout.marginL || x > layout.W - layout.ladderW) continue;
      if (y < layout.marginT || y > layout.marginT + layout.plotH) continue;

      // Freshness opacity: 1.0 at birth, fades to 0.15 at window edge
      const age = now - n.ts;
      const freshness = Math.max(0.15, 1 - (age / visibleWindowMs) * 0.85);

      // Base radius from contract size — capped to prevent chart-eating whales
      // sqrt scaling with hard cap at 30px (before dpr)
      const baseR = Math.min(30, Math.max(6, Math.sqrt(n.size) * 2)) * dpr;
      const color = n.side === 'buy' ? '#00C805' : '#FF5000';

      if (n.tag === 'sweep') {
        // SWEEP: dashed ring — institutions sweeping the book across exchanges
        ctx.save();
        ctx.globalAlpha = freshness * 0.6;
        ctx.strokeStyle = '#a855f7';
        ctx.lineWidth = 1.5 * dpr;
        ctx.setLineDash([3 * dpr, 2 * dpr]);
        ctx.beginPath();
        ctx.arc(x, y, baseR * 1.2, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();
      } else if (n.tag === 'block') {
        // BLOCK: solid ring — 100+ contract single print
        ctx.save();
        ctx.globalAlpha = freshness * 0.5;
        ctx.strokeStyle = color;
        ctx.lineWidth = 2 * dpr;
        ctx.beginPath();
        ctx.arc(x, y, baseR * 1.15, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      } else if (n.tag === 'whale') {
        // WHALE: subtle glow + ring — $100K+ premium. Visible but not chart-eating.
        ctx.save();
        ctx.globalAlpha = freshness * 0.15;
        const glow = ctx.createRadialGradient(x, y, baseR * 0.3, x, y, baseR * 1.6);
        glow.addColorStop(0, '#ffb300');
        glow.addColorStop(1, 'transparent');
        ctx.fillStyle = glow;
        ctx.fillRect(x - baseR * 1.6, y - baseR * 1.6, baseR * 3.2, baseR * 3.2);

        ctx.globalAlpha = freshness * 0.7;
        ctx.strokeStyle = '#ffb300';
        ctx.lineWidth = 2 * dpr;
        ctx.beginPath();
        ctx.arc(x, y, baseR * 1.3, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }
    }
  }

  function render(): void {
    syncTrades();

    if (!ensureCanvas() || !ctx || !canvas) return;

    const dpr = window.devicePixelRatio || 1;
    const W = canvas.width;
    const H = canvas.height;

    const cells = ticksToCells();
    if (!cells.length) {
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = '#0a0a12';
      ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = '#b0b0c8';
      ctx.font = `${12 * dpr}px "Geist Mono", "SF Mono", Menlo, monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('Waiting for option trades...', W / 2, H / 2);
      return;
    }

    const layout = computeLayout(W, H, dpr, cells, visibleWindowMs, aggSeconds, PRICE_TICK, true);
    if (!layout) return;

    drawFlowCanvas(ctx, layout, cells, aggSeconds, PRICE_TICK);

    // CVD velocity gradient (drawn after grid, before bubbles)
    drawCvdGradient(ctx, layout, dpr);

    const points = computeBubblePoints(layout, cells, aggSeconds, false);

    const minR = Math.max(4 * dpr, (layout.plotW / Math.max(visibleWindowMs / (aggSeconds * 1000), 1)) * 0.55);
    drawTrail(ctx, points, dpr, minR);

    // Draw notable trade overlays (sweep rings, whale glows) on Canvas 2D
    drawNotableOverlays(ctx, layout, dpr);

    if (bubbleRenderer?.isReady) {
      const rect = containerRef!.getBoundingClientRect();
      bubbleRenderer.resize(rect.width, rect.height);
      const pulseThreshold = Math.max(aggSeconds * 2000, 3000);
      bubbleRenderer.renderBubbles(points, dpr, pulseThreshold);
    }
  }

  let running = false;

  function startLoop() {
    if (running) return;
    running = true;
    function tick() {
      if (!running) return;
      if (ticks.length > 0 || optionsFlow.tradeCount > lastTradeCount) {
        render();
      }
      animTimer = setTimeout(tick, renderInterval);
    }
    animTimer = setTimeout(tick, renderInterval);
  }

  function stopLoop() {
    running = false;
    if (animTimer) { clearTimeout(animTimer); animTimer = null; }
  }

  onMount(async () => {
    if (!containerRef) return;
    containerRef.style.position = 'relative';

    bubbleRenderer = new FlowBubbleRenderer();
    await bubbleRenderer.init(containerRef);

    resizeObs = new ResizeObserver(() => { /* render loop handles it */ });
    resizeObs.observe(containerRef);

    startLoop();
  });

  onCleanup(() => {
    stopLoop();
    if (resizeObs) resizeObs.disconnect();
    if (bubbleRenderer) bubbleRenderer.destroy();
    bubbleRenderer = null;
    canvas = undefined;
    ctx = null;
    ticks = [];
    notables = [];
  });

  return (
    <div
      ref={containerRef}
      class="w-full h-full relative"
      style={{ 'min-height': '150px' }}
    />
  );
};
