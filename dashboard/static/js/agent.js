// ══════════════════════════════════════════════════════════════════════════
// AUTONOMOUS TRADER — UI control and status polling
// ══════════════════════════════════════════════════════════════════════════

let _autoTradePollTimer = null;

async function toggleAutoTrade(enable){
  try{
    const url = enable ? '/api/pm/enable' : '/api/pm/disable';
    const resp = await fetch(url, {method:'POST'});
    if(resp.ok){
      const data = await resp.json();
      console.log('[AutoTrade]', enable ? 'START' : 'STOP', data);
      UI.toast('Auto-trade ' + (enable ? 'started' : 'stopped'), enable ? 'success' : 'info');
      // Immediate status refresh
      pollAutoTradeStatus();
    } else {
      const msg = `Auto-trade ${enable ? 'start' : 'stop'} failed (${resp.status})`;
      UI.toast(msg, 'error');
      console.warn('[AutoTrade] Request failed:', resp.status);
    }
  }catch(e){
    UI.toast('Auto-trade error — server unreachable', 'error');
    console.error('[AutoTrade] Toggle error:', e);
  }
}

async function pollAutoTradeStatus(){
  try{
    const resp = await fetch('/api/pm/status');
    if(!resp.ok) return;
    const d = await resp.json();
    _renderAutoTradeStatus(d);
    // Also render decisions from the same response (avoids double-fetch)
    _renderAgentDecisions(d.decisions || []);
  }catch(e){ console.debug('[PM] Status poll failed:', e); }
}

function _renderAutoTradeStatus(d){
  if(!d || typeof d !== 'object') return; // Guard against bad data

  const running = d.running && d.enabled;
  const cfg = d.config || {};
  const ds = d.stats || {};
  const pnl = d.daily_pnl || 0;
  const inHours = d.in_trading_hours;

  // ── Agent tab top bar ──────────────────────────────────────────
  const agPulse = document.getElementById('agentATpulse');
  const agStatus = document.getElementById('agentATstatus');
  if(agPulse) agPulse.style.background = running ? 'var(--grn)' : '#666';
  if(agStatus){ agStatus.textContent = running ? 'ACTIVE' : 'disabled'; agStatus.style.color = running ? 'var(--grn)' : 'var(--mut)'; }
  // mode is always "Paper Simulation" — static label in toolbar, no dynamic update needed
  const agPnlEl = document.getElementById('agentAtDayPnl');
  if(agPnlEl){ agPnlEl.textContent = (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2); agPnlEl.style.color = pnl >= 0 ? 'var(--grn)' : 'var(--red)'; }
  _setText('agentAtOpenPos', d.open_positions || 0);
  const agIhEl = document.getElementById('agentAtInHours');
  if(agIhEl){ agIhEl.textContent = inHours ? 'YES' : 'NO'; agIhEl.style.color = inHours ? 'var(--grn)' : 'var(--red)'; }

  // ── Decisions sub-tab stats ────────────────────────────────────
  _setText('agDecEntered', ds.trades_entered || 0);
  _setText('agDecExited', ds.trades_exited || 0);
  _setText('agDecSkipped', ds.signals_skipped || 0);
  _setText('agDecErrors', ds.errors || 0);
  _setText('agDecMinTier', d.min_tier || cfg.min_tier || 'HIGH');

  // ── Performance — AI Weight Learner ───────────────────────────
  try {
    const wl = d.weight_learner || {};
    const td = d.training_data || {};
    _setText('agAtWeightVer', wl.version || 'v5.0');
    _setText('agAtLearnRate', wl.learning_rate || 0.03);
    _setText('agAtTradeCount', wl.trade_count || 0);
    _setText('agAtSamples', td.total_samples || 0);
    const changes = wl.weight_changes || {};
    const wcEl = document.getElementById('agAtWeightChanges');
    if(wcEl){
      const entries = Object.entries(changes)
        .filter(([,v]) => Math.abs(v) > 0.001)
        .sort((a,b) => Math.abs(b[1]) - Math.abs(a[1]))
        .slice(0, 6);
      wcEl.innerHTML = entries.length === 0
        ? '<span style="color:var(--mut)">Weights at baseline</span>'
        : entries.map(([k,v]) => {
            const c = v > 0 ? 'var(--grn)' : 'var(--red)';
            return `<div style="display:flex;justify-content:space-between;padding:1px 0"><span>${k.replace(/_/g,' ')}</span><span style="color:${c}">${v > 0 ? '+' : ''}${v.toFixed(3)}</span></div>`;
          }).join('');
    }
  } catch(e){ console.warn('[Agent] Weight render error:', e); }
}

