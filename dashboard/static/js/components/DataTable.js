/* ═══════════════════════════════════════════════════════════════════════════
   DataTable — Reusable, Configurable Table Component
   ═══════════════════════════════════════════════════════════════════════════
   A drop-in table component with:
   - Resizable columns (drag column borders)
   - Sortable headers (click to sort)
   - Configurable column visibility
   - Sticky headers
   - Scrollable body (horizontal + vertical)
   - Row click handler
   - Dynamic data updates
   - CSS token integration (uses tokens.css variables)

   Usage:
     const table = new DataTable({
       container: '#myTableWrap',
       columns: [
         { key: 'symbol', label: 'Symbol', width: 80, align: 'left', sortable: true },
         { key: 'pnl',    label: 'P&L',    width: 70, align: 'right', format: 'currency' },
         { key: 'delta',  label: 'Delta',   width: 60, align: 'right', format: 'number:2' },
       ],
       data: [ { symbol: 'SPY 450C', pnl: 45.50, delta: 0.42 } ],
       onRowClick: (row, index) => console.log('Clicked:', row),
       sortable: true,
       resizable: true,
       compact: false,
       emptyMessage: 'No trades yet',
       className: '',          // Extra CSS class on <table>
       maxHeight: null,         // null = fill container, or '300px'
     });

     // Update data later:
     table.setData(newRows);

     // Update single row:
     table.updateRow(index, newRowData);

     // Toggle column visibility:
     table.toggleColumn('delta', false);

     // Destroy:
     table.destroy();
   ═══════════════════════════════════════════════════════════════════════════ */

// UMD-compatible: works as ES module or plain <script> tag
class DataTable {
  constructor(options) {
    this.options = {
      container: null,
      columns: [],
      data: [],
      onRowClick: null,
      onSort: null,
      sortable: true,
      resizable: true,
      compact: false,
      striped: false,
      emptyMessage: 'No data',
      className: '',
      maxHeight: null,
      stickyHeader: true,
      highlightOnHover: true,
      ...options,
    };

    this._sortCol = null;
    this._sortAsc = true;
    this._colWidths = {};     // key → px width
    this._hiddenCols = new Set();
    this._resizing = null;    // { key, startX, startW }
    this._el = null;          // Root element
    this._thead = null;
    this._tbody = null;
    this._data = [...this.options.data];

    // Initialize column widths from config
    this.options.columns.forEach(col => {
      this._colWidths[col.key] = col.width || 100;
      if (col.hidden) this._hiddenCols.add(col.key);
    });

    this._build();
    this._render();
  }

  // ── PUBLIC API ──────────────────────────────────────────────────────────

  /** Replace all data and re-render */
  setData(data) {
    this._data = [...data];
    this._render();
  }

  /** Update a single row by index */
  updateRow(index, rowData) {
    if (index >= 0 && index < this._data.length) {
      this._data[index] = { ...this._data[index], ...rowData };
      this._renderRow(index);
    }
  }

  /** Append rows */
  appendRows(rows) {
    this._data.push(...rows);
    this._render();
  }

  /** Show/hide a column */
  toggleColumn(key, visible) {
    if (visible === false) {
      this._hiddenCols.add(key);
    } else {
      this._hiddenCols.delete(key);
    }
    this._build();
    this._render();
  }

  /** Get visible columns */
  getVisibleColumns() {
    return this.options.columns.filter(c => !this._hiddenCols.has(c.key));
  }

  /** Get current sort state */
  getSortState() {
    return { column: this._sortCol, ascending: this._sortAsc };
  }

  /** Programmatic sort */
  sort(key, ascending = true) {
    this._sortCol = key;
    this._sortAsc = ascending;
    this._applySort();
    this._render();
    this._updateSortIndicators();
  }

  /** Clean up */
  destroy() {
    // Remove resize listeners
    document.removeEventListener('mousemove', this._onResizeMove);
    document.removeEventListener('mouseup', this._onResizeEnd);
    if (this._el && this._el.parentElement) {
      this._el.parentElement.removeChild(this._el);
    }
    this._el = null;
  }

  /** Get the DOM element */
  getElement() {
    return this._el;
  }

  // ── PRIVATE: BUILD DOM ─────────────────────────────────────────────────

