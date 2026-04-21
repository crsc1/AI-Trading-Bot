#!/usr/bin/env python3
"""Full market check — all data sources, all levels, correct quote mapping."""

import json, urllib.request, math, datetime, sys, os

TODAY = datetime.datetime.now().strftime("%Y%m%d")
FLOW = "http://localhost:8081"
THETA = "http://localhost:25503"
POSITIONS_FILE = os.path.expanduser("~/.gstack/trading/positions.json")
IV_HISTORY_FILE = os.path.expanduser("~/.gstack/trading/iv_history.json")

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

# ── Position + IV tracking ──

def load_positions():
    try:
        with open(POSITIONS_FILE) as f:
            return json.load(f)
    except: return []

def save_positions(positions):
    os.makedirs(os.path.dirname(POSITIONS_FILE), exist_ok=True)
    with open(POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=2)

def load_iv_history():
    try:
        with open(IV_HISTORY_FILE) as f:
            return json.load(f)
    except: return {}

def save_iv_history(history):
    os.makedirs(os.path.dirname(IV_HISTORY_FILE), exist_ok=True)
    with open(IV_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

def get_greeks_direct(symbol, expiration, strike, right):
    """Pull greeks for a specific contract via direct query."""
    r = fetch(f"{THETA}/v3/option/snapshot/greeks/first_order?symbol={symbol}&expiration={expiration}&strike={strike}&right={right}")
    if "response" in r and r["response"]:
        g = r["response"][0]
        return {
            "iv": g.get("implied_volatility", 0),
            "delta": g.get("delta", 0),
            "gamma": g.get("gamma", 0),
            "theta": g.get("theta", 0),
            "vega": g.get("vega", 0),
        }
    return None

def get_quote_direct(symbol, expiration, strike, right):
    """Pull quote for a specific contract via direct query."""
    r = fetch(f"{THETA}/v3/option/snapshot/quote?symbol={symbol}&expiration={expiration}&strike={strike}&right={right}")
    if "response" in r and r["response"]:
        q = r["response"][0]
        return {"bid": q.get("bid", 0), "ask": q.get("ask", 0)}
    return None

def track_iv(key, iv, timestamp):
    """Record IV snapshot for a contract. Returns IV history + analysis."""
    history = load_iv_history()
    if key not in history:
        history[key] = []

    history[key].append({"ts": timestamp, "iv": iv})
    # Keep last 60 snapshots
    history[key] = history[key][-60:]
    save_iv_history(history)

    readings = history[key]
    result = {"current": iv, "readings": len(readings)}

    if len(readings) >= 2:
        prev = readings[-2]["iv"]
        result["prev"] = prev
        result["change"] = iv - prev
        result["pct_change"] = ((iv - prev) / prev * 100) if prev > 0 else 0

    if len(readings) >= 5:
        recent5 = [r["iv"] for r in readings[-5:]]
        result["min5"] = min(recent5)
        result["max5"] = max(recent5)
        result["trend5"] = recent5[-1] - recent5[0]

    if len(readings) >= 3:
        # Detect IV expansion vs compression
        ivs = [r["iv"] for r in readings[-3:]]
        if all(ivs[i] > ivs[i-1] for i in range(1, len(ivs))):
            result["state"] = "EXPANDING"
        elif all(ivs[i] < ivs[i-1] for i in range(1, len(ivs))):
            result["state"] = "COMPRESSING"
        else:
            result["state"] = "MIXED"
    else:
        result["state"] = "UNKNOWN"

    return result

def check_positions(spot):
    """Check all tracked positions with greeks + IV tracking."""
    positions = load_positions()
    if not positions:
        return

    ts = datetime.datetime.now().isoformat()
    active = []

    print(f"\n  {'='*50}")
    print(f"  OPEN POSITIONS")
    print(f"  {'='*50}")

    for pos in positions:
        sym = pos.get("symbol", "SPY")
        strike = pos.get("strike")
        right = pos.get("right", "call")
        entry = pos.get("entry_price", 0)
        right_param = "call" if right.upper() in ["C", "CALL"] else "put"

        # Get current quote
        quote = get_quote_direct(sym, TODAY, strike, right_param)
        if not quote or quote["bid"] <= 0:
            print(f"  {sym} {strike}{'C' if right_param=='call' else 'P'}: no quote (expired?)")
            continue

        bid = quote["bid"]
        pnl = bid - entry
        pnl_pct = (pnl / entry * 100) if entry > 0 else 0

        # Get greeks
        greeks = get_greeks_direct(sym, TODAY, strike, right_param)

        # Track IV
        key = f"{sym}_{strike}_{right_param}_{TODAY}"
        iv_info = None
        if greeks and greeks["iv"] > 0:
            iv_info = track_iv(key, greeks["iv"], ts)

        # Print
        r_label = "C" if right_param == "call" else "P"
        print(f"\n  {sym} {strike}{r_label} @ ${entry:.2f} → bid ${bid:.2f}  P/L: ${pnl:+.2f} ({pnl_pct:+.0f}%)")

        if greeks:
            intrinsic = max(spot - strike, 0) if right_param == "call" else max(strike - spot, 0)
            extrinsic = bid - intrinsic
            print(f"    IV: {greeks['iv']*100:.1f}%  Δ:{greeks['delta']:.3f}  θ:${greeks['theta']:.2f}/min  ν:${greeks['vega']:.3f}/1%IV")
            print(f"    Intrinsic: ${intrinsic:.2f}  Extrinsic: ${extrinsic:.2f}")

        if iv_info:
            state_icon = "📈" if iv_info["state"] == "EXPANDING" else ("📉" if iv_info["state"] == "COMPRESSING" else "〰")
            print(f"    IV {iv_info['state']} {state_icon} ({iv_info['current']*100:.1f}%", end="")
            if "change" in iv_info:
                print(f", chg: {iv_info['change']*100:+.1f}%", end="")
            if "trend5" in iv_info:
                print(f", 5-check trend: {iv_info['trend5']*100:+.1f}%", end="")
            print(")")

            # Vega impact analysis
            if greeks and "change" in iv_info and greeks["vega"] > 0:
                vega_impact = iv_info["change"] * 100 * greeks["vega"]
                print(f"    Vega P/L impact: ${vega_impact:+.2f} from IV move")

            # Alert on big IV moves
            if iv_info.get("pct_change", 0) > 10:
                print(f"    ** IV SPIKE +{iv_info['pct_change']:.0f}% — vega working FOR you **")
            elif iv_info.get("pct_change", 0) < -10:
                print(f"    ** IV CRUSH {iv_info['pct_change']:.0f}% — vega working AGAINST you **")

        active.append(pos)

    # Clean up expired
    save_positions(active)

def get_multi_day_levels():
    """Pull prior day and weekly levels from ThetaData EOD history."""
    today = datetime.datetime.now()
    start = (today - datetime.timedelta(days=7)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    hist = fetch(f"{THETA}/v3/stock/history/eod?symbol=SPY&start_date={start}&end_date={end}")

    lvls = {}
    if "response" not in hist or not hist["response"]:
        return lvls

    rows = hist["response"]

    # Previous day (last row that isn't today)
    today_int = int(today.strftime("%Y%m%d"))
    prior_days = [r for r in rows if r.get("date", 0) < today_int]

    if prior_days:
        prev = prior_days[-1]
        lvls["Prev Close"] = prev["close"]
        lvls["Prev High"] = prev["high"]
        lvls["Prev Low"] = prev["low"]

    # 2 days ago
    if len(prior_days) >= 2:
        d2 = prior_days[-2]
        lvls["2D Low"] = d2["low"]
        lvls["2D High"] = d2["high"]

    # Week high/low
    if len(prior_days) >= 3:
        week_high = max(r["high"] for r in prior_days[-5:])
        week_low = min(r["low"] for r in prior_days[-5:])
        lvls["Week High"] = week_high
        lvls["Week Low"] = week_low

    # Round numbers near spot
    # (added dynamically based on spot later)

    return lvls

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

# ── 2.5 Position + IV tracking ──
check_positions(s)

# ── 2.6 ATM IV monitor (track IV near spot even without a position) ──
atm_strike = int(round(s))
ts_now = datetime.datetime.now().isoformat()
iv_readings = {}
for offset in [-1, 0, 1]:
    strike = atm_strike + offset
    for right in ["call", "put"]:
        g = get_greeks_direct("SPY", TODAY, strike, right)
        if g and g["iv"] > 0:
            key = f"SPY_{strike}_{right}_{TODAY}"
            iv_info = track_iv(key, g["iv"], ts_now)
            label = f"{strike}{'C' if right=='call' else 'P'}"
            iv_readings[label] = iv_info

# Print IV environment
expanding = sum(1 for v in iv_readings.values() if v.get("state") == "EXPANDING")
compressing = sum(1 for v in iv_readings.values() if v.get("state") == "COMPRESSING")
if iv_readings:
    if expanding > compressing + 2:
        print(f"\n  IV ENVIRONMENT: EXPANDING ({expanding} expanding, {compressing} compressing)")
        print(f"  Vega is your friend — options gain value from IV alone")
    elif compressing > expanding + 2:
        print(f"\n  IV ENVIRONMENT: COMPRESSING ({compressing} compressing, {expanding} expanding)")
        print(f"  Vega crush — options lose value even if direction is right")
    else:
        # Show ATM IV level
        atm_ivs = [v["current"] for v in iv_readings.values() if "current" in v]
        if atm_ivs:
            avg_iv = sum(atm_ivs) / len(atm_ivs) * 100
            print(f"\n  IV: {avg_iv:.1f}% avg ATM", end="")
            trends = [v.get("trend5", 0) for v in iv_readings.values() if "trend5" in v]
            if trends:
                avg_trend = sum(trends) / len(trends) * 100
                if abs(avg_trend) > 0.5:
                    print(f" (trending {avg_trend:+.1f}%)", end="")
            print()

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

# GEX levels
for strike, gex in gex_map.items():
    if abs(gex / 1e6) > 5 and abs(strike - s) <= 10:
        tag = "SUP" if gex > 0 else "RES"
        levels[f"GEX {tag} {strike}"] = float(strike)

# OI walls
for k, v in sorted(oi_walls.items(), key=lambda x: x[1], reverse=True)[:6]:
    levels[f"OI {v:,} {k}"] = float(int(k[:-1]))

# Multi-day levels (prev close, prev high/low, week high/low)
multi_day = get_multi_day_levels()
for name, price in multi_day.items():
    if abs(price - s) <= 15:  # only show if within $15
        levels[name] = price

# Round numbers near spot
for rnd in range(int(s) - 10, int(s) + 11, 5):
    if rnd % 5 == 0 and abs(rnd - s) <= 10:
        levels[f"${rnd} round"] = float(rnd)

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

# ── MOMENTUM DETECTION: CVD recovery, volume spikes, consolidation ──
momentum_signals = []
momentum_score = 0  # adds to bull/bear score

if isinstance(candles, list) and len(candles) >= 5:
    last5 = candles[-5:]
    last10 = candles[-10:] if len(candles) >= 10 else candles

    # 1. CVD rate of change over last 5 candles
    cvd_start = last5[0]["cvd"]
    cvd_end = last5[-1]["cvd"]
    cvd_roc = cvd_end - cvd_start
    if cvd_roc > 30000:
        momentum_signals.append(f"CVD RECOVERY +{cvd_roc:,} in {len(last5)} candles — accumulation")
        momentum_score += 1
    elif cvd_roc < -30000:
        momentum_signals.append(f"CVD DUMP {cvd_roc:,} in {len(last5)} candles — distribution")
        momentum_score -= 1

    # 2. Volume spike detection (candle vol > 2x average of prior candles)
    if len(candles) >= 6:
        avg_vol = sum(c["volume"] for c in candles[-6:-1]) / 5
        latest_vol = candles[-1]["volume"]
        if latest_vol > avg_vol * 2 and avg_vol > 0:
            spike_bs = candles[-1]["buy_volume"] / candles[-1]["sell_volume"] if candles[-1]["sell_volume"] else 99
            if spike_bs > 1.2:
                momentum_signals.append(f"BUY VOLUME SPIKE {latest_vol:,} vs avg {avg_vol:,.0f} (B/S:{spike_bs:.2f})")
                momentum_score += 1
            elif spike_bs < 0.8:
                momentum_signals.append(f"SELL VOLUME SPIKE {latest_vol:,} vs avg {avg_vol:,.0f} (B/S:{spike_bs:.2f})")
                momentum_score -= 1

    # 3. Consolidation after push (bull flag / bear flag)
    # Look for: 2+ candle push followed by 3+ candles of tight range that hold gains
    if len(last10) >= 7:
        # Check last 7 candles: first 2 = push, next 5 = consolidation
        push = last10[-7:-5]
        consol = last10[-5:]

        # Bull flag: push up + consolidation holds above push open
        push_move = push[-1]["close"] - push[0]["open"]
        consol_low = min(c["low"] for c in consol)
        consol_high = max(c["high"] for c in consol)
        consol_range = consol_high - consol_low
        push_range = max(c["high"] for c in push) - min(c["low"] for c in push)

        if push_move > 0.20 and consol_low >= push[0]["open"] and consol_range < push_range * 0.7:
            momentum_signals.append(f"BULL FLAG: +${push_move:.2f} push, consolidating ${consol_low:.2f}-${consol_high:.2f} (holding gains)")
            momentum_score += 1.5

        # Bear flag: push down + consolidation stays below push open
        if push_move < -0.20 and consol_high <= push[0]["open"] and consol_range < abs(push_range) * 0.7:
            momentum_signals.append(f"BEAR FLAG: ${push_move:.2f} push, consolidating ${consol_low:.2f}-${consol_high:.2f} (holding losses)")
            momentum_score -= 1.5

    # 4. Consecutive green/red candles with building B/S
    greens = 0
    reds = 0
    for c in reversed(last5):
        if c["close"] > c["open"]: greens += 1
        else: break
    for c in reversed(last5):
        if c["close"] < c["open"]: reds += 1
        else: break

    if greens >= 3:
        bs_improving = all(
            (last5[-i]["buy_volume"] / last5[-i]["sell_volume"] if last5[-i]["sell_volume"] else 0) >=
            (last5[-i-1]["buy_volume"] / last5[-i-1]["sell_volume"] if last5[-i-1]["sell_volume"] else 0)
            for i in range(1, min(greens, 3))
        )
        momentum_signals.append(f"{greens} GREEN candles{' + B/S improving' if bs_improving else ''}")
        momentum_score += 0.5

    if reds >= 3:
        momentum_signals.append(f"{reds} RED candles")
        momentum_score -= 0.5

if momentum_signals:
    print(f"\n  MOMENTUM:")
    for sig in momentum_signals:
        direction = "▲" if "RECOVERY" in sig or "BUY" in sig or "BULL" in sig or "GREEN" in sig else ("▼" if "DUMP" in sig or "SELL" in sig or "BEAR" in sig or "RED" in sig else "·")
        print(f"    {direction} {sig}")
    print(f"    Score: {momentum_score:+.1f}")

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

    # ── Signal scoring: 2 of 3 confirms = entry ──
    # Bullish confirms: green candle, B/S > 1.0, 1m delta > 0
    # Bearish confirms: red candle, B/S < 1.0, 1m delta < 0
    bull_score = (1 if body > 0 else 0) + (1 if lbs > 1.0 else 0) + (1 if d1 > 0 else 0)
    bear_score = (1 if body < 0 else 0) + (1 if lbs < 1.0 else 0) + (1 if d1 < 0 else 0)

    # Strength bonus for strong readings
    if lbs > 1.5: bull_score += 0.5
    if lbs < 0.6: bear_score += 0.5
    if d1 > 10000: bull_score += 0.5
    if d1 < -10000: bear_score += 0.5

    # Momentum score from candle pattern analysis
    if momentum_score > 0: bull_score += momentum_score
    if momentum_score < 0: bear_score += abs(momentum_score)

    # Phase adjustment
    min_score = 1.5 * phase_mult  # normally 1.5, lunch needs 3.75

    def print_entries(direction):
        spy_strike = int(round(s))
        spx_approx = int(round(s * 10))
        right = "P" if direction == "PUTS" else "C"
        tgt = below[0] if direction == "PUTS" else (above[0] if above else None)
        stop_dir = 0.30 if direction == "PUTS" else -0.30

        print(f"  ═══ {direction} ═══")
        # SPY ATM
        if spy_strike in spy_chain and right in spy_chain[spy_strike]:
            e = spy_chain[spy_strike][right]
            if 0.01 < e["ask"] < 20: print(f"    SPY {spy_strike}{right} ${e['bid']:.2f}/${e['ask']:.2f}")
        # SPY 1 strike OTM
        otm = spy_strike + (1 if direction == "CALLS" else -1)
        if otm in spy_chain and right in spy_chain[otm]:
            e = spy_chain[otm][right]
            if 0.01 < e["ask"] < 20: print(f"    SPY {otm}{right} ${e['bid']:.2f}/${e['ask']:.2f}")
        # SPXW nearest ATM
        spx_entries = sorted(
            [(k, v[right]) for k, v in spx_chain.items() if right in v and v[right]["bid"] > 0 and 0.10 < v[right]["ask"] < 50 and abs(k - spx_approx) <= 30],
            key=lambda x: abs(x[0] - spx_approx)
        )
        for strike, e in spx_entries[:3]:
            print(f"    SPXW {strike}{right} ${e['bid']:.2f}/${e['ask']:.2f}")
        if tgt:
            stop = near[1] + stop_dir
            print(f"    Target: {tgt[0]} ${tgt[1]:.2f}  Stop: ${stop:.2f}  Time: 15m")

    # ── Breakout signal: price above session high or below session low ──
    breakout_up = s > hi - 0.05 and s > vwap and body > 0
    breakdown = s < lo + 0.05 and s < vwap and body < 0

    if near:
        print(f"  AT: {near[0]} ${near[1]:.2f}  [bull:{bull_score:.1f} bear:{bear_score:.1f} need:{min_score:.1f}]")

    if breakout_up and bull_score >= 1.5:
        print(f"  ** BREAKOUT ABOVE SESSION HIGH **")
        print_entries("CALLS")
    elif breakdown and bear_score >= 1.5:
        print(f"  ** BREAKDOWN BELOW SESSION LOW **")
        print_entries("PUTS")
    elif near and bear_score >= min_score:
        print(f"  REJECTION at {near[0]}")
        print_entries("PUTS")
    elif near and bull_score >= min_score:
        print(f"  BOUNCE off {near[0]}")
        print_entries("CALLS")
    elif near:
        # Show what's missing
        if bull_score > bear_score:
            missing = []
            if body <= 0: missing.append("green candle")
            if lbs <= 1.0: missing.append("B/S>1.0")
            if d1 <= 0: missing.append("1m delta+")
            print(f"  leaning calls but need: {', '.join(missing)}")
        elif bear_score > bull_score:
            missing = []
            if body >= 0: missing.append("red candle")
            if lbs >= 1.0: missing.append("B/S<1.0")
            if d1 >= 0: missing.append("1m delta-")
            print(f"  leaning puts but need: {', '.join(missing)}")
        else:
            print(f"  no lean — dead even")
    else:
        print(f"  no level nearby")

    # ── VWAP band bounce/rejection (even if not at a named level) ──
    if not near and not breakout_up and not breakdown:
        if abs(s - vwap_l) < 0.20 and bull_score >= 1.5:
            print(f"\n  VWAP LOWER BAND BOUNCE ${vwap_l:.2f}")
            print_entries("CALLS")
        elif abs(s - vwap_u) < 0.20 and bear_score >= 1.5:
            print(f"\n  VWAP UPPER BAND REJECTION ${vwap_u:.2f}")
            print_entries("PUTS")
        elif above and below:
            print(f"\n  Between {below[0][0]} ${below[0][1]:.2f} and {above[0][0]} ${above[0][1]:.2f}")

elif above and below:
    print(f"  Between {below[0][0]} ${below[0][1]:.2f} and {above[0][0]} ${above[0][1]:.2f}")
else:
    print(f"  no setup")
