import { type Component, For, Show, onMount, onCleanup } from 'solid-js';
import { scanner } from '../../signals/scanner';
import { subscribeScannerRuntime, unsubscribeScannerRuntime } from '../../runtime/scannerRuntime';
import { WidgetFrame } from '../system/WidgetFrame';
import { MetricTile } from '../system/MetricTile';
import { StatusPill } from '../system/StatusPill';
import { EmptyState } from '../system/EmptyState';
import { TableShell, type TableColumn } from '../system/TableShell';

const typeColors: Record<string, string> = {
  sweep: 'bg-accent/10 text-accent',
  whale: 'bg-warning/10 text-warning',
  block: 'bg-surface-3 text-text-primary',
  repeat: 'bg-positive/10 text-positive',
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

const scannerColumns: TableColumn[] = [
  { label: 'Score', width: '6%', align: 'center' },
  { label: 'Time', width: '8%' },
  { label: 'Type', width: '8%' },
  { label: 'Dir', width: '8%' },
  { label: 'Symbol', width: '7%' },
  { label: 'Contract', width: '13%' },
  { label: 'Size', width: '8%', align: 'right' },
  { label: 'Premium', width: '10%', align: 'right' },
  { label: 'Fills', width: '8%', align: 'right' },
  { label: 'Detail', width: '24%' },
];

export const Scanner: Component = () => {
  onMount(() => {
    subscribeScannerRuntime();
  });

  onCleanup(() => unsubscribeScannerRuntime());

  return (
    <div data-testid="scanner-page" class="h-full overflow-hidden bg-[linear-gradient(180deg,rgba(11,13,18,1),rgba(14,18,24,1))]">
      <div class="h-full min-h-0 p-4 flex flex-col gap-4">
        <WidgetFrame
          title="Scanner Workspace"
          subtitle="Realtime unusual-flow detection across the subscribed universe"
          badge={scanner.loading ? 'Loading' : 'Live'}
          badgeTone={scanner.loading ? 'warning' : 'positive'}
          actions={
            <div class="flex flex-wrap items-center justify-end gap-2">
              <StatusPill label="Universe" value={String(scanner.stats?.subscribed_symbols?.length || 0)} tone="accent" compact />
              <StatusPill label="Alerts" value={String(scanner.stats?.total_alerts || 0)} tone="warning" compact />
            </div>
          }
          contentClass="px-5 py-4"
        >
          <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <MetricTile label="Subscribed" value={String(scanner.stats?.subscribed_symbols?.length || 0)} />
            <MetricTile label="Alerts" value={String(scanner.alerts.length)} tone="text-warning" />
            <MetricTile label="Top Score" value={scanner.alerts[0] ? String(scanner.alerts[0].score) : '—'} tone="text-positive" />
            <MetricTile label="Latest Type" value={scanner.alerts[0] ? (typeLabels[scanner.alerts[0].alert_type] || scanner.alerts[0].alert_type) : '—'} />
            <MetricTile label="Universe" value={(scanner.stats?.subscribed_symbols || []).join(', ') || 'Loading…'} class="xl:col-span-2" />
          </div>
        </WidgetFrame>

        <div class="flex-1 min-h-0 rounded-2xl border-[1.5px] border-border-default bg-surface-1 shadow-[0_14px_32px_rgba(0,0,0,0.16)] overflow-hidden">
          <Show when={scanner.loading}>
            <EmptyState
              eyebrow="Scanner"
              title="Loading scanner"
              description="Fetching the current alert stream and subscribed symbol universe."
            />
          </Show>

          <Show when={!scanner.loading && scanner.alerts.length === 0}>
            <EmptyState
              eyebrow="Scanner"
              title="Flow scanner is live"
              description={`Scanning for sweeps, whales, blocks, and repeats across ${scanner.stats?.subscribed_symbols?.length || 'the active'} symbols. Alerts will appear here in realtime.`}
            />
          </Show>

          <Show when={!scanner.loading && scanner.alerts.length > 0}>
            <TableShell columns={scannerColumns} tableClass="text-[12px]">
              <For each={scanner.alerts}>
                {(alert) => (
                  <tr class={`border-b border-border-subtle hover:bg-surface-2/30 transition-colors ${
                    alert.score >= 70 ? 'bg-positive/5' :
                    alert.score >= 50 ? 'bg-warning/5' :
                    alert.alert_type === 'sweep' ? 'bg-accent/5' : ''
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
                      <span class={`font-data text-[10px] px-2.5 py-1 rounded-full border border-border-default font-semibold ${
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
            </TableShell>
          </Show>
        </div>
      </div>
    </div>
  );
};
