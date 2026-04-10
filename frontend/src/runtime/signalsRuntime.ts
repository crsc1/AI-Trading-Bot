import { api } from '../lib/api';
import {
  setDailyPerformance,
  setLastPositionsUpdateAt,
  setLastSignalsUpdateAt,
  setLatestSignal,
  setPositions,
  setPositionsLoading,
  setSignalHistory,
  setSignalsLoading,
} from '../signals/signals';
import type { Signal } from '../types/signal';

let signalSubscribers = 0;
let positionSubscribers = 0;
let signalTimer: ReturnType<typeof setInterval> | null = null;
let positionTimer: ReturnType<typeof setInterval> | null = null;
let signalsInflight: Promise<void> | null = null;
let positionsInflight: Promise<void> | null = null;

function normalizeSignal(raw: any): Signal | null {
  if (!raw || typeof raw !== 'object') return null;

  const action = raw.action ?? raw.signal;
  if (action !== 'BUY_CALL' && action !== 'BUY_PUT' && action !== 'NO_TRADE') {
    return null;
  }

  const tier = raw.tier ?? 'DEVELOPING';
  const status = raw.status ?? 'OPEN';

  return {
    id: String(raw.id ?? raw.timestamp ?? `${action}-${Date.now()}`),
    action,
    confidence: Number(raw.confidence ?? 0),
    tier: tier === 'TEXTBOOK' || tier === 'HIGH' || tier === 'VALID' || tier === 'DEVELOPING' ? tier : 'DEVELOPING',
    strike: Number(raw.strike ?? 0),
    entry_price: Number(raw.entry_price ?? 0),
    target_price: Number(raw.target_price ?? 0),
    stop_price: Number(raw.stop_price ?? 0),
    max_contracts: Number(raw.max_contracts ?? 0),
    reasoning: String(raw.reasoning ?? ''),
    key_factors: Array.isArray(raw.key_factors) ? raw.key_factors : Array.isArray(raw.factors) ? raw.factors : [],
    setup_name: raw.setup_name ? String(raw.setup_name) : undefined,
    timestamp: String(raw.timestamp ?? new Date().toISOString()),
    status:
      status === 'OPEN' || status === 'TARGET_HIT' || status === 'STOPPED' || status === 'EXPIRED' || status === 'CLOSED'
        ? status
        : 'OPEN',
    pnl_dollars: raw.pnl_dollars ?? undefined,
    pnl_percent: raw.pnl_percent ?? undefined,
  };
}

async function refreshSignals() {
  if (signalsInflight) return signalsInflight;

  setSignalsLoading(true);
  signalsInflight = (async () => {
    try {
      const [latest, history] = await Promise.all([
        api.getLatestSignal().catch(() => null),
        api.getSignalHistory().catch(() => ({ signals: [] })),
      ]);

      const latestSignal = normalizeSignal(latest);
      if (latestSignal) setLatestSignal(latestSignal);

      const historyRows = Array.isArray(history)
        ? history
        : Array.isArray(history?.signals)
          ? history.signals
          : [];
      const normalizedHistory = historyRows
        .map((row: any) => normalizeSignal(row))
        .filter((row: Signal | null): row is Signal => row !== null);
      setSignalHistory(normalizedHistory);
      setLastSignalsUpdateAt(Date.now());
    } finally {
      setSignalsLoading(false);
      signalsInflight = null;
    }
  })();

  return signalsInflight;
}

async function refreshPositions() {
  if (positionsInflight) return positionsInflight;

  setPositionsLoading(true);
  positionsInflight = (async () => {
    try {
      const [posData, statusData] = await Promise.all([
        api.getPositions().catch(() => ({ positions: [] })),
        api.getStatus().catch(() => null),
      ]);

      if (posData?.positions) setPositions(posData.positions);
      if (statusData) {
        setDailyPerformance({
          total_pnl: statusData.daily_pnl || 0,
          win_count: statusData.wins || 0,
          loss_count: statusData.losses || 0,
          win_rate: statusData.win_rate || 0,
          trades_today: statusData.trades_today || 0,
        });
      }
      setLastPositionsUpdateAt(Date.now());
    } finally {
      setPositionsLoading(false);
      positionsInflight = null;
    }
  })();

  return positionsInflight;
}

export function subscribeSignalFeed() {
  signalSubscribers += 1;
  if (signalSubscribers === 1) {
    void refreshSignals();
    signalTimer = setInterval(() => {
      void refreshSignals();
    }, 10_000);
  }
}

export function unsubscribeSignalFeed() {
  signalSubscribers = Math.max(0, signalSubscribers - 1);
  if (signalSubscribers === 0 && signalTimer) {
    clearInterval(signalTimer);
    signalTimer = null;
  }
}

export function subscribePositionSummary() {
  positionSubscribers += 1;
  if (positionSubscribers === 1) {
    void refreshPositions();
    positionTimer = setInterval(() => {
      void refreshPositions();
    }, 5_000);
  }
}

export function unsubscribePositionSummary() {
  positionSubscribers = Math.max(0, positionSubscribers - 1);
  if (positionSubscribers === 0 && positionTimer) {
    clearInterval(positionTimer);
    positionTimer = null;
  }
}
