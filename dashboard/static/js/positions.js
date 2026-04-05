// ══════════════════════════════════════════════════════════════════════════
// POSITIONS & P&L TAB
// ══════════════════════════════════════════════════════════════════════════
let equityChart = null, equitySeries = null;

let STARTING_BALANCE = 5000.00; // Default; updated from /api/pm/settings on init

let _posRefreshLock = false; // Prevent overlapping refreshes
async function refreshPositionsTab(){
  if(_posRefreshLock) return;
  _posRefreshLock = true;
  try{ await _doRefreshPositionsTab(); }finally{ _posRefreshLock = false; }
}
async function _doRefreshPositionsTab(){
  // Simulation mode — no Alpaca trading API calls. All data from PM + local DB.
  const [pmRes, botPosRes, tradesRes] = await Promise.all([
    fetch('/api/pm/status').then(r=>r.json()).catch(()=>({})),
    fetch('/api/signals/positions').then(r=>r.json()).catch(()=>({positions:[],summary:{}})),
    fetch('/api/signals/trades?limit=200').then(r=>r.json()).catch(()=>({trades:[]})),
  ]);

  // ── Simulation account summary ──────────────────────────────────────────
  const closedTrades = (tradesRes.trades || []).filter(t => t.exit_price != null);
  const realizedPnl  = closedTrades.reduce((s, t) => s + (t.pnl || 0), 0);
  const unrealizedPnl = botPosRes.summary?.total_unrealized_pnl || 0;
  const equity    = STARTING_BALANCE + realizedPnl + unrealizedPnl;
  const cash      = STARTING_BALANCE + realizedPnl; // cash = starting + realized (open pos not yet settled)
  const dailyPnl  = pmRes.daily_pnl ?? 0;  // Default to 0, NOT all-time realizedPnl
  const dailyPnlPct = STARTING_BALANCE > 0 ? (dailyPnl / STARTING_BALANCE * 100) : 0;

  const eqEl = document.getElementById('posEquity');
  if(eqEl){ eqEl.textContent = '$'+equity.toLocaleString(undefined,{minimumFractionDigits:2}); eqEl.style.color = '#fff'; }
  // Sync sidebar account bar
  const sbEq = document.getElementById('sbAccEquity');
  if(sbEq) sbEq.textContent = '$'+equity.toLocaleString(undefined,{minimumFractionDigits:2});
  const cashEl = document.getElementById('posCash');
  if(cashEl) cashEl.textContent = '$'+cash.toLocaleString(undefined,{minimumFractionDigits:2});
  const bpEl = document.getElementById('posBP');
  if(bpEl) bpEl.textContent = '$'+cash.toLocaleString(undefined,{minimumFractionDigits:2}); // BP = cash (cash acct, no margin)
  const plEl = document.getElementById('posDayPL');
  if(plEl){
    plEl.textContent = (dailyPnl>=0?'+':'')+dailyPnl.toFixed(2)+' ('+dailyPnlPct.toFixed(2)+'%)';
    plEl.style.color = dailyPnl >= 0 ? 'var(--grn)' : 'var(--red)';
  }

  // ── Open positions (simulation only — no Alpaca positions) ─────────────
  const botPositions = botPosRes.positions || [];
  const allPositions = [];

  // NOTE: Alpaca positions block removed — simulation mode places no broker orders.
  // Simulation positions — push all bot positions as source 'SIM'
  for(const bp of botPositions){
    const entry = parseFloat(bp.entry_price || 0);
    const current = parseFloat(bp.current_price || bp.entry_price || 0);
    const qty = bp.quantity || bp.qty || 1;
    const optType = bp.option_type || 'call';
    const strike = bp.strike || 0;
    allPositions.push({
      symbol: bp.symbol || 'SPY', strike, option_type: optType, quantity: qty,
      displaySymbol: strike ? `${bp.symbol||'SPY'} $${strike} ${optType.toUpperCase()}` : (bp.symbol||'Unknown'),
      side: 'long', avg_entry_price: entry, current_price: current,
      market_value: qty * current * 100,
      unrealized_pl: bp.unrealized_pnl || 0,
      unrealized_plpc: bp.unrealized_pnl_pct || (entry > 0 ? ((current - entry) / entry * 100) : 0),
      isBot: true, source: 'SIM',
      hold_minutes: bp.hold_minutes || 0,
      max_favorable: bp.max_favorable || 0, max_adverse: bp.max_adverse || 0,
      price_source: bp.price_source || '', bid: bp.bid, ask: bp.ask,
      live_greeks: bp.live_greeks || {},
      target_price: bp.target_price, stop_price: bp.stop_price,
      entry_time: bp.entry_time,
    });
  }

  // ── Summary bar ────────────────────────────────────────────────────────
  const posCountEl = document.getElementById('posCount');
  if(posCountEl) posCountEl.textContent = allPositions.length;
  const openPL = botPosRes.summary?.total_unrealized_pnl || 0;
  const plEl2 = document.getElementById('posOpenPL');
  if(plEl2){
    plEl2.textContent = (openPL>=0?'+':'')+openPL.toFixed(2);
    plEl2.style.color = openPL >= 0 ? 'var(--grn)' : 'var(--red)';
  }
  const posCountLbl = document.getElementById('posCountLabel');
  if(posCountLbl) posCountLbl.textContent = allPositions.length ? `(${allPositions.length})` : '';

  // ── Render positions table (DataTable component) ─────────────────────────
  const cardsWrap = document.getElementById('posCardsWrap');
  if(cardsWrap){
    if(!window._positionsTable){
      window._positionsTable = new DataTable({
        container: cardsWrap,
        compact: true,
        sortable: true,
        resizable: true,
        stickyHeader: true,
        highlightOnHover: true,
        emptyMessage: 'No open positions — bot is watching for signals',
        columns: [
          { key:'side',     label:'Side',    width:55, render: (_,r) => UI.badge(r._direction, r._dirVariant) },
          { key:'symbol',   label:'Symbol',  width:130, render: (_,r) => `<span style="color:var(--text-primary);font-weight:var(--font-bold)">${esc(r.displaySymbol||r.symbol||'SPY')}</span>` },
          { key:'quantity', label:'Qty',     width:40, align:'right' },
          { key:'avg_entry_price', label:'Entry', width:65, align:'right', format:'currency' },
          { key:'current_price',   label:'Current', width:65, align:'right', format:'currency' },
          { key:'unrealized_pl',   label:'P&L',   width:75, align:'right', sortable:true,
            render: (v) => { const c = v>=0?'var(--positive)':'var(--negative)'; return `<span style="color:${c}">${v>=0?'+':''}$${(v||0).toFixed(2)}</span>`; } },
          { key:'unrealized_plpc', label:'P&L %', width:65, align:'right', sortable:true,
            render: (v) => { const c = v>=0?'var(--positive)':'var(--negative)'; return `<span style="color:${c}">${v>=0?'+':''}${(v||0).toFixed(1)}%</span>`; } },
          { key:'market_value',    label:'Mkt Val', width:70, align:'right', format:'currency' },
          { key:'source',  label:'Source', width:55, render: (_,r) => UI.badge(r._srcLabel, r._srcVariant) },
        ],
      });
    }
    // Enrich rows with pre-computed display values
    const enriched = allPositions.map(p => {
      const optType = p.option_type || (p.side === 'short' ? 'put' : 'call');
      return { ...p,
        _direction: optType === 'put' ? 'PUT' : 'CALL',
        _dirVariant: optType === 'put' ? 'red' : 'green',
        _srcLabel: p.source || (p.isBot ? 'SIM' : 'ALPACA'),
        _srcVariant: p.isBot ? 'blue' : 'neutral',
      };
    });
    window._positionsTable.setData(enriched);
  }

  // ── Render trade history (DataTable component) ──────────────────────────
  const trades = tradesRes.trades || [];
  const histWrap = document.getElementById('tradeHistWrap');
  const histCount = document.getElementById('tradeHistCount');
  if(histCount) histCount.textContent = trades.length ? `(${trades.length})` : '';
  if(histWrap){
    if(!window._tradeHistTable){
      const _exitReasonVariants = {
        'profit_target':{label:'TARGET',variant:'green'}, 'profit_protected':{label:'PROTECTED',variant:'green'},
        'stop_loss':{label:'STOPPED',variant:'red'}, 'velocity_stop':{label:'V-STOP',variant:'red'},
        'breakeven_stop':{label:'BREAKEVEN',variant:'yellow'}, 'time_stop_0dte':{label:'TIME',variant:'yellow'},
        'max_hold_time':{label:'MAX HOLD',variant:'yellow'}, 'manual':{label:'MANUAL',variant:'neutral'},
        'theta_decay':{label:'THETA',variant:'red'}, 'trailing_stop':{label:'TRAIL',variant:'green'},
        'trailing_stop_remainder':{label:'TRAIL-R',variant:'green'}, 'dynamic_breakeven_protect':{label:'DEX-BE',variant:'yellow'},
      };
      const _gradeVariants = {A:'green',B:'blue',C:'yellow',D:'yellow',F:'red'};

      window._tradeHistTable = new DataTable({
        container: histWrap,
        compact: true,
        sortable: true,
        resizable: true,
        stickyHeader: true,
        highlightOnHover: true,
        emptyMessage: 'No trades yet — waiting for first signal execution',
        columns: [
          { key:'side',  label:'Side', width:55, render:(_,r)=>UI.badge(r._direction, r._dirVariant) },
          { key:'_sym',  label:'Symbol', width:130, render:(v)=>`<span style="color:var(--text-primary);font-weight:var(--font-bold)">${esc(v)}</span>` },
          { key:'quantity', label:'Qty', width:40, align:'right' },
          { key:'entry_price', label:'Entry', width:65, align:'right', format:'currency' },
          { key:'exit_price',  label:'Exit',  width:65, align:'right', format:'currency' },
          { key:'pnl', label:'P&L', width:75, align:'right', sortable:true,
            render:(v)=>{ const c=v>=0?'var(--positive)':'var(--negative)'; return `<span style="color:${c}">${v>=0?'+':''}$${(v||0).toFixed(2)}</span>`; } },
          { key:'pnl_pct', label:'P&L %', width:65, align:'right', sortable:true,
            render:(v)=>{ const c=v>=0?'var(--positive)':'var(--negative)'; return `<span style="color:${c}">${v>=0?'+':''}${(v||0).toFixed(1)}%</span>`; } },
          { key:'_holdMin', label:'Duration', width:60, align:'right', render:(v)=>`${v}m` },
          { key:'_exitReason', label:'Reason', width:75, render:(_,r)=>UI.badge(r._exitInfo.label, r._exitInfo.variant) },
          { key:'grade', label:'Grade', width:50, render:(v)=>v?UI.badge(v,_gradeVariants[v]||'neutral'):'<span style="color:var(--dim)">--</span>' },
          { key:'_timeStr', label:'Time', width:90, render:(_,r)=>`<span style="color:var(--dim)">${r._dateStr} ${r._timeStr}</span>` },
        ],
      });
    }
    // Enrich trade rows
    const _exitLookup = {
      'profit_target':{label:'TARGET',variant:'green'}, 'profit_protected':{label:'PROTECTED',variant:'green'},
      'stop_loss':{label:'STOPPED',variant:'red'}, 'velocity_stop':{label:'V-STOP',variant:'red'},
      'breakeven_stop':{label:'BREAKEVEN',variant:'yellow'}, 'time_stop_0dte':{label:'TIME',variant:'yellow'},
      'max_hold_time':{label:'MAX HOLD',variant:'yellow'}, 'manual':{label:'MANUAL',variant:'neutral'},
      'theta_decay':{label:'THETA',variant:'red'}, 'trailing_stop':{label:'TRAIL',variant:'green'},
      'trailing_stop_remainder':{label:'TRAIL-R',variant:'green'}, 'dynamic_breakeven_protect':{label:'DEX-BE',variant:'yellow'},
    };
    const enrichedTrades = trades.map(t => {
      const optType = t.option_type || 'call';
      const strike = t.strike || '';
      const entryTime = t.entry_time ? new Date(t.entry_time) : null;
      const exitTime = t.exit_time ? new Date(t.exit_time) : null;
      return { ...t,
        _direction: optType === 'put' ? 'PUT' : 'CALL',
        _dirVariant: optType === 'put' ? 'red' : 'green',
        _sym: strike ? `${t.symbol||'SPY'} $${strike}` : (t.symbol||'SPY'),
        _holdMin: (entryTime && exitTime) ? Math.round((exitTime - entryTime) / 60000) : 0,
        _exitInfo: _exitLookup[t.exit_reason] || {label:(t.exit_reason||'CLOSED').toUpperCase(), variant:'neutral'},
        _exitReason: t.exit_reason || 'closed',
        _timeStr: entryTime ? entryTime.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',hour12:true}) : '',
        _dateStr: entryTime ? entryTime.toLocaleDateString('en-US',{month:'short',day:'numeric'}) : '',
      };
    });
    window._tradeHistTable.setData(enrichedTrades);
  }

  // ── Orders section — paper simulation note ──────────────────────────────
  const ordCountEl2 = document.getElementById('ordCountLabel');
  if(ordCountEl2) ordCountEl2.textContent = '';
  const ordWrap = document.getElementById('ordTableWrap');
  if(ordWrap){
    ordWrap.innerHTML = '<div style="padding:16px;text-align:center;color:var(--mut);font-size:9px;line-height:1.6">'
      + '📄 Paper simulation mode<br>No broker orders are placed.<br>'
      + 'All trade records are stored locally in the DB.</div>';
  }

  // ── Portfolio equity curve — built from closed simulation trades ────────
  renderEquityChart(_buildEquityCurve(closedTrades));
}

