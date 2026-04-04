# AI Trading Bot: Money Machine Blueprint

**Date:** April 2, 2026
**Account:** $5,000 cash | 0DTE SPY/SPX | Single-leg options
**Goal:** Consistent daily profit through institutional-grade signal intelligence + disciplined execution

---

## Executive Summary

After a deep audit of every module in the codebase (signal engine, confluence scoring, position manager, exit engine, and all 9 indicator modules) combined with extensive research into proven professional 0DTE strategies, this plan identifies **3 critical bugs destroying profit**, **7 missing edges that professional traders exploit daily**, and **a 4-phase implementation roadmap** to transform this bot from a signal generator into a money-making machine.

The core thesis: **the bot's signal generation is solid (20 factors, v7 confluence) but its execution intelligence is broken and its market context awareness has critical blind spots.** Fix execution first, add missing edges second, optimize with ML third.

---

## PHASE 0: CRITICAL BUG FIXES (Week 1)

These bugs are actively losing money right now. Fix before anything else.

### Bug 1: Trailing Stop Doubles Quantity Denominator

**File:** `position_manager.py`, line 715
**Impact:** Trailing stop triggers at 2x the intended distance, letting winners give back 50%+ of gains

```python
# BROKEN — divides by quantity twice (max_favorable already includes quantity)
max_pnl_pct = max_favorable / (entry_price * 100 * quantity)

# FIX — remove quantity from denominator
max_pnl_pct = max_favorable / (entry_price * 100) if entry_price > 0 else 0
```

**Why this matters:** On a $2.00 option bought x2, a $0.80 gain ($160 total) calculates as 20% instead of 40%. The trailing stop won't activate until the position is up 80% real (thinking it's 40%), meaning the bot holds through reversals that should have been locked in.

### Bug 2: max_risk_per_trade_pct Never Checked

**File:** `position_manager.py`, `check_entry()` method (lines 167-203)
**Impact:** No per-trade risk limit enforcement — a single bad trade can blow 5-10% of account

The `max_risk_per_trade_pct` (2%) is defined in RiskManager but never actually validated in `check_entry()`. Add:

```python
# In check_entry(), after cooldown check:
max_risk_dollars = self.account_equity * self.max_risk_per_trade_pct
if signal.get('risk_amount', 0) > max_risk_dollars:
    return False, f"Risk ${signal['risk_amount']:.0f} exceeds {self.max_risk_per_trade_pct*100}% limit (${max_risk_dollars:.0f})"
```

### Bug 3: Signal ID Race Condition

**File:** `position_manager.py`
**Impact:** On DB commit failure, signal is marked as "seen" but trade never recorded — silent signal loss

Signal IDs get added to `_seen_signal_ids` *before* the database commit succeeds. If the commit fails, the signal is permanently lost. Move the `_seen_signal_ids.add()` call to *after* successful DB write.

---

## PHASE 1: EXECUTION INTELLIGENCE (Weeks 2-3)

The bot can identify setups. It cannot execute them intelligently. This phase transforms the exit engine from a static rule system into a dynamic, context-aware profit optimizer.

### 1.1 Smart Session-Aware Position Sizing

**Problem:** Position sizing ignores time of day. A 9:35 AM entry has 5.5 hours of runway; a 1:30 PM entry has 1.5 hours. Same size is wrong.

**Implementation:** Multiply risk allocation by session quality score (already in confluence.py):

| Session | Quality | Risk Multiplier | Rationale |
|---------|---------|-----------------|-----------|
| Opening Drive (9:30-10:00) | 0.85 | 1.0x | Full size — maximum edge window |
| Morning Trend (10:00-11:30) | 0.80 | 1.0x | Full size — confirmed trend |
| Midday Chop (11:30-1:30) | 0.30 | 0.0x | **No new entries** — proven dead zone |
| Afternoon Trend (1:30-3:00) | 0.70 | 0.75x | Reduced — less time for thesis to play |
| Power Hour (3:00-3:45) | 0.60 | 0.5x | Half size — high vol, theta cliff approaching |

**Key insight from research:** Professional 0DTE traders avoid midday entirely (12-1 PM). The bot currently trades all day. Adding a midday blackout alone could eliminate 30-40% of losing trades.

### 1.2 Dynamic Exit Engine v2 (5-Scorer System)

Replace static exit thresholds with a composite exit score that adapts to live conditions. Each scorer returns 0.0-1.0:

**Scorer 1: Momentum Exhaustion**
- RSI divergence (price making new highs, RSI declining)
- Volume declining on continuation moves
- CVD flattening after directional move
- Score > 0.7 = momentum dying, tighten stops

