# AI Trading Bot — Edge Research Plan

## The Problem: Everyone Has the Same Tools

Every retail trader has RSI, MACD, moving averages, and basic options chain data. Our current 10-factor confluence scoring already puts us ahead of most, but to consistently win at 0DTE SPY options, we need to analyze what others can't or don't.

This document is the result of deep research into what actually moves markets, what professional quant firms use, and what's realistically implementable in our Python-based bot.

---

## What the Research Says Actually Works for 0DTE SPY

### Tier 1 — High Conviction (Strong Evidence)

These signals have academic backing AND are used by professional prop firms:

**1. Dealer Hedging Flows: Gamma + Vanna + Charm**
- Our GEX engine covers gamma. But vanna (delta sensitivity to IV) and charm (delta decay over time) are equally important for 0DTE.
- Charm flows are the PRIMARY driver of 1:30-3:00 PM moves on expiration day. Dealers aggressively rebalance delta exposure as time passes, amplifying afternoon trends by 15-30 basis points.
- Vanna flows drive mean-reversion when IV drops — dealers who were hedging negative vanna unwind, creating buying pressure.
- Data: We can compute this from ThetaData Greeks (already have the chain data).
- Edge: VannaCharm.com reports 99% directional accuracy for 0DTE expirations when gamma + vanna + charm are combined.

**2. Order Flow Toxicity (VPIN)**
- Volume-synchronized Probability of Informed Trading — measures whether informed traders are present.
- Predicted the 2010 Flash Crash >1 hour in advance.
- Academic evidence: Predicts extreme volatility moves, especially during elevated volatility periods.
- Data: Can compute from ThetaData trade stream (we already have this).
- Caveat: Works best in volatile regimes; weak signal in calm markets.

**3. Options Sweep Detection**
- Large orders split across multiple exchanges to minimize impact while filling urgently.
- When someone pays the ask across 5 exchanges simultaneously to fill 1000 contracts, they know something.
- Data: ThetaData bulk trade endpoints provide individual trades with exchange, price, and timestamp.
- Implementation: Parse trade stream, detect multi-exchange fills within 500ms at same strike/expiry.

**4. VIX Term Structure Regime**
- Contango (84% of time): Near-term VIX < longer-dated = calm. Short premium has edge.
- Backwardation (16%): Near-term VIX > longer-dated = stress. Expect reversals, wider swings.
- Data: FREE via CBOE, FRED, VIXcentral.
- Use: Always-on regime filter. In backwardation, reduce position sizes 30-50%.

**5. Economic Calendar Event Positioning**
- CPI, FOMC, NFP create ±1-3% SPY moves. IV spikes 50-150% before data.
- Professional traders position 5-15 minutes before releases; detecting this pre-event flow is actionable.
- Data: FREE via Finnhub or Trading Economics API.
- Use: Event-driven. On event days, adjust the bot's behavior entirely.

### Tier 2 — Moderate Conviction (Evidence with Caveats)

**6. Bond/Treasury Lead-Lag**
- 10Y yields lead SPY by 5-30 minutes on macro data days.
- TLT down 1%+ before SPY reacts → expect SPY down within 30 minutes.
- 2Y-10Y spread compression → recession risk → equity selloff.
- Data: FREE via FRED API (DGS10, T10Y2Y).
- Caveat: Lead-lag only reliably exists on high-impact data days, not every day.

**7. Dollar Index (DXY) Correlation**
- 75-90% inverse correlation with SPY (stronger on down days).
- DXY rallying hard → reduce SPY long bias.
- Data: Free via Yahoo Finance / TradingView.
- Use: Always-on bias filter. Each 1% DXY move correlates to ~0.3-0.5% SPY move opposite.

**8. NYSE TICK Extremes**
- Real-time count of stocks upticking vs downticking.
- >600 = strong buying pressure, <-600 = strong selling pressure.
- Mean-reverts within minutes — perfect for fading extreme moves with 0DTE.
- Data: Requires real-time feed (TradingView, or compute from Alpaca sector ETFs as proxy).

**9. Sector Divergence (XLK, XLF, XLE vs SPY)**
- If XLK (tech, >30% of SPY weight) is rolling over but SPY hasn't moved, SPY follows within 30-60 min.
- XLF divergence on rate-related news is a leading signal.
- Data: FREE via Alpaca (already have this).
- Use: Always-on. Track 5-min relative strength of top 3 sector ETFs vs SPY.

**10. Unusual Options Activity (UOA) — Sweeps + Blocks**
- Large sweep orders (filled at ask across exchanges) signal institutional conviction.
- Block trades >100 contracts on lit exchanges — need to distinguish informed flow from hedging.
- Data: ThetaData trade stream (have it) or Unusual Whales API ($35-250/month).
- Caveat: 30-40% predictive accuracy alone. Must combine with GEX and flow toxicity.

