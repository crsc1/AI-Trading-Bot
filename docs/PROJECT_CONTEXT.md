# AI Trading Bot — Full Project Context

**Last updated:** March 30, 2026
**Purpose:** Continuity document so a new chat can pick up exactly where we left off.

---

## 1. What This Project Is

A **real-time 0DTE SPY/SPX options trading bot** with a $5,000 paper trading account. It combines order flow analysis, technical indicators, options Greeks, and a 15-factor confluence scoring system to generate and auto-execute trading signals via Alpaca paper trading.

The system has three layers:
1. **Rust Flow Engine** — high-performance tick ingestion, footprint charts, CVD, sweep/absorption/imbalance detection
2. **Python Agent Layer** (FastAPI) — signal engine, confluence scoring, autonomous trader, paper trader, position tracking
3. **Frontend Dashboard** (single-page HTML) — Lightweight Charts v4.1.1, PixiJS v8 canvas rendering, WebSocket real-time updates

---

## 2. Tech Stack

| Layer | Tech | Notes |
|-------|------|-------|
| Frontend | HTML/JS/CSS (single file: `flow-dashboard.html`) | ~6,500 lines, monolithic |
| Charts | Lightweight Charts v4.1.1 | Candle charts with indicators |
| Canvas | PixiJS v8.17.1 | GPU-accelerated flow bubbles, per-price, footprint |
| Backend | Python 3.10+ / FastAPI / Uvicorn | REST + WebSocket |
| Flow Engine | Rust / Tokio / Axum | Tick processing, event publishing |
| Database | SQLite (WAL mode) | Signals, trades, daily scorecards |
| Broker | Alpaca Paper Trading API | Real paper orders via OPRA |
| Data | Alpaca SIP (primary) + ThetaData (dropping ~April 2026) | |
| Config | pydantic-settings + .env | |

---

## 3. Project Structure

```
AI Trading Bot/
├── .env                          # API keys (ALPACA_API_KEY, ALPACA_SECRET_KEY, etc.)
├── start.sh                      # Starts flow engine + dashboard
├── stop.sh                       # Kills both processes
├── restart.sh                    # Restart helper
├── requirements.txt              # Python deps
├── main.py / run_dashboard.py    # Entry points
│
├── config/
│   ├── settings.py               # Pydantic settings (risk limits, timing, etc.)
│   └── api_keys.py.example       # Template for API keys
│
├── dashboard/                    # Python backend (FastAPI)
│   ├── app.py                    # FastAPI app, middleware, startup/shutdown
│   ├── signal_api.py             # Main API router (/api/signals/*)
│   ├── signal_engine.py          # 15-factor signal analysis pipeline
│   ├── confluence.py             # Confluence scoring, tiers, trade modes
│   ├── autonomous_trader.py      # Auto-execution engine with Dynamic Exit
│   ├── paper_trader.py           # Dual-mode: simulation or Alpaca paper
│   ├── position_tracker.py       # Live P&L with chain mid-price lookups
│   ├── signal_db.py              # SQLite persistence (signals, trades)
│   ├── trade_grader.py           # A/B/C/D/F trade grading
│   ├── weight_learner.py         # ML weight adjustment from trade outcomes
│   ├── signal_validator.py       # Signal validation rules
│   ├── market_levels.py          # VWAP bands, pivot points, HOD/LOD
│   ├── gex_engine.py             # GEX/DEX analysis
│   ├── options_analytics.py      # Options chain analytics
│   ├── vanna_charm_engine.py     # Vanna/Charm flow analysis
│   ├── regime_detector.py        # Market regime classification
│   ├── event_calendar.py         # Economic event awareness
│   ├── sweep_detector.py         # Institutional sweep detection
│   ├── flow_toxicity.py          # VPIN (Volume-sync Probability of Informed Trading)
│   ├── sector_monitor.py         # Sector divergence + bond yields
│   ├── alpaca_ws.py              # Alpaca WebSocket streaming
│   ├── websocket_handler.py      # Dashboard WebSocket manager
│   ├── api_routes.py             # General API routes
│   ├── trading_api.py            # Direct Alpaca trading routes
│   ├── orderflow_api.py          # Order flow REST endpoints
│   ├── tick_store.py             # Tick database for replay
│   ├── debug_middleware.py       # Request/response logging
│   ├── agents/                   # AI agent sub-system
│   │   └── api.py
│   └── static/
│       ├── flow-dashboard.html   # THE dashboard (6,500 lines)
│       ├── index.html            # Landing/redirect
│       └── debug.html            # Debug tools
│
├── engine/                       # Python signal components
│   ├── market_context.py
│   ├── pattern_analyzer.py
│   ├── probability.py
│   ├── risk_manager.py
│   └── signal_aggregator.py
│
├── flow-engine/                  # Rust flow engine
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs               # Axum server, WS endpoint
│       ├── alpaca_ws.rs          # Alpaca SIP WebSocket connection
│       ├── classifier.rs         # Buy/sell trade classification
│       ├── ingestion.rs          # Tick ingestion pipeline
│       ├── footprint.rs          # Footprint chart builder
│       ├── cvd.rs                # Cumulative Volume Delta
│       ├── detectors.rs          # Sweep, absorption, imbalance
│       └── events.rs             # Structured event types
│
├── strategies/                   # Trading strategy implementations
│   ├── directional.py
│   ├── momentum.py
│   ├── mean_reversion.py
│   ├── opening_range.py
│   ├── credit_spreads.py
│   └── flow_based.py
│
├── utils/
│   ├── greeks.py                 # Local Black-Scholes Greeks calculator
│   ├── indicators.py             # Technical indicators
│   └── logger.py
│
├── data/                         # SQLite databases, cached data
├── logs/                         # Application logs
└── tests/                        # Test suite
```