  _build() {
    const container = typeof this.options.container === 'string'
      ? document.querySelector(this.options.container)
      : this.options.container;

    if (!container) {
      console.error('[DataTable] Container not found:', this.options.container);
      return;
    }

    // Remove existing table if rebuilding
    if (this._el) {
      this._el.remove();
    }

    // Wrapper for scroll
    const wrap = document.createElement('div');
    wrap.className = 'dt-wrap';
    if (this.options.maxHeight) {
      wrap.style.maxHeight = this.options.maxHeight;
    }

    // Table element
    const table = document.createElement('table');
    table.className = `dt ${this.options.compact ? 'dt--compact' : ''} ${this.options.striped ? 'dt--striped' : ''} ${this.options.className}`.trim();

    // Colgroup for column widths
    const colgroup = document.createElement('colgroup');
    this._colgroup = colgroup;
    this.getVisibleColumns().forEach(col => {
      const colEl = document.createElement('col');
      colEl.style.width = this._colWidths[col.key] + 'px';
      colEl.dataset.key = col.key;
      colgroup.appendChild(colEl);
    });
    table.appendChild(colgroup);

    // Thead
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');

    this.getVisibleColumns().forEach(col => {
      const th = document.createElement('th');
      th.dataset.key = col.key;
      th.className = col.align === 'right' ? 'dt-r' : col.align === 'center' ? 'dt-c' : '';
      if (this.options.stickyHeader) th.classList.add('dt-sticky');

      // Header content
      const label = document.createElement('span');
      label.className = 'dt-header-label';
      label.textContent = col.label || col.key;
      th.appendChild(label);

      // Sort indicator
      if (this.options.sortable && col.sortable !== false) {
        const sortIcon = document.createElement('span');
        sortIcon.className = 'dt-sort-icon';
        sortIcon.innerHTML = '&#x25B4;'; // Small up triangle
        th.appendChild(sortIcon);
        th.classList.add('dt-sortable');

        th.addEventListener('click', (e) => {
          if (e.target.closest('.dt-resize-handle')) return; // Don't sort while resizing
          if (this._sortCol === col.key) {
            this._sortAsc = !this._sortAsc;
          } else {
            this._sortCol = col.key;
            this._sortAsc = true;
          }
          this._applySort();
          this._render();
          this._updateSortIndicators();
          if (this.options.onSort) {
            this.options.onSort(this._sortCol, this._sortAsc);
          }
        });
      }

      // Resize handle
      if (this.options.resizable && col.resizable !== false) {
        const handle = document.createElement('div');
        handle.className = 'dt-resize-handle';
        handle.addEventListener('mousedown', (e) => this._startResize(e, col.key));
        th.appendChild(handle);
      }

      headerRow.appendChild(th);
    });

    thead.appendChild(headerRow);
    table.appendChild(thead);
    this._thead = thead;

    // Tbody
    const tbody = document.createElement('tbody');
    table.appendChild(tbody);
    this._tbody = tbody;

    wrap.appendChild(table);
    container.appendChild(wrap);
    this._el = wrap;
    this._table = table;

    // Bind resize handlers (once)
    this._onResizeMove = this._onResizeMove.bind(this);
    this._onResizeEnd = this._onResizeEnd.bind(this);
  }

  // ── PRIVATE: RENDER ────────────────────────────────────────────────────

  _render() {
    if (!this._tbody) return;

    const visibleCols = this.getVisibleColumns();

    if (this._data.length === 0) {
      this._tbody.innerHTML = `<tr><td colspan="${visibleCols.length}" class="dt-empty">${this.options.emptyMessage}</td></tr>`;
      return;
    }

    // Build all rows
    const frag = document.createDocumentFragment();
    this._data.forEach((row, idx) => {
      frag.appendChild(this._createRow(row, idx, visibleCols));
    });

    this._tbody.innerHTML = '';
    this._tbody.appendChild(frag);
  }

  _createRow(row, idx, visibleCols) {
    visibleCols = visibleCols || this.getVisibleColumns();
    const tr = document.createElement('tr');
    tr.dataset.idx = idx;
    if (this.options.highlightOnHover) tr.classList.add('dt-hover');

    // Row-level styling
    if (row._rowClass) tr.className += ' ' + row._rowClass;
    if (row._rowStyle) tr.style.cssText = row._rowStyle;

    visibleCols.forEach(col => {
      const td = document.createElement('td');
      td.className = col.align === 'right' ? 'dt-r' : col.align === 'center' ? 'dt-c' : '';

      // Apply cell-level class if specified
      if (col.cellClass) {
        const cls = typeof col.cellClass === 'function' ? col.cellClass(row[col.key], row) : col.cellClass;
        if (cls) td.className += ' ' + cls;
      }

      // Format value
      const raw = row[col.key];
      if (col.render) {
        // Custom render function
        const content = col.render(raw, row, idx);
        if (typeof content === 'string') {
          td.innerHTML = content;
        } else if (content instanceof HTMLElement) {
          td.appendChild(content);
        }
      } else {
        td.textContent = this._formatValue(raw, col.format);
      }

      tr.appendChild(td);
    });

    // Row click
    if (this.options.onRowClick) {
      tr.style.cursor = 'pointer';
      tr.addEventListener('click', () => this.options.onRowClick(row, idx));
    }

    return tr;
  }

