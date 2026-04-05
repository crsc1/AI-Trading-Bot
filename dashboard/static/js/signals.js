// ══════════════════════════════════════════════════════════════════════════
// ORDER FLOW SIGNAL ALERTS (sidebar)
// ══════════════════════════════════════════════════════════════════════════
function addFlowSignal(type, side, detail, confidence){
  const feed = document.getElementById('sigFeed');
  // Remove "waiting for engine" placeholder
  const empty = feed.querySelector('.empty-msg');
  if(empty) empty.remove();

  const sig = document.createElement('div');
  sig.className = `sig ${side}`;
  const now = new Date();
  const timeStr = now.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
  sig.innerHTML = `
    <div class="sig-hdr">
      <span class="sig-type ${side}">${type}</span>
      <span class="sig-conf" style="color:${confidence>70?'var(--grn)':confidence>40?'var(--ylw)':'var(--dim)'}">
        ${confidence}%
      </span>
      <span class="sig-time">${timeStr}</span>
    </div>
    <div class="sig-detail">${detail}</div>`;
  feed.prepend(sig);

  // Keep max 50 signals
  while(feed.children.length > 50) feed.lastChild.remove();
  S.signals.push({type,side,detail,confidence,time:now});
}

// Generate signals from market data analysis
async function analyzeFlowSignals(){
  if(!S.flowData || !S.flowData.cells) return;
  const cells = S.flowData.cells;
  if(!cells.length) return;

  const meta = S.flowData.meta || {};
  const totalVol = meta.total_volume || 0;
  const buyVol = meta.buy_volume || 0;
  const sellVol = meta.sell_volume || 0;

  // Delta imbalance signal
  if(totalVol > 100000){
    const delta = buyVol - sellVol;
    const deltaRatio = Math.abs(delta) / totalVol;
    if(deltaRatio > 0.15){
      const side = delta > 0 ? 'buy' : 'sell';
      const conf = Math.min(95, Math.round(deltaRatio * 300));
      addFlowSignal('Delta Imbalance', side,
        `${side==='buy'?'Buying':'Selling'} pressure: ${(deltaRatio*100).toFixed(1)}% skew (${formatDelta(delta)} delta)`, conf);
    }
  }

  // Large volume concentration at price level
  const maxCell = cells.reduce((a,b) => (b.vol||0) > (a.vol||0) ? b : a, cells[0]);
  if(maxCell && maxCell.vol > totalVol * 0.05){
    const pctOfTotal = ((maxCell.vol / totalVol) * 100).toFixed(1);
    const side = (maxCell.buy_vol || 0) > (maxCell.sell_vol || 0) ? 'buy' : 'sell';
    addFlowSignal('Volume Cluster', side,
      `${formatVol(maxCell.vol)} vol (${pctOfTotal}%) at $${maxCell.price?.toFixed(2) || '?'}`, 60);
  }

  // P/C ratio signal from options snapshot
  try{
    const today = new Date().toISOString().slice(0,10);
    // Use nearest expiration from cached sidebar data
    const pcr = parseFloat(document.getElementById('mPcr')?.textContent);
    if(pcr && !isNaN(pcr)){
      if(pcr > 1.5){
        addFlowSignal('Put Heavy', 'sell', `P/C ratio ${pcr.toFixed(2)} — elevated put buying suggests bearish hedging`, Math.min(80, Math.round(pcr * 30)));
      } else if(pcr < 0.5){
        addFlowSignal('Call Heavy', 'buy', `P/C ratio ${pcr.toFixed(2)} — call-dominated flow suggests bullish sentiment`, Math.min(80, Math.round((1/pcr) * 20)));
      }
    }
  }catch(e){}
}

// ══════════════════════════════════════════════════════════════════════════
// AI SIGNAL CARD HELPERS
// ══════════════════════════════════════════════════════════════════════════

function _renderFactors(factors){
  if(!factors || !factors.length) return '';
  const items = factors.slice(0, 5).map(f => {
    const dir = f.direction || 'neutral';
    return `<div class="ai-sig-factor"><span class="dir ${dir}">${dir === 'bullish' ? '+' : dir === 'bearish' ? '-' : '~'}</span>${f.name}: ${f.detail}</div>`;
  }).join('');
  const more = factors.length > 5 ? `<div class="ai-sig-factor" style="color:var(--mut)">+${factors.length - 5} more factors</div>` : '';
  return `<div class="ai-sig-factors">${items}${more}</div>`;
}