// Legacy alias — decisions are now rendered from pollAutoTradeStatus() response
async function pollAutoTradeDecisions(){ await pollAutoTradeStatus(); }

function _renderAgentDecisions(decisions){
  const mount = document.getElementById('agDecTableMount');
  if(!mount) return;
  const _actionColors = {TRADE_ENTERED:'var(--positive)',TRADE_EXITED:T.warning,SKIPPED:'var(--text-muted)',REJECTED:'var(--negative)',ERROR:'var(--negative)',STARTED:T.info,STOPPED:T.mut};
  if(!window._agDecTable){
    window._agDecTable = new DataTable({
      container: mount,
      compact: true,
      sortable: true,
      resizable: true,
      stickyHeader: true,
      emptyMessage: 'Waiting for auto-trader... Loading...',
      columns: [
        { key:'_ts', label:'Time', width:70, render:(v)=>`<span style="color:var(--text-muted)">${v}</span>` },
        { key:'action', label:'Action', width:100, render:(v)=>`<span style="color:${_actionColors[v]||'var(--text-muted)'};font-weight:var(--font-bold)">${esc(v)}</span>` },
        { key:'reason', label:'Reason', width:180 },
        { key:'signal_tier', label:'Tier', width:75, render:(v)=>v?UI.badge(v,v.toLowerCase()):'--' },
        { key:'_conf', label:'Confidence', width:75, align:'right' },
        { key:'signal_direction', label:'Direction', width:70, render:(v)=>esc(v||'--') },
      ],
    });
  }
  const rows = [...decisions].reverse().slice(0,50).map(dec => ({
    ...dec,
    _ts: dec.timestamp ? new Date(dec.timestamp).toLocaleTimeString('en-US',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '--',
    _conf: dec.signal_confidence != null ? (dec.signal_confidence*100).toFixed(1)+'%' : '--',
  }));
  window._agDecTable.setData(rows);
}

function _setText(id, val){ const el=document.getElementById(id); if(el) el.textContent=val; }

function startAutoTradePoll(){
  if(_autoTradePollTimer) return;
  pollAutoTradeStatus();  // Single call fetches status + decisions together
  _autoTradePollTimer = setInterval(()=>{
    pollAutoTradeStatus();
  }, 10000); // Every 10s
}
startAutoTradePoll();

// ══════════════════════════════════════════════════════════════════════════
// AI AGENT TAB
// ══════════════════════════════════════════════════════════════════════════
let _activeAgentTab = 'positions';
let _agentPollTimer = null;

// ── Sub-tab switching ──────────────────────────────────────────
function switchAgentTab(tab){
  _activeAgentTab = tab;
  document.querySelectorAll('.agent-tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.agtab === tab);
  });
  document.querySelectorAll('.agent-sub-panel').forEach(p => p.classList.remove('active'));
  const map = {positions:'agSubPositions', decisions:'agSubDecisions', signals:'agSubSignals', history:'agSubHistory', perf:'agSubPerf'};
  document.getElementById(map[tab])?.classList.add('active');
  // Load data for the newly-visible sub-tab
  if(tab === 'positions'){ refreshPositionsTab(); pollBeatSpy(); }
  else if(tab === 'decisions') pollAutoTradeDecisions();
  else if(tab === 'signals') loadAgentSignals();
  else if(tab === 'history') loadAgentHistory();
  else if(tab === 'perf') loadAgentPerf();
}