// Old _renderPositionRow and _renderTradeRow removed — now handled by DataTable component

// ═══ ORDER TABLE ROW RENDERER ═══
function _renderOrderRow(o){
  const displaySym = o.option_info
    ? `${o.option_info.root} $${o.option_info.strike} ${o.option_info.right}`
    : (o.symbol || '???');
  const isBuy = o.side === 'buy';
  const sideVariant = isBuy ? 'green' : 'red';
  const time = o.filled_at || o.created_at;
  const timeStr = time ? new Date(time).toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',hour12:true}) : '';
  const dateStr = time ? new Date(time).toLocaleDateString('en-US',{month:'short',day:'numeric'}) : '';

  const statusVariants = {
    filled: 'green', partially_filled: 'yellow',
    new: 'blue', accepted: 'blue', pending_new: 'blue',
    canceled: 'neutral', expired: 'neutral',
    rejected: 'red', replaced: 'yellow',
  };
  const statusVariant = statusVariants[o.status] || 'neutral';
  const statusLabel = (o.status || 'unknown').replace(/_/g,' ').toUpperCase();

  return `<tr>
    <td>${UI.badge((o.side||'buy').toUpperCase(), sideVariant)}</td>
    <td style="color:#fff;font-weight:600">${esc(displaySym)}</td>
    <td>${(o.type || 'limit').toUpperCase()}</td>
    <td>${o.qty || 1}</td>
    <td class="col-right">${o.limit_price ? '$'+parseFloat(o.limit_price).toFixed(2) : '--'}</td>
    <td class="col-right">${o.filled_avg_price ? '$'+parseFloat(o.filled_avg_price).toFixed(2) : '--'}</td>
    <td>${UI.badge(statusLabel, statusVariant)}</td>
    <td style="color:var(--dim)">${dateStr} ${timeStr}</td>
  </tr>`;
}