### Tier 3 — Conditional / Weak Edge

**11. Dark Pool Prints**
- Institutional block trades on ATS networks predict direction BUT with a 30min-2hr lag.
- "Splash effect" — initial opposite-direction move before sustained move.
- Data: Unusual Whales ($35/mo) or Cheddar Flow.
- Verdict: Better for swing than 0DTE. Use as daily bias context only.

**12. News/Social Sentiment**
- 2025 academic study: Explicit sentiment scores lack robust predictive power for intraday.
- SPY is too heavily arbitraged by quants — sentiment is priced in almost instantly.
- StockTwits/Reddit sentiment is retail noise, not edge.
- Data: Free (StockTwits, Reddit APIs).
- Verdict: Daily bias color only. Not a factor in the scoring model.

**13. Max Pain / Pinning**
- Works 30-40% of time for SPY. Strongest in final 60 minutes.
- Collapses during macro events.
- We already have this in our options_analytics module.
- Verdict: Keep as is. Don't increase its weight.

**14. SEC Form 4 / 13F Filings**
- Too slow for intraday (filed same-day or next-day, 13F quarterly).
- Skip entirely for 0DTE.

---

## What We Already Have vs What We Need

### Already Built (Phase 1-2):
- ✅ GEX/DEX (gamma exposure, dealer positioning)
- ✅ 10-factor confluence scoring
- ✅ PCR, Max Pain, IV Rank
- ✅ Order flow imbalance, CVD divergence
- ✅ VWAP rejection, volume spike, delta regime
- ✅ Time of day scoring
- ✅ ThetaData chain with Greeks (delta, gamma, theta, vega)
- ✅ Paper trading + P&L tracking + trade grading

### New Factors to Build:

| Priority | Factor | Data Source | Cost | Complexity | Expected Edge |
|----------|--------|-------------|------|------------|---------------|
| P0 | Vanna & Charm flows | ThetaData (have it) | $0 | Medium | High — 0DTE game-changer |
| P0 | VIX term structure regime | FRED/CBOE (free) | $0 | Low | High — regime filter |
| P0 | Economic calendar awareness | Finnhub (free) | $0 | Low | High — event days |
| P1 | Bond yield lead-lag | FRED API (free) | $0 | Low | Medium — macro days |
| P1 | Sweep detection | ThetaData trade stream | $0 | Medium | Medium-High |
| P1 | VPIN (order flow toxicity) | ThetaData trade stream | $0 | Medium | Medium-High |
| P1 | DXY correlation filter | Yahoo/Alpaca (free) | $0 | Low | Medium |
| P2 | Sector divergence (XLK/XLF/XLE) | Alpaca (free) | $0 | Low | Medium |
| P2 | Correlation regime (SPY-TLT HMM) | FRED + computation | $0 | Hard | Medium |
| P2 | ES futures lead-lag | Needs CME data | $50-200/mo | Hard | Medium-High |
| P3 | Unusual Whales integration | Unusual Whales API | $35-250/mo | Low | Medium (confirmation) |
| P3 | Dark pool context | Unusual Whales API | incl. above | Low | Low (daily bias) |

---

## Proposed Architecture: Multi-Layer Intelligence

```
Layer 1: REGIME DETECTION (runs every 60 seconds)
├── VIX term structure: contango/backwardation → position sizing multiplier
├── Correlation regime: SPY-TLT rolling corr → HMM state (risk-on/off/transition)
├── DXY trend: Dollar strength filter → directional bias adjustment
└── Output: regime_state = {sizing_mult, directional_bias, volatility_regime}

Layer 2: EVENT AWARENESS (runs on schedule)
├── Economic calendar: Today's releases, time until next, expected impact
├── FOMC/CPI/NFP proximity: Pre-event (increase IV weight), post-event (IV crush trade)
├── OPEX/quad witching detection: Adjust gamma thresholds on expiration-heavy days
└── Output: event_context = {event_type, minutes_to_event, impact_level, stance}

Layer 3: MICROSTRUCTURE SIGNALS (runs every 5-15 seconds)
├── Vanna flows: Net dealer vanna → directional pull (especially 1:30-3 PM)
├── Charm flows: Delta decay acceleration → afternoon trend amplifier
├── Sweep detection: Multi-exchange fills → institutional conviction meter
├── VPIN: Order flow toxicity → informed trading probability
├── Sector divergence: XLK/XLF relative strength vs SPY
└── Output: micro_signals = {vanna_bias, charm_pressure, sweep_score, toxicity, sector_divergence}

Layer 4: ENHANCED CONFLUENCE (existing + new)
├── Existing 10 factors (order flow, CVD, GEX, DEX, VWAP, volume, delta, PCR, max pain, time)
├── + Vanna/Charm alignment (new factor)
├── + Regime adjustment (multiply/dampen scores based on Layer 1)
├── + Event adjustment (suppress/boost signals around events from Layer 2)
├── + Microstructure confirmation (Layer 3 sweep/VPIN as conviction multiplier)
└── Output: enhanced_signal with regime-adjusted confidence

Layer 5: ADAPTIVE FEEDBACK (Phase 3 — learns from trades)
├── Which factors predicted winners? → Increase weight
├── Which factors predicted losers? → Decrease weight
├── Regime-specific factor performance → Different weights per regime
└── Output: optimized_weights per regime per factor
```

