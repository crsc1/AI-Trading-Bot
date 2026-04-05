// ══════════════════════════════════════════════════════════════════════════
// P&L EQUITY CURVE — lightweight-charts mini chart in sidebar
// ══════════════════════════════════════════════════════════════════════════

let _equityCurveChart = null;
let _equityCurveSeries = null;
let _equityCurveTimer = null;

function _initEquityCurve(){
  const wrap = document.getElementById('equityCurveWrap');
  if(!wrap || _equityCurveChart) return;

  _equityCurveChart = LightweightCharts.createChart(wrap, {
    autoSize: true,
    height: 90,
    layout: { background: { type: 'solid', color: T.surface1 }, textColor: T.dim, fontSize: T.fontXs },
    grid: { vertLines: { visible: false }, horzLines: { color: T.borderSubtle } },
    timeScale: { visible: true, timeVisible: true, secondsVisible: false, borderColor: T.border },
    rightPriceScale: { borderColor: T.border, scaleMargins: { top: 0.1, bottom: 0.1 } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    handleScroll: false,
    handleScale: false,
  });

  _equityCurveSeries = _equityCurveChart.addAreaSeries({
    lineColor: T.accent,
    topColor: 'rgba(85,136,238,0.3)',
    bottomColor: 'rgba(85,136,238,0.01)',
    lineWidth: 1.5,
    priceFormat: { type: 'custom', formatter: v => '$' + v.toFixed(2) },
  });
  // Responsive resize handled by the unified _chartResizeObs system
}

async function pollEquityCurve(){
  try {
    const resp = await fetch('/api/signals/scorecard?period=today');
    if(!resp.ok) return;
    const d = await resp.json();
    const trades = d.trades || d.basic?.trades || [];
    if(trades.length === 0) return;

    // Build cumulative P&L series from trade timestamps + P&L
    let cumPnl = 0;
    const points = [];
    for(const t of trades){
      if(!t.exit_time && !t.closed_at && !t.timestamp) continue;
      const ts = t.exit_time || t.closed_at || t.timestamp;
      const epoch = Math.floor(new Date(ts).getTime() / 1000);
      const pnl = t.pnl || t.net_pnl || 0;
      cumPnl += pnl;
      points.push({ time: epoch, value: cumPnl });
    }

    if(points.length > 0 && _equityCurveSeries){
      // Sort and deduplicate by time
      points.sort((a,b) => a.time - b.time);
      const deduped = [];
      let lastTime = 0;
      for(const p of points){
        if(p.time > lastTime){ deduped.push(p); lastTime = p.time; }
      }
      _equityCurveSeries.setData(deduped);

      // Color based on final P&L
      const lineColor = cumPnl >= 0 ? T.positive : T.negative;
      _equityCurveSeries.applyOptions({
        lineColor,
        topColor: cumPnl >= 0 ? 'rgba(38,166,154,0.3)' : 'rgba(239,83,80,0.3)',
        bottomColor: cumPnl >= 0 ? 'rgba(38,166,154,0.01)' : 'rgba(239,83,80,0.01)',
      });
    }
  } catch(e){ /* silent */ }
}

function startEquityCurvePoll(){
  if(_equityCurveTimer) return;
  _initEquityCurve();
  _equityCurveTimer = setInterval(pollEquityCurve, 30000); // Every 30s
  setTimeout(pollEquityCurve, 5000);
}

// ══════════════════════════════════════════════════════════════════════════
// TRADE JOURNAL — mini-reports for each closed trade
// ══════════════════════════════════════════════════════════════════════════

let _journalPollTimer = null;
let _journalRenderedCount = 0;

async function pollTradeJournal(){
  try {
    const resp = await fetch('/api/signals/scorecard?period=today');
    if(!resp.ok) return;
    const d = await resp.json();
    const trades = d.trades || d.basic?.trades || [];
    if(trades.length === _journalRenderedCount) return; // No new trades
    _journalRenderedCount = trades.length;
    _renderTradeJournal(trades);
  } catch(e){ /* silent */ }
}

function _renderTradeJournal(trades){
  let container = document.getElementById('tradeJournalWrap');
  if(!container) return;

  if(trades.length === 0){
    container.innerHTML = '<div style="color:var(--mut);font-size:9px;padding:8px">No closed trades today</div>';
    return;
  }

  // Render in reverse chronological order
  const sorted = [...trades].reverse();
  container.innerHTML = sorted.map((t, i) => {
    const pnl = t.pnl || t.net_pnl || 0;
    const isWin = pnl >= 0;
    const borderColor = isWin ? 'var(--grn)' : 'var(--red)';
    const symbol = t.symbol || t.contract || 'SPY';
    const entryTime = t.entry_time || t.opened_at || '';
    const exitTime = t.exit_time || t.closed_at || '';
    const entryTs = entryTime ? new Date(entryTime).toLocaleTimeString('en-US', {hour12:false, hour:'2-digit', minute:'2-digit'}) : '--';
    const exitTs = exitTime ? new Date(exitTime).toLocaleTimeString('en-US', {hour12:false, hour:'2-digit', minute:'2-digit'}) : '--';
    const holdMin = t.hold_time_minutes || (entryTime && exitTime ? Math.round((new Date(exitTime) - new Date(entryTime)) / 60000) : 0);
    const entryPrice = t.entry_price ? '$' + parseFloat(t.entry_price).toFixed(2) : '--';
    const exitPrice = t.exit_price ? '$' + parseFloat(t.exit_price).toFixed(2) : '--';
    const reason = t.exit_reason || t.close_reason || 'manual';
    const mfe = t.mfe ? '+$' + parseFloat(t.mfe).toFixed(2) : '--';
    const mae = t.mae ? '-$' + Math.abs(parseFloat(t.mae)).toFixed(2) : '--';
    const grade = t.grade || '--';
    const gradeColor = grade === 'A' ? T.positive : grade === 'B' ? '#8bc34a' : grade === 'C' ? T.warning : grade === 'D' ? T.negative : 'var(--dim)';
    const confPct = t.confidence ? (t.confidence * 100).toFixed(0) + '%' : '--';

    return `<div style="background:var(--bg2);border:1px solid var(--brd);border-left:3px solid ${borderColor};border-radius:6px;padding:8px 10px;margin-bottom:6px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
        <div>
          <span style="font-weight:700;font-size:10px;color:#fff">${esc(symbol)}</span>
          <span style="font-size:8px;color:var(--dim);margin-left:6px">#${sorted.length - i}</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px">
          <span style="font-size:9px;font-weight:600;padding:1px 5px;border-radius:3px;background:${gradeColor}22;color:${gradeColor}">${grade}</span>
          <span style="font-size:10px;font-weight:700;color:${isWin ? 'var(--grn)' : 'var(--red)'}">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</span>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:4px;font-size:8px;margin-bottom:4px">
        <div><span style="color:var(--mut)">Entry</span><br>${entryPrice} @ ${entryTs}</div>
        <div><span style="color:var(--mut)">Exit</span><br>${exitPrice} @ ${exitTs}</div>
        <div><span style="color:var(--mut)">MFE</span><br><span style="color:var(--grn)">${mfe}</span></div>
        <div><span style="color:var(--mut)">MAE</span><br><span style="color:var(--red)">${mae}</span></div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:8px;color:var(--dim)">
        <span>${holdMin}m hold</span>
        <span>Conf: ${confPct}</span>
        <span>Exit: ${esc(reason)}</span>
      </div>
    </div>`;
  }).join('');
}
