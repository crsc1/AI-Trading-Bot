/* ═══════════════════════════════════════════════════════════════════════════
   TableUpgrade — Progressive Enhancement for Existing Tables
   ═══════════════════════════════════════════════════════════════════════════
   Enhances an existing <table> element in-place with:
   - Resizable columns (drag column header borders)
   - Optional sortable headers
   - Preserved existing event handlers and styles

   This is a NON-DESTRUCTIVE migration tool. It does NOT replace the table
   element — it enhances the existing one. Existing render functions
   (like loadAgentHistory) keep writing to the same <tbody> as before.

   Usage:
     // After the table is in the DOM:
     const upgrade = new TableUpgrade({
       table: '#agHistTable',   // Selector or element
       resizable: true,         // Enable column dragging
       sortable: false,         // Enable click-to-sort headers
       minColWidth: 40,         // Minimum column width in px
       persistKey: 'agHist',    // LocalStorage key for persisted widths
     });

     // Re-scan columns (if columns change dynamically):
     upgrade.refresh();

     // Remove enhancements:
     upgrade.destroy();
   ═══════════════════════════════════════════════════════════════════════════ */

class TableUpgrade {
  constructor(options) {
    this.options = {
      table: null,
      resizable: true,
      sortable: false,
      minColWidth: 40,
      persistKey: null,
      onSort: null,
      ...options,
    };

    this._table = typeof this.options.table === 'string'
      ? document.querySelector(this.options.table)
      : this.options.table;

    if (!this._table) {
      console.warn('[TableUpgrade] Table not found:', this.options.table);
      return;
    }

    this._colWidths = {};    // colIndex → width
    this._resizing = null;
    this._handles = [];
    this._sortCol = -1;
    this._sortAsc = true;

    // Load persisted widths
    this._loadWidths();

    // Apply table-layout: fixed for resizable columns
    if (this.options.resizable) {
      this._table.style.tableLayout = 'fixed';
    }

    // Enhance headers
    this._enhance();

    // Bind resize handlers
    this._onResizeMove = this._onResizeMove.bind(this);
    this._onResizeEnd = this._onResizeEnd.bind(this);
  }

  /** Re-scan and re-enhance (call after dynamic column changes) */
  refresh() {
    this._cleanup();
    this._enhance();
  }

  /** Remove all enhancements */
  destroy() {
    this._cleanup();
    document.removeEventListener('mousemove', this._onResizeMove);
    document.removeEventListener('mouseup', this._onResizeEnd);
    if (this._table) {
      this._table.style.tableLayout = '';
    }
  }

  // ── PRIVATE ────────────────────────────────────────────────────────────

  _enhance() {
    const ths = this._table.querySelectorAll('thead th');
    if (!ths.length) return;

    // Mark the table as enhanced
    this._table.classList.add('tu-enhanced');

    ths.forEach((th, idx) => {
      // Make position relative for handle
      th.style.position = 'relative';

      // Apply persisted width or auto-calculate initial width
      if (this._colWidths[idx]) {
        th.style.width = this._colWidths[idx] + 'px';
      }

      // Add resize handle (skip last column — it stretches to fill)
      if (this.options.resizable && idx < ths.length - 1) {
        const handle = document.createElement('div');
        handle.className = 'tu-resize-handle';
        handle.title = 'Drag to resize column';
        handle.addEventListener('mousedown', (e) => this._startResize(e, idx, th));
        th.appendChild(handle);
        this._handles.push(handle);
      }

      // Add sort capability
      if (this.options.sortable) {
        th.style.cursor = 'pointer';
        th.classList.add('tu-sortable');
        th.addEventListener('click', (e) => {
          if (e.target.closest('.tu-resize-handle')) return;
          this._doSort(idx);
        });
      }
    });
  }

  _cleanup() {
    // Remove resize handles
    this._handles.forEach(h => h.remove());
    this._handles = [];
  }

  // ── RESIZE ─────────────────────────────────────────────────────────────

  _startResize(e, colIdx, th) {
    e.preventDefault();
    e.stopPropagation();
    this._resizing = {
      colIdx,
      th,
      startX: e.clientX,
      startW: th.getBoundingClientRect().width,
    };
    this._table.classList.add('tu-resizing');
    document.addEventListener('mousemove', this._onResizeMove);
    document.addEventListener('mouseup', this._onResizeEnd);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }

  _onResizeMove(e) {
    if (!this._resizing) return;
    const { colIdx, th, startX, startW } = this._resizing;
    const dx = e.clientX - startX;
    const newW = Math.max(this.options.minColWidth, startW + dx);
    th.style.width = newW + 'px';
    this._colWidths[colIdx] = newW;
  }

  _onResizeEnd() {
    if (!this._resizing) return;
    this._resizing = null;
    this._table.classList.remove('tu-resizing');
    document.removeEventListener('mousemove', this._onResizeMove);
    document.removeEventListener('mouseup', this._onResizeEnd);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    this._saveWidths();
  }