function _renderKeyLevels(levels){
  if(!levels) return '';
  const show = [];
  if(levels.vwap) show.push(`VWAP $${levels.vwap.toFixed(2)}`);
  if(levels.hod) show.push(`HOD $${levels.hod.toFixed(2)}`);
  if(levels.lod) show.push(`LOD $${levels.lod.toFixed(2)}`);
  if(levels.poc) show.push(`POC $${levels.poc.toFixed(2)}`);
  if(levels.pivot) show.push(`Pivot $${levels.pivot.toFixed(2)}`);
  if(!show.length) return '';
  return `<div class="ai-sig-levels">${show.map(s => `<span class="lvl">${s}</span>`).join('')}</div>`;
}

// ══════════════════════════════════════════════════════════════════════════
// AI SIGNAL POLLING — fetch from real /api/signals endpoints every 15s
// ══════════════════════════════════════════════════════════════════════════
let _lastSignalId = null;
let _knownSignalIds = new Set();

async function pollAISignal(){
  try {
    // 1. Fetch latest signal from /api/signals/latest
    const resp = await fetch('/api/signals/latest');
    if(!resp.ok) return;
    const sig = await resp.json();

    const feed = document.getElementById('sigFeed');
    if(!feed) return;

    if(sig && sig.signal !== 'NO_TRADE'){
      const sid = sig.id || sig.signal_id || sig.timestamp;

      const existing = feed.querySelector(`[data-signal-id="${sid}"]`);
      if(existing){
        _updateSignalPL(existing, sig);
      } else if(!_knownSignalIds.has(sid)){
        _knownSignalIds.add(sid);
        renderAISignalCard(sig);
      }
    } else if(sig && sig.signal === 'NO_TRADE'){
      // Show live engine status instead of stale "Waiting for engine..."
      const emptyMsg = feed.querySelector('.empty-msg');
      if(emptyMsg){
        const sess = sig.session || {};
        const phase = sess.phase || '';
        const mins = sess.minutes_to_close;
        let status = sig.reasoning || 'Scanning...';
        if(sess.past_hard_stop) status = `Hard stop active — ${mins != null ? mins + 'min' : ''} to close`;
        else if(phase === 'close_risk') status = `Close risk mode — ${mins != null ? mins + 'min' : ''} to close`;
        else if(sig.tier === 'DEVELOPING') status = 'Scanning for confluence...';
        emptyMsg.textContent = status;
      }
    }

    // Update signal count
    const countEl = document.getElementById('sigCount');
    if(countEl){
      const feed = document.getElementById('sigFeed');
      const cards = feed ? feed.querySelectorAll('.ai-signal-card').length : 0;
      countEl.textContent = `${cards} active`;
    }

    // P&L updates now handled by pollPhantomPL() every 2s — no duplicate fetching here

  } catch(e) {
    // Silent fail — expected when server not running
  }
}

// ══════════════════════════════════════════════════════════════════════════
// METRIC POLLING — fetch GEX, regime, events, sweeps, VPIN, sectors
// ══════════════════════════════════════════════════════════════════════════
let _metricPollTimer = null;

async function pollMetrics(){
  // Fetch all metric endpoints in parallel
  const endpoints = [
    { url: '/api/signals/gex', handler: _updateGexMetrics },
    { url: '/api/signals/regime', handler: _updateRegimeMetrics },
    { url: '/api/signals/events', handler: _updateEventMetrics },
    { url: '/api/signals/vanna-charm', handler: _updateVannaCharmMetrics },
    { url: '/api/signals/sweeps', handler: _updateSweepMetrics },
    { url: '/api/signals/vpin', handler: _updateVpinMetrics },
    { url: '/api/signals/sectors', handler: _updateSectorMetrics },
  ];

  const fetches = endpoints.map(async (ep) => {
    try {
      const resp = await fetch(ep.url);
      if(resp.ok){
        const data = await resp.json();
        ep.handler(data);
      }
    } catch(e){}
  });

  await Promise.allSettled(fetches);

  // Refresh chart overlay data if any overlay is active
  if(S.ind.levels || S.ind.gex || S.ind.pivots) fetchOverlayLevels();
}