**Scorer 2: Greeks Dynamics**
- Theta acceleration curve (non-linear after 2 PM)
- Gamma exposure shift (positive → negative = amplified risk)
- IV crush detection (post-catalyst)
- Score > 0.7 = Greeks working against position

**Scorer 3: Level Proximity**
- Distance to VWAP bands (approaching ±2σ = mean reversion zone)
- Distance to GEX walls (call wall = resistance, put wall = support)
- Distance to HOD/LOD/pivot levels
- Score > 0.7 = approaching strong level, take partial profits

**Scorer 4: Session Context**
- Time remaining in session phase
- Approaching phase transition (e.g., morning → midday chop)
- Historical success rate of holding through next phase
- Score > 0.7 = unfavorable session transition approaching

**Scorer 5: Flow Reversal**
- Order flow delta reversing direction
- Sweep activity opposing position direction
- Dark pool prints contrary to position
- Score > 0.7 = institutional flow turning against

**Composite exit logic:**
```python
exit_urgency = (w1*momentum + w2*greeks + w3*levels + w4*session + w5*flow) / sum_weights

if exit_urgency > 0.8:    # URGENT — exit immediately
    exit("DYNAMIC_EXIT_URGENT")
elif exit_urgency > 0.6:  # WARNING — tighten trailing stop to 50% of current
    tighten_trailing_stop(0.5)
elif exit_urgency > 0.4:  # CAUTION — move stop to breakeven if profitable
    if pnl_pct > 0.05:
        move_stop_to_breakeven()
```

### 1.3 Profit Target Intelligence

**Problem:** Static profit targets (SCALP 20%, STANDARD 50%, SWING 80%) ignore market conditions. A 20% target on a strong trend day leaves massive profit on the table. A 50% target on a choppy day rarely gets hit.

**Solution:** ATR-based adaptive targets:

```python
# Morning session with expanding ATR = trending day → wider targets
if session == "morning_trend" and atr_expanding:
    target_multiplier = 1.5  # 75% instead of 50%

# Midday with contracting ATR = range day → tighter targets
if session == "midday" and atr_contracting:
    target_multiplier = 0.6  # 30% instead of 50%

# Power hour = take what you can get
if session == "power_hour":
    target_multiplier = 0.5  # 25% scalps only
```

### 1.4 Partial Exit Strategy

**Problem:** Current system is all-or-nothing. Enter 2 contracts, exit 2 contracts. No scaling.

**Solution:** Scale out in portions:

```
At +30% gain: Exit 50% of position (lock profit)
At +60% gain: Exit 25% more (trail the rest)
Remaining 25%: Trail with dynamic stop (let runners run)
```

This alone could improve average P&L by 15-25% by eliminating the "gave it all back" scenario.

---

## PHASE 2: MISSING MARKET EDGES (Weeks 3-5)

These are edges that professional 0DTE traders exploit every day that the bot completely lacks.

### 2.1 Market Internals Integration (TICK, ADD, VOLD)

**Gap:** The bot has ZERO market breadth awareness. It trades SPY options without knowing if the broader market supports the direction.

**Why this matters:** Research shows that when TICK, ADD, and VOLD all align, the next session opens in that direction 68-74% of the time. For intraday, aligned internals confirm moves and divergent internals warn of reversals.

**Implementation:**
```
New file: dashboard/market_internals.py

Data source: Alpaca SIP (already subscribed) for SPY, or
             free Yahoo Finance API for $TICK/$ADD/$VOLD indices

Signals produced:
- breadth_score: -1.0 to +1.0 (bearish to bullish)
- breadth_divergence: True when price and internals disagree
- extreme_reading: True when TICK > +800 or < -800

Integration: Add as Factor 21 in confluence.py (weight: 1.0)
```

**Expected impact:** Filters out 20-30% of false signals where price moves against broader market trend.

### 2.2 Opening Range Breakout Enhancement

**Gap:** ORB strategy exists in `strategies/opening_range.py` but isn't integrated into the main signal engine. It runs independently.

**Research finding:** 60-minute ORB shows 89.4% win rate with 1.44 profit factor — the single highest-probability 0DTE setup.

**Implementation:**
- Wire `opening_range.py` into `signal_engine.py` as a first-class signal source
- Use the ORB high/low as dynamic support/resistance levels all day (not just for the initial breakout)
- Add ORB range width as a volatility indicator (narrow ORB = explosive breakout likely)

### 2.3 VWAP Mean Reversion Enhancement

**Gap:** Current VWAP scoring (`_score_vwap()`) only considers price vs VWAP bands. Research shows the most profitable mean reversion requires VWAP deviation + volume exhaustion + RSI extreme as a 3-factor filter.

