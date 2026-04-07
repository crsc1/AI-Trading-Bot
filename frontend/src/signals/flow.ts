import { createStore } from 'solid-js/store';
import type { FlowState, FlowCloud, FlowMeta } from '../types/flow';

const initialState: FlowState = {
  clouds: [],
  bubbles: [],
  meta: null,
  connected: false,
};

const [flow, setFlow] = createStore(initialState);

export { flow, setFlow };

export function setClouds(clouds: FlowCloud[], meta: FlowMeta | null) {
  setFlow('clouds', clouds);
  setFlow('meta', meta);
}

export function setFlowConnected(connected: boolean) {
  setFlow('connected', connected);
}
