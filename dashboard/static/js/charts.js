// SESSION OVERLAY — ET timezone session backgrounds on candle charts
// Pre-market 04:00–09:30 ET (blue tint), RTH open/close dashed lines,
// After-hours 16:00–20:00 ET (amber tint). Canvas appended after LWC
// canvases so DOM order puts overlay on top; pointer-events:none passes through.
// ══════════════════════════════════════════════════════════════════════════
function _getETSessionBounds(shiftedSec) {
  // Data is already shifted to "ET as UTC" space, so we use getUTC* directly.
  const d = new Date(shiftedSec * 1000);
  const yr = d.getUTCFullYear(), mo = d.getUTCMonth(), dy = d.getUTCDate();
  return {
    preStart: Math.floor(Date.UTC(yr, mo, dy,  4,  0, 0) / 1000),
    rthStart: Math.floor(Date.UTC(yr, mo, dy,  9, 30, 0) / 1000),
    rthEnd:   Math.floor(Date.UTC(yr, mo, dy, 16,  0, 0) / 1000),
    ahEnd:    Math.floor(Date.UTC(yr, mo, dy, 20,  0, 0) / 1000),
  };
}

function _drawSessionBg(chart, canvas) {
  const el = canvas.parentElement;
  if (!el) return;
  const dpr = window.devicePixelRatio || 1;
  const w = el.offsetWidth, h = el.offsetHeight;
  if (w === 0 || h === 0) return;
  // Resize canvas only when dimensions change (avoids unnecessary GPU uploads)
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const ts = chart.timeScale();
  const range = ts.getVisibleRange();
  if (!range) return;
  // Helper: clamp timestamp → pixel X
  function secToX(sec) {
    if (sec <= range.from) return 0;
    if (sec >= range.to) return w;
    const x = ts.timeToCoordinate(sec);
    return x !== null ? x : (sec < range.from ? 0 : w);
  }
  // Session fill colors
  const PRE_FILL  = 'rgba(80, 90, 200, 0.08)';
  const AH_FILL   = 'rgba(190, 140, 30, 0.08)';
  const OPEN_CLR  = 'rgba(38, 166, 154, 0.55)'; // green dashed — 9:30 open
  const CLOSE_CLR = 'rgba(239, 83, 80, 0.55)';  // red dashed  — 16:00 close
  // Scan ET days covering the visible range + 2 day buffer each side
  let cursor = (Math.floor(range.from / 86400) - 2) * 86400;
  const scanEnd = range.to + 86400 * 2;
  while (cursor <= scanEnd) {
    const b = _getETSessionBounds(cursor + 43200); // noon UTC as day anchor
    // Skip weekends (check ET day name)
    const etDOW = new Date(b.rthStart * 1000).toLocaleDateString('en-US',{timeZone:'America/New_York',weekday:'short'});
    if (etDOW !== 'Sat' && etDOW !== 'Sun') {
      // Pre-market band
      const px1 = secToX(b.preStart), px2 = secToX(b.rthStart);
      if (px2 > px1 && px2 > 0 && px1 < w) {
        ctx.fillStyle = PRE_FILL;
        ctx.fillRect(px1, 0, px2 - px1, h);
      }
      // After-hours band
      const ax1 = secToX(b.rthEnd), ax2 = secToX(b.ahEnd);
      if (ax2 > ax1 && ax2 > 0 && ax1 < w) {
        ctx.fillStyle = AH_FILL;
        ctx.fillRect(ax1, 0, ax2 - ax1, h);
      }
      // 9:30 open line
      const ox = ts.timeToCoordinate(b.rthStart);
      if (ox !== null && ox >= 0 && ox <= w) {
        ctx.save();
        ctx.strokeStyle = OPEN_CLR; ctx.lineWidth = 1; ctx.setLineDash([3,3]);
        ctx.beginPath(); ctx.moveTo(ox, 0); ctx.lineTo(ox, h); ctx.stroke();
        ctx.restore();
      }
      // 16:00 close line
      const cx = ts.timeToCoordinate(b.rthEnd);
      if (cx !== null && cx >= 0 && cx <= w) {
        ctx.save();
        ctx.strokeStyle = CLOSE_CLR; ctx.lineWidth = 1; ctx.setLineDash([3,3]);
        ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, h); ctx.stroke();
        ctx.restore();
      }
    }
    cursor += 86400;
  }
}

let _sessionResizeObs = null;
function _initSessionOverlay(chartEl, chart) {
  const canvas = document.createElement('canvas');
  canvas.className = 'session-bg';
  // Appended AFTER LWC's internal divs — DOM order puts us on top.
  // pointer-events:none lets all mouse/crosshair events pass through to LWC.
  canvas.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:2;';
  chartEl.appendChild(canvas);
  const redraw = () => requestAnimationFrame(() => _drawSessionBg(chart, canvas));
  chart.timeScale().subscribeVisibleLogicalRangeChange(redraw);
  if (!_sessionResizeObs) _sessionResizeObs = new ResizeObserver(redraw);
  _sessionResizeObs.observe(chartEl);
  setTimeout(redraw, 200); // initial draw after LWC layout settles
}

function initCombinedCharts(){
  // Candle chart in combined tab
  combCandleChart = LightweightCharts.createChart(document.getElementById('candleWrapCombined'),{
    ...chartOpts, rightPriceScale:{...chartOpts.rightPriceScale,scaleMargins:{top:.05,bottom:.12}},
  });
  combCandleS = combCandleChart.addCandlestickSeries({upColor:T.positive,downColor:T.negative,borderUpColor:T.positive,borderDownColor:T.negative,wickUpColor:T.positive,wickDownColor:T.negative});
  combVolS = combCandleChart.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:''});
  combVolS.priceScale().applyOptions({scaleMargins:{top:.87,bottom:0}});

  // RSI in combined tab
  combRsiChart = LightweightCharts.createChart(document.getElementById('rsiWrapCombined'),{
    ...chartOpts, rightPriceScale:{...chartOpts.rightPriceScale,scaleMargins:{top:.05,bottom:.05}},
    timeScale:{...chartOpts.timeScale,visible:false},
  });
  combRsiS = combRsiChart.addLineSeries({color:T.rsi,lineWidth:1,priceLineVisible:false,lastValueVisible:true});
  combRsiS.createPriceLine({price:70,color:'rgba(239,83,80,.3)',lineWidth:1,lineStyle:2});
  combRsiS.createPriceLine({price:30,color:'rgba(38,166,154,.3)',lineWidth:1,lineStyle:2});

  // Sync combined candle + RSI timescales (per-group flag)
  [combCandleChart, combRsiChart].forEach((c,i,arr) => {
    c.timeScale().subscribeVisibleLogicalRangeChange(r => {
      if(_syncFlags.combined||!r) return; _syncFlags.combined=true;
      arr.forEach((oc,j)=>{if(i!==j) try{oc.timeScale().setVisibleLogicalRange(r)}catch(e){}});
      _syncFlags.combined=false;
    });
  });

  // OHLCV tooltip
  combCandleChart.subscribeCrosshairMove(param => showTooltip(param, combCandleS, combVolS, 'tooltipCombined', 'candleWrapCombined'));

  // Drawing clicks
  combCandleChart.subscribeClick(param => {
    if(!S.drawMode||!param.time||!param.point) return;
    handleDrawClick(param, combCandleS, combCandleChart);
  });

  // Session background overlay (ET timezone shading)
  _initSessionOverlay(document.getElementById('candleWrapCombined'), combCandleChart);
}

