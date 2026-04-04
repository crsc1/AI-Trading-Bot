# AI Signals Engine — Comprehensive Implementation Plan

## Executive Summary

This plan transforms the existing signal engine from a **one-shot analyzer** into a **full signal lifecycle system**: generate signals based on multi-factor confluence, automatically paper-trade each signal, track live P&L with Greeks decomposition, and grade every trade to continuously improve signal quality.

The system operates in two modes:
1. **Simulation Mode** — Black-Scholes repricing with realistic slippage modeling (no broker needed)
2. **Alpaca Paper Mode** — Real order execution on Alpaca's paper trading environment

---

## Part 1: What We Already Have

### Existing Infrastructure (Working)

| Component | File | What It Does |
|-----------|------|--------------|
| Signal Engine | `dashboard/signal_engine.py` | Orchestrates the full analysis pipeline: fetch data → levels → flow → confluence → strike → risk |
| Confluence Engine | `dashboard/confluence.py` | Evaluates 5 confluence factors, classifies trade direction + confidence tier |
| Market Levels | `dashboard/market_levels.py` | VWAP ±σ bands, HOD/LOD, Opening Range (5m/15m), Pivot Points, POC, Value Area, ATR |
| Greeks Calculator | `utils/greeks.py` | Black-Scholes pricing with delta/gamma/theta/vega/rho (py_vollib primary, simplified fallback) |
| Trading API | `dashboard/trading_api.py` | Alpaca paper account: balance, positions, orders, history |
| Signal API | `dashboard/signal_api.py` | REST endpoints: `/api/signals/analyze`, `/api/signals/latest`, `/api/signals/history` |
| Rust Flow Engine | `flow-engine/src/` | Real-time trade classification, CVD, sweep/absorption/imbalance detection, WebSocket ingestion |

### Current Confluence Factors (5 factors, need 2+ confirming)

1. **Delta Divergence** (weight 0.25) — CVD vs price divergence
2. **VWAP Interaction** (weight 0.15) — Price at VWAP bands with confirming flow
3. **HOD/LOD Interaction** (weight 0.20) — Absorption/rejection at day extremes
4. **Opening Range Breakout** (weight 0.20) — ORB break with volume confirmation
5. **Previous Day Levels** (weight 0.15) — Reaction at prev high/low/close

### What's Missing (Gaps to Fill)

1. **GEX/DEX Calculation** — No gamma exposure or delta exposure analysis
2. **Options Flow Detection** — Only equity flow; no unusual options activity tracking
3. **IV Rank / IV Percentile** — No historical volatility context
4. **Put/Call Ratio** — Not computed from options chain
5. **Signal Validation System** — Signals fire and forget; no tracking of outcomes
6. **Paper Trade Execution** — Trading API exists but nothing auto-trades signals
7. **Live P&L Tracking** — No real-time repricing of open positions
8. **Signal Scorecard** — No win rate, profit factor, or performance metrics
9. **Max Pain Calculation** — Not computed from open interest data
10. **Time-of-Day Weighting** — Session context exists but doesn't weight signals

---

## Part 2: Enhanced Confluence Scoring (10 Factors)

The upgraded engine scores each signal on 10 factors, requiring **6.5/10** for high-confidence entry (vs current 2/5).

### Factor 1: Order Flow Imbalance (weight 1.5)
**What it measures:** Net aggressive buying vs selling pressure over rolling 2-minute windows.

| Condition | Score |
|-----------|-------|
| Imbalance > 65% in signal direction | 1.5 |
| Imbalance 55-65% in signal direction | 1.0 |
| Balanced (45-55%) | 0.0 |
| Imbalance against signal direction | -1.0 |

**Data source:** Existing — `OrderFlowState.imbalance`, `aggressive_buy_pct`, `aggressive_sell_pct`

### Factor 2: CVD Divergence (weight 1.0)
**What it measures:** Cumulative volume delta diverging from price = hidden accumulation/distribution.

