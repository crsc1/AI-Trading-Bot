// ══════════════════════════════════════════════════════════════════════════
// PAPER TRADING SETTINGS PANEL
// ══════════════════════════════════════════════════════════════════════════

// ══════════════════════════════════════════════════════════════════════════
// SETTINGS MANAGER — Comprehensive settings using Modal + FormField components
// ══════════════════════════════════════════════════════════════════════════
const SettingsManager = (() => {
  let _modal = null;
  let _data  = {};   // Last fetched settings
  let _dirty = false;

  // ── Helpers ──────────────────────────────────────────────────────────
  function pct(v){ return ((v || 0) * 100).toFixed(1); }
  function fromPct(v){ return parseFloat(v) / 100; }

  function field(id, label, type, opts = {}) {
    const { help, suffix, min, max, step, value, options, checked } = opts;
    const cls = opts.horizontal ? ' ff--horizontal' : '';
    let html = `<div class="ff${cls}">`;
    html += `<label class="ff-label" for="s_${id}">${label}</label>`;

    if (type === 'select') {
      html += `<select class="ff-select" id="s_${id}">`;
      (options || []).forEach(o => {
        const sel = o.value === value ? ' selected' : '';
        html += `<option value="${o.value}"${sel}>${o.label}</option>`;
      });
      html += `</select>`;
    } else if (type === 'toggle') {
      html += `<label class="ff-toggle"><input type="checkbox" id="s_${id}"${checked ? ' checked' : ''}><span class="ff-toggle-slider"></span></label>`;
    } else if (type === 'number') {
      html += `<div class="ff-input-wrap">`;
      html += `<input class="ff-input" type="number" id="s_${id}" min="${min ?? ''}" max="${max ?? ''}" step="${step ?? 'any'}" value="${value ?? ''}">`;
      if (suffix) html += `<span class="ff-suffix">${suffix}</span>`;
      html += `</div>`;
    } else if (type === 'text') {
      html += `<input class="ff-input" type="text" id="s_${id}" value="${value ?? ''}" readonly>`;
    } else if (type === 'time') {
      html += `<input class="ff-input" type="time" id="s_${id}" value="${value ?? ''}" step="60">`;
    }

    if (help) html += `<div class="ff-help">${help}</div>`;
    html += `</div>`;
    return html;
  }

  function sectionTitle(text) {
    return `<div style="font-size:var(--font-xs);font-weight:var(--font-bold);color:var(--text-primary);margin:var(--space-md) 0 var(--space-sm);letter-spacing:0.3px;text-transform:uppercase">${text}</div>`;
  }

  function statusCard(label, value, color) {
    return `<div class="modal-status-card"><div class="modal-status-label">${label}</div><div class="modal-status-value" style="color:var(--${color || 'text-primary'})">${value}</div></div>`;
  }

  // ── Section Builders ────────────────────────────────────────────────
  function buildAccount(d) {
    const bal = d.account_balance || 5000;
    STARTING_BALANCE = bal;  // Sync global
    let h = `<div style="display:flex;gap:var(--space-sm);margin-bottom:var(--space-md)">`;
    h += statusCard('Account Balance', '$' + bal.toLocaleString('en-US', {minimumFractionDigits:2}), 'positive');
    h += statusCard('Mode', 'Paper Simulation', 'accent');
    h += `</div>`;

    h += sectionTitle('Risk Limits');
    const r = d.risk || {};
    h += field('maxDailyLoss', 'Max Daily Loss', 'number', { value: pct(r.max_daily_loss), suffix: '%', min:0.5, max:15, step:0.5, help: 'Circuit breaker — halts all trading when hit' });
    h += field('maxOpenPos', 'Max Open Positions', 'number', { value: r.max_open_positions || 3, min:1, max:10, step:1, help: 'Concurrent open positions allowed' });
    h += field('maxTradesDay', 'Max Trades / Day', 'number', { value: r.max_trades_per_day || 5, min:1, max:30, step:1 });
    h += field('riskPerTrade', 'Risk per Trade', 'number', { value: pct(r.max_risk_per_trade_pct), suffix: '%', min:0.5, max:10, step:0.5, help: 'Max % of account per single trade' });
    h += field('minSecBetween', 'Cooldown Between Trades', 'number', { value: r.min_seconds_between_trades || 30, suffix: 'sec', min:0, max:300, step:5 });

    h += sectionTitle('Signal Quality Gates');
    h += field('minTier', 'Min Tier', 'select', {
      value: d.min_tier || 'VALID',
      options: [
        { value:'DEVELOPING', label:'DEVELOPING' },
        { value:'VALID', label:'VALID' },
        { value:'HIGH', label:'HIGH' },
        { value:'TEXTBOOK', label:'TEXTBOOK' },
      ]
    });
    h += field('minConf', 'Min Confidence', 'number', { value: d.min_confidence || 0.45, min:0.1, max:0.99, step:0.05, help: 'Composite score threshold (0.0 – 1.0)' });
    h += field('dailyLossThrottle', 'Loss Throttle Level', 'number', { value: pct(r.daily_loss_throttle), suffix: '%', min:0.5, max:10, step:0.5, help: 'After this loss, only TEXTBOOK signals accepted' });

    return h;
  }

  function buildExitRules(d) {
    const ex = d.exit_rules || {};
    let h = sectionTitle('Profit & Loss Exits');
    h += field('stopLoss', 'Stop Loss', 'number', { value: pct(ex.stop_loss_pct), suffix: '%', min:5, max:100, step:5, help: 'Full exit when unrealized PnL drops below this' });
    h += field('profitTarget', 'Profit Target', 'number', { value: pct(ex.profit_target_pct), suffix: '%', min:10, max:500, step:10, help: 'Full exit when profit reaches this level' });
    h += field('trailingStop', 'Trailing Stop', 'number', { value: pct(ex.trailing_stop_pct), suffix: '%', min:3, max:50, step:1, help: 'Locks in gains — exits when price drops from peak' });
    h += field('trailingActivation', 'Trailing Activation', 'number', { value: pct(ex.trailing_stop_activation), suffix: '%', min:3, max:100, step:1, help: 'Trailing stop activates after this gain' });

    h += sectionTitle('Time Exits');
    h += field('maxHoldMin', 'Max Hold Time', 'number', { value: ex.max_hold_minutes || 60, suffix: 'min', min:5, max:300, step:5, help: 'Force exit after this many minutes' });
    h += field('noNewEntries', 'No New Entries After', 'time', { value: ex.no_new_entries_after || '14:30', help: 'Stop opening new positions (ET)' });
    h += field('closeLosers', 'Close Losers At', 'time', { value: ex.close_losers_at || '14:45', help: 'Close all losing positions (ET)' });
    h += field('hardExit', 'Hard Exit Time', 'time', { value: ex.hard_exit_time || '15:00', help: 'Force exit ALL positions (ET)' });

    h += sectionTitle('Theta Decay');
    h += field('thetaEnabled', 'Theta Decay Exit', 'toggle', { checked: ex.theta_decay_exit !== false });
    h += field('thetaThreshold', 'Theta Threshold', 'number', { value: pct(ex.theta_decay_threshold || -0.03), suffix: '%', min:-20, max:0, step:0.5, help: 'Exit when theta alone causes this loss' });

    return h;
  }

  function buildPartialExits(d) {
    const ex = d.exit_rules || {};
    let h = sectionTitle('Scale-Out Rules');
    h += field('partialEnabled', 'Partial Exits', 'toggle', { checked: ex.partial_exit_enabled !== false, help: 'Scale out at profit tiers (multi-contract only)' });

    const tiers = ex.partial_exit_tiers || [
      { label: 'T1', pnl_pct: 0.30, exit_frac: 0.33 },
      { label: 'T2', pnl_pct: 0.60, exit_frac: 0.50 },
    ];
    tiers.forEach((tier, i) => {
      h += `<div style="background:var(--surface-2);border-radius:var(--radius-md);padding:var(--space-sm);margin:var(--space-xs) 0">`;
      h += `<div style="font-size:var(--font-2xs);font-weight:var(--font-bold);color:var(--text-secondary);margin-bottom:var(--space-xs)">TIER ${i+1} — ${tier.label}</div>`;
      h += field(`partialPnl${i}`, 'Trigger at PnL', 'number', { value: pct(tier.pnl_pct), suffix: '%', min:5, max:500, step:5, horizontal: true });
      h += field(`partialFrac${i}`, 'Sell Fraction', 'number', { value: (tier.exit_frac * 100).toFixed(0), suffix: '%', min:10, max:90, step:5, horizontal: true });
      h += `</div>`;
    });

    h += sectionTitle('Remainder Trail');
    h += field('remainderTrail', 'Remainder Trail Stop', 'number', { value: pct(ex.remainder_trail_pct), suffix: '%', min:3, max:50, step:1, help: 'Tighter trail after all partials taken' });

    return h;
  }

  function buildDynamicExit(d) {
    const dex = d.dynamic_exit || {};
    let h = sectionTitle('Dynamic Exit Engine');
    h += field('dexEnabled', 'Dynamic Exit', 'toggle', { checked: dex.enabled === true, help: 'AI-weighted exit signals based on multi-factor analysis' });

    h += sectionTitle('Factor Weights');
    h += `<div class="ff-help" style="margin-bottom:var(--space-sm)">Weights must sum to 1.0. Controls how much each factor contributes to exit decisions.</div>`;
    h += field('dexMomentum', 'Momentum', 'number', { value: dex.w_momentum ?? 0.25, min:0, max:1, step:0.05 });
    h += field('dexGreeks', 'Greeks', 'number', { value: dex.w_greeks ?? 0.20, min:0, max:1, step:0.05 });
    h += field('dexLevels', 'Levels', 'number', { value: dex.w_levels ?? 0.20, min:0, max:1, step:0.05 });
    h += field('dexSession', 'Session', 'number', { value: dex.w_session ?? 0.15, min:0, max:1, step:0.05 });
    h += field('dexFlow', 'Flow', 'number', { value: dex.w_flow ?? 0.20, min:0, max:1, step:0.05 });

    return h;
  }

  function buildSignals(d) {
    const fp = d.fast_path || {};
    const llm = d.llm_validator || {};

    let h = sectionTitle('Fast Path (Event-Driven Entry)');
    h += field('fpEnabled', 'Fast Path', 'toggle', { checked: fp.enabled === true, help: 'Bypass analysis loop for high-conviction flow events' });
    h += field('fpMinTier', 'Fast Path Min Tier', 'select', {
      value: fp.min_tier || 'HIGH',
      options: [
        { value:'VALID', label:'VALID' },
        { value:'HIGH', label:'HIGH' },
        { value:'TEXTBOOK', label:'TEXTBOOK' },
      ]
    });
    h += field('fpMinConf', 'Fast Path Min Confidence', 'number', { value: fp.min_confidence || 0.65, min:0.3, max:0.99, step:0.05 });
    h += field('fpCooldown', 'Cooldown', 'number', { value: fp.cooldown_seconds || 60, suffix: 'sec', min:10, max:600, step:10 });

    h += sectionTitle('LLM Validator');
    h += field('llmEnabled', 'LLM Validation', 'toggle', { checked: llm.enabled === true, help: 'Claude advisory — never blocks trades, logs verdict' });
    h += field('llmMinTier', 'Min Tier for LLM', 'select', {
      value: llm.min_tier || 'HIGH',
      options: [
        { value:'VALID', label:'VALID' },
        { value:'HIGH', label:'HIGH' },
        { value:'TEXTBOOK', label:'TEXTBOOK' },
      ]
    });

    h += sectionTitle('Market Hours');
    h += field('tradingStart', 'Trading Start', 'time', { value: d.trading_start || '09:35', help: 'Signals only fire after this (ET)' });
    h += field('tradingEnd', 'Trading End', 'time', { value: d.trading_end || '15:55', help: 'No new signals after this (ET)' });

    return h;
  }

  function buildSystem(d) {
    const data = d.data || {};
    let h = sectionTitle('Connection Status');
    h += `<div style="display:flex;gap:var(--space-sm);margin-bottom:var(--space-md)">`;
    h += statusCard('ThetaData', data.theta_enabled ? 'Enabled' : 'Disabled', data.theta_enabled ? 'positive' : 'text-muted');
    h += statusCard('Data Feed', (data.alpaca_data_feed || 'sip').toUpperCase(), 'accent');
    h += `</div>`;

    h += sectionTitle('Data Sources (read-only)');
    h += field('thetaUrl', 'ThetaData URL', 'text', { value: data.theta_base_url || 'http://localhost:25510' });
    h += field('flowUrl', 'Flow Engine URL', 'text', { value: data.flow_engine_url || 'http://localhost:4001' });

    h += `<div class="modal-divider"></div>`;
    h += sectionTitle('Danger Zone');
    h += `<div class="ff-help" style="margin-bottom:var(--space-sm);color:var(--negative)">Wipes all open positions and today's trade history. The bot restarts fresh. Cannot be undone.</div>`;
    h += `<button class="btn btn--negative btn--md" id="s_resetBtn">Reset Paper Account</button>`;
    h += `<div id="s_resetMsg" style="font-size:var(--font-2xs);color:var(--text-muted);margin-top:var(--space-xs);min-height:14px"></div>`;

    return h;
  }

  // ── Collect values from form ────────────────────────────────────────
  function gv(id) { return document.getElementById('s_' + id)?.value ?? ''; }
  function gc(id) { return document.getElementById('s_' + id)?.checked ?? false; }

  function collectPayload() {
    return {
      risk: {
        max_daily_loss:          fromPct(gv('maxDailyLoss')),
        max_open_positions:      parseInt(gv('maxOpenPos')) || 3,
        max_trades_per_day:      parseInt(gv('maxTradesDay')) || 5,
        max_risk_per_trade_pct:  fromPct(gv('riskPerTrade')),
        min_seconds_between_trades: parseInt(gv('minSecBetween')) || 30,
        daily_loss_throttle:     fromPct(gv('dailyLossThrottle')),
      },
      min_tier:       gv('minTier') || 'VALID',
      min_confidence: parseFloat(gv('minConf')) || 0.45,
      exit_rules: {
        stop_loss_pct:            fromPct(gv('stopLoss')),
        profit_target_pct:        fromPct(gv('profitTarget')),
        trailing_stop_pct:        fromPct(gv('trailingStop')),
        trailing_stop_activation: fromPct(gv('trailingActivation')),
        max_hold_minutes:         parseInt(gv('maxHoldMin')) || 60,
        no_new_entries_after:     gv('noNewEntries') || '14:30',
        close_losers_at:          gv('closeLosers') || '14:45',
        hard_exit_time:           gv('hardExit') || '15:00',
        theta_decay_exit:         gc('thetaEnabled'),
        theta_decay_threshold:    fromPct(gv('thetaThreshold')),
        partial_exit_enabled:     gc('partialEnabled'),
        partial_exit_tiers: [
          { label: 'T1', pnl_pct: fromPct(gv('partialPnl0')), exit_frac: fromPct(gv('partialFrac0')) },
          { label: 'T2', pnl_pct: fromPct(gv('partialPnl1')), exit_frac: fromPct(gv('partialFrac1')) },
        ],
        remainder_trail_pct:      fromPct(gv('remainderTrail')),
      },
    };
  }

  // ── Save ─────────────────────────────────────────────────────────────
  async function save() {
    const payload = collectPayload();
    try {
      const r = await fetch('/api/pm/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      Toast.success('Settings Saved', 'All changes applied to live session');
      _dirty = false;
    } catch (e) {
      console.error('[Settings] save error:', e);
      Toast.error('Save Failed', e.message);
    }
  }

  // ── Reset ────────────────────────────────────────────────────────────
  async function resetAccount() {
    if (!confirm('Reset the paper account? This will close all open positions and wipe today\'s P&L. This cannot be undone.')) return;
    const msgEl = document.getElementById('s_resetMsg');
    if (msgEl) { msgEl.textContent = 'Resetting…'; msgEl.style.color = 'var(--text-muted)'; }
    try {
      const r = await fetch('/api/pm/reset', { method: 'POST' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      Toast.success('Account Reset', `Closed ${d.closed_positions} position(s), cleared ${d.deleted_rows} trade(s)`);
      if (msgEl) { msgEl.textContent = ''; }
      if (typeof refreshPositionsTab === 'function') refreshPositionsTab();
    } catch (e) {
      console.error('[Settings] reset error:', e);
      Toast.error('Reset Failed', e.message);
      if (msgEl) { msgEl.textContent = '✗ Reset failed'; msgEl.style.color = 'var(--negative)'; }
    }
  }

  // ── Init ─────────────────────────────────────────────────────────────
  function init() {
    _modal = new Modal({
      title: 'Settings',
      subtitle: 'Paper Trading Configuration',
      size: 'lg',
      closable: true,
      closeOnBackdrop: true,
      footer: true,
      footerActions: [
        { label: 'Cancel', variant: '', size: 'md', onClick: () => _modal.close() },
        { label: 'Save Settings', variant: 'positive', size: 'md', onClick: () => save() },
      ],
      sidebar: [
        { key: 'account',  label: 'Account & Risk', icon: '💰' },
        { key: 'exits',    label: 'Exit Rules',     icon: '🚪' },
        { key: 'partials', label: 'Scale-Out',      icon: '📊' },
        { key: 'dex',      label: 'Dynamic Exit',   icon: '🤖' },
        { key: 'signals',  label: 'Signals',        icon: '📡' },
        { key: 'system',   label: 'System',         icon: '⚙' },
      ],
      onOpen: () => loadSettingsData(),
      onSidebarChange: (key) => renderSection(key),
    });
  }

  async function loadSettingsData() {
    try {
      const r = await fetch('/api/pm/settings');
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      _data = await r.json();
      renderSection(_modal.getActiveSidebar());
    } catch (e) {
      console.warn('[Settings] load error:', e);
      Toast.warning('Settings', 'Could not load settings from server');
    }
  }

  function renderSection(key) {
    const builders = {
      account:  buildAccount,
      exits:    buildExitRules,
      partials: buildPartialExits,
      dex:      buildDynamicExit,
      signals:  buildSignals,
      system:   buildSystem,
    };
    const html = (builders[key] || builders.account)(_data);
    _modal.setSidebarContent(key, html);

    // Attach reset button handler if on system tab
    if (key === 'system') {
      const resetBtn = document.getElementById('s_resetBtn');
      if (resetBtn) resetBtn.addEventListener('click', resetAccount);
    }
  }

  return {
    open()  { if (!_modal) init(); _modal.open(); },
    close() { if (_modal) _modal.close(); },
  };
})();

window._settingsManager = SettingsManager;

// Legacy compat aliases
async function loadSettings(){ /* handled by SettingsManager.open() */ }
async function saveSettings(){ SettingsManager.open(); }
async function resetPaperAccount(){ SettingsManager.open(); }

