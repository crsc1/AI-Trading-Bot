/**
 * Canvas 2D rendering for order flow chart.
 * Handles: background, grids, price labels, time labels, price ladder,
 * volume bars, divergence indicator, absorption markers, imbalance arrows.
 *
 * Ported from dashboard/static/js/flow.js renderFlowChart() (lines 1154-1749).
 * The PixiJS bubble layer renders on top of this.
 */
import type { BubblePoint } from './flowRenderer';

export interface FlowCloudCell {
  price: number;
  time: string;
  buy_vol: number;
  sell_vol: number;
  delta: number;
  total_vol: number;
  _ms?: number; // Cached timestamp
}

export interface FlowLayout {
  marginL: number;
  marginT: number;
  ladderW: number;
  plotW: number;
  plotH: number;
  timeLabelH: number;
  volBarH: number;
  separatorH: number;
  dpr: number;
  W: number;
  H: number;
  xStartMs: number;
  xEndMs: number;
  windowMs: number;
  yMin: number;
  yMax: number;
  labelStep: number;
  firstPriceTick: number;
}

const COLORS = {
  bg: '#0a0a12',
  titleColor: '#5588ee',
  subtitleColor: '#6e6e88',
  labelColor: '#6e6e88',
  gridColor: 'rgba(255,255,255,0.03)',
  separatorColor: 'rgba(255,255,255,0.06)',
  positive: '#00C805',
  negative: '#FF5000',
  warning: '#ffb300',
  fontFamily: '"Geist Mono", "SF Mono", Menlo, monospace',
};

/**
 * Compute layout geometry and coordinate mappers.
 */
export function computeLayout(
  W: number,
  H: number,
  dpr: number,
  cells: FlowCloudCell[],
  windowMs: number,
  _aggSeconds: number,
  priceTick: number,
  hasLiveData: boolean
): FlowLayout | null {
  if (!cells.length) return null;

  // Ensure _ms cached
  for (const c of cells) {
    if (c._ms === undefined) c._ms = new Date(c.time).getTime();
  }
  cells.sort((a, b) => a._ms! - b._ms! || a.price - b.price);

  // X range (time window)
  let xEndMs: number;
  if (hasLiveData) {
    xEndMs = Date.now();
  } else {
    xEndMs = Math.max(...cells.map((c) => c._ms!));
  }
  const xStartMs = xEndMs - windowMs;

  // Filter to visible window
  const visible = cells.filter((c) => c._ms! >= xStartMs);
  if (!visible.length) return null;

  // Layout constants
  const marginL = 50 * dpr;
  const ladderW = 110 * dpr;
  const marginT = 8 * dpr;
  const isCompact = H / dpr < 420;
  const timeLabelH = isCompact ? 24 * dpr : 40 * dpr;
  const volBarH = isCompact ? Math.round(H * 0.1) : Math.round(H * 0.15);
  const separatorH = 2 * dpr;
  const marginB = timeLabelH + volBarH + separatorH * 2;
  const plotW = W - marginL - ladderW;
  const plotH = H - marginT - marginB;

  // Price range with IQR outlier filtering
  const prices = visible.map((c) => c.price).sort((a, b) => a - b);
  const q1Idx = Math.floor(prices.length * 0.25);
  const q3Idx = Math.floor(prices.length * 0.75);
  const q1 = prices[q1Idx], q3 = prices[q3Idx];
  const iqr = q3 - q1 || priceTick * 10;
  const lowerFence = q1 - 3 * iqr;
  const upperFence = q3 + 3 * iqr;
  const clean = prices.filter((p) => p >= lowerFence && p <= upperFence);
  const use = clean.length >= 3 ? clean : prices;

  const rawMin = use[0];
  const rawMax = use[use.length - 1];
  const rawRange = rawMax - rawMin;
  const dataMid = (rawMin + rawMax) / 2;

  // Fixed 22px label spacing
  const TARGET_LABEL_PX = 22 * dpr;
  const numLabels = Math.floor(plotH / TARGET_LABEL_PX);

  // Pick nice price step
  const niceSteps = [0.05, 0.1, 0.25, 0.5, 1, 2, 5];
  let labelStep = priceTick;
  for (const s of niceSteps) {
    if (s >= priceTick && s * numLabels >= rawRange * 1.3) {
      labelStep = s;
      break;
    }
  }
  if (labelStep * numLabels < rawRange) {
    labelStep = Math.ceil(rawRange / numLabels / priceTick) * priceTick;
  }

  const totalRange = numLabels * labelStep;
  const yMin = Math.floor((dataMid - totalRange / 2) / labelStep) * labelStep;
  const yMax = yMin + totalRange;
  const firstPriceTick = Math.ceil(yMin / labelStep) * labelStep;

  return {
    marginL, marginT, ladderW, plotW, plotH,
    timeLabelH, volBarH, separatorH, dpr, W, H,
    xStartMs, xEndMs, windowMs,
    yMin, yMax, labelStep, firstPriceTick,
  };
}

