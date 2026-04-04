/* ═══════════════════════════════════════════════════════════════════════════
   Modal — Reusable Dialog / Panel Component
   ═══════════════════════════════════════════════════════════════════════════
   A configurable modal with:
   - Multiple sizes (sm, md, lg, full)
   - Slide-in variant (from right edge)
   - Optional sidebar layout (for settings pages)
   - Header with title, subtitle, actions, close button
   - Scrollable body
   - Optional footer with action buttons
   - Focus trap + Escape to close
   - Backdrop click to close (configurable)
   - CSS token integration (uses tokens.css + modal.css)

   Usage:
     const modal = new Modal({
       title: 'Settings',
       subtitle: 'Configure trading parameters',
       size: 'lg',              // 'sm' | 'md' | 'lg' | 'full' | 'slide'
       closable: true,          // show X button, allow escape/backdrop close
       closeOnBackdrop: true,
       footer: true,
       footerActions: [
         { label: 'Cancel', variant: '', onClick: () => modal.close() },
         { label: 'Save', variant: 'positive', onClick: () => save() },
       ],
       sidebar: [               // optional — creates sidebar layout
         { key: 'account', label: 'Account', icon: '💰' },
         { key: 'risk',    label: 'Risk',    icon: '🛡' },
         { key: 'signals', label: 'Signals', icon: '📡' },
       ],
       onOpen: () => {},
       onClose: () => {},
       onSidebarChange: (key) => {},
     });

     // Set body content
     modal.setContent(element);
     modal.setContentHTML('<div>...</div>');

     // With sidebar: set content per sidebar section
     modal.setSidebarContent('account', element);

     // Open / close
     modal.open();
     modal.close();

     // Update footer actions
     modal.setFooterActions([...]);

     // Destroy (removes from DOM)
     modal.destroy();
   ═══════════════════════════════════════════════════════════════════════════ */

class Modal {
  constructor(options) {
    this.options = {
      title: '',
      subtitle: '',
      size: 'md',           // sm | md | lg | full | slide
      closable: true,
      closeOnBackdrop: true,
      footer: false,
      footerActions: [],
      footerSplit: false,    // space-between footer layout
      sidebar: null,         // array of { key, label, icon } or null
      headerActions: '',     // HTML string for extra header buttons
      className: '',
      onOpen: null,
      onClose: null,
      onSidebarChange: null,
    };
    Object.assign(this.options, options);

    this._isOpen = false;
    this._activeSidebar = this.options.sidebar?.[0]?.key || null;
    this._sidebarPanels = {};
    this._overlay = null;
    this._body = null;
    this._footer = null;
    this._previousFocus = null;

    this._build();
  }

  // ── PUBLIC API ──────────────────────────────────────────────────────────

  /** Open the modal */
  open() {
    if (this._isOpen) return;
    this._isOpen = true;
    this._previousFocus = document.activeElement;

    document.body.appendChild(this._overlay);

    // Force reflow before adding visible class for transition
    this._overlay.offsetHeight;
    this._overlay.classList.add('modal-visible');

    // Focus trap
    this._trapFocus();

    // Escape key handler
    this._escHandler = (e) => {
      if (e.key === 'Escape' && this.options.closable) this.close();
    };
    document.addEventListener('keydown', this._escHandler);

    // Prevent body scroll
    document.body.style.overflow = 'hidden';

    if (this.options.onOpen) this.options.onOpen();
  }

  /** Close the modal */
  close() {
    if (!this._isOpen) return;
    this._isOpen = false;

    this._overlay.classList.remove('modal-visible');

    // Remove after transition
    const onEnd = () => {
      this._overlay.removeEventListener('transitionend', onEnd);
      if (this._overlay.parentElement) {
        this._overlay.parentElement.removeChild(this._overlay);
      }
    };
    this._overlay.addEventListener('transitionend', onEnd);

    // Fallback if transitionend doesn't fire
    setTimeout(() => {
      if (this._overlay.parentElement) {
        this._overlay.parentElement.removeChild(this._overlay);
      }
    }, 400);

    // Restore
    document.removeEventListener('keydown', this._escHandler);
    document.body.style.overflow = '';
    if (this._previousFocus) this._previousFocus.focus();

    if (this.options.onClose) this.options.onClose();
  }

  /** Check if open */
  isOpen() { return this._isOpen; }

  /** Set body content (DOM element) */
  setContent(element) {
    const target = this.options.sidebar ? this._contentArea : this._body;
    if (!target) return;
    target.innerHTML = '';
    target.appendChild(element);
  }

  /** Set body content (HTML string) */
  setContentHTML(html) {
    const target = this.options.sidebar ? this._contentArea : this._body;
    if (!target) return;
    target.innerHTML = html;
  }

  /** Set content for a specific sidebar section */
  setSidebarContent(key, element) {
    if (!this._sidebarPanels[key]) {
      const panel = document.createElement('div');
      panel.className = 'tabs-panel' + (key === this._activeSidebar ? ' active' : '');
      panel.dataset.sidebarKey = key;
      this._contentArea.appendChild(panel);
      this._sidebarPanels[key] = panel;
    }
    this._sidebarPanels[key].innerHTML = '';
    if (typeof element === 'string') {
      this._sidebarPanels[key].innerHTML = element;
    } else {
      this._sidebarPanels[key].appendChild(element);
    }
  }

