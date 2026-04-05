
// ══════════════════════════════════════════════════════════════════════════
// TRADE MODE — scalp/standard/swing toggle
// ══════════════════════════════════════════════════════════════════════════

const _modeDescs = {scalp:'Quick scalp 10m', standard:'Balanced 25m', swing:'Longer hold 45m'};
const _modeColors = {scalp:'var(--grn)', standard:'var(--acc)', swing:'var(--ylw)'};

async function setTradeMode(mode){
  try {
    const resp = await fetch(`/api/signals/trade-mode?mode=${mode}`, {method:'POST'});
    if(resp.ok){
      const d = await resp.json();
      _renderTradeMode(d.mode || mode);
    } else {
      UI.toast(`Trade mode change failed (${resp.status})`, 'error');
    }
  } catch(e){ UI.toast('Trade mode error — server unreachable', 'error'); console.warn('[TradeMode]', e); }
}

function _renderTradeMode(mode){
  ['scalp','standard','swing'].forEach(m => {
    const btn = document.getElementById('mode' + m.charAt(0).toUpperCase() + m.slice(1));
    if(btn){
      const isActive = m === mode;
      btn.style.background = isActive ? (_modeColors[m] === 'var(--grn)' ? 'rgba(38,166,154,0.15)' : _modeColors[m] === 'var(--acc)' ? 'rgba(85,136,238,0.15)' : 'rgba(255,179,0,0.15)') : 'none';
      btn.style.color = isActive ? _modeColors[m] : 'var(--dim)';
      btn.style.borderColor = isActive ? _modeColors[m] : 'var(--brd)';
    }
  });
  const desc = document.getElementById('modeDesc');
  if(desc) desc.textContent = _modeDescs[mode] || mode;
}

async function initTradeMode(){
  try {
    const resp = await fetch('/api/signals/trade-mode');
    if(resp.ok){
      const d = await resp.json();
      _renderTradeMode(d.mode || 'scalp');
    }
  } catch(e){ console.debug('[TradeMode] Init failed:', e); }
}
initTradeMode();

// Start both polling loops on script load
startAISignalPolling();
startPhantomPLPolling();
startMetricPolling();
startStatsBannerPoll();
startAutoPosPoll();
startEquityCurvePoll();

// Start trade journal polling (every 20s)
_journalPollTimer = setInterval(pollTradeJournal, 20000);
setTimeout(pollTradeJournal, 6000);

// Set journal date label
(function(){ const el = document.getElementById('journalDate'); if(el) el.textContent = new Date().toLocaleDateString('en-US', {month:'short', day:'numeric', year:'numeric'}); })();

// ══════════════════════════════════════════════════════════════════════════
// BEAT SPY SCORECARD
// ══════════════════════════════════════════════════════════════════════════

async function pollBeatSpy(){
  // Only poll when positions tab is active
  if(!(S.activeTab === 'agent' && _activeAgentTab === 'positions')) return;
  try {
    const resp = await fetch('/api/signals/beat-spy');
    if(!resp.ok) return;
    const d = await resp.json();
    if(d.error) return;
    _renderBeatSpy(d);
  } catch(e){ /* silent */ }
}