| Condition | Score |
|-----------|-------|
| Strong divergence confirmed (CVD rising + price falling → bullish) | 1.0 |
| Mild divergence developing | 0.5 |
| CVD confirming price direction | 0.3 |
| CVD contradicting signal | -0.5 |

**Data source:** Existing — `OrderFlowState.divergence`, `cvd_trend`, `cvd_acceleration`

### Factor 3: GEX Alignment (weight 1.5) — NEW
**What it measures:** Dealer gamma exposure determines whether dealers dampen or amplify moves.

Positive GEX = dealers short gamma → they buy dips/sell rips → **range-bound** (fade signals)
Negative GEX = dealers long gamma → they amplify moves → **trend signals**

| Condition | Score |
|-----------|-------|
| Negative GEX + trend signal (breakout) | 1.5 |
| Positive GEX + mean-reversion signal (fade to VWAP) | 1.5 |
| Negative GEX + mean-reversion signal | -0.5 |
| Positive GEX + trend signal | -0.5 |

**Data source:** NEW — Calculate from options chain open interest:
```
GEX = Σ (OI × contract_multiplier × spot² × 0.01 × gamma)
```
For each strike: `gamma = N'(d1) / (S × σ × √T)`

Call gamma = positive dealer exposure (dealer sold calls, hedges by buying stock)
Put gamma = negative dealer exposure (dealer sold puts, hedges by selling stock)

**Call Wall** = strike with highest call GEX → resistance ceiling
**Put Wall** = strike with highest put GEX → support floor

### Factor 4: DEX Levels (weight 1.0) — NEW
**What it measures:** Delta Exposure shows where dealers need to hedge most aggressively.

| Condition | Score |
|-----------|-------|
| Price approaching DEX flip level + signal aligns with expected move | 1.0 |
| Price between call wall and put wall (normal range) | 0.3 |
| Signal pushes price beyond call/put wall (dealers amplify) | 0.5 |

**Data source:** NEW — Calculate from options chain:
```
DEX = Σ (OI × contract_multiplier × delta)
```
Calls contribute positive DEX, puts contribute negative DEX.

### Factor 5: VWAP Band Rejection (weight 1.0)
**What it measures:** Price bouncing off VWAP bands with volume confirmation.

| Condition | Score |
|-----------|-------|
| Touch VWAP ±2σ with absorption + reversal candle | 1.0 |
| Touch VWAP ±1σ with flow confirmation | 0.7 |
| Price at VWAP with neutral flow | 0.2 |
| Price extended beyond VWAP ±2σ (overextended) | -0.3 |

**Data source:** Existing — `MarketLevels.vwap_*` bands, enhanced with absorption detection

### Factor 6: Volume Spike Detection (weight 0.5)
**What it measures:** Sudden volume surge (>2x 20-period average) at key level = institutional activity.

| Condition | Score |
|-----------|-------|
| Volume > 3× average at support/resistance | 0.5 |
| Volume > 2× average with directional flow | 0.3 |
| Normal volume | 0.0 |
| Declining volume on breakout (suspect) | -0.3 |

**Data source:** Existing — `OrderFlowState.total_volume` + bars volume, new rolling average calculation

### Factor 7: Delta Regime (weight 1.0)
**What it measures:** Whether cumulative delta is accelerating in the signal direction.

| Condition | Score |
|-----------|-------|
| CVD accelerating in signal direction (2nd derivative positive) | 1.0 |
| CVD steady in signal direction | 0.5 |
| CVD decelerating (momentum fading) | -0.3 |
| CVD accelerating against signal | -1.0 |

**Data source:** Existing — `OrderFlowState.cvd_acceleration`, needs rolling window

### Factor 8: Put/Call Ratio (weight 0.5) — NEW
**What it measures:** Extreme put/call ratios signal sentiment extremes → contrarian signals.

| Condition | Score |
|-----------|-------|
| PCR > 1.2 + bullish signal (extreme fear = contrarian buy) | 0.5 |
| PCR < 0.7 + bearish signal (extreme greed = contrarian sell) | 0.5 |
| PCR 0.8-1.0 (neutral) | 0.0 |
| PCR confirms direction (not contrarian) | 0.2 |