// ── AT toggle (agent tab) ──────────────────────────────────────
async function agentToggleAT(enable){
  try{
    const url = enable ? '/api/pm/enable' : '/api/pm/disable';
    const resp = await fetch(url, {method:'POST'});
    if(resp.ok){
      UI.toast('Auto-trader ' + (enable ? 'started' : 'stopped'), enable ? 'success' : 'info');
      pollAutoTradeStatus();
    } else {
      UI.toast('Auto-trader ' + (enable ? 'start' : 'stop') + ' failed (' + resp.status + ')', 'error');
    }
  } catch(e){
    UI.toast('Auto-trader request failed', 'error');
    console.error('[Agent] Toggle AT error:', e);
  }
}

// ── 5-Agent status cards ───────────────────────────────────────
async function pollAgentStatus(){
  try{
    const resp = await fetch('/api/agents/status');
    if(!resp.ok) return;
    const d = await resp.json();
    _renderAgentCards(d);
  } catch(e){ console.debug('[Agent] Status poll failed:', e); }
}

function _renderAgentCards(d){
  const container = document.getElementById('agentCards');
  if(!container) return;
  // API returns agents as a dict {name: {active, direction, confidence, reasoning, stale}}
  // Also supports legacy array format
  const agentData = d.agents || {};
  const entries = Array.isArray(agentData)
    ? agentData.map(a => [a.name||a.agent_id||'Agent', a])
    : Object.entries(agentData);
  if(!entries.length){
    container.innerHTML = '<div style="color:var(--mut);font-size:9px">No agents running</div>';
    return;
  }
  const sysStatus = d.system || 'running';
  // System indicator
  const dirColors = {bullish:'var(--grn)', bearish:'var(--red)', neutral:'var(--mut)'};
  container.innerHTML = entries.map(([name, ag]) => {
    const active = ag.active !== false;
    const stale = ag.stale === true;
    const dotColor = stale ? T.warning : active ? 'var(--grn)' : T.mut;
    const dir = ag.direction || 'neutral';
    const dirColor = dirColors[dir] || 'var(--mut)';
    const conf = ag.confidence != null ? (ag.confidence * 100).toFixed(0) + '%' : '--';
    const reason = (ag.reasoning || '--').slice(0, 40);
    return `<div style="flex:1;min-width:140px;max-width:200px;background:rgba(255,255,255,0.03);border:1px solid var(--brd);border-radius:6px;padding:8px">
      <div style="display:flex;align-items:center;gap:5px;margin-bottom:5px">
        <span style="width:6px;height:6px;border-radius:50%;background:${dotColor};flex-shrink:0;display:inline-block"></span>
        <span style="font-size:9px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:.3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(name)}</span>
      </div>
      <div style="font-size:8px;color:var(--mut)">Direction: <span style="color:${dirColor};font-weight:600;text-transform:uppercase">${dir}</span></div>
      <div style="font-size:8px;color:var(--mut)">Confidence: <span style="color:#fff">${conf}</span></div>
      <div style="font-size:8px;color:var(--dim);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${esc(ag.reasoning||'')}">${esc(reason)}</div>
    </div>`;
  }).join('') + `<div style="display:flex;align-items:center;gap:5px;min-width:80px">
    <span style="font-size:8px;color:var(--mut)">System:</span>
    <span style="font-size:8px;color:${sysStatus==='running'?'var(--grn)':'var(--red)'};font-weight:600;text-transform:uppercase">${sysStatus}</span>
    <span style="font-size:8px;color:var(--mut)">${d.open_signals||0} open / ${d.closed_signals||0} closed</span>
  </div>`;
}