function _renderBeatSpy(d){
  // Your P&L
  const yourPL = document.getElementById('spyYourPL');
  if(yourPL){
    const pnl = d.your_pnl || 0;
    yourPL.textContent = (pnl >= 0 ? '+$' : '-$') + Math.abs(pnl).toFixed(2);
    yourPL.style.color = pnl >= 0 ? 'var(--grn)' : 'var(--red)';
  }
  const yourPct = document.getElementById('spyYourPct');
  if(yourPct) yourPct.textContent = (d.your_pct >= 0 ? '+' : '') + d.your_pct.toFixed(2) + '%';

  // SPY change
  const spyChange = document.getElementById('spySpyChange');
  if(spyChange){
    const pct = d.spy_pct || 0;
    spyChange.textContent = (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
    spyChange.style.color = pct >= 0 ? 'var(--grn)' : 'var(--red)';
  }
  const spyPct = document.getElementById('spySpyPct');
  if(spyPct && d.spy_current) spyPct.textContent = '$' + d.spy_current.toFixed(2);

  // Spread
  const spread = document.getElementById('spySpread');
  if(spread){
    const s = d.spread || 0;
    spread.textContent = (s >= 0 ? '+' : '') + s.toFixed(2) + '%';
    spread.style.color = s >= 0 ? 'var(--grn)' : 'var(--red)';
  }

  // Badge
  const badge = document.getElementById('spyBeatBadge');
  if(badge && d.trade_count > 0){
    badge.style.display = 'inline';
    if(d.beat_spy){
      badge.textContent = 'BEATING SPY';
      badge.style.background = 'var(--positive-subtle)';
      badge.style.color = T.positive;
    } else {
      badge.textContent = 'BEHIND SPY';
      badge.style.background = 'var(--negative-subtle)';
      badge.style.color = T.negative;
    }
  } else if(badge){
    badge.style.display = 'none';
  }

  // Streak
  const streakEl = document.getElementById('spyStreak');
  if(streakEl) streakEl.textContent = d.streak > 0 ? d.streak + ' days' : '--';

  // Win rate
  const wrEl = document.getElementById('spyWinRate');
  if(wrEl){
    const wr = d.win_rate || 0;
    wrEl.textContent = d.trade_count > 0 ? wr.toFixed(0) + '%' : '--';
    wrEl.style.color = wr >= 60 ? 'var(--grn)' : wr >= 40 ? 'var(--ylw)' : d.trade_count > 0 ? 'var(--red)' : '#fff';
  }

  // Grade pills
  const gradesEl = document.getElementById('spyGrades');
  if(gradesEl){
    const gl = d.grade_list || [];
    if(gl.length > 0){
      const colorMap = {A:T.positive,B:'#8bc34a',C:T.warning,D:T.negative,F:'#b71c1c','?':T.mut};
      gradesEl.innerHTML = gl.map(g => {
        const c = colorMap[g] || '#666';
        return `<span style="display:inline-block;padding:1px 6px;border-radius:3px;font-size:9px;font-weight:600;background:${c}22;color:${c}">${g}</span>`;
      }).join('');
    } else {
      gradesEl.innerHTML = '<span style="font-size:9px;color:var(--mut)">No trades today</span>';
    }
  }
}

// ══════════════════════════════════════════════════════════════════════════
// VOLATILITY WINDOW ADVISOR
// ══════════════════════════════════════════════════════════════════════════

const _riskColors = { green:T.positive, yellow:T.warning, red:T.negative, gray:T.mut };
const _strikeLabels = { OTM:'OTM Preferred', ATM_ONLY:'ATM Only', NONE:'No Entries' };
let _advPollTimer = null;

async function pollAdvisor(){
  try {
    const resp = await fetch('/api/signals/volatility-advisor');
    if(!resp.ok) return;
    const data = await resp.json();
    if(data.error) return;
    _renderAdvisor(data);
  } catch(e){ /* silent */ }
}

function _renderAdvisor(d){
  const pw = d.window || d.prism_window || {};
  const rt = d.risk_tier || {};
  const sess = d.session || {};
  const regime = d.regime || {};
  const events = d.events || {};
  const frag = d.fragility || {};
  const strikes = d.suggested_strikes || {};

  // Window header
  const dot = document.getElementById('advRiskDot');
  if(dot) dot.style.background = _riskColors[rt.color] || '#666';

  const lbl = document.getElementById('advWindowLabel');
  if(lbl) lbl.textContent = pw.label || 'Unknown';

  const timeRem = document.getElementById('advTimeRemaining');
  if(timeRem){
    const m = pw.time_remaining_min;
    if(m != null && m > 0){
      const h = Math.floor(m / 60);
      const mm = m % 60;
      timeRem.textContent = h > 0 ? `${h}h ${mm}m left` : `${mm}m left`;
    } else {
      timeRem.textContent = pw.current_time_et || '--';
    }
  }

  const progBar = document.getElementById('advProgressBar');
  if(progBar) progBar.style.width = (pw.progress_pct || 0) + '%';

  // Strike type
  const strike = document.getElementById('advStrikeType');
  if(strike){
    const st = pw.strike_type || 'NONE';
    strike.textContent = _strikeLabels[st] || st;
    strike.style.color = st === 'OTM' ? T.positive : st === 'ATM_ONLY' ? T.warning : T.negative;
  }

  // Description
  const desc = document.getElementById('advDescription');
  if(desc) desc.textContent = pw.description || '';

  // Fragility
  const fragEl = document.getElementById('advFragility');
  if(fragEl && frag.score != null){
    const lvl = frag.level || 'normal';
    const clr = lvl === 'high' ? T.negative : lvl === 'elevated' ? T.warning : lvl === 'low' ? T.positive : 'var(--fg)';
    fragEl.innerHTML = `<span style="color:${clr};font-weight:600">${frag.score.toFixed(1)}/3</span> <span style="color:var(--mut);font-size:8px">(${lvl})</span>`;
  }

  // Suggested strikes
  const strikesEl = document.getElementById('advStrikes');
  if(strikesEl){
    const calls = strikes.calls || [];
    const puts = strikes.puts || [];
    if(calls.length > 0 || puts.length > 0){
      let html = '';
      if(calls.length > 0){
        const callStr = calls.map(c => {
          const price = c.mid > 0 ? ` $${c.mid.toFixed(2)}` : '';
          return `<span style="color:var(--grn)">${c.strike}c</span><span style="color:var(--mut);font-size:7px">${price}</span>`;
        }).join(', ');
        html += `<div style="font-size:9px;line-height:1.6">Calls: ${callStr}</div>`;
      }
      if(puts.length > 0){
        const putStr = puts.map(p => {
          const price = p.mid > 0 ? ` $${p.mid.toFixed(2)}` : '';
          return `<span style="color:var(--red)">${p.strike}p</span><span style="color:var(--mut);font-size:7px">${price}</span>`;
        }).join(', ');
        html += `<div style="font-size:9px;line-height:1.6">Puts: ${putStr}</div>`;
      }
      strikesEl.innerHTML = html;
    } else {
      strikesEl.innerHTML = '<span style="font-size:9px;color:var(--mut)">No entries this window</span>';
    }
  }

  // Risk tier
  const rl = document.getElementById('advRiskLabel');
  if(rl){ rl.textContent = rt.label || '--'; rl.style.color = _riskColors[rt.color] || '#fff'; }
  const rg = document.getElementById('advRiskGrade');
  if(rg) rg.textContent = rt.grade ? `Grade: ${rt.grade}` : '';
  const rb = document.getElementById('advRiskBehavior');
  if(rb) rb.textContent = rt.behavior || '--';

  // Checklist
  const cl = document.getElementById('advChecklist');
  if(cl && pw.checklist){
    cl.innerHTML = pw.checklist.map((item, i) => {
      const isWarning = item.startsWith('\u26a0');
      return `<div style="display:flex;align-items:flex-start;gap:5px;padding:3px 0;font-size:9px;line-height:1.4;color:${isWarning ? 'var(--negative)' : 'var(--fg)'}">
        <span style="color:${isWarning ? 'var(--negative)' : 'var(--mut)'};flex-shrink:0;font-size:8px;margin-top:1px">${isWarning ? '\u26a0' : '\u25cb'}</span>
        <span>${item.replace(/^\u26a0\s*/, '')}</span>
      </div>`;
    }).join('');
  }

  // Session context
  const _s = (id, val) => { const e = document.getElementById(id); if(e) e.textContent = val; };
  _s('advPhase', (sess.phase || '--').replace(/_/g, ' '));
  const q = sess.session_quality;
  const qEl = document.getElementById('advQuality');
  if(qEl){
    const pct = q != null ? Math.round(q * 100) + '%' : '--';
    qEl.textContent = pct;
    qEl.className = 'mv ' + (q >= 0.7 ? 'grn' : q >= 0.4 ? 'ylw' : 'red');
  }
  _s('advToClose', sess.minutes_to_close != null ? sess.minutes_to_close + ' min' : '--');
  _s('adv0dte', sess.is_0dte ? 'Yes' : 'No');

  const vrEl = document.getElementById('advVolRegime');
  if(vrEl){
    const vr = regime.vol_regime || events.mode || '--';
    vrEl.textContent = vr;
    vrEl.className = 'mv ' + (vr === 'compressed' ? 'grn' : vr === 'elevated' ? 'red' : 'ylw');
  }

  const emEl = document.getElementById('advEventMode');
  if(emEl){
    const em = events.mode || 'normal';
    emEl.textContent = em.replace(/_/g, ' ');
    if(events.next_event && events.next_event_minutes != null){
      emEl.textContent += ` (${events.next_event} in ${Math.round(events.next_event_minutes)}m)`;
    }
    emEl.className = 'mv ' + (em === 'normal' ? 'grn' : em === 'pre_event' ? 'red' : 'ylw');
  }

  // Fragility detail in session context
  const fdEl = document.getElementById('advFragDetail');
  if(fdEl && frag.score != null){
    const lvl = frag.level || 'normal';
    fdEl.textContent = `${frag.score.toFixed(1)} (IV:${frag.iv_component} GEX:${frag.gex_component} OI:${frag.oi_component})`;
    fdEl.className = 'mv ' + (lvl === 'high' ? 'red' : lvl === 'elevated' ? 'ylw' : 'grn');
  }
}

function startAdvisorPolling(){
  if(_advPollTimer) return;
  _advPollTimer = setInterval(pollAdvisor, 15000); // Every 15s
  setTimeout(pollAdvisor, 1500); // First poll after 1.5s
}
function stopAdvisorPolling(){
  if(_advPollTimer){ clearInterval(_advPollTimer); _advPollTimer = null; }
}
startAdvisorPolling();

