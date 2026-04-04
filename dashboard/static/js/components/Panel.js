/* ═══════════════════════════════════════════════════════════════════════════
   Panel — Collapsible, Resizable Section Component
   ═══════════════════════════════════════════════════════════════════════════
   A configurable panel with:
   - Collapsible header (click to toggle)
   - Vertical resize handle (drag bottom edge)
   - Configurable min/max height
   - Persist collapsed state to localStorage
   - Header action buttons slot
   - CSS token integration

   Usage:
     const panel = new Panel({
       container: '#myWrap',
       title: 'Open Positions',
       id: 'positions-panel',       // Used for state persistence key
       collapsible: true,
       collapsed: false,
       resizable: true,
       minHeight: 80,
       maxHeight: 500,
       defaultHeight: 200,
       headerActions: '<button class="bar-btn">Refresh</button>',
       className: '',
       onCollapse: (collapsed) => {},
       onResize: (height) => {},
     });

     // Set body content
     panel.setContent(element);
     panel.setContentHTML('<div>...</div>');

     // Programmatic control
     panel.collapse();
     panel.expand();
     panel.toggle();
     panel.setHeight(300);

     // Get body container (for appending DataTable etc.)
     panel.getBody();

     // Destroy
     panel.destroy();
   ═══════════════════════════════════════════════════════════════════════════ */

class Panel {
  constructor(options) {
    this.options = {
      container: null,
      title: 'Panel',
      id: null,
      collapsible: true,
      collapsed: false,
      resizable: false,
      minHeight: 60,
      maxHeight: 600,
      defaultHeight: null,    // null = auto (flex)
      headerActions: '',
      className: '',
      icon: null,             // Optional icon HTML for header
      badge: null,            // Optional badge text
      onCollapse: null,
      onResize: null,
    };
    Object.assign(this.options, options);

    this._collapsed = this.options.collapsed;
    this._height = this.options.defaultHeight;
    this._el = null;
    this._header = null;
    this._body = null;
    this._resizing = null;

    // Restore persisted state
    if (this.options.id) {
      const saved = this._loadState();
      if (saved) {
        if (saved.collapsed !== undefined) this._collapsed = saved.collapsed;
        if (saved.height !== undefined) this._height = saved.height;
      }
    }

    this._build();
    this._applyState();

    // Bind resize handlers
    this._onResizeMove = this._onResizeMove.bind(this);
    this._onResizeEnd = this._onResizeEnd.bind(this);
  }

  // ── PUBLIC API ──────────────────────────────────────────────────────────

  /** Set body content from an element */
  setContent(element) {
    if (this._body) {
      this._body.innerHTML = '';
      this._body.appendChild(element);
    }
  }

  /** Set body content from HTML string */
  setContentHTML(html) {
    if (this._body) this._body.innerHTML = html;
  }

  /** Get the body container element */
  getBody() {
    return this._body;
  }

  /** Get the root element */
  getElement() {
    return this._el;
  }

  /** Collapse the panel */
  collapse() {
    this._collapsed = true;
    this._applyState();
    this._saveState();
    if (this.options.onCollapse) this.options.onCollapse(true);
  }

  /** Expand the panel */
  expand() {
    this._collapsed = false;
    this._applyState();
    this._saveState();
    if (this.options.onCollapse) this.options.onCollapse(false);
  }

  /** Toggle collapse state */
  toggle() {
    if (this._collapsed) this.expand();
    else this.collapse();
  }

  /** Set panel height programmatically */
  setHeight(h) {
    this._height = Math.max(this.options.minHeight, Math.min(this.options.maxHeight, h));
    this._applyState();
    this._saveState();
  }

  /** Update the badge text */
  setBadge(text) {
    const badgeEl = this._header?.querySelector('.pnl-badge');
    if (badgeEl) {
      badgeEl.textContent = text || '';
      badgeEl.style.display = text ? '' : 'none';
    }
  }

  /** Update header actions HTML */
  setHeaderActions(html) {
    const slot = this._header?.querySelector('.pnl-actions');
    if (slot) slot.innerHTML = html;
  }

  /** Destroy the panel */
  destroy() {
    document.removeEventListener('mousemove', this._onResizeMove);
    document.removeEventListener('mouseup', this._onResizeEnd);
    if (this._el && this._el.parentElement) {
      this._el.parentElement.removeChild(this._el);
    }
    this._el = null;
  }

  // ── PRIVATE: BUILD ─────────────────────────────────────────────────────