// ── Positions (now served by refreshPositionsTab in agSubPositions) ──

async function agentExitPos(tradeId){
  if(!tradeId) return;
  try{
    const resp = await fetch('/api/pm/exit', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({trade_id:tradeId})});
    if(!resp.ok){ UI.toast('Exit failed (' + resp.status + ')', 'error'); return; }
    UI.toast('Position exit requested', 'info');
    setTimeout(refreshPositionsTab, 800);
  } catch(e){
    UI.toast('Exit request failed', 'error');
    console.error('[Agent] Exit pos error:', e);
  }
}

async function agentCloseAll(){
  if(!confirm('Close all open positions?')) return;
  try{
    const resp = await fetch('/api/pm/close-all', {method:'POST'});
    if(!resp.ok){ UI.toast('Close all failed (' + resp.status + ')', 'error'); return; }
    UI.toast('Close all requested', 'info');
    setTimeout(refreshPositionsTab, 800);
  } catch(e){
    UI.toast('Close all failed', 'error');
    console.error('[Agent] Close all error:', e);
  }
}

// ── Signals ───────────────────────────────────────────────────
async function loadAgentSignals(){
  try{
    const resp = await fetch('/api/signals/history?limit=40');
    if(!resp.ok) return;
    const data = await resp.json();
    const sigs = Array.isArray(data) ? data : (data.signals || []);
    const mount = document.getElementById('agSigTableMount');
    if(!mount) return;
    if(!window._agSigTable){
      window._agSigTable = new DataTable({
        container: mount,
        compact: true,
        sortable: true,
        resizable: true,
        stickyHeader: true,
        emptyMessage: 'No signals yet',
        columns: [
          { key:'_time', label:'Time', width:70 },
          { key:'_id', label:'ID', width:50, render:(v)=>`<span style="color:var(--text-muted)">${v}</span>` },
          { key:'_dirLabel', label:'Direction', width:75, render:(_,r)=>UI.badge(r._dirLabel, r._dirVariant) },
          { key:'tier', label:'Tier', width:75, render:(v)=>v?UI.badge(v,v.toLowerCase()):'--' },
          { key:'_conf', label:'Confidence', width:75, align:'right', render:(v)=>`<b>${v}</b>` },
          { key:'strike', label:'Strike', width:60, align:'right', render:(v)=>v?'$'+v.toFixed(0):'--' },
          { key:'entry_price', label:'Entry', width:60, align:'right', format:'currency' },
          { key:'target_price', label:'Target', width:60, align:'right', format:'currency' },
          { key:'stop_price', label:'Stop', width:60, align:'right', format:'currency' },
          { key:'max_contracts', label:'Qty', width:40, align:'right', render:(v)=>v||'--' },
          { key:'_src', label:'Source', width:65, render:(v)=>`<span style="color:var(--text-muted)">${esc(v)}</span>` },
          { key:'_factorCount', label:'Factors', width:50, align:'right' },
          { key:'_topFactors', label:'Top Factors', width:130, render:(v,r)=>`<span style="color:var(--text-muted)" title="${esc(r._allFactors)}">${esc(v||'--')}</span>` },
        ],
      });
    }
    const rows = [...sigs].reverse().map(s => {
      const dir = s.signal || 'NO_TRADE';
      const isCall = dir.includes('CALL');
      const isPut = dir.includes('PUT');
      const factors = s.top_factors || s.confluence_factors || [];
      const factorNames = factors.length ? (typeof factors[0]==='object' ? factors.map(f=>f.name||f.factor||'?') : factors) : [];
      return { ...s,
        _time: s.timestamp ? new Date(s.timestamp).toLocaleTimeString('en-US',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '--',
        _id: (s.id||'').slice(0,6),
        _dirLabel: dir === 'NO_TRADE' ? 'NO TRADE' : dir.replace('BUY_',''),
        _dirVariant: isCall ? 'green' : isPut ? 'red' : 'neutral',
        _conf: ((s.confidence||s.final_confidence||0)*100).toFixed(1)+'%',
        _src: s.source || s.data_source || '--',
        _factorCount: s.confluence_count || factorNames.length,
        _topFactors: factorNames.slice(0,4).join(', '),
        _allFactors: factorNames.join(', '),
      };
    });
    window._agSigTable.setData(rows);
  } catch(e){ console.debug('[Agent] Signals load failed:', e); }
}

// ── History ───────────────────────────────────────────────────
async function loadAgentHistory(){
  try{
    const resp = await fetch('/api/signals/trades?limit=100');
    if(!resp.ok) return;
    const data = await resp.json();
    const trades = Array.isArray(data) ? data : (data.trades || []);
    const mount = document.getElementById('agHistTableMount');
    if(!mount) return;
    if(!window._agHistTable){
      const _gradeV = {A:'green',B:'blue',C:'yellow',D:'yellow',F:'red'};
      window._agHistTable = new DataTable({
        container: mount,
        compact: true,
        sortable: true,
        resizable: true,
        stickyHeader: true,
        emptyMessage: 'No closed trades',
        columns: [
          { key:'_exitDate', label:'Exit', width:100 },
          { key:'_id', label:'ID', width:50, render:(v)=>`<span style="color:var(--text-muted)">${v}</span>` },
          { key:'_type', label:'Type', width:55, render:(_,r)=>UI.badge(r._typeLabel, r._typeVariant) },
          { key:'strike', label:'Strike', width:60, align:'right', render:(v)=>'$'+(v||0).toFixed(0) },
          { key:'tier', label:'Tier', width:75, render:(v)=>v?UI.badge(v,v.toLowerCase()):'--' },
          { key:'entry_price', label:'Entry $', width:65, align:'right', format:'currency' },
          { key:'exit_price', label:'Exit $', width:65, align:'right', format:'currency' },
          { key:'pnl', label:'P&L', width:75, align:'right', sortable:true,
            render:(v)=>{ const c=v>=0?'var(--positive)':'var(--negative)'; return `<span style="color:${c};font-weight:var(--font-bold)">${v>=0?'+':''}$${(v||0).toFixed(2)}</span>`; } },
          { key:'_pnlPct', label:'P&L%', width:60, align:'right',
            render:(v)=>{ const c=v>=0?'var(--positive)':'var(--negative)'; return `<span style="color:${c}">${v>=0?'+':''}${v.toFixed(1)}%</span>`; } },
          { key:'_holdMin', label:'Hold', width:50, align:'right', render:(v)=>`${v}m` },
          { key:'exit_reason', label:'Reason', width:80, render:(v)=>esc(v||'--') },
          { key:'grade', label:'Grade', width:50, render:(v)=>v?UI.badge(v,_gradeV[v]||'neutral'):'--' },
          { key:'mode', label:'Mode', width:45, render:(v)=>`<span style="color:var(--text-muted)">${esc(v||'sim')}</span>` },
        ],
      });
    }
    const rows = trades.map(t => {
      const isCall = (t.option_type||'').toLowerCase().includes('call');
      let holdMin = '--';
      if(t.entry_time && t.exit_time){
        holdMin = ((new Date(t.exit_time) - new Date(t.entry_time)) / 60000).toFixed(0);
      }
      return { ...t,
        _exitDate: t.exit_time ? new Date(t.exit_time).toLocaleString('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}) : '--',
        _id: (t.id||'').slice(0,6),
        _type: t.option_type,
        _typeLabel: (t.option_type||'').toUpperCase(),
        _typeVariant: isCall ? 'green' : 'red',
        _pnlPct: (t.pnl_pct||0)*100,
        _holdMin: holdMin,
      };
    });
    window._agHistTable.setData(rows);
  } catch(e){ console.debug('[Agent] History load failed:', e); }
}

// ── Performance ───────────────────────────────────────────────
async function loadAgentPerf(){
  try{
    const resp = await fetch('/api/signals/scorecard?period=all');
    if(!resp.ok) return;
    const data = await resp.json();
    const s = data.scorecard || data || {};
    const pf = v => v >= 0 ? '+$' + v.toFixed(2) : '-$' + Math.abs(v).toFixed(2);
    _setText('agPvTotal', s.trades || 0);
    const wrEl = document.getElementById('agPvWr');
    if(wrEl){ wrEl.textContent = (s.win_rate||0).toFixed(1) + '%'; wrEl.style.color = (s.win_rate||0) >= 55 ? 'var(--grn)' : 'var(--red)'; }
    const netEl = document.getElementById('agPvNet');
    if(netEl){ const v = s.net_pnl||0; netEl.textContent = pf(v); netEl.style.color = v >= 0 ? 'var(--grn)' : 'var(--red)'; }
    _setText('agPvPf', (s.profit_factor||0).toFixed(2));
    const awEl = document.getElementById('agPvAw');
    if(awEl){ awEl.textContent = pf(s.avg_win||0); awEl.style.color = 'var(--grn)'; }
    const alEl = document.getElementById('agPvAl');
    if(alEl){ alEl.textContent = pf(s.avg_loss||0); alEl.style.color = 'var(--red)'; }
    _setText('agPvEx', pf(s.expectancy||0));
    const ddEl = document.getElementById('agPvDd');
    if(ddEl){ ddEl.textContent = pf(s.max_drawdown||0); ddEl.style.color = 'var(--red)'; }
    _setText('agPvSh', (s.sharpe||0).toFixed(2));
    _setText('agPvHold', (s.avg_hold_minutes||0).toFixed(0) + 'm');
    _setText('agPvWl', (s.wins||0) + ' / ' + (s.losses||0));

    // Render equity curve (same data source as Positions tab)
    try{
      const tradesResp = await fetch('/api/signals/trades?limit=500');
      if(tradesResp.ok){
        const tradesData = await tradesResp.json();
        const closed = (tradesData.trades || []).filter(t => t.exit_time);
        renderEquityChart(_buildEquityCurve(closed));
      }
    } catch(e2){ console.debug('[Agent] Equity curve load failed:', e2); }
  } catch(e){ console.debug('[Agent] Perf load failed:', e); }
}

// ── LLM Validator verdicts feed ───────────────────────────────
async function loadLlmVerdicts(){
  try{
    const resp = await fetch('/api/pm/llm/verdicts?limit=20');
    if(!resp.ok) return;
    const d = await resp.json();

    // Show setup warning if no API key (uses u-hidden class, not inline style)
    const warn = document.getElementById('llmSetupWarn');
    if(warn){ d.has_api_key ? warn.classList.add('u-hidden') : warn.classList.remove('u-hidden'); }

    // Stats summary
    const st = d.stats || {};
    const total = st.total_validated || 0;
    const statsEl = document.getElementById('llmStatsSummary');
    if(statsEl && total > 0){
      const ar = ((st.approve_rate||0)*100).toFixed(0);
      const rr = ((st.reject_rate||0)*100).toFixed(0);
      const lat = st.avg_latency_ms || 0;
      statsEl.textContent = `${total} validated · ${ar}% approve · ${rr}% reject · avg ${lat}ms`;
    } else if(statsEl){
      statsEl.textContent = d.has_api_key ? 'No signals validated yet' : 'API key required';
    }

    // Verdicts list
    const feed = document.getElementById('llmVerdictsFeed');
    const empty = document.getElementById('llmVerdictsEmpty');
    if(!feed) return;
    const verdicts = d.verdicts || [];
    if(!verdicts.length){
      if(empty) empty.style.display = 'block';
      return;
    }
    if(empty) empty.style.display = 'none';
    const verdictColors = {APPROVE:'var(--grn)', CAUTION:T.warning, REJECT:'var(--red)', PENDING:'var(--mut)'};
    const verdictIcons = {APPROVE:'✓', CAUTION:'⚠', REJECT:'✗', PENDING:'…'};
    feed.innerHTML = verdicts.map(v => {
      const vc = verdictColors[v.verdict] || 'var(--mut)';
      const vi = verdictIcons[v.verdict] || '?';
      const ts = v.timestamp ? new Date(v.timestamp).toLocaleTimeString('en-US',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '--';
      const conf = v.verdict_confidence != null ? (v.verdict_confidence*100).toFixed(0)+'%' : '';
      const latency = v.latency_ms ? `${v.latency_ms}ms` : '';
      const wouldBlock = v.would_block ? ' · <span style="color:var(--red);font-size:8px">would block</span>' : '';
      const errMsg = v.error ? `<div style="color:var(--red);font-size:8px;margin-top:2px">Error: ${esc(v.error)}</div>` : '';
      const keyFactors = (v.key_factors||[]).slice(0,3).join(', ');
      return `<div style="padding:5px 4px;border-bottom:1px solid rgba(255,255,255,0.04);display:flex;gap:6px;align-items:flex-start">
        <span style="color:${vc};font-size:11px;font-weight:700;flex-shrink:0;margin-top:1px">${vi}</span>
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
            <span style="color:${vc};font-weight:700;font-size:9px">${v.verdict}</span>
            ${conf ? `<span style="color:var(--mut)">${conf}</span>` : ''}
            <span class="ui-badge ${(v.signal_direction||'').includes('CALL')?'green':(v.signal_direction||'').includes('PUT')?'red':'neutral'}" style="font-size:7px">${v.signal_direction||'--'}</span>
            <span class="ui-badge ${(v.signal_tier||'').toLowerCase()}" style="font-size:7px">${v.signal_tier||'--'}</span>
            <span style="color:var(--dim);font-size:8px;margin-left:auto">${ts}${latency?' · '+latency:''}</span>
            ${wouldBlock}
          </div>
          ${v.reasoning ? `<div style="color:var(--dim);margin-top:2px;font-size:8px;line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(v.reasoning)}">${esc(v.reasoning)}</div>` : ''}
          ${keyFactors ? `<div style="color:var(--mut);font-size:8px;margin-top:1px">${esc(keyFactors)}</div>` : ''}
          ${errMsg}
        </div>
      </div>`;
    }).join('');
  } catch(e){ console.debug('[Agent] LLM verdicts load failed:', e); }
}

// ── Agent tab entry point (called when navTo('agent')) ─────────
let _agentTabStarted = false;
function startAgentTab(){
  if(_agentTabStarted) return;
  _agentTabStarted = true;
  // Initial loads
  pollAgentStatus();
  refreshPositionsTab(); pollBeatSpy();
  loadLlmVerdicts();
  // Recurring polls every 15s when agent tab is open
  _agentPollTimer = setInterval(() => {
    if(S.activeTab !== 'agent') return;
    pollAgentStatus();
    loadLlmVerdicts();
    if(_activeAgentTab === 'positions'){ refreshPositionsTab(); pollBeatSpy(); }
    else if(_activeAgentTab === 'signals') loadAgentSignals();
    else if(_activeAgentTab === 'history') loadAgentHistory();
    else if(_activeAgentTab === 'perf') loadAgentPerf();
  }, 15000);
}

// ══════════════════════════════════════════════════════════════════════════
// PIPELINE DIAGNOSTICS
// ══════════════════════════════════════════════════════════════════════════
let _lastPipelineStatus = '';

async function pollPipelineDiag(){
  try{
    const resp = await fetch('/api/signals/diagnostics');
    if(!resp.ok) return;
    const d = await resp.json();
    const dot = document.getElementById('dotPipeline');
    const lbl = document.getElementById('lblPipeline');
    if(!dot||!lbl) return;

    const status = d.pipeline_status || 'UNKNOWN';
    _lastPipelineStatus = status;

    if(status === 'FLOWING'){
      dot.className = 'dot on';
      lbl.textContent = 'Pipeline OK';
      lbl.style.color = 'var(--grn)';
    } else if(status.startsWith('BLOCKED')){
      dot.className = 'dot off';
      // Show short version in header
      const shortStatus = status.replace('BLOCKED — ', '').replace('BLOCKED at ', '');
      lbl.textContent = 'BLOCKED: ' + shortStatus.substring(0, 25);
      lbl.style.color = 'var(--negative-bright)';
    } else if(status.startsWith('READY')){
      dot.className = 'dot dim';
      lbl.textContent = 'Pipeline Ready';
      lbl.style.color = 'var(--ylw)';
    } else {
      dot.className = 'dot dim';
      lbl.textContent = 'Pipeline: ' + status.substring(0, 20);
      lbl.style.color = 'var(--mut)';
    }

    // Store for detail popup
    window._pipelineDiag = d;
  }catch(e){
    console.debug('Pipeline diag poll error:', e);
  }
}

function showPipelineDiag(){
  const d = window._pipelineDiag;
  if(!d){ alert('No diagnostics available yet'); return; }

  const da = d.data_availability || {};
  const eng = d.engine_diagnostics || {};
  const gate = eng.last_gate_result || {};

  let msg = `=== Signal Pipeline Diagnostics ===\n\n`;
  msg += `Status: ${d.pipeline_status}\n`;
  msg += `Signals generated: ${d.signal_count}\n`;
  msg += `Last signal: ${d.last_signal_action || 'none'} at ${d.last_signal_time || 'never'}\n\n`;

  msg += `--- Data Availability ---\n`;
  if(da.trades) msg += `Trades: ${da.trades.status} (${da.trades.available} available)\n`;
  if(da.quote) msg += `Quote: ${da.quote.status} (price=$${da.quote.price || 0})\n`;
  if(da.chain) msg += `Chain: ${da.chain.status} (${da.chain.calls}C/${da.chain.puts}P)\n`;
  msg += `\n`;

  msg += `--- Engine State ---\n`;
  msg += `Chain cached: ${eng.chain_cached} (${eng.chain_cache_calls}C/${eng.chain_cache_puts}P)\n`;
  msg += `Bars 1m: ${eng.bars_1m_cached}, Daily: ${eng.bars_daily_cached}\n`;
  msg += `Regime: ${eng.regime}, Sweeps: ${eng.sweeps}, VPIN: ${eng.vpin}\n`;
  msg += `\n`;

  if(gate.blocked_at){
    msg += `--- Last Block ---\n`;
    msg += `Gate: ${gate.blocked_at}\n`;
    msg += `Reason: ${gate.reason}\n`;
    if(gate.confidence) msg += `Confidence: ${(gate.confidence * 100).toFixed(1)}%\n`;
    if(gate.chain_calls != null) msg += `Chain at block: ${gate.chain_calls}C/${gate.chain_puts}P\n`;
  }

  if(da.connections){
    msg += `\n--- Connections ---\n`;
    const c = da.connections;
    if(c.theta) msg += `ThetaData: ${c.theta.reachable ? 'OK' : 'DOWN'}\n`;
    if(c.alpaca) msg += `Alpaca: ${c.alpaca.reachable ? 'OK' : 'DOWN'}\n`;
    if(c.engine) msg += `Rust Engine: ${c.engine.reachable ? 'OK' : 'DOWN'}\n`;
  }

  alert(msg);
}

// Poll pipeline diagnostics every 30s
setInterval(pollPipelineDiag, 30000);
pollPipelineDiag(); // Initial poll

