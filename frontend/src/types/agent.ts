export interface ChatMessage {
  id: string;
  role: 'user' | 'brain' | 'system';
  content: string;
  timestamp: string;
  metadata?: {
    cycle_number?: number;
    confidence?: number;
    action?: string;
    duration_ms?: number;
    input_tokens?: number;
    output_tokens?: number;
    cost_usd?: number;
  };
}

export interface BrainState {
  status: 'idle' | 'analyzing' | 'trading' | 'error';
  cycle_number: number;
  last_action: string;
  last_confidence: number;
  last_reasoning: string;
  model: string;
  uptime_s: number;
}

export interface BrainDecision {
  id?: string;
  timestamp?: string;
  action: 'TRADE' | 'HOLD' | 'EXIT' | 'ADJUST';
  direction?: 'BUY_CALL' | 'BUY_PUT';
  confidence: number;
  tier: string;
  reasoning: string;
  key_factors: string[];
  chat_response?: string;
  risk_notes?: string;
  cycle?: number;
  model?: string;
  latency_ms?: number;
}

export interface MarketMoment {
  id: string;
  timestamp: string;
  trigger_type: string;
  trigger_name?: string;
  trigger_detail?: string;
  spy_price: number;
  session_phase?: string;
  regime?: string;
  setup_name?: string;
  setup_quality?: number;
  outcome_direction?: string;
  outcome_magnitude?: string;
  move_pct_15min?: number;
  similarity?: number;
  brain_action?: string;
  brain_confidence?: number;
  was_traded?: boolean;
  trade_pnl?: number;
}

export interface PatternRecall {
  similar_moments: MarketMoment[];
  moments_stats: {
    total_moments: number;
    with_outcomes: number;
    today: number;
    cache_size: number;
  };
}

export interface ResearchFinding {
  id: string;
  type: 'sentiment' | 'pattern' | 'suggestion';
  title: string;
  content: string;
  source: string;
  confidence: number;
  timestamp: string;
}

export interface DataSource {
  name: string;
  status: 'live' | 'offline' | 'error';
  detail?: string;
  source?: string;
}

export interface SourcesResponse {
  sources: DataSource[];
  model: string;
}

export interface CycleUpdate {
  action: string;
  confidence: number;
  reasoning: string;
  trade_count: number;
  trades_source: string;
  timestamp: string;
}

export interface AgentState {
  brain: BrainState;
  messages: ChatMessage[];
  decisions: BrainDecision[];
  recentDecisionsLoading: boolean;
  lastRecentDecisionsUpdateAt: number | null;
  lastCycle: CycleUpdate | null;
  patternRecall: PatternRecall | null;
  sources: DataSource[];
  model: string;
  sourcesLoading: boolean;
  findingsLoading: boolean;
  lastSourcesUpdateAt: number | null;
  lastFindingsUpdateAt: number | null;
  findings: ResearchFinding[];
  chatConnected: boolean;
  activeTab: 'brain' | 'chat';
}
