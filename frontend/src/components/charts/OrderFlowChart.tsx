/**
 * Order Flow Chart — Canvas 2D + PixiJS GPU rendering.
 *
 * Architecture (matches original dashboard/static/js/flow.js):
 * - Accumulates raw ticks from Rust engine WS into a tick buffer
 * - Aggregates ticks into FlowCloudCells on render (at aggSeconds intervals)
 * - Canvas 2D draws grids, labels, price ladder, volume bars
 * - PixiJS renders GPU-accelerated volume bubbles
 * - Continuous render loop redraws at configured interval
 */
import { type Component, createEffect, on, onCleanup, onMount } from 'solid-js';
import * as Comlink from 'comlink';
import { FlowBubbleRenderer } from '../../lib/flowRenderer';
import {
  computeLayout,
  drawFlowCanvas,
  computeBubblePoints,
  drawTrail,
  type FlowCloudCell,
} from '../../lib/flowCanvas';
import { WSClient } from '../../lib/ws';
import { getProtoWorker } from '../../workers/protobuf.api';
import { api, type RecentOrderFlowTrade } from '../../lib/api';
import { market } from '../../signals/market';

const PRICE_TICK = 0.05;
const MAX_TICKS = 50000;
const MAX_SEEN_KEYS = 12000;

interface RawTick {
  price: number;
  size: number;
  side: 'buy' | 'sell' | 'neutral';
  ts: number; // ms timestamp
}

