import { type Component, For, Show, onMount } from 'solid-js';
import { agent } from '../../signals/agent';
import { ensureRecentBrainSignalsLoaded } from '../../runtime/brainRuntime';
import type { BrainDecision, MarketMoment } from '../../types/agent';
import { EmptyState } from '../system/EmptyState';

const tierColor = (tier: string) => {
  switch (tier) {
    case 'TEXTBOOK': return 'text-positive';
    case 'HIGH': return 'text-positive';
    case 'VALID': return 'text-warning';
    default: return 'text-text-muted';
  }
};

const actionColor = (action: string) => {
  switch (action) {
    case 'TRADE': return 'bg-positive/15 text-positive';
    case 'EXIT': return 'bg-negative/15 text-negative';
    case 'ADJUST': return 'bg-warning/15 text-warning';
    default: return 'bg-surface-3 text-text-muted';
  }
};

const formatTime = (ts: string) => {
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
      timeZone: 'America/New_York',
    });
  } catch { return ''; }
};

const DecisionCard: Component<{ decision: BrainDecision }> = (props) => {
  const d = () => props.decision;

  return (
    <div class={`px-5 py-4 border-b border-border-subtle ${
      d().action === 'TRADE' ? 'bg-positive/5' : ''
    }`}>
      {/* Header */}
      <div class="flex items-center justify-between mb-1.5">
        <div class="flex items-center gap-2">
          <span class={`text-[11px] font-semibold px-2.5 py-1 rounded-full font-data ${actionColor(d().action)}`}>
            {d().action}
          </span>
          <Show when={d().direction}>
            <span class={`text-[11px] font-data ${
              d().direction === 'BUY_CALL' ? 'text-positive' : 'text-negative'
            }`}>
              {d().direction === 'BUY_CALL' ? 'CALL' : 'PUT'}
            </span>
          </Show>
          <Show when={d().confidence > 0}>
            <span class={`text-[11px] font-data ${tierColor(d().tier)}`}>
              {(d().confidence * 100).toFixed(0)}% {d().tier}
            </span>
          </Show>
        </div>
        <div class="flex items-center gap-2 text-[11px] font-data text-text-muted">
          <Show when={d().cycle}>
            <span>#{d().cycle}</span>
          </Show>
          <Show when={d().timestamp}>
            <span>{formatTime(d().timestamp!)}</span>
          </Show>
          <Show when={d().latency_ms}>
            <span>{((d().latency_ms || 0) / 1000).toFixed(1)}s</span>
          </Show>
        </div>
      </div>

      {/* Reasoning */}
      <Show when={d().reasoning}>
        <div class="text-[13px] text-text-primary leading-[1.6] mb-2"
             style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
          {d().reasoning}
        </div>
      </Show>

      {/* Key factors */}
      <Show when={d().key_factors && d().key_factors.length > 0}>
        <div class="flex flex-wrap gap-1.5">
          <For each={d().key_factors}>
            {(factor) => (
              <span class="text-[11px] font-data px-2 py-0.5 rounded-full bg-surface-3 text-text-secondary">
                {factor}
              </span>
            )}
          </For>
        </div>
      </Show>
    </div>
  );
};

const MomentCard: Component<{ moment: MarketMoment }> = (props) => {
  const m = () => props.moment;

  return (
    <div class="flex items-center gap-3 px-5 py-3 text-[11px] font-data border-b border-border-subtle min-h-[52px]">
      <span class={`w-1.5 h-1.5 rounded-full ${
        m().outcome_direction === 'up' ? 'bg-positive' :
        m().outcome_direction === 'down' ? 'bg-negative' :
        'bg-text-muted'
      }`} />
      <span class="text-text-secondary w-12">{formatTime(m().timestamp)}</span>
      <span class="text-text-primary flex-1 truncate">
        {m().trigger_name || m().trigger_type}
      </span>
      <Show when={m().similarity}>
        <span class="text-text-muted">{((m().similarity || 0) * 100).toFixed(0)}%</span>
      </Show>
      <Show when={m().move_pct_15min != null}>
        <span class={m().move_pct_15min! >= 0 ? 'text-positive' : 'text-negative'}>
          {m().move_pct_15min! >= 0 ? '+' : ''}{m().move_pct_15min!.toFixed(2)}%
        </span>
      </Show>
    </div>
  );
};

export const BrainFeed: Component = () => {
  onMount(async () => {
    await ensureRecentBrainSignalsLoaded();
  });

  return (
    <div class="h-full flex flex-col">
      {/* Cycle status bar */}
      <Show when={agent.lastCycle}>
        <div class="px-5 py-3 border-b-[1.5px] border-border-default bg-surface-1 flex items-center justify-between gap-4">
          <div class="flex items-center gap-3">
            <span class={`w-2 h-2 rounded-full ${
              agent.lastCycle!.action !== 'NO_TRADE' ? 'bg-positive animate-pulse' : 'bg-text-muted'
            }`} />
            <span class="text-[12px] text-text-secondary truncate" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
              {agent.lastCycle!.action !== 'NO_TRADE'
                ? `Setup: ${agent.lastCycle!.reasoning.substring(0, 80)}`
                : (agent.lastCycle as any)?.levels || agent.lastCycle!.reasoning.substring(0, 60) || 'Scanning...'
              }
            </span>
          </div>
          <div class="flex items-center gap-3 font-data text-[11px] text-text-muted shrink-0">
            <Show when={(agent.lastCycle as any)?.options_vpin != null}>
              <span class={(agent.lastCycle as any)?.options_vpin_level === 'toxic' ? 'text-negative' : (agent.lastCycle as any)?.options_vpin_level === 'elevated' ? 'text-warning' : ''}>
                VPIN {(((agent.lastCycle as any)?.options_vpin || 0) * 100).toFixed(0)}%
              </span>
            </Show>
            <Show when={(agent.lastCycle as any)?.high_sms > 0}>
              <span>SMS70+ {(agent.lastCycle as any)?.high_sms}</span>
            </Show>
            <span>{agent.lastCycle!.trade_count} ticks</span>
            <span>{new Date(agent.lastCycle!.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}</span>
          </div>
        </div>
      </Show>

      {/* Decision feed */}
      <div class="flex-1 overflow-y-auto min-h-0">
        <Show when={agent.decisions.length === 0 && !agent.lastCycle}>
          <EmptyState
            eyebrow="Market Brain"
            title="Waiting for reasoning cycles"
            description="The brain analyzes the market continuously. Setups, decisions, and recalled patterns will appear here as the session develops."
          />
        </Show>

        <For each={agent.decisions}>
          {(decision) => <DecisionCard decision={decision} />}
        </For>
      </div>

      {/* Pattern recall panel — bottom */}
      <Show when={agent.patternRecall && agent.patternRecall.similar_moments.length > 0}>
        <div class="border-t border-border-default bg-surface-1 max-h-[200px] overflow-y-auto">
          <div class="px-5 py-3 flex items-center justify-between border-b border-border-subtle">
            <span class="text-[11px] font-display text-accent font-semibold tracking-[0.12em] uppercase">
              SIMILAR PATTERNS
            </span>
            <Show when={agent.patternRecall?.moments_stats}>
              <span class="text-[11px] font-data text-text-muted">
                {agent.patternRecall!.moments_stats.total_moments} in memory
              </span>
            </Show>
          </div>
          <For each={agent.patternRecall!.similar_moments}>
            {(moment) => <MomentCard moment={moment} />}
          </For>
        </div>
      </Show>
    </div>
  );
};