function _updateGexMetrics(data){
  const gex = data.gex;
  const analytics = data.analytics;
  if(gex){
    const netGex = gex.net_gex || 0;
    const gexStr = (netGex >= 0 ? '+' : '') + (netGex / 1e9).toFixed(1) + 'B';
    const el = document.getElementById('mGex');
    if(el){ el.textContent = gexStr; el.className = 'mv ' + (netGex >= 0 ? 'grn' : 'red'); }

    const netDex = gex.net_dex || 0;
    const dexStr = (netDex >= 0 ? '+' : '') + (netDex / 1e6).toFixed(0) + 'M';
    const dEl = document.getElementById('mDex');
    if(dEl){ dEl.textContent = dexStr; dEl.className = 'mv ' + (netDex >= 0 ? 'grn' : 'red'); }

    // Cache GEX data for chart overlay and redraw if GEX overlay is active
    _overlayGexData = gex;
    if(S.ind.gex) _redrawPriceLines();
    if(data.greeks_source) console.log('[GEX] Greeks source:', data.greeks_source, '| net_gex:', netGex.toFixed(0));
  } else if(data.error){
    console.warn('[GEX]', data.error);
  }
  if(analytics){
    const pcrEl = document.getElementById('mPcr');
    if(pcrEl && analytics.pcr != null) pcrEl.textContent = analytics.pcr.toFixed(2);

    const mpEl = document.getElementById('mMaxPain');
    if(mpEl && analytics.max_pain != null) mpEl.textContent = '$' + parseFloat(analytics.max_pain).toFixed(0);

    const ivEl = document.getElementById('mIv');
    if(ivEl && analytics.iv_rank != null){
      ivEl.textContent = analytics.iv_rank.toFixed(0) + '%';
      ivEl.className = 'mv ' + (analytics.iv_rank > 70 ? 'red' : analytics.iv_rank > 40 ? 'ylw' : 'grn');
    }
  }
}

function _updateRegimeMetrics(data){
  const r = data.regime;
  if(!r) return;
  const regEl = document.getElementById('mRegime');
  if(regEl){
    const regime = r.regime || 'unknown';
    regEl.textContent = regime.replace('_', ' ').toUpperCase();
    regEl.className = 'mv ' + (regime === 'risk_on' ? 'grn' : regime === 'risk_off' ? 'red' : 'ylw');
  }
  const vixEl = document.getElementById('mVixStruct');
  if(vixEl && r.vix_structure) vixEl.textContent = r.vix_structure;

  const smEl = document.getElementById('mSizeMult');
  if(smEl && r.sizing_multiplier != null){
    smEl.textContent = r.sizing_multiplier.toFixed(1) + 'x';
    smEl.className = 'mv ' + (r.sizing_multiplier >= 1.0 ? 'grn' : r.sizing_multiplier >= 0.7 ? 'ylw' : 'red');
  }
}

function _updateEventMetrics(data){
  const ctx = data.event_context;
  if(!ctx) return;
  const modeEl = document.getElementById('mEventMode');
  if(modeEl){
    const mode = ctx.mode || 'normal';
    modeEl.textContent = mode.replace('_', ' ');
    modeEl.className = 'mv ' + (mode === 'normal' ? 'grn' : mode === 'pre_event' ? 'red' : 'ylw');
  }
  const nextEl = document.getElementById('mNextEvent');
  if(nextEl){
    if(ctx.next_event){
      const name = ctx.next_event.name || 'Event';
      const mins = ctx.minutes_to_next != null ? Math.round(ctx.minutes_to_next) + 'm' : '';
      nextEl.textContent = name.slice(0, 12) + (mins ? ' ' + mins : '');
    } else {
      nextEl.textContent = 'None';
      nextEl.className = 'mv';
    }
  }
}

function _updateVannaCharmMetrics(data){
  const vc = data.vanna_charm;
  if(!vc) return;
  const vanEl = document.getElementById('mVanna');
  if(vanEl){
    const regime = vc.vanna_regime || 'neutral';
    vanEl.textContent = regime.replace('_', ' ');
    vanEl.className = 'mv ' + (regime.includes('bullish') ? 'grn' : regime.includes('bearish') ? 'red' : '');
  }
  const chEl = document.getElementById('mCharm');
  if(chEl){
    const regime = vc.charm_regime || 'neutral';
    const accel = vc.charm_acceleration ? ' ACC' : '';
    chEl.textContent = regime.replace('_', ' ') + accel;
    chEl.className = 'mv ' + (regime.includes('buying') ? 'grn' : regime.includes('selling') ? 'red' : '');
  }
}

