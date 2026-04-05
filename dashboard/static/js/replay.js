// ══════════════════════════════════════════════════════════════════════════
// SIGNAL REPLAY — replay historical signals against actual price action
// ══════════════════════════════════════════════════════════════════════════

let _replayInitialized = false;
let _replayData = null;

function initReplayTab(){
  if(!_replayInitialized){
    _replayInitialized = true;
    // Load available dates first, then auto-load most recent
    loadReplay();
  }
}

async function loadReplay(){
  const datePicker = document.getElementById('replayDatePicker');
  const dirFilter = document.getElementById('replayDirFilter');
  const tierFilter = document.getElementById('replayTierFilter');
  const timeline = document.getElementById('replayTimeline');

  const date = datePicker.value || '';
  const direction = dirFilter ? dirFilter.value : '';
  const tier = tierFilter ? tierFilter.value : '';

  timeline.innerHTML = UI.loading('Loading signals...');

  try {
    const params = new URLSearchParams();
    if(date) params.set('date', date);
    if(direction) params.set('direction', direction);
    if(tier) params.set('tier', tier);

    const resp = await fetch('/api/signals/replay?' + params.toString());
    if(!resp.ok) throw new Error('API error ' + resp.status);
    const data = await resp.json();

    if(data.error){
      timeline.innerHTML = UI.empty(data.error, 'error');
      return;
    }

    _replayData = data;

    // Populate date picker (only on first load or if dates changed)
    const dates = data.available_dates || [];
    if(dates.length > 0){
      const currentVal = datePicker.value;
      const opts = dates.map(d => `<option value="${esc(d)}"${d === data.date ? ' selected' : ''}>${esc(d)}</option>`);
      datePicker.innerHTML = opts.join('');
      if(!currentVal && data.date) datePicker.value = data.date;
    }

    // Update summary
    renderReplaySummary(data.summary);

    // Render timeline
    if(data.signals.length === 0){
      timeline.innerHTML = UI.empty('No signals found for this date and filters');
    } else {
      renderReplayTimeline(data.signals);
    }

  } catch(e){
    timeline.innerHTML = UI.empty('Failed to load replay: ' + e.message, 'error');
  }
}

function renderReplaySummary(s){
  if(!s) return;
  const el = id => document.getElementById(id);

  el('rsTotalSignals').textContent = s.total || 0;
  el('rsCorrect15').textContent = s.correct_15 || 0;
  el('rsCorrect30').textContent = s.correct_30 || 0;
  el('rsAccuracy30').textContent = (s.accuracy_30 || 0) + '%';
  el('rsAvgMove').textContent = (s.avg_move_30 || 0).toFixed(2) + '%';

  // Accuracy badge in header
  const badge = document.getElementById('replayAccuracyBadge');
  const acc = s.accuracy_30 || 0;
  badge.textContent = acc + '% accuracy (30m)';
  if(acc >= 60) {
    badge.style.background = 'rgba(38,166,154,0.15)';
    badge.style.color = 'var(--grn)';
  } else if(acc >= 45) {
    badge.style.background = 'rgba(255,179,0,0.15)';
    badge.style.color = 'var(--ylw)';
  } else {
    badge.style.background = 'rgba(239,83,80,0.15)';
    badge.style.color = 'var(--red)';
  }

  // Color accuracy card
  const accEl = el('rsAccuracy30');
  accEl.style.color = acc >= 60 ? 'var(--grn)' : acc >= 45 ? 'var(--ylw)' : 'var(--red)';
}