---

## 4. How To Start/Stop

```bash
# Full start (Rust engine + Python dashboard):
./start.sh

# Dashboard only (engine already running):
./start.sh --dash-only

# Force rebuild Rust engine:
./start.sh --build

# Stop everything:
./stop.sh

# Manual start:
python3 -m uvicorn dashboard.app:app --host 0.0.0.0 --port 8000
```

**Prerequisites:**
- `.env` file with `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`
- Rust toolchain (for flow engine)
- Python 3.10+ with FastAPI, uvicorn, aiohttp, pydantic-settings
- ThetaData Terminal (optional, running on port 25503)

---

## 5. Data Provider Strategy

- **Alpaca Algo Trader Plus** — primary data source. SIP real-time trades/quotes/bars + options chain via OPRA
- **ThetaData Standard** — currently active but being **dropped ~late April 2026** (billing cycle ends). Provides Greeks/IV/OI snapshots
- **After ThetaData drops:** Local Black-Scholes calculations in `utils/greeks.py` and `vanna_charm_engine.py` will replace ThetaData's computed Greeks using Alpaca's options bid/ask for IV derivation
- **Level 2 depth:** Evaluating Databento ($199/mo, L2+L3) or IBKR (free L2 with funded account)

---

## 6. Signal Engine (15-Factor Confluence Scoring)

The signal engine runs every 15 seconds in the background (`signal_api.py` → `ANALYSIS_INTERVAL = 15`). It fetches live market data server-side and scores confluence across 15 factors:

**v4 Factors:**
1. Order flow delta divergence
2. Absorption detection
3. Exhaustion signals
4. Large block trades
5. Aggressive vs passive flow
6. Bid/ask imbalance at levels
7. GEX (Gamma Exposure)
8. DEX (Delta Exposure)
9. Put/Call Ratio
10. Max Pain
11. Volume spike
12. Delta regime
13. Sweep detection (institutional)
14. VPIN (flow toxicity)
15. Sector divergence

**Confidence Tiers:**
- `TEXTBOOK` — 80%+ (8.0+/10 composite)
- `HIGH` — 60%+ (6.0+/10)
- `VALID` — 45%+ (4.5+/10)
- `DEVELOPING` — 30%+ (watch only)

**Trade Modes:** scalp (default for 0DTE), standard, swing

---

## 7. Autonomous Trader (Current Configuration)

Located in `dashboard/autonomous_trader.py`. Currently configured for:

- **Mode:** `alpaca_paper` (real Alpaca paper orders)
- **Min confidence:** `0.55` (55%+, HIGH tier minimum)
- **Min tier:** `HIGH`
- **Execution:** Fully automatic (no manual confirmation needed)
- **Master switch:** `enabled: False` by default (toggle via API)

### Risk Limits:
- Max daily loss: $100
- Max open positions: 2
- Max trades/day: 10
- Max risk per trade: 2% of account
- 60s cooldown between entries
- Trading window: 9:35 AM - 3:00 PM ET

### 6-Level Dynamic Exit Engine:
Evaluates exits in strict priority order:

