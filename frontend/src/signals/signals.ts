import { createStore } from 'solid-js/store';
import type { Signal, Position, DailyPerformance } from '../types/signal';

interface SignalState {
  latest: Signal | null;
  history: Signal[];
  positions: Position[];
  daily: DailyPerformance;
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
