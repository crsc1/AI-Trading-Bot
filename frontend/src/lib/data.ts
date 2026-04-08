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
import { addOptionTrade, type OptionTrade } from '../signals/optionsFlow';
import { updateCvd } from '../signals/flow';
import type { Tick, Candle } from '../types/market';

/**
 * Get today's midnight in Eastern Time as epoch ms.
 * ThetaData ms_of_day is relative to ET midnight, not UTC.
 * EDT = UTC-4, EST = UTC-5. We use a simple offset approach.
 */
let _etMidnightCache: { date: string; ms: number } | null = null;
function getTodayETMidnightMs(): number {
  const now = new Date();
  const todayStr = now.toLocaleDateString('en-US', { timeZone: 'America/New_York' });
  if (_etMidnightCache && _etMidnightCache.date === todayStr) return _etMidnightCache.ms;

  // Create a date at midnight ET by formatting and parsing
  const etNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const etMidnight = new Date(etNow);
  etMidnight.setHours(0, 0, 0, 0);
  // Convert back: the difference between local midnight and ET midnight
  const etOffsetMs = now.getTime() - etNow.getTime();
  const result = etMidnight.getTime() + etOffsetMs;
  _etMidnightCache = { date: todayStr, ms: result };
  return result;
}

let engineWS: WSClient | null = null;
let sipWS: WSClient | null = null;
let tickThrottler: ReturnType<typeof createThrottledUpdater<Tick>> | null = null;
let _barPollInterval: ReturnType<typeof setInterval> | null = null;

/**
 * Load historical candle data from REST API.
 * Retries up to 5 times with backoff if the backend isn't ready yet.
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
    // Wait before retrying: 1s, 2s, 4s, 8s, 16s
    if (attempt < retries - 1) {
      await new Promise(r => setTimeout(r, 1000 * Math.pow(2, attempt)));
    }
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
  // Guard against double-init (Layout calls once, pages may navigate)
  if (engineWS || sipWS) return;

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
    name: 'Engine',
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
      } else if (data.type === 'cvd') {
        updateCvd(
          data.value ?? 0,
          data.delta_1m ?? 0,
          data.delta_5m ?? 0,
        );
      }
    },
    onConnect: () => setConnected(true),
    onDisconnect: () => setConnected(false),
  });

  // SIP WebSocket (dashboard backend) — trades, quotes, bars, theta events
  sipWS = new WSClient({
    name: 'SIP',
    url: `ws://${wsHost}:8000/ws`,
    skipTypes: ['"theta_quote"'],  // Skip ~2,400/sec quote spam before JSON.parse
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
        case 'theta_trade': {
          // Option trade from ThetaData stream
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
            root: data.root ?? 'SPY',
            condition: data.condition ?? 0,
            side: data.side === 'buy' ? 'buy' : data.side === 'sell' ? 'sell' : 'mid',
            iv: data.iv ?? null,
            delta: data.delta ?? null,
            gamma: data.gamma ?? null,
            vpin: data.vpin ?? null,
            sms: data.sms ?? 0,
            tag: 'normal',
            clusterId: null,  // Assigned by addOptionTrade()
            spyPrice: market.lastPrice,  // SPY price at time of trade for bubble chart replay
          };
          if (trade.price > 0 && trade.size > 0) {
            addOptionTrade(trade);
          }
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
      if (!engineWS?.connected) setConnected(true);
      // Only refresh quote on reconnect, not full candle reload (prevents chart drift)
      loadQuote();
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

  // Refresh quote when user returns to the tab (WS may have been throttled)
  // Don't reload candles — pages are permanent, chart stays alive, WS reconnects
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      console.log('[Data] Tab visible — refreshing quote');
      loadQuote();
    } else {
      console.log('[Data] Tab hidden — WS may be throttled by browser');
    }
  });

  // Poll for fresh bars every 15s as fallback when Python stream is idle
  // (Rust engine handles ticks but doesn't push bar aggregations via WS)
  _barPollInterval = setInterval(async () => {
    try {
      const tf = market.timeframe || '5Min';
      const data = await api.get<{ bars: any[] }>(`/api/bars?symbol=SPY&timeframe=${tf}&limit=3`);
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
        // Check if this is a new bar or update to current
        const existing = market.candles;
        if (existing.length > 0) {
          const lastTime = existing[existing.length - 1].time;
          if (candle.time > lastTime) {
            appendCandle(candle);
          } else if (candle.time === lastTime) {
            setMarket('currentCandle', candle);
          }
        }
      }
    } catch {}
  }, 15000);
}

/**
 * Destroy the data layer — clean up WebSockets and throttlers.
 */
export function destroyDataLayer() {
  engineWS?.destroy();
  sipWS?.destroy();
  tickThrottler?.destroy();
  if (_barPollInterval) clearInterval(_barPollInterval);
  engineWS = null;
  sipWS = null;
  tickThrottler = null;
  _barPollInterval = null;
}
