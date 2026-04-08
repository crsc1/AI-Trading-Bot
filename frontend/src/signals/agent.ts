import { createStore } from 'solid-js/store';
import type { AgentState, ChatMessage, BrainState, ResearchFinding } from '../types/agent';

const initialBrain: BrainState = {
  status: 'idle',
  cycle_number: 0,
  last_action: 'HOLD',
  last_confidence: 0,
  last_reasoning: '',
  model: 'sonnet-4.6',
  uptime_s: 0,
};

const initialState: AgentState = {
  brain: initialBrain,
  messages: [],
  findings: [],
  chatConnected: false,
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

export function updateBrain(state: Partial<BrainState>) {
  setAgent('brain', (prev) => ({ ...prev, ...state }));
}

export function setFindings(findings: ResearchFinding[]) {
  setAgent('findings', findings);
}

export function setChatConnected(connected: boolean) {
  setAgent('chatConnected', connected);
}
