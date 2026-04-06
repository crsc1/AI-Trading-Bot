// ══════════════════════════════════════════════════════════════════════════
// INIT
// ══════════════════════════════════════════════════════════════════════════
function init(){
  // Load settings first (async) — updates STARTING_BALANCE before positions tab refreshes
  if(typeof loadSettings === 'function') loadSettings();
  // Restore stacked widget collapse states
  restoreWidgetStates();
  // Set initial widget context
  updateWidgetContext('combined');
  initCombinedCharts();
  initFullCandleCharts();
  // Restore indicator state from localStorage (must be after chart series are created)
  indRegistry.init();
  // Default to intraday 5m timeframe (always — daily is accessible via D button)
  S.tf = '5Min';
  document.querySelectorAll('#tfGroup .tb-btn').forEach(b=>b.classList.toggle('active',b.dataset.tf==='5Min'));
  document.querySelectorAll('.top-bar .bar-btn').forEach(b => b.classList.toggle('active', parseInt(b.dataset.bar)===5));
  // Initialize session label and left nav state
  _updateSessionLabel();
  setInterval(_updateSessionLabel, 60000); // Update session label every minute
  _startMarketCountdown();               // Start per-second countdown
  loadHistory('5Min');
  loadOrderFlow();
  loadExpirations();
  // Load options snapshot for sidebar metrics (P/C ratio, Max Pain, IV)
  loadSidebarOptions();
  connectWS();
  connectDashboardWS();  // SIP stream via Python backend
  // Load persisted ticks from SQLite for session continuity across page refreshes
  _loadPersistedTicks(S.sym);
  // Keyboard shortcuts
  document.addEventListener('keydown', handleKey);
  // Staggered polling timers — offsets prevent simultaneous network bursts
  // Each timer is staggered by a few seconds so requests don't pile up on the same tick.
  setInterval(refreshLiveData, 5000);                                              // t+0s, every 5s
  setTimeout(() => setInterval(() => {                                             // t+2s, every 60s
    if(isMarketHours()) loadOrderFlow();
  }, 60000), 2000);
  setTimeout(() => setInterval(() => {                                             // t+4s, every 30s
    if(isMarketHours() && S.tf !== '1D' && S.tf !== 'live') loadHistory();
  }, 30000), 4000);
  setTimeout(() => setInterval(analyzeFlowSignals, 30000), 7000);                  // t+7s, every 30s
  setTimeout(() => setInterval(() => {                                             // t+5s, every 5s for live P&L
    if(S.activeTab === 'agent' && _activeAgentTab === 'positions'){ refreshPositionsTab(); pollBeatSpy(); }
  }, 5000), 5000);
  // Fallback: if engine WS doesn't connect within 3s, start REST polling
  setTimeout(() => {
    if(!S.connected){
      console.log('Engine WS not connected — starting Alpaca REST polling (Algo Trader Plus)');
      startRestPolling();
    }
  }, 3000);

  // ── PHASE 1 COMPONENT FRAMEWORK: Enhance existing tables ──
  // TableUpgrade progressively enhances existing tables with resizable columns
  // and optional sorting. Existing render functions keep writing to <tbody> as before.
  setTimeout(() => {
    if(typeof TableUpgrade !== 'undefined'){
      // Agent tab: History table
      const agHist = document.getElementById('agHistTable');
      if(agHist) TableUpgrade.enhance(agHist, { resizable: true, sortable: true, persistKey: 'agHist' });

      // Agent tab: Signal table
      const agSig = document.getElementById('agSigTable');
      if(agSig) TableUpgrade.enhance(agSig, { resizable: true, sortable: true, persistKey: 'agSig' });

      // Agent tab: Decision log table
      const agDec = document.getElementById('agDecTable');
      if(agDec) TableUpgrade.enhance(agDec, { resizable: true, sortable: true, persistKey: 'agDec' });

      console.log('[UI] TableUpgrade: Enhanced agent tables with resizable columns + sorting');
    }
  }, 500);

  // ── SECTION RESIZE: Vertical drag handles on table sections ──
  // Lets user drag the bottom edge of a table section to make it taller/shorter.
  // Persists height to localStorage keyed by data-resize-key.
  (function initSectionResize(){
    // Restore persisted heights
    document.querySelectorAll('.pos-section.resizable').forEach(section => {
      const key = section.dataset.resizeKey;
      if(!key) return;
      try{
        const h = localStorage.getItem('sec_h_' + key);
        if(h) section.style.setProperty('--section-h', h + 'px');
      }catch(e){}
    });

    let _resizing = null;

    document.addEventListener('mousedown', (e) => {
      const handle = e.target.closest('.section-resize-handle');
      if(!handle) return;
      e.preventDefault();
      const section = handle.closest('.pos-section.resizable');
      if(!section) return;
      const wrap = section.querySelector('.pos-table-wrap');
      if(!wrap) return;

      _resizing = {
        section,
        wrap,
        key: section.dataset.resizeKey,
        startY: e.clientY,
        startH: wrap.getBoundingClientRect().height,
      };
      document.body.style.cursor = 'ns-resize';
      document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', (e) => {
      if(!_resizing) return;
      const dy = e.clientY - _resizing.startY;
      const maxH = Math.min(500, window.innerHeight * 0.45);
      const newH = Math.max(80, Math.min(maxH, _resizing.startH + dy));
      _resizing.section.style.setProperty('--section-h', newH + 'px');
    });

    document.addEventListener('mouseup', () => {
      if(!_resizing) return;
      // Persist
      const key = _resizing.key;
      if(key){
        const h = _resizing.wrap.getBoundingClientRect().height;
        try{ localStorage.setItem('sec_h_' + key, Math.round(h)); }catch(e){}
      }
      _resizing = null;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    });

    console.log('[UI] Section resize: Initialized drag handles for resizable table sections');
  })();
}

