/**
 * Data layer — Rust engine live transport + Python REST APIs.
 *
 * The frontend currently consumes:
 *   - Rust engine WebTransport with WebSocket fallback for live protobuf data
 *   - Python REST endpoints for candles, quotes, signals, and options metadata
 *
 * Web Worker decoding keeps the protobuf hot path off the main thread.
 * Call `initDataLayer()` once on app mount.
 */
import { api } from './api';
import { createTransport, type TransportClient } from './transport';
import * as Comlink from 'comlink';
import { getProtoWorker } from '../workers/protobuf.api';
import {
  market,
  setMarket,
  setCandles,
  setSymbol,
  updateFromTick,
  updateQuote,
  appendCandle,
  replaceCurrentCandle,
    setConnected,
    setTransport,
    setDataSource,
    setLastEngineMessageAt,
    setLastQuoteUpdateAt,
    setQuoteSource,
  } from '../signals/market';
import { addOptionTrade, resetOptionsFlow, type OptionTrade } from '../signals/optionsFlow';
import { updateChainFromTrade, resetChain } from '../signals/chain';
import { updateCvd } from '../signals/flow';
import { resetReferenceForSymbol } from '../signals/reference';
import type { Tick, Candle, ChartInterval, ChartRange } from '../types/market';

function normalizeBarTime(raw: unknown): number {
  if (typeof raw === 'number' && isFinite(raw)) return raw;
  if (typeof raw === 'string') {
    if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
      return Math.floor(Date.parse(`${raw}T12:00:00Z`) / 1000);
    }
    const parsed = Date.parse(raw);
    if (Number.isFinite(parsed)) return Math.floor(parsed / 1000);
  }
  return 0;
}

/**
 * Get today's midnight in Eastern Time as epoch ms.
 */
let _etMidnightCache: { date: string; ms: number } | null = null;
function getTodayETMidnightMs(): number {
  const now = new Date();
  const todayStr = now.toLocaleDateString('en-US', { timeZone: 'America/New_York' });
  if (_etMidnightCache && _etMidnightCache.date === todayStr) return _etMidnightCache.ms;

  const etNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const etMidnight = new Date(etNow);
  etMidnight.setHours(0, 0, 0, 0);
  const etOffsetMs = now.getTime() - etNow.getTime();
  const result = etMidnight.getTime() + etOffsetMs;
  _etMidnightCache = { date: todayStr, ms: result };
  return result;
}

let engineTransport: TransportClient | null = null;
let _barPollInterval: ReturnType<typeof setInterval> | null = null;
let _quotePollInterval: ReturnType<typeof setInterval> | null = null;
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _visibilityHandler: (() => void) | null = null;
let _destroyed = false;
let _connecting: Promise<void> | null = null;
let _lastLiveTickAt = 0;

// RAF-gated message buffer: accumulate binary frames, decode in batch at refresh rate
let msgBuffer: ArrayBuffer[] = [];
let rafPending = false;
let protoBatchPending = false;

// 60fps tick throttler — batches high-frequency ticks, applies latest price per frame
let lastTickRaf = 0;
let pendingTick: Tick | null = null;
function throttledTick(tick: Tick) {
  pendingTick = tick;
  const now = performance.now();
  if (now - lastTickRaf > 16) {
    lastTickRaf = now;
    updateFromTick(pendingTick);
    pendingTick = null;
  } else if (!rafPending) {
    rafPending = true;
    requestAnimationFrame(() => {
      rafPending = false;
      if (pendingTick) {
        updateFromTick(pendingTick);
        pendingTick = null;
      }
    });
  }
}

