// ══════════════════════════════════════════════════════════════════════════
// INDICATOR REGISTRY — Centralized state, persistence, and configuration
// ══════════════════════════════════════════════════════════════════════════
//
// Replaces the hardcoded S.ind object and toggleInd() if/else chain.
// All indicator state persists to localStorage across page loads.
//
// Usage:
//   indRegistry.toggle('ema')           — toggle on/off
//   indRegistry.isEnabled('ema')        — check state
//   indRegistry.getSettings('ema')      — {period:21, color:'#ffb300', ...}
//   indRegistry.setSettings('ema', {period:9})  — update + persist + re-render
//   indRegistry.getState()              — full state snapshot (for presets)
//   indRegistry.applyState(stateObj)    — bulk apply (from presets)

const indRegistry = (() => {
  const STORAGE_KEY = 'ind_state';

  // ── Indicator Definitions ───────────────────────────────────────────────
  // Each indicator's metadata and default settings.
  // type: 'overlay' = renders on main price chart
  // type: 'sub-pane' = renders in separate chart below (RSI, CVD, future MACD/Stoch/ATR)
  // type: 'price-lines' = renders as horizontal price lines (levels, GEX, pivots)

  const DEFINITIONS = {
    ema: {
      id: 'ema', name: 'EMA', group: 'trend', type: 'overlay',
      defaultSettings: { period: 21, color: '#ffb300', lineWidth: 1, lineStyle: 0 },
      btnId: 'btnEma', shortcut: 'E',
    },
    sma: {
      id: 'sma', name: 'SMA', group: 'trend', type: 'overlay',
      defaultSettings: { period: 50, color: '#42a5f5', lineWidth: 1, lineStyle: 0 },
      btnId: 'btnSma', shortcut: 'S',
    },
    bb: {
      id: 'bb', name: 'Bollinger Bands', group: 'volatility', type: 'overlay',
      defaultSettings: { period: 20, multiplier: 2, color: 'rgba(156,39,176,.5)', lineWidth: 1, lineStyle: 0 },
      btnId: 'btnBb', shortcut: 'B',
    },
    vwap: {
      id: 'vwap', name: 'VWAP', group: 'volatility', type: 'overlay',
      defaultSettings: { color: '#00e5ff', lineWidth: 2, lineStyle: 0 },
      btnId: 'btnVwap', shortcut: null,
    },
    vwapBands: {
      id: 'vwapBands', name: 'VWAP Bands', group: 'volatility', type: 'overlay',
      defaultSettings: { color: 'rgba(0,229,255,0.45)', lineWidth: 1, lineStyle: 2 },
      btnId: 'btnVwapBands', shortcut: null,
    },
    levels: {
      id: 'levels', name: 'Session Levels', group: 'levels', type: 'price-lines',
      defaultSettings: {},
      btnId: 'btnLevels', shortcut: null,
    },
    gex: {
      id: 'gex', name: 'GEX Levels', group: 'levels', type: 'price-lines',
      defaultSettings: {},
      btnId: 'btnGex', shortcut: null,
    },
    pivots: {
      id: 'pivots', name: 'Pivot Points', group: 'levels', type: 'price-lines',
      defaultSettings: {},
      btnId: 'btnPivots', shortcut: null,
    },
  };

  // ── Runtime State ───────────────────────────────────────────────────────
  // { id: { enabled: bool, settings: {...} } }
  let _state = {};

  // Callbacks registered by charts.js for when indicators change
  let _onToggle = null;      // (id, enabled) => void
  let _onSettingsChange = null; // (id, settings) => void

  // ── Persistence ─────────────────────────────────────────────────────────

  function _save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(_state));
    } catch (e) {
      console.warn('[IndRegistry] localStorage save failed:', e);
    }
  }

  function _load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        // Merge saved state with definitions (handles new indicators added after save)
        for (const id of Object.keys(DEFINITIONS)) {
          if (parsed[id]) {
            _state[id] = {
              enabled: !!parsed[id].enabled,
              settings: { ...DEFINITIONS[id].defaultSettings, ...parsed[id].settings },
            };
          } else {
            _state[id] = {
              enabled: false,
              settings: { ...DEFINITIONS[id].defaultSettings },
            };
          }
        }
        return true;
      }
    } catch (e) {
      console.warn('[IndRegistry] localStorage load failed:', e);
    }
    return false;
  }

  function _initDefaults() {
    for (const id of Object.keys(DEFINITIONS)) {
      _state[id] = {
        enabled: false,
        settings: { ...DEFINITIONS[id].defaultSettings },
      };
    }
  }

  // ── Public API ──────────────────────────────────────────────────────────

  function init() {
    const restored = _load();
    if (!restored) {
      _initDefaults();
    }

    // Sync button UI with restored state
    for (const id of Object.keys(_state)) {
      const def = DEFINITIONS[id];
      if (def && def.btnId) {
        const btn = document.getElementById(def.btnId);
        if (btn) btn.classList.toggle('active', _state[id].enabled);
      }
    }

    // Notify charts.js to apply visibility for all restored indicators
    if (_onToggle) {
      for (const id of Object.keys(_state)) {
        if (_state[id].enabled) {
          _onToggle(id, true);
        }
      }
    }

    console.log('[IndRegistry] Initialized' + (restored ? ' (restored from localStorage)' : ' (defaults)'));
  }

  function toggle(id) {
    if (!_state[id]) return;
    _state[id].enabled = !_state[id].enabled;
    const enabled = _state[id].enabled;

    // Update button UI
    const def = DEFINITIONS[id];
    if (def && def.btnId) {
      const btn = document.getElementById(def.btnId);
      if (btn) btn.classList.toggle('active', enabled);
    }

    // Persist
    _save();

    // Notify charts
    if (_onToggle) _onToggle(id, enabled);
  }

  function isEnabled(id) {
    return _state[id] ? _state[id].enabled : false;
  }

  function getSettings(id) {
    if (!_state[id]) return DEFINITIONS[id]?.defaultSettings || {};
    return { ...(_state[id].settings || {}) };
  }

  function setSettings(id, newSettings) {
    if (!_state[id]) return;
    _state[id].settings = { ..._state[id].settings, ...newSettings };
    _save();
    if (_onSettingsChange) _onSettingsChange(id, _state[id].settings);
  }

  function getDefinition(id) {
    return DEFINITIONS[id] || null;
  }

  function getAll() {
    return Object.keys(DEFINITIONS).map(id => ({
      ...DEFINITIONS[id],
      enabled: _state[id]?.enabled || false,
      settings: _state[id]?.settings || DEFINITIONS[id].defaultSettings,
    }));
  }

  function getByGroup(group) {
    return getAll().filter(ind => ind.group === group);
  }

  // Full state snapshot (for presets)
  function getState() {
    return JSON.parse(JSON.stringify(_state));
  }

  // Bulk apply state (from presets)
  function applyState(stateObj) {
    for (const id of Object.keys(DEFINITIONS)) {
      const prev = _state[id]?.enabled || false;
      if (stateObj[id]) {
        _state[id] = {
          enabled: !!stateObj[id].enabled,
          settings: { ...DEFINITIONS[id].defaultSettings, ...stateObj[id].settings },
        };
      } else {
        _state[id] = { enabled: false, settings: { ...DEFINITIONS[id].defaultSettings } };
      }

      // Update button UI
      const def = DEFINITIONS[id];
      if (def && def.btnId) {
        const btn = document.getElementById(def.btnId);
        if (btn) btn.classList.toggle('active', _state[id].enabled);
      }

      // Notify toggle change
      const now = _state[id].enabled;
      if (now !== prev && _onToggle) {
        _onToggle(id, now);
      }
    }
    _save();
  }

  function resetToDefaults() {
    _initDefaults();
    _save();
    // Update all buttons
    for (const id of Object.keys(DEFINITIONS)) {
      const def = DEFINITIONS[id];
      if (def && def.btnId) {
        const btn = document.getElementById(def.btnId);
        if (btn) btn.classList.remove('active');
      }
      if (_onToggle) _onToggle(id, false);
    }
  }

  // Register callbacks from charts.js
  function onToggle(fn) { _onToggle = fn; }
  function onSettingsChange(fn) { _onSettingsChange = fn; }

  return {
    init,
    toggle,
    isEnabled,
    getSettings,
    setSettings,
    getDefinition,
    getAll,
    getByGroup,
    getState,
    applyState,
    resetToDefaults,
    onToggle,
    onSettingsChange,
    DEFINITIONS,
  };
})();

// Auto-init on window load (after all chart series are created by charts.js)
window.addEventListener('load', () => {
  // Small delay to ensure charts.js has registered its onToggle callback
  setTimeout(() => indRegistry.init(), 100);
});
