// ══════════════════════════════════════════════════════════════════════════
// LEFT NAV + CONTEXT-SENSITIVE SIDEBAR
// ══════════════════════════════════════════════════════════════════════════
let _activeNav = 'combined';

// Map nav items to: which tab-panel to show + which sidebar panel to auto-select
const NAV_CONFIG = {
  combined:  { tab: 'combined',  sidebar: 'signals',   showSidebar: true  },
  flow:      { tab: 'flow',      sidebar: 'flowdetail', showSidebar: true  },
  candles:   { tab: 'candles',   sidebar: 'market',     showSidebar: true  },
  options:   { tab: 'options',   sidebar: 'market',     showSidebar: true  },
  agent:     { tab: 'agent',     sidebar: null,         showSidebar: false },
  // Sidebar-only nav items (no tab change, just switch sidebar panel)
  signals:   { tab: 'combined',  sidebar: 'signals',    showSidebar: true  },
  journal:   { tab: 'combined',  sidebar: 'journal',    showSidebar: true  },
  settings:  { tab: null,        sidebar: 'settings',   showSidebar: true  },
};

function navTo(nav){
  const cfg = NAV_CONFIG[nav];
  if(!cfg) return;

  _activeNav = nav;

  // Update left nav active state
  document.querySelectorAll('.ln-btn').forEach(b => b.classList.toggle('active', b.dataset.nav === nav));

  // Switch tab panel if this nav item has one
  if(cfg.tab){
    setTab(cfg.tab);
  }

  // Update widget context based on active tab
  if(cfg.sidebar) setSidebarPanel(cfg.sidebar); // compat
  updateWidgetContext(nav);

  // Show/hide sidebar
  const sidebar = document.getElementById('sidebarEl');
  if(sidebar){
    if(cfg.showSidebar === false){
      sidebar.style.display = 'none';
      document.querySelector('.main').style.gridTemplateColumns = '1fr';
    } else {
      sidebar.style.display = '';
      document.querySelector('.main').style.gridTemplateColumns = '1fr var(--sidebar-w, 260px)';
    }
    // Resize charts after layout change — use the unified resize system
    requestAnimationFrame(_resizeAllVisibleCharts);
  }

  // Update session label
  _updateSessionLabel();

  // Tab-specific init hooks
  if(nav === 'agent') startAgentTab();
}

function _updateSessionLabel(){
  const el = document.getElementById('sessionLabel');
  if(!el) return;
  const session = getMarketSession();
  const labels = { regular: 'MARKET OPEN', 'pre-market': 'PRE-MARKET', 'after-hours': 'AFTER HOURS', closed: 'CLOSED' };
  const colors = { regular: 'var(--grn)', 'pre-market': 'var(--ylw)', 'after-hours': 'var(--ylw)', closed: 'var(--red)' };
  el.textContent = labels[session] || 'CLOSED';
  el.style.color = colors[session] || 'var(--red)';
}

// ── Market countdown timer (ticks every second) ───────────────────────────
function _getNextMarketEvent(){
  // Returns { label, targetET (Date in ET), color } for the next transition
  const now = new Date();
  const et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const day = et.getDay(); // 0=Sun, 6=Sat
  const h = et.getHours(), m = et.getMinutes(), s = et.getSeconds();
  const totalSec = h * 3600 + m * 60 + s;

  // Helper: build a Date for today at HH:MM:SS ET (in local time)
  function etToday(hh, mm, ss = 0){
    const d = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
    d.setHours(hh, mm, ss, 0);
    // Convert back to UTC by adding the ET offset
    const etOffset = d.getTime() - new Date(d.toLocaleString('en-US', { timeZone: 'America/New_York' })).getTime();
    // Actually: use the diff between local and ET representation
    const localStr = d.toLocaleString('en-US', { timeZone: 'America/New_York' });
    const etDate = new Date(localStr);
    const delta = d.getTime() - etDate.getTime();
    return new Date(d.getTime() + delta);
  }

  // Simpler approach — compute seconds until each boundary, pick the right one
  const OPEN  = 9 * 3600 + 30 * 60;   // 09:30
  const CLOSE = 16 * 3600;             // 16:00
  const AH_END = 20 * 3600;            // 20:00

  // Weekend: find next Monday open
  function secsUntilNextOpen(){
    // Days until Monday
    const daysUntilMon = day === 0 ? 1 : day === 6 ? 2 : 0;
    if(daysUntilMon > 0){
      return daysUntilMon * 86400 - totalSec + OPEN;
    }
    // Weekday but after close
    return 86400 - totalSec + OPEN; // next day 9:30
  }

  if(day === 0 || day === 6){
    // Weekend
    const daysUntil = day === 0 ? 1 : 2;
    const secs = daysUntil * 86400 - totalSec + OPEN;
    return { label: 'Opens', secs, color: 'var(--grn)' };
  }

  if(totalSec < OPEN){
    // Pre-market: countdown to open
    return { label: 'Opens', secs: OPEN - totalSec, color: 'var(--grn)' };
  }
  if(totalSec < CLOSE){
    // Market open: countdown to close
    return { label: 'Closes', secs: CLOSE - totalSec, color: 'var(--red)' };
  }
  if(totalSec < AH_END){
    // After-hours: countdown to after-hours end
    return { label: 'AH ends', secs: AH_END - totalSec, color: 'var(--mut)' };
  }
  // 20:00+ — countdown to next open
  const secs = 86400 - totalSec + OPEN;
  return { label: 'Opens', secs, color: 'var(--grn)' };
}

function _tickMarketCountdown(){
  const el = document.getElementById('marketCountdown');
  if(!el) return;

  const { label, secs, color } = _getNextMarketEvent();

  // Format as HH:MM:SS
  const totalSec = Math.max(0, Math.round(secs));
  const hh = Math.floor(totalSec / 3600);
  const mm = Math.floor((totalSec % 3600) / 60);
  const ss = totalSec % 60;
  const pad = n => String(n).padStart(2, '0');
  const formatted = `${pad(hh)}:${pad(mm)}:${pad(ss)}`;

  el.textContent = `${label} in ${formatted}`;
  el.style.color = color;
}

function _startMarketCountdown(){
  _tickMarketCountdown(); // immediate render
  setInterval(_tickMarketCountdown, 1000);
}
