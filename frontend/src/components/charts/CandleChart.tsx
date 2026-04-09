/**
 * CandleChart — Direct lightweight-charts integration (no wrapper).
 *
 * Uses LWC v5 native multi-pane: candles in pane 0, volume in pane 1.
 * The chart handles separator rendering, crosshair sync, and scroll sync
 * automatically. No CSS hacks needed.
 */
import { type Component, createEffect, createSignal, on, Show, onMount, onCleanup } from 'solid-js';
import {
  createChart, createSeriesMarkers, CandlestickSeries, LineSeries, HistogramSeries,
  type IChartApi, type ISeriesApi, type ISeriesMarkersPluginApi, type Time, type CandlestickData,
  type HistogramData, type LineData, type SeriesMarker, type MouseEventParams,
} from 'lightweight-charts';
import { market } from '../../signals/market';
import { signals } from '../../signals/signals';
import { chartTheme } from '../../lib/theme';
import { calcVWAP, calcVWAPBands, calcPrevDayVWAP, calcBB, calcAAVWAP, calcBB_RH, calcAlligator_RH, calcFOSC_RH, calcHV_RH, calcIV, calcVolumeProfile, calcSessionVolumeProfile } from '../../lib/indicators';
import { optionsFlow } from '../../signals/optionsFlow';
import type { Candle } from '../../types/market';
import { ChartControls, getIndicatorColor } from './ChartControls';
import { ChartLegend } from './ChartLegend';
import { findIndicator } from '../../lib/indicatorRegistry';

// ET session boundaries in seconds from midnight UTC
// Market open: 9:30 AM ET = 13:30 UTC (EST+5) or 13:30 UTC (EDT+4)
// We compute per-bar since DST shifts

/**
 * Get the ET offset in seconds for a given UTC timestamp.
 * Handles EST (-5h) vs EDT (-4h) automatically.
 */
function getETOffset(unixSec: number): number {
  const d = new Date(unixSec * 1000);
  // Compare UTC hour with ET hour to determine offset
  const utcH = d.getUTCHours();
  const etStr = d.toLocaleString('en-US', { timeZone: 'America/New_York', hour12: false, hour: '2-digit' });
  const etH = parseInt(etStr);
  let diff = etH - utcH;
  if (diff > 12) diff -= 24;
  if (diff < -12) diff += 24;
  return diff * 3600;
}

/** Convert UTC unix timestamp to "ET-shifted" timestamp for LWC display */
function toETTime(unixSec: number): number {
  if (!unixSec || !isFinite(unixSec)) return unixSec;
  return unixSec + getETOffset(unixSec);
}

/** Get ET hour and minute from a unix timestamp */
function getETHourMin(unixSec: number): { h: number; m: number } {
  const d = new Date(unixSec * 1000);
  const etStr = d.toLocaleString('en-US', { timeZone: 'America/New_York', hour12: false, hour: '2-digit', minute: '2-digit' });
  const [h, m] = etStr.split(':').map(Number);
  return { h, m };
}

/** Check if a unix timestamp falls within RTH (9:30 AM - 4:00 PM ET) */
function isRTH(unixSec: number): boolean {
  const { h, m } = getETHourMin(unixSec);
  const totalMin = h * 60 + m;
  return totalMin >= 570 && totalMin < 960; // 9:30=570, 16:00=960
}

function toCandlestick(c: Candle): CandlestickData<Time> & { color?: string; wickColor?: string; borderColor?: string } {
  const rth = isRTH(c.time);
  const up = c.close >= c.open;
  return {
    time: toETTime(c.time) as Time,
    open: c.open, high: c.high, low: c.low, close: c.close,
    color: rth ? (up ? chartTheme.upColor : chartTheme.downColor) : (up ? chartTheme.extUpColor : chartTheme.extDownColor),
    wickColor: rth ? (up ? chartTheme.upWickColor : chartTheme.downWickColor) : (up ? chartTheme.extUpWickColor : chartTheme.extDownWickColor),
    borderColor: rth ? (up ? chartTheme.upColor : chartTheme.downColor) : (up ? chartTheme.extUpColor : chartTheme.extDownColor),
  };
}
function toVolume(c: Candle): HistogramData<Time> {
  const rth = isRTH(c.time);
  const up = c.close >= c.open;
  return {
    time: toETTime(c.time) as Time,
    value: c.volume,
    color: rth ? (up ? chartTheme.volumeUp : chartTheme.volumeDown) : (up ? chartTheme.extVolumeUp : chartTheme.extVolumeDown),
  };
}

