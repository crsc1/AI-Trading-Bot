import { type Component, For, Show, createSignal, onMount, onCleanup } from 'solid-js';
import { api } from '../../lib/api';

interface FlowAlert {
  id: string;
  timestamp: string;
  symbol: string;
  alert_type: string;
  direction: string;
  strike: number;
  right: string;
  size: number;
  premium: number;
  avg_price: number;
  fills: number;
  side: string;
  score: number;
  repeat_count: number;
  detail: string;
}

const typeColors: Record<string, string> = {
  sweep: 'bg-purple/15 text-purple',
  whale: 'bg-warning/15 text-warning',
  block: 'bg-accent/15 text-accent',
  repeat: 'bg-positive/15 text-positive',
};

const typeLabels: Record<string, string> = {
  sweep: 'SWEEP',
  whale: 'WHALE',
  block: 'BLOCK',
  repeat: 'REPEAT',
};

const dirColors: Record<string, string> = {
  bullish: 'text-positive',
  bearish: 'text-negative',
  exit_bullish: 'text-text-secondary',
  exit_bearish: 'text-text-secondary',
  neutral: 'text-text-muted',
};

const formatTime = (ts: string) => {
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: false, timeZone: 'America/New_York',
    });
  } catch { return ''; }
};

const formatPremium = (p: number) => {
  if (p >= 1_000_000) return `$${(p / 1_000_000).toFixed(1)}M`;
  if (p >= 1_000) return `$${(p / 1_000).toFixed(0)}K`;
  return `$${p.toFixed(0)}`;
};