function initFullCandleCharts(){
  // Main candle chart (full tab)
  fullCandleChart = LightweightCharts.createChart(document.getElementById('candleWrapFull'),{
    ...chartOpts, rightPriceScale:{...chartOpts.rightPriceScale,scaleMargins:{top:.05,bottom:.12}},
  });
  fullCandleS = fullCandleChart.addCandlestickSeries({upColor:T.positive,downColor:T.negative,borderUpColor:T.positive,borderDownColor:T.negative,wickUpColor:T.positive,wickDownColor:T.negative});
  fullVolS = fullCandleChart.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:''});
  fullVolS.priceScale().applyOptions({scaleMargins:{top:.87,bottom:0}});

  // Indicators (full tab only)
  fullEmaS = fullCandleChart.addLineSeries({color:T.ema,lineWidth:1,visible:false,priceLineVisible:false,lastValueVisible:false});
  fullSmaS = fullCandleChart.addLineSeries({color:T.sma,lineWidth:1,visible:false,priceLineVisible:false,lastValueVisible:false});
  fullBbUpperS = fullCandleChart.addLineSeries({color:'rgba(156,39,176,.5)',lineWidth:1,visible:false,priceLineVisible:false,lastValueVisible:false});
  fullBbLowerS = fullCandleChart.addLineSeries({color:'rgba(156,39,176,.5)',lineWidth:1,visible:false,priceLineVisible:false,lastValueVisible:false});
  fullVwapS = fullCandleChart.addLineSeries({color:T.vwap,lineWidth:2,visible:false,priceLineVisible:false,lastValueVisible:false,lineStyle:0});

  // VWAP ±σ band overlays (hidden by default)
  const _vbandOpts = (c) => ({color:c,lineWidth:1,lineStyle:2,visible:false,priceLineVisible:false,lastValueVisible:false});
  fullVwapUp1S = fullCandleChart.addLineSeries(_vbandOpts('rgba(0,229,255,0.45)'));
  fullVwapDn1S = fullCandleChart.addLineSeries(_vbandOpts('rgba(0,229,255,0.45)'));
  fullVwapUp2S = fullCandleChart.addLineSeries(_vbandOpts('rgba(0,229,255,0.28)'));
  fullVwapDn2S = fullCandleChart.addLineSeries(_vbandOpts('rgba(0,229,255,0.28)'));
  fullVwapUp3S = fullCandleChart.addLineSeries(_vbandOpts('rgba(0,229,255,0.15)'));
  fullVwapDn3S = fullCandleChart.addLineSeries(_vbandOpts('rgba(0,229,255,0.15)'));

  // LULD bands (Limit Up / Limit Down) — always visible when data arrives
  fullLuldUpS = fullCandleChart.addLineSeries({color:'rgba(255,23,68,0.6)',lineWidth:1,lineStyle:2,visible:true,priceLineVisible:false,lastValueVisible:true,title:'LULD Up'});
  fullLuldDownS = fullCandleChart.addLineSeries({color:'rgba(0,230,118,0.6)',lineWidth:1,lineStyle:2,visible:true,priceLineVisible:false,lastValueVisible:true,title:'LULD Dn'});

  // RSI (full tab)
  fullRsiChart = LightweightCharts.createChart(document.getElementById('rsiWrapFull'),{
    ...chartOpts, rightPriceScale:{...chartOpts.rightPriceScale,scaleMargins:{top:.05,bottom:.05}},
    timeScale:{...chartOpts.timeScale,visible:false},
  });
  fullRsiS = fullRsiChart.addLineSeries({color:T.rsi,lineWidth:1,priceLineVisible:false,lastValueVisible:true});
  fullRsiS.createPriceLine({price:70,color:'rgba(239,83,80,.3)',lineWidth:1,lineStyle:2});
  fullRsiS.createPriceLine({price:30,color:'rgba(38,166,154,.3)',lineWidth:1,lineStyle:2});

  // CVD (full tab)
  fullCvdChart = LightweightCharts.createChart(document.getElementById('cvdWrapFull'),{
    ...chartOpts, rightPriceScale:{...chartOpts.rightPriceScale,scaleMargins:{top:.1,bottom:.1}},
    timeScale:{...chartOpts.timeScale,visible:false},
  });
  fullCvdS = fullCvdChart.addLineSeries({color:T.cvd,lineWidth:2,priceLineVisible:false,lastValueVisible:true});

  // Sync full tab charts (per-group flag)
  const fullCharts = [fullCandleChart, fullRsiChart, fullCvdChart];
  fullCharts.forEach((c,i) => {
    c.timeScale().subscribeVisibleLogicalRangeChange(r => {
      if(_syncFlags.full||!r) return; _syncFlags.full=true;
      fullCharts.forEach((oc,j)=>{if(i!==j) try{oc.timeScale().setVisibleLogicalRange(r)}catch(e){}});
      _syncFlags.full=false;
    });
  });

  // Tooltip + drawing for full tab
  fullCandleChart.subscribeCrosshairMove(param => showTooltip(param, fullCandleS, fullVolS, 'tooltipFull', 'candleWrapFull'));
  fullCandleChart.subscribeClick(param => {
    if(!S.drawMode||!param.time||!param.point) return;
    handleDrawClick(param, fullCandleS, fullCandleChart);
  });

  // Session background overlay (ET timezone shading)
  _initSessionOverlay(document.getElementById('candleWrapFull'), fullCandleChart);
}

// ══════════════════════════════════════════════════════════════════════════
// TOOLTIP (shared)
// ══════════════════════════════════════════════════════════════════════════
function showTooltip(param, candleSeries, volSeries, tipId, wrapId){
  const tip = document.getElementById(tipId);
  if(!param.time || !param.point){tip.style.display='none';return;}
  const d = param.seriesData.get(candleSeries);
  const v = param.seriesData.get(volSeries);
  if(!d){tip.style.display='none';return;}
  const col = d.close>=d.open?'var(--grn)':'var(--red)';
  // Data is shifted to "ET as UTC" — read ET time via getUTC*
  const _td = new Date(param.time * 1000);
  const barTime = String(_td.getUTCHours()).padStart(2,'0') + ':' + String(_td.getUTCMinutes()).padStart(2,'0');
  tip.innerHTML=`
    <div class="t-row" style="border-bottom:1px solid rgba(255,255,255,.06);padding-bottom:3px;margin-bottom:2px"><span class="t-k" style="color:var(--dim)">ET</span><span class="t-v" style="color:var(--mut)">${barTime}</span></div>
    <div class="t-row"><span class="t-k">O</span><span class="t-v" style="color:${col}">${d.open?.toFixed(2)}</span></div>
    <div class="t-row"><span class="t-k">H</span><span class="t-v" style="color:${col}">${d.high?.toFixed(2)}</span></div>
    <div class="t-row"><span class="t-k">L</span><span class="t-v" style="color:${col}">${d.low?.toFixed(2)}</span></div>
    <div class="t-row"><span class="t-k">C</span><span class="t-v" style="color:${col}">${d.close?.toFixed(2)}</span></div>
    <div class="t-row"><span class="t-k">Vol</span><span class="t-v">${formatVol(v?.value||0)}</span></div>`;
  tip.style.display='block';
  const wrap = document.getElementById(wrapId);
  const x = Math.min(param.point.x+12, wrap.clientWidth-120);
  tip.style.left=x+'px'; tip.style.top=(param.point.y-60)+'px';
}

// Apply stored candle visible range (called after data load AND tab switch)
function applyCandleVisibleRange(){
  const r = S._candleVisibleRange;
  if(!r) return;
  requestAnimationFrame(()=>{
    try{ combCandleChart.timeScale().setVisibleLogicalRange(r); }catch(e){}
    try{ fullCandleChart.timeScale().setVisibleLogicalRange(r); }catch(e){}
  });
}

// ══════════════════════════════════════════════════════════════════════════
// TAB SWITCHING
// ══════════════════════════════════════════════════════════════════════════
function setTab(tab){
  S.activeTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab===tab));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  const panelMap = {combined:'tabCombined', flow:'tabFlow', candles:'tabCandles', options:'tabOptions', agent:'tabAgent', replay:'tabReplay'};
  document.getElementById(panelMap[tab])?.classList.add('active');

  // Resize charts after tab switch — two passes:
  // 1. Immediate RAF: trigger autoSize now that panel is display:block
  // 2. Double RAF: apply visible range / fitContent after layout fully settles
  //    (two frames guarantees the browser has measured + painted the container)
  // The unified _chartResizeObs also fires via ResizeObserver as a safety net.
  requestAnimationFrame(()=>{
    _resizeAllVisibleCharts();  // Immediate — handles all chart types

    // Restore visible range after charts have measured their containers
    if(tab==='combined' || tab==='candles'){
      requestAnimationFrame(()=>{
        if(S._candleVisibleRange) applyCandleVisibleRange();
        else {
          if(tab==='combined') combCandleChart?.timeScale().fitContent();
          if(tab==='candles') fullCandleChart?.timeScale().fitContent();
        }
      });
    }
    if(tab==='options'){
      loadOptionsBoard();
    }
  });
}