**Data source:** NEW — Calculate from options chain: `PCR = put_volume / call_volume` (use OI-weighted)

### Factor 9: Max Pain Proximity (weight 0.5) — NEW
**What it measures:** Options max pain = price where most options expire worthless. Price gravitates toward it on expiration day.

| Condition | Score |
|-----------|-------|
| 0DTE + signal pushes toward max pain | 0.5 |
| 0DTE + signal pushes away from max pain | -0.3 |
| Non-0DTE (max pain less relevant) | 0.0 |

**Data source:** NEW — Calculate from OI across all strikes:
```
max_pain = strike that minimizes Σ (intrinsic_value × OI) across all options
```

### Factor 10: Time-of-Day Quality (weight 0.5)
**What it measures:** Some session phases are statistically better for 0DTE entries.

| Phase | Quality Score | Notes |
|-------|--------------|-------|
| Opening Drive (9:30-10:00) | 0.5 | High momentum, clear direction |
| Morning Trend (10:00-11:30) | 0.5 | Best sustained moves |
| Midday Chop (11:30-13:30) | -0.3 | Low conviction, whipsaw city |
| Afternoon Trend (13:30-15:00) | 0.4 | Second wind, but 0DTE theta accelerating |
| Power Hour (15:00-15:45) | 0.3 | High vol but extreme theta decay |
| Close Risk (15:45-16:00) | -0.5 | Too late for 0DTE entries |

**Data source:** Existing — `SessionContext.phase`, `session_quality`

### Scoring Rules

- **Minimum score for entry: 6.5/10** (theoretical max: 10.0)
- **Veto conditions** (instant NO_TRADE regardless of score):
  - Past 0DTE hard stop (3:00 PM ET for new entries)
  - Spread > 5% of option price
  - IV Rank > 90th percentile (too expensive)
  - GEX alignment score is negative (dealers working against you)
  - Volume < 50% of 20-day average (no liquidity)

---

## Part 3: Signal Lifecycle

Every signal goes through 5 stages:

```
GENERATE → VALIDATE → ENTER → TRACK → GRADE
```

### Stage 1: GENERATE
The confluence engine runs continuously (triggered by flow events, not a fixed timer). When a FlowEvent arrives from the Rust engine (sweep detected, absorption, delta flip, imbalance threshold), it triggers a signal evaluation.

**Trigger conditions:**
- Sweep detected (>$50K notional)
- Delta flip (CVD crosses zero with acceleration)
- Imbalance threshold (>65% for 30+ seconds)
- Absorption at key level (bid/ask stacking with volume)
- VWAP band touch with volume spike

**Output:** Signal object with all 10 confluence scores, total score, entry/target/stop prices

### Stage 2: VALIDATE
Before entering, run pre-trade checks:

1. **Spread check** — Bid/ask spread < 5% of mid price
2. **Liquidity check** — Options volume > 100 contracts at selected strike
3. **Risk check** — Position size within risk limits (0.5-2% of account)
4. **Correlation check** — Not correlated with existing open position
5. **Daily loss check** — Haven't exceeded 2% daily max loss
6. **Cooldown check** — At least 5 minutes since last signal (avoid signal spam)

### Stage 3: ENTER (Dual Mode)

**Mode A: Simulation**
```python
class SimulatedPosition:
    signal_id: str
    symbol: str           # e.g., "SPY260327C00580000"
    option_type: str      # "call" or "put"
    strike: float
    expiry: str
    entry_price: float    # mid price + simulated slippage
    entry_time: datetime
    quantity: int
    entry_greeks: dict    # delta, gamma, theta, vega at entry

    # Slippage model
    slippage = max(0.02, spread * 0.3)  # SPY: typically $0.02-0.05
    entry_price = mid_price + slippage  # worse fill for buyer
```