/** Map time to X pixel */
export function tToX(ms: number, layout: FlowLayout): number {
  return layout.marginL + ((ms - layout.xStartMs) / layout.windowMs) * layout.plotW;
}

/** Map price to Y pixel */
export function pToY(price: number, layout: FlowLayout): number {
  return layout.marginT + layout.plotH - ((price - layout.yMin) / (layout.yMax - layout.yMin)) * layout.plotH;
}

/** Format volume for display */
function fmtVol(v: number): string {
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
  if (v >= 1_000) return (v / 1_000).toFixed(1) + 'K';
  return v.toFixed(0);
}

/**
 * Draw all Canvas 2D layers (background, grids, labels, ladder, volume bars, indicators).
 */
export function drawFlowCanvas(
  ctx: CanvasRenderingContext2D,
  layout: FlowLayout,
  cells: FlowCloudCell[],
  aggSeconds: number,
  _priceTick: number
): void {
  const { W, H, dpr, marginL, marginT, plotW, plotH, ladderW, timeLabelH, volBarH, separatorH } = layout;
  const { xStartMs, xEndMs, windowMs, yMax, labelStep, firstPriceTick } = layout;

  const timeLabelTop = marginT + plotH + separatorH;
  const volTop = timeLabelTop + timeLabelH + separatorH;
  const volH = volBarH - 4 * dpr;

  // Clear
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = COLORS.bg;
  ctx.fillRect(0, 0, W, H);

  // Visual separators
  ctx.fillStyle = 'rgba(255,255,255,0.08)';
  ctx.fillRect(marginL, marginT + plotH, plotW, separatorH);
  ctx.fillRect(marginL, volTop - separatorH, plotW, separatorH);
  ctx.fillStyle = 'rgba(8,8,16,0.5)';
  ctx.fillRect(marginL, timeLabelTop, plotW, timeLabelH);
  ctx.fillStyle = 'rgba(12,12,20,0.4)';
  ctx.fillRect(marginL, volTop, plotW, volH + 4 * dpr);

  // Y-axis grid
  ctx.lineWidth = 1;
  for (let p = firstPriceTick; p <= yMax; p += labelStep) {
    const gy = pToY(p, layout);
    if (gy < marginT || gy > marginT + plotH) continue;
    ctx.strokeStyle = 'rgba(255,255,255,0.04)';
    ctx.beginPath(); ctx.moveTo(marginL, gy); ctx.lineTo(W - ladderW, gy); ctx.stroke();
  }

  // X-axis grid
  const aggMs = aggSeconds * 1000;
  let timeStep = aggMs;
  const maxGridLines = 200;
  const minTimeStep = windowMs / maxGridLines;
  if (timeStep < minTimeStep) timeStep = minTimeStep;
  const niceTimeSteps = [5, 10, 25, 50, 100, 250, 500, 1000, 2000, 3000, 5000, 10000, 15000, 30000, 60000];
  if (timeStep > aggMs) {
    for (const s of niceTimeSteps) {
      if (s >= timeStep) { timeStep = s; break; }
    }
  }

  const firstTimeTick = Math.ceil(xStartMs / timeStep) * timeStep;
  const majorTimeStep = timeStep <= 1000 ? 5000 : timeStep <= 5000 ? 15000 : timeStep * 5;

  for (let t = firstTimeTick; t <= xEndMs; t += timeStep) {
    const gx = tToX(t, layout);
    if (gx < marginL || gx > W - ladderW) continue;
    const isMajor = Math.abs(t % majorTimeStep) < timeStep / 2;
    ctx.strokeStyle = isMajor ? 'rgba(255,255,255,0.07)' : 'rgba(255,255,255,0.025)';
    ctx.beginPath(); ctx.moveTo(gx, marginT); ctx.lineTo(gx, marginT + plotH); ctx.stroke();
  }

  // Left price labels
  ctx.font = `${9 * dpr}px ${COLORS.fontFamily}`;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let p = firstPriceTick; p <= yMax; p += labelStep) {
    const gy = pToY(p, layout);
    if (gy < marginT + 6 || gy > marginT + plotH - 6) continue;
    ctx.fillStyle = '#7a7a94';
    const label = p % 1 === 0 ? p.toFixed(0) : parseFloat(p.toFixed(2)).toString();
    ctx.fillText(label, marginL - 6 * dpr, gy);
  }

  // Price ladder (right side)
  const ladderX = W - ladderW;
  const priceLabelW = 46 * dpr;
  const ladderBarMaxW = ladderW - priceLabelW - 4 * dpr;
  const priceLabelX = ladderX + priceLabelW;
  const barStartX = priceLabelX + 2 * dpr;

  ctx.fillStyle = 'rgba(15,15,25,0.6)';
  ctx.fillRect(ladderX, marginT, ladderW, plotH);
  ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(ladderX, marginT); ctx.lineTo(ladderX, marginT + plotH); ctx.stroke();

  // Aggregate volume by price step for ladder bars
  const ladderProfile: Record<string, { buy: number; sell: number }> = {};
  const visible = cells.filter((c) => c._ms! >= xStartMs);
  for (const c of visible) {
    const key = (Math.round(c.price / labelStep) * labelStep).toFixed(2);
    if (!ladderProfile[key]) ladderProfile[key] = { buy: 0, sell: 0 };
    ladderProfile[key].buy += c.buy_vol;
    ladderProfile[key].sell += c.sell_vol;
  }
  const ladderMaxVol = Math.max(...Object.values(ladderProfile).map((v) => v.buy + v.sell), 1);

  ctx.font = `${9 * dpr}px ${COLORS.fontFamily}`;
  const TARGET_LABEL_PX = 22 * dpr;

  for (let p = firstPriceTick; p <= yMax; p += labelStep) {
    const gy = pToY(p, layout);
    if (gy < marginT + 4 || gy > marginT + plotH - 4) continue;
    const pKey = p.toFixed(2);
    const vol = ladderProfile[pKey];

    ctx.strokeStyle = 'rgba(255,255,255,0.03)';
    ctx.beginPath(); ctx.moveTo(ladderX, gy); ctx.lineTo(W, gy); ctx.stroke();

    if (vol) {
      const totalVol = vol.buy + vol.sell;
      const totalW = (totalVol / ladderMaxVol) * ladderBarMaxW;
      const sellW = totalW * (vol.sell / (totalVol || 1));
      const buyW = totalW - sellW;
      const barH = Math.max(2 * dpr, Math.min(TARGET_LABEL_PX * 0.7, 14 * dpr));

      ctx.fillStyle = 'rgba(239,83,80,0.75)';
      ctx.fillRect(barStartX, gy - barH / 2, sellW, barH);
      ctx.fillStyle = 'rgba(38,166,154,0.75)';
      ctx.fillRect(barStartX + sellW, gy - barH / 2, buyW, barH);

      // Imbalance arrows
      const imbalanceRatio = (vol.buy - vol.sell) / (totalVol);
      if (Math.abs(imbalanceRatio) > 0.2) {
        const isBuy = imbalanceRatio > 0.2;
        const arrowSize = 8 * dpr;
        const arrowX = W - 10 * dpr;
        ctx.fillStyle = isBuy ? COLORS.positive : COLORS.negative;
        ctx.globalAlpha = 0.65;
        ctx.beginPath();
        if (isBuy) {
          ctx.moveTo(arrowX - arrowSize / 2, gy + arrowSize / 2);
          ctx.lineTo(arrowX + arrowSize / 2, gy + arrowSize / 2);
          ctx.lineTo(arrowX, gy - arrowSize / 2);
        } else {
          ctx.moveTo(arrowX - arrowSize / 2, gy - arrowSize / 2);
          ctx.lineTo(arrowX + arrowSize / 2, gy - arrowSize / 2);
          ctx.lineTo(arrowX, gy + arrowSize / 2);
        }
        ctx.closePath();
        ctx.fill();
        ctx.globalAlpha = 1.0;
      }
    }

    const hasVol = !!vol;
    ctx.fillStyle = hasVol ? '#9898b0' : '#52526a';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.fillText(pKey, priceLabelX - 2 * dpr, gy);
  }

  // Time labels (rotated 60 degrees)
  const showSeconds = timeStep < 60000;
  const timeFontSize = 7;
  ctx.font = `${timeFontSize * dpr}px ${COLORS.fontFamily}`;
  const sampleLabel = showSeconds ? '09:45:32' : '09:45';
  const labelTextW = ctx.measureText(sampleLabel).width;
  const rotAngle = -60 * (Math.PI / 180);
  const effectiveLabelW = Math.abs(labelTextW * Math.cos(rotAngle)) + Math.abs(timeFontSize * dpr * Math.sin(rotAngle));
  const labelPxW = effectiveLabelW + 2 * dpr;
  const pxPerStep = (plotW / windowMs) * timeStep;
  const labelTimeSkip = Math.max(1, Math.ceil(labelPxW / pxPerStep));

  let labelIdx = 0;
  for (let t = firstTimeTick; t <= xEndMs; t += timeStep) {
    const gx = tToX(t, layout);
    if (gx < marginL + 5 || gx > W - ladderW - 5) { labelIdx++; continue; }

    if (labelIdx % labelTimeSkip === 0) {
      const d = new Date(t);
      const label = showSeconds
        ? d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
        : d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });

      const isMajor = Math.abs(t % majorTimeStep) < timeStep / 2;
      ctx.fillStyle = isMajor ? '#8888a0' : '#5a5a72';
      ctx.save();
      ctx.translate(gx, timeLabelTop + 3 * dpr);
      ctx.rotate(rotAngle);
      ctx.textAlign = 'right';
      ctx.textBaseline = 'top';
      ctx.fillText(label, 0, 0);
      ctx.restore();
    }
    labelIdx++;
  }

  // Volume bars at bottom
  const barBuckets: Record<number, { buy: number; sell: number }> = {};
  for (const c of visible) {
    const bucketMs = Math.floor(c._ms! / (aggSeconds * 1000)) * (aggSeconds * 1000);
    if (!barBuckets[bucketMs]) barBuckets[bucketMs] = { buy: 0, sell: 0 };
    barBuckets[bucketMs].buy += c.buy_vol;
    barBuckets[bucketMs].sell += c.sell_vol;
  }
  const barMaxVol = Math.max(...Object.values(barBuckets).map((b) => b.buy + b.sell), 1);
  const barW = Math.max(1, (plotW / (windowMs / (aggSeconds * 1000))) * 0.7);

  // Volume scale labels
  ctx.font = `${7 * dpr}px ${COLORS.fontFamily}`;
  ctx.textAlign = 'right';
  ctx.fillStyle = '#52526a';
  for (let i = 0; i <= 4; i++) {
    const volVal = Math.round((barMaxVol / 4) * i);
    const vy = volTop + volH - (i / 4) * volH;
    ctx.fillText(fmtVol(volVal), marginL - 6 * dpr, vy);
    ctx.strokeStyle = 'rgba(255,255,255,0.03)';
    ctx.beginPath(); ctx.moveTo(marginL, vy); ctx.lineTo(W - ladderW, vy); ctx.stroke();
  }

  // Clip and draw volume bars
  ctx.save();
  ctx.beginPath();
  ctx.rect(marginL - 1, volTop, plotW + 2, volH + 4 * dpr);
  ctx.clip();

  for (const [msStr, b] of Object.entries(barBuckets)) {
    const x = tToX(parseInt(msStr), layout);
    if (x < marginL || x > W - ladderW) continue;
    const totalH = ((b.buy + b.sell) / barMaxVol) * volH;
    const buyH = totalH * (b.buy / (b.buy + b.sell || 1));
    const sellH = totalH - buyH;
    ctx.fillStyle = 'rgba(38,166,154,0.7)';
    ctx.fillRect(x - barW / 2, volTop + volH - totalH, barW, buyH);
    ctx.fillStyle = 'rgba(239,83,80,0.7)';
    ctx.fillRect(x - barW / 2, volTop + volH - sellH, barW, sellH);
  }

  ctx.restore();

  // Divergence indicator
  if (visible.length >= 3) {
    let cumDelta = 0;
    const cvd: number[] = [];
    for (const c of visible) {
      cumDelta += c.delta;
      cvd.push(cumDelta);
    }
    const cutoff = Math.max(0, Math.floor(visible.length * 0.7));
    const recentPrices = visible.slice(cutoff).map((c) => c.price);
    const recentCVD = cvd.slice(cutoff);

    if (recentPrices.length >= 2 && recentCVD.length >= 2) {
      const priceSlope = recentPrices[recentPrices.length - 1] - recentPrices[0];
      const cvdSlope = recentCVD[recentCVD.length - 1] - recentCVD[0];

      const isBearishDiv = priceSlope > 0 && cvdSlope < 0;
      const isBullishDiv = priceSlope < 0 && cvdSlope > 0;

      if (isBearishDiv || isBullishDiv) {
        const bW = 60 * dpr;
        const bH = 12 * dpr;
        const bX = marginL + 8 * dpr;
        const bY = marginT + 5 * dpr;
        const col = isBullishDiv ? COLORS.positive : COLORS.negative;
        const label = isBullishDiv ? 'BULL DIV' : 'BEAR DIV';

        ctx.fillStyle = col;
        ctx.globalAlpha = 0.55;
        ctx.fillRect(bX, bY, bW, bH);
        ctx.globalAlpha = 1.0;

        ctx.fillStyle = col;
        ctx.font = `${10 * dpr}px ${COLORS.fontFamily}`;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(label, bX + 4 * dpr, bY + bH / 2);
      }
    }
  }
}

