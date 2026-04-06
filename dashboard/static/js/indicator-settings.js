// ══════════════════════════════════════════════════════════════════════════
// INDICATOR SETTINGS DIALOG — Right-click indicator button to configure
// ══════════════════════════════════════════════════════════════════════════
//
// Opens a small modal with per-indicator settings:
//   - Period (for EMA, SMA, BB)
//   - Multiplier (for BB)
//   - Color picker
//   - Line width
//   - Line style (solid / dashed / dotted)
//   - Reset to defaults
//
// Uses the Modal component and indRegistry for state.

const indSettings = (() => {
  let _modal = null;
  let _activeId = null;

  // Which settings each indicator supports
  const FIELDS = {
    ema:       ['period', 'color', 'lineWidth', 'lineStyle'],
    sma:       ['period', 'color', 'lineWidth', 'lineStyle'],
    bb:        ['period', 'multiplier', 'color', 'lineWidth', 'lineStyle'],
    vwap:      ['color', 'lineWidth', 'lineStyle'],
    vwapBands: ['color', 'lineWidth', 'lineStyle'],
    levels:    [],
    gex:       [],
    pivots:    [],
    macd:      ['fast', 'slow', 'signal', 'color', 'signalColor'],
    stoch:     ['kPeriod', 'dPeriod', 'color', 'dColor'],
    atr:       ['period', 'color'],
  };

  const LINE_STYLES = [
    { value: 0, label: 'Solid' },
    { value: 1, label: 'Dotted' },
    { value: 2, label: 'Dashed' },
  ];

  function open(id) {
    const def = indRegistry.getDefinition(id);
    if (!def) return;

    const fields = FIELDS[id];
    if (!fields || fields.length === 0) return; // No configurable settings

    _activeId = id;
    const settings = indRegistry.getSettings(id);

    if (_modal) _modal.destroy();

    _modal = new Modal({
      title: def.name + ' Settings',
      size: 'sm',
      closable: true,
      footer: true,
      footerActions: [
        { label: 'Reset', variant: '', onClick: () => _reset(id) },
        { label: 'Apply', variant: 'positive', onClick: () => _apply(id) },
      ],
    });

    _modal.setContent(_buildForm(id, fields, settings));
    _modal.open();
  }

  // Field config: maps field name to {label, type, min, max, step}
  const FIELD_CONFIG = {
    period:      { label: 'Period', type: 'number', min: 1, max: 200 },
    multiplier:  { label: 'Multiplier', type: 'number', min: 0.5, max: 5, step: 0.1 },
    fast:        { label: 'Fast Period', type: 'number', min: 1, max: 100 },
    slow:        { label: 'Slow Period', type: 'number', min: 1, max: 200 },
    signal:      { label: 'Signal Period', type: 'number', min: 1, max: 50 },
    kPeriod:     { label: '%K Period', type: 'number', min: 1, max: 100 },
    dPeriod:     { label: '%D Period', type: 'number', min: 1, max: 50 },
    color:       { label: 'Color', type: 'color' },
    signalColor: { label: 'Signal Color', type: 'color' },
    dColor:      { label: '%D Color', type: 'color' },
    lineWidth:   { label: 'Line Width', type: 'number', min: 1, max: 5 },
    lineStyle:   { label: 'Line Style', type: 'select' },
  };

  function _buildForm(id, fields, settings) {
    const form = document.createElement('div');
    form.style.cssText = 'display:flex;flex-direction:column;gap:12px;padding:4px 0';

    for (const field of fields) {
      const cfg = FIELD_CONFIG[field];
      if (!cfg) continue;
      const inputId = 'ind-' + field;
      if (cfg.type === 'number') {
        form.appendChild(_numberField(inputId, cfg.label, settings[field], cfg.min, cfg.max, cfg.step));
      } else if (cfg.type === 'color') {
        form.appendChild(_colorField(inputId, cfg.label, settings[field]));
      } else if (cfg.type === 'select') {
        form.appendChild(_selectField(inputId, cfg.label, settings[field], LINE_STYLES));
      }
    }

    return form;
  }

  function _numberField(inputId, label, value, min, max, step) {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;justify-content:space-between';
    const lbl = document.createElement('label');
    lbl.textContent = label;
    lbl.style.cssText = 'color:var(--txt-secondary);font-size:13px';
    lbl.htmlFor = inputId;
    const input = document.createElement('input');
    input.type = 'number';
    input.id = inputId;
    input.value = value;
    input.min = min;
    input.max = max;
    if (step) input.step = step;
    input.style.cssText = 'width:70px;padding:4px 8px;background:var(--bg-surface);color:var(--txt);border:1px solid var(--border);border-radius:4px;font-size:13px;text-align:right';
    row.appendChild(lbl);
    row.appendChild(input);
    return row;
  }

  function _colorField(inputId, label, value) {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;justify-content:space-between';
    const lbl = document.createElement('label');
    lbl.textContent = label;
    lbl.style.cssText = 'color:var(--txt-secondary);font-size:13px';
    lbl.htmlFor = inputId;

    const wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;align-items:center;gap:8px';

    const input = document.createElement('input');
    input.type = 'color';
    input.id = inputId;
    // Convert rgba/named colors to hex for the color picker
    input.value = _toHex(value);
    input.style.cssText = 'width:32px;height:28px;padding:0;border:1px solid var(--border);border-radius:4px;cursor:pointer;background:none';

    const preview = document.createElement('span');
    preview.id = inputId + '-preview';
    preview.textContent = _toHex(value);
    preview.style.cssText = 'font-size:11px;color:var(--txt-muted);font-family:monospace';
    input.addEventListener('input', () => { preview.textContent = input.value; });

    wrap.appendChild(input);
    wrap.appendChild(preview);
    row.appendChild(lbl);
    row.appendChild(wrap);
    return row;
  }

  function _selectField(inputId, label, value, options) {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;justify-content:space-between';
    const lbl = document.createElement('label');
    lbl.textContent = label;
    lbl.style.cssText = 'color:var(--txt-secondary);font-size:13px';
    lbl.htmlFor = inputId;
    const select = document.createElement('select');
    select.id = inputId;
    select.style.cssText = 'width:90px;padding:4px 8px;background:var(--bg-surface);color:var(--txt);border:1px solid var(--border);border-radius:4px;font-size:13px';
    options.forEach(opt => {
      const o = document.createElement('option');
      o.value = opt.value;
      o.textContent = opt.label;
      if (opt.value === value) o.selected = true;
      select.appendChild(o);
    });
    row.appendChild(lbl);
    row.appendChild(select);
    return row;
  }

  function _apply(id) {
    const fields = FIELDS[id];
    const newSettings = {};

    for (const field of fields) {
      const cfg = FIELD_CONFIG[field];
      if (!cfg) continue;
      const el = document.getElementById('ind-' + field);
      if (!el) continue;
      if (cfg.type === 'number') {
        const v = parseFloat(el.value);
        if (v && v > 0) newSettings[field] = cfg.step ? v : parseInt(el.value);
      } else if (cfg.type === 'color') {
        if (el.value) newSettings[field] = el.value;
      } else if (cfg.type === 'select') {
        newSettings[field] = parseInt(el.value);
      }
    }

    indRegistry.setSettings(id, newSettings);
    if (_modal) _modal.close();
  }

  function _reset(id) {
    const def = indRegistry.getDefinition(id);
    if (!def) return;
    indRegistry.setSettings(id, { ...def.defaultSettings });
    if (_modal) _modal.close();
  }

  // Convert CSS color to hex (best-effort for color picker)
  function _toHex(color) {
    if (!color) return '#ffffff';
    if (color.startsWith('#') && (color.length === 7 || color.length === 4)) return color;
    // Use canvas to resolve named/rgba colors
    const ctx = document.createElement('canvas').getContext('2d');
    ctx.fillStyle = color;
    const resolved = ctx.fillStyle; // returns hex or rgb()
    if (resolved.startsWith('#')) return resolved;
    // Parse rgb(r,g,b) or rgba(r,g,b,a)
    const m = resolved.match(/(\d+)/g);
    if (m && m.length >= 3) {
      return '#' + [m[0], m[1], m[2]].map(n => parseInt(n).toString(16).padStart(2, '0')).join('');
    }
    return '#ffffff';
  }

  return { open };
})();

// Global helper for onclick/oncontextmenu in HTML
function openIndSettings(id) { indSettings.open(id); }