function barsNeededForRange(interval: ChartInterval, range: ChartRange): number {
  const intervalSeconds: Record<ChartInterval, number> = {
    '1Min': 60,
    '2Min': 120,
    '5Min': 300,
    '10Min': 600,
    '15Min': 900,
    '30Min': 1800,
    '1H': 3600,
    '4Hour': 14400,
    '1D': 86400,
    '1Week': 604800,
  };
  const tradingDays: Record<ChartRange, number> = {
    '1D': 1,
    '1W': 5,
    '1M': 21,
    '3M': 63,
    '1Y': 252,
    'MAX': 520,
  };
  const seconds = intervalSeconds[interval];
  if (seconds >= 604800) {
    return Math.min(520, Math.max(26, Math.round(tradingDays[range] / 5) + 8));
  }
  if (seconds >= 86400) {
    return Math.min(5000, Math.max(60, tradingDays[range] + 20));
  }
  const sessionSeconds = tradingDays[range] * 6.5 * 3600;
  return Math.min(5000, Math.max(120, Math.round(sessionSeconds / seconds) + 30));
}

/**
 * Load historical candle data from REST API (Python backend).
 */
export async function loadCandles(retries = 5) {
  const limit = barsNeededForRange(market.interval, market.range);
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const data = await api.getBars(market.symbol, market.interval, limit);
      if (Array.isArray(data.bars) && data.bars.length > 0) {
        const candles: Candle[] = data.bars.map((b: any) => ({
          time: normalizeBarTime(b.time ?? b.t),
          open: b.open ?? b.o,
          high: b.high ?? b.h,
          low: b.low ?? b.l,
          close: b.close ?? b.c,
          volume: b.volume ?? b.v ?? 0,
        }));
        setCandles(candles);
        return;
      }
      if (Array.isArray(data.bars) && data.bars.length === 0) {
        setCandles([]);
        return;
      }
    } catch (e) {
      console.warn(`[Data] Failed to load candles (attempt ${attempt + 1}/${retries}):`, e);
    }
    if (attempt < retries - 1) {
      await new Promise(r => setTimeout(r, 1000 * Math.pow(2, attempt)));
    }
  }
}

async function loadQuote() {
  try {
    const data = await api.getQuote(market.symbol);
    setLastQuoteUpdateAt(Date.now());
    if (data.source) {
      setQuoteSource(data.source);
    }
    if (data.bid || data.ask) {
      updateQuote({
        bid: data.bid ?? 0,
        ask: data.ask ?? 0,
        bid_size: 0,
        ask_size: 0,
        timestamp_ms: Date.now(),
      });
    }
    if (data.last) {
      setMarket('lastPrice', data.last);

      // When the engine transport is connected but not receiving fresh stock ticks,
      // keep the active candle visually alive from the latest quote REST fallback.
      if (Date.now() - _lastLiveTickAt > 3000) {
        throttledTick({
          price: data.last,
          size: 0,
          side: 'unknown',
          timestamp_ms: Date.now(),
        });
      }
    }
  } catch (e) {
    console.warn('[Data] Failed to load quote:', e);
  }
}

export async function switchSymbol(symbol: string) {
  const sym = symbol.toUpperCase().trim();
  if (!sym || sym === market.symbol) return;

  resetReferenceForSymbol(sym);
  setSymbol(sym);
  setCandles([]);
  setMarket('currentCandle', null);
  setMarket('lastPrice', 0);
  setMarket('quote', null);
  setQuoteSource(null);
  setLastQuoteUpdateAt(null);
  resetOptionsFlow();
  resetChain();

  api.post('/api/stream/subscribe', [sym]).catch(() => {});
  api.post('/api/theta/subscribe', { symbol: sym }).catch(() => {});

  await Promise.all([loadCandles(), loadQuote()]);
}

// ── Message handler (processes decoded protobuf objects) ────────────────────

