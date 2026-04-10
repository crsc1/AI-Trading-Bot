/**
 * Options Bubble Chart — Two visualization modes:
 *
 * **Grid Mode** (Bookmap-style):
 *   Y-axis = underlying price, X-axis = time.
 *   Split-circle bubbles at time/price cells.
 *
 * **SnakeFlow Mode**:
 *   A living river of order flow. Bubbles flow along a smooth Catmull-Rom
 *   spline that bends upward on buy pressure and downward on sell pressure.
 *   Novel alpha features: absorption flattening, cluster thickness, momentum glow.
 */
import { type Component, createSignal, onMount, onCleanup } from 'solid-js';
import { FlowBubbleRenderer, type BubblePoint } from '../../lib/flowRenderer';
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
import { CatmullRomSpline, noise1d, type Vec2 } from '../../lib/spline';
import { optionsFlow } from '../../signals/optionsFlow';
import { market } from '../../signals/market';
import { cvd } from '../../signals/flow';

const PRICE_TICK = 0.05;

type ChartMode = 'grid' | 'snake' | 'demo';

interface OptionTick {
  price: number;
  size: number;
  side: 'buy' | 'sell';
  ts: number;
}

interface NotableTrade {
  price: number;
  ts: number;
  tag: 'sweep' | 'block' | 'whale';
  side: 'buy' | 'sell';
  size: number;
  sms: number;
}

// ─── Snake control point for pressure-driven spline ──────────────────────
interface SnakeControlPoint {
  timeMs: number;
  buyVol: number;
  sellVol: number;
  totalVol: number;
  pressure: number; // cumulative net pressure (-1 to +1 normalized)
}

const SNAKE_CONTROL_COUNT = 60; // ~5s per point over 5-minute window
const SNAKE_PRESSURE_SMOOTHING = 0.15; // EMA alpha for pressure
const SNAKE_NOISE_AMP = 0.008; // subtle wobble amplitude (fraction of plot height)
const SNAKE_NOISE_SPEED = 0.4; // wobble frequency