/**
 * Draw the flowing trail line + compute bubble points for the PixiJS layer.
 */
export function computeBubblePoints(
  layout: FlowLayout,
  cells: FlowCloudCell[],
  aggSeconds: number,
  fullScreen: boolean
): BubblePoint[] {
  const { dpr, plotW, xStartMs, windowMs, marginL, ladderW, W } = layout;
  const visible = cells.filter((c) => c._ms! >= xStartMs);
  if (!visible.length) return [];

  // Dynamic volume-to-radius using data percentiles (log-like scaling)
  const allVols = visible.map((c) => c.total_vol || c.buy_vol + c.sell_vol).filter((v) => v > 0).sort((a, b) => a - b);
  const p20 = allVols[Math.floor(allVols.length * 0.2)] || 1;
  const p50 = allVols[Math.floor(allVols.length * 0.5)] || 10;
  const p80 = allVols[Math.floor(allVols.length * 0.8)] || 100;
  const p95 = allVols[Math.floor(allVols.length * 0.95)] || 1000;

  const aggScale = Math.max(aggSeconds, 0.01);
  const numBuckets = windowMs / (aggScale * 1000);
  const pxPerBubble = plotW / Math.max(numBuckets, 1);
  const minR = Math.max(4 * dpr, pxPerBubble * 0.55);
  const maxR = Math.max(minR * 3.5, (fullScreen ? 28 : 24) * dpr);

  function volToRadius(vol: number): number {
    if (vol <= p20) return minR;
    if (vol <= p50) return minR + ((vol - p20) / (p50 - p20 || 1)) * minR * 0.5;
    if (vol <= p80) return minR * 1.5 + ((vol - p50) / (p80 - p50 || 1)) * minR;
    if (vol <= p95) return minR * 2.5 + ((vol - p80) / (p95 - p80 || 1)) * minR;
    return minR * 3.5 + Math.min(1, (vol - p95) / (p95 * 2 || 1)) * (maxR - minR * 3.5);
  }

  return visible
    .map((c) => {
      const x = tToX(c._ms!, layout);
      const y = pToY(c.price, layout);
      const r = volToRadius(c.total_vol || c.buy_vol + c.sell_vol);
      const age = (c._ms! - xStartMs) / windowMs;
      const opacity = Math.max(0.15, Math.min(0.95, 0.15 + age * 0.8));
      const totalVol = c.buy_vol + c.sell_vol;
      const deltaRatio = totalVol > 0 ? c.delta / totalVol : 0;
      return { x, y, r, tMs: c._ms!, opacity, deltaRatio };
    })
    .filter((p) => p.x >= marginL - 30 && p.x <= W - ladderW + 30);
}

/**
 * Draw subtle shadow trail connecting bubble positions.
 */
export function drawTrail(
  ctx: CanvasRenderingContext2D,
  points: BubblePoint[],
  dpr: number,
  minR: number
): void {
  if (points.length < 2) return;

  const shadowW = Math.max(2 * dpr, minR * 0.4);
  ctx.globalAlpha = 0.08;
  ctx.lineWidth = shadowW;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.strokeStyle = 'rgba(255,255,255,0.15)';
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let i = 1; i < points.length; i++) {
    ctx.lineTo(points[i].x, points[i].y);
  }
  ctx.stroke();
  ctx.globalAlpha = 1.0;
}
