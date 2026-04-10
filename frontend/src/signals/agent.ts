import { createStore } from 'solid-js/store';
import type { AgentState, ChatMessage, BrainState, BrainDecision, CycleUpdate, PatternRecall, ResearchFinding, DataSource } from '../types/agent';

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
  recentDecisionsLoading: false,
  lastRecentDecisionsUpdateAt: null,
  lastCycle: null,
  patternRecall: null,
  sources: [],
  model: '',
  sourcesLoading: true,
  findingsLoading: true,
  lastSourcesUpdateAt: null,
  lastFindingsUpdateAt: null,
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

export function setDecisions(decisions: BrainDecision[]) {
  setAgent('decisions', decisions);
}

export function setLastCycle(cycle: CycleUpdate) {
  setAgent('lastCycle', cycle);
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

export function setSources(sources: DataSource[]) {
  setAgent('sources', sources);
}

export function setModel(model: string) {
  setAgent('model', model);
}

export function setSourcesLoading(loading: boolean) {
  setAgent('sourcesLoading', loading);
}

export function setFindingsLoading(loading: boolean) {
  setAgent('findingsLoading', loading);
}

export function setLastSourcesUpdateAt(timestamp: number | null) {
  setAgent('lastSourcesUpdateAt', timestamp);
}

export function setLastFindingsUpdateAt(timestamp: number | null) {
  setAgent('lastFindingsUpdateAt', timestamp);
}

export function setRecentDecisionsLoading(loading: boolean) {
  setAgent('recentDecisionsLoading', loading);
}

export function setLastRecentDecisionsUpdateAt(timestamp: number | null) {
  setAgent('lastRecentDecisionsUpdateAt', timestamp);
}

export function setChatConnected(connected: boolean) {
  setAgent('chatConnected', connected);
}

export function setActiveTab(tab: 'brain' | 'chat') {
  setAgent('activeTab', tab);
}