**Mode B: Alpaca Paper Trading**
```python
# Alpaca Options Order (paper)
order = {
    "symbol": "SPY260327C00580000",  # OCC format
    "qty": 1,
    "side": "buy",
    "type": "limit",
    "time_in_force": "day",
    "limit_price": mid_price + 0.03,  # slight premium for fill
    "order_class": "simple"
}
# POST https://paper-api.alpaca.markets/v2/orders
```

### Stage 4: TRACK (Real-Time P&L)

Every 5 seconds while position is open:

**Simulation Mode:**
```python
def reprice_position(position, current_spot, current_iv, time_now):
    T = (expiry_dt - time_now).total_seconds() / (365.25 * 86400)

    greeks = calculate_greeks(
        S=current_spot,
        K=position.strike,
        T=T,
        r=0.05,  # risk-free rate
        sigma=current_iv,
        option_type=position.option_type[0].upper()
    )

    current_price = greeks['price']
    pnl = (current_price - position.entry_price) * 100 * position.quantity
    pnl_pct = ((current_price / position.entry_price) - 1) * 100

    # Greeks decomposition of P&L
    spot_change = current_spot - position.entry_spot
    delta_pnl = position.entry_greeks['delta'] * spot_change * 100
    gamma_pnl = 0.5 * position.entry_greeks['gamma'] * spot_change**2 * 100
    theta_pnl = position.entry_greeks['theta'] * elapsed_days * 100
    vega_pnl = position.entry_greeks['vega'] * (current_iv - position.entry_iv) * 100

    return {
        "current_price": current_price,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "delta_pnl": delta_pnl,
        "gamma_pnl": gamma_pnl,
        "theta_pnl": theta_pnl,
        "vega_pnl": vega_pnl,
        "greeks": greeks,
    }
```

**Alpaca Paper Mode:**
```python
# GET /v2/positions/{symbol}
# Returns: current_price, unrealized_pl, unrealized_plpc, qty, avg_entry_price
# Also available via WebSocket for real-time updates
```

**Exit conditions (checked every tick):**
1. **Target hit** — P&L reaches +50% of entry (e.g., bought at $2.00, exit at $3.00)
2. **Stop hit** — P&L reaches -50% of entry (e.g., bought at $2.00, stop at $1.00)
3. **Time stop** — Position open > 45 minutes (0DTE theta is ruthless)
4. **Trailing stop** — If P&L was +30% and drops back to +10%, exit
5. **Hard stop** — 3:00 PM ET for 0DTE positions (close everything)
6. **Volatility stop** — IV crush >15% since entry (post-catalyst)

### Stage 5: GRADE

After every closed trade:

```python
class TradeGrade:
    signal_id: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    exit_reason: str  # "target", "stop", "time", "trailing", "hard_stop"

    # Signal quality metrics
    confluence_score: float    # What the engine scored at entry
    max_favorable: float       # Best P&L during trade (MFE)
    max_adverse: float         # Worst P&L during trade (MAE)
    hold_time_minutes: int

    # Grade: A/B/C/D/F
    grade: str

    # Grading criteria:
    # A: Hit target, MFE > 2× MAE, held to plan
    # B: Profitable exit (trailing or partial), MFE > MAE
    # C: Small loss (stopped out but < 25% of risk budget)
    # D: Full stop loss hit
    # F: Time stopped or hard stopped with loss
```

---

## Part 4: Signal Scorecard (Cumulative Performance)

Displayed in the AI Signals panel on the frontend.

### Key Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| **Win Rate** | wins / total_trades | > 55% |
| **Profit Factor** | gross_profit / gross_loss | > 1.5 |
| **Average Win** | Σ winning_pnl / wins | Track |
| **Average Loss** | Σ losing_pnl / losses | Track |
| **Expectancy** | (win_rate × avg_win) - (loss_rate × avg_loss) | > $0 |
| **Sharpe Ratio** | mean(returns) / stdev(returns) × √252 | > 1.0 |
| **Sortino Ratio** | mean(returns) / downside_dev × √252 | > 1.5 |
| **Max Drawdown** | peak_to_trough / peak | < 15% |
| **Avg Hold Time** | mean(exit_time - entry_time) | 10-30 min |
| **Grade Distribution** | count per A/B/C/D/F | Mostly A+B |

