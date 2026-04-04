# AI Trading Bot — Comprehensive Trading Domain Audit
**Date:** March 27, 2026
**Auditor:** Expert in Institutional Order Flow, Market Microstructure, Options Greeks
**Status:** DETAILED FINDINGS WITH CRITICAL SECURITY ISSUES IDENTIFIED

---

## EXECUTIVE SUMMARY

This is a **WORKING PROTOTYPE** with **SOUND DOMAIN LOGIC** but **CRITICAL SECURITY VULNERABILITIES** that must be addressed before any real-money deployment.

**Domain Correctness:** 7/10 (Good logic, minor edge cases)
**Security Posture:** 2/10 (Multiple critical exposures)
**Production Readiness:** 1/10 (Unsafe as-is)

---

## 1. ORDER FLOW CLASSIFICATION — `dashboard/orderflow_api.py`

### PASS ✓

**Tick Rule Implementation:** CORRECT
- Lines 518-523: Buy/sell classification uses proper tick rule logic
  - `if price > prev_price → buy` (aggressor lifted ask)
  - `if price < prev_price → sell` (aggressor hit bid)
  - `if price == prev_price → inherit previous` (Lee-Ready tie-break)
- **Domain correctness:** Matches Hasbrouck & Seppi (1992) tick rule exactly

**VWAP for Bubble Placement:** CORRECT
- Lines 289-291: VWAP calculation from OHLC bars
  - Formula: `vwap = bar.get("vw", 0) or round((o + h + l + c) / 4, 2)`
  - Uses Alpaca's native VWAP (`vw` field) when available
  - Falls back to typical price average (acceptable simplification)
- **Edge case:** Correctly handles missing VWAP by computing from OHLC

**Volume Cloud Aggregation:** CORRECT (WITH NOTES)
- Lines 264-355: `_bars_to_clouds()` correctly:
  - Creates one bubble per bar at VWAP (avoids vertical stacking)
  - Calculates buy/sell split from close position in bar range
  - Uses buy_ratio formula (line 316): `buy_ratio = 0.5 + min(max(vwap_offset, -0.25), 0.25)`
    - Bounds check prevents outliers
    - Weighting approach is reasonable (not strictly tick rule but defensible)
  - Aggregation logic is sound: no double-counting, proper bucketing

**Minor Issue:** Buy/sell split in OHLCV bars is *heuristic-based* (close position), not strict tick classification. This is acceptable for visualization but differs from true order flow analysis.

---

## 2. SIGNAL ENGINE & CONFLUENCE — `dashboard/signal_engine.py` + `dashboard/confluence.py`

### PASS ✓ (With Caveats)

**Confluence Framework Logic:** SOUND
- Lines 412-500+ in confluence.py: 16-factor composite scoring
  - Each factor weighted: `order_flow_imbalance (1.5), cvd_divergence (1.0), gex_alignment (1.5), ...`
  - Max total weight: 14.75 points
  - Scaling is transparent: higher weight = higher importance
- **Confidence tiers:**
  - `TIER_TEXTBOOK = 0.80` (8/10 setup)
  - `TIER_HIGH = 0.60` (6/10 setup)
  - `TIER_VALID = 0.45` (4.5/10 setup)
  - **Weighting makes sense:** TEXTBOOK (2% of account), VALID (0.75% of account)

**3:00 PM Hard Stop for 0DTE Options:** CORRECT
- Line 81 in confluence.py: `ZERO_DTE_HARD_STOP = dt_time(15, 0)`
- Session context (lines 385-388): Correctly detects `past_hard_stop` after 3 PM ET
- **Reasoning:** 0DTE options decay faster, gamma risk escalates post-3 PM, exit liquidity deteriorates — standard institutional practice
- **Implementation:** Properly blocks NO_TRADE signals and generates reasoning (lines 427-428)

**Confluence Factor Weightings — ARE THESE REASONABLE?**
- ✓ Large weights (1.5) for GEX/DEX alignment + order flow imbalance — directional catalysts
- ✓ Medium weights (1.0) for CVD divergence, VWAP rejection, delta regime — structural validation
- ✓ Small weights (0.5) for volume spike, PCR, max pain — secondary confirmations
- ✓ NEW v5 addition: agent_consensus (1.5) — multi-agent validation is strong

