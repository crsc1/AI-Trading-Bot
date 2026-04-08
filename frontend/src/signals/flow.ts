import { createStore } from 'solid-js/store';
import type { FlowState, FlowCloud, FlowMeta } from '../types/flow';

export interface CvdState {
  value: number;       // cumulative volume delta
  delta1m: number;     // 1-minute rolling delta
  delta5m: number;     // 5-minute rolling delta
  velocity: number;    // rate of change (delta1m normalized)
  acceleration: number; // change in velocity (delta1m - delta5m trend)
  lastUpdate: number;  // timestamp ms
}

const initialState: FlowState = {
  clouds: [],
  bubbles: [],
  meta: null,
  connected: false,
};

const [flow, setFlow] = createStore(initialState);

const [cvd, setCvdStore] = createStore<CvdState>({
  value: 0,
  delta1m: 0,
  delta5m: 0,
  velocity: 0,
  acceleration: 0,
  lastUpdate: 0,
});

export { flow, setFlow, cvd };

// Rolling velocity history for acceleration computation
let prevDelta1m = 0;
let prevDelta1mTs = 0;

export function updateCvd(value: number, delta1m: number, delta5m: number) {
  const now = Date.now();

  // Velocity: normalized rate of buying/selling pressure
  // delta1m / 1000 gives a human-readable scale (-1 to +1 ish)
  const velocity = delta1m / 1000;

  // Acceleration: is buying/selling pressure increasing or decreasing?
  // Compare current 1m delta to previous reading
  let acceleration = 0;
  if (prevDelta1mTs > 0 && now - prevDelta1mTs < 10_000) {
    // Rate of change of delta1m (per second, scaled)
    // Floor at 0.1s to avoid extreme spikes on rapid updates / reconnect bursts
    const dtSec = Math.max(0.1, (now - prevDelta1mTs) / 1000);
    acceleration = (delta1m - prevDelta1m) / dtSec / 500;
  }
  prevDelta1m = delta1m;
  prevDelta1mTs = now;

  setCvdStore({
    value,
    delta1m,
    delta5m,
    velocity,
    acceleration,
    lastUpdate: now,
  });
}

export function setClouds(clouds: FlowCloud[], meta: FlowMeta | null) {
  setFlow('clouds', clouds);
  setFlow('meta', meta);
}

export function setFlowConnected(connected: boolean) {
  setFlow('connected', connected);
}