/** Handle a single decoded message — same logic as before, just extracted */
function handleDecodedMessage(data: any) {
  if (!data || !data.type) return;
  setLastEngineMessageAt(Date.now());
  const type = data.type;

  switch (type) {
    case 'tick':
    case 'Tick':
    case 'trade': {
      if (data.symbol && data.symbol !== market.symbol) break;
      _lastLiveTickAt = Date.now();
      // Throttle ticks to 60fps — high-frequency data would freeze the chart otherwise
      throttledTick({
        price: data.price ?? data.p,
        size: data.size ?? data.s ?? 0,
        side: data.side ?? 'unknown',
        timestamp_ms: data.timestamp ?? data.t ?? Date.now(),
      });
      break;
    }
    case 'quote': {
      if (data.symbol && data.symbol !== market.symbol) break;
      _lastLiveTickAt = Date.now();
      updateQuote({
        bid: data.bid ?? data.bp ?? 0,
        ask: data.ask ?? data.ap ?? 0,
        bid_size: data.bid_size ?? data.bs ?? 0,
        ask_size: data.ask_size ?? data.as ?? 0,
        timestamp_ms: data.timestamp ?? Date.now(),
      });
      break;
    }
    case 'theta_trade': {
      if (data.root && data.root !== market.symbol) break;
      const trade: OptionTrade = {
        strike: data.strike ?? 0,
        right: data.right === 'P' ? 'P' : 'C',
        price: data.price ?? 0,
        size: data.size ?? 0,
        premium: data.premium ?? (data.price ?? 0) * (data.size ?? 0) * 100,
        exchange: String(data.exchange ?? ''),
        timestamp: data.ms_of_day
          ? getTodayETMidnightMs() + data.ms_of_day
          : (data.timestamp ? data.timestamp * 1000 : Date.now()),
        expiration: data.expiration ?? 0,
        root: data.root ?? market.symbol,
        condition: data.condition ?? 0,
        side: data.side === 'buy' ? 'buy' : data.side === 'sell' ? 'sell' : 'mid',
        iv: data.iv ?? null,
        delta: data.delta ?? null,
        gamma: data.gamma ?? null,
        vpin: data.vpin ?? null,
        sms: data.sms ?? 0,
        tag: 'normal',
        clusterId: null,
        spyPrice: market.lastPrice,
      };
      if (trade.price > 0 && trade.size > 0) {
        addOptionTrade(trade);
        updateChainFromTrade(trade);
      }
      break;
    }
    case 'bar':
    case 'bar_update': {
      if (data.symbol && data.symbol !== market.symbol) break;
      const candle: Candle = {
        time: normalizeBarTime(data.t ?? data.timestamp),
        open: data.o ?? data.open,
        high: data.h ?? data.high,
        low: data.l ?? data.low,
        close: data.c ?? data.close,
        volume: data.v ?? data.volume ?? 0,
      };
      if (type === 'bar') appendCandle(candle);
      else replaceCurrentCandle(candle);
      break;
    }
    case 'cvd': {
      updateCvd(data.value ?? 0, data.delta_1m ?? 0, data.delta_5m ?? 0);
      break;
    }
    // Flow events: footprint, sweep, imbalance, absorption, delta_flip, large_trade
    // Currently consumed by flow_subscriber on the Python side.
    case 'footprint':
    case 'sweep':
    case 'imbalance':
    case 'absorption':
    case 'delta_flip':
    case 'large_trade':
      break;
    case 'heartbeat':
      if (data.data_source) {
        setDataSource(data.data_source);
      }
      break;
  }
}

// ── Data layer init/destroy ─────────────────────────────────────────────────

/** Process a raw message (ArrayBuffer or string) from any transport */
function handleRawMessage(raw: any, protoWorker: any) {
  if (raw instanceof ArrayBuffer) {
    const view = new Uint8Array(raw);
    if (view.length === 0) return;

    if (view[0] === 0x7B) {
      // JSON text encoded as ArrayBuffer
      try {
        const text = new TextDecoder().decode(view);
        if (text.indexOf('"theta_quote"') >= 0 && text.indexOf('"theta_quote"') < 20) return;
        const data = JSON.parse(text);
        handleDecodedMessage(data);
      } catch {}
    } else {
      // Protobuf binary
      msgBuffer.push(raw);
      if (!protoBatchPending) {
        protoBatchPending = true;
        requestAnimationFrame(async () => {
          protoBatchPending = false;
          const batch = msgBuffer;
          msgBuffer = [];
          if (batch.length === 0) return;
          try {
            const decoded = await protoWorker.decodeBatch(
              Comlink.transfer(batch, batch)
            );
            for (const msg of decoded) {
              handleDecodedMessage(msg);
            }
          } catch (e) {
            console.warn('[Data] Proto decode error:', e);
          }
        });
      }
    }
  } else if (typeof raw === 'string') {
    try {
      if (raw.indexOf('"theta_quote"') >= 0 && raw.indexOf('"theta_quote"') < 20) return;
      const data = JSON.parse(raw);
      handleDecodedMessage(data);
    } catch {}
  }
}

