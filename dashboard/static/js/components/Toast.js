/* ═══════════════════════════════════════════════════════════════════════════
   Toast — Non-Blocking Notification Component
   ═══════════════════════════════════════════════════════════════════════════
   A notification toast system with:
   - 4 variants (info, success, warning, error)
   - Auto-dismiss with progress bar
   - Manual dismiss (X button)
   - Stacking (newest at bottom)
   - CSS token integration (uses tokens.css + toast.css)

   Usage:
     // Show a toast (returns the toast instance for programmatic control)
     Toast.info('Settings saved');
     Toast.success('Trade executed', 'Bought 2x SPY 520C @ $1.45');
     Toast.warning('Approaching daily loss limit');
     Toast.error('Order rejected', 'Insufficient buying power');

     // With options
     Toast.show({
       type: 'success',          // 'info' | 'success' | 'warning' | 'error'
       title: 'Trade Executed',
       message: 'Bought 2x SPY 520C @ $1.45',
       duration: 5000,           // ms, 0 = no auto-dismiss
       closable: true,
       onClick: () => {},
     });

     // Dismiss all
     Toast.dismissAll();
   ═══════════════════════════════════════════════════════════════════════════ */

class Toast {
  // Static: shared container + toast list
  static _container = null;
  static _toasts = [];
  static _maxVisible = 5;

  static _ICONS = {
    info:    'ℹ',
    success: '✓',
    warning: '⚠',
    error:   '✕',
  };

  static _DEFAULTS = {
    type: 'info',
    title: '',
    message: '',
    duration: 4000,
    closable: true,
    onClick: null,
  };

  // ── Static convenience methods ──────────────────────────────────────────

  static info(title, message, opts = {}) {
    return Toast.show({ ...opts, type: 'info', title, message });
  }

  static success(title, message, opts = {}) {
    return Toast.show({ ...opts, type: 'success', title, message });
  }

  static warning(title, message, opts = {}) {
    return Toast.show({ ...opts, type: 'warning', title, message });
  }

  static error(title, message, opts = {}) {
    return Toast.show({ ...opts, type: 'error', title, message });
  }

  /** Show a toast with full options */
  static show(options) {
    const opts = { ...Toast._DEFAULTS, ...options };
    const toast = new Toast(opts);
    Toast._toasts.push(toast);

    // Limit visible toasts
    while (Toast._toasts.length > Toast._maxVisible) {
      Toast._toasts[0].dismiss();
    }

    return toast;
  }

  /** Dismiss all active toasts */
  static dismissAll() {
    [...Toast._toasts].forEach(t => t.dismiss());
  }

  static _ensureContainer() {
    if (Toast._container && document.body.contains(Toast._container)) return;
    Toast._container = document.createElement('div');
    Toast._container.className = 'toast-container';
    document.body.appendChild(Toast._container);
  }

  // ── Instance ────────────────────────────────────────────────────────────

  constructor(options) {
    this._options = options;
    this._el = null;
    this._timer = null;
    this._dismissed = false;

    this._build();
    this._show();
  }

  /** Dismiss this toast */
  dismiss() {
    if (this._dismissed) return;
    this._dismissed = true;
    clearTimeout(this._timer);

    if (this._el) {
      this._el.classList.remove('toast-visible');
      this._el.classList.add('toast-exiting');

      const onEnd = () => {
        this._el.removeEventListener('transitionend', onEnd);
        if (this._el.parentElement) {
          this._el.parentElement.removeChild(this._el);
        }
      };
      this._el.addEventListener('transitionend', onEnd);
      // Fallback
      setTimeout(() => {
        if (this._el && this._el.parentElement) {
          this._el.parentElement.removeChild(this._el);
        }
      }, 300);
    }

    // Remove from static list
    const idx = Toast._toasts.indexOf(this);
    if (idx > -1) Toast._toasts.splice(idx, 1);
  }

  // ── PRIVATE: BUILD ──────────────────────────────────────────────────────

  _build() {
    const { type, title, message, closable, onClick, duration } = this._options;

    Toast._ensureContainer();

    const el = document.createElement('div');
    el.className = `toast toast--${type}`;
    el.setAttribute('role', 'alert');
    el.setAttribute('aria-live', 'polite');
    if (onClick) {
      el.style.cursor = 'pointer';
      el.addEventListener('click', (e) => {
        if (!e.target.closest('.toast-close')) onClick();
      });
    }

    // Icon
    const icon = document.createElement('div');
    icon.className = 'toast-icon';
    icon.textContent = Toast._ICONS[type] || Toast._ICONS.info;
    el.appendChild(icon);

    // Content
    const content = document.createElement('div');
    content.className = 'toast-content';
    if (title) {
      const titleEl = document.createElement('div');
      titleEl.className = 'toast-title';
      titleEl.textContent = title;
      content.appendChild(titleEl);
    }
    if (message) {
      const msgEl = document.createElement('div');
      msgEl.className = 'toast-message';
      msgEl.textContent = message;
      content.appendChild(msgEl);
    }
    el.appendChild(content);

    // Close button
    if (closable) {
      const closeBtn = document.createElement('button');
      closeBtn.className = 'toast-close';
      closeBtn.innerHTML = '&times;';
      closeBtn.setAttribute('aria-label', 'Dismiss');
      closeBtn.addEventListener('click', () => this.dismiss());
      el.appendChild(closeBtn);
    }

    // Progress bar (auto-dismiss)
    if (duration > 0) {
      const progress = document.createElement('div');
      progress.className = 'toast-progress';
      progress.style.width = '100%';
      progress.style.transition = `width ${duration}ms linear`;
      el.style.position = 'relative';
      el.style.overflow = 'hidden';
      el.appendChild(progress);

      // Start progress animation after mount
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          progress.style.width = '0%';
        });
      });
    }

    this._el = el;
  }

  _show() {
    Toast._container.appendChild(this._el);

    // Trigger enter animation
    requestAnimationFrame(() => {
      this._el.classList.add('toast-visible');
    });

    // Auto-dismiss
    if (this._options.duration > 0) {
      this._timer = setTimeout(() => this.dismiss(), this._options.duration);
    }
  }
}

// Attach to global scope
if (typeof window !== 'undefined') window.Toast = Toast;
if (typeof module !== 'undefined' && module.exports) module.exports = Toast;
