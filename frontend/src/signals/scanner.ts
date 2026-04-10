import { createStore } from 'solid-js/store';
import type { FlowAlert, ScannerStats } from '../types/scanner';

interface ScannerState {
  alerts: FlowAlert[];
  stats: ScannerStats | null;
  loading: boolean;
  lastUpdatedAt: number | null;
}

const initialState: ScannerState = {
  alerts: [],
  stats: null,
  loading: true,
  lastUpdatedAt: null,
};

const [scanner, setScanner] = createStore(initialState);

export { scanner, setScanner };

export function setAlerts(alerts: FlowAlert[]) {
  setScanner('alerts', alerts);
}

export function setScannerStats(stats: ScannerStats | null) {
  setScanner('stats', stats);
}

export function setScannerLoading(loading: boolean) {
  setScanner('loading', loading);
}

export function setScannerLastUpdatedAt(timestamp: number | null) {
  setScanner('lastUpdatedAt', timestamp);
}