// ══════════════════════════════════════════════════════════════════════════
// UNIFIED CHART RESIZE SYSTEM
// Handles: flow charts (Canvas 2D + PixiJS), Lightweight Charts (candle/RSI/CVD),
//          equity curve. Triggered by: window resize, sidebar drag, tab switch,
//          panel collapse/expand, any container dimension change.
// ══════════════════════════════════════════════════════════════════════════
var _chartResizeTimer = null;
var _loadHistoryInFlight = false;

function _resizeAllVisibleCharts(){
  if(_loadHistoryInFlight) return;  // Skip resize during active data load
  const tab = S.activeTab;

  // Lightweight Charts — use applyOptions({autoSize:true}) which re-measures container
  // NOTE: Do NOT call resize(0,0) first — that can leave charts stuck at zero if the
  // container isn't fully laid out yet. autoSize handles measurement internally.
  // Only resize charts whose containers are actually visible (offsetWidth > 0)
  if(tab === 'combined'){
    const cw = document.getElementById('candleWrapCombined');
    if(cw && cw.offsetWidth > 0){
      combCandleChart?.applyOptions({autoSize:true});
      combRsiChart?.applyOptions({autoSize:true});
    }
  }
  if(tab === 'candles'){
    const fw = document.getElementById('candleWrapFull');
    if(fw && fw.offsetWidth > 0){
      fullCandleChart?.applyOptions({autoSize:true});
      fullRsiChart?.applyOptions({autoSize:true});
      fullCvdChart?.applyOptions({autoSize:true});
    }
  }

  // Flow charts — re-render at new container size
  if(S.flowData){
    if(tab === 'combined') renderFlowChart('flowWrapCombined', S.flowData, false);
    if(tab === 'flow') renderFlowChart('flowWrapFull', S.flowData, true);
  }

  // Equity curve
  if(typeof _equityCurveChart !== 'undefined' && _equityCurveChart){
    _equityCurveChart.applyOptions({autoSize:true});
  }
}

// Single ResizeObserver for ALL chart containers — 50ms debounce (fast enough to catch
// panel opens, low enough to batch rapid sidebar drags)
const _chartResizeObs = new ResizeObserver(() => {
  clearTimeout(_chartResizeTimer);
  _chartResizeTimer = setTimeout(_resizeAllVisibleCharts, 50);
});

// Attach ResizeObserver after DOM ready
document.addEventListener('DOMContentLoaded', () => {
  // Flow containers
  const fc = document.getElementById('flowWrapCombined');
  const ff = document.getElementById('flowWrapFull');
  if(fc) _chartResizeObs.observe(fc);
  if(ff) _chartResizeObs.observe(ff);
  // Candle chart containers
  ['candleWrapCombined','rsiWrapCombined','candleWrapFull','rsiWrapFull','cvdWrapFull'].forEach(id => {
    const el = document.getElementById(id);
    if(el) _chartResizeObs.observe(el);
  });
  // Main content area (catches window resize, sidebar drag)
  const main = document.querySelector('.main-area') || document.querySelector('.app-main');
  if(main) _chartResizeObs.observe(main);
});

// ══════════════════════════════════════════════════════════════════════════
// FLOW SUB-TAB SWITCHING (Bubbles | Per-Price | Footprint)
// ══════════════════════════════════════════════════════════════════════════
let currentFlowView = 'bubbles';

function setFlowView(view){
  currentFlowView = view;
  // Update all sub-tab buttons across both Flow-Only and Combined panels
  document.querySelectorAll('.flow-sub-tab').forEach(b => {
    b.classList.toggle('active', b.dataset.flowview === view);
  });
  // Hide/show PixiJS bubble overlay based on view
  _togglePixiCanvases(view === 'bubbles');
  // Re-render the active flow chart with new view mode
  if(S.flowData){
    if(S.activeTab === 'combined') renderFlowChart('flowWrapCombined', S.flowData, false);
    if(S.activeTab === 'flow') renderFlowChart('flowWrapFull', S.flowData, true);
  }
  console.log(`[FlowView] Switched to: ${view}`);
}

// Hide or show all PixiJS WebGL canvases overlaying the flow charts
function _togglePixiCanvases(show){
  Object.values(flowRenderers).forEach(fr => {
    if(fr && fr.app && fr.app.canvas){
      fr.app.canvas.style.display = show ? '' : 'none';
    }
  });
}

// ══════════════════════════════════════════════════════════════════════════
// STACKED WIDGET SYSTEM — context-aware visibility + collapsible
// ══════════════════════════════════════════════════════════════════════════
let currentSidebarPanel = 'signals'; // kept for backward compat

// Legacy compat: setSidebarPanel is still called by some code paths
function setSidebarPanel(panel){
  currentSidebarPanel = panel;
  // Trigger data refresh for advisor when it becomes visible
  if(panel === 'advisor' && typeof pollAdvisor === 'function') pollAdvisor();
}

// Show/hide widgets based on active tab context
function updateWidgetContext(tabName){
  document.querySelectorAll('.sb-widget[data-ctx]').forEach(w => {
    const contexts = w.dataset.ctx.split(' ');
    if(contexts.includes(tabName)){
      w.classList.remove('hidden-ctx');
    } else {
      w.classList.add('hidden-ctx');
    }
  });
  console.log(`[Sidebar] Widget context: ${tabName}`);
}

// Toggle widget collapse
function toggleWidget(widgetId){
  const body = document.getElementById(widgetId + 'Body');
  const hdr = body?.previousElementSibling;
  const chevron = hdr?.querySelector('.chevron');
  if(!body) return;
  body.classList.toggle('collapsed');
  if(chevron) chevron.classList.toggle('collapsed');
  // Persist state
  try{ localStorage.setItem('wc_' + widgetId, body.classList.contains('collapsed') ? '1' : '0'); }catch(e){}
}

// Restore widget collapse states from localStorage
function restoreWidgetStates(){
  document.querySelectorAll('.sb-widget').forEach(w => {
    const key = 'wc_' + w.id;
    try{
      const val = localStorage.getItem(key);
      if(val === '1'){
        const body = document.getElementById(w.id + 'Body');
        const chevron = w.querySelector('.chevron');
        if(body) body.classList.add('collapsed');
        if(chevron) chevron.classList.add('collapsed');
      }
    }catch(e){}
  });
}

// Settings modal
function openSettingsModal(){
  if(window._settingsManager) window._settingsManager.open();
}
function closeSettingsModal(){
  if(window._settingsManager) window._settingsManager.close();
}

// Sync account bar with position data
function updateAccountBar(data){
  const eq = document.getElementById('sbAccEquity');
  const pnl = document.getElementById('sbAccDayPL');
  const wr = document.getElementById('sbAccWinRate');
  const op = document.getElementById('sbAccOpen');
  if(eq && data.equity != null) eq.textContent = '$' + parseFloat(data.equity).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
  if(pnl && data.daily_pnl != null){
    const v = parseFloat(data.daily_pnl);
    pnl.textContent = (v>=0?'+':'') + '$' + Math.abs(v).toFixed(2);
    pnl.className = 'sa-v ' + (v>0?'text-positive':v<0?'text-negative':'text-muted');
  }
  if(wr && data.win_rate != null) wr.textContent = (data.win_rate*100).toFixed(0) + '%';
  if(op && data.open_count != null) op.textContent = data.open_count;
}