**Signal Generation Logic:** SOUND
- Lines 223-250 in signal_engine.py: Full pipeline
  1. Validates minimum data (5+ trades)
  2. Computes market levels (VWAP, pivots, ATR) ✓
  3. Analyzes order flow ✓
  4. Gets session context + event calendar ✓
  5. Computes GEX/DEX, vanna/charm, regime ✓
  6. Evaluates confluence (16 factors) ✓
  7. Selects strike and calculates risk ✓

**Edge Case:** Lines 206-210: Regime detection, event context, and agent verdicts are *cached from signal_api layer* rather than recomputed. This is reasonable for performance but creates dependency on signal_api initialization.

---

## 3. GEX/DEX ENGINE — `dashboard/gex_engine.py`

### PASS ✓ (Formulas Correct)

**GEX Calculation — Formula Correct**
- Line 141: `gex = oi * gamma * spot * spot * 0.01 * CONTRACT_MULT`
- **Verification:**
  - GEX = OI × Γ × S² × 0.01 × 100 (contract multiplier)
  - Standard gamma exposure formula from market-maker hedging literature
  - ✓ Accounts for spot squared (convexity effect)
  - ✓ Uses 0.01 conversion (per-$1 move normalized)
  - ✓ Dealer SHORT call → positive GEX (accurate)

**DEX Calculation — Correct**
- Line 148: `dex = oi * delta_val * CONTRACT_MULT`
- ✓ Standard aggregate delta exposure formula
- ✓ Call delta stays positive (dealers short → negative delta, but code correctly aggregates)

**Put GEX Handling — Correct Sign**
- Line 164: `gex = -oi * gamma * spot * spot * 0.01 * CONTRACT_MULT`
- ✓ Dealers SHORT puts → negative gamma exposure (sign flip is correct)
- ✓ Put GEX aggregation correctly nets with call GEX

**GEX Flip Level — Sound**
- Lines 221-250: Linear interpolation between strikes to find zero crossing
- ✓ Identifies price level where aggregate dealer gamma flips positive/negative
- ✓ Interpolation prevents gaps

**Regime Classification — Correct**
- Lines 205-216:
  - `positive GEX` (net_gex > 0) = dealers short gamma = dampening regime
  - `negative GEX` (net_gex < 0) = dealers long gamma = amplifying regime
  - Regime strength normalized by total absolute GEX (0-1 scale)
- ✓ Matches dealer positioning literature

---

## 4. FLOW TOXICITY (VPIN) — `dashboard/flow_toxicity.py`

### PASS ✓ (Algorithm Academically Sound)

**VPIN Formula — Correct per Easley, Lopez de Prado, O'Hara (2012)**
- Lines 69-201: Volume-bucketed VPIN implementation
- **Algorithm:**
  1. Divide trades into equal-sized *volume* buckets (1000 shares each, line 37)
  2. Classify each trade as buy/sell using Lee-Ready (line 163-184)
  3. For each bucket: compute `|buy_vol - sell_vol|` (line 152)
  4. VPIN = mean(bucket imbalances) / bucket_size (line 201)

**Verification:**
- ✓ Uses volume bars, not time bars (correct per paper)
- ✓ Lee-Ready classification (lines 178-184):
  - Trade at ask → 100% buy
  - Trade at bid → 0% buy
  - Trade between bid/ask → linear interpolation by price level
  - Falls back to 50/50 split when no quote data
- ✓ Bucket overflow handling (lines 138-161): Proportional carryover prevents bias

**VPIN Thresholds — Reasonable**
- Line 39-40: `VPIN_HIGH_THRESHOLD = 0.70, ELEVATED = 0.50`
- Based on empirical research (Easley et al. found >0.7 predicts informed trading)
- ✓ Normal range: 0.2-0.4 (matches academic baseline for SPY)

