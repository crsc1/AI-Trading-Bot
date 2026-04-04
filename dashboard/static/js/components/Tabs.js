/* ═══════════════════════════════════════════════════════════════════════════
   Tabs — Reusable Tab Navigation Component
   ═══════════════════════════════════════════════════════════════════════════
   A configurable tab component with:
   - Horizontal (default) or vertical layout
   - Underline, pills, or compact style variants
   - Badge counts on tabs
   - Icons on tabs
   - Keyboard navigation (arrow keys)
   - ARIA roles for accessibility
   - CSS token integration (uses tokens.css + tabs.css)

   Usage:
     const tabs = new Tabs({
       container: '#myTabWrap',
       variant: 'default',       // 'default' | 'pills' | 'compact'
       vertical: false,
       tabs: [
         { key: 'positions', label: 'Positions', icon: '📊', badge: 3 },
         { key: 'history',   label: 'History',   icon: '📜' },
         { key: 'settings',  label: 'Settings',  icon: '⚙' },
       ],
       activeTab: 'positions',
       onChange: (key, prevKey) => console.log('Switched to:', key),
     });

     // Switch tab programmatically
     tabs.setActive('history');

     // Update badge
     tabs.setBadge('positions', 5);

     // Get active tab
     tabs.getActive(); // → 'history'

     // Add content to panel
     tabs.setPanelContent('positions', element);
     tabs.setPanelHTML('history', '<div>...</div>');

     // Get panel container
     tabs.getPanel('settings'); // → DOM element

     // Destroy
     tabs.destroy();
   ═══════════════════════════════════════════════════════════════════════════ */

class Tabs {
  constructor(options) {
    this.options = {
      container: null,
      variant: 'default',     // default | pills | compact
      vertical: false,
      tabs: [],
      activeTab: null,
      onChange: null,
      className: '',
    };
    Object.assign(this.options, options);

    this._active = this.options.activeTab || this.options.tabs[0]?.key || null;
    this._el = null;
    this._tabItems = {};    // key → tab button element
    this._panels = {};      // key → panel element
    this._badges = {};      // key → badge element

    this._build();
  }

  // ── PUBLIC API ──────────────────────────────────────────────────────────

  /** Set active tab */
  setActive(key) {
    const prev = this._active;
    if (key === prev) return;
    this._active = key;

    // Update tab items
    Object.entries(this._tabItems).forEach(([k, el]) => {
      const isActive = k === key;
      el.classList.toggle('active', isActive);
      el.setAttribute('aria-selected', isActive ? 'true' : 'false');
      el.setAttribute('tabindex', isActive ? '0' : '-1');
    });

    // Update panels
    Object.entries(this._panels).forEach(([k, el]) => {
      el.classList.toggle('active', k === key);
    });

    if (this.options.onChange) this.options.onChange(key, prev);
  }

  /** Get active tab key */
  getActive() { return this._active; }

  /** Update badge count */
  setBadge(key, value) {
    const badge = this._badges[key];
    if (!badge) return;
    if (value === null || value === undefined || value === 0) {
      badge.style.display = 'none';
      badge.textContent = '';
    } else {
      badge.style.display = '';
      badge.textContent = String(value);
    }
  }

  /** Set panel content (DOM element) */
  setPanelContent(key, element) {
    const panel = this._panels[key];
    if (!panel) return;
    panel.innerHTML = '';
    panel.appendChild(element);
  }

  /** Set panel content (HTML string) */
  setPanelHTML(key, html) {
    const panel = this._panels[key];
    if (!panel) return;
    panel.innerHTML = html;
  }

  /** Get panel DOM element */
  getPanel(key) { return this._panels[key] || null; }

  /** Get root element */
  getElement() { return this._el; }

  /** Destroy */
  destroy() {
    if (this._el && this._el.parentElement) {
      this._el.parentElement.removeChild(this._el);
    }
    this._el = null;
    this._tabItems = {};
    this._panels = {};
    this._badges = {};
  }