---

## Implementation Plan

### Phase 3A: Core Edge Factors (P0 — Zero Additional Cost)

Build 3 new modules using data we already have:

**1. `vanna_charm_engine.py`** — Compute aggregate vanna/charm from ThetaData Greeks chain
- Net dealer vanna exposure across all strikes
- Charm acceleration curve (how fast delta is decaying)
- Scoring: Vanna alignment with signal direction, charm pressure in afternoon

**2. `regime_detector.py`** — Multi-signal regime classification
- VIX term structure (contango/backwardation from VIX vs VIX3M)
- SPY-TLT rolling correlation (60-min window, HMM for state detection)
- DXY trend filter (dollar index direction and strength)
- Output: Regime state with position sizing multiplier

**3. `event_calendar.py`** — Economic event awareness
- Pull today's events from Finnhub free API
- Classify impact level (high/medium/low)
- Pre-event mode: Suppress new entries 15 min before high-impact releases
- Post-event mode: Enable IV crush trades after release

**4. Upgrade `confluence.py`** — Integrate new factors into scoring
- Add vanna/charm as Factor 11-12 (or replace lower-value factors)
- Apply regime multiplier to final composite score
- Apply event adjustments (suppress signals pre-FOMC, etc.)

### Phase 3B: Microstructure Edge (P1 — Zero Additional Cost)

**5. `sweep_detector.py`** — Parse ThetaData trade stream for sweeps
- Identify multi-exchange fills within 500ms at same strike/expiry
- Classify as bullish (at ask) or bearish (at bid)
- Output: Sweep conviction score fed into confluence

**6. `flow_toxicity.py`** — VPIN calculation
- Volume-synchronized probability of informed trading
- Rolling window computation from trade stream
- High VPIN + our signal alignment = higher conviction entry

**7. `sector_monitor.py`** — Track sector ETF divergences
- XLK, XLF, XLE 5-min relative strength vs SPY
- Divergence detection → reversal warning or trend confirmation
- Bond yield (10Y) direction as macro overlay

### Phase 3C: Paid Data Integration (P2-P3 — If Budget Approved)

**8. Unusual Whales API** ($35-250/month)
- Real-time options flow + dark pool prints
- Would supplement our ThetaData sweep detection with cleaner labeling
- Congressional trading alerts (unique data)

**9. ES Futures Lead-Lag** ($50-200/month for CME data)
- Sub-second lead-lag between ES and SPY
- Professional desks trade this as core strategy
- Requires separate data feed

---

## Cost Summary

| Phase | Monthly Cost | New Factors | Expected Win Rate Improvement |
|-------|-------------|-------------|-------------------------------|
| 3A (P0) | $0 | Vanna/Charm, Regime, Events | +10-20% |
| 3B (P1) | $0 | Sweeps, VPIN, Sectors, Bonds | +5-15% |
| 3C (P2) | $35-250 | UOA, Dark Pool | +3-8% (confirmation layer) |
| 3C (P3) | $50-200 | ES Lead-Lag | +5-10% (speed edge) |

**Phase 3A alone gets us 80% of the edge for $0 in additional cost.**

---

## What Makes This Different From Retail

Most retail traders:
- Look at charts and indicators AFTER the move
- Don't understand dealer positioning or hedging dynamics
- Ignore macro regime entirely
- Trade the same strategy in every market condition
- Don't measure or grade their execution

Our bot will:
- Detect the REGIME first, then adapt strategy (no one-size-fits-all)
- Understand WHY price is moving (dealer flows, not just "price went up")
- Know WHEN to sit out (pre-FOMC, daily loss limit, wrong regime)
- Detect institutional positioning in real-time (sweeps, VPIN, vanna)
- Grade every trade and learn from it (Phase 3 adaptive feedback)
- Combine 15+ uncorrelated signals that retail doesn't have access to

---

## Decision Points

Before we build, we need to decide:

1. **Phase 3A first?** (Vanna/Charm + Regime + Events — $0 cost, highest edge)
2. **Should we subscribe to Unusual Whales?** ($35/mo minimum for flow + dark pool)
3. **ES futures data?** (Requires separate CME subscription — defer until Phase 3C?)
4. **How many factors is too many?** (Overfitting risk — need backtesting framework)

---

*Research conducted March 2026. Sources include academic papers, quant trading firm publications, API documentation, and market microstructure research.*