### Rolling Windows
- **Today** — Current session stats
- **5-Day** — Trading week performance
- **20-Day** — Monthly performance
- **All-Time** — Since system start

### Signal Quality Feedback Loop
The scorecard feeds back into signal generation:
- If win rate drops below 40% over 20 trades → raise minimum confluence to 7.5/10
- If average loss > 2× average win → tighten stops from 50% to 35%
- If most exits are "time stop" → reduce max hold time or filter by time-of-day more aggressively
- Track which confluence factors correlate most with wins → dynamically adjust factor weights

---

## Part 5: Data Sources

### Currently Available (via Alpaca)
- Real-time equity trades (WebSocket) → Rust engine
- 1-minute and daily bars → `api_routes.py`
- Real-time quotes (bid/ask/last) → `api_routes.py`
- Options chain (strikes, expiries, bid/ask) → `api_routes.py`
- Options snapshots → `api_routes.py`
- Paper trading execution → `trading_api.py`

### Needs Enhancement
1. **Options chain Greeks** — Alpaca returns bid/ask/OI but **not Greeks/IV** per strike. We must compute them ourselves using Black-Scholes from our `utils/greeks.py` module. For each strike: given bid/ask mid price, solve for IV, then compute all Greeks.

2. **GEX/DEX** — Computed from options chain OI + calculated gamma/delta per strike. No external data needed — just math on top of what Alpaca already provides.

3. **IV Rank** — Requires historical IV data. We can compute daily IV from ATM options and store a rolling 252-day window in SQLite. IV Rank = (current_IV - 52wk_low) / (52wk_high - 52wk_low).

4. **Put/Call Ratio** — Sum put OI / call OI from chain data. Already available, just needs computation.

5. **Max Pain** — Iterate all strikes in the chain, calculate total pain at each strike, find minimum. Data already available from chain endpoint.

### Data Storage
- **SQLite** for signal history, trade history, scorecard, IV history
- **In-memory** for real-time state (current positions, live P&L, current GEX/DEX)
- **Existing trade cache** from Rust engine for flow analysis

---

## Part 6: Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (HTML/JS)                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐ │
│  │  Flow Chart   │ │ Candle Chart │ │   AI Signals     │ │
│  │  (PixiJS +    │ │  (Canvas)    │ │   Panel          │ │
│  │   Canvas 2D)  │ │              │ │  - Active Sigs   │ │
│  │              │ │              │ │  - Live P&L      │ │
│  │              │ │              │ │  - Scorecard     │ │
│  └──────────────┘ └──────────────┘ └──────────────────┘ │
└────────────────────────┬────────────────────────────────┘
                         │ WebSocket + REST