  _renderRow(index) {
    if (!this._tbody) return;
    const existing = this._tbody.querySelector(`tr[data-idx="${index}"]`);
    if (!existing) return;
    const newRow = this._createRow(this._data[index], index);
    existing.replaceWith(newRow);
  }

  // ── PRIVATE: FORMATTING ────────────────────────────────────────────────

  _formatValue(val, format) {
    if (val === null || val === undefined) return '—';
    if (!format) return String(val);

    if (format === 'currency') {
      const num = Number(val);
      if (isNaN(num)) return String(val);
      const sign = num >= 0 ? '+' : '';
      return sign + '$' + Math.abs(num).toFixed(2);
    }
    if (format === 'percent') {
      const num = Number(val);
      if (isNaN(num)) return String(val);
      return (num >= 0 ? '+' : '') + num.toFixed(1) + '%';
    }
    if (format === 'volume') {
      const num = Number(val);
      if (isNaN(num)) return String(val);
      if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
      if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
      return String(num);
    }
    if (format.startsWith('number:')) {
      const decimals = parseInt(format.split(':')[1]) || 2;
      const num = Number(val);
      if (isNaN(num)) return String(val);
      return num.toFixed(decimals);
    }
    if (format === 'time') {
      if (!val) return '—';
      try {
        return new Date(val).toLocaleTimeString('en-US', {
          hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
        });
      } catch { return String(val); }
    }
    if (format === 'date') {
      if (!val) return '—';
      try {
        return new Date(val).toLocaleDateString('en-US', {
          month: 'short', day: 'numeric'
        });
      } catch { return String(val); }
    }
    if (format === 'datetime') {
      if (!val) return '—';
      try {
        const d = new Date(val);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
               d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
      } catch { return String(val); }
    }

    return String(val);
  }

  // ── PRIVATE: SORTING ───────────────────────────────────────────────────

  _applySort() {
    if (!this._sortCol) return;
    const col = this.options.columns.find(c => c.key === this._sortCol);
    if (!col) return;

    const dir = this._sortAsc ? 1 : -1;
    this._data.sort((a, b) => {
      let va = a[this._sortCol];
      let vb = b[this._sortCol];

      // Handle null/undefined
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;

      // Numeric comparison
      const na = Number(va), nb = Number(vb);
      if (!isNaN(na) && !isNaN(nb)) return (na - nb) * dir;

      // String comparison
      return String(va).localeCompare(String(vb)) * dir;
    });
  }

  _updateSortIndicators() {
    if (!this._thead) return;
    this._thead.querySelectorAll('th').forEach(th => {
      th.classList.remove('dt-sort-asc', 'dt-sort-desc');
      if (th.dataset.key === this._sortCol) {
        th.classList.add(this._sortAsc ? 'dt-sort-asc' : 'dt-sort-desc');
      }
    });
  }

  // ── PRIVATE: COLUMN RESIZE ─────────────────────────────────────────────

  _startResize(e, key) {
    e.preventDefault();
    e.stopPropagation();
    this._resizing = {
      key,
      startX: e.clientX,
      startW: this._colWidths[key] || 100,
    };
    document.addEventListener('mousemove', this._onResizeMove);
    document.addEventListener('mouseup', this._onResizeEnd);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }

  _onResizeMove(e) {
    if (!this._resizing) return;
    const { key, startX, startW } = this._resizing;
    const dx = e.clientX - startX;
    const newW = Math.max(30, startW + dx); // Minimum 30px width
    this._colWidths[key] = newW;

    // Update colgroup
    const colEl = this._colgroup?.querySelector(`col[data-key="${key}"]`);
    if (colEl) colEl.style.width = newW + 'px';
  }

  _onResizeEnd() {
    this._resizing = null;
    document.removeEventListener('mousemove', this._onResizeMove);
    document.removeEventListener('mouseup', this._onResizeEnd);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }
}

// Attach to global scope for non-module environments
if (typeof window !== 'undefined') window.DataTable = DataTable;
// ES module export for future bundler migration
if (typeof module !== 'undefined' && module.exports) module.exports = DataTable;
