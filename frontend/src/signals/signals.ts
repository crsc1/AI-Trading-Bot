import { createStore } from 'solid-js/store';
import type { Signal, Position, DailyPerformance } from '../types/signal';

interface SignalState {
  latest: Signal | null;
  history: Signal[];
  positions: Position[];
  daily: DailyPerformance;
  signalsLoading: boolean;
  positionsLoading: boolean;
  lastSignalsUpdateAt: number | null;
  lastPositionsUpdateAt: number | null;
}

const initialState: SignalState = {
  latest: null,
  history: [],
  positions: [],
  daily: {
    total_pnl: 0,
    win_count: 0,
    loss_count: 0,
    win_rate: 0,
    trades_today: 0,
  },
  signalsLoading: true,
  positionsLoading: true,
  lastSignalsUpdateAt: null,
  lastPositionsUpdateAt: null,
};

const [signals, setSignals] = createStore(initialState);

export { signals, setSignals };

export function setLatestSignal(signal: Signal) {
  setSignals('latest', signal);
}

export function setSignalHistory(history: Signal[]) {
  setSignals('history', history);
}

export function setPositions(positions: Position[]) {
  setSignals('positions', positions);
}

export function setDailyPerformance(daily: DailyPerformance) {
  setSignals('daily', daily);
}

export function setSignalsLoading(loading: boolean) {
  setSignals('signalsLoading', loading);
}

export function setPositionsLoading(loading: boolean) {
  setSignals('positionsLoading', loading);
}

export function setLastSignalsUpdateAt(timestamp: number | null) {
  setSignals('lastSignalsUpdateAt', timestamp);
}

export function setLastPositionsUpdateAt(timestamp: number | null) {
  setSignals('lastPositionsUpdateAt', timestamp);
}
