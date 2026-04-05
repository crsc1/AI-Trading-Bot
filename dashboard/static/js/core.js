// ══════════════════════════════════════════════════════════════════════════
// UTILS
// ══════════════════════════════════════════════════════════════════════════
function esc(s){ const d=document.createElement('div'); d.textContent=String(s||''); return d.innerHTML; }

// ══════════════════════════════════════════════════════════════════════════
// UI GLOBAL COMPONENT SYSTEM
// ══════════════════════════════════════════════════════════════════════════
const UI = {
  // --- Badge ---
  badge(text, variant = 'neutral'){
    // variant: green, red, yellow, blue, neutral, accent
    return `<span class="ui-badge ${variant}">${esc(text)}</span>`;
  },

  // --- Toast ---
  _toastId: 0,
  toast(message, type = 'info', duration = 3500){
    // type: info, success, warning, error
    const container = document.getElementById('uiToastContainer');
    if(!container) return;
    const id = 'toast-' + (++UI._toastId);
    const el = document.createElement('div');
    el.className = `ui-toast ${type}`;
    el.id = id;
    el.innerHTML = `<span>${esc(message)}</span>`;
    container.appendChild(el);
    setTimeout(() => {
      el.classList.add('out');
      setTimeout(() => el.remove(), 220);
    }, duration);
    return id;
  },

  // --- Loading ---
  loading(text = 'Loading...'){
    return `<div class="loading"><div class="loading-dots"><span></span><span></span><span></span></div> ${esc(text)}</div>`;
  },

  // --- Empty state ---
  // variant: 'empty' (default), 'loading', 'error'
  empty(text = 'No data', variant = 'empty'){
    const icons = {
      loading: '<div class="loading-dots" style="display:inline-flex;gap:3px;margin-right:6px;vertical-align:middle"><span></span><span></span><span></span></div>',
      empty: '<span style="color:var(--mut);margin-right:4px">&#8212;</span>',
      error: '<span style="color:var(--red);margin-right:4px">&#9888;</span>',
    };
    const icon = icons[variant] || icons.empty;
    const suffix = variant === 'loading' ? ' Loading...' : variant === 'error' ? ' <span style="color:var(--acc);cursor:pointer;text-decoration:underline" onclick="location.reload()">Retry</span>' : '';
    return `<div class="empty-msg empty-${esc(variant)}">${icon}${esc(text)}${suffix}</div>`;
  },

  // --- Tooltip (global singleton) ---
  tooltip: {
    _el: null,
    show(targetEl, html){
      const tip = document.getElementById('uiTooltip');
      if(!tip) return;
      tip.innerHTML = html;
      tip.style.display = 'block';
      const rect = targetEl.getBoundingClientRect();
      tip.style.left = rect.left + rect.width/2 - tip.offsetWidth/2 + 'px';
      tip.style.top = rect.top - tip.offsetHeight - 6 + 'px';
      // Clamp to viewport
      const tr = tip.getBoundingClientRect();
      if(tr.left < 4) tip.style.left = '4px';
      if(tr.right > window.innerWidth - 4) tip.style.left = (window.innerWidth - tr.width - 4) + 'px';
      if(tr.top < 4){ tip.style.top = rect.bottom + 6 + 'px'; }
    },
    hide(){
      const tip = document.getElementById('uiTooltip');
      if(tip) tip.style.display = 'none';
    }
  },

  // --- Confirm dialog ---
  confirm(title, message, options = {}){
    return new Promise(resolve => {
      const overlay = document.createElement('div');
      overlay.className = 'ui-confirm-overlay';
      const btnClass = options.danger ? 'btn danger' : 'btn primary';
      const confirmLabel = options.confirmLabel || (options.danger ? 'Delete' : 'Confirm');
      const cancelLabel = options.cancelLabel || 'Cancel';
      overlay.innerHTML = `<div class="ui-confirm-box">
        <div class="title">${esc(title)}</div>
        <div class="msg">${esc(message)}</div>
        <div class="actions">
          <button class="btn" data-action="cancel">${esc(cancelLabel)}</button>
          <button class="${btnClass}" data-action="confirm">${esc(confirmLabel)}</button>
        </div>
      </div>`;
      overlay.addEventListener('click', e => {
        const action = e.target.dataset?.action;
        if(action === 'confirm'){ overlay.remove(); resolve(true); }
        else if(action === 'cancel' || e.target === overlay){ overlay.remove(); resolve(false); }
      });
      document.body.appendChild(overlay);
      // Focus confirm button
      overlay.querySelector('[data-action="confirm"]')?.focus();
    });
  },

  // --- Status dot ---
  dot(state = 'off'){
    // state: on, off, dim
    return `<span class="dot ${state}"></span>`;
  },
};