export const OptionsBubbleChart: Component = () => {
  let containerRef: HTMLDivElement | undefined;
  let canvas: HTMLCanvasElement | undefined;
  let ctx: CanvasRenderingContext2D | null = null;
  let bubbleRenderer: FlowBubbleRenderer | null = null;
  let animTimer: ReturnType<typeof setTimeout> | null = null;
  let resizeObs: ResizeObserver | null = null;

  const [mode, setMode] = createSignal<ChartMode>('grid');

  // Tick buffer
  let ticks: OptionTick[] = [];
  let notables: NotableTrade[] = [];
  let lastTradeCount = 0;
  const MAX_TICKS = 10000;
  const MAX_NOTABLES = 500;

  // Config
  const aggSeconds = 0.25;
  const visibleWindowMs = 5 * 60 * 1000;
  const renderInterval = 80;

  // Snake state
  let snakePoints: SnakeControlPoint[] = [];
  let smoothedPressure = 0;
  let lastSnakeRebuildMs = 0;

  // ─── Canvas management ──────────────────────────────────────────────

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

  // ─── Trade ingestion (shared by both modes) ─────────────────────────

  function syncTrades() {
    const storeCount = optionsFlow.tradeCount;
    if (storeCount <= lastTradeCount) return;

    const newCount = storeCount - lastTradeCount;
    const newTrades = optionsFlow.trades.slice(0, newCount);

    for (const t of newTrades) {
      const spyPrice = t.spyPrice || market.lastPrice;
      if (spyPrice <= 0) continue;
      const tradeTs = t.timestamp || Date.now();
      const displaySize = Math.min(80, t.size);

      if (t.side === 'mid') {
        const half = displaySize / 2;
        ticks.push({ price: spyPrice, size: half, side: 'buy', ts: tradeTs });
        ticks.push({ price: spyPrice, size: half, side: 'sell', ts: tradeTs });
      } else {
        const side = t.side === 'sell' ? 'sell' as const : 'buy' as const;
        ticks.push({ price: spyPrice, size: displaySize, side, ts: tradeTs });
      }

      if (t.tag !== 'normal') {
        const side = t.side === 'sell' ? 'sell' as const : 'buy' as const;
        notables.push({ price: spyPrice, ts: tradeTs, tag: t.tag, side, size: t.size, sms: t.sms });
      }
    }

    lastTradeCount = storeCount;
    if (ticks.length > MAX_TICKS) ticks = ticks.slice(-Math.floor(MAX_TICKS * 0.8));
    if (notables.length > MAX_NOTABLES) notables = notables.slice(-Math.floor(MAX_NOTABLES * 0.8));
  }

  // ─── Aggregation (shared) ───────────────────────────────────────────

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
      if (t.side === 'buy') cell.buy += t.size; else cell.sell += t.size;
    }

    const result: FlowCloudCell[] = [];
    for (const c of grid.values()) {
      result.push({
        price: c.price,
        time: new Date(c.time).toISOString(),
        buy_vol: c.buy,
        sell_vol: c.sell,
        delta: c.buy - c.sell,
        total_vol: c.buy + c.sell,
      });
    }
    return result;
  }

  // ─── Time-only aggregation for snake (collapse price dimension) ─────

  function ticksToTimeBuckets(): SnakeControlPoint[] {
    if (ticks.length === 0) return [];
    const now = Date.now();
    const cutoff = now - visibleWindowMs;
    const bucketMs = visibleWindowMs / SNAKE_CONTROL_COUNT;

    const buckets = new Map<number, { buy: number; sell: number; total: number }>();
    for (let i = ticks.length - 1; i >= 0; i--) {
      const t = ticks[i];
      if (t.ts < cutoff) break;
      const key = Math.floor((t.ts - cutoff) / bucketMs);
      let b = buckets.get(key);
      if (!b) { b = { buy: 0, sell: 0, total: 0 }; buckets.set(key, b); }
      if (t.side === 'buy') b.buy += t.size; else b.sell += t.size;
      b.total += t.size;
    }

    // Build ordered control points
    const points: SnakeControlPoint[] = [];
    let cumPressure = 0;
    for (let i = 0; i < SNAKE_CONTROL_COUNT; i++) {
      const b = buckets.get(i);
      const buyVol = b?.buy ?? 0;
      const sellVol = b?.sell ?? 0;
      const totalVol = b?.total ?? 0;

      // Net pressure: -1 (all sell) to +1 (all buy)
      const rawPressure = totalVol > 0 ? (buyVol - sellVol) / totalVol : 0;

      // EMA smoothing
      smoothedPressure = smoothedPressure * (1 - SNAKE_PRESSURE_SMOOTHING) + rawPressure * SNAKE_PRESSURE_SMOOTHING;
      cumPressure += smoothedPressure * 0.3; // accumulate for path curvature

      points.push({
        timeMs: cutoff + i * bucketMs + bucketMs / 2,
        buyVol,
        sellVol,
        totalVol,
        pressure: cumPressure,
      });
    }

    // Normalize pressure to [-1, 1] range
    const maxAbs = Math.max(1, ...points.map(p => Math.abs(p.pressure)));
    for (const p of points) p.pressure /= maxAbs;

    return points;
  }

  // ═══════════════════════════════════════════════════════════════════════
  // GRID MODE RENDERING (existing Bookmap-style)
  // ═══════════════════════════════════════════════════════════════════════

  function drawCvdGradient(ctx: CanvasRenderingContext2D, layout: FlowLayout, _dpr: number): void {
    const vel = cvd.velocity;
    const accel = cvd.acceleration;
    const staleness = Date.now() - cvd.lastUpdate;
    if (staleness > 5000 || (vel === 0 && accel === 0)) return;
    const staleFade = staleness < 2000 ? 1.0 : Math.max(0, 1 - (staleness - 2000) / 3000);
    const intensity = Math.min(1, Math.abs(vel) * 1.5);
    const accelBoost = 1 + Math.min(0.5, Math.abs(accel) * 2) * Math.sign(accel) * Math.sign(vel);
    const alpha = Math.min(0.12, intensity * 0.12 * Math.max(0.3, accelBoost)) * staleFade;
    if (alpha < 0.005) return;
    const color = vel > 0 ? '0, 200, 5' : '255, 80, 0';
    const grad = ctx.createLinearGradient(layout.marginL, 0, layout.marginL + layout.plotW, 0);
    grad.addColorStop(0, `rgba(${color}, 0)`);
    grad.addColorStop(0.6, `rgba(${color}, ${alpha * 0.3})`);
    grad.addColorStop(1, `rgba(${color}, ${alpha})`);
    ctx.save();
    ctx.fillStyle = grad;
    ctx.fillRect(layout.marginL, layout.marginT, layout.plotW, layout.plotH);
    ctx.restore();
  }

  function drawNotableOverlays(ctx: CanvasRenderingContext2D, layout: FlowLayout, dpr: number): void {
    const now = Date.now();
    const cutoff = now - visibleWindowMs;
    for (const n of notables) {
      if (n.ts < cutoff) continue;
      const x = tToX(n.ts, layout);
      const y = pToY(n.price, layout);
      if (x < layout.marginL || x > layout.W - layout.ladderW) continue;
      if (y < layout.marginT || y > layout.marginT + layout.plotH) continue;
      const age = now - n.ts;
      const freshness = Math.max(0.15, 1 - (age / visibleWindowMs) * 0.85);
      const baseR = Math.min(18, Math.max(5, Math.sqrt(n.size) * 1.5)) * dpr;
      const color = n.side === 'buy' ? '#00C805' : '#FF5000';
      if (n.tag === 'sweep') {
        ctx.save(); ctx.globalAlpha = freshness * 0.6; ctx.strokeStyle = '#a855f7';
        ctx.lineWidth = 1.5 * dpr; ctx.setLineDash([3 * dpr, 2 * dpr]);
        ctx.beginPath(); ctx.arc(x, y, baseR * 1.2, 0, Math.PI * 2); ctx.stroke();
        ctx.setLineDash([]); ctx.restore();
      } else if (n.tag === 'block') {
        ctx.save(); ctx.globalAlpha = freshness * 0.5; ctx.strokeStyle = color;
        ctx.lineWidth = 2 * dpr; ctx.beginPath(); ctx.arc(x, y, baseR * 1.15, 0, Math.PI * 2);
        ctx.stroke(); ctx.restore();
      } else if (n.tag === 'whale') {
        ctx.save(); ctx.globalAlpha = freshness * 0.15;
        const glow = ctx.createRadialGradient(x, y, baseR * 0.3, x, y, baseR * 1.6);
        glow.addColorStop(0, '#ffb300'); glow.addColorStop(1, 'transparent');
        ctx.fillStyle = glow;
        ctx.fillRect(x - baseR * 1.6, y - baseR * 1.6, baseR * 3.2, baseR * 3.2);
        ctx.globalAlpha = freshness * 0.7; ctx.strokeStyle = '#ffb300';
        ctx.lineWidth = 2 * dpr; ctx.beginPath(); ctx.arc(x, y, baseR * 1.3, 0, Math.PI * 2);
        ctx.stroke(); ctx.restore();
      }
    }
  }

  function renderGrid(): void {
    if (!ctx || !canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.width;
    const H = canvas.height;
    const cells = ticksToCells();
    if (!cells.length) {
      ctx.clearRect(0, 0, W, H); ctx.fillStyle = '#0a0a12'; ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = '#b0b0c8'; ctx.font = `${12 * dpr}px "Geist Mono", "SF Mono", Menlo, monospace`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText('Waiting for option trades...', W / 2, H / 2);
      return;
    }
    const layout = computeLayout(W, H, dpr, cells, visibleWindowMs, aggSeconds, PRICE_TICK, true);
    if (!layout) return;
    drawFlowCanvas(ctx, layout, cells, aggSeconds, PRICE_TICK);
    drawCvdGradient(ctx, layout, dpr);
    const points = computeBubblePoints(layout, cells, aggSeconds, false);
    const minR = Math.max(4 * dpr, (layout.plotW / Math.max(visibleWindowMs / (aggSeconds * 1000), 1)) * 0.55);
    drawTrail(ctx, points, dpr, minR);
    drawNotableOverlays(ctx, layout, dpr);
    if (bubbleRenderer?.isReady) {
      bubbleRenderer.resize(containerRef!.getBoundingClientRect().width, containerRef!.getBoundingClientRect().height);
      bubbleRenderer.renderBubbles(points, dpr, Math.max(aggSeconds * 2000, 3000));
    }
  }

  // ═══════════════════════════════════════════════════════════════════════
  // SNAKE MODE RENDERING
  // ═══════════════════════════════════════════════════════════════════════

  function renderSnake(): void {
    if (!ctx || !canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.width;
    const H = canvas.height;

    // Rebuild control points (throttled to 150ms)
    const now = Date.now();
    if (now - lastSnakeRebuildMs > 150 || snakePoints.length === 0) {
      snakePoints = ticksToTimeBuckets();
      lastSnakeRebuildMs = now;
    }

    // Background
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#0a0a12';
    ctx.fillRect(0, 0, W, H);

    if (snakePoints.length < 3) {
      ctx.fillStyle = '#b0b0c8';
      ctx.font = `${12 * dpr}px "Geist Mono", "SF Mono", Menlo, monospace`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText('Waiting for option trades...', W / 2, H / 2);
      return;
    }

    // Layout margins
    const marginL = 60 * dpr;
    const marginR = 20 * dpr;
    const marginT = 30 * dpr;
    const marginB = 30 * dpr;
    const plotW = W - marginL - marginR;
    const plotH = H - marginT - marginB;
    const centerY = marginT + plotH / 2;

    // ── Draw background grid ──

    ctx.save();
    ctx.strokeStyle = 'rgba(255,255,255,0.04)';
    ctx.lineWidth = 1;
    // Horizontal center line
    ctx.beginPath(); ctx.moveTo(marginL, centerY); ctx.lineTo(marginL + plotW, centerY); ctx.stroke();
    // Faint grid lines at 25% and 75%
    for (const frac of [0.25, 0.75]) {
      const y = marginT + plotH * frac;
      ctx.beginPath(); ctx.moveTo(marginL, y); ctx.lineTo(marginL + plotW, y); ctx.stroke();
    }
    ctx.restore();

    // ── Labels ──
    ctx.save();
    ctx.fillStyle = '#8080a0';
    ctx.font = `${9 * dpr}px "Geist", sans-serif`;
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    ctx.fillText('BUY', marginL - 8 * dpr, marginT + plotH * 0.15);
    ctx.fillText('SELL', marginL - 8 * dpr, marginT + plotH * 0.85);
    ctx.fillStyle = '#505070'; ctx.fillText('NET 0', marginL - 8 * dpr, centerY);
    ctx.restore();

    // ── Build spline from control points ──

    const splineVecs: Vec2[] = snakePoints.map((cp, i) => {
      const xFrac = i / (snakePoints.length - 1);
      const x = marginL + xFrac * plotW;
      // Pressure drives Y: positive = up (buy), negative = down (sell)
      const pressureY = -cp.pressure * (plotH * 0.4); // ±40% of plot height
      // Add organic wobble on the tail (older points wobble more)
      const age = 1 - xFrac; // 1 = oldest, 0 = newest
      const wobble = noise1d(i * SNAKE_NOISE_SPEED + now * 0.0003) * SNAKE_NOISE_AMP * plotH * age;
      const y = centerY + pressureY + wobble;
      return { x, y };
    });

    const spline = new CatmullRomSpline(splineVecs);

    // ── Draw snake trail on Canvas 2D ──

    const trailSamples = 200;
    ctx.save();
    ctx.lineWidth = Math.max(3 * dpr, 4);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    // Draw trail with pressure-based color gradient
    for (let i = 1; i < trailSamples; i++) {
      const t0 = (i - 1) / (trailSamples - 1);
      const t1 = i / (trailSamples - 1);
      const p0 = spline.getPointAt(t0);
      const p1 = spline.getPointAt(t1);

      // Color: interpolate based on local slope (rising = green, falling = red)
      const slope = p1.y - p0.y; // negative slope = upward = buying
      const slopeNorm = Math.min(1, Math.abs(slope) / (2 * dpr));

      // Alpha: fade older parts of trail
      const freshness = 0.08 + t1 * 0.25; // 0.08 at oldest, 0.33 at newest

      if (slope < -0.5) {
        ctx.strokeStyle = `rgba(0, 200, 5, ${freshness * slopeNorm + freshness * 0.3})`;
      } else if (slope > 0.5) {
        ctx.strokeStyle = `rgba(255, 80, 0, ${freshness * slopeNorm + freshness * 0.3})`;
      } else {
        ctx.strokeStyle = `rgba(136, 136, 176, ${freshness * 0.4})`;
      }

      ctx.beginPath();
      ctx.moveTo(p0.x, p0.y);
      ctx.lineTo(p1.x, p1.y);
      ctx.stroke();
    }
    ctx.restore();

    // ── Alpha feature: absorption glow (snake flattens despite volume) ──

    drawAbsorptionZones(ctx, spline, snakePoints, marginL, plotW, dpr);

    // ── Alpha feature: momentum acceleration glow ──

    drawMomentumGlow(ctx, spline, snakePoints, marginL, plotW, plotH, centerY, dpr);

    // ── Place bubbles along spline using PixiJS ──

    const cells = ticksToCells();
    if (!cells.length || !bubbleRenderer?.isReady) return;

    const cutoff = now - visibleWindowMs;
    const bubblePoints: BubblePoint[] = [];

    // Volume percentiles for radius scaling (same as grid mode)
    const allVols = cells.map(c => c.total_vol).filter(v => v > 0).sort((a, b) => a - b);
    const p20 = allVols[Math.floor(allVols.length * 0.2)] || 1;
    const p50 = allVols[Math.floor(allVols.length * 0.5)] || 10;
    const p80 = allVols[Math.floor(allVols.length * 0.8)] || 100;
    const p95 = allVols[Math.floor(allVols.length * 0.95)] || 1000;
    const minR = Math.max(4 * dpr, 6 * dpr);
    const maxR = Math.max(minR * 3.5, 20 * dpr);

    function volToRadius(vol: number): number {
      if (vol <= p20) return minR;
      if (vol <= p50) return minR + ((vol - p20) / (p50 - p20 || 1)) * minR * 0.5;
      if (vol <= p80) return minR * 1.5 + ((vol - p50) / (p80 - p50 || 1)) * minR;
      if (vol <= p95) return minR * 2.5 + ((vol - p80) / (p95 - p80 || 1)) * minR;
      return minR * 3.5 + Math.min(1, (vol - p95) / (p95 * 2 || 1)) * (maxR - minR * 3.5);
    }

    for (const c of cells) {
      const cellMs = c._ms ?? Date.parse(c.time);
      if (cellMs < cutoff) continue;

      // Map cell time to spline parameter (0 = oldest, 1 = newest)
      const t = (cellMs - cutoff) / visibleWindowMs;
      const pt = spline.getPointAt(Math.max(0, Math.min(1, t)));

      // Slight vertical scatter by price hash to prevent bubble stacking
      const priceHash = ((c.price * 100) % 17) / 17 - 0.5;
      const scatter = priceHash * 12 * dpr;

      const r = volToRadius(c.total_vol);
      const totalVol = c.buy_vol + c.sell_vol;
      const buyRatio = totalVol > 0 ? c.buy_vol / totalVol : 0.5;
      const deltaRatio = totalVol > 0 ? c.delta / totalVol : 0;
      const age = t;
      const opacity = Math.max(0.15, Math.min(0.95, 0.15 + age * 0.8));

      bubblePoints.push({
        x: pt.x,
        y: pt.y + scatter,
        r,
        tMs: cellMs,
        opacity,
        deltaRatio,
        buyRatio,
      });
    }

    // ── Alpha feature: cluster thickness (thicker segments where volume clusters) ──

    drawClusterThickness(ctx, spline, cells, cutoff, visibleWindowMs, dpr);

    bubbleRenderer.resize(containerRef!.getBoundingClientRect().width, containerRef!.getBoundingClientRect().height);
    bubbleRenderer.renderBubbles(bubblePoints, dpr, 3000);
  }

  // ─── Alpha Feature: Absorption Zones ────────────────────────────────
  // When the snake flattens (low slope) despite high volume, big orders
  // are being absorbed without moving price. Highlight these zones.

  function drawAbsorptionZones(
    ctx: CanvasRenderingContext2D,
    spline: CatmullRomSpline,
    points: SnakeControlPoint[],
    marginL: number,
    plotW: number,
    dpr: number,
  ): void {
    if (points.length < 5) return;

    ctx.save();
    for (let i = 2; i < points.length - 2; i++) {
      const cp = points[i];
      if (cp.totalVol < 10) continue; // need meaningful volume

      // Check flatness: 3-point slope window
      const slopeBefore = points[i].pressure - points[i - 2].pressure;
      const slopeAfter = points[i + 2].pressure - points[i].pressure;
      const flatness = 1 - Math.min(1, (Math.abs(slopeBefore) + Math.abs(slopeAfter)) * 5);

      if (flatness < 0.6) continue; // not flat enough

      // Volume intensity
      const volIntensity = Math.min(1, cp.totalVol / 50);

      // Absorption = flat + high volume
      const absorption = flatness * volIntensity;
      if (absorption < 0.3) continue;

      const t = i / (points.length - 1);
      const pt = spline.getPointAt(t);
      const radius = (8 + absorption * 16) * dpr;

      ctx.globalAlpha = absorption * 0.12;
      const glow = ctx.createRadialGradient(pt.x, pt.y, 0, pt.x, pt.y, radius);
      glow.addColorStop(0, '#ffb300');
      glow.addColorStop(0.5, 'rgba(255, 179, 0, 0.3)');
      glow.addColorStop(1, 'transparent');
      ctx.fillStyle = glow;
      ctx.fillRect(pt.x - radius, pt.y - radius, radius * 2, radius * 2);
    }
    ctx.restore();
  }

  // ─── Alpha Feature: Momentum Acceleration Glow ──────────────────────
  // When pressure is accelerating (curve bending harder), draw intensified
  // glow on the trail edge. Green when accelerating up, red when down.

  function drawMomentumGlow(
    ctx: CanvasRenderingContext2D,
    spline: CatmullRomSpline,
    points: SnakeControlPoint[],
    marginL: number,
    plotW: number,
    plotH: number,
    centerY: number,
    dpr: number,
  ): void {
    if (points.length < 4) return;

    ctx.save();
    for (let i = 2; i < points.length; i++) {
      const accel = points[i].pressure - 2 * points[i - 1].pressure + points[i - 2].pressure;
      const absAccel = Math.abs(accel);
      if (absAccel < 0.02) continue;

      const intensity = Math.min(1, absAccel * 15);
      const t = i / (points.length - 1);
      const pt = spline.getPointAt(t);
      const radius = (6 + intensity * 10) * dpr;
      const color = accel < 0 ? '0, 200, 5' : '255, 80, 0'; // negative accel = curving up = bullish

      ctx.globalAlpha = intensity * 0.08;
      const glow = ctx.createRadialGradient(pt.x, pt.y, 0, pt.x, pt.y, radius);
      glow.addColorStop(0, `rgba(${color}, 0.4)`);
      glow.addColorStop(1, 'transparent');
      ctx.fillStyle = glow;
      ctx.fillRect(pt.x - radius, pt.y - radius, radius * 2, radius * 2);
    }
    ctx.restore();
  }

  // ─── Alpha Feature: Cluster Thickness ───────────────────────────────
  // Where many trades cluster in a narrow time window, draw a thicker
  // band along the snake to show "congestion zones".

  function drawClusterThickness(
    ctx: CanvasRenderingContext2D,
    spline: CatmullRomSpline,
    cells: FlowCloudCell[],
    cutoff: number,
    windowMs: number,
    dpr: number,
  ): void {
    // Count cells per time bucket (congestion = many price levels active at once)
    const bucketCount = 30;
    const bucketMs = windowMs / bucketCount;
    const counts = new Float32Array(bucketCount);
    const volumes = new Float32Array(bucketCount);

    for (const c of cells) {
      const ms = c._ms ?? Date.parse(c.time);
      if (ms < cutoff) continue;
      const idx = Math.min(bucketCount - 1, Math.floor((ms - cutoff) / bucketMs));
      counts[idx]++;
      volumes[idx] += c.total_vol;
    }

    const maxCount = Math.max(1, ...counts);

    ctx.save();
    ctx.lineCap = 'round';
    for (let i = 0; i < bucketCount; i++) {
      const density = counts[i] / maxCount;
      if (density < 0.3) continue;

      const t0 = i / bucketCount;
      const t1 = (i + 1) / bucketCount;
      const p0 = spline.getPointAt(t0);
      const p1 = spline.getPointAt(t1);

      const thickness = (2 + density * 6) * dpr;
      ctx.globalAlpha = density * 0.15;
      ctx.strokeStyle = 'rgba(85, 136, 238, 0.5)'; // accent blue
      ctx.lineWidth = thickness;
      ctx.beginPath();
      ctx.moveTo(p0.x, p0.y);
      ctx.lineTo(p1.x, p1.y);
      ctx.stroke();
    }
    ctx.restore();
  }

  // ═══════════════════════════════════════════════════════════════════════
  // DEMO MODE — Simulated trade generator for testing without live data
  // ═══════════════════════════════════════════════════════════════════════

  let simInterval: ReturnType<typeof setInterval> | null = null;
  let simPrice = 550; // simulated SPY price
  let simTrend = 0; // momentum drift (-1 to +1)
  let simSeeded = false;

  function startSim() {
    if (simInterval) return;
    simSeeded = false;

    // Seed with 2 minutes of historical sim data so chart isn't empty
    function seedHistory() {
      if (simSeeded) return;
      simSeeded = true;
      const now = Date.now();
      for (let ms = now - 120_000; ms < now; ms += 200 + Math.random() * 300) {
        injectSimTrade(ms);
      }
    }

    seedHistory();

    // Inject 3-8 trades per second (realistic 0DTE flow during active session)
    simInterval = setInterval(() => {
      const count = 3 + Math.floor(Math.random() * 6);
      const now = Date.now();
      for (let i = 0; i < count; i++) {
        injectSimTrade(now - Math.random() * 80);
      }
    }, 200);
  }

  function stopSim() {
    if (simInterval) { clearInterval(simInterval); simInterval = null; }
  }

  function injectSimTrade(ts: number) {
    // Random walk for price with momentum
    simTrend += (Math.random() - 0.5) * 0.1;
    simTrend = Math.max(-0.6, Math.min(0.6, simTrend)) * 0.995; // mean-revert
    simPrice += simTrend * 0.02 + (Math.random() - 0.5) * 0.03;
    simPrice = Math.max(540, Math.min(560, simPrice));

    // Directional bias follows trend
    const buyProb = 0.5 + simTrend * 0.3;
    const side: 'buy' | 'sell' = Math.random() < buyProb ? 'buy' : 'sell';

    // Size: mostly small, occasional large (power law)
    const sizeRaw = Math.random();
    const size = sizeRaw < 0.7 ? 1 + Math.floor(Math.random() * 5)
      : sizeRaw < 0.92 ? 10 + Math.floor(Math.random() * 40)
      : 50 + Math.floor(Math.random() * 150); // rare whale

    ticks.push({
      price: Math.round(simPrice * 100) / 100,
      size: Math.min(80, size),
      side,
      ts,
    });

    if (ticks.length > MAX_TICKS) ticks = ticks.slice(-Math.floor(MAX_TICKS * 0.8));
  }

  // ═══════════════════════════════════════════════════════════════════════
  // RENDER DISPATCH + LOOP
  // ═══════════════════════════════════════════════════════════════════════

  function render(): void {
    const m = mode();
    if (m !== 'demo') syncTrades();
    if (!ensureCanvas() || !ctx || !canvas) return;

    if (m === 'snake' || m === 'demo') {
      renderSnake();
    } else {
      renderGrid();
    }
  }

  let running = false;

  function startLoop() {
    if (running) return;
    running = true;
    function tick() {
      if (!running) return;
      // Demo mode always renders (sim generates ticks continuously)
      if (mode() === 'demo' || ticks.length > 0 || optionsFlow.tradeCount > lastTradeCount) render();
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
    resizeObs = new ResizeObserver(() => {});
    resizeObs.observe(containerRef);
    startLoop();
  });

  onCleanup(() => {
    stopLoop();
    stopSim();
    if (resizeObs) resizeObs.disconnect();
    if (bubbleRenderer) bubbleRenderer.destroy();
    bubbleRenderer = null;
    canvas = undefined;
    ctx = null;
    ticks = [];
    notables = [];
    snakePoints = [];
  });

  return (
    <div ref={containerRef} class="w-full h-full relative" style={{ 'min-height': '150px' }}>
      {/* Mode toggle overlay */}
      <div class="absolute top-2 right-2 z-10 flex items-center gap-0.5 bg-surface-2/80 backdrop-blur-sm rounded-lg border border-border-default p-0.5">
        {(['grid', 'snake', 'demo'] as ChartMode[]).map(m => (
          <button
            class={`px-2.5 py-1 text-[10px] font-display rounded-md transition-colors ${
              mode() === m
                ? m === 'demo' ? 'bg-warning/20 text-warning' : 'bg-accent/20 text-accent'
                : 'text-text-muted hover:text-text-secondary'
            }`}
            onClick={() => {
              const prev = mode();
              if (prev === 'demo') stopSim();
              setMode(m);
              if (m === 'demo') {
                ticks = []; snakePoints = []; smoothedPressure = 0;
                startSim();
              }
            }}
          >
            {m === 'demo' ? 'Demo' : m === 'snake' ? 'Snake' : 'Grid'}
          </button>
        ))}
      </div>
    </div>
  );
};
