/**
 * Order Flow Chart — SolidJS wrapper for Canvas 2D + PixiJS GPU rendering.
 *
 * Architecture:
 * - SolidJS component manages the container div and lifecycle
 * - FlowBubbleRenderer (PixiJS) handles GPU-accelerated bubble sprites
 * - flowCanvas (Canvas 2D) handles grids, labels, ladder, volume bars, indicators
 * - requestAnimationFrame batches all rendering at 60fps
 */
import { type Component, onMount, onCleanup, createEffect, on } from 'solid-js';
import { FlowBubbleRenderer } from '../../lib/flowRenderer';
import {
  computeLayout,
  drawFlowCanvas,
  computeBubblePoints,
  drawTrail,
  type FlowCloudCell,
} from '../../lib/flowCanvas';
import { flow } from '../../signals/flow';
import { api } from '../../lib/api';
import { setClouds } from '../../signals/flow';

const WINDOW_MS = 4 * 60 * 1000;  // 4 minute visible window
const AGG_SECONDS = 1;             // 1 second aggregation
const PRICE_TICK = 0.05;           // SPY price tick

export const OrderFlowChart: Component = () => {
  let containerRef: HTMLDivElement | undefined;
  let canvas: HTMLCanvasElement | undefined;
  let ctx: CanvasRenderingContext2D | null = null;
  let bubbleRenderer: FlowBubbleRenderer | null = null;
  let rafId: number | null = null;
  let resizeObserver: ResizeObserver | null = null;

  // Current data (mutable for perf — no reactive overhead on 60fps renders)
  let currentCells: FlowCloudCell[] = [];
  let needsRender = true;

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
      needsRender = true;
    }

    return true;
  }

  function render(): void {
    if (!ensureCanvas() || !ctx || !canvas) return;

    const dpr = window.devicePixelRatio || 1;
    const W = canvas.width;
    const H = canvas.height;

    const cells = currentCells;
    if (!cells.length) {
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = '#0a0a12';
      ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = '#6e6e88';
      ctx.font = `${12 * dpr}px "SF Mono", Menlo, monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('Waiting for order flow data...', W / 2, H / 2);
      return;
    }

    const hasLiveData = false; // Will be true when WS ticks arrive
    const layout = computeLayout(W, H, dpr, cells, WINDOW_MS, AGG_SECONDS, PRICE_TICK, hasLiveData);
    if (!layout) return;

    // 1. Draw Canvas 2D layer (grids, labels, ladder, volume bars, indicators)
    drawFlowCanvas(ctx, layout, cells, AGG_SECONDS, PRICE_TICK);

    // 2. Compute bubble positions
    const points = computeBubblePoints(layout, cells, AGG_SECONDS, false);

    // 3. Draw trail shadow on Canvas 2D
    const minR = Math.max(4 * dpr, (layout.plotW / Math.max(WINDOW_MS / (AGG_SECONDS * 1000), 1)) * 0.55);
    drawTrail(ctx, points, dpr, minR);

    // 4. Render GPU bubbles via PixiJS
    if (bubbleRenderer?.isReady) {
      bubbleRenderer.resize(
        containerRef!.getBoundingClientRect().width,
        containerRef!.getBoundingClientRect().height
      );
      const pulseThreshold = Math.max(AGG_SECONDS * 2000, 3000);
      bubbleRenderer.renderBubbles(points, dpr, pulseThreshold);
    }
  }

  function renderLoop(): void {
    if (needsRender) {
      render();
      needsRender = false;
    }
    rafId = requestAnimationFrame(renderLoop);
  }

  async function loadFlowData(): Promise<void> {
    try {
      const data = await api.getFlowClouds('SPY', 5);
      if (data.clouds && data.clouds.length > 0) {
        const cells: FlowCloudCell[] = data.clouds.map((c: any) => ({
          price: c.price,
          time: c.time,
          buy_vol: c.buy_vol || 0,
          sell_vol: c.sell_vol || 0,
          delta: c.delta || 0,
          total_vol: c.total_vol || (c.buy_vol || 0) + (c.sell_vol || 0),
        }));
        currentCells = cells;
        setClouds(
          cells.map((c) => ({
            price: c.price,
            time: new Date(c.time).getTime() / 1000,
            buy_vol: c.buy_vol,
            sell_vol: c.sell_vol,
            delta: c.delta,
          })),
          data.meta || null
        );
        needsRender = true;
      }
    } catch (e) {
      console.warn('[OrderFlow] Failed to load clouds:', e);
    }
  }

  onMount(async () => {
    if (!containerRef) return;
    containerRef.style.position = 'relative';

    // Initialize PixiJS bubble renderer
    bubbleRenderer = new FlowBubbleRenderer();
    await bubbleRenderer.init(containerRef);

    // Start render loop
    renderLoop();

    // Watch for container resizes
    resizeObserver = new ResizeObserver(() => {
      needsRender = true;
    });
    resizeObserver.observe(containerRef);

    // Load initial data
    loadFlowData();

    // Refresh every 15 seconds
    const interval = setInterval(loadFlowData, 15000);
    onCleanup(() => clearInterval(interval));
  });

  onCleanup(() => {
    if (rafId !== null) cancelAnimationFrame(rafId);
    if (resizeObserver) resizeObserver.disconnect();
    if (bubbleRenderer) bubbleRenderer.destroy();
    bubbleRenderer = null;
    canvas = undefined;
    ctx = null;
  });

  // Re-render when flow store updates
  createEffect(
    on(
      () => flow.clouds.length,
      () => {
        needsRender = true;
      }
    )
  );

  return (
    <div
      ref={containerRef}
      class="w-full h-full relative"
      style={{ 'min-height': '150px' }}
    />
  );
};