**Enhancement:**
```python
# Current: Simple band check
if price > vwap_plus_2sigma: score = 1.0  # bearish

# Enhanced: 3-factor confirmation required
if price > vwap_plus_2sigma:
    volume_exhausting = current_volume < avg_volume * 0.7
    rsi_extreme = rsi > 70
    cvd_diverging = cvd_slope < 0 while price_slope > 0

    factors_confirmed = sum([volume_exhausting, rsi_extreme, cvd_diverging])
    if factors_confirmed >= 2:
        score = 1.0  # HIGH confidence mean reversion
        trade_mode = "SCALP"  # Quick in-and-out fade
    elif factors_confirmed == 1:
        score = 0.5  # Moderate confidence
```

### 2.4 Gamma Exposure (GEX) Trading Logic

**Gap:** `gex_engine.py` calculates GEX levels but doesn't use them to modulate strategy behavior. GEX regime should fundamentally change how the bot trades:

```
Negative GEX Environment (market makers amplify moves):
  → Use momentum/breakout strategies
  → Wider stops (expect bigger swings)
  → Larger profit targets
  → Reduce position size (higher volatility)

Positive GEX Environment (market makers dampen moves):
  → Use mean reversion strategies
  → Tighter stops (expect range-bound)
  → Tighter profit targets
  → Can increase position size (lower volatility)
```

**Implementation:** Add GEX regime as a strategy selector in signal_engine.py, not just a confluence factor.

### 2.5 Volatility Regime Detector Enhancement

**Gap:** `regime_detector.py` uses UVXY/SVXY proxy for VIX structure. Missing: GARCH-based volatility clustering (low vol persists, high vol persists) and regime transition detection.

**Enhancement:**
```python
# Add to regime_detector.py
def detect_vol_regime(returns_series):
    """
    Simple regime classification without GARCH library:
    - Calculate 5-day realized vol vs 20-day realized vol
    - Rising ratio = vol expanding (trend/momentum regime)
    - Falling ratio = vol compressing (mean reversion regime)
    - Extreme ratio = regime transition likely
    """
    rv5 = returns_series[-5:].std() * math.sqrt(252)
    rv20 = returns_series[-20:].std() * math.sqrt(252)
    ratio = rv5 / rv20

    if ratio > 1.5: return "VOL_EXPANDING"   # momentum strategies
    elif ratio < 0.6: return "VOL_COMPRESSING" # mean reversion + watch for breakout
    else: return "VOL_NORMAL"
```

### 2.6 Implied vs Realized Volatility Edge

**Gap:** `options_analytics.py` calculates ATM IV and IV Rank but never compares implied to realized volatility. This is the #1 edge in options trading:

```
When IV > Realized Vol (options are expensive):
  → Sell premium (spreads when we support them)
  → For long options: tighter profit targets (theta working against you harder)
  → Reduce hold time

When IV < Realized Vol (options are cheap):
  → Buy premium aggressively
  → Wider profit targets (gamma working for you)
  → Can hold longer
```

**Implementation:** Track 5-day and 20-day realized vol, compare to current ATM IV. Pass ratio to confluence scoring as Factor 22.

---

## PHASE 3: SIGNAL QUALITY OPTIMIZATION (Weeks 5-7)

### 3.1 Confluence Scoring Rebalance ✅ DONE (Step 11)

Rebalanced the 23-factor confluence system to reduce false HIGH/TEXTBOOK signals.

**Changes implemented:**

1. **Anti-correlation dampening** — 4 correlated factor clusters soft-capped:
   - Flow cluster (F1+F2+F7+F13+F14): max combined 3.0 (was 4.75 theoretical)
   - Greek cluster (F11+F12): max combined 1.0 (was 1.50)
   - TA cluster (F17+F18+F19): max combined 1.75 (was 2.50)
   - Options cluster (F3+F4+F8+F9): max combined 2.5 (was 3.50)

2. **Raised confluence bonus floor thresholds** for 23 factors:
   - TEXTBOOK: 10+ confirming AND ≤2 opposing (was 8+, no opposing gate)
   - HIGH*0.95: 8+ confirming AND ≤3 opposing (was 6+)
   - HIGH*0.85: 6+ confirming (was 5+)
   - Added minimum pure_score ≥ 0.30 gate (prevents many weak factors → high tier)

3. **Clamped all 23 factors** — F1, F2, F5, F6, F7, F10 were previously unclamped.
   F1 and F7 could return -1.0 (excessive negative drag), now capped at -0.50.

