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
  action: 'TRADE' | 'HOLD' | 'EXIT' | 'ADJUST';
  direction?: 'BUY_CALL' | 'BUY_PUT';
  confidence: number;
  tier: string;
  reasoning: string;
  key_factors: string[];
  chat_response?: string;
  risk_notes?: string;
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

export interface AgentState {
  brain: BrainState;
  messages: ChatMessage[];
  findings: ResearchFinding[];
  chatConnected: boolean;
}