  _build() {
    const container = typeof this.options.container === 'string'
      ? document.querySelector(this.options.container)
      : this.options.container;
    if (!container) return;

    // Root
    const root = document.createElement('div');
    root.className = `pnl ${this.options.className}`.trim();
    if (this.options.id) root.id = this.options.id;

    // Header
    const header = document.createElement('div');
    header.className = 'pnl-header';

    // Title area (left)
    const titleArea = document.createElement('div');
    titleArea.className = 'pnl-title-area';

    if (this.options.collapsible) {
      const chevron = document.createElement('span');
      chevron.className = 'pnl-chevron';
      chevron.innerHTML = '&#x25B6;'; // Right-pointing triangle
      titleArea.appendChild(chevron);
    }

    if (this.options.icon) {
      const iconEl = document.createElement('span');
      iconEl.className = 'pnl-icon';
      iconEl.innerHTML = this.options.icon;
      titleArea.appendChild(iconEl);
    }

    const title = document.createElement('span');
    title.className = 'pnl-title';
    title.textContent = this.options.title;
    titleArea.appendChild(title);

    if (this.options.badge !== null) {
      const badge = document.createElement('span');
      badge.className = 'pnl-badge';
      badge.textContent = this.options.badge || '';
      if (!this.options.badge) badge.style.display = 'none';
      titleArea.appendChild(badge);
    }

    header.appendChild(titleArea);

    // Actions area (right)
    const actions = document.createElement('div');
    actions.className = 'pnl-actions';
    actions.innerHTML = this.options.headerActions;
    header.appendChild(actions);

    // Click to toggle
    if (this.options.collapsible) {
      titleArea.style.cursor = 'pointer';
      titleArea.addEventListener('click', () => this.toggle());
    }

    root.appendChild(header);
    this._header = header;

    // Body
    const body = document.createElement('div');
    body.className = 'pnl-body';
    root.appendChild(body);
    this._body = body;

    // Resize handle
    if (this.options.resizable) {
      const handle = document.createElement('div');
      handle.className = 'pnl-resize-handle';
      handle.addEventListener('mousedown', (e) => this._startResize(e));
      root.appendChild(handle);
    }

    container.appendChild(root);
    this._el = root;
  }

  _applyState() {
    if (!this._el) return;

    // Collapse
    if (this._collapsed) {
      this._el.classList.add('pnl--collapsed');
      this._body.style.display = 'none';
    } else {
      this._el.classList.remove('pnl--collapsed');
      this._body.style.display = '';
    }

    // Height
    if (this._height && !this._collapsed) {
      this._el.style.height = this._height + 'px';
      this._body.style.flex = '1';
      this._body.style.minHeight = '0';
      this._body.style.overflow = 'auto';
    } else if (!this._collapsed && !this._height) {
      this._el.style.height = '';
    }

    // Chevron rotation
    const chevron = this._header?.querySelector('.pnl-chevron');
    if (chevron) {
      chevron.style.transform = this._collapsed ? 'rotate(0deg)' : 'rotate(90deg)';
    }
  }

  // ── PRIVATE: RESIZE ────────────────────────────────────────────────────

  _startResize(e) {
    e.preventDefault();
    this._resizing = {
      startY: e.clientY,
      startH: this._el.getBoundingClientRect().height,
    };
    document.addEventListener('mousemove', this._onResizeMove);
    document.addEventListener('mouseup', this._onResizeEnd);
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
  }

  _onResizeMove(e) {
    if (!this._resizing) return;
    const dy = e.clientY - this._resizing.startY;
    const newH = Math.max(this.options.minHeight, Math.min(this.options.maxHeight, this._resizing.startH + dy));
    this._height = newH;
    this._el.style.height = newH + 'px';
  }

  _onResizeEnd() {
    if (!this._resizing) return;
    this._resizing = null;
    document.removeEventListener('mousemove', this._onResizeMove);
    document.removeEventListener('mouseup', this._onResizeEnd);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    this._saveState();
    if (this.options.onResize) this.options.onResize(this._height);
  }

  // ── PRIVATE: STATE PERSISTENCE ─────────────────────────────────────────

  _saveState() {
    if (!this.options.id) return;
    try {
      const state = { collapsed: this._collapsed };
      if (this._height) state.height = this._height;
      localStorage.setItem('panel_' + this.options.id, JSON.stringify(state));
    } catch (e) { /* localStorage unavailable */ }
  }

  _loadState() {
    if (!this.options.id) return null;
    try {
      const raw = localStorage.getItem('panel_' + this.options.id);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }
}

// Global scope for non-module environments
if (typeof window !== 'undefined') window.Panel = Panel;
if (typeof module !== 'undefined' && module.exports) module.exports = Panel;