// ══════════════════════════════════════════════════════════════════════════
// SIDEBAR DRAG-TO-RESIZE
// ══════════════════════════════════════════════════════════════════════════
// Sidebar resize — initialized directly (script runs after DOM is parsed)
(function initSidebarResize(){
  const MIN_W = 200, MAX_W = 600, DEFAULT_W = 260;
  const handle = document.getElementById('sbResizeHandle');
  const sidebar = document.getElementById('sidebarEl');
  if(!handle || !sidebar){ console.warn('[Resize] sbResizeHandle or sidebarEl not found'); return; }

  // Set CSS variable on init to guarantee sync with CSS fallback
  document.documentElement.style.setProperty('--sidebar-w', DEFAULT_W + 'px');
  let dragging = false, startX = 0, startW = DEFAULT_W;

  handle.addEventListener('mousedown', e => {
    e.preventDefault();
    dragging = true;
    startX = e.clientX;
    startW = sidebar.getBoundingClientRect().width;
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', e => {
    if(!dragging) return;
    const dx = startX - e.clientX;
    const newW = Math.min(MAX_W, Math.max(MIN_W, startW + dx));
    document.documentElement.style.setProperty('--sidebar-w', newW + 'px');
  });

  document.addEventListener('mouseup', () => {
    if(!dragging) return;
    dragging = false;
    handle.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    // Chart resize is handled automatically by the unified _chartResizeObs.
    // The ResizeObserver fires when sidebar width changes the chart containers.
    // Force an immediate resize in case the observer debounce hasn't fired yet.
    requestAnimationFrame(_resizeAllVisibleCharts);
  });
})();

// ══════════════════════════════════════════════════════════════════════════
// SYMBOL SWITCHING + SEARCH (any ticker via Alpaca)
// ══════════════════════════════════════════════════════════════════════════
function setSym(sym){
  if(!sym) return;
  const prev = S.sym;
  S.sym = sym.toUpperCase();
  document.getElementById('symInput').value = S.sym;
  document.title = `${S.sym} — Order Flow Trading Platform`;
  document.querySelectorAll('.sym-pill').forEach(b => b.classList.toggle('active', b.dataset.sym===S.sym));
  // Reset state
  S.lastPrice = null;
  S.prevClose = null;
  S.flowData = null;
  liveFlow.ticks = [];
  S.liveCandles.clear();
  rtCandle = null;  // Reset real-time candle on symbol switch
  luldData = {up:[], down:[]};
  restPollCount = 0;
  _destroyAllFlowRenderers(); // Free GPU memory from old symbol's renderers
  _streamState.tradeCount = 0;
  _streamState.quoteCount = 0;
  _streamState.lastTradeMs = 0;
  _streamState.lastQuoteMs = 0;
  const _hp = document.getElementById('hPrice'); if(_hp) _hp.textContent = '--';
  const _hc = document.getElementById('hChg'); if(_hc) _hc.textContent = '--';
  const _hba = document.getElementById('hBidAsk'); if(_hba) _hba.textContent = '';

  // Subscribe the backend SIP stream to the new symbol
  // This ensures real-time WS data flows for the selected ticker
  if(S.sym !== prev){
    fetch('/api/stream/subscribe', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify([S.sym]),
    }).then(r => r.json()).then(d => {
      console.log(`[Stream] Subscribed to ${S.sym}:`, d);
    }).catch(e => console.warn('[Stream] Subscribe failed:', e));

    // Load persisted ticks for this symbol (session continuity)
    _loadPersistedTicks(S.sym);
  }

  // Clear stale sidebar order flow data before reloading
  ['imbFeed','lgPrintFeed','absorbFeed'].forEach(id => {
    const el = document.getElementById(id);
    if(el){ el.innerHTML = ''; if(el._pool) el._pool = []; }
  });
  const _lgEmpty = document.getElementById('lgPrintEmpty');
  if(_lgEmpty) _lgEmpty.style.display = '';

  // Reload everything for new symbol
  loadHistory();
  loadOrderFlow();
  loadExpirations();
  refreshLiveData();
}

// Load persisted ticks from SQLite to restore session state after symbol switch or page refresh
async function _loadPersistedTicks(symbol){
  try{
    const windowMs = liveFlow.visibleWindowMs || 4 * 60 * 1000;
    const startMs = Date.now() - windowMs * 2; // Load 2x the visible window for context
    const r = await fetch(`/api/ticks?symbol=${symbol}&start_ms=${startMs}&limit=20000`);
    const d = await r.json();
    if(d.ticks && d.ticks.length > 0){
      let loaded = 0;
      d.ticks.forEach(t => {
        handleFlowTick(t.p, t.s, t.side || null, t.ts);
        loaded++;
      });
      console.log(`[TickStore] Loaded ${loaded} persisted ticks for ${symbol}`);
    }
  }catch(e){ console.debug('Persisted tick load failed:', e); }
}

let searchTimer = null;
function searchTicker(q){
  if(searchTimer) clearTimeout(searchTimer);
  if(!q || q.length < 1) { hideSearch(); return; }
  searchTimer = setTimeout(async () => {
    try{
      const r = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
      const d = await r.json();
      const box = document.getElementById('symResults');
      if(!d.results || !d.results.length){ box.innerHTML='<div style="padding:8px;color:var(--dim);font-size:9px">No results</div>'; box.classList.remove('u-hidden'); return; }
      box.innerHTML = d.results.map(s =>
        `<div onclick="setSym('${s.symbol}');hideSearch()" style="padding:5px 8px;cursor:pointer;font-size:10px;border-bottom:1px solid var(--brd);display:flex;gap:8px;align-items:center" onmouseover="this.style.background='var(--bg3)'" onmouseout="this.style.background=''">
          <span style="font-weight:700;color:#fff;min-width:50px">${s.symbol}</span>
          <span style="color:var(--dim);font-size:9px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.name}</span>
          <span style="color:var(--mut);font-size:8px;margin-left:auto">${s.exchange}</span>
        </div>`
      ).join('');
      box.classList.remove('u-hidden');
    }catch(e){ console.debug('[Search] Failed:', e); }
  }, 200);
}
function showSearch(){ /* triggered on focus */ }
function hideSearch(){ document.getElementById('symResults').classList.add('u-hidden'); }

// ══════════════════════════════════════════════════════════════════════════
// SYMBOL TOGGLE (SPY ↔ SPX)
// ══════════════════════════════════════════════════════════════════════════
async function toggleSymbol(){
  const newSym = S.sym === 'SPY' ? 'SPX' : 'SPY';
  try {
    const r = await fetch(`/api/signals/symbol?symbol=${newSym}`, {method:'POST'});
    if(!r.ok){ UI.toast(`Symbol switch failed (${r.status})`, 'error'); return; }
    const d = await r.json();
    if(d.error){ UI.toast('Symbol switch failed: ' + d.error, 'warning'); return; }
    setSym(d.symbol);
  } catch(e){ UI.toast('Symbol switch error — server unreachable', 'error'); console.error('Symbol toggle error:', e); }
}

// On load: sync symbol with server state
(async function initSymbol(){
  try {
    const r = await fetch('/api/signals/symbol');
    const d = await r.json();
    if(d.symbol){
      setSym(d.symbol);
    }
  } catch(e){ console.debug('[SymInit] Failed to sync symbol from server:', e); }
})();

// ══════════════════════════════════════════════════════════════════════════
// BAR DURATION
// ══════════════════════════════════════════════════════════════════════════
function setBar(minutes){
  S.barMinutes = minutes;
  // Sync top bar buttons
  document.querySelectorAll('.top-bar .bar-btn').forEach(b => b.classList.toggle('active', parseInt(b.dataset.bar)===minutes));
  loadOrderFlow(); // re-aggregate with new bar size

  // Map bar minutes to Alpaca timeframe and sync candle chart
  const barToTf = {1:'1Min', 5:'5Min', 15:'15Min', 30:'15Min', 60:'1H'};
  const tf = barToTf[minutes] || '5Min';
  S.tf = tf;
  // Sync candles toolbar buttons
  document.querySelectorAll('#tfGroup .tb-btn').forEach(b => b.classList.toggle('active', b.dataset.tf === tf));
  loadHistory(tf);
}


