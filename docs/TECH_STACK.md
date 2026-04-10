# Technology Stack

## Architecture Overview

Three-layer trading platform: SolidJS frontend, Rust flow engine, Python analytics dashboard.

```
Frontend (SolidJS + PixiJS + Lightweight Charts)
  |
  |-- WebTransport/QUIC (port 4433) -----> Rust Flow Engine (port 8081)
  |-- WebSocket (port 8081) -------------> Rust Flow Engine
  |-- REST (port 8000) ------------------> Python Dashboard (FastAPI)
  |
Rust Flow Engine
  |-- Alpaca SIP WebSocket (equities, real-time trades + NBBO quotes)
  |-- ThetaDataDx FPSS (options, direct FPSS without Java Terminal)
  |-- Protobuf binary broadcast to all connected frontends
  |
Python Dashboard (FastAPI on Uvicorn)
  |-- Alpaca REST (bars, account, orders, positions)
  |-- ThetaData Terminal WS (options quotes/trades for scanner)
  |-- Anthropic Claude API (signal validation, Market Brain)
  |-- SQLite (9 databases: signals, ticks, trades, ML training, scanner alerts)
```

---

## Frontend

| Dependency | Version | Purpose |
|---|---|---|
| SolidJS | 1.9.12 | Reactive UI framework |
| Vite | 8.0.4 | Build tool + HMR |
| TypeScript | 6.0.2 | Type safety |
| Tailwind CSS | 4.2.2 | Utility-first styling |
| Pixi.js | 8.17.1 | GPU-accelerated 2D rendering (bubble chart) |
| Lightweight Charts | 5.1.0 | Candlestick/line charts (TradingView engine) |
| lightweight-charts-indicators | 0.4.0 | VWAP, SMA, EMA, Bollinger Bands |
| protobufjs | 8.0.1 | Binary message decoding in Web Worker |
| comlink | 4.4.2 | Web Worker RPC (off-main-thread protobuf decoding) |
| marked | 18.0.0 | Markdown rendering for AI chat |
| @solidjs/router | 0.16.1 | Client-side routing |

**Typography**: Geist (display/body), Geist Mono (data/prices), JetBrains Mono (AI output)

**State management**: SolidJS `createStore` + `createSignal`. No Redux/MobX. Stores in `frontend/src/signals/`.

**Runtime modules**: Data fetching with subscribe/unsubscribe pattern in `frontend/src/runtime/`.

---

## Rust Flow Engine

| Dependency | Version | Purpose |
|---|---|---|
| tokio | 1.x | Async runtime (full features) |
| axum | 0.7 | HTTP/WebSocket server |
| wtransport | 0.6 | WebTransport (QUIC) server |
| prost | 0.14 | Protobuf encoding (Rust -> Browser binary frames) |
| thetadatadx | 6.0.1 | ThetaData direct FPSS client (no Java Terminal) |
| tokio-tungstenite | 0.24 | WebSocket client (Alpaca SIP feed) |
| rustls | 0.23 | TLS (ring crypto provider) |
| reqwest | 0.12 | HTTP client (REST polling fallback) |
| serde / serde_json | 1.x | JSON serialization |
| chrono | 0.4 | Date/time handling |
| libm | 0.2 | Math (erf for Black-Scholes normal CDF) |
| ordered-float | 4.x | Price keys in sorted maps |

**Build profile**: opt-level=3, LTO, codegen-units=1 (max optimization).

### Engine Pipeline

```
Alpaca SIP WebSocket (trades + NBBO quotes)
  -> TradeClassifier (Lee-Ready: buy/sell/neutral)
    -> FootprintBuilder (volume at price, bid/ask split)
    -> CvdCalculator (cumulative volume delta, 1m/5m windows)
    -> SweepDetector (multi-level aggressive fills)
    -> AbsorptionDetector (large resting orders held)
    -> ImbalanceDetector (bid/ask volume ratios)
      -> Protobuf MarketMessage broadcast (WebSocket + WebTransport)

ThetaDataDx FPSS (options quotes + trades)
  -> OptionsEnricher (IV, Greeks, VPIN, Smart Money Score)
    -> JSON theta_trade broadcast via external channel
    -> 2000-trade ring buffer for frontend hydration on refresh
```

### Options Enrichment (Rust-native, no Python dependency)