export const OrderFlowChart: Component = () => {
  let containerRef: HTMLDivElement | undefined;
  let canvas: HTMLCanvasElement | undefined;
  let ctx: CanvasRenderingContext2D | null = null;
  let bubbleRenderer: FlowBubbleRenderer | null = null;
  let animTimer: ReturnType<typeof setTimeout> | null = null;
  let resizeObserver: ResizeObserver | null = null;
  let flowWS: WSClient | null = null;
  let recentPollTimer: ReturnType<typeof setInterval> | null = null;
  let protoBatchPending = false;
  let msgBuffer: ArrayBuffer[] = [];
  let recentTradesRequestId = 0;

  // Live tick buffer (matches original liveFlow.ticks)
  let ticks: RawTick[] = [];
  let seenTickKeys = new Set<string>();
  let seenTickQueue: string[] = [];
  let prevPrice = 0;
  let prevSide: 'buy' | 'sell' | 'neutral' = 'neutral';

  // Adaptive noise filter: recalculated from recent tick distribution
  let minSize = 1; // start permissive so the chart doesn't look dead before adaptation kicks in
  let recentSizes: number[] = []; // last N raw tick sizes (before filtering)
  const ADAPT_SAMPLE = 500; // recalc threshold after this many raw ticks
  let adaptCounter = 0;

  function recalcThreshold() {
    if (recentSizes.length < 50) return;
    // Volume-weighted 25th percentile: drops bottom 25% of volume (noise), keeps 75%
    const sorted = [...recentSizes].sort((a, b) => a - b);
    const totalVol = sorted.reduce((s, v) => s + v, 0);
    let cumVol = 0;
    let threshold = sorted[0];
    for (const s of sorted) {
      cumVol += s;
      if (cumVol >= totalVol * 0.25) { threshold = s; break; }
    }
    // Clamp: never below 5 (absolute noise), never above 500 (would filter real flow)
    minSize = Math.max(5, Math.min(500, threshold));
    recentSizes = []; // reset for next window
    adaptCounter = 0;
  }

  // Config (matches original defaults)
  let aggSeconds = 0.25;       // 250ms aggregation for smooth trail
  let visibleWindowMs = 2 * 60 * 1000;  // 2-minute sliding window
  let renderInterval = 80;     // ms between renders (~12fps)

  function resetTickState(): void {
    ticks = [];
    seenTickKeys = new Set();
    seenTickQueue = [];
    prevPrice = 0;
    prevSide = 'neutral';
    minSize = 1;
    recentSizes = [];
    adaptCounter = 0;
  }

  function tickKey(price: number, size: number, side: string, ts: number): string {
    return `${ts}|${price.toFixed(2)}|${size}|${side}`;
  }

  function rememberTick(key: string): boolean {
    if (seenTickKeys.has(key)) return false;
    seenTickKeys.add(key);
    seenTickQueue.push(key);
    if (seenTickQueue.length > MAX_SEEN_KEYS) {
      const stale = seenTickQueue.splice(0, seenTickQueue.length - MAX_SEEN_KEYS);
      for (const item of stale) seenTickKeys.delete(item);
    }
    return true;
  }

  function ingestTick(price: number, size: number, side: 'buy' | 'sell' | 'neutral', ts: number): void {
    if (!isFinite(price) || price <= 0 || !isFinite(size) || size < 0 || !isFinite(ts) || ts <= 0) return;
    const key = tickKey(price, size, side, ts);
    if (!rememberTick(key)) return;

    recentSizes.push(size);
    adaptCounter++;
    if (adaptCounter >= ADAPT_SAMPLE) recalcThreshold();
    if (size < minSize) return;

    ticks.push({
      price: Math.round(price * 100) / 100,
      size,
      side,
      ts,
    });

    if (ticks.length > MAX_TICKS) {
      ticks = ticks.slice(-Math.floor(MAX_TICKS * 0.8));
    }
  }

  async function syncRecentTrades(): Promise<void> {
    const symbol = market.symbol;
    const requestId = ++recentTradesRequestId;
    try {
      const data = await api.getRecentOrderFlowTrades(symbol, 1500, 5);
      if (requestId !== recentTradesRequestId || symbol !== market.symbol) return;
      const trades = Array.isArray(data.trades) ? [...data.trades] : [];
      trades.sort((a, b) => Date.parse(a.t) - Date.parse(b.t));
      for (const trade of trades) {
        ingestRecentTrade(trade);
      }
      if (ticks.length > 0) render();
    } catch (error) {
      console.warn('[OrderFlowChart] Recent trades fallback failed:', error);
    }
  }

  function ingestRecentTrade(trade: RecentOrderFlowTrade): void {
    const ts = Date.parse(trade.t);
    const side = trade.side === 'buy' || trade.side === 'sell' ? trade.side : 'neutral';
    ingestTick(trade.p, trade.s, side, ts);
  }

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

  // ── Aggregate ticks into FlowCloudCells (matches original) ───────────

  function ticksToCells(): FlowCloudCell[] {
    if (ticks.length === 0) return [];

    const now = Date.now();
    const cutoff = now - visibleWindowMs;
    const aggMs = aggSeconds * 1000;

    // Build grid: (timeBucket, priceBucket) → {buy_vol, sell_vol}
    const grid = new Map<string, { price: number; time: number; buy: number; sell: number }>();

    for (let i = ticks.length - 1; i >= 0; i--) {
      const t = ticks[i];
      if (t.ts < cutoff) break; // ticks are roughly time-ordered

      const timeBucket = Math.floor(t.ts / aggMs) * aggMs;
      const priceBucket = Math.round(t.price / PRICE_TICK) * PRICE_TICK;
      const key = `${timeBucket}:${priceBucket.toFixed(2)}`;

      let cell = grid.get(key);
      if (!cell) {
        cell = { price: priceBucket, time: timeBucket, buy: 0, sell: 0 };
        grid.set(key, cell);
      }

      if (t.side === 'buy') cell.buy += t.size;
      else if (t.side === 'sell') cell.sell += t.size;
      else {
        // Split evenly for neutral
        cell.buy += Math.floor(t.size / 2);
        cell.sell += Math.ceil(t.size / 2);
      }
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

  // ── Render ───────────────────────────────────────────────────────────

  function render(): void {
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
      ctx.fillText('Waiting for order flow data...', W / 2, H / 2);
      return;
    }

    const layout = computeLayout(W, H, dpr, cells, visibleWindowMs, aggSeconds, PRICE_TICK, true);
    if (!layout) return;

    drawFlowCanvas(ctx, layout, cells, aggSeconds, PRICE_TICK);

    const points = computeBubblePoints(layout, cells, aggSeconds, false);

    const minR = Math.max(4 * dpr, (layout.plotW / Math.max(visibleWindowMs / (aggSeconds * 1000), 1)) * 0.55);
    drawTrail(ctx, points, dpr, minR);

    if (bubbleRenderer?.isReady) {
      bubbleRenderer.resize(
        containerRef!.getBoundingClientRect().width,
        containerRef!.getBoundingClientRect().height
      );
      const pulseThreshold = Math.max(aggSeconds * 2000, 3000);
      bubbleRenderer.renderBubbles(points, dpr, pulseThreshold);
    }
  }

  // ── Continuous animation loop (matches original setTimeout approach) ──

  let animRunning = false;

  function startAnimLoop() {
    if (animRunning) return;
    animRunning = true;

    function tick() {
      if (!animRunning) { animTimer = null; return; }
      if (ticks.length > 0) {
        render();
      }
      animTimer = setTimeout(tick, renderInterval);
    }
    animTimer = setTimeout(tick, renderInterval);
  }

  function stopAnimLoop() {
    animRunning = false;
    if (animTimer) { clearTimeout(animTimer); animTimer = null; }
  }

  // ── Handle raw ticks from Rust engine WS ─────────────────────────────

  function handleDecodedMessage(data: any): void {
    if (data.type === 'tick' || data.type === 'Tick') {
      const price = data.price ?? data.p;
      const size = data.size ?? data.s ?? 1;
      let side: 'buy' | 'sell' | 'neutral' = 'neutral';

      // Tick-rule classification
      const rawSide = data.side ?? 'unknown';
      if (rawSide === 'buy' || rawSide === 'sell') {
        side = rawSide;
      } else if (price > prevPrice) {
        side = 'buy';
      } else if (price < prevPrice) {
        side = 'sell';
      } else {
        side = prevSide;
      }
      prevPrice = price;
      prevSide = side;

      const ts = data.timestamp
        ? new Date(data.timestamp).getTime()
        : Date.now();

      ingestTick(price, size, side, ts);
    }
  }

  function handleRawMessage(raw: any, protoWorker: any): void {
    if (raw instanceof ArrayBuffer) {
      msgBuffer.push(raw);
      if (protoBatchPending) return;

      protoBatchPending = true;
      requestAnimationFrame(async () => {
        protoBatchPending = false;
        const batch = msgBuffer;
        msgBuffer = [];
        if (batch.length === 0) return;

        try {
          const decoded = await protoWorker.decodeBatch(
            Comlink.transfer(batch, batch)
          );
          for (const message of decoded) {
            handleDecodedMessage(message);
          }
        } catch (error) {
          console.warn('[OrderFlowChart] Proto decode error:', error);
        }
      });
      return;
    }

    if (typeof raw === 'string') {
      try {
        handleDecodedMessage(JSON.parse(raw));
      } catch (error) {
        console.warn('[OrderFlowChart] JSON parse error:', error);
      }
    }
  }

  // ── Lifecycle ────────────────────────────────────────────────────────

  onMount(async () => {
    if (!containerRef) return;
    containerRef.style.position = 'relative';
    const protoWorker = getProtoWorker();

    // Initialize PixiJS
    bubbleRenderer = new FlowBubbleRenderer();
    await bubbleRenderer.init(containerRef);

    // Watch for resizes
    resizeObserver = new ResizeObserver(() => { /* render loop handles it */ });
    resizeObserver.observe(containerRef);

    // Connect to Rust engine WS for raw ticks
    if (window.location.protocol !== 'https:') {
      const wsHost = window.location.hostname || 'localhost';
      flowWS = new WSClient({
        url: `ws://${wsHost}:8081/ws`,
        encoding: 'auto',
        onMessage: (raw) => handleRawMessage(raw, protoWorker),
      });
      flowWS.connect();
    }

    await syncRecentTrades();
    recentPollTimer = setInterval(() => {
      void syncRecentTrades();
    }, 5000);

    // Start continuous render loop
    startAnimLoop();
  });

  createEffect(on(() => market.symbol, () => {
    resetTickState();
    void syncRecentTrades();
  }, { defer: true }));

  onCleanup(() => {
    stopAnimLoop();
    if (recentPollTimer) clearInterval(recentPollTimer);
    if (resizeObserver) resizeObserver.disconnect();
    if (bubbleRenderer) bubbleRenderer.destroy();
    if (flowWS) flowWS.destroy();
    bubbleRenderer = null;
    flowWS = null;
    recentPollTimer = null;
    msgBuffer = [];
    protoBatchPending = false;
    canvas = undefined;
    ctx = null;
    resetTickState();
  });

  return (
    <div
      ref={containerRef}
      class="w-full h-full relative"
      style={{ 'min-height': '360px' }}
    />
  );
};
