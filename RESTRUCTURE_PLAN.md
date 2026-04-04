# 0DTE Trading Bot — Full Restructure Plan

## What's Wrong Right Now (Audit Findings)

### 1. Three Position Systems, Zero Coordination
The bot has **three independent systems** managing positions with no synchronization:

- **PositionTracker** (`position_tracker.py`) — computes live P&L, checks exit triggers, updates MFE/MAE
- **AutonomousTrader** (`autonomous_trader.py`) — watches signals, auto-executes, has its OWN exit rules
- **PaperTrader** (`paper_trader.py`) — executes orders (simulation or Alpaca paper), computes P&L at exit

Each calculates P&L differently. Exit logic lives in two places (position_tracker AND autonomous_trader config). Race conditions possible when multiple systems write to the same SQLite trades table.

### 2. Data Source Mixing
- ThetaData provides options chains, Greeks, IV — but Alpaca is used as fallback with different Greeks calculations
- Position tracker may use stale chain data when sources lag
- No validation of data freshness or source reliability
- Greeks from ThetaData Black-Scholes vs Alpaca snapshots can diverge

### 3. No Signal Testing
- Zero backtesting capability
- No historical signal replay
- No way to measure if signals actually predict profitable trades
- Weight learner only adjusts from live/paper trades (forward-looking, no historical validation)

### 4. Limited LLM Usage
- Only the News Agent uses Claude (Haiku, 150 tokens max)
- All other decisions are pure heuristics
- No LLM validation of trade entries/exits
- No market regime analysis via LLM

---

## Research: How the Best AI Trading Bots Work

### Architecture Pattern That Works Best: LLM as Validator + Multi-Agent Debate

Based on research into 6+ active open-source projects (Kalshi bot, Polymarket bot, TradingAgents framework, LLM-TradeBot, etc.):

**What actually works:**
- **Ensemble consensus** — Multiple models voting produces more robust signals than any single model
- **LLM as validator, not primary decider** — Traditional signals + LLM final check outperforms either alone
- **Multi-agent debate** — Bull/Bear researchers argue, Risk Manager approves. TradingAgents (ICML 2025) showed improvements in cumulative returns, Sharpe ratio, and max drawdown
- **0DTE + ensemble signals** — Documented case: $20K → $400K in 1 year using LLM probability estimates with time decay exploitation

**What fails:**
- LLM as sole decision maker (inconsistent strategy adherence, hallucinated data)
- No regime awareness (over-aggressive in bear markets, too conservative in bull)
- Trusting LLM memory for prices/Greeks instead of API data
- Single-model strategies (too volatile)

### Token Optimization (Critical for Cost Control)
- **Prompt caching**: Cache daily market regime, reuse all day (73% cost reduction)
- **Model routing**: Simple checks → Claude Haiku ($0.25/1M tokens), complex decisions → Sonnet/Opus
- **Structured minimal prompts**: Only pass essential indicators, not raw data dumps
- **Expected cost**: <$1-2/day at our trading frequency

### Backtesting for LLM Bots
- Can't replay LLM calls deterministically — cache responses during dev, replay from cache
- Two-layer: historical backtest on cached LLM responses + live paper trading validation
- Track: win rate, Sharpe, Sortino, max drawdown, expectancy per signal tier

---

## Research: Professional Trading Dashboard Design

### What the Pros Use
Analyzed: Thinkorswim, DAS Trader, Tradovate, TradingView, Interactive Brokers, Tastytrade

**Common layout pattern for active day trading:**

