# SPY/SPX 0DTE Options Trading Bot

A real-time autonomous trading platform for 0DTE (zero days to expiration) SPY/SPX options. Features a confluence-based signal engine, AI-powered trade validation, order flow analysis via a Rust WebSocket engine, and a professional dark-themed dashboard — all built for a $5K cash account trading single-leg options.

## Architecture

```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐
│  ThetaData   │───▶│ Signal Engine │───▶│ LLM Validator │
│  (Options)   │    │ (Confluence)  │    │  (Claude)     │
└─────────────┘    └──────────────┘    └───────┬───────┘
┌─────────────┐    ┌──────────────┐            │
│   Alpaca     │───▶│ Flow Engine   │            ▼
│  (Broker)    │    │   (Rust WS)   │    ┌──────────────┐
└─────────────┘    └──────────────┘    │ Paper Trader  │
                                        │  (Alpaca)     │
       ┌────────────────────────────────┘──────────────┘
       ▼
┌──────────────────────────────────────────────────────┐
│              FastAPI Dashboard (8000)                  │
│  Candles │ Positions │ Combined │ Options │ AI Agent  │
└──────────────────────────────────────────────────────┘
```

## Quick start

```bash
# 1. Clone and enter
git clone <repo-url> && cd ai-trading-bot

# 2. Environment
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Fill in your Alpaca + ThetaData keys

# 4. Run
python run_dashboard.py
# Open http://localhost:8000
```

## Project structure

```
├── dashboard/          # FastAPI app + monolithic HTML dashboard
│   ├── app.py          # Entry point, WebSocket, CORS
│   ├── api_routes.py   # REST endpoints (signals, trades, P&L, market)
│   ├── signal_api.py   # Signal engine API bridge
│   ├── pm_api.py       # Position manager API bridge
│   ├── agents/         # AI agent layer (autonomous trader, LLM validator)
│   └── static/         # Frontend (flow-dashboard.html + CSS/JS)
├── engine/             # Core trading logic (confluence, signals, risk)
├── config/             # Settings, environment config
├── data/               # ThetaData + market data providers
├── docs/               # Architecture, setup guides, references
├── flow-engine/        # Rust WebSocket order flow engine
├── strategies/         # Trading strategy implementations
├── tests/              # Pytest suite
└── utils/              # Shared utilities
```

## Data providers

| Provider | Role | Data |
|----------|------|------|
| **ThetaData** | Primary options data | Greeks, IV, tick-level NBBO, chains |
| **Alpaca** | Broker + equities | Order execution, equity bars, fallback data |

## Key features

**Signal engine** — Confluence scoring across technicals, order flow, options greeks, and market regime. Signals are tiered (DEVELOPING → VALID → STRONG → EXCEPTIONAL) with configurable thresholds.

**LLM validator** — Claude evaluates trade setups before execution: checks alignment between signal, market structure, and risk parameters. Reduces false signals.

**Rust flow engine** — High-performance WebSocket server for real-time order flow (sweeps, blocks, absorption detection, CVD). Sub-200ms latency.

**Dashboard** — 8-tab professional UI: Charts, Flow, Candles, Options, Signals, AI Agent, Journal, and Settings. Dark-themed with real-time data, order flow visualization, and trade management.

**Dynamic exit engine** — Partial profit-taking, trailing stops, time-based exits tuned for 0DTE theta decay.

## Development

```bash
# Lint
ruff check .

# Format
ruff format .

# Test
pytest tests/ -v

# Run flow engine (requires Rust)
cd flow-engine && cargo run --release
```

API docs are auto-generated at [localhost:8000/docs](http://localhost:8000/docs) when the server is running.

## Security

- `.env` is gitignored — never commit API keys
- `.env.example` contains the template with no real values
- CI includes a secret scan that blocks pushes containing key patterns
- All API keys should be rotated periodically

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full development guide.

## Documentation

| Doc | Purpose |
|-----|---------|
| `docs/ARCHITECTURE.md` | System design and component interactions |
| `docs/INSTALLATION.md` | Detailed setup instructions |
| `docs/DASHBOARD_SETUP.md` | Dashboard integration guide |
| `CONTRIBUTING.md` | Development workflow and standards |

## License

Private — all rights reserved.