`flow-engine/src/options_enrichment.rs`:
- **Black-Scholes IV solver**: Newton-Raphson, 30-iteration convergence, Brenner-Subrahmanyam initial guess
- **Greeks**: delta, gamma, theta, vega from converged IV
- **VPIN**: Volume-synchronized probability of informed trading (200 contracts/bucket, 40-bucket rolling window)
- **Smart Money Score**: Composite 0-100 (size sqrt-scaled + gamma normalized + aggression + ATM proximity)
- **Timestamp**: date + ms_of_day -> Unix milliseconds (ET -> UTC conversion)

### Protobuf Schema (`frontend/src/proto/market.proto`)

MarketMessage envelope containing one of:
Tick, Quote, Candle, Footprint, Cvd, Sweep, Imbalance, Absorption, DeltaFlip, LargeTrade, OptionTrade, Heartbeat, ExternalJson

---

## Python Dashboard

| Dependency | Version | Purpose |
|---|---|---|
| FastAPI | >=0.104 | Async web framework |
| uvicorn | >=0.24 | ASGI server |
| anthropic | >=0.87 | Claude API SDK |
| aiohttp | >=3.9 | Async HTTP client |
| aiosqlite | >=0.19 | Async SQLite |
| pandas | >=2.0 | Data analysis |
| websockets | >=12.0 | WebSocket protocol |
| pydantic-settings | >=2.0 | Config management |

### AI / Agent System

**5-Agent Orchestration** (`dashboard/agents/`):
1. PriceFlow Agent — order flow analysis (sweeps, absorption, CVD)
2. Market Structure Agent — session regime, support/resistance
3. Sentiment Agent — options flow, put/call ratios
4. News Agent — economic calendar, earnings
5. Signal Publisher — aggregates verdicts, publishes unified signals

**Market Brain** (`dashboard/market_brain.py`):
- Sonnet 4.6 for 15-second analysis cycles
- Opus 4.6 for trade re-evaluation before execution
- Rolling 30-turn conversation window
- Structured JSON output: action, direction, confidence, tier, reasoning

**LLM Validator** (`dashboard/llm_validator.py`):
- Advisory layer (never blocks trades)
- Claude Sonnet 4.6, max 512 tokens
- Stores last 100 verdicts

### Signal Engine

7 core factors (down from 23, optimized for 0DTE):
1. Order flow imbalance (weight 2.0)
2. CVD divergence (1.5)
3. GEX alignment (1.5)
4. VWAP rejection (1.0)
5. Sweep activity (1.0)
6. ORB breakout (1.25)
7. Support/resistance (1.0)

4 confidence tiers: TEXTBOOK (>=0.80), HIGH (>=0.60), VALID (>=0.45), DEVELOPING (>=0.30)

---

## Database Layer (SQLite)

| Database | Size | Purpose |
|---|---|---|
| ticks.db | 376MB | Equity tick archive (Alpaca SIP) |
| signals.db | 660KB | Signal history + outcomes |
| training_data.db | 11MB | ML training samples |
| market_moments.db | 532KB | Market regime moments |
| weight_learner.db | 232KB | Strategy weight optimization |
| scanner_alerts.db | 76KB | Flow scanner detections |
| trading_bot.db | 48KB | Main trading state |
| afterhours_analysis.db | 36KB | Post-session learning |
| iv_history.db | 12KB | IV time series |

All use WAL mode for concurrent reads. Async access via aiosqlite.

---

## External Data Providers

### Alpaca Markets (Broker + Equities)
- **SIP feed**: Real-time trades + NBBO quotes via WebSocket
- **REST**: Bars (1m/5m/1h/1d), account, orders, positions, calendar
- **Plan**: Algo Trader Plus (SIP access)
- **Ports**: REST `data.alpaca.markets`, WS `stream.data.alpaca.markets/v2/sip`

### ThetaData (Options)
- **FPSS (via ThetaDataDx)**: Direct Rust client, real-time option quotes + trades, no Java Terminal
- **Terminal WS**: `ws://localhost:25520/v1/events` (Python scanner feed)
- **Terminal REST**: `http://localhost:25503` (chains, Greeks, IV history)
- **Plan**: OPTION.STANDARD ($80/mo, up to 10K quote + 15K trade contracts)

### Anthropic Claude (AI)
- **Models**: Sonnet 4.6 (analysis), Opus 4.6 (trade decisions)
- **Usage**: Signal validation, Market Brain, exit advisor, daily review

---