1. **TARGET HIT** — `current_price >= target_price`
2. **PROFIT PROTECTED** — Dynamic giveback tiers:
   - Gain 10-25%: allow 50% giveback
   - Gain 25-50%: allow 30% giveback
   - Gain 50-100%: allow 20% giveback
   - Gain 100%+: allow only 10% giveback
3. **STOPPED** — Hard stop loss at `stop_price`
4. **VELOCITY STOP** — Price drops >8% in one tick
5. **BREAKEVEN** — If was ever up 5%+, exit at +0.5%
6. **TIME EXIT** — Max hold (45 min) or 0DTE hard stop at 3:00 PM ET

Tracks `_peak_prices` (highest seen) and `_prev_prices` (previous tick) per trade for these calculations.

---

## 8. Paper Trader

Located in `dashboard/paper_trader.py`. Dual-mode execution:

- **Simulation mode:** Black-Scholes repricing, no broker interaction
- **Alpaca Paper mode:** Places real limit buy orders on Alpaca paper account, market sell-to-close

Key details:
- Uses OCC option symbol format: `SPY250326C00570000`
- Tags orders with `ai_signal_` prefix to identify bot orders
- Records every trade in signal_db (signals + trades tables)
- Tracks MFE (max favorable excursion) and MAE (max adverse excursion)

---

## 9. Position Tracker (Live P&L)

Located in `dashboard/position_tracker.py`. 3-tier pricing priority:

1. **Chain mid-price** — `(bid + ask) / 2` from live options chain (via `update_chain_prices()`)
2. **Black-Scholes** — local repricing when chain data is stale (>30 seconds)
3. **Cached price** — last known price as final fallback

Returns per-position: `live_greeks` (delta, gamma, theta, vega, IV), `price_source` (chain_mid/black_scholes/cached), `bid`, `ask`, MFE, MAE.

---

## 10. Dashboard (Frontend)

Single monolithic HTML file: `dashboard/static/flow-dashboard.html` (~6,500 lines)

### Tabs:
1. **Flow + Candles** — Combined order flow visualization + price chart
2. **Flow Only** — Dedicated flow analysis (bubbles, per-price, footprint subtabs)
3. **Candles Only** — Full candlestick chart with indicators (VWAP, Bollinger Bands)
4. **Options Board** — Options chain display
5. **Positions** — Trade management (recently rebuilt, see below)

### Positions Tab (Robinhood-Style — Latest Build):
- **Open Positions:** Card layout with:
  - BUY CALL / BUY PUT direction badges (green/red)
  - Large P&L display: +$XX.XX (+X.X%)
  - Price grid: Entry, Current (bid×ask), MFE, MAE
  - Live Greeks: delta, gamma, theta, IV
  - Target/Stop progress bar with entry marker
  - Source badge: BOT · LIVE (green pulse) or BOT · THEO
- **Trade History:** Full log with:
  - Direction: "BOUGHT CALL" / "BOUGHT PUT"
  - Symbol, strike, date/time, entry→exit prices, hold time, contracts
  - Exit reason badges: TARGET, PROTECTED, STOPPED, V-STOP, BREAKEVEN, TIME, THETA, MANUAL
  - Grade badges: A/B/C/D/F with color coding
  - P&L prominently displayed
- **Beat SPY scorecard** — Bot vs buy-and-hold comparison
- **Equity curve** — Portfolio value over time
- **Recent orders** — Latest Alpaca order log

### Key Frontend Details:
- WebSocket-based real-time updates
- `requestAnimationFrame` throttling for chart updates
- `_posRefreshLock` mutex to prevent overlapping position tab refreshes
- Canvas renderers MUST use `FLOW_LAYOUT` shared config for DPR scaling (never hardcode pixel values)

---

## 11. API Endpoints

### Signal Endpoints (`/api/signals/`):
- `POST /analyze` — Real-time analysis from frontend tick data
- `GET /latest` — Most recent signal
- `GET /history` — Last 50 signals
- `GET /config` — Current configuration
- `GET /levels` — Market structure levels (VWAP, pivots, etc.)
- `GET /gex` — GEX/DEX analysis
- `GET /sweeps` — Institutional sweep detection
- `GET /vpin` — Flow toxicity status
- `GET /sectors` — Sector divergence

### Trading Endpoints (`/api/signals/`):
- `POST /trade` — Process signal through paper trader
- `GET /positions` — Open positions with live P&L
- `GET /trades?limit=50` — Closed trade history
- `GET /scorecard` — Performance metrics
- `POST /exit` — Manually exit a position

