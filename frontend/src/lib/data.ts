/**
 * Data layer — single WebSocket (protobuf binary) to Rust engine + REST to Python.
 *
 * Architecture:
 *   Rust engine (port 8081) = unified WS broadcaster, protobuf binary frames
 *     - Flow events (tick, cvd, footprint, sweep, etc.) encoded natively by Rust
 *     - Python events (theta_trade, quote, bar) forwarded via /ingest, wrapped in ExternalJson
 *   Web Worker decodes protobuf off main thread via Comlink
 *   RAF gating: messages buffered, decoded in batch, applied at screen refresh rate
 *   Python backend (port 8000) = REST-only for AI, signals, positions, candles
 *
 * Call `initDataLayer()` once on app mount.
 */
import { WSClient } from './ws';
import { api } from './api';
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
  setConnected,
} from '../signals/market';
import { addOptionTrade, resetOptionsFlow, type OptionTrade } from '../signals/optionsFlow';
import { updateChainFromTrade, resetChain } from '../signals/chain';
import { updateCvd } from '../signals/flow';
import type { Tick, Candle } from '../types/market';

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

let ws: WSClient | null = null;
let _barPollInterval: ReturnType<typeof setInterval> | null = null;

// RAF-gated message buffer: accumulate binary frames, decode in batch at refresh rate
let msgBuffer: ArrayBuffer[] = [];
let rafPending = false;

/**
 * Load historical candle data from REST API (Python backend).
 */
export async function loadCandles(retries = 5) {
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const data = await api.getBars(market.symbol, market.timeframe);
      if (data.bars && data.bars.length > 0) {
        const candles: Candle[] = data.bars.map((b: any) => ({
          time: b.time ?? b.t,
          open: b.open ?? b.o,
          high: b.high ?? b.h,
          low: b.low ?? b.l,
          close: b.close ?? b.c,
          volume: b.volume ?? b.v ?? 0,
        }));
        setCandles(candles);
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
    if (data.last) setMarket('lastPrice', data.last);
  } catch (e) {
    console.warn('[Data] Failed to load quote:', e);
  }
}

export async function switchSymbol(symbol: string) {
  const sym = symbol.toUpperCase().trim();
  if (!sym || sym === market.symbol) return;

  setSymbol(sym);
  setCandles([]);
  setMarket('currentCandle', null);
  setMarket('lastPrice', 0);
  setMarket('quote', null);
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
  const type = data.type;

  switch (type) {
    case 'tick':
    case 'Tick':
    case 'trade': {
      if (data.symbol && data.symbol !== market.symbol) break;
      updateFromTick({
        price: data.price ?? data.p,
        size: data.size ?? data.s ?? 0,
        side: data.side ?? 'unknown',
        timestamp_ms: data.timestamp ?? data.t ?? Date.now(),
      });
      break;
    }
    case 'quote': {
      if (data.symbol && data.symbol !== market.symbol) break;
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
        time: data.t ?? data.timestamp,
        open: data.o ?? data.open,
        high: data.h ?? data.high,
        low: data.l ?? data.low,
        close: data.c ?? data.close,
        volume: data.v ?? data.volume ?? 0,
      };
      if (type === 'bar') appendCandle(candle);
      else setMarket('currentCandle', candle);
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
    case 'heartbeat':
      break;
  }
}

// ── Data layer init/destroy ─────────────────────────────────────────────────

export function initDataLayer() {
  if (ws) return;

  const protoWorker = getProtoWorker();
  const wsHost = window.location.hostname || 'localhost';

  ws = new WSClient({
    name: 'Engine',
    url: `ws://${wsHost}:8081/ws`,
    encoding: 'protobuf',
    onMessage: (buffer: ArrayBuffer) => {
      // Accumulate binary frames — don't decode on main thread
      msgBuffer.push(buffer);

      if (!rafPending) {
        rafPending = true;
        requestAnimationFrame(async () => {
          rafPending = false;
          const batch = msgBuffer;
          msgBuffer = [];

          if (batch.length === 0) return;

          try {
            // Transfer ArrayBuffers to worker (zero-copy, ownership moves to worker)
            const decoded = await protoWorker.decodeBatch(
              Comlink.transfer(batch, batch)
            );

            // Apply decoded messages to stores
            for (const msg of decoded) {
              handleDecodedMessage(msg);
            }
          } catch (e) {
            console.warn('[Data] Proto decode error:', e);
          }
        });
      }
    },
    onConnect: () => {
      setConnected(true);
      loadQuote();
    },
    onDisconnect: () => setConnected(false),
  });

  ws.connect();

  // Load initial data via REST (Python backend)
  loadCandles();
  loadQuote();

  // Refresh quote when tab becomes visible
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') loadQuote();
  });

  // Poll for fresh bars every 15s as fallback
  _barPollInterval = setInterval(async () => {
    try {
      const tf = market.timeframe || '5Min';
      const data = await api.get<{ bars: any[] }>(`/api/bars?symbol=${market.symbol}&timeframe=${tf}&limit=3`);
      if (data?.bars?.length) {
        const latest = data.bars[data.bars.length - 1];
        const candle: Candle = {
          time: latest.time ?? latest.t,
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
          else if (candle.time === lastTime) setMarket('currentCandle', candle);
        }
      }
    } catch {}
  }, 15000);
}

export function destroyDataLayer() {
  ws?.destroy();
  if (_barPollInterval) clearInterval(_barPollInterval);
  ws = null;
  _barPollInterval = null;
  msgBuffer = [];
  rafPending = false;
}
