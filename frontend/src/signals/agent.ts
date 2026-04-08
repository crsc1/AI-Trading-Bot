import { createStore } from 'solid-js/store';
import type { AgentState, ChatMessage, BrainState, BrainDecision, PatternRecall, ResearchFinding } from '../types/agent';

const initialBrain: BrainState = {
  status: 'idle',
  cycle_number: 0,
  last_action: 'HOLD',
  last_confidence: 0,
  last_reasoning: '',
  model: '',
  uptime_s: 0,
};

const initialState: AgentState = {
  brain: initialBrain,
  messages: [],
  decisions: [],
  patternRecall: null,
  findings: [],
  chatConnected: false,
  activeTab: 'brain',
};

const [agent, setAgent] = createStore(initialState);

export { agent, setAgent };

export function addMessage(msg: ChatMessage) {
  // Deduplicate by id (server replays history on reconnect)
  setAgent('messages', (prev) => {
    if (prev.some((m) => m.id === msg.id)) return prev;
    return [...prev, msg];
  });
}

export function addDecision(decision: BrainDecision) {
  setAgent('decisions', (prev) => {
    // Keep last 50 decisions
    const next = [decision, ...prev];
    return next.slice(0, 50);
  });
}

export function setPatternRecall(recall: PatternRecall) {
  setAgent('patternRecall', recall);
}

export function updateBrain(state: Partial<BrainState>) {
  setAgent('brain', (prev) => ({ ...prev, ...state }));
}

export function setFindings(findings: ResearchFinding[]) {
  setAgent('findings', findings);
}

export function setChatConnected(connected: boolean) {
  setAgent('chatConnected', connected);
}

export function setActiveTab(tab: 'brain' | 'chat') {
  setAgent('activeTab', tab);
}
