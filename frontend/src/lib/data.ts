/**
 * Data layer — connects WebSocket streams and REST endpoints to SolidJS stores.
 * Call `initDataLayer()` once on app mount.
 */
import { WSClient } from './ws';
import { createThrottledUpdater } from './throttle';
import { api } from './api';
import {
  market,
  setMarket,
  setCandles,
  updateFromTick,
  updateQuote,
  appendCandle,
  setConnected,
} from '../signals/market';
import type { Tick, Candle } from '../types/market';

let engineWS: WSClient | null = null;
let sipWS: WSClient | null = null;
let tickThrottler: ReturnType<typeof createThrottledUpdater<Tick>> | null = null;

/**
 * Load historical candle data from REST API
 */
export async function loadCandles() {
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
    }
  } catch (e) {
    console.warn('[Data] Failed to load candles:', e);
  }
}

/**
 * Load initial quote
 */
async function loadQuote() {
  try {
    const data = await api.getQuote(market.symbol);
    if (data.last) {
      setMarket('lastPrice', data.last);
    }
  } catch (e) {
    console.warn('[Data] Failed to load quote:', e);
  }
}

/**
 * Initialize the data layer — WebSocket connections + initial data load.
 */
export function initDataLayer() {
  // 60fps throttled tick processor
  tickThrottler = createThrottledUpdater<Tick>((batch) => {
    // Apply last tick from each batch (most recent price)
    if (batch.length > 0) {
      updateFromTick(batch[batch.length - 1]);
    }
  });

  // Rust flow engine WebSocket (port 8081) — ticks, signals
  const wsHost = window.location.hostname || 'localhost';
  engineWS = new WSClient({
    url: `ws://${wsHost}:8081/ws`,
    onMessage: (data) => {
      if (data.type === 'Tick' || data.type === 'tick') {
        const tick: Tick = {
          price: data.price ?? data.p,
          size: data.size ?? data.s ?? 0,
          side: data.side ?? 'unknown',
          timestamp_ms: data.timestamp ?? data.t ?? Date.now(),
        };
        tickThrottler?.push(tick);
      }
    },
    onConnect: () => setConnected(true),
    onDisconnect: () => setConnected(false),
  });

  // SIP WebSocket (dashboard backend) — trades, quotes, bars
  sipWS = new WSClient({
    url: `ws://${wsHost}:8000/ws`,
    onMessage: (data) => {
      const type = data.type ?? data.event;
      switch (type) {
        case 'trade': {
          const tick: Tick = {
            price: data.price ?? data.p,
            size: data.size ?? data.s ?? 0,
            side: data.side ?? 'unknown',
            timestamp_ms: data.timestamp ?? data.t ?? Date.now(),
          };
          tickThrottler?.push(tick);
          break;
        }
        case 'quote': {
          updateQuote({
            bid: data.bid ?? data.bp ?? 0,
            ask: data.ask ?? data.ap ?? 0,
            bid_size: data.bid_size ?? data.bs ?? 0,
            ask_size: data.ask_size ?? data.as ?? 0,
            timestamp_ms: data.timestamp ?? Date.now(),
          });
          break;
        }
        case 'bar':
        case 'bar_update': {
          const candle: Candle = {
            time: data.t ?? data.timestamp,
            open: data.o ?? data.open,
            high: data.h ?? data.high,
            low: data.l ?? data.low,
            close: data.c ?? data.close,
            volume: data.v ?? data.volume ?? 0,
          };
          if (type === 'bar') {
            appendCandle(candle);
          } else {
            // Update current candle
            setMarket('currentCandle', candle);
          }
          break;
        }
      }
    },
    onConnect: () => {
      // SIP connected — we can consider this as connected too
      if (!engineWS?.connected) setConnected(true);
    },
    onDisconnect: () => {
      if (!engineWS?.connected) setConnected(false);
    },
  });

  // Connect WebSockets
  engineWS.connect();
  sipWS.connect();

  // Load initial data
  loadCandles();
  loadQuote();
}

/**
 * Destroy the data layer — clean up WebSockets and throttlers.
 */
export function destroyDataLayer() {
  engineWS?.destroy();
  sipWS?.destroy();
  tickThrottler?.destroy();
  engineWS = null;
  sipWS = null;
  tickThrottler = null;
}