### Auto-Trader Endpoints (`/api/signals/auto-trader/`):
- `GET /status` — Current config + stats
- `POST /start` — Enable auto-trading
- `POST /stop` — Disable auto-trading
- `POST /config` — Update configuration
- `GET /decisions` — Decision audit log

---

## 12. Key Configuration (settings.py)

```python
starting_capital = 5000.0
max_risk_per_trade = 0.02        # 2% per trade
max_daily_loss = 0.02            # 2% daily max loss
max_total_open_positions = 5
default_hold_minutes = 60
default_stop_loss_percent = 0.10  # 10%
default_profit_target_percent = 0.25  # 25%
max_day_trades = 3                # PDT rule
trading_start_time = 9:45 AM
trading_end_time = 3:30 PM
dashboard_port = 8000
flow_engine_port = 8081
```

---

## 13. Bugs Fixed in Latest Session (March 30, 2026)

### Candle Chart Fixes (6 critical bugs):
1. `rtCandle` not reset on symbol switch → added `rtCandle = null` in `setSym()`
2. `resize(0,0)` causing flicker on tab switch → replaced with `applyOptions({autoSize:true})` + `fitContent()`
3. Missing `combVolS.update(vol)` in bar handler → added
4. Unbounded `liveCandles` Map → capped at 500 entries
5. Rapid tick updates causing render flicker → throttled via `requestAnimationFrame`
6. `bar_update` only updating full chart → now updates both full and combined charts

### Positions Tab Fixes:
1. NULL pointer in `renderEquityChart()` → added `if(!wrap) return;`
2. Duplicate autoTraderPositionsWrap DOM creation → removed entire duplicate system
3. Two separate 5s polling intervals fighting → unified into single `refreshPositionsTab()` with `_posRefreshLock` mutex
4. Complete Positions tab rebuild from table layout to Robinhood-style cards

### AutoTrader Fixes:
- Defaults changed from `mode="simulation"` + `min_confidence=0.45` to `mode="alpaca_paper"` + `min_confidence=0.55`
- Added `_peak_prices` and `_prev_prices` tracking dicts for Dynamic Exit Engine
- Replaced simple exit logic with 6-level Dynamic Exit Engine
- Added `_cleanup_trade_state()` helper

### Position Tracker Fixes:
- Added `_chain_cache` and `_chain_update_time` for live chain data
- Added `update_chain_prices()` and `_lookup_chain_price()` methods
- Modified `_compute_position()` to use 3-tier pricing priority (chain_mid > black_scholes > cached)

---

## 14. Important Rules & Preferences

1. **Never ask the user to close Chrome** — use headless Chromium via Python's `playwright` library instead. Playwright MCP conflicts with the user's Chrome profile.
2. **Canvas renderers must use `FLOW_LAYOUT` shared config** — all pixel coordinates multiplied by `dpr`. Never hardcode raw pixel values.
3. **Security is always a consideration** — API keys in `.env`, never committed to git.
4. **Ask questions before building** — use buttons/multiple choice when possible to clarify requirements.
5. **Don't assume things** — research and verify before implementing.
6. **Optimize for token efficiency** — minimize unnecessary prompting.
7. **Use latest tech** — stay current with dependencies and approaches.
8. **Analyze the market thoroughly** — ensure trading logic is valid and realistic.

---

## 15. Pending / Next Steps

After the latest session's changes:
- **Server needs restart** (Python backend files were modified). Run `./start.sh --dash-only` or restart uvicorn manually.
- **Test Positions tab** — verify Robinhood-style cards render correctly with real data
- **Test Auto-Trader** — enable via API and observe signal-driven execution
- **ThetaData migration** — before April 2026 billing ends:
  - Integrate any remaining valuable ThetaData endpoints
  - Build local Greeks computation from Alpaca options chain
  - Remove ThetaData dependency from codebase
- **Level 2 data** — evaluate Databento or IBKR for depth-of-book

---

## 16. How to Restart the Server

```bash
# Option 1: Full restart
./stop.sh && ./start.sh

# Option 2: Dashboard only
pkill -f "uvicorn dashboard.app" && sleep 1
cd /path/to/AI\ Trading\ Bot
python3 -m uvicorn dashboard.app:app --host 0.0.0.0 --port 8000

# Option 3: Just use restart.sh
./restart.sh
```

After restart, hard-refresh the browser (`Cmd+Shift+R` or `Ctrl+Shift+R`).