## Options Flow Bubble Chart Architecture

The bubble chart (`frontend/src/components/charts/OptionsBubbleChart.tsx`) visualizes real-time options order flow as Bookmap-style split-circle bubbles on a price x time canvas.

### Data Pipeline

```
ThetaDataDx FPSS -> Rust OptionsEnricher -> theta_trade JSON
  -> WebSocket/WebTransport -> Frontend protobuf worker (off-thread decode)
    -> optionsFlow store (4Hz batched flush, 1000 trade ring buffer)
      -> OptionsBubbleChart.syncTrades() -> tick buffer (10K max)
        -> ticksToCells() aggregation (250ms time buckets x $0.05 price buckets)
          -> computeBubblePoints() (percentile-based radius, age-based opacity)
            -> Canvas 2D (grid, labels, price ladder, CVD gradient, notable overlays)
            -> PixiJS GPU sprites (split-circle bubbles from texture atlas)
```

### Rendering Layers

**Layer 1 — Canvas 2D** (`flowCanvas.ts`):
- Background grid + price labels + time axis
- Volume bars at each price level
- CVD velocity gradient (green/red background indicating flow direction)
- Trail line connecting bubble centers
- Notable trade overlays: sweep rings (dashed purple), block rings (solid), whale glows (gold radial)

**Layer 2 — PixiJS GPU** (`flowRenderer.ts`):
- Pre-rendered texture atlas: 55 textures (11 buy-ratio steps x 5 size tiers)
- Each texture is a split-circle: green arc (buy %) + red arc (sell %) with radial gradients
- Sprite pool: 5000 pre-allocated sprites, reused per frame (no GC pressure)
- Glow ring on trades < 3 seconds old (spray effect: 1.8x scale, fading alpha)
- Age-based opacity: 95% (newest) fading to 15% (oldest in window)

### Split-Circle Bubble Design (Bookmap-style)

Each bubble is a mini pie chart showing the buy/sell volume RATIO within that time/price cell:

- **Green arc**: buy volume proportion, sweeps clockwise from 12 o'clock
- **Red arc**: sell volume proportion, fills the remainder
- **Size**: total volume at that cell (percentile-scaled across visible data)
  - 5 tiers: tiny (10px), small (16px), medium (24px), large (36px), huge (52px)
  - Adaptive: sizes scale relative to the data distribution, not absolute volume
- **Quantization**: 11 steps (0%, 10%, 20%... 100% buy) — pre-rendered as textures
- **Border**: interpolates between green and red based on dominant side

### Coordinate System

- **X-axis**: time (ms since window start, 5-minute sliding window)
- **Y-axis**: underlying price (SPY) at time of option trade, IQR-filtered for outliers
- **Price tick**: $0.05 resolution
- **Time bucket**: 250ms aggregation intervals
- **Layout**: computed per-frame with margins for labels, price ladder, volume bars

### Trade Classification

Option trades are classified by the Rust enrichment pipeline:
- **Side**: Lee-Ready (buy = at ask, sell = at bid, mid = between)
- **Mid trades**: split 50/50 between buy and sell volume (no buy-side bias)
- **Tags**: SWEEP (3+ exchanges in 2s), BLOCK (100+ contracts), WHALE ($100K+ premium)
- **Clusters**: same strike/right/side within 30s and 20% price tolerance = parent order

### Hydration on Refresh

Rust engine buffers last 2000 theta_trade events in a ring buffer.
`GET /theta/trades/recent?limit=N` serves them newest-first.
Frontend calls `hydrateOptionsFlow()` on init, replaying trades through the standard
`handleDecodedMessage` pipeline to restore trade tape, bubble chart, and premium totals.

---

## Ports

| Service | Port | Protocol |
|---|---|---|
| Python Dashboard | 8000 | HTTP + WebSocket |
| Rust Flow Engine | 8081 | HTTP + WebSocket |
| WebTransport (QUIC) | 4433 | UDP/QUIC |
| ThetaData Terminal REST | 25503 | HTTP |
| ThetaData Terminal WS | 25520 | WebSocket |
| Vite Dev Server | 3000 | HTTPS (mkcert) |

---

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`):
- **Lint**: Ruff (Python)
- **Test**: pytest with pytest-asyncio (Python 3.12, Ubuntu)
- **Security**: Secret scanning (blocks hardcoded API keys)
- **Build**: Rust release binary (cargo build --release, LTO)
