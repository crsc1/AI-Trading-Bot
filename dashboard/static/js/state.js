// ══════════════════════════════════════════════════════════════════════════
// STATE
// ══════════════════════════════════════════════════════════════════════════
const S = {
  sym: 'SPY',
  ws: null, connected: false, ticks: 0,
  signals: [], maxSignals: 50,
  lastPrice: null, prevClose: null,
  activeTab: 'combined',
  barMinutes: 5,
  tf: '1D',
  // Live candle building from engine ticks
  liveCandles: new Map(),
  liveInterval: 60,
  // Flow aggregation (seconds)
  flowAggSeconds: 5,
  // Indicators
  ind: { ema: false, sma: false, bb: false, vwap: false, vwapBands: false, levels: false, gex: false, pivots: false },
  // Drawing
  drawMode: null, drawClicks: [],
  drawings: [], drawIdCounter: 0,
  // Order flow data cache
  flowData: null,
  // Markers
  markers: [],
};

// ══════════════════════════════════════════════════════════════════════════
// CHART INSTANCES
// ══════════════════════════════════════════════════════════════════════════
// Combined tab (stacked)
let combCandleChart, combCandleS, combVolS;
let combRsiChart, combRsiS;
// Full candle tab
let fullCandleChart, fullCandleS, fullVolS, fullEmaS, fullSmaS, fullBbUpperS, fullBbLowerS, fullVwapS;
let fullLuldUpS, fullLuldDownS;  // LULD band series
// Overlay series — VWAP bands, session levels, GEX, pivots
let fullVwapUp1S, fullVwapDn1S, fullVwapUp2S, fullVwapDn2S, fullVwapUp3S, fullVwapDn3S;
let _overlayPriceLines = [];  // Active price lines for levels/gex/pivots
let _overlayLevelsData = null; // Cached levels data from /api/signals/levels
let _overlayGexData = null;    // Cached GEX data from /api/signals/gex
let fullRsiChart, fullRsiS;
let fullCvdChart, fullCvdS;
// Per-group sync flags to prevent cross-chart deadlocks
const _syncFlags = { combined: false, full: false };

const chartOpts = (typeof LightweightCharts !== 'undefined') ? {
  layout:{background:{color:T.surface0},textColor:T.dim,fontSize:T.fontBase},
  grid:{vertLines:{color:T.borderSubtle},horzLines:{color:T.borderSubtle}},
  crosshair:{mode:LightweightCharts.CrosshairMode.Normal,vertLine:{color:'rgba(85,136,238,.2)',width:1},horzLine:{color:'rgba(85,136,238,.2)',width:1}},
  rightPriceScale:{borderColor:T.border},
  timeScale:{
    borderColor:T.border,timeVisible:true,secondsVisible:false,
    // No tickMarkFormatter needed — data is shifted to "ET as UTC" so LWC
    // naturally places ticks at ET-aligned boundaries (09:30, 10:00 …).
  },
  localization:{
    // Data is shifted to "ET as UTC" — use getUTC* to read the ET time directly
    timeFormatter: (ts) => {
      const d = new Date(ts * 1000);
      const hh = String(d.getUTCHours()).padStart(2,'0');
      const mm = String(d.getUTCMinutes()).padStart(2,'0');
      return hh + ':' + mm;
    },
    dateFormatter: (ts) => {
      const d = new Date(ts * 1000);
      const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      return months[d.getUTCMonth()] + ' ' + d.getUTCDate();
    },
  },
  handleScroll:true,handleScale:true,autoSize:true,
} : {};
