/**
 * Protobuf decoder Web Worker — runs off main thread.
 *
 * Receives binary ArrayBuffers from the WebSocket, decodes them using
 * protobufjs static module, and returns plain JS objects that the main
 * thread can patch into SolidJS stores.
 */
import { expose } from 'comlink';
import { market } from '../proto/compiled/market';

const MarketMessage = market.MarketMessage;
const TradeSide = market.TradeSide;

/** Map protobuf TradeSide enum to string */
function sideStr(side: market.TradeSide | null | undefined): string {
  if (side === TradeSide.SIDE_BUY) return 'buy';
  if (side === TradeSide.SIDE_SELL) return 'sell';
  return 'unknown';
}

/** Convert Long to number (protobufjs uses Long for int64/uint64) */
function num(v: any): number {
  if (v == null) return 0;
  if (typeof v === 'number') return v;
  // Long object from protobufjs
  if (typeof v.toNumber === 'function') return v.toNumber();
  return Number(v);
}

/** Decode a single binary frame into a plain JS object matching the existing message format */
function decode(buffer: ArrayBuffer): any {
  const msg = MarketMessage.decode(new Uint8Array(buffer));
  const kind = msg.payload; // discriminated union: "tick" | "quote" | etc.

  switch (kind) {
    case 'tick': {
      const t = msg.tick!;
      return { type: 'tick', price: t.price, size: num(t.size), side: sideStr(t.side), timestamp: num(t.timestampMs) };
    }
    case 'quote': {
      const q = msg.quote!;
      return { type: 'quote', bid: q.bid, ask: q.ask, bid_size: num(q.bidSize), ask_size: num(q.askSize), timestamp: num(q.timestampMs), symbol: q.symbol };
    }
    case 'candle': {
      const c = msg.candle!;
      return { type: c.isUpdate ? 'bar_update' : 'bar', o: c.open, h: c.high, l: c.low, c: c.close, v: num(c.volume), t: num(c.timestamp), symbol: c.symbol };
    }
    case 'cvd': {
      const d = msg.cvd!;
      return { type: 'cvd', value: num(d.value), delta_1m: num(d.delta1m), delta_5m: num(d.delta5m) };
    }
    case 'footprint': {
      const f = msg.footprint!;
      return { type: 'footprint', bar_time: num(f.barTime), levels: f.levels, total_buy_vol: num(f.totalBuyVol), total_sell_vol: num(f.totalSellVol) };
    }
    case 'sweep': {
      const s = msg.sweep!;
      return { type: 'sweep', price: s.price, size: num(s.size), side: sideStr(s.side), levels_hit: s.levelsHit };
    }
    case 'imbalance': {
      const i = msg.imbalance!;
      return { type: 'imbalance', price: i.price, side: sideStr(i.side), ratio: i.ratio, stacked: i.stacked };
    }
    case 'absorption': {
      const a = msg.absorption!;
      return { type: 'absorption', price: a.price, volume: num(a.volume), side: sideStr(a.side), held: a.held };
    }
    case 'deltaFlip': {
      const d = msg.deltaFlip!;
      return { type: 'delta_flip', from: sideStr(d.from), to: sideStr(d.to), cvd_at_flip: num(d.cvdAtFlip) };
    }
    case 'largeTrade': {
      const l = msg.largeTrade!;
      return { type: 'large_trade', price: l.price, size: num(l.size), side: sideStr(l.side) };
    }
    case 'optionTrade': {
      const o = msg.optionTrade!;
      return {
        type: 'theta_trade', root: o.root, strike: o.strike, right: o.right,
        price: o.price, size: num(o.size), premium: o.premium,
        side: o.side, iv: o.iv, delta: o.delta, gamma: o.gamma,
        vpin: o.vpin, sms: o.sms, expiration: o.expiration,
        exchange: o.exchange, timestamp: num(o.timestampMs) / 1000, // seconds for existing handler
        ms_of_day: num(o.msOfDay), condition: o.condition,
      };
    }
    case 'heartbeat': {
      return { type: 'heartbeat' };
    }
    case 'external': {
      // Python-forwarded events: JSON string inside protobuf wrapper
      try {
        return JSON.parse(msg.external!.json);
      } catch {
        return null;
      }
    }
    default:
      return null;
  }
}

/** Decode a batch of binary frames. Used with RAF gating for bulk processing. */
function decodeBatch(buffers: ArrayBuffer[]): any[] {
  const results: any[] = [];
  for (const buf of buffers) {
    const decoded = decode(buf);
    if (decoded) results.push(decoded);
  }
  return results;
}

expose({ decode, decodeBatch });
