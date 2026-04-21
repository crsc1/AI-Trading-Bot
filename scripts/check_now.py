#!/usr/bin/env python3
"""Full market check — all data sources, all levels, correct quote mapping."""

import json, urllib.request, math, datetime, sys

TODAY = datetime.datetime.now().strftime("%Y%m%d")
FLOW = "http://localhost:8081"
THETA = "http://localhost:25503"

def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def bs_gamma(S, K, T, iv):
    if T <= 0 or iv <= 0 or S <= 0: return 0.0
    d1 = (math.log(S / K) + (0.5 * iv * iv) * T) / (iv * math.sqrt(T))
    return math.exp(-0.5 * d1 * d1) / (S * iv * math.sqrt(2 * math.pi * T))

def build_chain(symbol):
    """Build properly mapped chain: strike -> {C: {bid, ask, oi}, P: {bid, ask, oi}}"""
    strikes = fetch(f"{THETA}/v3/option/list/strikes?symbol={symbol}&expiration={TODAY}")
    if "response" not in strikes: return {}, []
    strike_list = [int(s) for s in strikes["response"]]

    calls = fetch(f"{THETA}/v3/option/snapshot/quote?symbol={symbol}&expiration={TODAY}&strike=0&right=call")
    puts = fetch(f"{THETA}/v3/option/snapshot/quote?symbol={symbol}&expiration={TODAY}&strike=0&right=put")
    call_oi = fetch(f"{THETA}/v3/option/snapshot/open_interest?symbol={symbol}&expiration={TODAY}&strike=0&right=call")
    put_oi = fetch(f"{THETA}/v3/option/snapshot/open_interest?symbol={symbol}&expiration={TODAY}&strike=0&right=put")
    greeks_c = fetch(f"{THETA}/v3/option/snapshot/greeks/first_order?symbol={symbol}&expiration={TODAY}&strike=0&right=call")
    greeks_p = fetch(f"{THETA}/v3/option/snapshot/greeks/first_order?symbol={symbol}&expiration={TODAY}&strike=0&right=put")

    cq = calls.get("response", [])
    pq = puts.get("response", [])
    co = call_oi.get("response", [])
    po = put_oi.get("response", [])
    gc = greeks_c.get("response", [])
    gp = greeks_p.get("response", [])

    chain = {}
    for i, strike in enumerate(strike_list):
        chain[strike] = {}
        if i < len(cq):
            chain[strike]["C"] = {
                "bid": cq[i].get("bid", 0), "ask": cq[i].get("ask", 0),
                "oi": co[i].get("open_interest", 0) if i < len(co) else 0,
                "iv": gc[i].get("implied_volatility", 0) if i < len(gc) else 0,
            }
        if i < len(pq):
            chain[strike]["P"] = {
                "bid": pq[i].get("bid", 0), "ask": pq[i].get("ask", 0),
                "oi": po[i].get("open_interest", 0) if i < len(po) else 0,
                "iv": gp[i].get("implied_volatility", 0) if i < len(gp) else 0,
            }
    return chain, strike_list

# ── 1. Flow state ──
f = fetch(f"{FLOW}/flow-state")
if "error" in f:
    print("Flow engine not responding"); sys.exit(1)

s = f["last_price"]; vwap = f["vwap"]; vwap_u = f["vwap_upper"]; vwap_l = f["vwap_lower"]
rsi = f["rsi"]; vpoc = f["vpoc"]; cvd = f["cvd"]; d1 = f["delta_1m"]; d5 = f["delta_5m"]
hi = f["session_high"]; lo = f["session_low"]
bs = f["total_buy_vol"] / f["total_sell_vol"] if f["total_sell_vol"] else 0
phase = f["market_phase"]; phase_mult = f["phase_confidence_mult"]; regime = f["regime"]

now = datetime.datetime.now()
hrs = max((now.replace(hour=15, minute=0, second=0) - now).total_seconds() / 3600, 0)
T = hrs / (252 * 6.5) if hrs > 0 else 0.001

# ── 2. Candles ──
candles = fetch(f"{FLOW}/candles?last=5")
last = candles[-1] if isinstance(candles, list) and candles else None

# ── 3. SPY chain (correct mapping) ──
spy_chain, spy_strikes = build_chain("SPY")

# ── 4. SPXW chain (correct mapping) ──
spx_chain, spx_strikes = build_chain("SPXW")

# ── 5. GEX + OI walls from SPY ──
gex_map = {}
oi_walls = {}
for strike, data in spy_chain.items():
    for right in ["C", "P"]:
        if right not in data: continue
        d = data[right]
        oi = d["oi"]; iv = d["iv"]
        gamma = bs_gamma(s, strike, T, iv) if 0 < iv < 5 else 0.0
        sign = 1 if right == "C" else -1
        gex_map[strike] = gex_map.get(strike, 0) + oi * gamma * 100 * s * sign
        if oi >= 2000 and abs(strike - s) <= 10:
            oi_walls[f"{strike}{right}"] = oi

# ── 6. All levels ──
levels = {"VWAP": vwap, "VWAP+σ": vwap_u, "VWAP-σ": vwap_l, "VPOC": vpoc, "Hi": hi, "Lo": lo}
for strike, gex in gex_map.items():
    if abs(gex / 1e6) > 5 and abs(strike - s) <= 10:
        tag = "SUP" if gex > 0 else "RES"
        levels[f"GEX {tag} {strike}"] = float(strike)