function _updateSweepMetrics(data){
  const sw = data.sweeps;
  if(!sw) return;
  const el = document.getElementById('mSweeps');
  if(!el) return;
  const bc = sw.bullish_count || 0;
  const brc = sw.bearish_count || 0;
  if(bc === 0 && brc === 0){
    el.textContent = 'None';
    el.className = 'mv';
  } else {
    el.textContent = `${bc}B / ${brc}S`;
    el.className = 'mv ' + (bc > brc ? 'grn' : brc > bc ? 'red' : 'ylw');
  }
}

function _updateVpinMetrics(data){
  const vp = data.vpin;
  if(!vp) return;
  const el = document.getElementById('mVpin');
  if(!el) return;
  const val = vp.vpin != null ? (vp.vpin * 100).toFixed(0) + '%' : '--';
  const level = vp.toxicity_level || 'normal';
  el.textContent = val + ' ' + level;
  el.className = 'mv ' + (level === 'high' ? 'red' : level === 'elevated' ? 'ylw' : 'grn');
}

function _updateSectorMetrics(data){
  const sec = data.sectors;
  if(!sec) return;
  const el = document.getElementById('mSectors');
  if(!el) return;
  const bias = sec.composite_bias || 0;
  const div = sec.divergence_count || 0;
  if(div === 0){
    el.textContent = 'Aligned';
    el.className = 'mv';
  } else {
    el.textContent = `${div} div ${bias > 0 ? 'bull' : bias < 0 ? 'bear' : 'mixed'}`;
    el.className = 'mv ' + (bias > 0 ? 'grn' : bias < 0 ? 'red' : 'ylw');
  }
}

function startMetricPolling(){
  if(_metricPollTimer) return;
  _metricPollTimer = setInterval(pollMetrics, 30000); // Every 30s
  setTimeout(pollMetrics, 3000); // First poll after 3s
}
function stopMetricPolling(){
  if(_metricPollTimer){ clearInterval(_metricPollTimer); _metricPollTimer = null; }
}

function _updateSignalPL(card, sig){
  // Update the P/L display on an existing card — enhanced Robinhood-style
  const plEl = card.querySelector('.ai-sig-pl');
  if(!plEl) return;

  const pnl = sig.pnl != null ? sig.pnl : (sig.pnl_dollars || 0);
  const pnlPct = sig.pnl_pct != null ? sig.pnl_pct : (sig.pnl_percent || 0);
  const peakPnl = sig.peak_pnl || 0;
  const peakPnlPct = sig.peak_pnl_pct || 0;
  const status = sig.status || 'LIVE';
  const targetDist = sig.target_distance_pct || 0;
  const stopDist = sig.stop_distance_pct || 0;
  const heldSec = sig.held_seconds || 0;
  const wasTraded = sig.was_traded || false;
  const targetHitAt = sig.target_hit_at || null;

  const cls = pnl >= 0 ? 'grn' : 'red';
  const sign = pnl >= 0 ? '+' : '';

  // Format hold timer
  const mins = Math.floor(heldSec / 60);
  const secs = heldSec % 60;
  const holdStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;

  // Peak P/L line — show "MISSED" warning if peak was significantly positive but retreated
  let peakHtml = '';
  if(peakPnl > 0 && pnl < peakPnl * 0.5 && status === 'LIVE'){
    peakHtml = `<div class="ai-sig-pl-peak missed">MISSED +$${peakPnl.toFixed(2)} (${peakPnlPct.toFixed(1)}%)</div>`;
  } else if(peakPnl > 0){
    peakHtml = `<div class="ai-sig-pl-peak">Best: +$${peakPnl.toFixed(2)}</div>`;
  }

  // Progress bar — green toward target, red toward stop
  let barHtml = '';
  if(status === 'LIVE'){
    if(pnl >= 0){
      barHtml = `<div class="ai-sig-pl-bar"><div class="ai-sig-pl-bar-fill grn" style="width:${Math.min(100, targetDist)}%"></div></div>`;
    } else {
      barHtml = `<div class="ai-sig-pl-bar"><div class="ai-sig-pl-bar-fill red" style="width:${Math.min(100, stopDist)}%"></div></div>`;
    }
  }

  // Status badge
  let statusBadge = '';
  if(status === 'LIVE'){
    statusBadge = `<span class="ai-sig-status-badge live"><span class="pulse"></span>LIVE</span>`;
  } else if(status === 'TARGET_HIT'){
    statusBadge = `<span class="ai-sig-status-badge target-hit">✓ TARGET HIT</span>`;
  } else if(status === 'STOP_HIT'){
    statusBadge = `<span class="ai-sig-status-badge stop-hit">✗ STOP HIT</span>`;
  } else if(status === 'MISSED'){
    statusBadge = `<span class="ai-sig-status-badge missed">⚠ MISSED</span>`;
  }

  // Traded badge
  const tradedBadge = wasTraded ? `<span class="ai-sig-status-badge traded">TRADED</span>` : '';

  plEl.innerHTML = `
    <div class="ai-sig-pl-wrap">
      <div class="ai-sig-pl-main"><span class="val ${cls}">${sign}$${pnl.toFixed(2)} (${sign}${pnlPct.toFixed(1)}%)</span></div>
      ${peakHtml}
      ${barHtml}
      <div class="ai-sig-pl-hold">${holdStr}</div>
    </div>`;

  // Update status area in the card header
  const statusEl = card.querySelector('.ai-sig-status');
  if(statusEl) statusEl.innerHTML = `${statusBadge} ${tradedBadge}`;

  // Adjust card opacity for closed states
  if(status === 'TARGET_HIT'){
    card.style.opacity = '0.85';
  } else if(status === 'STOP_HIT' || status === 'MISSED'){
    card.style.opacity = '0.55';
  } else {
    card.style.opacity = '1';
  }
}