// ══════════════════════════════════════════════════════════════════════════
// CANDLE CHART — ThetaData EOD + Engine ticks
// ══════════════════════════════════════════════════════════════════════════
function setTf(tf){
  S.tf=tf;
  // Sync candles toolbar
  document.querySelectorAll('#tfGroup .tb-btn').forEach(b=>b.classList.toggle('active',b.dataset.tf===tf));
  // Sync nav bar buttons
  const tfToBar = {'1Min':1, '5Min':5, '15Min':15, '1H':60};
  const barMin = tfToBar[tf];
  if(barMin){
    S.barMinutes = barMin;
    document.querySelectorAll('.top-bar .bar-btn').forEach(b => b.classList.toggle('active', parseInt(b.dataset.bar)===barMin));
  } else {
    // live or 1D — no matching top bar button, deselect all
    document.querySelectorAll('.top-bar .bar-btn').forEach(b => b.classList.remove('active'));
  }
  if(tf==='live'){
    if(!_etOffset) _etOffset = _getETOffsetSec(Math.floor(Date.now()/1000));
    const arr = [...S.liveCandles.entries()].sort((a,b)=>a[0]-b[0]).map(([t,c])=>({time:t+_etOffset,...c}));
    if(arr.length){
      setAllCandleData(arr);
    }
  } else {
    loadHistory(tf);
  }
}

function setAllCandleData(candles){
  const vols = candles.map(b=>({time:b.time,value:b.volume||0,color:b.close>=b.open?'rgba(38,166,154,.2)':'rgba(239,83,80,.2)'}));
  // Combined tab
  try{ combCandleS.setData(candles); combVolS.setData(vols); }catch(e){}
  // Full tab
  try{ fullCandleS.setData(candles); fullVolS.setData(vols); }catch(e){}
}

// Real-time candle update: build/update the current bar from live ticks
// Works on any intraday timeframe (1m, 5m, 15m, 1H)
let rtCandle = null;  // {time, open, high, low, close, volume}
const tfSeconds = {'1Min':60, '5Min':300, '15Min':900, '1H':3600};

// ── Tick batching: accumulate ticks over 200ms window, render VWAP instead of
//    individual tick prices. Prevents price line stutter / false pump-dump visual.
//
//    FIX: High/low are now computed from the batch (not per-tick) so wicks
//    stay consistent with the VWAP close. This eliminates false pump/dump
//    artifacts where wicks extended to outlier ticks while close lagged behind.
let _rtBatchTimer = null;
const RT_BATCH_MS = 200;   // Render interval (ms) — balances smoothness vs responsiveness
let _rtTickBatch = [];      // Accumulates {price, size} during batch window
let _rtAllTicksHigh = 0;    // True high across ALL ticks in the current bar
let _rtAllTicksLow = Infinity; // True low across ALL ticks in the current bar
let _rtBarVolume = 0;       // Cumulative volume for the current bar

function updateRealtimeCandle(price, size){
  if(!price || price <= 0 || S.tf === '1D') return;
  const interval = tfSeconds[S.tf];
  if(!interval) return;

  const now = Math.floor(Date.now() / 1000);
  const barTime = now - (now % interval);

  if(!rtCandle || rtCandle.time !== barTime){
    // New bar period — flush pending batch, then start fresh
    _flushRtBatch();
    rtCandle = {time: barTime, open: price, high: price, low: price, close: price, volume: 0};
    _rtAllTicksHigh = price;
    _rtAllTicksLow = price;
    _rtBarVolume = 0;
  }

  const sz = size || 1;

  // Track true high/low across entire bar (used at flush time)
  _rtAllTicksHigh = Math.max(_rtAllTicksHigh, price);
  _rtAllTicksLow = Math.min(_rtAllTicksLow, price);
  _rtBarVolume += sz;

  // Accumulate tick into batch
  _rtTickBatch.push({price, size: sz});

  // Schedule batch flush if not already pending
  if(!_rtBatchTimer){
    _rtBatchTimer = setTimeout(_flushRtBatch, RT_BATCH_MS);
  }
}

function _flushRtBatch(){
  _rtBatchTimer = null;
  if(!rtCandle || _rtTickBatch.length === 0) return;

  // Compute VWAP of this batch for smooth close price
  let sumPV = 0, sumV = 0;
  let batchHigh = -Infinity, batchLow = Infinity;
  for(const t of _rtTickBatch){
    sumPV += t.price * t.size;
    sumV += t.size;
    if(t.price > batchHigh) batchHigh = t.price;
    if(t.price < batchLow) batchLow = t.price;
  }
  const vwapClose = sumV > 0 ? sumPV / sumV : _rtTickBatch[_rtTickBatch.length - 1].price;
  rtCandle.close = Math.round(vwapClose * 100) / 100;

  // High/low: use full-bar extremes (not just this batch) to stay accurate
  // but clamp to prevent single outlier ticks from creating huge wicks.
  // Allow wicks up to 2x the close-to-open range beyond close price.
  const range = Math.abs(rtCandle.close - rtCandle.open) || 0.01;
  const maxWick = range * 3; // Allow reasonable wicks but cap outliers
  rtCandle.high = Math.min(_rtAllTicksHigh, Math.max(rtCandle.open, rtCandle.close) + maxWick);
  rtCandle.low = Math.max(_rtAllTicksLow, Math.min(rtCandle.open, rtCandle.close) - maxWick);
  // Ensure high >= max(open,close) and low <= min(open,close)
  rtCandle.high = Math.max(rtCandle.high, rtCandle.open, rtCandle.close);
  rtCandle.low = Math.min(rtCandle.low, rtCandle.open, rtCandle.close);
  rtCandle.volume = _rtBarVolume;

  _rtTickBatch = [];

  // Render to chart
  requestAnimationFrame(()=>{
    if(!rtCandle) return;
    const shiftedTime = rtCandle.time + _etOffset;
    const bar = {time: shiftedTime, open: rtCandle.open, high: rtCandle.high, low: rtCandle.low, close: rtCandle.close};
    const vol = {time: shiftedTime, value: rtCandle.volume, color: rtCandle.close >= rtCandle.open ? 'rgba(38,166,154,.4)' : 'rgba(239,83,80,.4)'};
    const tab = S.activeTab;
    try{
      if(tab === 'candles' || tab === 'combined'){
        fullCandleS.update(bar); fullVolS.update(vol);
      }
      if(tab === 'combined'){
        combCandleS.update(bar); combVolS.update(vol);
      }
    }catch(e){}
  });
}