for k, v in sorted(oi_walls.items(), key=lambda x: x[1], reverse=True)[:6]:
    levels[f"OI {v:,} {k}"] = float(int(k[:-1]))

above = sorted([(n, p) for n, p in levels.items() if p > s + 0.08], key=lambda x: x[1])
below = sorted([(n, p) for n, p in levels.items() if p < s - 0.08], key=lambda x: x[1], reverse=True)

# ── PRINT ──
print(f"{'=' * 55}")
print(f"  SPY ${s:.2f}  |  {phase}  |  {hrs:.1f}h")
print(f"{'=' * 55}")
print(f"  VWAP ${vwap:.2f} [${vwap_l:.2f}—${vwap_u:.2f}]  RSI {rsi:.0f}  VPOC ${vpoc:.2f}")
print(f"  CVD {cvd:+,}  1m {d1:+,}  5m {d5:+,}  B/S {bs:.2f}  {regime}")
print(f"\n  Above: {', '.join(f'{n} ${p:.2f}' for n, p in above[:4])}")
print(f"  >>> ${s:.2f}")
print(f"  Below: {', '.join(f'{n} ${p:.2f}' for n, p in below[:4])}")

if last:
    ts = datetime.datetime.fromtimestamp(last["ts"]).strftime("%H:%M")
    lbs = last["buy_volume"] / last["sell_volume"] if last["sell_volume"] else 99
    body = last["close"] - last["open"]
    print(f"\n  Candle: {ts} {last['open']:.2f}→{last['close']:.2f} H{last['high']:.2f} L{last['low']:.2f} B/S:{lbs:.2f} {'▲' if body > 0 else '▼'}")

# ── ENTRY LOGIC ──
NEAR = 0.20
near = None
for n, p in levels.items():
    if abs(s - p) <= NEAR:
        near = (n, p)

print()
if near and last:
    body = last["close"] - last["open"]
    lbs = last["buy_volume"] / last["sell_volume"] if last["sell_volume"] else 99
    bt = 0.8 * phase_mult
    bth = 1.2 / phase_mult if phase_mult > 0 else 1.2
    dt = 5000 * phase_mult

    print(f"  AT: {near[0]} ${near[1]:.2f}")

    def find_entry(chain, spot, right, max_dist=20):
        """Find ATM option from properly mapped chain."""
        spot_rounded = int(round(spot)) if right == "C" or right == "P" else int(round(spot / 5) * 5)
        candidates = []
        for strike, data in chain.items():
            if right not in data: continue
            d = data[right]
            if d["bid"] <= 0 or d["ask"] <= 0.01: continue
            if d["ask"] > 50: continue  # skip deep ITM
            dist = abs(strike - (spot if "SPY" in str(strike) else spot * 10))
            candidates.append((strike, d, dist))
        # For SPX, adjust distance calc
        return sorted(candidates, key=lambda x: x[2])

    if body < 0 and lbs < bt and d1 < -dt:
        tgt = below[0] if below else None
        spy_strike = int(round(s))
        spx_approx = int(round(s * 10))

        print(f"  ═══ PUTS ═══")
        # SPY
        if spy_strike in spy_chain and "P" in spy_chain[spy_strike]:
            p = spy_chain[spy_strike]["P"]
            if p["bid"] > 0: print(f"    SPY {spy_strike}P ${p['bid']:.2f}/${p['ask']:.2f}")
        # SPXW — find nearest ATM
        spx_puts = sorted(
            [(k, v["P"]) for k, v in spx_chain.items() if "P" in v and v["P"]["bid"] > 0 and 0.10 < v["P"]["ask"] < 50 and abs(k - spx_approx) <= 30],
            key=lambda x: abs(x[0] - spx_approx)
        )
        for strike, p in spx_puts[:3]:
            print(f"    SPXW {strike}P ${p['bid']:.2f}/${p['ask']:.2f}")
        if tgt: print(f"    Target: {tgt[0]} ${tgt[1]:.2f}  Stop: ${near[1] + 0.30:.2f}  Time: 15m")

    elif body > 0 and lbs > bth and d1 > dt:
        tgt = above[0] if above else None
        spy_strike = int(round(s))
        spx_approx = int(round(s * 10))

        print(f"  ═══ CALLS ═══")
        # SPY
        if spy_strike in spy_chain and "C" in spy_chain[spy_strike]:
            c = spy_chain[spy_strike]["C"]
            if c["bid"] > 0: print(f"    SPY {spy_strike}C ${c['bid']:.2f}/${c['ask']:.2f}")
        # SPXW
        spx_calls = sorted(
            [(k, v["C"]) for k, v in spx_chain.items() if "C" in v and v["C"]["bid"] > 0 and 0.10 < v["C"]["ask"] < 50 and abs(k - spx_approx) <= 30],
            key=lambda x: abs(x[0] - spx_approx)
        )
        for strike, c in spx_calls[:3]:
            print(f"    SPXW {strike}C ${c['bid']:.2f}/${c['ask']:.2f}")
        if tgt: print(f"    Target: {tgt[0]} ${tgt[1]:.2f}  Stop: ${near[1] - 0.30:.2f}  Time: 15m")

    else:
        print(f"  no confirmation (B/S:{lbs:.2f} {'G' if body > 0 else 'R'} 1m:{d1:+,})")
elif above and below:
    print(f"  Between {below[0][0]} ${below[0][1]:.2f} and {above[0][0]} ${above[0][1]:.2f}")
else:
    print(f"  no setup")
