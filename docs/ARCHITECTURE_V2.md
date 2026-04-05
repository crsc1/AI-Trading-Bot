# Order Flow Trading Platform — Architecture V2

## Philosophy
Trade SPY options based on real-time order flow signals — the way skilled
human order flow traders do. No indicator soup. No heavy ML. Pure flow:
footprint imbalances, CVD, absorption, sweeps, delta flips.

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      FRONTEND (Next.js / Tauri)                 │
│  ┌──────────┐  ┌──────────────────┐  ┌───────────────────────┐  │
│  │ Options   │  │ Price Chart      │  │ Agent Reasoning Panel │  │
│  │ Chain +   │  │ (LW Charts)      │  │ - Current signals     │  │
│  │ Agent     │  │ + Footprint/CVD  │  │ - Confidence / Risk   │  │
│  │ Status    │  │ (Canvas/PixiJS)  │  │ - Human overrides     │  │
│  └──────────┘  └──────────────────┘  └───────────────────────┘  │
│                         ▲ WebSocket (JSON)                      │
└─────────────────────────┼───────────────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────────────┐
│              PYTHON AGENT LAYER (LangGraph)                     │
│                         │                                       │
│  ┌──────────────┐  ┌────┴──────┐  ┌───────────┐  ┌──────────┐  │
│  │ Order Flow   │  │ Setup     │  │ Risk &    │  │Supervisor│  │
│  │ Analyst      │  │ Detector  │  │ Executor  │  │          │  │
│  │              │  │           │  │           │  │          │  │
│  │ Reads flow   │  │ Pattern   │  │ Size,     │  │ Approves │  │
│  │ events,      │→ │ matching: │→ │ entry via │→ │ trades,  │  │
│  │ detects      │  │ absorption│  │ Alpaca,   │  │ enforces │  │
│  │ imbalances   │  │ + delta   │  │ stop/tgt  │  │ limits   │  │
│  └──────┬───────┘  │ flip etc  │  │ mgmt      │  │          │  │
│         │          └───────────┘  └───────────┘  └──────────┘  │
│         ▲ WebSocket (structured events)                        │
└─────────┼──────────────────────────────────────────────────────┘
          │
┌─────────┼──────────────────────────────────────────────────────┐
│         │        RUST ENGINE (Tokio + Axum)                    │
│         │                                                      │
│  ┌──────┴───────────────────────────────────────────────────┐  │
│  │                    Event Publisher                        │  │
│  │  Publishes: FootprintUpdate, CVDUpdate, ImbalanceAlert,  │  │
│  │  SweepDetected, DeltaFlip, AbsorptionSignal              │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                         │                                      │
│  ┌──────────────────────┴───────────────────────────────────┐  │
│  │              Order Flow Engine                            │  │
│  │                                                           │  │
│  │  • Footprint builder (price-level bid/ask volume grid)    │  │
│  │  • CVD calculator (running cumulative delta)              │  │
│  │  • Imbalance detector (stacked bid/ask ratios)            │  │
│  │  • Large trade / sweep detector                           │  │
│  │  • Absorption detector (volume absorbed at level)         │  │
│  │  • Delta flip detector (sign change in rolling delta)     │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                         │                                      │
│  ┌──────────────────────┴───────────────────────────────────┐  │
│  │              Tick Ingestion                                │  │
│  │  ThetaData Terminal REST → parse trades + NBBO quotes     │  │
│  │  Classify: trade at ask = buy, trade at bid = sell        │  │
│  │  Fallback: tick rule if no quote available                │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

## Data Flow (Per Tick)

1. ThetaData streams a trade tick: `{price, size, timestamp, conditions}`
2. Rust engine classifies buy/sell using latest NBBO quote
3. Updates footprint grid (price-level → {bid_vol, ask_vol})
4. Updates CVD (running sum of signed volume)
5. Checks imbalance rules (e.g., ask_vol > 3× bid_vol at level)
6. Checks sweep rules (large trade, aggressive side, multiple levels)
7. Checks absorption (high volume at level, price NOT moving through)
8. Publishes structured events via WebSocket to Python agents
9. Agents evaluate, detect setups, manage risk, execute

## Event Types (Rust → Python)

```json
{"type": "footprint",   "bar_time": 1711324800, "levels": [...]}
{"type": "cvd",         "value": 15230, "delta_1m": 3400, "delta_5m": -1200}
{"type": "imbalance",   "price": 562.35, "side": "buy", "ratio": 4.2, "stacked": 3}
{"type": "sweep",       "price": 562.40, "size": 5000, "side": "buy", "levels_hit": 3}
{"type": "absorption",  "price": 562.00, "volume": 12000, "side": "bid", "held": true}
{"type": "delta_flip",  "from": "sell", "to": "buy", "cvd_at_flip": -5400}
{"type": "large_trade", "price": 562.35, "size": 2500, "side": "buy"}
```

## Order Flow Concepts Implemented

### Footprint Chart
Grid of price levels × time bars. Each cell shows volume traded at bid
vs at ask. Reveals where aggressive buying/selling is concentrated.

### CVD (Cumulative Volume Delta)
Running sum: +volume for buys, -volume for sells. Divergence between
CVD and price = smart money signal. Rising price + falling CVD = sellers
absorbing, likely reversal.

### Imbalance
When ask volume exceeds bid volume (or vice versa) by 3:1+ ratio at a
price level. Stacked imbalances (3+ consecutive levels) = strong
directional conviction.

### Absorption
High volume at a price level where price does NOT break through. Means
a large participant is absorbing all the aggression. Reversal signal.

### Sweep
Large order that aggressively takes liquidity across multiple price
levels in rapid succession. Shows urgency.

### Delta Flip
CVD changes sign (negative to positive or vice versa). Combined with
price at support/resistance = entry signal.

## Risk Rules (Hardcoded)
- Max 1-2% account risk per trade
- Daily loss limit: 3-5% of account
- Max 2 concurrent positions
- Paper trading only until 200+ trades with positive expectancy
- Every trade logged with flow-based reasoning

## File Structure
```
AI Trading Bot/
├── flow-engine/           # Rust: tick ingestion + order flow math
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs        # Axum server + WebSocket publisher
│       ├── ingestion.rs   # ThetaData tick reader
│       ├── classifier.rs  # Buy/sell classification
│       ├── footprint.rs   # Footprint grid builder
│       ├── cvd.rs         # CVD calculator
│       ├── detectors.rs   # Imbalance, sweep, absorption, delta flip
│       └── events.rs      # Event types + serialization
├── agents/                # Python: LangGraph multi-agent system
│   ├── pyproject.toml
│   ├── flow_analyst.py    # Order Flow Analyst agent
│   ├── setup_detector.py  # Setup Detector agent
│   ├── risk_executor.py   # Risk & Executor agent
│   ├── supervisor.py      # Supervisor agent
│   └── ws_client.py       # WebSocket client to Rust engine
├── dashboard/             # Current dashboard (evolving)
│   ├── app.py
│   └── static/
└── .env
```