async function loadHistory(timeframe){
  if(_loadHistoryInFlight) return;  // Prevent concurrent loads
  _loadHistoryInFlight = true;
  const tf = timeframe || S.tf || '1D';
  // Limit bars per timeframe: cover enough sessions so the most recent day always appears
  const limitMap = {'1Min': 780, '5Min': 400, '15Min': 260, '1H': 200, '1D': 365};
  const limit = limitMap[tf] || 365;

  try{
    const r = await fetch(`/api/bars?symbol=${S.sym}&timeframe=${tf}&limit=${limit}`);
    const d = await r.json();
    if(d.bars && d.bars.length){
      d.bars.sort((a,b)=>(a.time<b.time?-1:1));

      // Shift intraday timestamps from UTC to "ET as UTC" so LWC places
      // tick marks at ET-natural boundaries (09:30, 10:00, 10:30 …)
      if(tf !== '1D' && typeof d.bars[0].time === 'number'){
        _etOffset = _getETOffsetSec(d.bars[0].time);
        d.bars.forEach(b => { b.time += _etOffset; });
      }

      const candles = d.bars.map(b=>({time:b.time,open:b.open,high:b.high,low:b.low,close:b.close}));
      const vols = d.bars.map(b=>({time:b.time,value:b.volume||0,color:b.close>=b.open?'rgba(38,166,154,.2)':'rgba(239,83,80,.2)'}));

      // Set on both candle charts
      try{
        combCandleS.setData(candles);
        combVolS.setData(vols);
      }catch(e){ console.warn('combCandle setData:', e); }
      try{
        fullCandleS.setData(candles);
        fullVolS.setData(vols);
      }catch(e){ console.warn('fullCandle setData:', e); }

      // Smart visible range: target ~30-min tick marks on the time axis.
      // LWC needs ≥ ~70px between adjacent tick marks to render them.
      // We tune visible bars per-TF so 30-min intervals get enough pixel room.
      //   1m:  180 bars ≈ 3h  → 30 bars/mark × (880px/180) ≈ 147px ✓
      //   5m:   54 bars ≈ 4.5h → 6 bars/mark × (880/54) ≈ 98px ✓
      //   15m:  26 bars ≈ 6.5h → 2 bars/mark × (880/26) ≈ 68px ≈ borderline
      //   1H:   keep 1.2× — 30-min ticks not possible on hourly data
      if(tf !== '1D' && candles.length > 0){
        const showMap = {'1Min': 180, '5Min': 54, '15Min': 26, '1H': 9};
        const showBars = Math.min(showMap[tf] || 78, candles.length);
        const fromIdx = Math.max(0, candles.length - showBars);
        // Store in state so tab switch can re-apply after resize
        S._candleVisibleRange = {from: fromIdx, to: candles.length - 1};
        applyCandleVisibleRange();
      } else {
        // Daily chart — fitContent shows everything
        S._candleVisibleRange = null;
        requestAnimationFrame(()=>{
          try{ combCandleChart.timeScale().fitContent(); }catch(e){}
          try{ fullCandleChart.timeScale().fitContent(); }catch(e){}
        });
      }

      // Price from last bar if no live
      if(!S.lastPrice){
        const last = candles[candles.length-1];
        S.lastPrice = last.close;
        S.prevClose = candles.length>1 ? candles[candles.length-2].close : last.close;
        updatePrice(last.close, S.prevClose);
      }

      // Compute indicators on ALL timeframes (not just daily)
      if(d.bars.length >= 20){
        computeIndicators(d.bars);
        const closes = d.bars.map(c=>c.close);
        const rsi14 = calcRSI(closes, 14);
        try{ combRsiS.setData(rsi14.map((v,i)=>({time:d.bars[i+closes.length-rsi14.length]?.time,value:v})).filter(d=>d.time)); }catch(e){}
      } else {
        try{ combRsiS.setData([]); }catch(e){}
      }

      document.getElementById('dotData').className='dot on';
      document.getElementById('lblData').textContent = d.source || 'SIP';
    } else if(d.error){
      console.warn('Bars error:', d.error);
      document.getElementById('lblData').textContent = 'No data for ' + tf;
    }
  }catch(e){
    console.error('Load history failed:', e);
  }

  // Fetch live price + quote for current symbol
  try{
    const mr = await fetch(`/api/market?symbol=${S.sym}`);
    const md = await mr.json();
    if(md.spy){
      S.lastPrice = md.spy.price;
      S.prevClose = md.spy.prev_close || md.spy.price;
      updatePrice(md.spy.price, S.prevClose);
      if(md.spy.source){
        // Clean up source labels for display
        const srcMap = {'alpaca_sip':'LIVE — SIP','alpaca_iex':'LIVE — IEX','thetadata_eod':'ThetaData EOD','engine':'LIVE — Engine'};
        document.getElementById('lblData').textContent = srcMap[md.spy.source] || md.spy.source;
      }
      if(md.spy.bid && md.spy.ask){
        const spread = (md.spy.ask - md.spy.bid).toFixed(2);
        document.getElementById('hBidAsk').textContent = `${md.spy.bid.toFixed(2)} × ${md.spy.ask.toFixed(2)} (${spread})`;
      }
    }
  }catch(e){}
  _loadHistoryInFlight = false;
}

function updatePrice(price, prev){
  const hp = document.getElementById('hPrice');
  if(hp) hp.textContent = '$'+price.toFixed(2);
  const chg = price - (prev || price);
  const pct = prev ? ((chg/prev)*100) : 0;
  const el = document.getElementById('hChg');
  if(el){
    el.textContent = `${chg>=0?'+':''}${chg.toFixed(2)} (${pct>=0?'+':''}${pct.toFixed(2)}%)`;
    el.style.color = chg >= 0 ? 'var(--grn)' : 'var(--red)';
  }
}

// ══════════════════════════════════════════════════════════════════════════
// INDICATORS — Registry-driven toggle + rendering
// ══════════════════════════════════════════════════════════════════════════

// Toggle handler — called by buttons and keyboard shortcuts
function toggleInd(name){
  indRegistry.toggle(name);
}

// Registry callback: apply indicator visibility to chart series
indRegistry.onToggle((id, enabled) => {
  if(id==='ema' && fullEmaS) fullEmaS.applyOptions({visible:enabled});
  if(id==='sma' && fullSmaS) fullSmaS.applyOptions({visible:enabled});
  if(id==='bb'){
    if(fullBbUpperS) fullBbUpperS.applyOptions({visible:enabled});
    if(fullBbLowerS) fullBbLowerS.applyOptions({visible:enabled});
  }
  if(id==='vwap' && fullVwapS) fullVwapS.applyOptions({visible:enabled});
  if(id==='vwapBands'){
    [fullVwapUp1S,fullVwapDn1S,fullVwapUp2S,fullVwapDn2S,fullVwapUp3S,fullVwapDn3S].forEach(s=>{ if(s) s.applyOptions({visible:enabled}); });
    if(enabled) fetchOverlayLevels();
  }
  if(id==='levels' || id==='gex' || id==='pivots'){
    _redrawPriceLines();
    if(enabled) fetchOverlayLevels();
  }
});

// Registry callback: re-render when settings change (period, color, etc.)
indRegistry.onSettingsChange((id, settings) => {
  // Update series visual style (color, lineWidth, lineStyle)
  const styleOpts = {color:settings.color, lineWidth:settings.lineWidth, lineStyle:settings.lineStyle};
  if(id==='ema' && fullEmaS) fullEmaS.applyOptions(styleOpts);
  if(id==='sma' && fullSmaS) fullSmaS.applyOptions(styleOpts);
  if(id==='bb'){
    if(fullBbUpperS) fullBbUpperS.applyOptions(styleOpts);
    if(fullBbLowerS) fullBbLowerS.applyOptions(styleOpts);
  }
  if(id==='vwap' && fullVwapS) fullVwapS.applyOptions(styleOpts);
  if(id==='vwapBands'){
    const vbStyle = {color:settings.color, lineWidth:settings.lineWidth, lineStyle:settings.lineStyle};
    [fullVwapUp1S,fullVwapDn1S,fullVwapUp2S,fullVwapDn2S,fullVwapUp3S,fullVwapDn3S].forEach(s => {
      if(s) s.applyOptions(vbStyle);
    });
  }
  // Recompute with new periods
  if(_lastCandles && _lastCandles.length > 0) computeIndicators(_lastCandles);
});

// Store last candles for recomputation when settings change
let _lastCandles = [];

function computeIndicators(candles){
  if(!candles.length) return;
  _lastCandles = candles;
  const closes = candles.map(c=>c.close);

  // Helper: map indicator values to {time, value} format for LWC
  const _map = (vals, offset) => vals.map((v,i)=>({time:candles[i+offset]?.time,value:v})).filter(d=>d.time);

  // EMA — period from registry (default 21)
  const emaPeriod = indRegistry.getSettings('ema').period || 21;
  const ema=calcEMA(closes, emaPeriod);
  try{fullEmaS.setData(_map(ema, closes.length-ema.length));}catch(e){}

  // SMA — period from registry (default 50)
  const smaPeriod = indRegistry.getSettings('sma').period || 50;
  const sma=calcSMA(closes, smaPeriod);
  try{fullSmaS.setData(_map(sma, closes.length-sma.length));}catch(e){}

  // Bollinger Bands — period and multiplier from registry (default 20, 2)
  const bbSettings = indRegistry.getSettings('bb');
  const bbPeriod = bbSettings.period || 20;
  const bbMult = bbSettings.multiplier || 2;
  const bb=calcBB(closes, bbPeriod, bbMult);
  try{
    fullBbUpperS.setData(_map(bb.upper, closes.length-bb.upper.length));
    fullBbLowerS.setData(_map(bb.lower, closes.length-bb.lower.length));
  }catch(e){}

  // RSI (always 14 for now — will be configurable in Phase 3)
  const rsi14=calcRSI(closes,14);
  try{fullRsiS.setData(_map(rsi14, closes.length-rsi14.length));}catch(e){}

  // VWAP — session-anchored
  const vwapData=calcVWAP(candles);
  try{fullVwapS.setData(vwapData);}catch(e){}

  // VWAP ±σ bands
  if(indRegistry.isEnabled('vwapBands')) _computeVwapBands(candles);
}