  // ── SORT ───────────────────────────────────────────────────────────────

  _doSort(colIdx) {
    if (this._sortCol === colIdx) {
      this._sortAsc = !this._sortAsc;
    } else {
      this._sortCol = colIdx;
      this._sortAsc = true;
    }

    const tbody = this._table.querySelector('tbody');
    if (!tbody) return;

    const rows = Array.from(tbody.querySelectorAll('tr'));
    const dir = this._sortAsc ? 1 : -1;

    rows.sort((a, b) => {
      const cellA = a.cells[colIdx];
      const cellB = b.cells[colIdx];
      if (!cellA || !cellB) return 0;

      let va = cellA.textContent.trim();
      let vb = cellB.textContent.trim();

      // Try numeric sort first
      const na = parseFloat(va.replace(/[^0-9.\-]/g, ''));
      const nb = parseFloat(vb.replace(/[^0-9.\-]/g, ''));
      if (!isNaN(na) && !isNaN(nb)) return (na - nb) * dir;

      return va.localeCompare(vb) * dir;
    });

    // Re-append sorted rows
    rows.forEach(r => tbody.appendChild(r));

    // Update header indicators
    this._table.querySelectorAll('thead th').forEach((th, i) => {
      th.classList.remove('tu-sort-asc', 'tu-sort-desc');
      if (i === colIdx) {
        th.classList.add(this._sortAsc ? 'tu-sort-asc' : 'tu-sort-desc');
      }
    });

    if (this.options.onSort) this.options.onSort(colIdx, this._sortAsc);
  }

  // ── PERSISTENCE ────────────────────────────────────────────────────────

  _saveWidths() {
    if (!this.options.persistKey) return;
    try {
      localStorage.setItem('tu_' + this.options.persistKey, JSON.stringify(this._colWidths));
    } catch (e) {}
  }

  _loadWidths() {
    if (!this.options.persistKey) return;
    try {
      const raw = localStorage.getItem('tu_' + this.options.persistKey);
      if (raw) this._colWidths = JSON.parse(raw);
    } catch (e) {}
  }
}

// CSS for TableUpgrade (injected once)
(function injectTableUpgradeCSS() {
  if (document.getElementById('tu-styles')) return;
  const style = document.createElement('style');
  style.id = 'tu-styles';
  style.textContent = `
    /* Resize handle — wide hit area, thin visible line */
    .tu-resize-handle {
      position: absolute;
      right: -4px;
      top: 0;
      bottom: 0;
      width: 9px;
      cursor: col-resize;
      z-index: 2;
    }
    /* Thin visible bar inside the hit area */
    .tu-resize-handle::after {
      content: '';
      position: absolute;
      right: 4px;
      top: 4px;
      bottom: 4px;
      width: 1px;
      background: rgba(255,255,255,0.08);
      border-radius: 1px;
      transition: background 0.15s, width 0.15s;
    }
    .tu-resize-handle:hover::after {
      background: rgba(85,136,238,0.6);
      width: 2px;
      right: 3px;
    }
    .tu-resize-handle:active::after {
      background: rgba(85,136,238,0.9);
      width: 2px;
    }
    /* Active resize state on the table */
    table.tu-resizing {
      cursor: col-resize !important;
      user-select: none !important;
    }
    table.tu-resizing * {
      cursor: col-resize !important;
    }
    /* Header styles */
    .tu-enhanced th {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .tu-sortable { cursor: pointer; }
    .tu-sortable:hover { color: var(--txt, #d0d0da); }
    .tu-sort-asc::after { content: ' ▴'; color: var(--acc, #5588ee); font-size: 8px; }
    .tu-sort-desc::after { content: ' ▾'; color: var(--acc, #5588ee); font-size: 8px; }
  `;
  document.head.appendChild(style);
})();

/**
 * Static helper: enhance a table, reusing existing instance if the table was
 * rebuilt (innerHTML). Prevents memory leaks from creating new instances every refresh.
 * Usage: TableUpgrade.enhance(tableEl, { resizable: true, persistKey: 'posOpen' })
 */
TableUpgrade._registry = {};
TableUpgrade.enhance = function(tableOrSelector, options) {
  const table = typeof tableOrSelector === 'string'
    ? document.querySelector(tableOrSelector)
    : tableOrSelector;
  if (!table) return null;

  const key = options.persistKey || ('_auto_' + Math.random().toString(36).slice(2));

  // If we already have an instance for this key, destroy the old one
  if (TableUpgrade._registry[key]) {
    TableUpgrade._registry[key].destroy();
  }

  const instance = new TableUpgrade({ table, ...options });
  TableUpgrade._registry[key] = instance;
  return instance;
};

// Global scope
if (typeof window !== 'undefined') window.TableUpgrade = TableUpgrade;
if (typeof module !== 'undefined' && module.exports) module.exports = TableUpgrade;