**Confluence Scoring:** Lines 272-300
- High VPIN + aligned direction → +0.5 points (max)
- High VPIN + conflicted direction → reduce size
- Low VPIN → neutral
- ✓ Weighting is sensible (0.5 max prevents overfit to single signal)

---

## 5. MARKET LEVELS — `dashboard/market_levels.py`

### PASS ✓ (With Minor Edge Case)

**VWAP with Standard Deviation Bands — Correct**
- Lines 151-175: Proper formula
  - `VWAP = Σ(tp × v) / Σ(v)` where tp = (H+L+C)/3
  - Variance = E[TP²] - E[TP]² (standard formula)
  - σ = sqrt(variance)
  - Bands: ±1σ, ±2σ, ±3σ
- ✓ Mathematically sound

**Pivot Point Formulas — All Correct**
- Lines 130-138: Classic pivot point formulas
  - Pivot = (H + L + C) / 3 ✓
  - R1 = 2×Pivot - L ✓
  - S1 = 2×Pivot - H ✓
  - R2 = Pivot + (H - L) ✓
  - S2 = Pivot - (H - L) ✓
  - R3 = H + 2×(Pivot - L) ✓
  - S3 = L - 2×(H - Pivot) ✓

**Opening Range (ORB) — Correct**
- Lines 179-186: First 5/15 bars = first 5/15 minutes of trading
- ✓ Proper time-windowed high/low

**ATR Calculation — Correct**
- Lines 219-230:
  - TR = max(H - L, |H - PC|, |L - PC|) ✓
  - ATR = SMA(TR, 14) ✓
  - 5-min ATR estimated as 1-min ATR × 2.236 (√5 scaling)
  - Note: 2.236 is sqrt(5), correct for time-squared scaling

**Minor Issue — Line 196:**
```python
price_key = round(bar.get("vwap", bar.get("close", 0)) * 4) / 4
```
POC is computed using VWAP rounded to nearest $0.25. This is *acceptable for visualization* but may hide true volume concentration. For strict market microstructure, would use actual trade prices. **Not a bug, just a simplification.**

---

## 6. REGIME DETECTION — `dashboard/regime_detector.py`

### PASS ✓ (Heuristic-Based, Reasonable)

**VIX Term Structure Analysis — Sound Logic**
- Lines 148-193: Uses UVXY/SVXY ratio as VIX regime proxy
- ✓ UVXY tracks +1.5× daily VIX futures returns
- ✓ SVXY is inverse (short volatility ETF)
- ✓ Ratio > 1.5 → backwardation (stress), < 0.5 → contango (calm)
- **Note:** Approximation only (true VIX term structure requires futures data), but reasonable given data constraints

**SPY-TLT Correlation — Correct**
- Lines 196-229: Rolling correlation of returns
- ✓ Inverse correlation (-0.3 to -0.7) = normal risk-on/off
- ✓ Positive correlation (>0.3) = panic / flight-to-safety
- ✓ Uses 60-min window (15-min bars × 4)
- **Sound reasoning:** Correlation regime captures macro risk sentiment

**Dollar Strength (UUP) — Reasonable**
- Lines 235-250: UUP (dollar bullish ETF) as DXY proxy
- ✓ 3-hour price change detects trend
- ✓ DXY correlation with equities is well-established

**Regime Classification — Logic Sound**
- Creates `sizing_multiplier` (0.3 to 1.5) and `directional_bias` (-0.5 to +0.5)
- Used by risk management to adjust position size per regime
- ✓ Risk-off reduces size, risk-on increases size

**Minor Note:** VIX approximation from UVXY/SVXY is *heuristic*, not academic. For research, would use VIX futures term structure. But for signals, this is reasonable.

---

## 7. SECURITY AUDIT — CRITICAL FINDINGS

### FAIL ✗✗✗ — MULTIPLE CRITICAL VULNERABILITIES

#### 🔴 CRITICAL: API KEYS HARDCODED IN .env (Line 5-6)

**File:** `/AI Trading Bot/.env`
```
ALPACA_API_KEY=<REDACTED>
ALPACA_SECRET_KEY=<REDACTED>
```