export function initDataLayer() {
  if (engineTransport || _connecting) return;

  _destroyed = false;

  const protoWorker = getProtoWorker();
  const wsHost = window.location.hostname || 'localhost';

  const connect = async () => {
    if (_destroyed || engineTransport || _connecting) return;

    _connecting = (async () => {
      try {
        const transport = await createTransport(wsHost);
        if (_destroyed) {
          transport.close();
          return;
        }

        engineTransport = transport;
        setConnected(true);
        setTransport(transport.transport);
        transport.onMessage((raw) => {
          handleRawMessage(raw, protoWorker);
        });
        transport.onClose(() => {
          if (engineTransport !== transport) return;
          engineTransport = null;
          setConnected(false);
          setTransport('disconnected');
          if (!_destroyed) {
            _reconnectTimer = setTimeout(() => {
              void connect();
            }, 1500);
          }
        });
        loadQuote();
      } catch (e) {
        console.warn('[Data] Failed to connect to engine transport:', e);
        setConnected(false);
        setTransport('disconnected');
        if (!_destroyed) {
          _reconnectTimer = setTimeout(() => {
            void connect();
          }, 3000);
        }
      } finally {
        _connecting = null;
      }
    })();

    await _connecting;
  };

  void connect();

  // Load initial data via REST (Python backend)
  loadCandles();
  loadQuote();

  // Refresh quote when tab becomes visible
  _visibilityHandler = () => {
    if (document.visibilityState === 'visible') loadQuote();
  };
  document.addEventListener('visibilitychange', _visibilityHandler);

  // Quote poll keeps the chart moving when the engine is connected but the
  // current stock tick source is stale or replay-only.
  _quotePollInterval = setInterval(() => {
    void loadQuote();
  }, 5000);

  // Poll for fresh bars as fallback to advance the active candle/bar window.
  _barPollInterval = setInterval(async () => {
    try {
      const tf = market.interval || '5Min';
      const data = await api.get<{ bars: any[] }>(`/api/bars?symbol=${market.symbol}&timeframe=${tf}&limit=3`);
      if (data?.bars?.length) {
        const latest = data.bars[data.bars.length - 1];
        const candle: Candle = {
          time: normalizeBarTime(latest.time ?? latest.t),
          open: latest.open ?? latest.o,
          high: latest.high ?? latest.h,
          low: latest.low ?? latest.l,
          close: latest.close ?? latest.c,
          volume: latest.volume ?? latest.v ?? 0,
        };
        const existing = market.candles;
        if (existing.length > 0) {
          const lastTime = existing[existing.length - 1].time;
          if (candle.time > lastTime) appendCandle(candle);
          else if (candle.time === lastTime) replaceCurrentCandle(candle);
        }
      }
    } catch {}
  }, 15000);
}

export function destroyDataLayer() {
  _destroyed = true;
  if (_reconnectTimer) clearTimeout(_reconnectTimer);
  if (_barPollInterval) clearInterval(_barPollInterval);
  if (_quotePollInterval) clearInterval(_quotePollInterval);
  if (_visibilityHandler) {
    document.removeEventListener('visibilitychange', _visibilityHandler);
  }
  engineTransport?.close();
  engineTransport = null;
  _barPollInterval = null;
  _quotePollInterval = null;
  _reconnectTimer = null;
  _visibilityHandler = null;
  _connecting = null;
  _lastLiveTickAt = 0;
  setConnected(false);
  setTransport('disconnected');
  setDataSource(null);
  setQuoteSource(null);
  setLastEngineMessageAt(null);
  setLastQuoteUpdateAt(null);
  msgBuffer = [];
  rafPending = false;
}