  /** Switch active sidebar section */
  setSidebarActive(key) {
    this._activeSidebar = key;

    // Update sidebar items
    if (this._sidebarEl) {
      this._sidebarEl.querySelectorAll('.modal-sidebar-item').forEach(item => {
        item.classList.toggle('active', item.dataset.key === key);
      });
    }

    // Update panels
    Object.entries(this._sidebarPanels).forEach(([k, panel]) => {
      panel.classList.toggle('active', k === key);
    });

    if (this.options.onSidebarChange) this.options.onSidebarChange(key);
  }

  /** Get the active sidebar key */
  getActiveSidebar() { return this._activeSidebar; }

  /** Update footer actions */
  setFooterActions(actions) {
    this.options.footerActions = actions;
    if (this._footer) this._renderFooter();
  }

  /** Get body container (for appending content dynamically) */
  getBody() { return this.options.sidebar ? this._contentArea : this._body; }

  /** Get the overlay element */
  getElement() { return this._overlay; }

  /** Destroy — remove from DOM */
  destroy() {
    if (this._isOpen) this.close();
    document.removeEventListener('keydown', this._escHandler);
    this._overlay = null;
    this._body = null;
    this._footer = null;
  }

  // ── PRIVATE: BUILD DOM ─────────────────────────────────────────────────

  _build() {
    const { title, subtitle, size, closable, closeOnBackdrop, footer,
            sidebar, headerActions, className } = this.options;

    // Overlay
    const overlay = document.createElement('div');
    overlay.className = `modal-overlay modal--${size} ${className}`.trim();
    if (closeOnBackdrop && closable) {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) this.close();
      });
    }

    // Modal container
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    if (title) modal.setAttribute('aria-label', title);

    // ── Header
    if (title || closable) {
      const header = document.createElement('div');
      header.className = 'modal-header';

      const titleWrap = document.createElement('div');
      const titleEl = document.createElement('div');
      titleEl.className = 'modal-header-title';
      titleEl.textContent = title;
      titleWrap.appendChild(titleEl);

      if (subtitle) {
        const subEl = document.createElement('div');
        subEl.className = 'modal-header-subtitle';
        subEl.textContent = subtitle;
        titleWrap.appendChild(subEl);
      }
      header.appendChild(titleWrap);

      // Header actions slot
      if (headerActions) {
        const actionsWrap = document.createElement('div');
        actionsWrap.className = 'modal-header-actions';
        actionsWrap.innerHTML = headerActions;
        header.appendChild(actionsWrap);
      }

      if (closable) {
        const closeBtn = document.createElement('button');
        closeBtn.className = 'modal-close-btn';
        closeBtn.innerHTML = '&times;';
        closeBtn.setAttribute('aria-label', 'Close');
        closeBtn.addEventListener('click', () => this.close());
        header.appendChild(closeBtn);
      }

      modal.appendChild(header);
    }

    // ── Body (with or without sidebar)
    if (sidebar && sidebar.length > 0) {
      const withSidebar = document.createElement('div');
      withSidebar.className = 'modal-with-sidebar';

      // Sidebar nav
      const sidebarEl = document.createElement('nav');
      sidebarEl.className = 'modal-sidebar';
      sidebarEl.setAttribute('role', 'tablist');
      sidebar.forEach(item => {
        const sideItem = document.createElement('div');
        sideItem.className = 'modal-sidebar-item' + (item.key === this._activeSidebar ? ' active' : '');
        sideItem.dataset.key = item.key;
        sideItem.setAttribute('role', 'tab');
        sideItem.setAttribute('aria-selected', item.key === this._activeSidebar ? 'true' : 'false');
        if (item.icon) {
          const icon = document.createElement('span');
          icon.className = 'modal-sidebar-icon';
          icon.textContent = item.icon;
          sideItem.appendChild(icon);
        }
        const label = document.createElement('span');
        label.textContent = item.label;
        sideItem.appendChild(label);
        sideItem.addEventListener('click', () => this.setSidebarActive(item.key));
        sidebarEl.appendChild(sideItem);
      });
      this._sidebarEl = sidebarEl;
      withSidebar.appendChild(sidebarEl);

      // Content area
      const contentArea = document.createElement('div');
      contentArea.className = 'modal-content-area';
      contentArea.setAttribute('role', 'tabpanel');
      this._contentArea = contentArea;
      withSidebar.appendChild(contentArea);

      modal.appendChild(withSidebar);
    } else {
      const body = document.createElement('div');
      body.className = 'modal-body';
      this._body = body;
      modal.appendChild(body);
    }

    // ── Footer
    if (footer) {
      const footerEl = document.createElement('div');
      footerEl.className = 'modal-footer' + (this.options.footerSplit ? ' modal-footer--split' : '');
      this._footer = footerEl;
      this._renderFooter();
      modal.appendChild(footerEl);
    }

    overlay.appendChild(modal);
    this._overlay = overlay;
    this._modal = modal;
  }

  _renderFooter() {
    if (!this._footer) return;
    this._footer.innerHTML = '';
    this.options.footerActions.forEach(action => {
      const btn = document.createElement('button');
      const variant = action.variant ? ` btn--${action.variant}` : '';
      const size = action.size ? ` btn--${action.size}` : ' btn--md';
      btn.className = `btn${variant}${size}`;
      if (action.disabled) btn.disabled = true;
      btn.textContent = action.label;
      if (action.onClick) btn.addEventListener('click', action.onClick);
      this._footer.appendChild(btn);
    });
  }

  _trapFocus() {
    if (!this._modal) return;
    const focusable = this._modal.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (focusable.length > 0) focusable[0].focus();
  }
}

// Attach to global scope
if (typeof window !== 'undefined') window.Modal = Modal;
if (typeof module !== 'undefined' && module.exports) module.exports = Modal;