**Severity:** CRITICAL ⚠️
- **Issue:** Both API keys are visible in plaintext
- **Risk:** If repository is ever committed (even accidentally) or code is shared, keys are compromised
- **Alpaca Impact:** Attacker can trade on account with SIP real-time feed ($99/mo)
- **Action Required:**
  - ✓ Revoke these keys immediately in Alpaca dashboard
  - ✓ Use environment variables only (never .env in repo)
  - ✓ Add .env to .gitignore (already present: `.gitignore` has `.env`)

**Current Status:** .gitignore is present, so accidental commits are prevented. **However, the keys are still visible in working memory — revoke them NOW.**

---

#### 🔴 CRITICAL: CORS MISCONFIGURATION

**File:** `dashboard/app.py`, lines 55-61
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Severity:** CRITICAL ⚠️
- **Issue:** `allow_origins=["*"]` + `allow_credentials=True` is a **contradiction**
  - This allows ANY domain to make authenticated requests (XSS vulnerability)
  - Combined with wildcard headers/methods → maximum attack surface
- **Risk:**
  - Malicious website can craft requests to trade API from user's browser
  - No origin validation
  - CSRF tokens not implemented
- **Mitigation:**
  ```python
  allow_origins=["http://localhost:3000", "http://127.0.0.1:8000"],  # Only local dev
  allow_credentials=False,  # Or True only if origins are restricted
  allow_methods=["GET", "POST", "OPTIONS"],  # Not "*"
  allow_headers=["Content-Type"],  # Explicit, not "*"
  ```

---

#### 🔴 CRITICAL: WebSocket No Authentication

**File:** `dashboard/app.py`, lines 95-109
```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
```

**Severity:** CRITICAL ⚠️
- **Issue:** WebSocket `/ws` endpoint accepts *any* client without authentication
- **Risk:**
  - Any client can connect and receive real-time trading signals
  - Potential for data exfiltration (bid/ask, order flow, signal timing)
  - No origin validation, no token validation
- **Mitigation:**
  ```python
  @app.websocket("/ws")
  async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
      if not verify_token(token):
          await websocket.close(code=1008, reason="Unauthorized")
      await manager.connect(websocket)
  ```

---

#### 🟡 HIGH: Unvalidated REST Endpoints

**File:** `dashboard/api_routes.py`
- Line 61: `symbol: str = Query("SPY")` — **No validation**
- Line 97: `url = f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/snapshot?feed={sip}"`
- Line 182: `feed: str = Query("sip")` — **Only whitelist check is feed in ("sip", "iex")**

**Issue:** Symbol parameter is user-controlled but not validated
- Could theoretically be exploited for path traversal (though unlikely with Alpaca API)
- **Best practice:** Whitelist known symbols or validate with regex

**Mitigation:**
```python
import re
def validate_symbol(s: str) -> str:
    if not re.match(r"^[A-Z]{1,5}$", s):
        raise ValueError("Invalid symbol")
    return s
```

---

#### 🟡 HIGH: SQL Injection (SQLite)

**File:** `dashboard/signal_db.py`, lines 110-132
```python
conn.execute("""
    INSERT OR REPLACE INTO signals
    (id, timestamp, symbol, ...)
    VALUES (?, ?, ?, ...)
""", (sig_id, timestamp, symbol, ...))
```

**Status:** ✓ SAFE
- **Correct:** Uses parameterized queries (`?` placeholders)
- All data binding is via tuple parameters, not string formatting
- **No injection risk**

---

#### 🟡 MEDIUM: Theta Terminal API Proxy Not Validated

**File:** `dashboard/app.py`, lines 243-274
```python
url = f"{theta_base}/v3/stock/history/eod?symbol={symbol}&start_date={start_date}&end_date={end_date}&format=json"
```

**Issue:** Symbol, start_date, end_date are user-controlled and directly interpolated into URL
- Potential for parameter injection
- **Mitigation:** Validate date format and symbol format

---

#### 🟡 MEDIUM: Rate Limiting Not Implemented