  // ── PRIVATE: BUILD DOM ─────────────────────────────────────────────────

  _build() {
    const container = typeof this.options.container === 'string'
      ? document.querySelector(this.options.container)
      : this.options.container;

    if (!container) {
      console.error('[Tabs] Container not found:', this.options.container);
      return;
    }

    // Root
    const root = document.createElement('div');
    const variantCls = this.options.variant === 'pills' ? ' tabs--pills' :
                       this.options.variant === 'compact' ? ' tabs--compact' : '';
    const verticalCls = this.options.vertical ? ' tabs--vertical' : '';
    root.className = `tabs${variantCls}${verticalCls} ${this.options.className}`.trim();

    // Tab list
    const tabList = document.createElement('div');
    tabList.className = 'tabs-list';
    tabList.setAttribute('role', 'tablist');

    this.options.tabs.forEach((tab, idx) => {
      const item = document.createElement('button');
      item.className = 'tabs-item' + (tab.key === this._active ? ' active' : '');
      item.dataset.key = tab.key;
      item.setAttribute('role', 'tab');
      item.setAttribute('aria-selected', tab.key === this._active ? 'true' : 'false');
      item.setAttribute('aria-controls', `tabpanel-${tab.key}`);
      item.setAttribute('tabindex', tab.key === this._active ? '0' : '-1');

      // Icon
      if (tab.icon) {
        const icon = document.createElement('span');
        icon.className = 'tabs-item-icon';
        icon.textContent = tab.icon;
        item.appendChild(icon);
      }

      // Label
      const label = document.createElement('span');
      label.textContent = tab.label;
      item.appendChild(label);

      // Badge
      const badge = document.createElement('span');
      badge.className = 'tabs-item-badge';
      if (tab.badge !== undefined && tab.badge !== null && tab.badge !== 0) {
        badge.textContent = String(tab.badge);
      } else {
        badge.style.display = 'none';
      }
      item.appendChild(badge);
      this._badges[tab.key] = badge;

      // Click handler
      item.addEventListener('click', () => this.setActive(tab.key));

      // Keyboard navigation
      item.addEventListener('keydown', (e) => this._onKeyDown(e, idx));

      this._tabItems[tab.key] = item;
      tabList.appendChild(item);
    });

    root.appendChild(tabList);

    // Content panels
    const content = document.createElement('div');
    content.className = 'tabs-content';

    this.options.tabs.forEach(tab => {
      const panel = document.createElement('div');
      panel.className = 'tabs-panel' + (tab.key === this._active ? ' active' : '');
      panel.id = `tabpanel-${tab.key}`;
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', tab.key);
      this._panels[tab.key] = panel;
      content.appendChild(panel);
    });

    root.appendChild(content);
    container.appendChild(root);
    this._el = root;
  }

  _onKeyDown(e, currentIdx) {
    const keys = this.options.tabs.map(t => t.key);
    const isVertical = this.options.vertical;
    let nextIdx = null;

    if ((!isVertical && e.key === 'ArrowRight') || (isVertical && e.key === 'ArrowDown')) {
      nextIdx = (currentIdx + 1) % keys.length;
    } else if ((!isVertical && e.key === 'ArrowLeft') || (isVertical && e.key === 'ArrowUp')) {
      nextIdx = (currentIdx - 1 + keys.length) % keys.length;
    } else if (e.key === 'Home') {
      nextIdx = 0;
    } else if (e.key === 'End') {
      nextIdx = keys.length - 1;
    }

    if (nextIdx !== null) {
      e.preventDefault();
      this.setActive(keys[nextIdx]);
      this._tabItems[keys[nextIdx]]?.focus();
    }
  }
}

// Attach to global scope
if (typeof window !== 'undefined') window.Tabs = Tabs;
if (typeof module !== 'undefined' && module.exports) module.exports = Tabs;
