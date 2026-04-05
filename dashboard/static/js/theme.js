// ══════════════════════════════════════════════════════════════════════════
// THEME — read CSS tokens once so JS chart configs stay in sync with tokens.css
// ══════════════════════════════════════════════════════════════════════════
const T = (() => {
  const g = k => getComputedStyle(document.documentElement).getPropertyValue(k).trim();
  return {
    surface0: g('--surface-0'),   surface1: g('--surface-1'),
    surface2: g('--surface-2'),   surface3: g('--surface-3'),
    border:   g('--border'),      borderSubtle: g('--border-subtle'),
    txt:      g('--text-primary'),dim: g('--text-secondary'), mut: g('--text-muted'),
    accent:   g('--accent'),      accentHover: g('--accent-hover'),
    positive: g('--positive'),    negative: g('--negative'),
    warning:  g('--warning'),     info: g('--info'),
    purple:   g('--purple'),
    // Chart indicator colors
    rsi:  g('--chart-rsi'),   sma:  g('--chart-sma'),
    ema:  g('--chart-ema'),   vwap: g('--chart-vwap'),
    cvd:  g('--chart-cvd'),
    // Font sizes (strip 'px' for Lightweight Charts which wants numbers)
    fontSm: parseInt(g('--font-sm')) || 9,
    fontXs: parseInt(g('--font-xs')) || 8,
    fontBase: parseInt(g('--font-base')) || 10,
  };
})();
