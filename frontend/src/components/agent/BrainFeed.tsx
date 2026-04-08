import { type Component, For, Show, onMount } from 'solid-js';
import { agent, addDecision } from '../../signals/agent';
import { api } from '../../lib/api';
import type { BrainDecision, MarketMoment } from '../../types/agent';

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
    <div class={`px-4 py-3 border-b border-border-subtle ${
      d().action === 'TRADE' ? 'bg-positive/5' : ''
    }`}>
      {/* Header */}
      <div class="flex items-center justify-between mb-1.5">
        <div class="flex items-center gap-2">
          <span class={`text-[11px] font-medium px-2 py-0.5 rounded font-data ${actionColor(d().action)}`}>
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
        <div class="text-[13px] text-text-primary leading-[1.5] mb-1.5"
             style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
          {d().reasoning}
        </div>
      </Show>

      {/* Key factors */}
      <Show when={d().key_factors && d().key_factors.length > 0}>
        <div class="flex flex-wrap gap-1.5">
          <For each={d().key_factors}>
            {(factor) => (
              <span class="text-[11px] font-data px-1.5 py-0.5 rounded bg-surface-3 text-text-secondary">
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
    <div class="flex items-center gap-3 px-4 py-2 text-[11px] font-data border-b border-border-subtle">
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
  // Load recent signals on mount if feed is empty
  onMount(async () => {
    if (agent.decisions.length > 0) return;
    try {
      const data = await api.get<{ signals: any[] }>('/api/brain/signals/recent');
      if (data?.signals) {
        for (const s of data.signals) {
          addDecision({
            id: s.id,
            timestamp: s.timestamp,
            action: s.action === 'NO_TRADE' ? 'HOLD' : 'TRADE',
            direction: s.action,
            confidence: s.confidence,
            tier: s.tier,
            reasoning: `[Signal Engine] ${s.reasoning}`,
            key_factors: s.setup_name ? [s.setup_name] : [],
            model: 'non-LLM',
          });
        }
      }
    } catch {}
  });

  return (
    <div class="h-full flex flex-col">
      {/* Cycle status bar */}
      <Show when={agent.lastCycle}>
        <div class="px-4 py-2 border-b border-border-default bg-surface-1 flex items-center justify-between">
          <div class="flex items-center gap-3">
            <span class={`w-2 h-2 rounded-full ${
              agent.lastCycle!.action !== 'NO_TRADE' ? 'bg-positive animate-pulse' : 'bg-text-muted'
            }`} />
            <span class="text-[12px] text-text-secondary" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
              {agent.lastCycle!.action !== 'NO_TRADE'
                ? `Setup: ${agent.lastCycle!.reasoning.substring(0, 80)}`
                : agent.lastCycle!.reasoning.substring(0, 80) || 'Scanning...'
              }
            </span>
          </div>
          <div class="flex items-center gap-3 font-data text-[11px] text-text-muted">
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
          <div class="flex items-center justify-center h-full">
            <div class="text-center px-6">
              <div class="text-[18px] text-text-secondary mb-2"
                   style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-weight: 500;">
                Market Brain
              </div>
              <div class="text-[13px] text-text-muted leading-relaxed"
                   style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                Analyzing every 15 seconds during market hours.
                <br />Setups and signals will appear here.
              </div>
            </div>
          </div>
        </Show>

        <For each={agent.decisions}>
          {(decision) => <DecisionCard decision={decision} />}
        </For>
      </div>

      {/* Pattern recall panel — bottom */}
      <Show when={agent.patternRecall && agent.patternRecall.similar_moments.length > 0}>
        <div class="border-t border-border-default bg-surface-1 max-h-[200px] overflow-y-auto">
          <div class="px-4 py-2 flex items-center justify-between">
            <span class="text-[11px] font-display text-purple font-medium tracking-[0.8px]">
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