/** Find session boundary timestamps (9:30 AM and 4:00 PM ET) within a set of candles */
function findSessionBoundaries(candles: Candle[]): { opens: number[]; closes: number[] } {
  const opens: number[] = [];
  const closes: number[] = [];
  const seen = new Set<string>();

  for (const c of candles) {
    const d = new Date(c.time * 1000);
    const dateStr = d.toLocaleDateString('en-US', { timeZone: 'America/New_York' });
    const { h, m } = getETHourMin(c.time);
    const totalMin = h * 60 + m;

    const openKey = `open-${dateStr}`;
    const closeKey = `close-${dateStr}`;

    // Market open at 9:30 — find the bar closest to it
    if (totalMin >= 570 && totalMin <= 575 && !seen.has(openKey)) {
      opens.push(toETTime(c.time));
      seen.add(openKey);
    }
    // Market close at 16:00 — find the bar closest to it
    if (totalMin >= 955 && totalMin <= 960 && !seen.has(closeKey)) {
      closes.push(toETTime(c.time));
      seen.add(closeKey);
    }
  }
  return { opens, closes };
}
function toLineData(data: { time: number; value: number }[]): LineData<Time>[] {
  return data.map(d => ({ time: toETTime(d.time) as Time, value: d.value }));
}

export const CandleChart: Component = () => {
  let containerRef: HTMLDivElement | undefined;
  let chart: IChartApi | undefined;
  let candleSeries: ISeriesApi<'Candlestick'> | undefined;
  let volumeSeries: ISeriesApi<'Histogram'> | undefined;
  let overlaySeries: ISeriesApi<any>[] = [];
  let markersPlugin: ISeriesMarkersPluginApi<Time> | undefined;
  let dataLoaded = false;
  let lastBarCount = 0;

  const savedIds = (() => {
    try {
      const stored = localStorage.getItem('chart-indicators');
      if (stored) return new Set<string>(JSON.parse(stored));
    } catch {}
    return new Set<string>();
  })();
  const [activeIds, setActiveIds] = createSignal<Set<string>>(savedIds);
  const [priceScaleMode, setPriceScaleMode] = createSignal(
    (() => { try { return parseInt(localStorage.getItem('chart-price-scale') || '0'); } catch { return 0; } })()
  );
  const [crosshairData, setCrosshairData] = createSignal<string | null>(null);

  const toggleIndicator = (id: string) => {
    setActiveIds(prev => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      try { localStorage.setItem('chart-indicators', JSON.stringify([...n])); } catch {}
      return n;
    });
  };
  const cyclePriceScale = () => {
    const next = (priceScaleMode() + 1) % 3;
    setPriceScaleMode(next);
    chart?.priceScale('right').applyOptions({ mode: next });
    try { localStorage.setItem('chart-price-scale', String(next)); } catch {}
  };

  // ── Create chart once on mount ───────────────────────────────────────

  onMount(() => {
    if (!containerRef) return;

    chart = createChart(containerRef, {
      autoSize: true,
      layout: {
        background: { color: chartTheme.background },
        textColor: chartTheme.textColor,
        fontFamily: chartTheme.fontFamily,
        fontSize: 10,
      },
      grid: {
        vertLines: { color: chartTheme.gridColor },
        horzLines: { color: chartTheme.gridColor },
      },
      crosshair: {
        mode: 0,
        vertLine: { color: chartTheme.crosshairColor, width: 1, style: 3 },
        horzLine: { color: chartTheme.crosshairColor, width: 1, style: 3 },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: chartTheme.gridColor,
        rightOffset: 5,
        barSpacing: 8,
        minBarSpacing: 4,
        shiftVisibleRangeOnNewBar: false,
        lockVisibleTimeRangeOnResize: true,
      },
      rightPriceScale: {
        borderColor: chartTheme.gridColor,
        minimumWidth: 65,
      },
    });

    // ── Pane 0: Price candles ────────────────────────────────────────
    candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: chartTheme.upColor,
      downColor: chartTheme.downColor,
      wickUpColor: chartTheme.upWickColor,
      wickDownColor: chartTheme.downWickColor,
      borderVisible: false,
    });

    // ── Pane 1: Volume bars (separate pane via third argument) ───────
    volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      lastValueVisible: false,
      priceLineVisible: false,
    }, 1);

    // Set pane sizes: 80% price, 20% volume
    const panes = chart.panes();
    if (panes.length >= 2) {
      panes[0].setStretchFactor(0.8);
      panes[1].setStretchFactor(0.2);
    }

    // Crosshair handler
    let lastCH = 0;
    chart.subscribeCrosshairMove((param: MouseEventParams<Time>) => {
      if (!param.time || !param.point) { setCrosshairData(null); return; }
      const now = performance.now();
      if (now - lastCH < 100) return;
      lastCH = now;
      const t = param.time as number;
      const c = market.candles.find(c => toETTime(c.time) === t);
      if (c) setCrosshairData(`O ${c.open.toFixed(2)}  H ${c.high.toFixed(2)}  L ${c.low.toFixed(2)}  C ${c.close.toFixed(2)}  V ${(c.volume / 1000).toFixed(0)}K`);
    });

    // Load data if already available
    loadInitialData();
  });

  onCleanup(() => {
    if (chart) { chart.remove(); chart = undefined; }
    candleSeries = undefined;
    volumeSeries = undefined;
    overlaySeries = [];
  });

  // ── Load initial historical data (called once) ───────────────────────

  function loadInitialData() {
    if (dataLoaded || !candleSeries || !volumeSeries) return;
    const candles = market.candles;
    if (candles.length === 0) return;

    candleSeries.setData(candles.map(toCandlestick));
    volumeSeries.setData(candles.map(toVolume));
    lastBarCount = candles.length;
    dataLoaded = true;

    // Fit visible range to today's session (from 9:30 AM ET open)
    fitToTodaySession(candles);

    // Set signal markers (includes session boundaries)
    updateMarkers();
    // Build overlay indicators
    rebuildIndicators();
  }

  /** Fit visible range to today's RTH session (9:30 AM ET) with some pre-market context */
  function fitToTodaySession(candles: Candle[]) {
    if (!chart || candles.length === 0) return;

    // Find today's 9:00 AM ET bar (30 min before open for context)
    const now = new Date();
    const todayStr = now.toLocaleDateString('en-US', { timeZone: 'America/New_York' });

    let sessionStart = -1;
    for (let i = candles.length - 1; i >= 0; i--) {
      const d = new Date(candles[i].time * 1000);
      const dayStr = d.toLocaleDateString('en-US', { timeZone: 'America/New_York' });
      if (dayStr !== todayStr) break;
      const { h } = getETHourMin(candles[i].time);
      if (h >= 9) sessionStart = i;
    }

    if (sessionStart >= 0) {
      // Show from 30 min before session start (or session start if no pre-market)
      const fromIdx = Math.max(0, sessionStart - 6); // 6 bars * 5min = 30 min
      const fromTime = toETTime(candles[fromIdx].time) as Time;
      const toTime = toETTime(candles[candles.length - 1].time) as Time;
      chart.timeScale().setVisibleRange({ from: fromTime, to: toTime });
    }
  }

  // ── React to candles arriving (for initial load timing) ──────────────

  createEffect(on(
    () => market.candles.length,
    (len) => {
      if (!dataLoaded) { loadInitialData(); return; }
      // New bar appended
      if (len > lastBarCount && candleSeries && volumeSeries) {
        const c = market.candles[len - 1];
        candleSeries.update(toCandlestick(c));
        volumeSeries.update(toVolume(c));
        lastBarCount = len;
        scheduleIndicatorRebuild();
      }
    }
  ));

  // ── Live tick update: 1 per animation frame ──────────────────────────

  let rafPending = false;
  createEffect(on(
    () => market.lastPrice,
    () => {
      if (!dataLoaded) { loadInitialData(); return; }
      if (rafPending) return;
      rafPending = true;
      requestAnimationFrame(() => {
        rafPending = false;
        const c = market.currentCandle;
        if (!c || !candleSeries) return;
        candleSeries.update(toCandlestick(c));
        volumeSeries?.update(toVolume(c));
      });
    }
  ));

  // ── Signal markers ───────────────────────────────────────────────────

  function updateMarkers() {
    if (!candleSeries) return;
    const allMarkers: SeriesMarker<Time>[] = [];

    // Signal markers
    const hist = signals.history;
    if (hist && hist.length > 0) {
      for (const s of hist.filter(s => s.action !== 'NO_TRADE' && s.timestamp).slice(0, 50)) {
        const rawTs = Math.floor(new Date(s.timestamp).getTime() / 1000);
        const ts = toETTime(rawTs) as Time;
        const isBuy = s.action === 'BUY_CALL';
        allMarkers.push({
          time: ts,
          position: isBuy ? 'belowBar' as const : 'aboveBar' as const,
          color: isBuy ? '#00C805' : '#FF5000',
          shape: isBuy ? 'arrowUp' as const : 'arrowDown' as const,
          text: `${isBuy ? 'CALL' : 'PUT'} $${s.strike}`,
        });
      }
    }

    // Session boundary markers
    const sessionMarkers = getSessionMarkers(market.candles);
    allMarkers.push(...sessionMarkers);

    // Sort by time (required by LWC)
    allMarkers.sort((a, b) => (a.time as number) - (b.time as number));

    // LWC v5: use createSeriesMarkers plugin instead of series.setMarkers()
    if (markersPlugin) {
      markersPlugin.setMarkers(allMarkers);
    } else {
      markersPlugin = createSeriesMarkers(candleSeries, allMarkers);
    }
  }

  // ── Session boundary lines ───────────────────────────────────────────

  /** Build session boundary markers to merge into the candle series markers */
  function getSessionMarkers(candles: Candle[]): SeriesMarker<Time>[] {
    const { opens, closes } = findSessionBoundaries(candles);
    const markers: SeriesMarker<Time>[] = [];

    for (const t of opens) {
      markers.push({
        time: t as Time,
        position: 'aboveBar',
        color: 'rgba(88,136,238,0.6)',
        shape: 'square',
        text: '9:30 OPEN',
      });
    }
    for (const t of closes) {
      markers.push({
        time: t as Time,
        position: 'aboveBar',
        color: 'rgba(88,136,238,0.6)',
        shape: 'square',
        text: '4:00 CLOSE',
      });
    }
    return markers;
  }

  // ── Overlay indicators (imperative) ──────────────────────────────────

  let rebuildTimer: ReturnType<typeof setTimeout> | null = null;
  function scheduleIndicatorRebuild() {
    if (rebuildTimer) return;
    rebuildTimer = setTimeout(() => { rebuildTimer = null; rebuildIndicators(); }, 1000);
  }
  onCleanup(() => { if (rebuildTimer) clearTimeout(rebuildTimer); });

  // Rebuild when active indicator set changes
  createEffect(on(() => [...activeIds()].sort().join(','), () => rebuildIndicators()));

  function rebuildIndicators() {
    if (!chart || market.candles.length === 0) return;
    const candles = market.candles;

    // Remove old
    for (const s of overlaySeries) { try { chart.removeSeries(s); } catch {} }
    overlaySeries = [];

    for (const id of activeIds()) {
      if (id === 'net-delta') continue;
      let plots: { data: LineData<Time>[]; color: string; style: number; width: number; label?: boolean }[] = [];

      if (id === 'vwap') {
        plots = [{ data: toLineData(calcVWAP(candles)), color: '#00e5ff', style: 0, width: 2, label: true }];
      } else if (id === 'vwap-bands') {
        const vb = calcVWAPBands(candles);
        plots = [
          { data: toLineData(vb.vwap), color: '#00e5ff', style: 0, width: 2, label: true },
          { data: toLineData(vb.upper1), color: '#42a5f5', style: 2, width: 1, label: true },
          { data: toLineData(vb.lower1), color: '#42a5f5', style: 2, width: 1, label: true },
          { data: toLineData(vb.upper2), color: '#7e57c2', style: 3, width: 1, label: true },
          { data: toLineData(vb.lower2), color: '#7e57c2', style: 3, width: 1, label: true },
        ];
      } else if (id === 'prev-day-vwap') {
        const pv = calcPrevDayVWAP(candles);
        if (pv) {
          const lineData = candles
            .filter(c => c.time >= pv.startTime)
            .map(c => ({ time: c.time, value: pv.value }));
          plots = [{ data: toLineData(lineData), color: '#ffb300', style: 2, width: 2, label: true }];
        }
      } else if (id === 'aavwap') {
        plots = [{ data: toLineData(calcAAVWAP(candles, 10)), color: '#e040fb', style: 0, width: 2, label: true }];
      } else if (id === 'bollinger-bands') {
        const bb = calcBB(candles, 20, 2);
        plots = [
          { data: toLineData(bb.upper), color: 'rgba(66,165,245,0.4)', style: 2, width: 1 },
          { data: toLineData(bb.lower), color: 'rgba(66,165,245,0.4)', style: 2, width: 1 },
        ];
      } else if (id === 'bb-rh') {
        const bb = calcBB_RH(candles, 20, 2);
        plots = [
          { data: toLineData(bb.basis), color: 'rgba(255,183,77,0.6)', style: 0, width: 1 },
          { data: toLineData(bb.upper), color: 'rgba(255,183,77,0.4)', style: 2, width: 1 },
          { data: toLineData(bb.lower), color: 'rgba(255,183,77,0.4)', style: 2, width: 1 },
        ];
      } else if (id === 'alligator-rh') {
        const al = calcAlligator_RH(candles);
        plots = [
          { data: toLineData(al.jaw), color: '#42a5f5', style: 0, width: 2 },   // Jaw = blue
          { data: toLineData(al.teeth), color: '#ef5350', style: 0, width: 1 },  // Teeth = red
          { data: toLineData(al.lips), color: '#66bb6a', style: 0, width: 1 },   // Lips = green
        ];
      } else if (id === 'fosc-rh') {
        const data = calcFOSC_RH(candles, 14);
        plots = [{ data: toLineData(data), color: '#ab47bc', style: 0, width: 1 }];
      } else if (id === 'hv-rh') {
        const data = calcHV_RH(candles, 20);
        plots = [{ data: toLineData(data), color: '#ff7043', style: 0, width: 1 }];
      } else if (id === 'implied-vol') {
        const ivResult = calcIV(candles, optionsFlow.trades);
        const ivData = ivResult.plots['IV'] ?? [];
        if (ivData.length > 0) {
          plots = [{ data: toLineData(ivData), color: '#e040fb', style: 0, width: 2 }];
        }
      } else if (id === 'vol-profile' || id === 'session-vp') {
        const vp = id === 'session-vp' ? calcSessionVolumeProfile(candles) : calcVolumeProfile(candles);
        if (vp) {
          // Draw POC + VAH + VAL as horizontal lines across all candles
          const lineCandles = candles.filter(c => c.time >= vp.startTime);
          const pocLine = lineCandles.map(c => ({ time: c.time, value: vp.poc }));
          const vahLine = lineCandles.map(c => ({ time: c.time, value: vp.vah }));
          const valLine = lineCandles.map(c => ({ time: c.time, value: vp.val }));
          plots = [
            { data: toLineData(pocLine), color: '#ffd600', style: 0, width: 2, label: true },  // POC = gold
            { data: toLineData(vahLine), color: 'rgba(255,214,0,0.4)', style: 2, width: 1, label: true }, // VAH = dim gold
            { data: toLineData(valLine), color: 'rgba(255,214,0,0.4)', style: 2, width: 1, label: true }, // VAL = dim gold
          ];
        }
      } else {
        const info = findIndicator(id);
        if (!info || !info.overlay) continue;
        try {
          const result = info.module.calculate(candles);
          if (!result?.plots) continue;
          const baseColor = getIndicatorColor(id);
          let pi = 0;
          for (const [, pd] of Object.entries(result.plots)) {
            const arr = (pd as any[]).filter(d => d.value != null && isFinite(d.value));
            if (arr.length === 0) continue;
            plots.push({ data: toLineData(arr), color: pi === 0 ? baseColor : shiftHue(baseColor, pi * 40), style: pi > 0 ? 2 : 0, width: 1 });
            pi++;
          }
        } catch { continue; }
      }

      for (const p of plots) {
        const showLabel = (p as any).label === true;
        const s = chart.addSeries(LineSeries, {
          color: p.color, lineWidth: p.width as any, lineStyle: p.style,
          crosshairMarkerVisible: false,
          lastValueVisible: showLabel,
          priceLineVisible: showLabel,
          priceLineStyle: p.style || 0,
          priceLineColor: p.color,
        });
        s.setData(p.data as any);
        overlaySeries.push(s);
      }
    }
  }

  return (
    <div class="flex flex-col h-full min-h-0">
      <ChartControls indicators={activeIds()} onToggle={toggleIndicator}
        priceScaleMode={priceScaleMode()} onCyclePriceScale={cyclePriceScale} />

      <div class="flex-1 min-h-0 relative overflow-hidden">
        <ChartLegend indicators={activeIds()} onRemove={toggleIndicator} />
        <Show when={crosshairData()}>
          <div class="absolute top-2 right-16 z-10 px-2 py-1 rounded bg-surface-0/80 pointer-events-none" style={{ "min-width": "320px" }}>
            <span class="font-data text-[10px] text-text-secondary tabular-nums">{crosshairData()}</span>
          </div>
        </Show>

        <div ref={containerRef} class="w-full h-full" />
      </div>
    </div>
  );
};

function shiftHue(hex: string, deg: number): string {
  const r = parseInt(hex.slice(1, 3), 16) / 255, g = parseInt(hex.slice(3, 5), 16) / 255, b = parseInt(hex.slice(5, 7), 16) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
  let h = 0, s = 0; const l = (mx + mn) / 2;
  if (mx !== mn) { const d = mx - mn; s = l > .5 ? d / (2 - mx - mn) : d / (mx + mn); if (mx === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6; else if (mx === g) h = ((b - r) / d + 2) / 6; else h = ((r - g) / d + 4) / 6; }
  h = ((h * 360 + deg) % 360) / 360; if (h < 0) h += 1;
  const h2r = (p: number, q: number, t: number) => { if (t < 0) t += 1; if (t > 1) t -= 1; if (t < 1 / 6) return p + (q - p) * 6 * t; if (t < 1 / 2) return q; if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6; return p; };
  const q = l < .5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
  return `#${Math.round(h2r(p, q, h + 1 / 3) * 255).toString(16).padStart(2, '0')}${Math.round(h2r(p, q, h) * 255).toString(16).padStart(2, '0')}${Math.round(h2r(p, q, h - 1 / 3) * 255).toString(16).padStart(2, '0')}`;
}