// ══════════════════════════════════════════════════════════════════════════
// CHART OVERLAYS — VWAP Bands, Session Levels, GEX Levels, Pivot Points
// ══════════════════════════════════════════════════════════════════════════

/**
 * Compute VWAP ±1/2/3σ bands from candle data.
 * Uses session-aware reset at 9:30 ET (same as main VWAP).
 */
function _computeVwapBands(candles){
  if(!candles.length) return;
  const bands = {up1:[],dn1:[],up2:[],dn2:[],up3:[],dn3:[]};
  let cumVol=0, cumTpVol=0, cumTp2Vol=0;
  let prevDay = null;

  for(const c of candles){
    // Session reset detection (intraday only)
    const t = c.time;
    let curDay = null;
    if(typeof t === 'object' && t.year){
      curDay = `${t.year}-${t.month}-${t.day}`;
    } else if(typeof t === 'number'){
      // Data is shifted to "ET as UTC" — use getUTC* for correct ET day boundaries
      const d = new Date(t * 1000);
      curDay = `${d.getUTCFullYear()}-${d.getUTCMonth()}-${d.getUTCDate()}`;
    }
    // Reset at new session (intraday)
    if(curDay && prevDay && curDay !== prevDay){
      cumVol=0; cumTpVol=0; cumTp2Vol=0;
    }
    prevDay = curDay;

    const v = c.volume || 0;
    if(v <= 0) continue;
    const tp = (c.high + c.low + c.close) / 3;
    cumVol += v;
    cumTpVol += tp * v;
    cumTp2Vol += (tp*tp) * v;

    const vwap = cumTpVol / cumVol;
    const variance = (cumTp2Vol / cumVol) - (vwap * vwap);
    const std = Math.sqrt(Math.max(0, variance));

    bands.up1.push({time:t, value: Math.round((vwap + std)*10000)/10000});
    bands.dn1.push({time:t, value: Math.round((vwap - std)*10000)/10000});
    bands.up2.push({time:t, value: Math.round((vwap + 2*std)*10000)/10000});
    bands.dn2.push({time:t, value: Math.round((vwap - 2*std)*10000)/10000});
    bands.up3.push({time:t, value: Math.round((vwap + 3*std)*10000)/10000});
    bands.dn3.push({time:t, value: Math.round((vwap - 3*std)*10000)/10000});
  }

  try{
    fullVwapUp1S.setData(bands.up1); fullVwapDn1S.setData(bands.dn1);
    fullVwapUp2S.setData(bands.up2); fullVwapDn2S.setData(bands.dn2);
    fullVwapUp3S.setData(bands.up3); fullVwapDn3S.setData(bands.dn3);
  }catch(e){}
}

/**
 * Fetch overlay data (market levels + GEX) from backend and draw price lines.
 * Called when user toggles LVL/GEX/PIV on, and periodically during pollMetrics.
 */
let _overlayFetchInFlight = false;
async function fetchOverlayLevels(){
  if(_overlayFetchInFlight) return;
  _overlayFetchInFlight = true;
  try{
    const [levelsResp, gexResp] = await Promise.allSettled([
      fetch('/api/signals/levels').then(r=>r.ok?r.json():null),
      fetch('/api/signals/gex').then(r=>r.ok?r.json():null),
    ]);
    if(levelsResp.status==='fulfilled' && levelsResp.value){
      _overlayLevelsData = levelsResp.value.levels || null;
    }
    if(gexResp.status==='fulfilled' && gexResp.value){
      _overlayGexData = gexResp.value.gex || null;
    }
    _redrawPriceLines();
  }catch(e){}
  _overlayFetchInFlight = false;
}

/**
 * Clear and redraw all horizontal price lines based on current toggle state.
 * Uses Lightweight Charts `createPriceLine()` on the candle series.
 */
function _redrawPriceLines(){
  if(!fullCandleS) return;
  // Remove existing overlay lines
  for(const pl of _overlayPriceLines){
    try{ fullCandleS.removePriceLine(pl); }catch(e){}
  }
  _overlayPriceLines = [];

  const _line = (price, title, color, lineStyle, lineWidth) => {
    if(!price || price <= 0) return;
    const pl = fullCandleS.createPriceLine({
      price: price,
      color: color,
      lineWidth: lineWidth || 1,
      lineStyle: lineStyle ?? 2, // 0=solid, 1=dotted, 2=dashed
      axisLabelVisible: true,
      title: title,
    });
    _overlayPriceLines.push(pl);
  };

  // ── Session Levels ──
  if(indRegistry.isEnabled('levels') && _overlayLevelsData){
    const L = _overlayLevelsData;
    // Day range
    if(L.hod) _line(L.hod, 'HOD', T.warning, 2, 1);
    if(L.lod) _line(L.lod, 'LOD', T.warning, 2, 1);
    // Previous day
    if(L.prev_close) _line(L.prev_close, 'Prev Close', T.dim, 1, 1);
    if(L.prev_high) _line(L.prev_high, 'Prev Hi', 'rgba(158,158,158,0.5)', 1, 1);
    if(L.prev_low) _line(L.prev_low, 'Prev Lo', 'rgba(158,158,158,0.5)', 1, 1);
    // Opening Range
    if(L.orb_5_high) _line(L.orb_5_high, 'ORB 5m Hi', T.purple, 2, 1);
    if(L.orb_5_low) _line(L.orb_5_low, 'ORB 5m Lo', T.purple, 2, 1);
    if(L.orb_15_high) _line(L.orb_15_high, 'ORB 15m Hi', 'rgba(124,77,255,0.5)', 1, 1);
    if(L.orb_15_low) _line(L.orb_15_low, 'ORB 15m Lo', 'rgba(124,77,255,0.5)', 1, 1);
    // Volume Profile
    if(L.poc) _line(L.poc, 'POC', T.warning, 0, 2);
    if(L.value_area_high) _line(L.value_area_high, 'VA Hi', 'rgba(255,235,59,0.4)', 1, 1);
    if(L.value_area_low) _line(L.value_area_low, 'VA Lo', 'rgba(255,235,59,0.4)', 1, 1);
  }

  // ── GEX Levels ──
  if(indRegistry.isEnabled('gex') && _overlayGexData){
    const G = _overlayGexData;
    if(G.call_wall) _line(G.call_wall, 'Call Wall', T.negative, 0, 2);
    if(G.put_wall) _line(G.put_wall, 'Put Wall', T.positive, 0, 2);
    if(G.gex_flip_level) _line(G.gex_flip_level, 'GEX Flip', T.warning, 2, 1);
    if(G.max_gamma_strike) _line(G.max_gamma_strike, 'Max γ', 'rgba(255,193,7,0.4)', 1, 1);
  }

  // ── Pivot Points ──
  if(indRegistry.isEnabled('pivots') && _overlayLevelsData){
    const L = _overlayLevelsData;
    if(L.pivot) _line(L.pivot, 'Pivot', T.dim, 0, 1);
    if(L.r1) _line(L.r1, 'R1', 'rgba(239,83,80,0.6)', 2, 1);
    if(L.r2) _line(L.r2, 'R2', 'rgba(239,83,80,0.4)', 1, 1);
    if(L.r3) _line(L.r3, 'R3', 'rgba(239,83,80,0.25)', 1, 1);
    if(L.s1) _line(L.s1, 'S1', 'rgba(38,166,154,0.6)', 2, 1);
    if(L.s2) _line(L.s2, 'S2', 'rgba(38,166,154,0.4)', 1, 1);
    if(L.s3) _line(L.s3, 'S3', 'rgba(38,166,154,0.25)', 1, 1);
  }
}

