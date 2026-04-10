import { api } from '../lib/api';
import { setAlerts, setScannerLastUpdatedAt, setScannerLoading, setScannerStats } from '../signals/scanner';
import type { FlowAlert, ScannerStats } from '../types/scanner';

let scannerSubscribers = 0;
let scannerTimer: ReturnType<typeof setInterval> | null = null;
let scannerInflight: Promise<void> | null = null;

async function refreshScanner() {
  if (scannerInflight) return scannerInflight;

  setScannerLoading(true);
  scannerInflight = (async () => {
    try {
      const [alertsData, statsData] = await Promise.all([
        api.get<{ alerts: FlowAlert[] }>('/api/brain/scanner/alerts?limit=100').catch(() => ({ alerts: [] })),
        api.get<ScannerStats>('/api/brain/scanner/stats').catch(() => null),
      ]);
      setAlerts(alertsData?.alerts || []);
      setScannerStats(statsData);
      setScannerLastUpdatedAt(Date.now());
    } finally {
      setScannerLoading(false);
      scannerInflight = null;
    }
  })();

  return scannerInflight;
}

export function subscribeScannerRuntime() {
  scannerSubscribers += 1;
  if (scannerSubscribers === 1) {
    void refreshScanner();
    scannerTimer = setInterval(() => {
      void refreshScanner();
    }, 5_000);
  }
}

export function unsubscribeScannerRuntime() {
  scannerSubscribers = Math.max(0, scannerSubscribers - 1);
  if (scannerSubscribers === 0 && scannerTimer) {
    clearInterval(scannerTimer);
    scannerTimer = null;
  }
}