**Files:**
- `dashboard/orderflow_api.py`: Alpaca rate limits are 200 req/min free tier, higher for paid
- No rate limiting on `/api/orderflow/*`, `/api/bars`, `/api/quote`
- **Risk:** Brute-force API exhaustion, accidental DDoS

**Mitigation:**
```python
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)
@app.get("/api/quote")
@limiter.limit("10/minute")
async def get_live_quote(...):
```

---

#### 🟡 MEDIUM: Logging Sensitive Data

**File:** `dashboard/debug_middleware.py` (implied by name)
- Debug middleware may log request/response bodies
- **Risk:** API keys, signal details, trade data in logs

**Check:** Search logs for plaintext secrets before production

---

### Security Verdict: 2/10

**Summary:**
- ✓ SQL injection: Safe (parameterized queries)
- ✗ API keys: Exposed in .env (critical — revoke now)
- ✗ CORS: Wildcard misconfiguration (critical)
- ✗ WebSocket: No authentication (critical)
- ✗ REST endpoints: Insufficient input validation (high)
- ✗ Rate limiting: Not implemented (medium)
- ✗ Logging: May include sensitive data (medium)

---

## 8. ALGORITHMIC CORRECTNESS SUMMARY

| Component | Formula Correctness | Implementation | Notes |
|-----------|-------------------|-----------------|-------|
| **Tick Rule** | 100% | ✓ Correct | Matches Hasbrouck & Seppi |
| **VWAP** | 100% | ✓ Correct | Fallback to OHLC avg is sound |
| **Volume Clouds** | 95% | ✓ Sound | Buy/sell split is heuristic not strict tick |
| **Confluence (16-factor)** | 90% | ✓ Reasonable | Weights make sense for institutional trading |
| **3 PM Hard Stop** | 100% | ✓ Correct | Standard 0DTE practice |
| **Confidence Tiers** | 100% | ✓ Correct | TEXTBOOK/HIGH/VALID mapping is sound |
| **GEX Calculation** | 100% | ✓ Correct | Standard formula with proper sign handling |
| **DEX Calculation** | 100% | ✓ Correct | Aggregate dealer delta is correct |
| **VPIN (Flow Toxicity)** | 100% | ✓ Correct | Matches Easley et al. paper |
| **VPIN Thresholds** | 100% | ✓ Reasonable | 0.7 high threshold is empirically sound |
| **Pivot Points** | 100% | ✓ Correct | All 6 formulas are standard |
| **ATR** | 100% | ✓ Correct | √5 scaling for 5-min is correct |
| **Regime Detection** | 80% | ✓ Reasonable | Heuristic-based, not academic model |

---

## 9. BUGS AND CORRECTNESS ISSUES

### No Critical Domain Bugs Found

**What's Working Well:**
1. ✓ Tick rule classification matches market microstructure literature
2. ✓ VWAP calculation is mathematically correct
3. ✓ GEX/DEX formulas use proper dealer positioning logic
4. ✓ VPIN algorithm matches Easley et al. (2012) paper
5. ✓ Pivot points use standard formulas
6. ✓ Confluence weighting is balanced and reasonable
7. ✓ 3 PM hard stop is institutional best practice
8. ✓ Tick store (SQLite) properly uses parameterized queries

### Minor Edge Cases (Not Bugs)

1. **Buy/Sell Split in OHLCV Bars** (orderflow_api.py, line 316)
   - Uses close position in range, not strict tick classification
   - **Impact:** Minor — acceptable for visualization
   - **Fix:** If strict order flow needed, use individual trade data

2. **VPIN Bucket Size (1000 shares)** (flow_toxicity.py, line 37)
   - Reasonable for SPY but may need tuning for lower-volume stocks
   - **Impact:** None for SPY (liquid, millions of shares/day)

3. **Regime Detection Uses Proxy ETFs** (regime_detector.py, line 162-174)
   - Uses UVXY/SVXY, not true VIX futures term structure
   - **Impact:** Approximate, good enough for signals
   - **Note:** This is a design choice, not a bug

