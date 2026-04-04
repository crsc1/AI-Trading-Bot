# SPX/SPY Options Trading Bot - Architecture Document

**Status:** Development Plan
**Target Users:** Python Beginners
**Capital:** $5,000 USD
**Data Budget:** $100-$300/month
**Trading Restrictions:** PDT (Pattern Day Trader)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Tech Stack](#2-tech-stack)
3. [Project Structure](#3-project-structure)
4. [Data Flow Architecture](#4-data-flow-architecture)
5. [Signal Scoring System](#5-signal-scoring-system)
6. [Risk Management Rules](#6-risk-management-rules)
7. [API Integration Plan](#7-api-integration-plan)
8. [Database Schema](#8-database-schema)
9. [Dashboard Features](#9-dashboard-features)
10. [Security Framework](#10-security-framework)
11. [Deployment & Operations](#11-deployment--operations)
12. [Development Roadmap](#12-development-roadmap)

---

## 1. System Overview

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        MARKET DATA SOURCES                       │
├──────────┬──────────┬──────────┬──────────┬──────────────────────┤
│ Polygon  │ FinnHub  │ Alpha    │ Unusual  │ Economic Calendar    │
│ (Options)│ (News)   │ Vantage  │ Whales   │ (Market Events)      │
│          │          │(Sentiment)│(Options)│                      │
└──────────┴──────────┴──────────┴──────────┴──────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │   DATA AGGREGATOR     │
                    │  ├─ Cache Manager     │
                    │  ├─ Rate Limiter      │
                    │  └─ DB Storage        │
                    └───────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
        ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
        │ STRATEGIES   │ │ PROBABILITY  │ │ MARKET       │
        │              │ │ ENGINE       │ │ CONTEXT      │
        ├──────────────┤ ├──────────────┤ ├──────────────┤
        │- Opening R.  │ │- IV Rank     │ │- Correlation│
        │- Directional │ │- Greeks      │ │- Sentiment  │
        │- Spreads     │ │- Win Rate    │ │- Macro      │
        │- Iron Condor │ │- Risk/Reward │ │- Volatility │
        │- Momentum    │ └──────────────┘ └──────────────┘
        │- Mean Rev.   │
        └──────────────┘
                │
                └─────────────────────┐
                                      ▼
                        ┌──────────────────────────┐
                        │  SIGNAL AGGREGATOR       │
                        │  (Weighted Combination)  │
                        └──────────────────────────┘
                                      │
                ┌─────────────────────┼─────────────────────┐
                ▼                     ▼                     ▼
        ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐
        │  RISK MANAGER   │  │  POSITION SIZER │  │ STRIKE/EXP   │
        │  (Hardcoded)    │  │ (Half-Kelly)    │  │ SELECTOR     │
        └─────────────────┘  └─────────────────┘  └──────────────┘
                │
                └─────────────────────┐
                                      ▼
                        ┌──────────────────────────┐
                        │  THREE OPERATION MODES   │
                        └──────────────────────────┘
                ┌───────────────────┬────────────────┬──────────────┐
                ▼                   ▼                ▼              ▼
        ┌──────────────┐   ┌──────────────┐  ┌──────────────┐
        │   SIGNAL     │   │  SEMI-AUTO   │  │  FULL-AUTO   │
        │   MODE       │   │  MODE        │  │  MODE        │
        ├──────────────┤   ├──────────────┤  ├──────────────┤
        │ Push alerts  │   │ One-click    │  │ Auto-execute │
        │ Dashboard    │   │ confirmation │  │ with limits  │
        │ Only suggest │   │ Then execute │  │ Constant     │
        │              │   │              │  │ monitoring   │
        └──────────────┘   └──────────────┘  └──────────────┘
                │                 │                │
                └─────────────────┴────────────────┤
                                      ▼
                        ┌──────────────────────────┐
                        │  BROKER INTEGRATION      │
                        │ (TastyTrade/Alpaca/Paper)│
                        └──────────────────────────┘
                                      │
                ┌─────────────────────┼─────────────────────┐
                ▼                     ▼                     ▼
        ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
        │  LIVE TRADES │     │  MONITORING  │     │  P&L TRACKING│
        │              │     │              │     │              │
        └──────────────┘     └──────────────┘     └──────────────┘
                │
                └─────────────────────┐
                                      ▼
                        ┌──────────────────────────┐
                        │  DASHBOARD (Web UI)      │
                        │  ├─ Real-time signals    │
                        │  ├─ P&L tracker          │
                        │  ├─ Risk exposure        │
                        │  ├─ Trading history      │
                        │  ├─ Economic calendar    │
                        │  └─ Alert settings       │
                        └──────────────────────────┘
```

### Operating Modes

| Mode | User | Workflow | Use Case |
|------|------|----------|----------|
| **Signal/Alert** | Beginner | Bot identifies signals → Dashboard notification → Manual execution | Learning, testing, low confidence |
| **Semi-Auto** | Intermediate | Bot identifies signals → One-click confirmation → Auto execute | Comfortable with decisions but want speed |
| **Full-Auto** | Advanced | Bot executes directly with safeguards | Consistent strategy, trusted system |

---

## 2. Tech Stack

### Core Requirements

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Language** | Python 3.11+ | Vast finance libraries, beginner-friendly |
| **Web Framework** | FastAPI | Async support, WebSocket real-time updates, automatic docs |
| **Database** | SQLite | No server setup, perfect for single-trader, local first |
| **Frontend** | Vanilla HTML/JS | No build step, beginner-friendly, lightweight |
| **WebSocket** | FastAPI + websockets | Real-time signal delivery to dashboard |

### Core Libraries

```
# Data Processing & Analysis
pandas==2.0+              # Data manipulation
pandas-ta==0.3.14b       # Technical analysis indicators
numpy==1.24+             # Numerical computing

# Options & Greeks Calculation
py_vollib==0.1.20        # IV, Greeks calculation
scipy==1.10+             # Scientific computing

# Market Data APIs (see Section 7 for details)
aiohttp==3.8+            # Async HTTP client
websockets==11.0+        # WebSocket client
requests==2.31+          # HTTP requests (fallback)

# Broker APIs
# tastytrade-api          # TastyTrade integration
# alpaca-py               # Alpaca integration

# Web Framework & AsyncIO
fastapi==0.104+          # Web framework
uvicorn==0.24+           # ASGI server
pydantic==2.0+           # Data validation
python-dotenv==1.0+      # Environment variables

# Logging & Monitoring
python-json-logger==2.0+ # Structured logging
pytz==2024.1             # Timezone handling

# Development
pytest==7.4+             # Testing
black==23.0+             # Code formatting
flake8==6.0+             # Linting
```

### Why These Choices?

- **FastAPI**: Automatic async support for handling multiple data sources concurrently
- **SQLite**: No infrastructure overhead, great for local-first development
- **Vanilla JS**: No npm/webpack complexity—just HTML, CSS, JS in static folder
- **pandas-ta**: Pre-built indicators for technical analysis (RSI, MACD, Bollinger Bands, etc.)
- **py_vollib**: Industry-standard Greeks calculation (Delta, Gamma, Theta, Vega, Rho)
- **WebSockets**: Push updates to dashboard in real-time without polling

---

## 3. Project Structure

### Complete Directory Tree

```
ai-trading-bot/
├── config/
│   ├── __init__.py
│   ├── settings.py          # Central configuration (all env-driven)
│   ├── api_keys.py.example  # Template (copy to .env, never commit)
│   ├── constants.py         # Hard limits, mode configurations
│   └── logging_config.py    # Logging setup
│
├── data/
│   ├── __init__.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py          # BaseProvider abstract class
│   │   ├── polygon.py       # Real-time SPX/SPY options data
│   │   ├── finnhub.py       # News, earnings calendar, sentiment
│   │   ├── alpha_vantage.py # Sentiment score, RSI alerts
│   │   ├── unusual_whales.py # Options flow, unusual activity
│   │   └── cache.py         # In-memory cache with TTL
│   │
│   ├── storage.py           # SQLite ORM layer (no external ORM)
│   ├── market_data.py       # Current market data aggregation
│   └── refresh_service.py   # Background data refresh loop
│
├── strategies/
│   ├── __init__.py
│   ├── base.py              # BaseStrategy abstract class
│   ├── opening_range.py      # 0DTE Opening Range Breakout (9:45-10:30 breakout)
│   ├── directional.py        # Call/Put buying on sentiment + technicals
│   ├── credit_spreads.py     # High IV rank → sell spreads
│   ├── iron_condor.py        # Range-bound → straddle-lite
│   ├── momentum.py           # Trend following (20/50/200 MA)
│   └── mean_reversion.py     # Oversold/Overbought (RSI, Bollinger)
│
├── engine/
│   ├── __init__.py
│   ├── signal_aggregator.py # Weighted combination of all strategies
│   ├── probability.py       # IV Rank, Win Rate calc, Greeks scoring
│   ├── risk_manager.py      # PDT tracking, position limits, Greeks limits
│   ├── pattern_analyzer.py  # Historical backtesting, pattern matching
│   ├── market_context.py    # Correlation, macro sentiment, volatility regime
│   └── position_tracker.py  # Current open positions, Greeks summary
│
├── broker/
│   ├── __init__.py
│   ├── base.py              # BaseBroker abstract interface
│   ├── tastytrade.py        # TastyTrade API integration
│   ├── alpaca.py            # Alpaca API integration
│   └── paper.py             # Paper trading (simulated execution)
│
├── dashboard/
│   ├── __init__.py
│   ├── app.py               # FastAPI application setup
│   ├── api_routes.py        # REST API endpoints
│   ├── websocket.py         # WebSocket connection handlers
│   ├── schemas.py           # Pydantic response models
│   └── static/
│       ├── index.html       # Main dashboard HTML
│       ├── styles.css       # Minimal CSS styling
│       ├── app.js           # Frontend JavaScript logic
│       └── charts.js        # Chart rendering (Chart.js)
│
├── utils/
│   ├── __init__.py
│   ├── logger.py            # Structured logging setup
│   ├── greeks.py            # Greeks helper functions
│   ├── indicators.py        # Technical indicator wrappers
│   ├── validators.py        # Input validation
│   └── decorators.py        # Rate limiting, caching decorators
│
├── tests/
│   ├── __init__.py
│   ├── test_strategies.py   # Strategy unit tests
│   ├── test_signal_agg.py   # Signal aggregation tests
│   ├── test_risk_manager.py # Risk rule validation
│   └── test_broker.py       # Broker API mock tests
│
├── main.py                  # Entry point (CLI + daemon)
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── .gitignore               # Exclude .env, __pycache__, venv
├── README.md                # User setup guide
└── ARCHITECTURE.md          # This document
```

### Key Design Patterns

- **Abstract Base Classes**: `BaseProvider`, `BaseStrategy`, `BaseBroker` for extensibility
- **Dependency Injection**: Pass dependencies to classes (testable, no globals)
- **Async/Await**: All I/O operations use `asyncio` for concurrency
- **Configuration as Code**: `settings.py` centralizes all tuning parameters
- **No External ORM**: Raw SQL in `storage.py` keeps it simple and transparent

---

## 4. Data Flow Architecture

### Complete Request Flow (from market data to dashboard)

```
┌─────────────────┐
│  Market Opens   │
│   (9:30 AM ET)  │
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────┐
│ REFRESH SERVICE (5-10s interval) │
│ ├─ Async HTTP requests to APIs   │
│ ├─ Deserialize JSON              │
│ └─ Update SQLite + Cache         │
└────────┬─────────────────────────┘
         │
         ├──────────────────────┬──────────────────────┐
         ▼                      ▼                      ▼
    ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
    │ Price Feed  │       │ News/Earnings│      │Options Flows│
    │ - SPX/SPY   │       │ - Headlines │       │ - Unusual   │
    │ - Greeks    │       │ - Calendar  │       │ - Levels    │
    │ - IV Rank   │       │ - Sentiment │       │ - Volume    │
    └─────────────┘       └─────────────┘       └─────────────┘
         │
         └──────────────────────┬──────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  STRATEGY ENGINE      │
                    │  (Runs every 5s)      │
                    └───────────────────────┘
                                │
        ┌───────────┬───────────┼───────────┬──────────────┐
        │           │           │           │              │
        ▼           ▼           ▼           ▼              ▼
    ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐
    │Opening │ │Directio│ │Spreads │ │Iron    │ │Momentum/ │
    │Range   │ │nal     │ │Credit  │ │Condor  │ │MeanRev   │
    └────┬───┘ └───┬────┘ └───┬────┘ └───┬────┘ └────┬─────┘
         │         │          │          │           │
         └─────────┼──────────┼──────────┼───────────┘
                   │          │          │
                   ▼          ▼          ▼
        ┌──────────────────────────────────┐
        │  PROBABILITY SCORING ENGINE      │
        │  ├─ IV Rank adjustment           │
        │  ├─ Greeks risk assessment       │
        │  ├─ Historical win rate          │
        │  └─ Risk/Reward ratio            │
        └──────────────────────────────────┘
                   │
                   ▼
        ┌──────────────────────────────────┐
        │  SIGNAL AGGREGATOR               │
        │  ├─ Weight by confidence         │
        │  ├─ Market regime filter         │
        │  └─ Correlation check            │
        └──────────────────────────────────┘
                   │
                   ▼
        ┌──────────────────────────────────┐
        │  RISK MANAGER VALIDATION         │
        │  ├─ Max 1-2% risk check          │
        │  ├─ Daily loss limit check       │
        │  ├─ PDT counter check            │
        │  └─ Greeks exposure check        │
        └──────────────────────────────────┘
         │
         ├─ SIGNAL REJECTED ──→ Log rejection reason
         │
         └─ SIGNAL APPROVED ──┐
                              │
                              ▼
                    ┌───────────────────────┐
                    │  FINAL RECOMMENDATION │
                    │  {                    │
                    │    action: "BUY CALL",│
                    │    strike: 5850,      │
                    │    expiry: "2d",      │
                    │    entry: 145.50,     │
                    │    stop: 130.00,      │
                    │    target: 160.00,    │
                    │    size: 1 contract,  │
                    │    confidence: 78%,   │
                    │    risk_amt: $87      │
                    │  }                    │
                    └───────────────────────┘
                              │
                ┌─────────────┼─────────────┐
                │             │             │
                ▼             ▼             ▼
            ┌────────┐  ┌────────────┐ ┌──────────┐
            │SIGNAL  │  │SEMI-AUTO   │ │FULL-AUTO │
            │MODE    │  │MODE        │ │MODE      │
            │        │  │            │ │          │
            │Log DB  │  │Wait for UI │ │Auto-exec │
            │Push to │  │confirmation│ │w/ safegds│
            │WS      │  │→ Log & Send│ │Log & Send│
            └────────┘  └────────────┘ └──────────┘
                │             │             │
                └─────────────┴─────────────┘
                              │
                              ▼
                    ┌───────────────────────┐
                    │  BROKER EXECUTION     │
                    │  (TastyTrade/Alpaca)  │
                    └───────────────────────┘
                              │
                              ▼
                    ┌───────────────────────┐
                    │  TRADE MONITORING     │
                    │  ├─ Live P&L update   │
                    │  ├─ Greeks tracking   │
                    │  ├─ Stop loss check   │
                    │  └─ Profit target chk │
                    └───────────────────────┘
                              │
                              ▼
                    ┌───────────────────────┐
                    │  DASHBOARD WS PUSH    │
                    │  ├─ Trade execution   │
                    │  ├─ P&L update        │
                    │  ├─ Signal history    │
                    │  └─ Risk exposure     │
                    └───────────────────────┘
```

### Data Refresh Intervals

```
Interval     Data Source          Purpose
──────────────────────────────────────────────────────────────
5 seconds    Polygon (price, IV)   Real-time signal generation
15 seconds   Options flow (UW)     Unusual activity detection
30 seconds   News (FinnHub)        Sentiment shifts
1 minute     Greeks (calculated)   Position risk update
5 minutes    Economic calendar     Macro event monitoring
Daily (EOD)  Backup historical     Archive daily data
```

---

## 5. Signal Scoring System

### Philosophy

Each strategy produces an **independent score from -100 to +100**, representing conviction:
- **-100**: Extreme short bias (buy puts hard)
- **-50 to 0**: Moderate short bias
- **0**: Neutral/no signal
- **+50 to +100**: Bullish (buy calls)

A **confidence level (0-100%)** reflects signal strength based on:
- Agreement across indicators
- Historical win rate
- Current market regime
- Greeks favorability

### Individual Strategy Scoring

#### 1. Opening Range Breakout (0DTE Focus)

```python
Score Calculation:
  base_score = 0

  # Price action (primary)
  if price > opening_range_high:
    base_score += 40  # Bullish break
  elif price < opening_range_low:
    base_score -= 40  # Bearish break
  else:
    base_score = 0    # No break, no signal

  # Volume confirmation
  if volume > 30d_avg_volume * 1.5:
    base_score += 20  # High volume confirms break
  else:
    base_score += 5   # Low volume weakens signal

  # IV Rank adjustment
  if iv_rank > 70:
    base_score += 15  # High IV inflates options prices
  elif iv_rank < 30:
    base_score -= 10  # Low IV makes options cheap but offers less reward

  # Result: Score from -100 to +100
  confidence = min(100, abs(base_score) + agreement_bonus)
```

**Entry Logic:**
- Time: 9:45 AM - 10:30 AM ET (0DTE signal window)
- Opening Range: 9:30 - 10:00 AM high/low
- If SPX breaks above, suggest BUY CALL
- If SPX breaks below, suggest BUY PUT
- Expiry: Same-day (0DTE) for max leverage
- Strike: 1-2 strikes OTM

---

#### 2. Directional (Sentiment + Technical)

```python
Score Calculation:
  technicals_score = 0

  # RSI signal
  if rsi > 70:
    technicals_score -= 30  # Overbought → put bias
  elif rsi < 30:
    technicals_score += 30  # Oversold → call bias
  else:
    technicals_score += (rsi - 50) * 0.6  # Neutral lean

  # MACD signal
  if macd > signal_line:
    technicals_score += 20  # Bullish momentum
  else:
    technicals_score -= 20  # Bearish momentum

  # Bollinger Bands
  if price > bb_upper:
    technicals_score -= 15  # Overbought
  elif price < bb_lower:
    technicals_score += 15  # Oversold

  # Sentiment overlay (from FinnHub news)
  sentiment_score = sentiment_score * 25  # Bias: -25 to +25

  # Combine
  base_score = (technicals_score * 0.7) + (sentiment_score * 0.3)
  confidence = 50 + (abs(technicals_score) * 0.3) + (abs(sentiment_score) * 0.2)
```

**Entry Logic:**
- If score > +60: Suggest BUY CALL (3-5 DTE)
- If score < -60: Suggest BUY PUT (3-5 DTE)
- Strike: At-money or 1 strike OTM
- Size: 1 contract (fixed for beginners)

---

#### 3. Credit Spreads (High IV Rank)

```python
Score Calculation:
  if iv_rank < 30:
    return 0  # Too low IV → not enough premium, skip

  base_score = 0

  # IV Rank drives spreads
  iv_percentile = (iv_rank / 100) * 50  # Scale to ±50
  base_score = iv_percentile

  # Direction from technicals
  if rsi > 60:
    base_score -= 20  # More likely down → sell call spreads
  elif rsi < 40:
    base_score += 20  # More likely up → sell put spreads

  # Add correlation bias
  if spy_correlation > 0.8:
    base_score *= 1.1  # SPX and SPY move together, strengthen signal

  confidence = 40 + (iv_rank / 2)  # High IV = high confidence
```

**Entry Logic:**
- IV Rank > 50: Generate spread signals
- If bullish technicals: Sell PUT SPREAD (collect premium, benefit from theta)
- If bearish technicals: Sell CALL SPREAD
- Strike: 10-15 delta short leg
- Expiry: 7-21 DTE (balance theta decay vs. time value)

---

#### 4. Iron Condor (Range-Bound)

```python
Score Calculation:
  # Iron Condor is "do nothing" bet—works when market stays in range

  # Bollinger Band width
  bb_width = (bb_upper - bb_lower) / sma_20
  if bb_width < 0.03:  # Narrow bands = low volatility
    return 0  # Not enough movement for range trade

  # Support/Resistance levels (via recent price history)
  support = min(close[-20:])
  resistance = max(close[-20:])
  range_ratio = (resistance - support) / support

  if 0.02 < range_ratio < 0.05:  # Tight 2-5% range
    base_score = 30  # Good for IC
  else:
    base_score = 0  # Too much movement risk

  confidence = 35 + (bb_width * 1000)  # Low confidence trade
```

**Entry Logic:**
- For 0DTE/1DTE when price confined to clear range
- Sell PUT at support, Sell CALL at resistance
- Target profit: 50% of max spread width
- Risk: 50% of max spread width

---

#### 5. Momentum (Trend Following)

```python
Score Calculation:
  ma_20 = moving_avg(close, 20)
  ma_50 = moving_avg(close, 50)
  ma_200 = moving_avg(close, 200)

  base_score = 0

  # Golden Cross / Death Cross
  if ma_20 > ma_50 > ma_200:
    base_score = +50  # Strong uptrend
  elif ma_20 < ma_50 < ma_200:
    base_score = -50  # Strong downtrend
  else:
    base_score = 0  # Mixed signals

  # Acceleration check (price vs. MA)
  if price > ma_20 and (close - open) > 0:
    base_score += 20  # Accelerating up
  elif price < ma_20 and (close - open) < 0:
    base_score -= 20  # Accelerating down

  # Recent momentum (ROC)
  roc_5d = ((close[-1] - close[-5]) / close[-5]) * 100
  base_score += (roc_5d * 0.5)  # Add ROC bias (capped)

  confidence = 60 + (abs(base_score) * 0.2)  # High confidence on trends
```

**Entry Logic:**
- If score > +70 and MA trend aligned: BUY CALL (3-5 DTE, ATM)
- If score < -70 and MA trend aligned: BUY PUT (3-5 DTE, ATM)
- Size: 1-2 contracts
- Exit: At profit target or on trend break

---

#### 6. Mean Reversion

```python
Score Calculation:
  # Bollinger Band squeeze + RSI divergence
  rsi_val = rsi(close, 14)
  bb_position = (close - bb_lower) / (bb_upper - bb_lower)

  base_score = 0

  # RSI extremes
  if rsi_val < 20:
    base_score = +60  # Extremely oversold
  elif rsi_val > 80:
    base_score = -60  # Extremely overbought
  else:
    base_score = 0

  # Recent move (5-10% swings indicate reversal opportunity)
  recent_move = abs((close[-1] - close[-10]) / close[-10]) * 100
  if recent_move > 3:
    base_score *= 1.2  # Strong move before reversal

  # Historical volatility reversion
  if realized_vol > average_vol * 1.5:
    base_score *= 1.15  # High vol reverts to mean

  confidence = 40 + (abs(rsi_val - 50) / 50) * 40  # Extreme RSI = confidence
```

**Entry Logic:**
- When RSI < 25 + technicals bearish: BUY PUT (mean reversion down)
- When RSI > 75 + technicals bullish: BUY CALL (mean reversion up)
- Expiry: 1-3 DTE (quick reversal)
- Strike: 1-2 OTM
- Target: Return to 20-MA

---

### Signal Aggregation & Weighting

```python
# PSEUDO-CODE: Signal Aggregator

def aggregate_signals(signals: Dict[str, Signal]) -> AggregatedSignal:
    """
    Combine all strategy signals into final recommendation.

    signals = {
        'opening_range': Signal(score=45, confidence=85),
        'directional': Signal(score=30, confidence=70),
        'credit_spreads': Signal(score=20, confidence=60),
        'iron_condor': Signal(score=0, confidence=0),
        'momentum': Signal(score=35, confidence=75),
        'mean_reversion': Signal(score=15, confidence=40),
    }
    """

    # Filter out weak or missing signals
    valid_signals = {
        k: v for k, v in signals.items()
        if v.confidence >= 40  # Only use signals with ≥40% confidence
    }

    if not valid_signals:
        return AggregatedSignal(action='HOLD', confidence=0, reason='No strong signals')

    # Weighted sum (weight by confidence)
    total_weight = sum(s.confidence for s in valid_signals.values())
    weighted_score = sum(
        s.score * (s.confidence / total_weight)
        for s in valid_signals.values()
    )

    # Market context adjustment
    market_context_adjustment = get_market_context_adjustment()  # ±30 points
    weighted_score += market_context_adjustment

    # Clamp score to [-100, +100]
    weighted_score = max(-100, min(100, weighted_score))

    # Aggregate confidence
    avg_confidence = np.mean([s.confidence for s in valid_signals.values()])
    final_confidence = min(100, avg_confidence * 1.1)  # Slight boost for agreement

    # Final recommendation
    if weighted_score > 60:
        action = 'BUY CALL'
        intensity = 'STRONG' if weighted_score > 80 else 'MODERATE'
    elif weighted_score < -60:
        action = 'BUY PUT'
        intensity = 'STRONG' if weighted_score < -80 else 'MODERATE'
    elif weighted_score > 30:
        action = 'BUY CALL'
        intensity = 'WEAK'
    elif weighted_score < -30:
        action = 'BUY PUT'
        intensity = 'WEAK'
    else:
        action = 'HOLD'
        intensity = 'NEUTRAL'

    return AggregatedSignal(
        action=action,
        intensity=intensity,
        score=weighted_score,
        confidence=final_confidence,
        constituent_signals=valid_signals,
    )
```

### Final Recommendation Format

```json
{
    "timestamp": "2024-03-20T14:23:45Z",
    "action": "BUY CALL",
    "intensity": "STRONG",
    "aggregate_score": 72,
    "confidence": 82,
    "rationale": "Opening range breakout + strong momentum + oversold technicals",

    "entry": {
        "underlying": "SPX",
        "contract_type": "CALL",
        "strike": 5850,
        "expiry": "2024-03-20",  // 0DTE
        "entry_price": 145.50,
        "quantity": 1
    },

    "risk_management": {
        "stop_loss": 130.00,
        "profit_target": 160.00,
        "risk_amount": 87.50,  // 1.75% of $5K
        "reward_amount": 287.50,
        "risk_reward_ratio": 3.3
    },

    "greeks": {
        "delta": 0.72,
        "gamma": 0.008,
        "theta": -0.15,
        "vega": 0.45,
        "probability_itm": 0.74
    },

    "position_sizing": {
        "kelly_fraction": 0.25,
        "suggested_size": 1,
        "max_size": 2,
        "pct_of_capital": 1.75
    },

    "market_regime": {
        "iv_rank": 65,
        "volatility_regime": "Normal",
        "correlation_regime": "Positive",
        "macro_sentiment": "Neutral"
    }
}
```

---

## 6. Risk Management Rules

### Hardcoded Constraints (Non-Negotiable)

All rules are enforced **before** any trade execution, regardless of signal strength.

#### 6.1 Position Sizing (Half-Kelly Criterion)

```python
def calculate_position_size(
    win_rate: float,           # Historical strategy win rate
    avg_win: float,           # Average $ gain on winners
    avg_loss: float,          # Average $ loss on losers
    account_equity: float,    # Current account balance
    max_risk_pct: float = 0.015,  # 1.5% max risk per trade
) -> int:
    """
    Kelly Criterion: f* = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
    Half-Kelly: f = f* / 2  (conservative: f / 2)

    Position size in $ = account_equity * half_kelly
    """

    if win_rate <= 0 or win_rate >= 1:
        return 1  # Safety: use 1 contract

    # Kelly formula
    kelly_f = (
        (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
    ) / avg_win

    # Half Kelly (conservative)
    half_kelly = kelly_f / 2

    # Cap at reasonable range [0.5%, 3%]
    risk_pct = np.clip(half_kelly, 0.005, 0.03)
    risk_amt = account_equity * risk_pct

    # Account for trade loss amount (from stop loss)
    contracts = max(1, int(risk_amt / abs(avg_loss)))

    # Enforce max 1-2 contracts for options (low capital account)
    return min(contracts, 2)

# Example:
# win_rate = 0.55, avg_win = $150, avg_loss = $85
# account = $5000, max_risk = 1.5%
# kelly_f = (0.55*150 - 0.45*85) / 150 = 0.205
# half_kelly = 0.1025 (≈1% risk)
# risk_amt = $5000 * 0.01 = $50
# contracts = $50 / $85 = 0.58 → 1 contract
```

#### 6.2 Daily Loss Limit (Hard Stop)

```python
def check_daily_loss_limit(
    daily_realized_pnl: float,
    daily_unrealized_pnl: float,
    account_equity: float,
    max_daily_loss_pct: float = 0.02,  # -2% max daily loss
) -> bool:
    """
    Calculate current daily loss. If at/below limit, reject new trades.
    """

    total_daily_pnl = daily_realized_pnl + daily_unrealized_pnl
    daily_loss_pct = total_daily_pnl / account_equity

    if daily_loss_pct <= -max_daily_loss_pct:
        logger.warning(
            f"Daily loss limit hit: {daily_loss_pct:.2%} of {daily_loss_pct:.2%} allowed"
        )
        return False  # Reject new trades

    return True  # OK to trade
```

#### 6.3 Per-Trade Risk Limit (1-2% per trade)

```python
def validate_trade_risk(
    entry_price: float,
    stop_loss_price: float,
    quantity: int,
    contract_multiplier: int = 100,  # Options contracts
    account_equity: float,
    max_risk_pct: float = 0.02,  # 2% max per trade
) -> bool:
    """
    Ensure single trade risk is ≤ 2% of account.

    Risk $ = (entry - stop) * quantity * multiplier
    Risk % = Risk $ / account_equity
    """

    per_contract_loss = abs(entry_price - stop_loss_price) * contract_multiplier
    total_loss = per_contract_loss * quantity
    risk_pct = total_loss / account_equity

    if risk_pct > max_risk_pct:
        logger.warning(
            f"Trade exceeds risk limit: {risk_pct:.2%} > {max_risk_pct:.2%}"
        )
        return False

    return True
```

#### 6.4 PDT Tracking & Enforcement

```python
def check_pdt_limits(
    day_trades_today: int,
    trades_this_week: list,  # [(date, count), ...]
    account_equity: float,
    max_day_trades: int = 3,  # PDT rule
) -> bool:
    """
    Pattern Day Trader rules (US):
    - Cannot execute more than 3 day trades in 5 business days
    - Account minimum: $25,000 (we have $5,000, so strict)

    Strategy: Count "round-trip" trades (open + close same day)
    """

    # Count day trades in past 5 business days
    five_days_ago = datetime.now() - timedelta(days=5)
    recent_day_trades = sum(
        count for date, count in trades_this_week
        if date >= five_days_ago
    )

    if recent_day_trades >= max_day_trades:
        logger.warning(
            f"PDT limit reached: {recent_day_trades} day trades in 5 days"
        )
        return False

    return True
```

#### 6.5 Greeks-Based Position Limits

```python
def validate_greeks_exposure(
    portfolio_delta: float,    # Sum of all position deltas
    portfolio_theta: float,    # Sum of all position thetas
    portfolio_vega: float,     # Sum of all position vegas
    max_delta: float = 2.0,    # Can hold up to 2 delta equivalent
    max_vega: float = 5.0,     # Can hold up to 5 vega exposure
    max_theta: float = -0.5,   # Can lose up to $0.50/day to theta
) -> bool:
    """
    Prevent over-concentrated directional or volatility exposure.
    """

    checks = {
        'delta': abs(portfolio_delta) <= max_delta,
        'vega': abs(portfolio_vega) <= max_vega,
        'theta': portfolio_theta >= max_theta,  # Note: theta is negative
    }

    for greek, valid in checks.items():
        if not valid:
            logger.warning(f"Greeks limit exceeded: {greek}")
            return False

    return True
```

#### 6.6 Naked Options Prohibition

```python
def validate_no_naked_options(positions: List[Position]) -> bool:
    """
    Enforce: No naked calls, no naked puts.
    All short options must be hedged.
    """

    for pos in positions:
        if pos.type == 'short':
            # For beginners: require spread (long + short) structure
            has_long_leg = any(
                p.type == 'long' and
                p.underlying == pos.underlying and
                p.expiry == pos.expiry and
                p.strike_comparison_ok(pos.strike)  # OTM from short
                for p in positions
            )
            if not has_long_leg:
                logger.error(f"Naked short detected: {pos}. Spreads only.")
                return False

    return True
```

#### 6.7 Operational Rules Summary

| Rule | Limit | Check | Action |
|------|-------|-------|--------|
| **Per-Trade Risk** | 1-2% of equity | Before execution | Reject if exceeds |
| **Daily Loss** | -2% cumulative | Every trade check | Halt if hit |
| **PDT Day Trades** | ≤3 in 5 days | Before execution | Reject if would exceed |
| **Max Contracts/Trade** | 2 | Before execution | Cap at 2 |
| **Portfolio Delta** | ±2.0 | Position check | Reduce if exceeded |
| **Portfolio Vega** | ±5.0 | Position check | Reduce if exceeded |
| **Portfolio Theta** | ≥-$0.50/day | Daily check | Reduce if exceeded |
| **Naked Options** | 0 allowed | Position validation | Reject naked short |

---

## 7. API Integration Plan

### Data Providers & Cost Structure

#### 1. **Polygon.io** - Real-Time Options Data

| Aspect | Details |
|--------|---------|
| **Cost** | $99/month (Pro tier) |
| **What We Get** | • Real-time SPX/SPY option chains • Greeks (delta, gamma, theta, vega) • IV Rank calculation • Volume/OI • Last trade price & time |
| **Rate Limits** | 600 requests/minute (10/sec) |
| **Refresh Interval** | 5-10 seconds (during market hours) |
| **Coverage** | All US equity options, real-time |
| **Latency** | <100ms after print |
| **Key Endpoint** | `/v3/snapshot/options/{ticker}/chains` |

**Implementation:**
```python
# data/providers/polygon.py
class PolygonProvider(BaseProvider):
    async def get_option_chain(self, ticker: str) -> dict:
        """Fetch full SPX option chain with Greeks."""
        # Hit endpoint, parse chain, calculate IV Rank
        # Cache for 5 seconds
        # Return: {strike: {call: {...}, put: {...}}, iv_rank: XX}

    async def get_greeks(self, contract_id: str) -> dict:
        """Get real-time Greeks for specific contract."""
        # Return: {delta, gamma, theta, vega, rho}
```

---

#### 2. **FinnHub** - News, Sentiment, Economic Calendar

| Aspect | Details |
|--------|---------|
| **Cost** | $49/month (Plus tier) |
| **What We Get** | • Real-time market news • Earnings calendar • Economic events (CPI, jobs, FOMC) • Sentiment score • Company news • Insider trading |
| **Rate Limits** | 60 requests/minute (1/sec) |
| **Refresh Interval** | 30 seconds (news) / Real-time (calendar events) |
| **Coverage** | Global market news, US-focused calendar |
| **Latency** | 5-10 seconds behind market events |
| **Key Endpoints** | `/news`, `/calendar/economic`, `/calendar/earnings` |

**Implementation:**
```python
# data/providers/finnhub.py
class FinnhubProvider(BaseProvider):
    async def get_news(self, ticker: str = "SPX") -> List[dict]:
        """Latest news with sentiment."""
        # Return: [{headline, sentiment, timestamp, source}, ...]

    async def get_economic_calendar(self) -> List[dict]:
        """Next economic events."""
        # Return: [{event, forecast, actual, impact}, ...]

    def sentiment_score(self, articles: List[dict]) -> float:
        """Aggregate sentiment from articles."""
        # Return: -1.0 (very bearish) to +1.0 (very bullish)
```

---

#### 3. **Alpha Vantage** - Technical Analysis & Sentiment

| Aspect | Details |
|--------|---------|
| **Cost** | Free tier (5/min), $20/month (Premium) |
| **What We Get** | • Sentiment score (news sentiment, social media) • Technical indicators (SMA, RSI, BBANDS, MACD) • Intraday OHLC data • Volume analysis |
| **Rate Limits** | 5/min free, 300/min premium |
| **Refresh Interval** | 1-5 minutes (intraday) |
| **Coverage** | US equities, limited to major symbols |
| **Latency** | 5-15 minute delay |
| **Key Endpoints** | `/query?function=SENTIMENT`, `/query?function=RSI` |

**Implementation:**
```python
# data/providers/alpha_vantage.py
class AlphaVantageProvider(BaseProvider):
    async def get_sentiment(self, ticker: str) -> dict:
        """Daily sentiment score."""
        # Return: {overall_sentiment, articles_count, bullish_pct, bearish_pct}

    async def get_indicators(self, ticker: str) -> dict:
        """Technical indicators."""
        # Return: {rsi, macd, bb_upper, bb_lower, bb_mid, sma_20, sma_50}
```

---

#### 4. **Unusual Whales** - Options Flow Intelligence

| Aspect | Details |
|--------|---------|
| **Cost** | $20/month (Flow API) |
| **What We Get** | • Unusual options activity (alerts) • Large option blocks/spreads • Options imbalance • Volume concentration • Smart money signals |
| **Rate Limits** | 100 requests/hour |
| **Refresh Interval** | Real-time (but batched by UW) |
| **Coverage** | US equity options |
| **Latency** | 1-5 seconds after execution |
| **Key Endpoints** | `/alerts`, `/flow`, `/imbalance` |

**Implementation:**
```python
# data/providers/unusual_whales.py
class UnusualWhalesProvider(BaseProvider):
    async def get_alerts(self) -> List[dict]:
        """Live unusual activity alerts."""
        # Return: [{ticker, contract, volume, size, direction, confidence}, ...]

    async def get_imbalance(self, ticker: str) -> dict:
        """Call vs put imbalance."""
        # Return: {call_volume, put_volume, put_call_ratio, trend}
```

---

#### 5. **Alpaca Markets** - Market Data (Fallback)

| Aspect | Details |
|--------|---------|
| **Cost** | Free |
| **What We Get** | • 15-minute delayed stock prices (real-time for paid) • Minute-bar data • Daily OHLCV • Snapshots |
| **Rate Limits** | Varies by tier |
| **Coverage** | US stocks only (SPX/SPY available) |
| **Note** | Free tier has 15m delay; fine as fallback |

---

#### 6. **Economic Calendar** (Alternative)

For free economic calendar, we can use:
- **Investing.com API** (free, limited)
- **TradingView Webhook** (free, via calendar integration)
- **FRED API** (Federal Reserve data, free)

---

### Total Monthly Data Cost Estimate

```
Polygon.io       $99   (Real-time options)
FinnHub          $49   (News + calendar)
Alpha Vantage    $20   (Sentiment + technicals)
Unusual Whales   $20   (Options flow)
────────────────────
TOTAL           $188/month (within $100-300 budget)
```

### API Rate Limiting & Caching Strategy

```python
# data/providers/cache.py
class CacheManager:
    def __init__(self):
        self.cache = {}
        self.ttl = {  # Seconds
            'option_chain': 5,
            'greeks': 5,
            'iv_rank': 5,
            'news': 30,
            'sentiment': 300,
            'technical': 60,
            'economic_calendar': 3600,  # 1 hour
        }

    async def get_or_fetch(self, key: str, fetch_fn, *args):
        """Check cache first, fetch if expired."""
        if key in self.cache:
            if time.time() - self.cache[key]['timestamp'] < self.ttl.get(key, 60):
                return self.cache[key]['value']

        value = await fetch_fn(*args)
        self.cache[key] = {'value': value, 'timestamp': time.time()}
        return value

# Rate limiter
class RateLimiter:
    def __init__(self, calls_per_second: float):
        self.calls_per_second = calls_per_second
        self.last_call = 0

    async def wait(self):
        """Async wait to respect rate limit."""
        elapsed = time.time() - self.last_call
        min_interval = 1.0 / self.calls_per_second
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        self.last_call = time.time()
```

---

## 8. Database Schema

### SQLite Tables

#### Table 1: `signals` - All generated signals (audit trail)

```sql
CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Signal metadata
    underlying TEXT NOT NULL,  -- 'SPX' or 'SPY'
    action TEXT NOT NULL,      -- 'BUY_CALL', 'BUY_PUT', 'SELL_CALL_SPREAD', 'SELL_PUT_SPREAD', 'IRON_CONDOR', 'HOLD'
    intensity TEXT,            -- 'STRONG', 'MODERATE', 'WEAK', 'NEUTRAL'

    -- Scoring
    aggregate_score REAL,      -- -100 to +100
    confidence REAL,           -- 0-100%

    -- Constituent signals (JSON)
    constituent_signals TEXT,  -- JSON: {"opening_range": {score, confidence}, ...}

    -- Market context
    iv_rank REAL,
    volatility_regime TEXT,    -- 'Low', 'Normal', 'High'
    sentiment_score REAL,      -- -1.0 to +1.0

    -- Recommendation details
    entry_contract TEXT,       -- '2024-03-20 CALL 5850'
    entry_price REAL,
    stop_loss REAL,
    profit_target REAL,
    suggested_quantity INTEGER,

    -- Risk details
    risk_amount REAL,          -- $ at risk
    reward_amount REAL,        -- $ potential gain

    -- Greeks
    delta REAL,
    gamma REAL,
    theta REAL,
    vega REAL,

    -- Execution status
    status TEXT,               -- 'GENERATED', 'ALERTED', 'CONFIRMED', 'EXECUTED', 'REJECTED', 'CANCELLED'
    rejection_reason TEXT,     -- Why rejected

    -- Trade linkage (if executed)
    trade_id INTEGER,          -- FK to trades table

    FOREIGN KEY (trade_id) REFERENCES trades(id)
);

CREATE INDEX idx_signals_timestamp ON signals(timestamp);
CREATE INDEX idx_signals_status ON signals(status);
```

---

#### Table 2: `trades` - Executed trades

```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Trade entry
    entry_timestamp DATETIME NOT NULL,
    underlying TEXT NOT NULL,
    contract_type TEXT,        -- 'CALL', 'PUT', 'SPREAD', 'IRON_CONDOR'
    strike REAL,
    expiry_date DATE,
    quantity INTEGER,
    entry_price REAL,

    -- Strategy that generated trade
    strategy TEXT,             -- 'opening_range', 'directional', etc.

    -- Risk parameters
    stop_loss REAL,
    profit_target REAL,
    risk_amount REAL,
    reward_amount REAL,

    -- Greeks at entry
    delta_entry REAL,
    gamma_entry REAL,
    theta_entry REAL,
    vega_entry REAL,

    -- Position tracking
    current_price REAL,
    current_delta REAL,
    current_theta REAL,
    unrealized_pnl REAL,
    unrealized_pnl_pct REAL,

    -- Exit (if filled)
    exit_timestamp DATETIME,
    exit_price REAL,
    exit_reason TEXT,          -- 'SL_HIT', 'PT_HIT', 'MANUAL', 'EXPIRED'
    realized_pnl REAL,
    realized_pnl_pct REAL,
    holding_days INTEGER,

    -- PDT tracking
    is_day_trade INTEGER,      -- 1 if opened and closed same day

    -- Order IDs from broker
    open_order_id TEXT,
    close_order_id TEXT,

    status TEXT,               -- 'OPEN', 'CLOSED', 'EXPIRED'

    FOREIGN KEY (underlying) REFERENCES market_data(ticker)
);

CREATE INDEX idx_trades_timestamp ON trades(entry_timestamp);
CREATE INDEX idx_trades_status ON trades(status);
CREATE INDEX idx_trades_strategy ON trades(strategy);
```

---

#### Table 3: `market_data` - Cached market state

```sql
CREATE TABLE market_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    ticker TEXT NOT NULL,      -- 'SPX', 'SPY'

    -- Price data
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,

    -- IV & Volatility
    iv REAL,
    iv_rank REAL,
    iv_percentile REAL,
    realized_volatility REAL,

    -- Greeks (at-the-money call estimate)
    atm_delta REAL,
    atm_gamma REAL,
    atm_theta REAL,
    atm_vega REAL,

    -- Technicals (calculated from close)
    sma_20 REAL,
    sma_50 REAL,
    sma_200 REAL,
    rsi_14 REAL,
    macd REAL,
    macd_signal REAL,
    bb_upper REAL,
    bb_lower REAL,
    bb_mid REAL,
    atr_14 REAL,

    -- Sentiment
    news_sentiment REAL,
    social_sentiment REAL,

    -- Volume patterns
    avg_volume_20d INTEGER,
    volume_ratio REAL,

    UNIQUE(ticker, timestamp)
);

CREATE INDEX idx_market_data_timestamp ON market_data(timestamp);
```

---

#### Table 4: `daily_pnl` - Daily P&L summary

```sql
CREATE TABLE daily_pnl (
    date DATE PRIMARY KEY,

    -- P&L summary
    trades_count INTEGER,
    wins INTEGER,
    losses INTEGER,
    win_rate REAL,

    realized_pnl REAL,
    unrealized_pnl REAL,
    total_pnl REAL,

    pnl_pct REAL,              -- % of starting capital

    -- Risk metrics
    max_loss_trade REAL,
    max_gain_trade REAL,
    avg_loss_trade REAL,
    avg_gain_trade REAL,

    -- PDT tracking
    day_trades_count INTEGER,

    -- Daily activity
    signals_generated INTEGER,
    false_signals INTEGER,

    -- Greeks exposure (end of day)
    portfolio_delta REAL,
    portfolio_theta REAL,
    portfolio_vega REAL,

    -- Closing balance
    account_balance REAL
);

CREATE INDEX idx_daily_pnl_date ON daily_pnl(date);
```

---

#### Table 5: `settings` - User configuration & state

```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    data_type TEXT,           -- 'int', 'float', 'bool', 'str', 'json'
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Example rows:
-- ('mode', 'SEMI_AUTO', 'str')
-- ('max_contracts_per_trade', '2', 'int')
-- ('max_daily_loss_pct', '0.02', 'float')
-- ('pdt_day_trades_limit', '3', 'int')
-- ('api_keys', '{"polygon": "...", "finnhub": "..."}', 'json')
-- ('trading_active', 'true', 'bool')
```

---

#### Table 6: `strategy_stats` - Per-strategy win rates

```sql
CREATE TABLE strategy_stats (
    strategy TEXT PRIMARY KEY,  -- 'opening_range', 'directional', etc.

    -- Historical performance
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate REAL,

    avg_win REAL,
    avg_loss REAL,
    profit_factor REAL,        -- Sum of wins / Sum of losses

    -- Kelly parameters
    kelly_fraction REAL,
    half_kelly_fraction REAL,

    -- Average holding time
    avg_holding_hours REAL,

    -- Streak tracking
    current_streak INTEGER,    -- Positive for wins, negative for losses
    max_win_streak INTEGER,
    max_loss_streak INTEGER,

    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

#### Table 7: `trades_log` - Audit trail for all events

```sql
CREATE TABLE trades_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    trade_id INTEGER,
    event_type TEXT,          -- 'CREATED', 'UPDATED', 'EXECUTED', 'CLOSED', 'SL_HIT', 'PT_HIT'

    old_value TEXT,           -- JSON of old state
    new_value TEXT,           -- JSON of new state

    reason TEXT,              -- Why the change
    user_action INTEGER,      -- 1 if manual, 0 if automatic

    FOREIGN KEY (trade_id) REFERENCES trades(id)
);
```

---

### Database Initialization Script

```python
# data/storage.py
class Database:
    def __init__(self, db_path: str = "trading_bot.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Create all tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Execute all CREATE TABLE statements
        cursor.executescript(self.SCHEMA_SQL)
        conn.commit()
        conn.close()

    # Methods for CRUD operations...
    async def save_signal(self, signal: dict) -> int:
        """Insert signal, return ID."""
        pass

    async def save_trade(self, trade: dict) -> int:
        """Insert trade, return ID."""
        pass

    async def update_trade_pnl(self, trade_id: int, current_price: float):
        """Update unrealized P&L."""
        pass

    async def get_daily_pnl(self, date: str) -> dict:
        """Get day's P&L summary."""
        pass
```

---

## 9. Dashboard Features

### Frontend Stack

- **HTML5** - Semantic structure
- **CSS3** - Flexbox/Grid for responsive layout
- **Vanilla JavaScript** - No build tool, no frameworks
- **Chart.js** - Simple charting library (CDN)
- **WebSocket API** - Real-time updates from backend

### Dashboard Layout

```
┌────────────────────────────────────────────────────────────┐
│                     TRADING BOT DASHBOARD                  │
│ Mode: SEMI-AUTO | Last Signal: 2m ago | Today's P&L: +$124│
└────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ LIVE SIGNALS                              [Refresh: 5s]     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  2024-03-20 14:23:45                            STRONG BUY  │
│  ACTION: BUY CALL                                CONFIDENCE  │
│  SPX 5850C (0DTE)                              82%           │
│  Entry: $145.50 | Stop: $130.00 | Target: $160.00          │
│  Risk: $87.50 (1.75%) | Reward: $287.50 | R:R = 3.3       │
│  Strategies: Opening Range (↑45), Momentum (↑35), Dir (↑30) │
│  [CONFIRM & TRADE]  [DISMISS]                               │
│                                                               │
│  2024-03-20 13:52:12                            WEAK BUY    │
│  ACTION: BUY PUT                                 CONFIDENCE  │
│  SPX 5800P (1DTE)                              58%           │
│  Entry: $98.75 | Stop: $115.00 | Target: $85.00           │
│  Risk: $125 (2.5%) | Reward: $212.50 | R:R = 1.7          │
│  Strategies: Mean Reversion (↑55), Directional (↑28)       │
│  [CONFIRM & TRADE]  [DISMISS]                               │
│                                                               │
└─────────────────────────────────────────────────────────────┘

┌──────────────────────────┬──────────────────────────┐
│ TODAY'S P&L              │ CURRENT EXPOSURE         │
├──────────────────────────┼──────────────────────────┤
│ Starting Balance: $5,000 │ Delta: +0.45             │
│ Realized: +$245          │ Theta: +$0.15/day        │
│ Unrealized: -$121        │ Vega: +$1.20             │
│ TOTAL: +$124 (+2.48%)    │ Max Risk: $87.50         │
│                          │ Daily Loss: -$0          │
│ Trades Today: 3          │ PDT Used: 0/3            │
│ Win Rate: 66.7% (2/3)    │ Contracts: 2 open       │
└──────────────────────────┴──────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ OPEN POSITIONS (2)                                          │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│ #1: SPX 5900C (0DTE) x1                                      │
│ Entry: $156.00 | Current: $165.50 | P&L: +$950 (+60.9%)    │
│ Delta: 0.82 | Theta: -$0.45/day | Vega: +$0.65             │
│ Stop: $140.00 | Target: $175.00 | Time to Expiry: 4h 23m   │
│                                                               │
│ #2: SPX 5800/5750 PUT SPREAD (1DTE)                          │
│ Entry: $28.50 (credit) | Current: $22.00 | P&L: +$650      │
│ Delta: -0.35 | Theta: +$0.85/day | Vega: -$0.42            │
│ Loss Limit: $150 | Target: $20.00 | Time to Expiry: 28h     │
│                                                               │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ MARKET SNAPSHOT                                              │
├──────────────────────────────────────────────────────────────┤
│ SPX: 5,847.23 (+0.32%) | IV Rank: 65 | Vol Regime: Normal  │
│ SPY: 585.43 (+0.35%)   | Correlation: 0.98 (High)          │
│ Sentiment: +0.34 (Bullish) | Key Levels: S 5,820 | R 5,880 │
│ Next Event: FOMC Meeting (Tue 10:30am) | 56h away          │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ TRADE HISTORY (This Week)                                    │
├──────────────────────────────────────────────────────────────┤
│ Date       | Action    | Strg | Entry | Exit  | P&L   | Time│
│ 2024-03-20 | BUY CALL  | OPEN | 145.5 | ---   | +950  | 4h  │
│ 2024-03-20 | SPREAD    | OPEN | 28.50 | ---   | +650  | 26h │
│ 2024-03-19 | BUY CALL  | CLOS | 98.00 | 112.5 | +1450 | 2h  │
│ 2024-03-19 | BUY PUT   | CLOS | 76.50 | 65.00 | +1150 | 3h  │
│ 2024-03-18 | BUY CALL  | CLOS | 128.0 | 110.0 | -1800 | 8h  │
│ Weekly: 5 trades | Win%: 60% | Profit: +$2,400 | Sharpe: 1.8│
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ ECONOMIC CALENDAR (Today + Tomorrow)                         │
├──────────────────────────────────────────────────────────────┤
│ 8:30 AM | Initial Jobless Claims | High Impact | ---        │
│ 10:30 AM| Weekly Petroleum Status | Medium Impact| ---       │
│ 2:00 PM | Crude Oil Inventory | Medium Impact | ---         │
│ --      | No Major Events Tomorrow                            │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ SETTINGS & ALERTS                                            │
├──────────────────────────────────────────────────────────────┤
│ Trading Mode: [SIGNAL] [SEMI-AUTO*] [FULL-AUTO]             │
│ Alert Volume: [OFF] [LOW] [MEDIUM*] [HIGH]                 │
│ ☑ Notify on new signals  ☑ Notify on SL/PT hit             │
│ ☑ Enable economic calendar alerts                           │
│ Last API Sync: 2m ago | Status: Connected ✓                │
│ [SETTINGS] [LOGOUT]                                          │
└──────────────────────────────────────────────────────────────┘
```

### Key Features

#### 1. **Real-Time Signal Feed**

- WebSocket connection to backend
- Auto-refresh every 5 seconds
- Show: Action, Strike, Expiry, Entry/Stop/Target, Confidence, R:R
- Action buttons: CONFIRM, DISMISS, SNOOZE (30 min)

#### 2. **P&L Tracker**

- Running tally: Realized + Unrealized + Daily Total
- Win rate display
- P&L chart (daily rolling sum)

#### 3. **Open Positions Panel**

- List all open trades with P&L
- Greeks display (Delta, Theta, Vega)
- Time to expiry
- Quick exit buttons (Close at market, Edit SL/PT)

#### 4. **Risk Dashboard**

- Portfolio Greeks summary
- Daily loss tracking (as % of limit)
- PDT trade counter
- Max position exposure

#### 5. **Economic Calendar**

- Fetched from FinnHub API
- Show impact level, time, actual vs forecast
- Highlight high-impact events (bold)
- Color: RED (high impact), YELLOW (medium), GRAY (low)

#### 6. **Trade History Table**

- Sortable by date, strategy, P&L
- Filter by status (open/closed)
- Show holding time, win rate per strategy
- Export to CSV

#### 7. **Alerts & Notifications**

- Browser notifications (if enabled)
- Audio alert sound option
- Telegram/Discord webhook integration (future)

#### 8. **Settings Modal**

- Toggle trading mode
- Adjust alert volume
- View API connection status
- Logout

### Frontend Code Structure

```
dashboard/static/
├── index.html           # Main dashboard
├── styles.css           # Unified styling
├── app.js               # Core logic & event handlers
├── api.js               # API client functions
├── websocket.js         # WebSocket connection manager
├── charts.js            # Chart rendering (Chart.js wrapper)
├── utils.js             # Helper functions
└── config.js            # Frontend config (API URL, etc)
```

### JavaScript Modules (Pseudo-code)

```javascript
// websocket.js
class DashboardSocket {
  constructor(url) {
    this.ws = new WebSocket(url);
    this.handlers = {};

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.route(data);
    };
  }

  route(data) {
    const { type, payload } = data;
    if (this.handlers[type]) {
      this.handlers[type](payload);
    }
  }

  subscribe(messageType, handler) {
    this.handlers[messageType] = handler;
  }
}

// app.js
const socket = new DashboardSocket('ws://localhost:8000/ws');

socket.subscribe('new_signal', (signal) => {
  appendSignalCard(signal);
  playAlertSound();
  notifyUser(`New ${signal.action} signal`);
});

socket.subscribe('trade_update', (trade) => {
  updatePositionRow(trade.id, trade);
  updatePLTotal(trade.unrealized_pnl);
});

socket.subscribe('daily_pnl', (pnl) => {
  document.getElementById('daily-pnl').textContent = formatCurrency(pnl);
  document.getElementById('pnl-pct').textContent = formatPercent(pnl.pct);
});

// Confirm & Trade button
document.addEventListener('click', async (e) => {
  if (e.target.classList.contains('confirm-btn')) {
    const signal = e.target.dataset.signalId;
    await fetch('/api/execute-signal', {
      method: 'POST',
      body: JSON.stringify({ signal_id: signal }),
    });
  }
});
```

---

## 10. Security Framework

### 1. API Key Management

```python
# config/settings.py
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()  # Load from .env file (never commit)

POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
ALPHA_VANTAGE_KEY = os.getenv('ALPHA_VANTAGE_KEY')
UNUSUAL_WHALES_KEY = os.getenv('UNUSUAL_WHALES_KEY')

# Broker credentials (most secure if available)
TASTYTRADE_USERNAME = os.getenv('TASTYTRADE_USERNAME')
TASTYTRADE_PASSWORD = os.getenv('TASTYTRADE_PASSWORD')
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

# Check all required keys present on startup
def validate_config():
    required_keys = [
        'POLYGON_API_KEY',
        'FINNHUB_API_KEY',
        'TASTYTRADE_USERNAME',  # or ALPACA_API_KEY
    ]
    for key in required_keys:
        if not os.getenv(key):
            raise ValueError(f"Missing required env var: {key}")
```

### 2. Environment Variable Template

```bash
# .env.example (commit this, NOT actual .env)

# Market Data APIs
POLYGON_API_KEY=pk_xxxxxxxxxxxxx
FINNHUB_API_KEY=xxxxxxxxxxxxx
ALPHA_VANTAGE_KEY=xxxxxxxxxxxxx
UNUSUAL_WHALES_KEY=xxxxxxxxxxxxx

# Broker APIs (choose one primary)
TASTYTRADE_USERNAME=your_username
TASTYTRADE_PASSWORD=your_password
# OR:
ALPACA_API_KEY=xxxxxxxxxxxxx
ALPACA_SECRET_KEY=xxxxxxxxxxxxx

# Paper Trading (for testing)
PAPER_TRADING_ENABLED=true

# App Config
LOG_LEVEL=INFO
DATABASE_PATH=./trading_bot.db
API_HOST=0.0.0.0
API_PORT=8000
```

### 3. .gitignore Configuration

```
# Never commit secrets
.env
.env.local
.env.*.local
secrets/
credentials.json

# Python artifacts
__pycache__/
*.pyc
*.pyo
.pytest_cache/
venv/
env/

# IDE
.vscode/
.idea/
*.swp

# Data files (optional)
trading_bot.db
logs/
backups/

# OS
.DS_Store
Thumbs.db
```

### 4. Input Validation

```python
# utils/validators.py
from pydantic import BaseModel, validator

class TradeInput(BaseModel):
    underlying: str
    action: str
    strike: float
    quantity: int

    @validator('underlying')
    def validate_underlying(cls, v):
        if v not in ['SPX', 'SPY']:
            raise ValueError('Only SPX/SPY allowed')
        return v

    @validator('action')
    def validate_action(cls, v):
        allowed = ['BUY_CALL', 'BUY_PUT', 'SELL_CALL_SPREAD', 'SELL_PUT_SPREAD', 'IRON_CONDOR']
        if v not in allowed:
            raise ValueError(f'Action must be one of {allowed}')
        return v

    @validator('quantity')
    def validate_quantity(cls, v):
        if v < 1 or v > 2:
            raise ValueError('Quantity must be 1-2')
        return v
```

### 5. Rate Limiting

```python
# dashboard/app.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from collections import defaultdict

app = FastAPI()

# Simple rate limiter (IP-based)
rate_limit_store = defaultdict(list)

async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    now = datetime.now()

    # Keep only requests from last minute
    rate_limit_store[client_ip] = [
        t for t in rate_limit_store[client_ip]
        if now - t < timedelta(minutes=1)
    ]

    # Check limit: max 60 requests per minute
    if len(rate_limit_store[client_ip]) > 60:
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded"}
        )

    rate_limit_store[client_ip].append(now)
    response = await call_next(request)
    return response

app.middleware("http")(rate_limit_middleware)
```

### 6. Logging & Audit Trail

```python
# utils/logger.py
import logging
import json
from datetime import datetime

class StructuredLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        handler = logging.FileHandler('trading_bot.log')
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def log_trade(self, event: str, trade_id: int, details: dict):
        """Log all trade events in audit trail."""
        msg = {
            'timestamp': datetime.now().isoformat(),
            'event': event,
            'trade_id': trade_id,
            **details
        }
        self.logger.info(json.dumps(msg))

    def log_api_call(self, endpoint: str, method: str, status: int, duration_ms: float):
        """Log API calls for monitoring."""
        self.logger.debug(f"{method} {endpoint} -> {status} ({duration_ms:.0f}ms)")
```

### 7. HTTPS & WebSocket Security

```python
# dashboard/app.py (Production)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.https import HTTPSMiddleware

app = FastAPI()

# CORS: Allow only your domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # Not "*" in production
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# HTTPS redirect (if running behind reverse proxy)
# app.add_middleware(HTTPSMiddleware)

# WebSocket requires wss:// in production
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocketConnectionManager):
    await websocket.accept()
    # Client should connect to wss://... not ws://...
```

---

## 11. Deployment & Operations

### Running the Bot

#### Development Mode

```bash
# 1. Setup virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env with your API keys

# 4. Initialize database
python main.py --init-db

# 5. Run bot (with logging)
python main.py --mode semi-auto --log-level info
```

#### Production Mode (Linux/macOS)

```bash
# Use systemd service file
sudo cp trading-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl start trading-bot

# View logs
sudo journalctl -u trading-bot -f
```

**trading-bot.service:**
```ini
[Unit]
Description=AI Trading Bot
After=network.target

[Service]
Type=simple
User=trader
WorkingDirectory=/home/trader/ai-trading-bot
Environment="PATH=/home/trader/ai-trading-bot/venv/bin"
ExecStart=/home/trader/ai-trading-bot/venv/bin/python main.py --mode semi-auto
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Monitoring & Alerts

```python
# main.py (health check loop)
async def health_monitor():
    """Monitor API connections, log errors."""
    while True:
        try:
            # Test each API connection
            async with aiohttp.ClientSession() as session:
                for provider_name, provider in providers.items():
                    try:
                        await provider.health_check()
                    except Exception as e:
                        logger.error(f"{provider_name} down: {e}")
                        # Send alert (email, Slack, etc.)
        except Exception as e:
            logger.error(f"Health check failed: {e}")

        await asyncio.sleep(300)  # Check every 5 min
```

### Backup Strategy

```bash
# Daily backup (in crontab)
0 17 * * * sqlite3 /path/to/trading_bot.db ".backup /backups/trading_bot_$(date +\%Y\%m\%d).db"
```

---

## 12. Development Roadmap

### Phase 1: MVP (Week 1-2)
- [x] Project structure setup
- [ ] Database schema & ORM layer
- [ ] Single strategy (Momentum)
- [ ] Paper trading only
- [ ] Signal/Alert mode dashboard
- [ ] Basic logging

### Phase 2: Multi-Strategy (Week 3-4)
- [ ] 3 additional strategies (Opening Range, Directional, Mean Reversion)
- [ ] Signal aggregation engine
- [ ] Risk manager implementation
- [ ] Real Polygon API integration
- [ ] Semi-Auto mode

### Phase 3: Production Ready (Week 5-6)
- [ ] Broker integration (TastyTrade/Alpaca)
- [ ] Full-Auto mode with safeguards
- [ ] Economic calendar integration
- [ ] Advanced dashboard features
- [ ] Options flow (Unusual Whales)
- [ ] Unit tests & integration tests

### Phase 4: Optimization (Week 7+)
- [ ] Backtest framework
- [ ] Parameter optimization
- [ ] Advanced analytics
- [ ] Mobile app (optional)
- [ ] Telegram/Discord alerts

---

## Appendix A: Quick Start Checklist

- [ ] Python 3.11+ installed
- [ ] Virtual environment created & activated
- [ ] `requirements.txt` installed
- [ ] `.env` file created with API keys
- [ ] SQLite database initialized
- [ ] Broker account set up (paper trading OK for start)
- [ ] Dashboard accessible at `http://localhost:8000`
- [ ] First signal generated (check logs)
- [ ] First trade executed (paper/semi-auto)

---

## Appendix B: Common Troubleshooting

| Issue | Solution |
|-------|----------|
| "Missing POLYGON_API_KEY" | Check `.env` file, ensure key is set |
| "Database locked" | Close other connections, restart bot |
| "WebSocket disconnected" | Check firewall, restart dashboard |
| "No signals generated" | Check market hours (9:30-16:00 ET), verify API data flows |
| "PDT violation" | Reduce day trades, use 2-3 DTE options instead |

---

**Document Version:** 1.0
**Last Updated:** 2024-03-20
**Status:** Ready for Development