// ══════════════════════════════════════════════════════════════════════════
// PHANTOM P/L POLLING — Robinhood-style real-time P/L on every signal card
// ══════════════════════════════════════════════════════════════════════════
let _phantomPLTimer = null;

async function pollPhantomPL(){
  try {
    const resp = await fetch('/api/signals/phantom-pl');
    if(!resp.ok) return;
    const data = await resp.json();
    const entries = data.entries || [];
    const feed = document.getElementById('sigFeed');
    if(!feed) return;

    for(const entry of entries){
      const card = feed.querySelector(`[data-signal-id="${entry.signal_id}"]`);
      if(card){
        _updateSignalPL(card, entry);
        // Also update level_note if present
        if(entry.level_note){
          let noteEl = card.querySelector('.ai-sig-level-note');
          if(!noteEl){
            noteEl = document.createElement('div');
            noteEl.className = 'ai-sig-level-note';
            noteEl.style.cssText = 'font-size:7px;color:var(--ylw);margin-top:2px;padding:2px 4px;background:rgba(255,179,0,.06);border-radius:2px';
            const grid = card.querySelector('.ai-sig-grid');
            if(grid) grid.parentNode.insertBefore(noteEl, grid.nextSibling);
          }
          noteEl.textContent = entry.level_note;
        }
      }
    }
  } catch(e){
    // Silent fail — don't spam console on network blip
  }
}

function startPhantomPLPolling(){
  if(_phantomPLTimer) return;
  _phantomPLTimer = setInterval(pollPhantomPL, 2000);
  setTimeout(pollPhantomPL, 1000); // First poll after 1s
}
function stopPhantomPLPolling(){
  if(_phantomPLTimer){ clearInterval(_phantomPLTimer); _phantomPLTimer = null; }
}

// Agent status bar removed — metric polling handles all status display now

