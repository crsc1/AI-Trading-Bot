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

  function _buildForm(id, fields, settings) {
    const form = document.createElement('div');
    form.style.cssText = 'display:flex;flex-direction:column;gap:12px;padding:4px 0';

    if (fields.includes('period')) {
      form.appendChild(_numberField('ind-period', 'Period', settings.period, 1, 200));
    }
    if (fields.includes('multiplier')) {
      form.appendChild(_numberField('ind-multiplier', 'Multiplier', settings.multiplier, 0.5, 5, 0.1));
    }
    if (fields.includes('color')) {
      form.appendChild(_colorField('ind-color', 'Color', settings.color));
    }
    if (fields.includes('lineWidth')) {
      form.appendChild(_numberField('ind-lineWidth', 'Line Width', settings.lineWidth, 1, 5));
    }
    if (fields.includes('lineStyle')) {
      form.appendChild(_selectField('ind-lineStyle', 'Line Style', settings.lineStyle, LINE_STYLES));
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

    if (fields.includes('period')) {
      const v = parseInt(document.getElementById('ind-period')?.value);
      if (v && v > 0) newSettings.period = v;
    }
    if (fields.includes('multiplier')) {
      const v = parseFloat(document.getElementById('ind-multiplier')?.value);
      if (v && v > 0) newSettings.multiplier = v;
    }
    if (fields.includes('color')) {
      const v = document.getElementById('ind-color')?.value;
      if (v) newSettings.color = v;
    }
    if (fields.includes('lineWidth')) {
      const v = parseInt(document.getElementById('ind-lineWidth')?.value);
      if (v && v > 0) newSettings.lineWidth = v;
    }
    if (fields.includes('lineStyle')) {
      const v = document.getElementById('ind-lineStyle')?.value;
      if (v !== undefined) newSettings.lineStyle = parseInt(v);
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