function getMarketSession(){
  // Returns: 'regular', 'pre-market', 'after-hours', or 'closed'
  const now = new Date();
  const et = new Date(now.toLocaleString('en-US',{timeZone:'America/New_York'}));
  const h = et.getHours(), m = et.getMinutes();
  const day = et.getDay();
  if(day===0||day===6) return 'closed'; // weekend
  const mins = h*60+m;
  if(mins >= 570 && mins <= 960) return 'regular';       // 9:30 - 16:00
  if(mins >= 240 && mins < 570) return 'pre-market';     // 4:00 - 9:30
  if(mins > 960 && mins <= 1200) return 'after-hours';   // 16:00 - 20:00
  return 'closed'; // 20:00 - 4:00
}
function isMarketHours(){
  return getMarketSession() === 'regular';
}
function isTradingActive(){
  // Returns true during any session where trades can happen
  return getMarketSession() !== 'closed';
}

// REST polling fallback: fetch recent trades via SIP REST when engine WS is down
let restPollTimer = null;
let restPollCount = 0;
function startRestPolling(){
  if(restPollTimer) return;
  console.log('Starting SIP REST polling');
  pollRecentTrades(); // immediate first poll
  // Poll every 1 second for smoother flow when WS is unavailable
  restPollTimer = setInterval(pollRecentTrades, 1000);
}
function stopRestPolling(){
  if(restPollTimer){ clearInterval(restPollTimer); restPollTimer = null; }
}
async function pollRecentTrades(){
  // Only stop REST polling if engine is actively delivering ticks (not just connected with stale data)
  if(S.connected && S.ticks > 0){ stopRestPolling(); return; }
  const session = getMarketSession();
  if(session === 'closed'){
    document.getElementById('dotData').className='dot dim';
    document.getElementById('lblData').textContent = 'Market Closed';
    return;
  }
  try{
    const r = await fetch(`/api/orderflow/trades/recent?symbol=${S.sym}&limit=500&feed=sip`);
    const d = await r.json();
    if(d.error){
      document.getElementById('lblData').textContent = 'Data: ' + d.error.substring(0,40);
      return;
    }
    if(d.trades && d.trades.length){
      let newTicks = 0;
      d.trades.forEach(t => {
        const ts = t.t ? new Date(t.t).getTime() : Date.now();
        // Only add if newer than our latest tick
        if(!liveFlow.ticks.length || ts > liveFlow.ticks[liveFlow.ticks.length-1].ts){
          handleFlowTick(t.p, t.s, t.side || null, ts);
          newTicks++;
        }
      });
      restPollCount += newTicks;
      if(newTicks > 0){
        document.getElementById('dotData').className='dot on';
        const sessionTag = session==='pre-market'?' Pre-Mkt':session==='after-hours'?' AH':'';
        document.getElementById('lblData').textContent = `LIVE${sessionTag} — SIP (${restPollCount.toLocaleString()} ticks)`;
      }
      // Update price from latest trade
      if(d.trades.length > 0){
        const lastTrade = d.trades[d.trades.length-1];
        if(lastTrade.p > 0){
          S.lastPrice = lastTrade.p;
          updatePrice(lastTrade.p, S.prevClose || lastTrade.p);
        }
      }
    }
  }catch(e){ console.debug('REST poll failed:', e); }
}

// ══════════════════════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════════════════════
// ET TIMEZONE SHIFT — LWC treats all timestamps as UTC. We shift bar
// timestamps so LWC's internal tick placement lands at ET-natural times
// (09:30, 10:00, 10:30 …) instead of UTC-natural ones (12:00, 16:00 …).
// ══════════════════════════════════════════════════════════════════════════
let _etOffset = 0;  // cached offset in seconds (negative for behind UTC)

/**
 * Compute the seconds to ADD to a UTC timestamp so that
 * new Date(shifted * 1000).getUTCHours/Minutes returns ET local time.
 * E.g. during EDT (UTC-4): offset = -4*3600 → but we WANT the reverse:
 * we want 09:30 ET to look like 09:30 UTC, so we ADD the negative of the
 * UTC offset.  Result: +4h during EDT, +5h during EST.
 */
function _getETOffsetSec(utcSec) {
  const d = new Date(utcSec * 1000);
  const p = {};
  new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    year:'numeric', month:'2-digit', day:'2-digit',
    hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false
  }).formatToParts(d).forEach(pt => { p[pt.type] = parseInt(pt.value); });
  const h = p.hour === 24 ? 0 : p.hour;
  const etAsUTC = Date.UTC(p.year, p.month - 1, p.day, h, p.minute, p.second || 0);
  return Math.floor(etAsUTC / 1000) - utcSec;
}