function renderAISignalCard(sig){
  const feed = document.getElementById('sigFeed');
  if(!feed) return;

  const isCall = sig.signal === 'BUY_CALL';
  const isPut = sig.signal === 'BUY_PUT';
  const isNoTrade = sig.signal === 'NO_TRADE';

  // Skip NO_TRADE cards entirely
  if(isNoTrade) return;

  // Remove empty-msg placeholder
  const emptyEl = feed.querySelector('.empty-msg');
  if(emptyEl) emptyEl.remove();

  // Cap signal cards at 15 — remove oldest (bottom) to prevent unbounded growth
  const existingCards = feed.querySelectorAll('.ai-signal-card');
  if(existingCards.length >= 15){
    for(let i = existingCards.length - 1; i >= 14; i--){
      existingCards[i].remove();
    }
  }

  const empty = feed.querySelector('.empty-msg');
  if(empty) empty.remove();

  const side = isCall ? 'call' : isPut ? 'put' : 'no-trade';
  const actionText = isCall ? 'BUY CALL' : isPut ? 'BUY PUT' : 'NO TRADE';
  const confPct = Math.round((sig.confidence || 0) * 100);
  const confClass = confPct >= 75 ? 'high' : confPct >= 55 ? 'med' : 'low';
  const tier = sig.tier || 'DEVELOPING';

  const card = document.createElement('div');
  card.className = `ai-signal-card ${side} flash-new`;
  card.setAttribute('data-signal-id', sig.id || sig.signal_id || sig.timestamp || '');
  card.setAttribute('data-added-at', String(Date.now()));
  // Remove flash after animation
  setTimeout(() => card.classList.remove('flash-new'), 800);

  // Date/time stamp
  const now = new Date();
  const dateStr = now.toLocaleDateString('en-US',{month:'short',day:'numeric'});
  const timeStr = now.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
  const fullTimeStamp = `${dateStr} ${timeStr}`;

  const sym = sig.symbol || S.sym || 'SPY';
  const strike = (sig.strike != null && sig.strike > 0) ? sig.strike : '--';
  // Format expiry: YYYYMMDD → M/D or "today"
  let expiry = '--';
  if(sig.expiry){
    const raw = String(sig.expiry).replace(/-/g,'');
    if(raw.length === 8){
      const m = parseInt(raw.substring(4,6),10);
      const d = parseInt(raw.substring(6,8),10);
      const today = new Date();
      const isToday = (m === today.getMonth()+1 && d === today.getDate());
      expiry = isToday ? '0DTE' : `${m}/${d}`;
    } else { expiry = sig.expiry; }
  }
  const optType = isCall ? 'C' : 'P';
  const instrument = `${sym} ${strike}${optType} ${expiry}`;
  const entry = sig.entry_price ? '$' + sig.entry_price.toFixed(2) : '--';
  const target = sig.target_price ? '$' + sig.target_price.toFixed(2) : '--';
  const stop = sig.stop_price ? '$' + sig.stop_price.toFixed(2) : '--';
  const riskPct = sig.risk_pct ? sig.risk_pct.toFixed(1) + '%' : '--';
  const maxContracts = sig.risk_management?.max_contracts || sig.contracts || '--';
  const delta = (sig.option_data?.delta || sig.option_delta) != null ? (sig.option_data?.delta || sig.option_delta).toFixed(2) : '--';
  const rrRatio = sig.target_price && sig.stop_price && sig.entry_price && sig.entry_price !== sig.stop_price
    ? ((sig.target_price - sig.entry_price) / (sig.entry_price - sig.stop_price)).toFixed(1) : '--';

  // P/L tracking
  const pnl = sig.pnl_dollars || 0;
  const pnlPct = sig.pnl_percent || 0;
  const status = sig.status || 'OPEN';
  const pnlCls = pnl >= 0 ? 'grn' : 'red';
  const pnlSign = pnl >= 0 ? '+' : '';

  // Phase 3A/3B context badges
  let metaBadges = '';
  if(sig.regime){
    const r = sig.regime.regime || '';
    const rClass = r === 'risk_on' ? 'regime-on' : r === 'risk_off' ? 'regime-off' : 'regime-trans';
    metaBadges += `<span class="badge ${rClass}">${r.replace('_',' ').toUpperCase()}</span>`;
  }
  if(sig.sweeps){
    const sw = sig.sweeps;
    const bc = sw.bullish_count || 0;
    const brc = sw.bearish_count || 0;
    if(bc > 0 || brc > 0){
      metaBadges += `<span class="badge sweep">${bc}B/${brc}S sweeps</span>`;
    }
  }
  if(sig.event_context){
    const ec = sig.event_context;
    if(ec.mode && ec.mode !== 'normal'){
      metaBadges += `<span class="badge event">${ec.mode.replace('_',' ')}</span>`;
    }
  }
  if(sig.vpin){
    const vp = sig.vpin;
    if(vp.toxicity_level === 'high' || vp.toxicity_level === 'elevated'){
      metaBadges += `<span class="badge" style="background:rgba(255,179,0,.1);color:var(--ylw)">VPIN ${(vp.vpin*100).toFixed(0)}%</span>`;
    }
  }

  // Factors (show top 5)
  const factors = sig.factors || [];
  const factorHtml = factors.slice(0, 5).map(f => {
    const dir = f.direction || 'neutral';
    const color = dir === 'bullish' ? 'bullish' : dir === 'bearish' ? 'bearish' : '';
    return `<div class="ai-sig-factor"><span class="dir ${color}">${dir === 'bullish' ? '+' : dir === 'bearish' ? '-' : '~'}</span>${f.name}: ${f.detail || ''}</div>`;
  }).join('');
  const moreFactors = factors.length > 5 ? `<div class="ai-sig-factor" style="color:var(--mut)">+${factors.length - 5} more</div>` : '';

  // Build exit rules display
  const exitRules = [];
  if(sig.target_price) exitRules.push({label:`Target ${target}`, active: false});
  if(sig.stop_price) exitRules.push({label:`Stop ${stop}`, active: false});
  exitRules.push({label:'Max hold 45m', active: false});
  exitRules.push({label:'Hard stop 3:00 PM', active: false});
  if(sig.levels){
    if(sig.levels.vwap) exitRules.push({label:`VWAP $${parseFloat(sig.levels.vwap).toFixed(0)}`, active: false});
    if(sig.levels.hod) exitRules.push({label:`HOD $${parseFloat(sig.levels.hod).toFixed(0)}`, active: false});
  }
  const exitHtml = exitRules.slice(0,6).map(r =>
    `<div class="exit-rule"><span class="dot ${r.active?'active':'pending'}"></span>${r.label}</div>`
  ).join('');

  card.innerHTML = `
    <div class="ai-sig-top">
      <span class="ai-sig-action ${side}">${actionText}</span>
      <span class="ai-sig-tier ${tier}">${tier}</span>
      <span class="ai-sig-status"><span class="ai-sig-status-badge live"><span class="pulse"></span>LIVE</span></span>
      <span class="ai-sig-confidence ${confClass}">${confPct}%</span>
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
      <div class="ai-sig-instrument" style="margin-bottom:0">${instrument}</div>
      <span style="font-size:8px;color:var(--mut)">${fullTimeStamp}</span>
    </div>
    ${metaBadges ? `<div class="ai-sig-meta">${metaBadges}</div>` : ''}
    <div class="ai-sig-grid">
      <div class="ai-sig-cell"><div class="lbl">Entry</div><div class="val">${entry}</div></div>
      <div class="ai-sig-cell"><div class="lbl">Target</div><div class="val grn">${target}</div></div>
      <div class="ai-sig-cell"><div class="lbl">Stop</div><div class="val red">${stop}</div></div>
      <div class="ai-sig-cell"><div class="lbl">R:R</div><div class="val ylw">${rrRatio === '--' ? '--' : rrRatio + 'x'}</div></div>
      <div class="ai-sig-cell"><div class="lbl">P/L</div><div class="ai-sig-pl"><div class="ai-sig-pl-wrap"><div class="ai-sig-pl-main"><span class="val ${pnlCls}">${pnlSign}$${pnl.toFixed(2)}</span></div><div class="ai-sig-pl-hold">0s</div></div></div></div>
      <div class="ai-sig-cell"><div class="lbl">${maxContracts}x · Δ${delta}</div><div class="val">${riskPct}</div></div>
    </div>
    ${(sig.risk_management && sig.risk_management.level_note) ? `<div class="ai-sig-level-note" style="font-size:7px;color:var(--ylw);margin-top:2px;padding:2px 4px;background:rgba(255,179,0,.06);border-radius:2px">${sig.risk_management.level_note}</div>` : ''}
    <div class="ai-sig-exits"><div style="grid-column:1/-1;font-size:7px;color:var(--mut);font-weight:600;margin-bottom:1px">EXIT RULES</div>${exitHtml}</div>
    <div class="ai-sig-reasoning" style="margin-top:4px">${sig.reasoning || ''}</div>
    <div class="ai-sig-time">${sig.confluence_count || 0} factors · ${fullTimeStamp}</div>`;

  // Play alert sound for new signals
  _playSignalAlert(isCall ? 'call' : 'put');

  // Opacity handled by _updateSignalPL via phantomPL polling

  // Prepend new card, keep max 10
  feed.prepend(card);
  while(feed.children.length > 10){
    const removed = feed.lastChild;
    if(removed){
      const removedId = removed.getAttribute('data-signal-id');
      if(removedId) _knownSignalIds.delete(removedId);
      removed.remove();
    }
  }
}

