import { api } from '../lib/api';
import {
  agent,
  setDecisions,
  setLastRecentDecisionsUpdateAt,
  setRecentDecisionsLoading,
} from '../signals/agent';
import type { BrainDecision } from '../types/agent';

let recentSignalsInflight: Promise<void> | null = null;

function toDecision(signal: any): BrainDecision {
  return {
    id: signal.id,
    timestamp: signal.timestamp,
    action: signal.action === 'NO_TRADE' ? 'HOLD' : 'TRADE',
    direction: signal.action,
    confidence: signal.confidence,
    tier: signal.tier,
    reasoning: `[Signal Engine] ${signal.reasoning}`,
    key_factors: signal.setup_name ? [signal.setup_name] : [],
    model: 'non-LLM',
  };
}

export async function ensureRecentBrainSignalsLoaded() {
  if (agent.decisions.length > 0 || recentSignalsInflight) return recentSignalsInflight;

  setRecentDecisionsLoading(true);
  recentSignalsInflight = (async () => {
    try {
      const data = await api.get<{ signals: any[] }>('/api/brain/signals/recent');
      const decisions = (data?.signals || []).map(toDecision);
      if (decisions.length > 0) setDecisions(decisions);
      setLastRecentDecisionsUpdateAt(Date.now());
    } catch (_) {
      // Keep the existing empty state on failure.
    } finally {
      setRecentDecisionsLoading(false);
      recentSignalsInflight = null;
    }
  })();

  return recentSignalsInflight;
}