export const Scanner: Component = () => {
  const [alerts, setAlerts] = createSignal<FlowAlert[]>([]);
  const [stats, setStats] = createSignal<any>(null);
  let pollInterval: ReturnType<typeof setInterval>;

  async function loadAlerts() {
    try {
      const data = await api.get<{ alerts: FlowAlert[] }>('/api/brain/scanner/alerts?limit=100');
      if (data?.alerts) setAlerts(data.alerts);
    } catch {}
  }

  async function loadStats() {
    try {
      const data = await api.get<any>('/api/brain/scanner/stats');
      if (data) setStats(data);
    } catch {}
  }

  onMount(() => {
    loadAlerts();
    loadStats();
    pollInterval = setInterval(() => { loadAlerts(); loadStats(); }, 5000);
  });

  onCleanup(() => clearInterval(pollInterval));

  return (
    <div class="h-full flex flex-col">
      {/* Header */}
      <div class="h-10 flex items-center justify-between px-4 bg-surface-1 border-b border-border-default shrink-0">
        <div class="flex items-center gap-3">
          <span class="font-display text-[13px] font-medium">Options Flow Scanner</span>
          <Show when={stats()}>
            <span class="font-data text-[11px] text-text-secondary">
              {stats()?.subscribed_symbols?.length || 0} symbols
            </span>
            <span class="font-data text-[11px] text-text-secondary">
              {stats()?.total_alerts || 0} alerts
            </span>
          </Show>
        </div>
        <div class="flex items-center gap-2">
          <Show when={stats()?.subscribed_symbols}>
            <div class="flex items-center gap-1.5">
              <For each={stats()?.subscribed_symbols || []}>
                {(sym: string) => (
                  <span class="font-data text-[10px] px-1.5 py-0.5 rounded bg-surface-3 text-text-secondary">
                    {sym}
                  </span>
                )}
              </For>
            </div>
          </Show>
        </div>
      </div>

      {/* Alert feed */}
      <div class="flex-1 overflow-y-auto min-h-0">
        <Show when={alerts().length === 0}>
          <div class="flex items-center justify-center h-full">
            <div class="text-center px-6">
              <div class="text-[18px] text-text-secondary mb-2"
                   style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-weight: 500;">
                Flow Scanner
              </div>
              <div class="text-[13px] text-text-muted leading-relaxed"
                   style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                Scanning for sweeps, whale trades, and unusual activity
                <br />across {stats()?.subscribed_symbols?.length || '...'} symbols.
                <br />Alerts appear here in real-time.
              </div>
            </div>
          </div>
        </Show>

        <table class="w-full table-fixed">
          <Show when={alerts().length > 0}>
            <colgroup>
              <col style="width: 5%" />   {/* SCORE */}
              <col style="width: 7%" />   {/* TIME */}
              <col style="width: 7%" />   {/* TYPE */}
              <col style="width: 7%" />   {/* DIR */}
              <col style="width: 6%" />   {/* SYMBOL */}
              <col style="width: 12%" />  {/* CONTRACT */}
              <col style="width: 7%" />   {/* SIZE */}
              <col style="width: 8%" />   {/* PREMIUM */}
              <col style="width: 6%" />   {/* FILLS */}
              <col style="width: 35%" />  {/* DETAIL */}
            </colgroup>
            <thead class="sticky top-0 bg-surface-1 z-10">
              <tr class="text-[11px] font-display text-text-secondary tracking-wider border-b border-border-default">
                <th class="text-center px-3 py-2">SCORE</th>
                <th class="text-left px-3 py-2">TIME</th>
                <th class="text-left px-3 py-2">TYPE</th>
                <th class="text-left px-3 py-2">DIR</th>
                <th class="text-left px-3 py-2">SYMBOL</th>
                <th class="text-left px-3 py-2">CONTRACT</th>
                <th class="text-right px-3 py-2">SIZE</th>
                <th class="text-right px-3 py-2">PREMIUM</th>
                <th class="text-right px-3 py-2">FILLS</th>
                <th class="text-left px-4 py-2">DETAIL</th>
              </tr>
            </thead>
          </Show>
          <tbody>
            <For each={alerts()}>
              {(alert) => (
                <tr class={`border-b border-border-subtle hover:bg-surface-2/30 transition-colors ${
                  alert.score >= 70 ? 'bg-positive/5' :
                  alert.score >= 50 ? 'bg-warning/5' :
                  alert.alert_type === 'sweep' ? 'bg-purple/5' : ''
                }`}>
                  <td class="px-3 py-2.5 text-center">
                    <span class={`font-data text-[12px] font-bold ${
                      alert.score >= 70 ? 'text-positive' :
                      alert.score >= 50 ? 'text-warning' :
                      alert.score >= 30 ? 'text-accent' : 'text-text-muted'
                    }`}>
                      {alert.score}
                    </span>
                  </td>
                  <td class="px-3 py-2.5 font-data text-[12px] text-accent">
                    {formatTime(alert.timestamp)}
                  </td>
                  <td class="px-3 py-2.5">
                    <span class={`font-data text-[10px] px-2 py-0.5 rounded font-medium ${
                      typeColors[alert.alert_type] || 'bg-surface-3 text-text-muted'
                    }`}>
                      {typeLabels[alert.alert_type] || alert.alert_type}
                    </span>
                  </td>
                  <td class="px-3 py-2.5">
                    <span class={`font-data text-[11px] font-medium ${
                      dirColors[alert.direction] || 'text-text-muted'
                    }`}>
                      {alert.direction === 'bullish' ? '▲ BULL' :
                       alert.direction === 'bearish' ? '▼ BEAR' :
                       alert.direction === 'exit_bullish' ? '↗ EXIT' :
                       alert.direction === 'exit_bearish' ? '↙ EXIT' : '—'}
                    </span>
                  </td>
                  <td class="px-3 py-2.5 font-data text-[13px] text-text-primary font-medium">
                    {alert.symbol}
                  </td>
                  <td class="px-3 py-2.5 font-data text-[12px] text-text-secondary">
                    ${alert.strike}{alert.right} @ ${alert.avg_price?.toFixed(2) || '?'}
                  </td>
                  <td class="px-3 py-2.5 font-data text-[12px] text-text-primary text-right font-medium">
                    {alert.size.toLocaleString()}x
                  </td>
                  <td class="px-3 py-2.5 font-data text-[13px] text-text-primary text-right font-medium">
                    {formatPremium(alert.premium)}
                  </td>
                  <td class="px-3 py-2.5 font-data text-[11px] text-text-secondary text-right">
                    {alert.fills}{alert.repeat_count >= 3 ? ` (${alert.repeat_count}x)` : ''}
                  </td>
                  <td class="px-4 py-2.5 text-[12px] text-text-secondary truncate"
                      style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                    {alert.detail}
                  </td>
                </tr>
              )}
            </For>
          </tbody>
        </table>
      </div>
    </div>
  );
};