┌────────────────────────┴────────────────────────────────┐
│                   BACKEND (FastAPI)                       │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              Signal Lifecycle Manager                 │ │
│  │  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐ │ │
│  │  │ Enhanced │→│Validator │→│ Paper  │→│  P&L     │ │ │
│  │  │Confluence│ │ (pre-    │ │ Trader │ │ Tracker  │ │ │
│  │  │ Engine   │ │  trade)  │ │        │ │          │ │ │
│  │  │(10 factor│ │          │ │ Sim or │ │ Reprices │ │ │
│  │  │ scoring) │ │          │ │ Alpaca │ │ every 5s │ │ │
│  │  └──────────┘ └──────────┘ └────────┘ └──────────┘ │ │
│  │                                           ↓         │ │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────────┐  │ │
│  │  │  GEX/DEX │ │ IV Rank  │ │   Trade Grader +   │  │ │
│  │  │Calculator│ │ Tracker  │ │    Scorecard        │  │ │
│  │  └──────────┘ └──────────┘ └────────────────────┘  │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Market Levels │  │ Signal Engine│  │ Trading API   │  │
│  │ (existing)    │  │ (existing)   │  │ (existing)    │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│              RUST FLOW ENGINE (existing)                  │
│  Trade ingestion → Classification → CVD → Detectors      │
│  Sweeps | Absorption | Imbalance | Delta Flips            │
└─────────────────────────────────────────────────────────┘
```

---

## Part 7: Implementation Phases

### Phase 1: GEX/DEX + Enhanced Confluence (Priority: HIGH)
**New files:**
- `dashboard/gex_engine.py` — GEX/DEX calculation from options chain
- `dashboard/options_analytics.py` — IV Rank, PCR, Max Pain computation

**Modified files:**
- `dashboard/confluence.py` — Upgrade from 5 to 10 factors, new scoring thresholds
- `dashboard/signal_engine.py` — Integrate new factors into pipeline

**Estimated effort:** 2-3 sessions

### Phase 2: Signal Validation + Paper Trading (Priority: HIGH)
**New files:**
- `dashboard/signal_validator.py` — Pre-trade validation checks
- `dashboard/paper_trader.py` — Dual-mode execution (sim + Alpaca)
- `dashboard/position_tracker.py` — Real-time P&L with Greeks decomposition
- `dashboard/trade_grader.py` — Post-trade grading and scorecard

**Modified files:**
- `dashboard/signal_api.py` — New endpoints for positions, P&L, scorecard
- `dashboard/trading_api.py` — Options order execution via Alpaca

**Estimated effort:** 3-4 sessions

### Phase 3: Signal History + Feedback Loop (Priority: MEDIUM)
**New files:**
- `dashboard/signal_db.py` — SQLite schema for signals, trades, scorecard, IV history
- `dashboard/signal_feedback.py` — Adaptive parameter tuning based on performance

**Modified files:**
- `dashboard/signal_engine.py` — Query historical performance for dynamic thresholds

**Estimated effort:** 1-2 sessions

### Phase 4: Frontend Integration (Priority: HIGH)
**Modified files:**
- `dashboard/static/flow-dashboard.html` — AI Signals panel with:
  - Active signal cards (live P&L, Greeks, grade)
  - Signal history list (scrollable, filterable)
  - Scorecard widget (win rate, PF, expectancy, drawdown)
  - Mode toggle (Simulation ↔ Alpaca Paper)

**Estimated effort:** 2-3 sessions

### Phase 5: Event-Driven Signal Triggers (Priority: MEDIUM)
**Modified files:**
- `flow-engine/src/events.rs` — New event types for signal triggers
- `dashboard/signal_engine.py` — Subscribe to Rust engine events via WebSocket

Instead of polling, signals generate when specific flow events fire:
- Sweep detected (>$50K)
- Delta flip with acceleration
- Absorption at VWAP/POC/pivot
- Volume spike > 3× average at key level

**Estimated effort:** 1-2 sessions

---

## Part 8: Risk Management Rules

### Per-Trade Risk
| Tier | Max Risk (% of Account) | Max Contracts | Stop Loss |
|------|------------------------|---------------|-----------|
| TEXTBOOK (≥8.5) | 2.0% | 4 | 50% of premium |
| HIGH (≥7.0) | 1.5% | 3 | 50% of premium |
| VALID (≥6.5) | 0.75% | 2 | 40% of premium |
| Below 6.5 | 0% (no trade) | 0 | — |

### Daily Limits
- **Max daily loss:** 2% of account ($100 on $5,000)
- **Max concurrent positions:** 2
- **Max signals per day:** 10 (prevents overtrading)
- **Cooldown between entries:** 5 minutes minimum
- **Hard stop:** No new 0DTE entries after 3:00 PM ET

### Position Sizing Formula
```python
risk_amount = account_balance * risk_pct
max_loss_per_contract = entry_price * stop_pct * 100  # 100 shares per contract
quantity = min(
    floor(risk_amount / max_loss_per_contract),
    max_contracts_for_tier,
    floor(buying_power / (entry_price * 100))
)
```

---

## Part 9: Frontend Signal Card Design

Each signal in the AI Signals panel shows:

```
┌─────────────────────────────┐
│ 🟢 BUY CALL         +$142  │  ← Direction + Live P&L
│ SPY $580C 0DTE      +18.9% │  ← Contract + P&L %
│                             │
│ Entry: $2.50 → Now: $2.97   │  ← Price tracking
│ Target: $3.75  Stop: $1.25  │  ← Risk levels
│                             │
│ Score: 7.8/10  Tier: HIGH   │  ← Confluence score
│ ▓▓▓▓▓▓▓▓░░ 78%             │  ← Visual bar
│                             │
│ Δ +$0.32  Γ +$0.08  Θ -$0.15│ ← Greeks P&L decomposition
│                             │
│ ⏱ 12m ago  | Hold: 23m     │  ← Timing
│ Exit: Trailing at +30%      │  ← Current exit plan
└─────────────────────────────┘
```

### Scorecard Widget (Bottom of Panel)
```
┌─────────────────────────────┐
│ TODAY'S SCORECARD            │
│                             │
│ Trades: 4  |  W/L: 3/1     │
│ Win Rate: 75%               │
│ P&L: +$287  (+5.7%)        │
│ Profit Factor: 3.2          │
│ Avg Win: +$112 | Avg Loss: -$49│
│                             │
│ Best: A (TEXTBOOK @ 10:14)  │
│ Streak: 🟢🟢🟢🔴            │
└─────────────────────────────┘
```

---

## Part 10: Database Schema

```sql
-- Signal history (every signal generated, whether traded or not)
CREATE TABLE signals (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    symbol TEXT DEFAULT 'SPY',
    direction TEXT NOT NULL,        -- BUY_CALL, BUY_PUT, NO_TRADE
    confidence REAL,
    tier TEXT,
    confluence_score REAL,
    factors TEXT,                    -- JSON array of factor scores
    strike REAL,
    expiry TEXT,
    entry_price REAL,
    target_price REAL,
    stop_price REAL,
    was_traded INTEGER DEFAULT 0,   -- 1 if entered
    reject_reason TEXT              -- why not traded (if applicable)
);