// Start AI signal polling (every 15s during active trading)
let _aiSignalPollTimer = null;
function startAISignalPolling(){
  if(_aiSignalPollTimer) return;
  _aiSignalPollTimer = setInterval(pollAISignal, 15000);
  setTimeout(pollAISignal, 5000);
}
function stopAISignalPolling(){
  if(_aiSignalPollTimer){ clearInterval(_aiSignalPollTimer); _aiSignalPollTimer = null; }
}
// ══════════════════════════════════════════════════════════════════════════
// SIGNAL ALERT — audio beep + visual flash on new signal
// ══════════════════════════════════════════════════════════════════════════

let _audioCtx = null;
function _playSignalAlert(type){
  try {
    if(!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = _audioCtx.createOscillator();
    const gain = _audioCtx.createGain();
    osc.connect(gain);
    gain.connect(_audioCtx.destination);
    // Call = rising tone, Put = falling tone
    const isCall = type === 'call';
    osc.type = 'sine';
    osc.frequency.setValueAtTime(isCall ? 660 : 440, _audioCtx.currentTime);
    osc.frequency.linearRampToValueAtTime(isCall ? 880 : 330, _audioCtx.currentTime + 0.15);
    gain.gain.setValueAtTime(0.12, _audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, _audioCtx.currentTime + 0.3);
    osc.start(_audioCtx.currentTime);
    osc.stop(_audioCtx.currentTime + 0.3);

    // Visual flash on signals widget header
    const hdr = document.querySelector('#wSignals .sb-widget-hdr');
    if(hdr){
      hdr.style.transition = 'background 0.3s';
      hdr.style.background = isCall ? 'rgba(38,166,154,0.25)' : 'rgba(239,83,80,0.25)';
      setTimeout(() => { hdr.style.background = ''; }, 600);
    }
  } catch(e){ /* AudioContext may be blocked until user interaction — silent fail */ }
}

// ══════════════════════════════════════════════════════════════════════════
// STATS BANNER — poll scorecard and populate win/loss metrics
// ══════════════════════════════════════════════════════════════════════════

let _statsBannerTimer = null;
async function pollStatsBanner(){
  try {
    const resp = await fetch('/api/signals/scorecard?period=today');
    if(!resp.ok) return;
    const d = await resp.json();
    if(d.error) return;
    _renderStatsBanner(d);
  } catch(e){ /* silent */ }
}

function _renderStatsBanner(d){
  const basic = d.basic || d;
  const advanced = d.advanced || {};
  const tc = basic.trades ?? basic.total_trades ?? basic.trade_count ?? 0;

  // Win rate — update account bar
  const wr = basic.win_rate ?? advanced.win_rate;
  const wrEl = document.getElementById('sbAccWinRate');
  if(wrEl){
    if(tc === 0){
      wrEl.textContent = '--%';
      wrEl.className = 'sa-v text-muted';
    } else if(wr != null){
      wrEl.textContent = wr.toFixed(0) + '%';
      wrEl.className = 'sa-v ' + (wr >= 60 ? 'text-positive' : wr >= 40 ? 'text-warning' : 'text-negative');
    }
  }

  // Day P&L — update account bar
  const pnl = basic.net_pnl ?? basic.total_pnl ?? 0;
  const plEl = document.getElementById('sbAccDayPL');
  if(plEl){
    plEl.textContent = (pnl >= 0 ? '+$' : '-$') + Math.abs(pnl).toFixed(2);
    plEl.className = 'sa-v ' + (pnl >= 0 ? 'text-positive' : 'text-negative');
  }

  // Open position count for account bar
  const opEl = document.getElementById('sbAccOpen');
  if(opEl) opEl.textContent = basic.open_positions ?? basic.open_count ?? '0';

}

function startStatsBannerPoll(){
  if(_statsBannerTimer) return;
  _statsBannerTimer = setInterval(pollStatsBanner, 20000); // Every 20s
  setTimeout(pollStatsBanner, 3000); // First poll after 3s
}

// ══════════════════════════════════════════════════════════════════════════
// AUTO-TRADER POSITIONS — now handled by unified refreshPositionsTab()
// Stubs kept for backward compatibility with init code
// ══════════════════════════════════════════════════════════════════════════
function pollAutoTraderPositions(){} // No-op: unified into refreshPositionsTab
function _renderAutoTraderPositions(){} // No-op: unified into refreshPositionsTab
function startAutoPosPoll(){} // No-op: polling handled by refreshPositionsTab interval

