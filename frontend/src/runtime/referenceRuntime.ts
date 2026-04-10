import { api } from '../lib/api';
import { market } from '../signals/market';
import { loadChainSnapshot } from '../signals/chain';
import {
  reference,
  setChainStatus,
  setReferenceExpiration,
  setReferenceResource,
  setReferenceSymbol,
} from '../signals/reference';

let subscribers = 0;
let symbolTimer: ReturnType<typeof setInterval> | null = null;
let gexTimer: ReturnType<typeof setInterval> | null = null;
let sectorsTimer: ReturnType<typeof setInterval> | null = null;
let gexInflight: Promise<void> | null = null;
let sectorsInflight: Promise<void> | null = null;
let latestSymbolRequestId = 0;

async function refreshSymbolLinkedResources(force = false) {
  const symbol = market.symbol;
  if (!symbol) return;
  if (!force && reference.symbol === symbol && reference.volatility.lastUpdatedAt && Date.now() - reference.volatility.lastUpdatedAt < 5_000) {
    return;
  }

  const requestId = ++latestSymbolRequestId;

  setReferenceSymbol(symbol);
  setChainStatus(true, reference.chainReady, null);
  setReferenceResource('volatility', { loading: true, error: null });
  setReferenceResource('snapshot', { loading: true, error: null });
  setReferenceResource('levels', { loading: true, error: null });

  const isCurrent = () => requestId === latestSymbolRequestId && market.symbol === symbol;

  try {
    const expData = await api.getExpirations(symbol);
    if (!isCurrent()) return;

    const expirations = expData?.response || expData?.expirations || [];
    const nearest = expirations.length > 0 ? String(expirations[0]) : null;
    setReferenceExpiration(nearest);

    const tasks: Promise<void>[] = [
      api.getVolatilityAdvisor(symbol)
        .then((data) => {
          if (!isCurrent()) return;
          setReferenceResource('volatility', {
            data,
            loading: false,
            error: null,
            lastUpdatedAt: Date.now(),
          });
        })
        .catch((e: any) => {
          if (!isCurrent()) return;
          setReferenceResource('volatility', {
            loading: false,
            error: e?.message || 'Failed to load',
          });
        }),
      api.getLevels(symbol)
        .then((data) => {
          if (!isCurrent()) return;
          setReferenceResource('levels', {
            data,
            loading: false,
            error: null,
            lastUpdatedAt: Date.now(),
          });
        })
        .catch((e: any) => {
          if (!isCurrent()) return;
          setReferenceResource('levels', {
            loading: false,
            error: e?.message || 'Failed to load',
          });
        }),
    ];

    if (nearest) {
      tasks.push(
        api.getOptionsChain(symbol, nearest)
          .then((data) => {
            if (!isCurrent()) return;
            loadChainSnapshot(data);
            setChainStatus(false, true, null);
          })
          .catch((e: any) => {
            if (!isCurrent()) return;
            setChainStatus(false, false, e?.message || 'Failed to load');
          })
      );
      tasks.push(
        api.getOptionsSnapshot(symbol, nearest)
          .then((data) => {
            if (!isCurrent()) return;
            setReferenceResource('snapshot', {
              data,
              loading: false,
              error: null,
              lastUpdatedAt: Date.now(),
            });
          })
          .catch((e: any) => {
            if (!isCurrent()) return;
            setReferenceResource('snapshot', {
              loading: false,
              error: e?.message || 'Failed to load',
            });
          })
      );
    } else {
      setChainStatus(false, false, 'No expirations available');
      setReferenceResource('snapshot', {
        data: null,
        loading: false,
        error: 'No expirations available',
      });
    }

    await Promise.all(tasks);
  } catch (e: any) {
    if (!isCurrent()) return;
    const error = e?.message || 'Failed to load';
    setChainStatus(false, false, error);
    setReferenceResource('volatility', { loading: false, error });
    setReferenceResource('snapshot', { loading: false, error });
    setReferenceResource('levels', { loading: false, error });
  }
}

async function refreshGex() {
  if (gexInflight) return gexInflight;
  setReferenceResource('gex', { loading: true, error: null });
  gexInflight = (async () => {
    try {
      const data = await api.getGex();
      setReferenceResource('gex', {
        data,
        loading: false,
        error: null,
        lastUpdatedAt: Date.now(),
      });
    } catch (e: any) {
      setReferenceResource('gex', {
        loading: false,
        error: e?.message || 'Failed to load',
      });
    } finally {
      gexInflight = null;
    }
  })();
  return gexInflight;
}

async function refreshSectors() {
  if (sectorsInflight) return sectorsInflight;
  setReferenceResource('sectors', { loading: true, error: null });
  sectorsInflight = (async () => {
    try {
      const data = await api.getSectors();
      setReferenceResource('sectors', {
        data,
        loading: false,
        error: null,
        lastUpdatedAt: Date.now(),
      });
    } catch (e: any) {
      setReferenceResource('sectors', {
        loading: false,
        error: e?.message || 'Failed to load',
      });
    } finally {
      sectorsInflight = null;
    }
  })();
  return sectorsInflight;
}

export function refreshReferenceSymbolData(force = false) {
  return refreshSymbolLinkedResources(force);
}

export function subscribeReferenceRuntime() {
  subscribers += 1;
  if (subscribers === 1) {
    void refreshSymbolLinkedResources(true);
    void refreshGex();
    void refreshSectors();
    symbolTimer = setInterval(() => {
      void refreshSymbolLinkedResources();
    }, 30_000);
    gexTimer = setInterval(() => {
      void refreshGex();
    }, 30_000);
    sectorsTimer = setInterval(() => {
      void refreshSectors();
    }, 60_000);
  }
}

export function unsubscribeReferenceRuntime() {
  subscribers = Math.max(0, subscribers - 1);
  if (subscribers === 0) {
    if (symbolTimer) clearInterval(symbolTimer);
    if (gexTimer) clearInterval(gexTimer);
    if (sectorsTimer) clearInterval(sectorsTimer);
    symbolTimer = null;
    gexTimer = null;
    sectorsTimer = null;
  }
}
