/**
 * Centralized formatting utilities for the entire platform.
 * Import from here — never redefine formatters locally.
 */

/** $123.45 — null-safe */
export function fmtPrice(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return '—';
  return `$${n.toFixed(2)}`;
}

/** $1.2M / $500K / $123 — compact premium display */
export function fmtPremium(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return '—';
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

/** 12.3% — null-safe */
export function fmtPct(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return '—';
  return `${n.toFixed(1)}%`;
}

/** +0.450 / -0.320 — signed delta */
export function fmtDelta(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return '—';
  return n >= 0 ? `+${n.toFixed(3)}` : n.toFixed(3);
}

/** 2.1B / 45.3M / 1234 — GEX-scale numbers */
export function fmtGex(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return '—';
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  return n.toFixed(0);
}

/** Locale-aware number: 1,234,567 */
export function fmtNum(n: number | null | undefined, decimals = 0): string {
  if (n == null || !isFinite(n)) return '—';
  return n.toLocaleString('en-US', { maximumFractionDigits: decimals });
}

/** +1.23 / -0.45 — signed price change */
export function fmtChange(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`;
}

/** +1.23% / -0.45% — signed percentage change */
export function fmtChangePct(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}

/** 14:32:05 — 24h trade timestamp from epoch ms */
export function fmtTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

/** 14:32 — short time from ISO string */
export function fmtTimeShort(isoOrTs: string | number): string {
  const d = typeof isoOrTs === 'string' ? new Date(isoOrTs) : new Date(isoOrTs);
  return d.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}