4. **Raised active threshold** from 0.01 → 0.03 to prevent near-zero scores from inflating the adaptive denominator.

5. **Increased opposing factor penalty** from 0.04 → 0.05 per opposing factor.

Tests: 23 new tests in `tests/test_confluence_rebalance.py`, 140 total passing.

### 3.2 Signal Filtering by Win Rate

**Add trade outcome tracking per signal type:**

```python
# Track win/loss by:
# - Time of day (which session phase)
# - Direction (calls vs puts)
# - Confidence tier
# - Trade mode (scalp/standard/swing)
# - GEX regime (positive/negative)

# After 50+ trades, filter out losing combinations:
if historical_win_rate(session, direction, tier, mode, regime) < 0.45:
    skip_signal("Historical win rate below 45% for this setup type")
```

This is the weight learner (`weight_learner.py`) put to real use — not just adjusting weights, but vetoing entire setup categories that lose money.

### 3.3 LLM Validator Upgrade

Current LLM validator is fire-and-forget advisory. Upgrade to include:

**Structured context window:**
```python
# Pass to Claude:
{
    "signal": signal_data,
    "market_regime": "VOL_EXPANDING",
    "gex_regime": "NEGATIVE",
    "session_phase": "morning_trend",
    "internals": {"tick": +450, "add": "+1200", "vold": "bullish"},
    "orb": {"high": 520.50, "low": 518.20, "broken": "above"},
    "recent_trades": last_5_trades_with_outcomes,
    "daily_pnl": current_daily_pnl,
    "iv_rv_ratio": 1.3  # options expensive
}
```

**Enhanced verdict categories:**
- STRONG_APPROVE (increase size 1.25x)
- APPROVE (standard size)
- CAUTION (reduce size 0.5x) — currently this does nothing
- REJECT (skip trade) — currently advisory only

**Consideration:** Making REJECT actually block trades requires careful testing. Start with CAUTION reducing size, monitor for 2 weeks, then consider REJECT blocking.

---

## PHASE 4: ADVANCED STRATEGIES (Weeks 7-10)

### 4.1 Multi-Strategy Engine

Instead of one monolithic signal engine, run parallel strategy engines that specialize:

**Strategy 1: ORB Momentum (9:30-10:30 AM)**
- Trigger: ORB breakout confirmed with volume + VWAP alignment
- Target: 50-100% gain
- Stop: Below ORB range
- Session: Morning only

**Strategy 2: VWAP Mean Reversion (10:30 AM - 2:30 PM)**
- Trigger: Price at VWAP ±2σ + volume exhaustion + RSI extreme
- Target: 20-30% scalp (quick fade back to VWAP)
- Stop: Beyond ±3σ
- Session: Mid-morning through afternoon

**Strategy 3: Trend Continuation (All day, momentum regime)**
- Trigger: Strong confluence (HIGH+) + aligned internals + positive GEX
- Target: 50%+ with trailing stop
- Stop: Dynamic via exit scorer
- Session: Any trending phase

**Strategy 4: Power Hour Momentum (3:00-3:30 PM)**
- Trigger: Direction matches first 30 min of day + volume spike
- Target: 25-40% quick scalp
- Stop: Tight — 15% max loss
- Session: 3:00-3:30 PM only (exit by 3:30)

Each strategy has its own entry/exit parameters, risk allocation, and win rate tracking.

### 4.2 Correlation-Based Signal Confirmation

**Add cross-asset correlation checks:**
- SPY vs QQQ divergence (if QQQ leading, SPY likely follows)
- SPY vs TLT inverse correlation (bonds falling + SPY rising = confirmed risk-on)
- VIX term structure (contango = calm, backwardation = fear)
- DXY (dollar strength) impact on SPY direction

Currently `sector_monitor.py` has basic TLT bond signal but nothing else. Expand to full cross-asset confirmation.

### 4.3 ML Ensemble for Direction Prediction ✅ DONE (Step 12)

Implemented `dashboard/ml_predictor.py` — lightweight logistic regression trade gate.

**Architecture:**
- 30-feature vector: 23 confluence factor scores + 7 context features (confidence, direction, session phase, GEX regime, minutes since open, active factor count, opposing ratio)
- Trains on `signal_outcomes` table (all signals, not just executed trades — 5-10x more data)
- Logistic regression with balanced class weights, StandardScaler normalization
- Persisted to SQLite (`ml_models` table in weight_learner.db)
- Auto-trains on server startup, manual retrain via `POST /api/pm/ml-retrain`

**Trade gate integration:**
- Inserted in position_manager.py signal consumer (both normal and fast-path)
- Blocks trades when P(win) < 58% (configurable MIN_WIN_PROBABILITY)
- Graceful fallback: allows all trades if model not trained or sklearn missing
- Requires minimum 30 labeled outcomes before activating