```
┌─────────────────────────────────────────────────────────┐
│  HEADER: Account Balance | Day P&L | Time to Expiry     │
│          Portfolio Greeks (Δ Γ Θ Ν) | Risk Status       │
├────────────────────────────────┬────────────────────────┤
│                                │  SIGNAL FEED           │
│  CHART + LEVELS               │  (live signals with     │
│  (price action, VWAP, key     │   confidence, direction │
│   support/resistance)          │   LLM verdict)         │
│                                │                        │
│                                ├────────────────────────┤
│                                │  AI AGENT PANEL        │
│                                │  (agent verdicts,      │
│                                │   debate summary)      │
├────────────────────────────────┴────────────────────────┤
│  TABS: Open Positions | Closed Trades | Orders | Perf   │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Symbol | Strike | Exp | Side | Qty | Entry | Last  │ │
│  │ P&L $ | P&L % | Δ | Γ | Θ/min | IV% | Exit Trig  │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**0DTE-specific elements:**
- Time-to-expiry countdown (color-coded: green > 2hr, yellow > 30min, red < 30min)
- Theta decay curve ("hockey stick" acceleration)
- P&L velocity display (+$X/min)
- Max loss scenario always visible
- 3:00 PM hard stop warning

---

## Proposed New Architecture

### Phase 1: Clean Foundation (Week 1)

**1A. Unified Position Manager** — Replace three systems with one:

```
NEW: PositionManager (single source of truth)
├── Entry execution (absorbs PaperTrader's order logic)
├── Live P&L tracking (absorbs PositionTracker's pricing)
├── Exit rule engine (single definition, not scattered)
├── MFE/MAE tracking
├── Risk budget enforcement
└── Database writes (single writer, no race conditions)

REMOVED: Separate PositionTracker, merge into PositionManager
SIMPLIFIED: PaperTrader becomes thin execution layer only
SIMPLIFIED: AutonomousTrader becomes signal consumer + PositionManager caller
```

**1B. Clean Data Layer** — One source of truth per data type:

```
DataRouter (new)
├── Options Chain: ThetaData ONLY (no Alpaca fallback for Greeks)
├── Stock Quote: ThetaData snapshot → Alpaca fallback
├── Historical Bars: Alpaca (has better intraday) → ThetaData EOD fallback
├── Order Execution: Alpaca ONLY (our broker)
└── Each response tagged with: source, timestamp, staleness_ms
```

**1C. Unified Dashboard** — Single-page with tabs:

```
Tab 1: TRADING (default)
  - Open Positions table (live P&L, Greeks, exit triggers, time-to-expiry)
  - Quick actions: manual exit, adjust stop
  - Autotrader status + controls (enable/disable, config)

Tab 2: SIGNALS
  - Live signal feed with confidence tiers
  - AI agent verdicts (all 5 agents)
  - LLM validation result
  - Confluence breakdown

Tab 3: HISTORY
  - Closed trades table (entry/exit, P&L, grade, duration)
  - Filterable by date, direction, tier, exit reason

Tab 4: PERFORMANCE
  - Equity curve
  - Win rate, Sharpe, Sortino, max drawdown
  - Per-tier breakdown (TEXTBOOK vs HIGH vs VALID)
  - Signal accuracy metrics

Tab 5: BACKTEST (new)
  - Historical signal replay results
  - Strategy comparison
  - Paper trading validation log
```

### Phase 2: LLM Integration (Week 2)

**Architecture: Signal Pipeline + LLM Validator + Agent Debate**

```
Market Data (ThetaData)
    ↓
Signal Engine (existing 16 factors + confluence)
    ↓ generates candidate signal
LLM Validator (NEW)
    ├── Receives: signal direction, confidence, top 5 factors,
    │   current regime, recent price action summary, Greeks snapshot
    ├── Claude Haiku for routine validation ($0.001/call)
    ├── Claude Sonnet for edge cases (low confidence, regime change)
    ├── Returns: APPROVE / REJECT / REDUCE_SIZE + reasoning
    └── Cached regime context (refreshed every 30 min, not per-trade)
    ↓ if APPROVED
Agent Debate (enhanced from existing)
    ├── Bull Agent: argues FOR the trade
    ├── Bear Agent: argues AGAINST
    ├── Risk Agent: evaluates sizing + worst case
    └── Returns: consensus + final confidence adjustment
    ↓ if consensus reached
Position Manager → Execute
```

**Token Budget:**
- Regime analysis: ~500 tokens input, ~200 output, every 30 min = ~32 calls/day
- Signal validation: ~300 tokens input, ~100 output, ~20-50 signals/day
- Agent debate: ~800 tokens total, only for APPROVED signals (~5-15/day)
- **Estimated daily cost: $0.50-$1.50 using Haiku + Sonnet routing**

### Phase 3: Testing Infrastructure (Week 2-3)

**3A. Signal Backtester:**
```
Historical Data (ThetaData/Alpaca bars + options chains)
    ↓
Replay Engine (feeds data to signal engine chronologically)
    ↓
Signal Engine (same code as live, no modifications)
    ↓
Result Collector (records: signal time, direction, confidence, tier)
    ↓
P&L Calculator (checks what would have happened: entry → exit)
    ↓
Report Generator (win rate, P&L curve, per-tier stats)
```

**3B. Paper Trading Validation:**
- Run signals live against Alpaca paper account
- Track every signal, whether traded or filtered
- After 30 days: compare signal accuracy vs actual P&L
- A/B compare: signals-only vs signals+LLM-validated

**3C. Signal Quality Metrics (tracked automatically):**
- Signal accuracy: % of signals that were profitable if held to target
- False positive rate: % of signals that hit stop-loss
- Tier reliability: accuracy breakdown by TEXTBOOK / HIGH / VALID
- Time-to-profit: how long from entry to reaching target
- Optimal exit: was the actual exit close to the best possible exit (MFE)?

---

## Implementation Priority

| Priority | Task | Why |
|----------|------|-----|
| P0 | Unified PositionManager | Eliminates duplication, race conditions, mixed P&L |
| P0 | Clean DataRouter | Stops data source mixing, ensures consistent Greeks |
| P0 | New dashboard with tabs | Single organized view, no confusion |
| P1 | LLM Validator in signal pipeline | Biggest edge improvement with lowest cost |
| P1 | Paper trading validation tracking | Can't improve what you can't measure |
| P2 | Historical backtester | Validate strategy before risking capital |
| P2 | Agent debate system | Higher conviction trades, lower false positives |
| P3 | Signal quality dashboard | Long-term optimization data |
| P3 | A/B testing framework | Compare strategies side by side |

---

## Files to Create / Modify

### New Files:
- `dashboard/position_manager.py` — Unified position management
- `dashboard/data_router.py` — Clean data source routing
- `dashboard/llm_validator.py` — LLM trade validation
- `dashboard/backtester.py` — Historical signal replay
- `dashboard/signal_metrics.py` — Signal quality tracking
- `dashboard/static/trading.html` — New unified dashboard

### Files to Simplify:
- `dashboard/paper_trader.py` → Thin execution layer only
- `dashboard/autonomous_trader.py` → Signal consumer, delegates to PositionManager
- `dashboard/position_tracker.py` → Absorbed into PositionManager (eventually remove)
- `dashboard/signal_api.py` → Cleaner endpoints, delegates to PositionManager

### Files Unchanged:
- `dashboard/confluence.py` — Keep v8 adaptive scoring
- `dashboard/signal_engine.py` — Keep 16-factor engine
- `dashboard/agents/` — Keep existing agents, enhance with debate
- `dashboard/signal_db.py` — Keep schema, add backtest tables

---

## Key References

- [TradingAgents (ICML 2025)](https://github.com/TauricResearch/TradingAgents) — Multi-agent debate framework
- [Kalshi AI Trading Bot](https://github.com/ryanfrigo/kalshi-ai-trading-bot) — 5-model ensemble with Kelly sizing
- [Polymarket AI Bot](https://github.com/dylanpersonguy/Fully-Autonomous-Polymarket-AI-Trading-Bot) — Multi-model ensemble + 15 risk checks
- [LLM Options Trading ($20K→$400K)](https://scriptedalchemy.medium.com/from-20k-to-400k-in-a-year-my-llm-options-trading-experiment-1f9d6cecc719) — Real 0DTE case study
- [StockBench (arXiv)](https://arxiv.org/html/2510.02209v1) — LLM trading benchmark
- [Can LLMs Beat Markets? (arXiv)](https://arxiv.org/html/2505.07078v3) — Critical: LLMs alone fail long-term