// Build an equity curve from a list of closed simulation trades.
// Returns array of {time: unix_seconds, equity: float} sorted ascending.
function _buildEquityCurve(closedTrades){
  const sorted = [...closedTrades]
    .filter(t => t.exit_time)
    .sort((a, b) => new Date(a.exit_time) - new Date(b.exit_time));

  if(!sorted.length) return [];

  let equity = STARTING_BALANCE;
  const points = [];
  let prevTs = 0;

  // Opening anchor point (1 second before first trade closes)
  const firstTs = Math.floor(new Date(sorted[0].exit_time).getTime() / 1000);
  points.push({ time: firstTs - 1, equity: STARTING_BALANCE });

  for(let i = 0; i < sorted.length; i++){
    equity += (sorted[i].pnl || 0);
    let ts = Math.floor(new Date(sorted[i].exit_time).getTime() / 1000);
    // Guarantee strictly ascending timestamps (LightweightCharts requirement)
    if(ts <= prevTs) ts = prevTs + 1;
    points.push({ time: ts, equity });
    prevTs = ts;
  }
  return points;
}

function renderEquityChart(points){
  const wrap = document.getElementById('equityChartWrap');
  if(!wrap) return; // Guard against missing DOM element
  if(!points.length){
    wrap.innerHTML = UI.empty('No portfolio history — equity curve builds as trades close');
    return;
  }
  if(!equityChart){
    equityChart = LightweightCharts.createChart(wrap, {
      autoSize:true,
      layout:{background:{type:'solid',color:T.surface1},textColor:T.dim,fontSize:T.fontSm,fontFamily:'monospace'},
      grid:{vertLines:{color:T.borderSubtle},horzLines:{color:T.borderSubtle}},
      crosshair:{mode:0},
      timeScale:{borderColor:T.border,timeVisible:false},
      rightPriceScale:{borderColor:T.border},
    });
    equitySeries = equityChart.addAreaSeries({
      lineColor:T.accent,topColor:'rgba(85,136,238,.25)',bottomColor:'rgba(85,136,238,.02)',lineWidth:2,
    });
  }
  const data = points.filter(p=>p.equity!=null).map(p=>({time:p.time,value:p.equity}));
  if(data.length){
    equitySeries.setData(data);
    requestAnimationFrame(()=>{ try{equityChart.timeScale().fitContent();}catch(e){} });
  }
}