-- Trade history (only signals that were entered)
CREATE TABLE trades (
    id TEXT PRIMARY KEY,
    signal_id TEXT REFERENCES signals(id),
    mode TEXT NOT NULL,              -- 'simulation' or 'alpaca'
    entry_time TEXT NOT NULL,
    exit_time TEXT,
    entry_price REAL NOT NULL,
    exit_price REAL,
    quantity INTEGER DEFAULT 1,
    pnl REAL,
    pnl_pct REAL,
    max_favorable REAL,             -- MFE
    max_adverse REAL,               -- MAE
    exit_reason TEXT,
    grade TEXT,                     -- A/B/C/D/F
    greeks_at_entry TEXT,           -- JSON
    greeks_at_exit TEXT             -- JSON
);

-- Daily scorecard snapshots
CREATE TABLE daily_scorecard (
    date TEXT PRIMARY KEY,
    trades INTEGER,
    wins INTEGER,
    losses INTEGER,
    gross_profit REAL,
    gross_loss REAL,
    net_pnl REAL,
    win_rate REAL,
    profit_factor REAL,
    expectancy REAL,
    max_drawdown REAL,
    avg_hold_minutes REAL,
    grade_distribution TEXT         -- JSON {"A": 2, "B": 1, "C": 0, "D": 1, "F": 0}
);

-- IV history for IV Rank calculation
CREATE TABLE iv_history (
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    atm_iv REAL NOT NULL,
    iv_rank REAL,
    iv_percentile REAL,
    PRIMARY KEY (date, symbol)
);
```

---

## Recommended Build Order

1. **Phase 1** (GEX/DEX + Enhanced Confluence) — This is the brain. Everything else depends on better signal quality.
2. **Phase 2** (Validation + Paper Trading) — This is the proof. Can't trust signals without tracking outcomes.
3. **Phase 4** (Frontend) — User needs to see it working to provide feedback.
4. **Phase 3** (History + Feedback) — Persistence and adaptive learning.
5. **Phase 5** (Event-Driven Triggers) — Optimization, not required for v1.

Ready to start Phase 1 on your go.
