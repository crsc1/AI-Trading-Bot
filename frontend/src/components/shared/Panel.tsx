/**
 * Panel — Reusable panel frame for dashboard tiles.
 *
 * Provides: consistent header, loading/error states, fullscreen toggle.
 * Every tile on the Reference page (and eventually other pages) uses this.
 */
import { type Component, type JSX, Show, createSignal, onCleanup } from 'solid-js';

interface PanelProps {
  title: string;
  subtitle?: string;
  badge?: string;
  badgeColor?: string;
  loading?: boolean;
  error?: string;
  children: JSX.Element;
}

export const Panel: Component<PanelProps> = (props) => {
  const [fullscreen, setFullscreen] = createSignal(false);

  const toggle = () => setFullscreen(!fullscreen());

  // Escape key exits fullscreen
  const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && fullscreen()) setFullscreen(false); };
  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', onKey);
    onCleanup(() => window.removeEventListener('keydown', onKey));
  }

  return (
    <div
      class={`flex flex-col ${
        fullscreen()
          ? 'fixed inset-0 z-50 bg-surface-1'
          : 'h-full'
      }`}
    >
      {/* Header */}
      <div class="h-10 px-4 flex items-center justify-between border-b border-border-default shrink-0">
        <div class="flex items-center gap-2">
          <span class="font-display text-[11px] font-medium text-text-secondary tracking-wider uppercase">
            {props.title}
          </span>
          <Show when={props.subtitle}>
            <span class="font-display text-[9px] text-text-muted">{props.subtitle}</span>
          </Show>
        </div>
        <div class="flex items-center gap-2">
          <Show when={props.badge}>
            <span class={`text-[8px] px-1.5 py-0.5 rounded-full font-display ${
              props.badgeColor === 'positive' ? 'bg-positive/15 text-positive' :
              props.badgeColor === 'warning' ? 'bg-warning/15 text-warning' :
              'bg-accent/15 text-accent'
            }`}>
              {props.badge}
            </span>
          </Show>
          <button
            onClick={toggle}
            class="text-text-muted hover:text-text-secondary text-[12px] w-6 h-6 flex items-center justify-center rounded hover:bg-surface-3 transition-colors cursor-pointer"
            title={fullscreen() ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {fullscreen() ? '✕' : '⛶'}
          </button>
        </div>
      </div>

      {/* Content */}
      <div class="flex-1 overflow-y-auto min-h-0">
        <Show when={props.error}>
          <div class="flex items-center justify-center h-full p-4">
            <span class="text-negative text-[10px] font-data">{props.error}</span>
          </div>
        </Show>
        <Show when={props.loading && !props.error}>
          <div class="flex items-center justify-center h-full">
            <span class="text-text-secondary text-[10px] font-display">Loading...</span>
          </div>
        </Show>
        <Show when={!props.loading && !props.error}>
          {props.children}
        </Show>
      </div>
    </div>
  );
};

/** Consistent key-value data row */
interface DataRowProps {
  label: string;
  value: string | number;
  color?: string;
  large?: boolean;
}

export const DataRow: Component<DataRowProps> = (props) => (
  <div class="flex items-center justify-between py-1">
    <span class="font-display text-[9px] text-text-secondary uppercase tracking-wider">{props.label}</span>
    <span class={`font-data ${props.large ? 'text-[14px] font-medium' : 'text-[12px]'} ${props.color || 'text-text-primary'}`}>
      {props.value}
    </span>
  </div>
);

/** Formatting helpers */
export function fmtPct(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return '—';
  return `${n >= 0 ? '' : ''}${n.toFixed(1)}%`;
}

export function fmtPrice(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return '—';
  return `$${n.toFixed(2)}`;
}

export function fmtPremium(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return '—';
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

export function fmtDelta(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return '—';
  return n >= 0 ? `+${n.toFixed(3)}` : n.toFixed(3);
}

export function fmtGex(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return '—';
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  return n.toFixed(0);
}

export function fmtNum(n: number | null | undefined, decimals = 0): string {
  if (n == null || !isFinite(n)) return '—';
  return n.toLocaleString('en-US', { maximumFractionDigits: decimals });
}