4. **POC Resolution ($0.25 rounding)** (market_levels.py, line 196)
   - May hide high-resolution volume concentration
   - **Impact:** Minor for visualization
   - **Note:** Acceptable simplification

---

## 10. MISSING CONTROLS & RECOMMENDATIONS

### Before Production Deployment:

**SECURITY (MUST FIX):**
1. ⚠️ Revoke Alpaca API keys immediately
2. ⚠️ Restrict CORS origins to specific domains
3. ⚠️ Implement WebSocket authentication (JWT or similar)
4. ⚠️ Add input validation to REST endpoints (whitelist symbols, validate dates)
5. ⚠️ Implement rate limiting on all public endpoints
6. ⚠️ Use secrets management (AWS Secrets Manager, HashiCorp Vault, not .env)
7. ⚠️ Add logging filters to prevent sensitive data in logs
8. ⚠️ Implement CSRF tokens for state-changing endpoints

**DOMAIN-LEVEL (NICE-TO-HAVE):**
1. Add true tick rule classification from individual trade data (not OHLCV approximation)
2. Add transaction cost modeling to signal confidence
3. Add slippage estimation in strike selection
4. Test VPIN bucket size sensitivity (current 1000 is reasonable for SPY)
5. Add circuit breakers (hard stops if VIX > 50, correlation breaks, etc.)
6. Add position correlation tracking (delta/gamma/vega exposure across strikes)
7. Add win-rate tracking and p-value calculation for signal validity

---

## 11. DEPLOYMENT READINESS

| Dimension | Score | Status |
|-----------|-------|--------|
| **Domain Logic** | 7/10 | ✓ Production-ready (with noted edge cases) |
| **Code Quality** | 6/10 | Reasonable (good structure, minor review items) |
| **Security** | 2/10 | ✗ NOT production-ready (critical flaws) |
| **Testing** | 4/10 | Limited (some test files but not comprehensive) |
| **Monitoring** | 5/10 | Basic logging present |
| **Documentation** | 8/10 | Good (docstrings and READMEs) |

**Overall:** ✗ **NOT READY FOR REAL-MONEY TRADING**

---

## 12. ACTION PLAN

### IMMEDIATE (Today):
1. **Revoke Alpaca keys** in Alpaca dashboard
2. **Rotate secrets** (generate new keys)
3. **Fix CORS** — restrict to localhost only for dev
4. **Add WebSocket auth** — implement simple token validation
5. **Search codebase** for other hardcoded credentials (check .env.example too)

### SHORT-TERM (This Week):
1. Implement input validation for all REST endpoints
2. Add rate limiting (slowapi library)
3. Switch to environment variable injection (not .env file in code)
4. Add security headers (X-Frame-Options, CSP, etc.)
5. Implement CSRF protection

### MEDIUM-TERM (Before Live Trading):
1. Comprehensive security audit by 3rd party
2. Penetration testing on API endpoints
3. Add end-to-end encryption for sensitive data
4. Implement proper secrets management (Vault or cloud equivalent)
5. Add PII/PCI controls (if handling customer data)
6. Load testing and stress testing
7. Disaster recovery / backup strategy

---

## 13. FINAL ASSESSMENT

### Domain & Algorithms: SOUND ✓
- Order flow classification is textbook correct
- VWAP and volume cloud aggregation are mathematically sound
- GEX/DEX formulas match institutional dealer positioning models
- VPIN calculation matches Easley et al. (2012) academic paper
- Confluence framework weighting is balanced and reasonable
- 3 PM hard stop and risk management are standard practice

### Security: CRITICAL FLAWS ✗
- **Do not use with real money** until security is addressed
- API keys are exposed
- CORS is misconfigured
- WebSocket has no authentication
- Input validation is insufficient

### Recommendation:
**This is a well-designed trading system with excellent domain knowledge implementation.** The algorithms are sound and the logic is correct. However, **security must be fixed before any production use**.

Use this system for:
- ✓ Paper trading (backtesting, simulation)
- ✓ Signal validation in sandbox
- ✗ Real-money trading (until security audit passes)

---

**End of Audit Report**