**Safety:**
- Minimum 5 positive + 5 negative samples required (prevents degenerate models)
- Cross-validation when 50+ samples available
- Feature importance tracked for dashboard display

Tests: 23 new tests in `tests/test_ml_predictor.py`.

---

## IMPLEMENTATION PRIORITY MATRIX

| Priority | Item | Expected Impact | Effort | ROI |
|----------|------|-----------------|--------|-----|
| P0 | Fix trailing stop bug | Stop giving back 50%+ of winners | 1 hour | CRITICAL |
| P0 | Fix max_risk_per_trade check | Prevent catastrophic single-trade loss | 1 hour | CRITICAL |
| P0 | Fix signal ID race condition | Stop losing signals silently | 30 min | HIGH |
| P1 | Midday blackout (no trades 11:30-1:30) | Eliminate 30-40% of losing trades | 2 hours | VERY HIGH |
| P1 | Partial exit strategy (scale out) | +15-25% avg P&L improvement | 1 day | VERY HIGH |
| P1 | Session-aware position sizing | Right-size risk to time remaining | 4 hours | HIGH |
| P2 | Market internals (TICK/ADD/VOLD) | Filter 20-30% false signals | 2 days | HIGH |
| P2 | Dynamic Exit Engine v2 (5-scorer) | Smarter exits = more profit retained | 3 days | HIGH |
| P2 | ORB integration into signal engine | Access to 89% win rate setup | 1 day | HIGH |
| P2 | GEX regime strategy switching | Trade with market maker flow | 1 day | MEDIUM-HIGH |
| P3 | VWAP mean reversion 3-factor | Better fade entries | 4 hours | MEDIUM |
| P3 | IV vs Realized Vol comparison | Know when options are cheap/expensive | 1 day | MEDIUM |
| P3 | Confluence scoring rebalance | Reduce false HIGH/TEXTBOOK signals | 4 hours | MEDIUM |
| P3 | Signal filtering by historical win rate | Stop repeating losing patterns | 2 days | MEDIUM |
| P4 | Multi-strategy engine | Specialized approach per market condition | 1 week | MEDIUM |
| P4 | ML direction prediction | Data-driven trade selection | 1 week | MEDIUM |
| P4 | Cross-asset correlation | Broader market confirmation | 2 days | LOW-MEDIUM |

---

## DAILY PROFIT TARGET FRAMEWORK

With a $5,000 account and these improvements:

**Conservative target:** $50-100/day (1-2% of account)
- 2-4 trades per day
- 60%+ win rate
- Average winner: $40-60
- Average loser: $20-30 (with proper stops)
- Risk per trade: $50-100 (1-2%)

**Realistic weekly target after Phase 2:** $250-400/week
**Monthly target:** $1,000-1,600/month (20-32% monthly return)

**Compounding effect:** At 1.5% daily average, $5,000 becomes ~$8,500 in 3 months, ~$14,500 in 6 months.

**Critical success factors:**
1. Never risk more than 2% per trade ($100 max on $5K)
2. Daily loss limit of $100 (2% of account) — stop trading for the day
3. Avoid midday (11:30 AM - 1:30 PM) — this alone could be the difference between profit and loss
4. Take partial profits at +30% — don't let winners become losers
5. Track every trade outcome by session + regime + direction → filter out losing combinations after 50 trades

---

## WHAT NOT TO BUILD (Anti-Patterns)

Based on research, these are traps that look appealing but don't work for 0DTE:

1. **Complex ML models without sufficient data** — Need 500+ labeled trades minimum for meaningful ML. Start with rules, add ML after 3 months of data.
2. **Spreads before mastering singles** — Account is $5K cash, no margin. Spreads add complexity without proportional edge.
3. **Alerts/notifications** — The bot should trade autonomously. If you need alerts, the automation isn't good enough.
4. **Over-optimization** — More factors ≠ better signals. 20 factors is already at the upper bound. Quality of each factor matters more than quantity.
5. **News trading** — Event calendar exists but 0DTE news trading is essentially gambling. The bot should avoid catalysts, not trade them.
6. **Holding past 3:30 PM** — Theta cliff is real. Every professional source agrees: exit before 3:30 PM for 0DTE longs.

---

## NEXT STEP

Tell me which phase to start building, or if you want to modify priorities. I recommend starting with **Phase 0 (bug fixes)** immediately since those are actively losing money, then moving to **Phase 1.1 (midday blackout + session sizing)** as the highest-ROI quick win.