function renderReplayTimeline(signals){
  const timeline = document.getElementById('replayTimeline');
  if(!signals || signals.length === 0){
    timeline.innerHTML = UI.empty('No signals');
    return;
  }

  const cards = signals.map(sig => {
    // Time
    const ts = sig.timestamp || '';
    const timePart = ts.includes('T') ? ts.split('T')[1].substring(0, 8) : ts.substring(11, 19);

    // Direction
    const isCall = (sig.direction || '').includes('CALL');
    const dirLabel = isCall ? 'CALL' : 'PUT';
    const dirVariant = isCall ? 'green' : 'red';

    // Tier
    const tier = sig.tier || 'UNKNOWN';
    const tierVariants = { EXCEPTIONAL: 'accent', STRONG: 'green', VALID: 'blue', DEVELOPING: 'neutral' };
    const tierVariant = tierVariants[tier] || 'neutral';

    // SPY price
    const spyPrice = sig.spy_price || sig.spy_price_at_signal || 0;

    // Confidence
    const conf = (sig.confidence || 0).toFixed(0);

    // Outcomes
    const m15 = sig.move_pct_15min;
    const m30 = sig.move_pct_30min;
    const dc15 = sig.direction_correct_15;
    const dc30 = sig.direction_correct_30;

    const fmtMove = (m) => m != null ? (m >= 0 ? '+' : '') + m.toFixed(3) + '%' : '--';
    const moveColor = (m) => m != null ? (m >= 0 ? 'var(--grn)' : 'var(--red)') : 'var(--mut)';
    const arrow = (dc) => dc === 1 ? '<span style="color:var(--grn)">&#9650;</span>' : dc === 0 ? '<span style="color:var(--red)">&#9660;</span>' : '<span style="color:var(--mut)">&#8212;</span>';

    // Correct/Wrong badge
    let outcomeHtml = '';
    if(dc30 === 1) outcomeHtml = UI.badge('CORRECT', 'green');
    else if(dc30 === 0) outcomeHtml = UI.badge('WRONG', 'red');
    else outcomeHtml = UI.badge('PENDING', 'neutral');

    // Traded badge
    const tradedHtml = sig.was_traded ? UI.badge('TRADED', 'accent') : UI.badge('SKIPPED', 'neutral');

    // P&L if traded
    let pnlHtml = '';
    if(sig.was_traded && sig.trade_pnl != null){
      const pnl = sig.trade_pnl;
      const pnlColor = pnl >= 0 ? 'var(--grn)' : 'var(--red)';
      pnlHtml = `<span style="color:${pnlColor};font-weight:600;font-size:var(--font-sm)">P&L: ${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</span>`;
    }

    // Top factors
    const factors = sig.top_factors || [];
    const factorsHtml = factors.length > 0
      ? factors.map(f => `<span class="replay-factor-tag">${esc(f)}</span>`).join(' ')
      : '<span class="replay-factor-tag" style="color:var(--mut)">No factors</span>';

    return `
      <div class="replay-card">
        <!-- Time column -->
        <div class="replay-time">
          <div class="replay-time-ts">${esc(timePart)}</div>
          <div class="replay-time-spy">SPY ${spyPrice ? spyPrice.toFixed(2) : '--'}</div>
        </div>

        <!-- Direction + Tier -->
        <div class="replay-meta">
          <div>${UI.badge(dirLabel, dirVariant)} ${UI.badge(tier, tierVariant)}</div>
          <div class="replay-time-spy">Conf: ${conf}%</div>
        </div>

        <!-- 15m / 30m outcomes -->
        <div class="replay-outcomes">
          <div class="replay-outcomes-row">
            <div>
              <span style="color:var(--mut);font-size:var(--font-2xs)">15m:</span>
              ${arrow(dc15)} <span style="color:${moveColor(m15)};font-variant-numeric:tabular-nums">${fmtMove(m15)}</span>
            </div>
            <div>
              <span style="color:var(--mut);font-size:var(--font-2xs)">30m:</span>
              ${arrow(dc30)} <span style="color:${moveColor(m30)};font-variant-numeric:tabular-nums">${fmtMove(m30)}</span>
            </div>
          </div>
          <div style="margin-top:3px">${outcomeHtml} ${tradedHtml}</div>
        </div>

        <!-- Factors + P&L -->
        <div class="replay-factors">
          <div style="display:flex;gap:4px;flex-wrap:wrap">${factorsHtml}</div>
          ${pnlHtml ? `<div style="margin-top:4px">${pnlHtml}</div>` : ''}
        </div>
      </div>`;
  });

  timeline.innerHTML = cards.join('');
}
