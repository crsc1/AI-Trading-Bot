// ══════════════════════════════════════════════════════════════════════════
// INDICATOR PRESETS — Named indicator sets saved to localStorage
// ══════════════════════════════════════════════════════════════════════════
//
// Built-in presets + user-created custom presets.
// Each preset is a full state snapshot from indRegistry.getState().

const indPresets = (() => {
  const STORAGE_KEY = 'ind_presets';

  // Built-in presets (not editable)
  const BUILTINS = {
    '0dte-scalp': {
      name: '0DTE Scalp',
      state: {
        ema:  { enabled: true,  settings: { period: 9, color: '#ffb300', lineWidth: 1, lineStyle: 0 } },
        sma:  { enabled: false, settings: {} },
        bb:   { enabled: false, settings: {} },
        vwap: { enabled: true,  settings: { color: '#00e5ff', lineWidth: 2, lineStyle: 0 } },
        vwapBands: { enabled: true, settings: { color: 'rgba(0,229,255,0.45)', lineWidth: 1, lineStyle: 2 } },
        levels: { enabled: true, settings: {} },
        gex:    { enabled: true, settings: {} },
        pivots: { enabled: false, settings: {} },
        macd:   { enabled: false, settings: {} },
        stoch:  { enabled: false, settings: {} },
        atr:    { enabled: false, settings: {} },
      },
    },
    'swing': {
      name: 'Swing',
      state: {
        ema:  { enabled: true,  settings: { period: 21, color: '#ffb300', lineWidth: 1, lineStyle: 0 } },
        sma:  { enabled: true,  settings: { period: 50, color: '#42a5f5', lineWidth: 1, lineStyle: 0 } },
        bb:   { enabled: true,  settings: { period: 20, multiplier: 2, color: 'rgba(156,39,176,.5)', lineWidth: 1, lineStyle: 0 } },
        vwap: { enabled: false, settings: {} },
        vwapBands: { enabled: false, settings: {} },
        levels: { enabled: false, settings: {} },
        gex:    { enabled: false, settings: {} },
        pivots: { enabled: false, settings: {} },
        macd:   { enabled: true,  settings: { fast: 12, slow: 26, signal: 9, color: '#2196f3', signalColor: '#ff9800' } },
        stoch:  { enabled: false, settings: {} },
        atr:    { enabled: false, settings: {} },
      },
    },
    'clean': {
      name: 'Clean',
      state: {}, // empty = all off
    },
    'full': {
      name: 'Full',
      state: {
        ema: { enabled: true, settings: {} },
        sma: { enabled: true, settings: {} },
        bb:  { enabled: true, settings: {} },
        vwap: { enabled: true, settings: {} },
        vwapBands: { enabled: true, settings: {} },
        levels: { enabled: true, settings: {} },
        gex: { enabled: true, settings: {} },
        pivots: { enabled: true, settings: {} },
        macd: { enabled: true, settings: {} },
        stoch: { enabled: true, settings: {} },
        atr: { enabled: true, settings: {} },
      },
    },
  };

  function _loadCustom() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (e) { return {}; }
  }

  function _saveCustom(presets) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(presets)); } catch (e) {}
  }

  function apply(key) {
    const preset = BUILTINS[key] || _loadCustom()[key];
    if (!preset) return;
    indRegistry.applyState(preset.state);
    _updateDropdown(key);
  }

  function saveCustom(name) {
    const key = 'custom-' + name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
    const custom = _loadCustom();
    custom[key] = { name, state: indRegistry.getState() };
    _saveCustom(custom);
    _rebuildDropdown();
    return key;
  }

  function deleteCustom(key) {
    const custom = _loadCustom();
    delete custom[key];
    _saveCustom(custom);
    _rebuildDropdown();
  }

  function getAll() {
    const all = {};
    for (const [k, v] of Object.entries(BUILTINS)) all[k] = { ...v, builtin: true };
    for (const [k, v] of Object.entries(_loadCustom())) all[k] = { ...v, builtin: false };
    return all;
  }

  // ── Dropdown UI ─────────────────────────────────────────────────────────

  function _rebuildDropdown() {
    const sel = document.getElementById('selPreset');
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = '<option value="">Presets</option>';

    // Built-ins
    for (const [k, v] of Object.entries(BUILTINS)) {
      const opt = document.createElement('option');
      opt.value = k;
      opt.textContent = v.name;
      sel.appendChild(opt);
    }

    // Custom
    const custom = _loadCustom();
    const keys = Object.keys(custom);
    if (keys.length > 0) {
      const sep = document.createElement('option');
      sep.disabled = true;
      sep.textContent = '───────────';
      sel.appendChild(sep);
      for (const [k, v] of Object.entries(custom)) {
        const opt = document.createElement('option');
        opt.value = k;
        opt.textContent = v.name;
        sel.appendChild(opt);
      }
    }

    sel.value = current;
  }

  function _updateDropdown(key) {
    const sel = document.getElementById('selPreset');
    if (sel) sel.value = key || '';
  }

  function initDropdown() {
    _rebuildDropdown();
  }

  // ── Save dialog ─────────────────────────────────────────────────────────

  function openSaveDialog() {
    const name = prompt('Preset name:');
    if (!name || !name.trim()) return;
    saveCustom(name.trim());
  }

  return { apply, saveCustom, deleteCustom, getAll, initDropdown, openSaveDialog };
})();

// Global helpers for HTML
function applyPreset(key) { indPresets.apply(key); }
function savePreset() { indPresets.openSaveDialog(); }