function calcEMA(data,p){if(data.length<p)return[];const k=2/(p+1);let e=[data.slice(0,p).reduce((a,b)=>a+b,0)/p];for(let i=p;i<data.length;i++)e.push(data[i]*k+e[e.length-1]*(1-k));return e;}
// O(n) SMA using running sum (replaces O(n×p) slice-reduce approach)
function calcSMA(data,p){
  if(data.length<p) return [];
  const r = new Array(data.length - p + 1);
  let sum = 0;
  for(let i = 0; i < p; i++) sum += data[i];
  r[0] = sum / p;
  for(let i = p; i < data.length; i++){
    sum += data[i] - data[i - p];
    r[i - p + 1] = sum / p;
  }
  return r;
}
// O(n) Bollinger Bands using running variance (replaces O(n×p) nested-slice approach)
function calcBB(data,p,m){
  const s = calcSMA(data,p);
  if(!s.length) return {upper:[], lower:[]};
  const u = new Array(s.length), l = new Array(s.length);
  // Compute initial variance for first window
  let sumSq = 0;
  for(let i = 0; i < p; i++){
    const d = data[i] - s[0];
    sumSq += d * d;
  }
  let std = Math.sqrt(sumSq / p);
  u[0] = s[0] + m * std;
  l[0] = s[0] - m * std;
  // Slide window: update variance incrementally
  for(let j = 1; j < s.length; j++){
    const oldVal = data[j - 1], newVal = data[j + p - 1];
    const oldDev = oldVal - s[j - 1], newDev = newVal - s[j];
    // Recompute sumSq from scratch every 50 windows to prevent floating-point drift
    if(j % 50 === 0){
      sumSq = 0;
      for(let k = j; k < j + p; k++){ const d = data[k] - s[j]; sumSq += d * d; }
    } else {
      sumSq = sumSq - oldDev * oldDev + newDev * newDev;
      if(sumSq < 0) sumSq = 0; // Guard against float rounding
    }
    std = Math.sqrt(sumSq / p);
    u[j] = s[j] + m * std;
    l[j] = s[j] - m * std;
  }
  return {upper: u, lower: l};
}
function calcRSI(data,p){if(data.length<p+1)return[];const r=[];let aG=0,aL=0;for(let i=1;i<=p;i++){const d=data[i]-data[i-1];if(d>0)aG+=d;else aL-=d;}aG/=p;aL/=p;r.push(aL===0?100:100-100/(1+aG/aL));for(let i=p+1;i<data.length;i++){const d=data[i]-data[i-1];aG=(aG*(p-1)+(d>0?d:0))/p;aL=(aL*(p-1)+(d<0?-d:0))/p;r.push(aL===0?100:100-100/(1+aG/aL));}return r;}

function calcVWAP(candles){
  // VWAP = cumulative(typical_price * volume) / cumulative(volume)
  // For daily bars: anchored to start of visible data (no reset)
  // For intraday: resets at 9:30 AM ET each trading day (proper session boundary)
  if(!candles.length) return [];
  const result = [];
  let cumTPV = 0, cumVol = 0, lastSessionDate = '';
  const isIntraday = typeof candles[0].time === 'number';

  for(const c of candles){
    const tp = (c.high + c.low + c.close) / 3;
    const vol = c.volume || 0;

    if(isIntraday){
      // Data is shifted to "ET as UTC" — read ET time via getUTC* directly
      const etDate = new Date(c.time * 1000);
      const etHour = etDate.getUTCHours();
      const etMin = etDate.getUTCMinutes();
      // Session date: if before 9:30 ET, pre-market belongs to previous session
      let sessionDate;
      if(etHour < 9 || (etHour === 9 && etMin < 30)){
        sessionDate = lastSessionDate || etDate.toISOString().slice(0,10);
      } else {
        sessionDate = etDate.toISOString().slice(0,10);
      }
      if(sessionDate !== lastSessionDate && lastSessionDate !== ''){
        cumTPV = 0; cumVol = 0;
      }
      lastSessionDate = sessionDate;
    }
    // Daily bars: never reset — anchored VWAP across the entire visible range

    cumTPV += tp * vol;
    cumVol += vol;
    if(cumVol > 0) result.push({time:c.time, value: Math.round((cumTPV/cumVol)*100)/100});
  }
  return result;
}

// ══════════════════════════════════════════════════════════════════════════
// DRAWING TOOLS
// ══════════════════════════════════════════════════════════════════════════
function setDraw(mode){
  if(S.drawMode===mode){
    S.drawMode=null;S.drawClicks=[];
    document.querySelectorAll('.draw-mode').forEach(el=>el.style.display='none');
    document.querySelectorAll('#btnHLine,#btnTrend,#btnFib').forEach(b=>b.classList.remove('active'));
    return;
  }
  S.drawMode=mode;S.drawClicks=[];
  document.querySelectorAll('#btnHLine,#btnTrend,#btnFib').forEach(b=>b.classList.remove('active'));
  const btnMap={hline:'btnHLine',trend:'btnTrend',fib:'btnFib'};
  document.getElementById(btnMap[mode])?.classList.add('active');
  const labels={hline:'Click to place H-Line',trend:'Click start point',fib:'Click high point'};
  document.querySelectorAll('.draw-mode').forEach(el=>{el.textContent=labels[mode];el.style.display='block';});
}

function handleDrawClick(param, candleSeries, chart){
  const price=candleSeries.coordinateToPrice(param.point.y);
  const time=param.time;

  if(S.drawMode==='hline'){
    candleSeries.createPriceLine({price,color:T.accent,lineWidth:1,lineStyle:2,axisLabelVisible:true});
    S.drawMode=null;document.querySelectorAll('.draw-mode').forEach(el=>el.style.display='none');
    document.getElementById('btnHLine').classList.remove('active');
  }
  else if(S.drawMode==='trend'){
    S.drawClicks.push({time,price});
    if(S.drawClicks.length===1) document.querySelectorAll('.draw-mode').forEach(el=>el.textContent='Click end point');
    if(S.drawClicks.length===2){
      const ls=chart.addLineSeries({color:T.accent,lineWidth:1,priceLineVisible:false,lastValueVisible:false});
      ls.setData([{time:S.drawClicks[0].time,value:S.drawClicks[0].price},{time:S.drawClicks[1].time,value:S.drawClicks[1].price}]);
      S.drawings.push(ls);S.drawMode=null;S.drawClicks=[];
      document.querySelectorAll('.draw-mode').forEach(el=>el.style.display='none');
      document.getElementById('btnTrend').classList.remove('active');
    }
  }
  else if(S.drawMode==='fib'){
    S.drawClicks.push({time,price});
    if(S.drawClicks.length===1) document.querySelectorAll('.draw-mode').forEach(el=>el.textContent='Click low point');
    if(S.drawClicks.length===2){
      const high=Math.max(S.drawClicks[0].price,S.drawClicks[1].price);
      const low=Math.min(S.drawClicks[0].price,S.drawClicks[1].price);
      const diff=high-low;
      [0,0.236,0.382,0.5,0.618,0.786,1].forEach((lv,i)=>{
        const colors=[T.negative,T.warning,'#ff9800',T.sma,T.positive,T.rsi,T.negative];
        candleSeries.createPriceLine({price:high-diff*lv,color:colors[i],lineWidth:1,lineStyle:2,title:`${(lv*100).toFixed(1)}%`,axisLabelVisible:true});
      });
      S.drawMode=null;S.drawClicks=[];
      document.querySelectorAll('.draw-mode').forEach(el=>el.style.display='none');
      document.getElementById('btnFib').classList.remove('active');
    }
  }
}

