"""
Confluence Engine — Setup + Trigger framework (v4: 15-factor + regime + events).

Evaluates all confluence factors and determines signal direction + confidence.
Includes order flow analysis, session context detection, strike selection, and risk calculation.

v2: 10-factor scoring. GEX, DEX, PCR, Max Pain, Volume Spike, Delta Regime.
v3: +Vanna/Charm (12 factors) + regime multiplier + event awareness.
v4: +Sweep detection, VPIN flow toxicity, sector divergence (15 factors).
    All data from existing Alpaca + ThetaData — $0 additional cost.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone, time as dt_time
import math
import statistics
import logging

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except ImportError:
    ET = timezone(timedelta(hours=-4))

from .market_levels import MarketLevels
from .market_internals import MarketBreadth, score_market_breadth
from .gex_regime import get_regime_profile, apply_regime_to_risk
from .vol_analyzer import VolAnalysis, score_vol_edge, apply_vol_to_risk
from .config import cfg

logger = logging.getLogger(__name__)

# Configuration constants
ACCOUNT_BALANCE = cfg.ACCOUNT_BALANCE
SYMBOL = "SPY"

# ── Active trading symbol (user-selectable: SPY or SPX) ──
_active_symbol: str = "SPY"

# SPX ≈ SPY × 10 (used when we need SPX index price but only have SPY data)
SPX_MULTIPLIER = cfg.SPX_MULTIPLIER


def get_active_symbol() -> str:
    """Return the currently selected trading symbol."""
    return _active_symbol


def set_active_symbol(sym: str) -> str:
    """Set the active trading symbol. Returns the validated symbol."""
    global _active_symbol
    sym = sym.upper().strip()
    if sym not in ("SPY", "SPX"):
        raise ValueError(f"Unsupported symbol: {sym}. Must be SPY or SPX.")
    _active_symbol = sym
    return _active_symbol


def derive_spx_price(spy_price: float) -> float:
    """Derive approximate SPX index price from SPY ETF price."""
    return round(spy_price * SPX_MULTIPLIER, 2)


TIER_TEXTBOOK = cfg.TIER_TEXTBOOK   # 8.0+/10 composite → perfect setup
TIER_HIGH = cfg.TIER_HIGH       # 6.0+/10 composite → strong setup
TIER_VALID = cfg.TIER_VALID      # 4.5+/10 composite → acceptable
TIER_DEVELOPING = cfg.TIER_DEVELOPING # below 4.5 → watch only
MIN_TRADE_CONFIDENCE = cfg.MIN_TRADE_CONFIDENCE  # Lowered from 0.55 — let more signals through, filter by tier

# ── Trade Mode (exit strategy) ──
# User-selectable: "scalp", "standard", "swing"
_trade_mode: str = "scalp"  # Default to scalp for 0DTE

def get_trade_mode() -> str:
    return _trade_mode

def set_trade_mode(mode: str) -> str:
    global _trade_mode
    mode = mode.lower().strip()
    if mode not in ("scalp", "standard", "swing"):
        raise ValueError(f"Unsupported trade mode: {mode}. Must be scalp, standard, or swing.")
    _trade_mode = mode
    return _trade_mode

# Exit parameters per mode — base values, scaled by IV at runtime
TRADE_MODE_PARAMS = cfg.TRADE_MODE_PARAMS

# v2 composite scoring: 10 factors, max 10 points
# Minimum composite score for entry (maps to MIN_TRADE_CONFIDENCE)
MIN_COMPOSITE_SCORE = cfg.MIN_COMPOSITE_SCORE

RISK_TABLE = cfg.RISK_TABLE

# v7 baseline factor weights — 23 factors, total = 19.75
# These are the BASELINE weights — the weight learner can override them at runtime.
# v8: Confidence uses active-factors denominator + coverage discount (not FULL always).
# v11: Anti-correlation dampening + rebalanced confluence bonus floors.
FACTOR_WEIGHTS_BASELINE = cfg.FACTOR_WEIGHTS_BASELINE
FULL_DENOMINATOR = sum(FACTOR_WEIGHTS_BASELINE.values())  # 19.75

# ── v11: Correlated factor groups ──
# When multiple factors in the same cluster fire together, their combined
# contribution is soft-capped to avoid correlated signals inflating confidence.
# Each cluster defines: (factor_keys, max_combined_positive, max_combined_negative)
CORRELATION_CLUSTERS = [
    # Flow cluster: order flow, CVD, delta regime, sweeps, toxicity
    # Theoretical max positive: 1.5 + 1.0 + 1.0 + 0.75 + 0.5 = 4.75
    # Capped to 3.0 — still strong but prevents flow-only TEXTBOOK signals
    (["order_flow_imbalance", "cvd_divergence", "delta_regime",
      "sweep_activity", "flow_toxicity"], 3.0, -1.5),
    # Greek cluster: vanna + charm from same data source
    # Theoretical max: 0.75 + 0.75 = 1.50 → cap to 1.0
    (["vanna_alignment", "charm_pressure"], 1.0, -0.40),
    # Technical cluster: EMA/SMA, BB squeeze, support/resistance
    # Theoretical max: 0.75 + 0.75 + 1.0 = 2.50 → cap to 1.75
    (["ema_sma_trend", "bb_squeeze", "support_resistance"], 1.75, -0.60),
    # Options positioning: GEX + DEX + PCR + max pain
    # Theoretical max: 1.5 + 1.0 + 0.5 + 0.5 = 3.50 → cap to 2.5
    (["gex_alignment", "dex_levels", "pcr", "max_pain"], 2.5, -0.80),
]

# Active weights — starts as baseline, updated by weight learner at runtime
FACTOR_WEIGHTS = dict(FACTOR_WEIGHTS_BASELINE)

# Weight learner reference — set by signal_api.py on startup
_weight_learner = None


def set_weight_learner(learner):
    """Register the weight learner. Called once at startup."""
    global _weight_learner
    _weight_learner = learner


def get_active_weights() -> dict:
    """Get current active weights (from learner if available, else baseline)."""
    if _weight_learner:
        return _weight_learner.get_current_weights()
    return dict(FACTOR_WEIGHTS)


def refresh_weights():
    """Pull latest weights from learner into the active FACTOR_WEIGHTS dict."""
    global FACTOR_WEIGHTS
    if _weight_learner:
        learned = _weight_learner.get_current_weights()
        FACTOR_WEIGHTS.update(learned)

SESSION_PHASES = {
    "pre_market":     (dt_time(4, 0),  dt_time(9, 29)),
    "opening_drive":  (dt_time(9, 30), dt_time(9, 59)),
    "morning_trend":  (dt_time(10, 0), dt_time(11, 29)),
    "midday_chop":    (dt_time(11, 30), dt_time(13, 29)),
    "afternoon_trend":(dt_time(13, 30), dt_time(14, 59)),
    "power_hour":     (dt_time(15, 0), dt_time(15, 44)),
    "close_risk":     (dt_time(15, 45), dt_time(16, 0)),
}

ZERO_DTE_HARD_STOP = dt_time(15, 0)


@dataclass
class OrderFlowState:
    """Aggregated order flow metrics."""
    # Cumulative delta
    cvd: float = 0.0
    cvd_trend: str = "neutral"  # rising, falling, neutral
    cvd_acceleration: float = 0.0  # rate of change

    # Price-delta relationship
    price_trend: str = "neutral"
    divergence: str = "none"  # bullish, bearish, none

    # Volume profile
    total_volume: int = 0
    buy_volume: int = 0
    sell_volume: int = 0
    imbalance: float = 0.5  # 0=all sell, 1=all buy

    # Aggressive vs passive
    aggressive_buy_pct: float = 0.0
    aggressive_sell_pct: float = 0.0

    # Large trade detection
    large_trade_count: int = 0
    large_trade_bias: str = "neutral"  # buy, sell, neutral
    large_trade_volume: int = 0

    # Absorption
    absorption_detected: bool = False
    absorption_levels: List[float] = field(default_factory=list)
    absorption_bias: str = "neutral"

    # Exhaustion
    volume_exhausted: bool = False
    exhaustion_strength: float = 0.0

    # Bid/ask stacking
    bid_depth_ratio: float = 1.0  # >1 = more bids stacked (bullish)

    def to_dict(self) -> Dict:
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, float):
                d[k] = round(v, 4)
            elif isinstance(v, list):
                d[k] = [round(x, 2) if isinstance(x, float) else x for x in v]
            else:
                d[k] = v
        return d


@dataclass
class SessionContext:
    """Time and market context."""
    phase: str = "unknown"
    minutes_to_close: int = 0
    is_0dte: bool = False
    past_hard_stop: bool = False
    phase_bias: str = "neutral"  # trending, choppy, volatile
    session_quality: float = 0.5  # 0-1 (how good this phase is for trading)

    def to_dict(self) -> Dict:
        return self.__dict__.copy()


@dataclass
class ConfluenceFactor:
    """A single confirming factor for the signal."""
    name: str
    direction: str  # bullish, bearish, neutral
    weight: float   # 0.0 - 1.0 importance
    detail: str     # human-readable explanation


# ============================================================================
# ORDER FLOW ANALYSIS
# ============================================================================

def analyze_order_flow(
    trades: List[Dict],
    levels: MarketLevels,
) -> OrderFlowState:
    """
    Professional order flow analysis from tick data.

    Detects:
    - CVD trend and divergence from price
    - Aggressive vs passive order classification
    - Absorption at key levels
    - Volume exhaustion at extremes
    - Large block trade detection and bias
    - Bid/ask imbalance
    """
    state = OrderFlowState()

    if not trades or len(trades) < 10:
        return state

    # ── Basic volume split ──
    for t in trades:
        size = t.get("s", t.get("size", 0))
        side = t.get("side", "neutral")
        if side == "buy":
            state.buy_volume += size
        elif side == "sell":
            state.sell_volume += size
        state.total_volume += size

    if state.total_volume > 0:
        state.imbalance = state.buy_volume / state.total_volume

    # ── Cumulative Volume Delta (CVD) ──
    cvd_values = []
    running_cvd = 0
    for t in trades:
        size = t.get("s", t.get("size", 0))
        side = t.get("side", "neutral")
        if side == "buy":
            running_cvd += size
        elif side == "sell":
            running_cvd -= size
        cvd_values.append(running_cvd)

    state.cvd = running_cvd

    # CVD trend: compare first third vs last third
    n = len(cvd_values)
    if n >= 6:
        first_third_avg = statistics.mean(cvd_values[:n // 3])
        last_third_avg = statistics.mean(cvd_values[2 * n // 3:])
        mid_avg = statistics.mean(cvd_values[n // 3:2 * n // 3])

        if last_third_avg > first_third_avg * 1.1:
            state.cvd_trend = "rising"
        elif last_third_avg < first_third_avg * 0.9:
            state.cvd_trend = "falling"
        else:
            state.cvd_trend = "neutral"

        # Acceleration: is CVD accelerating or decelerating?
        first_slope = mid_avg - first_third_avg
        second_slope = last_third_avg - mid_avg
        state.cvd_acceleration = second_slope - first_slope

    # ── Price trend ──
    prices = [t.get("p", t.get("price", 0)) for t in trades if t.get("p", t.get("price", 0)) > 0]
    if len(prices) >= 10:
        first_price = statistics.mean(prices[:len(prices) // 5])
        last_price = statistics.mean(prices[-len(prices) // 5:])
        price_diff = last_price - first_price
        threshold = levels.atr_1m * 0.3 if levels.atr_1m > 0 else 0.02
        if price_diff > threshold:
            state.price_trend = "rising"
        elif price_diff < -threshold:
            state.price_trend = "falling"

    # ── Delta-Price Divergence ──
    if state.price_trend == "falling" and state.cvd_trend == "rising":
        state.divergence = "bullish"
    elif state.price_trend == "rising" and state.cvd_trend == "falling":
        state.divergence = "bearish"

    # ── Aggressive order detection ──
    # Trades at or above ask = aggressive buy; at or below bid = aggressive sell
    agg_buy = 0
    agg_sell = 0
    if levels.bid > 0 and levels.ask > 0:
        for t in trades:
            p = t.get("p", t.get("price", 0))
            size = t.get("s", t.get("size", 0))
            if p >= levels.ask:
                agg_buy += size
            elif p <= levels.bid:
                agg_sell += size
    else:
        # Fallback: use side classification
        agg_buy = state.buy_volume
        agg_sell = state.sell_volume

    total_agg = agg_buy + agg_sell
    if total_agg > 0:
        state.aggressive_buy_pct = agg_buy / total_agg
        state.aggressive_sell_pct = agg_sell / total_agg

    # ── Large trade detection ──
    # SPY: trades >= 5000 shares are institutional-size
    large_threshold = 5000
    large_buy_vol = 0
    large_sell_vol = 0
    for t in trades:
        size = t.get("s", t.get("size", 0))
        if size >= large_threshold:
            state.large_trade_count += 1
            state.large_trade_volume += size
            side = t.get("side", "neutral")
            if side == "buy":
                large_buy_vol += size
            elif side == "sell":
                large_sell_vol += size

    if state.large_trade_count > 0:
        if large_buy_vol > large_sell_vol * 1.5:
            state.large_trade_bias = "buy"
        elif large_sell_vol > large_buy_vol * 1.5:
            state.large_trade_bias = "sell"

    # ── Absorption detection ──
    # High volume at a price level with price not breaking through = absorption
    if prices and state.total_volume > 0:
        price_vol_map: Dict[float, Dict] = {}
        for t in trades:
            p = round(t.get("p", t.get("price", 0)), 2)
            s = t.get("s", t.get("size", 0))
            side = t.get("side", "neutral")
            if p not in price_vol_map:
                price_vol_map[p] = {"total": 0, "buy": 0, "sell": 0}
            price_vol_map[p]["total"] += s
            if side in ("buy", "sell"):
                price_vol_map[p][side] += s

        if price_vol_map:
            avg_level_vol = statistics.mean(v["total"] for v in price_vol_map.values())

            # Absorption = high volume level near HOD/LOD/key level where
            # opposite-side volume dominates (e.g., lots of selling at support that holds)
            for price_level, vol_data in price_vol_map.items():
                if vol_data["total"] < avg_level_vol * 2.0:
                    continue  # Need significantly above-average volume

                # Check if near a key level
                near_levels = levels.nearby_levels(price_level, threshold=0.20)
                if not near_levels:
                    continue

                state.absorption_detected = True
                state.absorption_levels.append(price_level)

                # Determine absorption bias.
                # When one side dominates 1.3x at a key level it's absorption,
                # regardless of HOD/LOD proximity.  The HOD/LOD constraint was
                # preventing mid-range absorption detection during sell-offs.
                if vol_data["sell"] > vol_data["buy"] * 1.3:
                    state.absorption_bias = "bullish"  # Heavy selling absorbed → support holding
                elif vol_data["buy"] > vol_data["sell"] * 1.3:
                    state.absorption_bias = "bearish"  # Heavy buying absorbed → resistance holding

    # ── Volume exhaustion ──
    # Declining volume on new highs/lows = exhaustion
    if len(trades) >= 30:
        half = len(trades) // 2
        first_half_vol = sum(t.get("s", t.get("size", 0)) for t in trades[:half])
        second_half_vol = sum(t.get("s", t.get("size", 0)) for t in trades[half:])

        if first_half_vol > 0:
            ratio = second_half_vol / first_half_vol
            # Check if we're at new highs/lows with declining volume
            if ratio < 0.6:
                recent_prices = prices[-10:] if len(prices) >= 10 else prices
                if max(recent_prices) >= levels.hod - 0.02 or min(recent_prices) <= levels.lod + 0.02:
                    state.volume_exhausted = True
                    state.exhaustion_strength = min(1.0, 1.0 - ratio)

    # ── Bid/Ask depth ratio from quote ──
    _bid_size = levels.bid  # These come from quote data
    _ask_size = levels.ask
    # Use quote's bid_size/ask_size if available
    # For now, use buy/sell volume ratio as proxy
    if state.sell_volume > 0:
        state.bid_depth_ratio = state.buy_volume / state.sell_volume

    return state


# ============================================================================
# SESSION CONTEXT
# ============================================================================

def get_session_context(now_et: Optional[datetime] = None) -> SessionContext:
    """
    Determine current market session phase and trading quality.
    """
    if now_et is None:
        now_et = datetime.now(ET)

    ctx = SessionContext()
    current_time = now_et.time()

    # Determine phase
    for phase_name, (start, end) in SESSION_PHASES.items():
        if start <= current_time <= end:
            ctx.phase = phase_name
            break
    else:
        if current_time > dt_time(16, 0):
            ctx.phase = "after_hours"
        elif current_time < dt_time(4, 0):
            ctx.phase = "overnight"

    # Minutes to close
    close_dt = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    if now_et < close_dt:
        ctx.minutes_to_close = int((close_dt - now_et).total_seconds() / 60)

    # Is it a 0DTE day? (Mon-Fri SPY has daily expirations now)
    ctx.is_0dte = now_et.weekday() < 5

    # Past hard stop for 0DTE
    ctx.past_hard_stop = current_time >= ZERO_DTE_HARD_STOP

    # Phase characteristics
    phase_config = {
        "opening_drive":   ("trending", 0.85),
        "morning_trend":   ("trending", 0.80),
        "midday_chop":     ("choppy", 0.30),
        "afternoon_trend": ("trending", 0.70),
        "power_hour":      ("volatile", 0.60),
        "close_risk":      ("volatile", 0.10),
        "pre_market":      ("neutral", 0.0),
        "after_hours":     ("neutral", 0.0),
    }
    bias, quality = phase_config.get(ctx.phase, ("neutral", 0.5))
    ctx.phase_bias = bias
    ctx.session_quality = quality

    return ctx


# ============================================================================
# CONFLUENCE EVALUATION
# ============================================================================

def evaluate_confluence(
    flow: OrderFlowState,
    levels: MarketLevels,
    session: SessionContext,
    options_data: Optional[Dict] = None,
    gex_data: Optional[Any] = None,
    chain_analytics: Optional[Any] = None,
    vanna_charm_data: Optional[Any] = None,
    regime_state: Optional[Any] = None,
    event_context: Optional[Any] = None,
    sweep_data: Optional[Any] = None,
    vpin_state: Optional[Any] = None,
    sector_data: Optional[Any] = None,
    agent_verdicts: Optional[Dict[str, Any]] = None,
    breadth_data: Optional[MarketBreadth] = None,
    vol_data: Optional[VolAnalysis] = None,
    trades_source: str = "options_flow",
) -> Tuple[str, float, List[ConfluenceFactor]]:
    """
    Evaluate all confluence factors and determine signal direction + confidence.

    v5: 16-factor composite scoring + regime multiplier + event awareness
        + multi-agent AI consensus.
    v8: + ORB Breakout (Factor 21) + Market Breadth (Factor 22).
    v12: trades_source dampening — when using synthetic options_flow data,
         order flow factors are dampened because they measure call/put volume
         ratio, not actual order flow aggression.
    Fully backward compatible — all new params are optional.

    Args:
        flow: OrderFlowState from analyze_order_flow()
        levels: MarketLevels from compute_market_levels()
        session: SessionContext from get_session_context()
        options_data: Legacy options snapshot (pc_ratio, max_pain)
        gex_data: GEXResult from gex_engine.calculate_gex()
        chain_analytics: OptionsAnalytics from options_analytics.analyze_options()
        vanna_charm_data: VannaCharmResult from vanna_charm_engine — v3
        regime_state: RegimeState from regime_detector — v3
        event_context: EventContext from event_calendar — v3
        sweep_data: SweepAnalysis from sweep_detector — v4
        vpin_state: VPINState from flow_toxicity — v4
        sector_data: SectorAnalysis from sector_monitor — v4
        agent_verdicts: Dict of agent verdicts from 5-agent system — v5 NEW
        trades_source: "rust_engine" for real ticks, "options_flow" for synthetic

    Returns:
        (action, confidence, factors) where action is BUY_CALL, BUY_PUT, or NO_TRADE
    """
    factors: List[ConfluenceFactor] = []
    price = levels.current_price

    # ━━━━ PHASE 1: Determine preliminary direction from flow ━━━━
    # (needed so we can score GEX/DEX relative to signal direction)
    prelim_direction = _get_preliminary_direction(flow, levels, session)

    # ━━━━ v2 COMPOSITE SCORING ━━━━
    # Each factor scores 0 to its max weight. Some can go negative (headwinds).
    composite_scores: Dict[str, float] = {}

    # ── Factor 1: Order Flow Imbalance (max 1.5) ──
    # Requires real tick data from Rust flow engine (NBBO-classified).
    # Signal loop guarantees real data or no signal.
    f1_score, f1_detail = _score_flow_imbalance(flow, prelim_direction)
    composite_scores["order_flow_imbalance"] = max(-0.50, min(1.5, f1_score))
    if abs(f1_score) > 0.1:
        direction = prelim_direction if f1_score > 0 else ("bearish" if prelim_direction == "bullish" else "bullish")
        factors.append(ConfluenceFactor("Order Flow Imbalance", direction, f1_score, f1_detail))

    # ── Factor 2: CVD Divergence (max 1.0) ──
    f2_score, f2_detail = _score_cvd_divergence(flow, prelim_direction)
    composite_scores["cvd_divergence"] = max(-0.30, min(1.0, f2_score))
    if abs(f2_score) > 0.1:
        factors.append(ConfluenceFactor(
            "CVD Divergence",
            "bullish" if flow.divergence == "bullish" else ("bearish" if flow.divergence == "bearish" else "neutral"),
            f2_score, f2_detail
        ))

    # ── Factor 3: GEX Alignment (max 1.5) — NEW ──
    if gex_data is not None:
        from .gex_engine import score_gex_alignment
        is_trend = _is_trend_signal(flow, levels, session)
        f3_score, f3_detail = score_gex_alignment(gex_data, prelim_direction, is_trend)
        composite_scores["gex_alignment"] = max(-0.5, min(1.5, f3_score))
        if abs(f3_score) > 0.1:
            factors.append(ConfluenceFactor(
                "GEX Alignment", "neutral", f3_score, f3_detail
            ))

    # ── Factor 4: DEX Levels (max 1.0) — NEW ──
    if gex_data is not None:
        from .gex_engine import score_dex_levels
        f4_score, f4_detail = score_dex_levels(gex_data, prelim_direction)
        composite_scores["dex_levels"] = max(-0.3, min(1.0, f4_score))
        if abs(f4_score) > 0.1:
            factors.append(ConfluenceFactor(
                "DEX Levels", prelim_direction if f4_score > 0 else "neutral", f4_score, f4_detail
            ))

    # ── Factor 5: VWAP Band Rejection (max 1.0) ──
    f5_score, f5_factors = _score_vwap(flow, levels)
    composite_scores["vwap_rejection"] = max(-0.30, min(1.0, f5_score))
    factors.extend(f5_factors)

    # ── Factor 6: Volume Spike (max 0.5) ──
    f6_score, f6_detail = _score_volume_spike(flow, levels)
    composite_scores["volume_spike"] = max(0.0, min(0.5, f6_score))
    if abs(f6_score) > 0.1:
        factors.append(ConfluenceFactor(
            "Volume Spike", prelim_direction if f6_score > 0 else "neutral", f6_score, f6_detail
        ))

    # ── Factor 7: Delta Regime (max 1.0) ──
    f7_score, f7_detail = _score_delta_regime(flow, prelim_direction)
    composite_scores["delta_regime"] = max(-0.50, min(1.0, f7_score))
    if abs(f7_score) > 0.1:
        direction = prelim_direction if f7_score > 0 else ("bearish" if prelim_direction == "bullish" else "bullish")
        factors.append(ConfluenceFactor("Delta Regime", direction, f7_score, f7_detail))

    # ── Factor 8: Put/Call Ratio (max 0.5) ──
    # NOTE: PCR shows -53.0% accuracy delta in historical analysis.
    # The scoring logic likely inverts the signal (high PCR = hedging = bullish,
    # but the factor interprets it as bearish). Dampened alongside flow factors
    # until the scoring logic is audited.
    # ── Factor 8: Put/Call Ratio (max 0.5) ──
    # NOTE: -53.0% accuracy delta in historical analysis. The scoring logic
    # likely inverts the signal (high PCR = hedging = bullish, but scored as
    # bearish). Needs scoring audit — runs at full strength with real data.
    if chain_analytics is not None:
        from .options_analytics import score_pcr
        f8_score, f8_detail = score_pcr(chain_analytics, prelim_direction)
        composite_scores["pcr"] = max(-0.2, min(0.5, f8_score))
        if abs(f8_score) > 0.1:
            factors.append(ConfluenceFactor(
                "Put/Call Ratio", prelim_direction if f8_score > 0 else "neutral", f8_score, f8_detail
            ))
    elif options_data:
        _add_legacy_options_factors(factors, options_data, price)

    # ── Factor 9: Max Pain (max 0.5) ──
    # NOTE: -53.2% accuracy delta. Max pain theory has weak evidence for 0DTE
    # where gamma exposure dominates. Needs scoring audit.
    if chain_analytics is not None:
        from .options_analytics import score_max_pain
        f9_score, f9_detail = score_max_pain(chain_analytics, price, prelim_direction, session.is_0dte)
        composite_scores["max_pain"] = max(-0.3, min(0.5, f9_score))
        if abs(f9_score) > 0.1:
            factors.append(ConfluenceFactor(
                "Max Pain", prelim_direction if f9_score > 0 else ("bearish" if prelim_direction == "bullish" else "bullish"),
                f9_score, f9_detail
            ))

    # ── Factor 10: Time of Day (max 0.5) ──
    f10_score, f10_detail = _score_time_of_day(session)
    composite_scores["time_of_day"] = max(-0.30, min(0.5, f10_score))
    if abs(f10_score) > 0.1:
        factors.append(ConfluenceFactor(
            "Session Quality", "neutral", f10_score, f10_detail
        ))

    # ── Factor 11: Vanna Alignment (max 0.75) — v3 NEW ──
    if vanna_charm_data is not None:
        try:
            from .vanna_charm_engine import score_vanna_alignment
            f11_score, f11_detail = score_vanna_alignment(vanna_charm_data, prelim_direction)
            composite_scores["vanna_alignment"] = max(-0.25, min(0.75, f11_score))
            if abs(f11_score) > 0.1:
                direction = "bullish" if f11_score > 0 else ("bearish" if f11_score < 0 else "neutral")
                factors.append(ConfluenceFactor(
                    "Vanna Flow", direction, f11_score, f11_detail
                ))
        except Exception as e:
            logger.debug(f"Vanna scoring error: {e}")

    # ── Factor 12: Charm Pressure (max 0.75) — v3 NEW ──
    if vanna_charm_data is not None:
        try:
            from .vanna_charm_engine import score_charm_pressure
            f12_score, f12_detail = score_charm_pressure(vanna_charm_data, prelim_direction)
            composite_scores["charm_pressure"] = max(-0.25, min(0.75, f12_score))
            if abs(f12_score) > 0.1:
                direction = "bullish" if f12_score > 0 else ("bearish" if f12_score < 0 else "neutral")
                factors.append(ConfluenceFactor(
                    "Charm Pressure", direction, f12_score, f12_detail
                ))
        except Exception as e:
            logger.debug(f"Charm scoring error: {e}")

    # ── Factor 13: Sweep Activity (max 0.75) — v4 NEW ──
    if sweep_data is not None:
        try:
            from .sweep_detector import score_sweep_activity
            f13_score, f13_detail = score_sweep_activity(sweep_data, prelim_direction)
            composite_scores["sweep_activity"] = max(-0.25, min(0.75, f13_score))
            if abs(f13_score) > 0.05:
                direction = "bullish" if f13_score > 0 else ("bearish" if f13_score < 0 else "neutral")
                factors.append(ConfluenceFactor(
                    "Sweep Flow", direction, f13_score, f13_detail
                ))
        except Exception as e:
            logger.debug(f"Sweep scoring error: {e}")

    # ── Factor 14: Flow Toxicity / VPIN (max 0.5) — v4 NEW ──
    if vpin_state is not None:
        try:
            from .flow_toxicity import score_flow_toxicity
            f14_score, f14_detail = score_flow_toxicity(vpin_state, prelim_direction)
            composite_scores["flow_toxicity"] = max(-0.25, min(0.5, f14_score))
            if abs(f14_score) > 0.05:
                direction = "bullish" if f14_score > 0 else ("bearish" if f14_score < 0 else "neutral")
                factors.append(ConfluenceFactor(
                    "Flow Toxicity", direction, f14_score, f14_detail
                ))
        except Exception as e:
            logger.debug(f"VPIN scoring error: {e}")

    # ── Factor 15: Sector Divergence + Bonds (max 0.5) — v4 NEW ──
    if sector_data is not None:
        try:
            from .sector_monitor import score_sector_divergence
            f15_score, f15_detail = score_sector_divergence(sector_data, prelim_direction)
            composite_scores["sector_divergence"] = max(-0.25, min(0.5, f15_score))
            if abs(f15_score) > 0.05:
                direction = "bullish" if f15_score > 0 else ("bearish" if f15_score < 0 else "neutral")
                factors.append(ConfluenceFactor(
                    "Sector/Bond", direction, f15_score, f15_detail
                ))
        except Exception as e:
            logger.debug(f"Sector scoring error: {e}")

    # ── Factor 16: Agent Consensus (max 1.5) — v5 NEW ──
    if agent_verdicts:
        try:
            f16_score, f16_detail = _score_agent_consensus(agent_verdicts, prelim_direction)
            composite_scores["agent_consensus"] = max(-0.5, min(1.5, f16_score))
            if abs(f16_score) > 0.05:
                direction = "bullish" if f16_score > 0 else ("bearish" if f16_score < 0 else "neutral")
                factors.append(ConfluenceFactor(
                    "AI Agents", direction, f16_score, f16_detail
                ))
        except Exception as e:
            logger.debug(f"Agent consensus scoring error: {e}")

    # ── Factor 17: EMA/SMA Trend as Mean-Reversion Signal (max 0.75) — v13 ──
    # INVERTED for 0DTE: stacked uptrend on 1-min bars = move exhaustion, not
    # continuation. Historical data: factor was right 64.2% when OPPOSING signals.
    # Now scored as mean-reversion: stacked trend = expect reversal.
    f17_score, f17_detail = _score_ema_sma_trend(levels, prelim_direction)
    f17_score = -f17_score  # INVERT: trend alignment now opposes signal direction
    composite_scores["ema_sma_trend"] = max(-0.30, min(0.75, f17_score))
    if abs(f17_score) > 0.05:
        direction = prelim_direction if f17_score > 0 else ("bearish" if prelim_direction == "bullish" else "bullish")
        factors.append(ConfluenceFactor("EMA/SMA Trend", direction, f17_score, f17_detail + " (inverted: mean-reversion)"))

    # ── Factor 18: Bollinger Band Squeeze — NON-DIRECTIONAL (max 0.75) — v13 ──
    # BB Squeeze detects volatility expansion but CANNOT predict direction.
    # Historical: 27.4% when confirming direction, 89.7% when opposing.
    # Now scored as volatility signal only: squeeze present = higher expected
    # move magnitude (useful for position sizing), but zero directional weight.
    # "Riding upper band" is exhaustion on 0DTE, not continuation.
    f18_score, f18_detail = _score_bb_squeeze(levels, prelim_direction)
    # Only keep the squeeze detection component (non-directional), zero out
    # any directional scoring (band position, which was anti-predictive)
    bb_upper = getattr(levels, 'bb_upper', 0)
    bb_lower = getattr(levels, 'bb_lower', 0)
    bb_mid = getattr(levels, 'bb_mid', 0)
    if bb_upper > 0 and bb_lower > 0 and bb_mid > 0:
        bb_width_pct = ((bb_upper - bb_lower) / bb_mid) * 100
        avg_width = getattr(levels, 'avg_bb_width_pct', bb_width_pct)
        is_squeeze = bb_width_pct < avg_width * 0.6 if avg_width > 0 else bb_width_pct < 0.3
        if is_squeeze:
            # Squeeze = expect larger move. Score as small positive (non-directional)
            f18_score = 0.15
            f18_detail = f"BB squeeze ({bb_width_pct:.2f}% width) — expect larger move (non-directional)"
        else:
            f18_score = 0.0
            f18_detail = "No BB squeeze"
    else:
        f18_score = 0.0
        f18_detail = "BB data unavailable"
    composite_scores["bb_squeeze"] = max(0.0, min(0.75, f18_score))
    if f18_score > 0:
        factors.append(ConfluenceFactor("BB Squeeze", "neutral", f18_score, f18_detail))

    # ── Factor 19: Support/Resistance levels (max 1.0) — v7 NEW ──
    # Replaces legacy _add_structural_factors for scoring purposes
    f19_score, f19_detail = _score_support_resistance(flow, levels, session, prelim_direction)
    composite_scores["support_resistance"] = max(-0.40, min(1.0, f19_score))
    if abs(f19_score) > 0.05:
        direction = prelim_direction if f19_score > 0 else ("bearish" if prelim_direction == "bullish" else "bullish")
        factors.append(ConfluenceFactor("S/R Levels", direction, f19_score, f19_detail))

    # ── Factor 20: Candle Pattern (max 0.5) — v7 NEW ──
    f20_score, f20_detail = _score_candle_pattern(levels, flow, prelim_direction)
    composite_scores["candle_pattern"] = max(-0.30, min(0.5, f20_score))
    if abs(f20_score) > 0.05:
        direction = prelim_direction if f20_score > 0 else ("bearish" if prelim_direction == "bullish" else "bullish")
        factors.append(ConfluenceFactor("Candle Pattern", direction, f20_score, f20_detail))

    # ── Factor 21: ORB Breakout (max 1.25) — v8 NEW ──
    # Research: 30-min ORB has 89% win rate with 1.44 profit factor.
    # Scores breakout quality during morning, acts as S/R the rest of the day.
    f21_score, f21_detail = _score_orb_breakout(levels, flow, session, prelim_direction)
    composite_scores["orb_breakout"] = max(-0.40, min(1.25, f21_score))
    if abs(f21_score) > 0.05:
        direction = prelim_direction if f21_score > 0 else ("bearish" if prelim_direction == "bullish" else "bullish")
        factors.append(ConfluenceFactor("ORB Breakout", direction, f21_score, f21_detail))

    # ── Factor 22: Market Breadth (max 1.0, min -0.40) — v8 NEW ──
    # Synthetic breadth index from 11 ETFs (sectors + market proxies + risk gauges).
    # Detects broad market alignment/divergence that single-symbol analysis misses.
    if breadth_data is not None and breadth_data.symbols_fetched >= 3:
        f22_score, f22_detail = score_market_breadth(breadth_data, prelim_direction)
        composite_scores["market_breadth"] = max(-0.40, min(1.0, f22_score))
        if abs(f22_score) > 0.05:
            direction = prelim_direction if f22_score > 0 else ("bearish" if prelim_direction == "bullish" else "bullish")
            factors.append(ConfluenceFactor("Market Breadth", direction, f22_score, f22_detail))

    # ── Factor 23: Vol Edge — IV vs Realized Vol (max 0.75, min -0.30) — v10 NEW ──
    # When options are cheap (IV < RV), buying premium has a structural edge.
    # When expensive (IV > RV), premium has a headwind.
    if vol_data is not None and vol_data.data_quality != "insufficient":
        f23_score, f23_detail = score_vol_edge(vol_data, prelim_direction)
        composite_scores["vol_edge"] = max(-0.30, min(0.75, f23_score))
        if abs(f23_score) > 0.05:
            direction = prelim_direction if f23_score > 0 else ("bearish" if prelim_direction == "bullish" else "bullish")
            factors.append(ConfluenceFactor("Vol Edge", direction, f23_score, f23_detail))

    # ── Legacy structural display factors (HOD/LOD, etc.) ──
    # Still added for display in the factor list, but scoring is now handled
    # by Factor 19 (support_resistance) and Factor 21 (ORB) in composite_scores.
    _add_structural_factors(factors, flow, levels, session, price)

    # ── 0DTE Hard Stop (veto) ──
    if session.past_hard_stop and session.is_0dte:
        factors.append(ConfluenceFactor(
            "0DTE Hard Stop", "neutral", -0.50,
            f"Past {ZERO_DTE_HARD_STOP.strftime('%I:%M %p')} ET — NO new 0DTE trades"
        ))

    # ━━━━ ADAPTIVE WEIGHT SCALING — apply learned weights ━━━━
    # Scale composite scores by ratio of (learned_weight / baseline_weight)
    # so the weight learner's adjustments affect confidence without modifying
    # the individual scoring functions.
    active_w = get_active_weights()
    for factor_name, base_score in list(composite_scores.items()):
        baseline = FACTOR_WEIGHTS_BASELINE.get(factor_name, 0)
        learned = active_w.get(factor_name, baseline)
        if baseline > 0 and abs(learned - baseline) > 0.001:
            scale = learned / baseline
            composite_scores[factor_name] = base_score * scale

    # ━━━━ v11: ANTI-CORRELATION DAMPENING ━━━━
    # Correlated factor clusters can all fire together (e.g., 5 flow factors),
    # inflating both the composite score and the confirming count.
    # Soft-cap each cluster's combined contribution.
    _dampening_applied = {}
    for cluster_keys, max_pos, max_neg in CORRELATION_CLUSTERS:
        cluster_pos = sum(composite_scores.get(k, 0) for k in cluster_keys
                         if composite_scores.get(k, 0) > 0)
        cluster_neg = sum(composite_scores.get(k, 0) for k in cluster_keys
                         if composite_scores.get(k, 0) < 0)

        # Dampen positive cluster scores if over cap
        if cluster_pos > max_pos and cluster_pos > 0:
            scale = max_pos / cluster_pos
            for k in cluster_keys:
                s = composite_scores.get(k, 0)
                if s > 0:
                    composite_scores[k] = round(s * scale, 4)
            _dampening_applied[cluster_keys[0]] = f"pos_capped_{cluster_pos:.2f}→{max_pos:.2f}"

        # Dampen negative cluster scores if over (abs) cap
        if cluster_neg < max_neg and cluster_neg < 0:
            scale = max_neg / cluster_neg
            for k in cluster_keys:
                s = composite_scores.get(k, 0)
                if s < 0:
                    composite_scores[k] = round(s * scale, 4)
            _dampening_applied[cluster_keys[0]] = f"neg_capped_{cluster_neg:.2f}→{max_neg:.2f}"

    if _dampening_applied:
        logger.debug(f"[Confluence] Correlation dampening: {_dampening_applied}")

    # ━━━━ ORDER FLOW VETO — flow must confirm direction ━━━━
    # Order flow is the ground truth. If flow doesn't show clear directional
    # aggression, other factors (EMA trend, breadth, PCR) are just noise.
    # Require order flow imbalance > 55% to allow a trade signal.
    flow_imbalance = flow.imbalance  # 0.0 to 1.0, 0.5 = balanced
    flow_confirms_bullish = flow_imbalance >= 0.55
    flow_confirms_bearish = flow_imbalance <= 0.45
    flow_has_direction = flow_confirms_bullish or flow_confirms_bearish

    # ━━━━ AGGREGATE: determine direction and confidence ━━━━
    bullish_weight = sum(f.weight for f in factors if f.direction == "bullish")
    bearish_weight = sum(f.weight for f in factors if f.direction == "bearish")

    bullish_count = sum(1 for f in factors if f.direction == "bullish")
    bearish_count = sum(1 for f in factors if f.direction == "bearish")

    # Determine direction — order flow must agree
    if bullish_weight > bearish_weight and bullish_count >= 1:
        if flow_confirms_bullish:
            action = "BUY_CALL"
        elif not flow_has_direction:
            action = "NO_TRADE"  # Flow is neutral, don't trade
            factors.append(ConfluenceFactor(
                "Order Flow Veto", "neutral", 0.0,
                f"Flow imbalance {flow_imbalance:.1%} too weak to confirm bullish — need >55%"
            ))
        else:
            action = "NO_TRADE"  # Flow opposes
            factors.append(ConfluenceFactor(
                "Order Flow Veto", "bearish", 0.0,
                f"Flow imbalance {flow_imbalance:.1%} opposes bullish signal"
            ))
        confirming = bullish_count
        opposing = bearish_count
    elif bearish_weight > bullish_weight and bearish_count >= 1:
        if flow_confirms_bearish:
            action = "BUY_PUT"
        elif not flow_has_direction:
            action = "NO_TRADE"
            factors.append(ConfluenceFactor(
                "Order Flow Veto", "neutral", 0.0,
                f"Flow imbalance {flow_imbalance:.1%} too weak to confirm bearish — need <45%"
            ))
        else:
            action = "NO_TRADE"
            factors.append(ConfluenceFactor(
                "Order Flow Veto", "bullish", 0.0,
                f"Flow imbalance {flow_imbalance:.1%} opposes bearish signal"
            ))
        confirming = bearish_count
        opposing = bullish_count
    else:
        action = "NO_TRADE"
        confirming = 0
        opposing = 0

    # ── Compute confidence ──
    # v11: Rebalanced for 23-factor system.
    #   - Active threshold raised from 0.01 → 0.03 (reduce noise inflation)
    #   - Confluence bonus floors scaled to 23 factors (~43% = TEXTBOOK)
    #   - Opposing factor penalty increased
    #   - Minimum strength gate on confirming factors
    total_composite = sum(max(0, v) for v in composite_scores.values())
    num_active_factors = len(composite_scores)
    num_total_factors = len(FACTOR_WEIGHTS_BASELINE)

    # v11: Raised threshold from 0.01 → 0.03 so near-zero scores don't
    # inflate the active denominator and artificially boost pure_score.
    active_keys = [k for k in composite_scores if abs(composite_scores[k]) > 0.03]
    active_max = sum(FACTOR_WEIGHTS_BASELINE.get(k, 0) for k in active_keys)
    if active_max <= 0:
        active_max = FULL_DENOMINATOR  # fallback

    if num_active_factors >= 3:
        # v11: Increased opposing penalty from 0.04 → 0.05
        penalty = 0.05 * opposing

        # Coverage discount: floor of 0.55 means 3-5 always-present factors can
        # still generate signals if strongly aligned.
        data_coverage = num_active_factors / num_total_factors  # 0.0 - 1.0
        coverage_discount = max(0.55, data_coverage)

        # Small bonus for near-complete data
        data_bonus = 0.0
        if data_coverage >= 0.80:
            data_bonus = 0.05

        # Pure score against only active factors, then discounted by coverage
        pure_score = total_composite / active_max
        raw_confidence = (pure_score * coverage_discount) + data_bonus - penalty

        # ── v11: Rebalanced confluence bonus floors ──
        # With 23 factors, the old 8-confirming threshold was ~35% of factors,
        # making TEXTBOOK too easy. New thresholds:
        #   TEXTBOOK:  10+ confirming (~43%) AND opposing ≤ 2
        #   HIGH*0.95:  8+ confirming (~35%) AND opposing ≤ 3
        #   HIGH*0.85:  6+ confirming (~26%)
        # Also require the composite score to be meaningful (pure_score > 0.30)
        # so many weak confirming factors don't override a low actual score.
        if data_coverage >= 0.50 and pure_score >= 0.30:
            if confirming >= 10 and opposing <= 2:
                raw_confidence = max(raw_confidence, TIER_TEXTBOOK)
            elif confirming >= 8 and opposing <= 3:
                raw_confidence = max(raw_confidence, TIER_HIGH * 0.95)
            elif confirming >= 6:
                raw_confidence = max(raw_confidence, TIER_HIGH * 0.85)
    else:
        # Too few factors — no meaningful signal
        raw_confidence = 0.0

    confidence = max(0.0, min(1.0, raw_confidence))

    # ── v3: Apply regime multiplier ──
    if regime_state is not None:
        try:
            from .regime_detector import score_regime_alignment
            is_trend = _is_trend_signal(flow, levels, session)
            regime_mult, regime_detail = score_regime_alignment(
                regime_state, action if action != "NO_TRADE" else prelim_direction,
                signal_type="trend" if is_trend else "mean_reversion",
            )
            confidence *= regime_mult
            if abs(regime_mult - 1.0) > 0.05:
                factors.append(ConfluenceFactor(
                    "Regime", "neutral", regime_mult - 1.0, regime_detail
                ))
        except Exception as e:
            logger.debug(f"Regime scoring error: {e}")

    # ── v3: Apply event multiplier ──
    if event_context is not None:
        try:
            from .event_calendar import score_event_context
            event_mult, event_detail = score_event_context(event_context)
            confidence *= event_mult
            if abs(event_mult - 1.0) > 0.05:
                direction = "neutral"
                if event_mult < 0.5:
                    direction = "bearish"  # Events suppress confidence
                factors.append(ConfluenceFactor(
                    "Event Calendar", direction, event_mult - 1.0, event_detail
                ))
            # Hard suppress if pre-event
            if hasattr(event_context, 'suppress_entries') and event_context.suppress_entries:
                action = "NO_TRADE"
                factors.append(ConfluenceFactor(
                    "Event Block", "neutral", -1.0,
                    f"Entries suppressed: {event_detail}"
                ))
        except Exception as e:
            logger.debug(f"Event scoring error: {e}")

    confidence = max(0.0, min(1.0, confidence))

    if confidence < MIN_TRADE_CONFIDENCE:
        action = "NO_TRADE"

    return action, confidence, factors


# ============================================================================
# v2 FACTOR SCORING HELPERS
# ============================================================================

def _get_preliminary_direction(
    flow: OrderFlowState,
    levels: MarketLevels,
    session: SessionContext,
) -> str:
    """Quick directional read from flow data (used to orient GEX/DEX scoring).

    When indicators are tied, use price_trend as tiebreaker instead of
    defaulting to 'neutral'. A neutral prelim_direction starves downstream
    factors of directional tagging and suppresses signal generation.
    """
    bull_signals = 0
    bear_signals = 0

    # Divergence (strongest signal — 2 pts)
    if flow.divergence == "bullish":
        bull_signals += 2
    elif flow.divergence == "bearish":
        bear_signals += 2

    # CVD trend
    if flow.cvd_trend == "rising":
        bull_signals += 1
    elif flow.cvd_trend == "falling":
        bear_signals += 1

    # Imbalance (symmetric thresholds)
    if flow.imbalance > 0.58:
        bull_signals += 1
    elif flow.imbalance < 0.42:
        bear_signals += 1

    # Large trade bias
    if flow.large_trade_bias == "buy":
        bull_signals += 1
    elif flow.large_trade_bias == "sell":
        bear_signals += 1

    if bull_signals > bear_signals:
        return "bullish"
    elif bear_signals > bull_signals:
        return "bearish"

    # ── Tiebreaker: use price trend so we don't drop to neutral ──
    pt = getattr(flow, "price_trend", "")
    if pt == "falling":
        return "bearish"
    elif pt == "rising":
        return "bullish"

    return "neutral"


def _is_trend_signal(
    flow: OrderFlowState,
    levels: MarketLevels,
    session: SessionContext,
) -> bool:
    """Determine if the signal is trend-following (vs mean reversion)."""
    price = levels.current_price
    # Trend signals: ORB breakout, HOD/LOD break, strong directional CVD
    if session.phase in ("opening_drive", "morning_trend"):
        if levels.orb_5_high > 0 and (price > levels.orb_5_high or price < levels.orb_5_low):
            return True

    if levels.hod > 0 and price >= levels.hod:
        return True
    if levels.lod > 0 and price <= levels.lod:
        return True

    # Mean reversion: VWAP band rejection, absorption, exhaustion
    if flow.volume_exhausted or flow.absorption_detected:
        return False

    # Default: trend if strong momentum, reversion if choppy
    return session.phase_bias == "trending"


def _score_flow_imbalance(flow: OrderFlowState, direction: str) -> Tuple[float, str]:
    """Factor 1: Order flow imbalance scoring (max 1.5).

    Thresholds are symmetric around 0.50:
      Bullish confirms at imb > 0.60, penalized below 0.40
      Bearish confirms at imb < 0.40, penalized above 0.60
    """
    imb = flow.imbalance  # 0=all sell, 1=all buy

    if direction == "bullish":
        if imb > 0.60:
            score = min(1.5, 0.5 + (imb - 0.50) * 5.0)
            return score, f"Strong buy imbalance {imb:.0%} — aggressive buying confirms bullish"
        elif imb < 0.40:
            return -1.0, f"Sell imbalance {imb:.0%} — flow contradicts bullish signal"
        return 0.0, f"Balanced flow {imb:.0%}"

    elif direction == "bearish":
        if imb < 0.40:
            score = min(1.5, 0.5 + (0.50 - imb) * 5.0)
            return score, f"Strong sell imbalance {imb:.0%} — aggressive selling confirms bearish"
        elif imb > 0.60:
            return -1.0, f"Buy imbalance {imb:.0%} — flow contradicts bearish signal"
        return 0.0, f"Balanced flow {imb:.0%}"

    return 0.0, f"Flow imbalance {imb:.0%} (no direction)"


def _score_cvd_divergence(flow: OrderFlowState, direction: str) -> Tuple[float, str]:
    """Factor 2: CVD divergence scoring (max 1.0)."""
    if flow.divergence == "bullish" and direction == "bullish":
        return 1.0, f"Bullish divergence — price {flow.price_trend} but CVD {flow.cvd_trend} (hidden buying)"
    elif flow.divergence == "bearish" and direction == "bearish":
        return 1.0, f"Bearish divergence — price {flow.price_trend} but CVD {flow.cvd_trend} (hidden selling)"
    elif flow.divergence == "bullish" and direction == "bearish":
        return -0.5, "Bullish divergence contradicts bearish signal"
    elif flow.divergence == "bearish" and direction == "bullish":
        return -0.5, "Bearish divergence contradicts bullish signal"

    # No divergence — check if CVD confirms direction
    if direction == "bullish" and flow.cvd_trend == "rising":
        return 0.3, f"CVD confirming — {flow.cvd_trend} with bullish bias"
    elif direction == "bearish" and flow.cvd_trend == "falling":
        return 0.3, f"CVD confirming — {flow.cvd_trend} with bearish bias"

    return 0.0, f"CVD {flow.cvd_trend}, divergence: {flow.divergence}"


def _score_vwap(flow: OrderFlowState, levels: MarketLevels) -> Tuple[float, List[ConfluenceFactor]]:
    """Factor 5: VWAP band scoring (max 1.0). Returns score + factor entries."""
    score = 0.0
    vwap_factors: List[ConfluenceFactor] = []
    price = levels.current_price

    if levels.vwap <= 0 or price <= 0:
        return 0.0, []

    if levels.atr_1m > 0 and abs(price - levels.vwap) < levels.atr_1m * 0.5:
        vwap_factors.append(ConfluenceFactor(
            "VWAP Test", "neutral", 0.15,
            f"Price testing VWAP at ${levels.vwap:.2f}"
        ))
        score = 0.2
    elif price > levels.vwap_upper_1 and flow.cvd_trend == "rising":
        vwap_factors.append(ConfluenceFactor(
            "Above VWAP+1σ", "bullish", 0.7,
            f"Price ${price:.2f} above VWAP+1σ (${levels.vwap_upper_1:.2f}) with rising CVD"
        ))
        score = 0.7
    elif price < levels.vwap_lower_1 and flow.cvd_trend == "falling":
        vwap_factors.append(ConfluenceFactor(
            "Below VWAP-1σ", "bearish", 0.7,
            f"Price ${price:.2f} below VWAP-1σ (${levels.vwap_lower_1:.2f}) with falling CVD"
        ))
        score = 0.7

    # Mean reversion at ±2σ
    if price >= levels.vwap_upper_2 and flow.volume_exhausted:
        vwap_factors.append(ConfluenceFactor(
            "VWAP+2σ Rejection", "bearish", 1.0,
            f"Rejection at VWAP+2σ (${levels.vwap_upper_2:.2f}) with volume exhaustion"
        ))
        score = 1.0
    elif price <= levels.vwap_lower_2 and flow.volume_exhausted:
        vwap_factors.append(ConfluenceFactor(
            "VWAP-2σ Rejection", "bullish", 1.0,
            f"Rejection at VWAP-2σ (${levels.vwap_lower_2:.2f}) with volume exhaustion"
        ))
        score = 1.0

    return min(1.0, score), vwap_factors


def _score_volume_spike(flow: OrderFlowState, levels: MarketLevels) -> Tuple[float, str]:
    """Factor 6: Volume spike detection (max 0.5)."""
    # We can approximate volume spike from the flow data
    # A more precise calculation would use bar volume vs rolling average
    if flow.total_volume <= 0:
        return 0.0, "No volume data"

    # Check for large trade clustering (proxy for spike)
    if flow.large_trade_count >= 3:
        return 0.5, f"{flow.large_trade_count} large blocks ({flow.large_trade_volume:,} shares) — volume spike"
    elif flow.large_trade_count >= 2:
        return 0.3, f"{flow.large_trade_count} large blocks — elevated institutional activity"

    return 0.0, "Normal volume"


def _score_delta_regime(flow: OrderFlowState, direction: str) -> Tuple[float, str]:
    """Factor 7: Delta regime / CVD acceleration (max 1.0)."""
    accel = flow.cvd_acceleration

    if direction == "bullish":
        if accel > 0 and flow.cvd_trend == "rising":
            score = min(1.0, 0.5 + abs(accel) * 0.001)
            return score, f"CVD accelerating upward ({accel:+.0f}) — bullish momentum building"
        elif flow.cvd_trend == "rising" and accel <= 0:
            return 0.3, "CVD rising but decelerating — momentum fading"
        elif accel < 0 and flow.cvd_trend == "falling":
            return -1.0, "CVD accelerating downward — strong headwind for bullish"
        return 0.0, "CVD neutral regime"

    elif direction == "bearish":
        if accel < 0 and flow.cvd_trend == "falling":
            score = min(1.0, 0.5 + abs(accel) * 0.001)
            return score, f"CVD accelerating downward ({accel:+.0f}) — bearish momentum building"
        elif flow.cvd_trend == "falling" and accel >= 0:
            return 0.3, "CVD falling but decelerating — momentum fading"
        elif accel > 0 and flow.cvd_trend == "rising":
            return -1.0, "CVD accelerating upward — strong headwind for bearish"
        return 0.0, "CVD neutral regime"

    return 0.0, "No delta regime signal"


def _score_time_of_day(session: SessionContext) -> Tuple[float, str]:
    """Factor 10: Time of day quality scoring (max 0.5)."""
    phase_scores = {
        "opening_drive": (0.5, "Opening Drive — high momentum, clear direction"),
        "morning_trend": (0.5, "Morning Trend — best sustained moves of the day"),
        "midday_chop": (-0.3, "Midday Chop — low conviction, whipsaw risk"),
        "afternoon_trend": (0.4, "Afternoon Trend — second wind possible"),
        "power_hour": (0.3, "Power Hour — volatile but extreme theta decay"),
        "close_risk": (-0.5, "Close Risk — too late for 0DTE entries"),
        "pre_market": (-0.3, "Pre-Market — no options trading"),
        "after_hours": (-0.3, "After Hours — no options trading"),
    }
    score, detail = phase_scores.get(session.phase, (0.0, f"Unknown phase: {session.phase}"))
    return score, detail


def _score_agent_consensus(
    agent_verdicts: Dict[str, Any],
    prelim_direction: str,
) -> Tuple[float, str]:
    """
    Factor 16: Multi-agent AI consensus scoring (max 1.5).

    Reads verdicts from the 5-agent system (PriceFlow, Structure, News,
    Sentiment) and computes a weighted consensus score. Agents that agree
    with the confluence engine's preliminary direction add to the score;
    disagreeing agents subtract.

    Agent weights mirror the SignalPublisher's own weighting:
      PriceFlow: 35%, Structure: 25%, News: 25%, Sentiment: 15%
    """
    AGENT_WEIGHTS = {
        "PriceFlow": 0.35,
        "Structure": 0.25,
        "News": 0.25,
        "Sentiment": 0.15,
    }

    bullish_score = 0.0
    bearish_score = 0.0
    agent_details = []
    active_agents = 0

    for agent_name, weight in AGENT_WEIGHTS.items():
        verdict = agent_verdicts.get(agent_name)
        if not verdict:
            continue

        # Skip stale verdicts
        if verdict.get("stale", False):
            continue

        direction = verdict.get("direction", "none")
        conf = verdict.get("confidence", 0.0)

        if direction in ("none", "neutral") or conf < 0.1:
            continue

        active_agents += 1
        weighted_conf = weight * conf

        if direction == "bullish" or direction == "BULLISH":
            bullish_score += weighted_conf
            agent_details.append(f"{agent_name}↑{conf:.0%}")
        elif direction == "bearish" or direction == "BEARISH":
            bearish_score += weighted_conf
            agent_details.append(f"{agent_name}↓{conf:.0%}")

    if active_agents == 0:
        return 0.0, "No active agent verdicts"

    # Determine consensus direction and score
    max_weight = FACTOR_WEIGHTS["agent_consensus"]  # 1.5

    if bullish_score > bearish_score:
        consensus_dir = "bullish"
        net_score = bullish_score - bearish_score * 0.5  # Opposing agents dampen
    elif bearish_score > bullish_score:
        consensus_dir = "bearish"
        net_score = bearish_score - bullish_score * 0.5
    else:
        return 0.0, f"Mixed agent signals ({', '.join(agent_details)})"

    # Scale to factor weight range
    # Max possible weighted score ≈ 0.35+0.25+0.25+0.15 = 1.0 (all agree at 100%)
    raw_score = min(net_score, 1.0) * max_weight

    # If agents disagree with confluence direction, flip sign
    if consensus_dir != prelim_direction and prelim_direction in ("bullish", "bearish"):
        raw_score = -raw_score * 0.5  # Lighter penalty — agents may see ahead

    detail = f"{active_agents} agents: {', '.join(agent_details)}"
    return round(raw_score, 3), detail


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# v7 NEW: Chart-based indicator factors
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _score_ema_sma_trend(
    levels: "MarketLevels",
    direction: str,
) -> Tuple[float, str]:
    """
    Factor 17: EMA/SMA trend alignment (max 0.75).

    Uses 9/21 EMA and 50 SMA from 1-minute bars.
    Bullish: price > EMA9 > EMA21 > SMA50 (stacked uptrend)
    Bearish: price < EMA9 < EMA21 < SMA50 (stacked downtrend)
    Crossover: EMA9 crossing EMA21 signals momentum shift
    """
    price = levels.current_price
    ema9 = getattr(levels, 'ema_9', 0)
    ema21 = getattr(levels, 'ema_21', 0)
    sma50 = getattr(levels, 'sma_50', 0)

    if not (ema9 > 0 and ema21 > 0):
        return 0.0, "EMA data unavailable"

    score = 0.0
    details = []

    # Check stacked trend alignment
    if direction == "bullish":
        if price > ema9 > ema21:
            score += 0.35
            details.append("price > EMA9 > EMA21 (uptrend)")
            if sma50 > 0 and ema21 > sma50:
                score += 0.15
                details.append("above SMA50")
        elif price < ema9 < ema21:
            score -= 0.30
            details.append("stacked downtrend opposes bullish")
        # EMA9 crossing above EMA21 (golden cross on 1m)
        if ema9 > ema21 and abs(ema9 - ema21) / ema21 < 0.0005:
            score += 0.25
            details.append("EMA9/21 bullish crossover")
    elif direction == "bearish":
        if price < ema9 < ema21:
            score += 0.35
            details.append("price < EMA9 < EMA21 (downtrend)")
            if sma50 > 0 and ema21 < sma50:
                score += 0.15
                details.append("below SMA50")
        elif price > ema9 > ema21:
            score -= 0.30
            details.append("stacked uptrend opposes bearish")
        if ema9 < ema21 and abs(ema9 - ema21) / ema21 < 0.0005:
            score += 0.25
            details.append("EMA9/21 bearish crossover")

    return max(-0.30, min(0.75, round(score, 3))), " | ".join(details) if details else "No clear EMA trend"


def _score_bb_squeeze(
    levels: "MarketLevels",
    direction: str,
) -> Tuple[float, str]:
    """
    Factor 18: Bollinger Band squeeze/expansion detection (max 0.75).

    Squeeze: BB width narrows (< 50% of avg) → imminent breakout
    Expansion: BB width widens after squeeze → confirming move
    Price at band edge: potential reversal or continuation
    """
    bb_upper = getattr(levels, 'bb_upper', 0)
    bb_lower = getattr(levels, 'bb_lower', 0)
    bb_mid = getattr(levels, 'bb_mid', 0)
    price = levels.current_price

    if not (bb_upper > 0 and bb_lower > 0 and bb_mid > 0):
        return 0.0, "Bollinger Band data unavailable"

    bb_width = bb_upper - bb_lower
    bb_width_pct = (bb_width / bb_mid) * 100 if bb_mid > 0 else 0
    avg_bb_width = getattr(levels, 'avg_bb_width_pct', bb_width_pct)

    score = 0.0
    details = []

    # Squeeze detection (width < 60% of average)
    is_squeeze = bb_width_pct < avg_bb_width * 0.6 if avg_bb_width > 0 else bb_width_pct < 0.3
    if is_squeeze:
        score += 0.30
        details.append(f"BB squeeze ({bb_width_pct:.2f}% width)")

    # Price position relative to bands
    if price > 0:
        band_position = (price - bb_lower) / bb_width if bb_width > 0 else 0.5
        if direction == "bullish":
            if band_position > 0.85:
                # Price near upper band — expansion confirmation
                score += 0.25
                details.append("riding upper band")
            elif band_position < 0.15:
                # Price at lower band — potential bounce
                score += 0.20
                details.append("lower band bounce setup")
            elif band_position < 0.35:
                score -= 0.15
                details.append("weak position in bands for bullish")
        elif direction == "bearish":
            if band_position < 0.15:
                score += 0.25
                details.append("riding lower band")
            elif band_position > 0.85:
                score += 0.20
                details.append("upper band rejection setup")
            elif band_position > 0.65:
                score -= 0.15
                details.append("weak position in bands for bearish")

    return max(-0.25, min(0.75, round(score, 3))), " | ".join(details) if details else "No BB signal"


def _score_support_resistance(
    flow: "OrderFlowState",
    levels: "MarketLevels",
    session: "SessionContext",
    direction: str,
) -> Tuple[float, str]:
    """
    Factor 19: Support/Resistance, HOD/LOD, pivots, absorption (max 1.0).

    Consolidates all structural level factors into a single scored factor.
    Previously these were in _add_structural_factors() but didn't score
    into composite_scores — now they count toward confidence.
    """
    price = levels.current_price
    score = 0.0
    details = []

    # ── HOD/LOD interaction ──
    if levels.hod > 0 and levels.lod > 0:
        range_size = levels.hod - levels.lod
        if range_size > 0:
            atr_threshold = levels.atr_1m * 0.3 if levels.atr_1m > 0 else 0.10
            if direction == "bullish":
                if price >= levels.hod - atr_threshold:
                    if flow.cvd_trend == "rising" and flow.aggressive_buy_pct > 0.6:
                        score += 0.30
                        details.append(f"HOD breakout ${levels.hod:.2f} w/ aggressive buying")
                    else:
                        score -= 0.15
                        details.append(f"at HOD ${levels.hod:.2f} without conviction")
                elif price <= levels.lod + atr_threshold:
                    if flow.absorption_bias == "bullish" or flow.volume_exhausted:
                        score += 0.25
                        details.append(f"LOD bounce ${levels.lod:.2f}")
                    else:
                        score -= 0.20
                        details.append(f"at LOD ${levels.lod:.2f} — breakdown risk")
            elif direction == "bearish":
                if price <= levels.lod + atr_threshold:
                    if flow.cvd_trend == "falling" and flow.aggressive_sell_pct > 0.6:
                        score += 0.30
                        details.append(f"LOD breakdown ${levels.lod:.2f} w/ aggressive selling")
                    else:
                        score -= 0.15
                        details.append(f"at LOD ${levels.lod:.2f} without conviction")
                elif price >= levels.hod - atr_threshold:
                    if flow.absorption_bias == "bearish" or flow.volume_exhausted:
                        score += 0.25
                        details.append(f"HOD rejection ${levels.hod:.2f}")
                    else:
                        score -= 0.20
                        details.append(f"at HOD ${levels.hod:.2f} — breakout risk")

    # ── Absorption at key levels ──
    if flow.absorption_detected:
        if (flow.absorption_bias == "bullish" and direction == "bullish") or \
           (flow.absorption_bias == "bearish" and direction == "bearish"):
            score += 0.25
            details.append(f"absorption confirms {direction}")
        elif flow.absorption_bias and flow.absorption_bias != direction:
            score -= 0.20
            details.append(f"absorption opposes {direction}")

    # ── Pivot levels ──
    if levels.pivot > 0:
        nearest = levels.nearby_levels(price, threshold=0.20)
        pivot_names = [n for n, _ in nearest if n in ("Pivot", "R1", "R2", "S1", "S2")]
        if pivot_names:
            lvl = pivot_names[0]
            if direction == "bullish" and lvl.startswith("S") and flow.cvd_trend != "falling":
                score += 0.15
                details.append(f"{lvl} support holding")
            elif direction == "bearish" and lvl.startswith("R") and flow.cvd_trend != "rising":
                score += 0.15
                details.append(f"{lvl} resistance holding")
            elif direction == "bullish" and lvl.startswith("R"):
                score -= 0.10
                details.append(f"approaching {lvl} resistance")
            elif direction == "bearish" and lvl.startswith("S"):
                score -= 0.10
                details.append(f"approaching {lvl} support")

    # ── ORB (Opening Range Breakout) ──
    if levels.orb_5_high > 0 and levels.orb_5_low > 0 and session.phase in ("opening_drive", "morning_trend"):
        if direction == "bullish" and price > levels.orb_5_high and flow.cvd_trend == "rising":
            score += 0.20
            details.append(f"ORB breakout up ${levels.orb_5_high:.2f}")
        elif direction == "bearish" and price < levels.orb_5_low and flow.cvd_trend == "falling":
            score += 0.20
            details.append(f"ORB breakdown ${levels.orb_5_low:.2f}")

    return max(-0.40, min(1.0, round(score, 3))), " | ".join(details) if details else "No S/R signal"


def _score_orb_breakout(
    levels: "MarketLevels",
    flow: "OrderFlowState",
    session: "SessionContext",
    direction: str,
) -> Tuple[float, str]:
    """
    Factor 21: Opening Range Breakout (max 1.25).

    Research: 30-min ORB has 89% win rate with 1.44 profit factor.

    Scoring modes:
    A) BREAKOUT MODE (opening_drive, morning_trend): Score the breakout itself
       - Price above/below 30m ORB range
       - Volume confirmation (CVD aligning)
       - VWAP alignment with breakout direction
       - Narrow range bonus (compressed → explosive)

    B) S/R MODE (all other sessions): ORB levels as support/resistance
       - Price testing ORB high/low from inside = potential bounce/rejection
       - Price holding above/below after breakout = trend continuation
    """
    price = levels.current_price
    if price <= 0:
        return 0.0, "No price data"

    # Prefer 30m ORB, fall back to 15m, then 5m
    orb_high = levels.orb_30_high or levels.orb_15_high or levels.orb_5_high
    orb_low = levels.orb_30_low or levels.orb_15_low or levels.orb_5_low
    orb_width = levels.orb_30_width or (orb_high - orb_low if orb_high > orb_low else 0)

    if orb_high <= 0 or orb_low <= 0 or orb_high <= orb_low:
        return 0.0, "ORB not established"

    orb_source = "30m" if levels.orb_30_high > 0 else ("15m" if levels.orb_15_high > 0 else "5m")
    score = 0.0
    details = []

    # ATR for relative measurements
    atr = levels.atr_5m if levels.atr_5m > 0 else (levels.atr_1m if levels.atr_1m > 0 else 1.0)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # A) BREAKOUT MODE — during opening_drive and morning_trend
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if session.phase in ("opening_drive", "morning_trend"):

        above_orb = price > orb_high
        below_orb = price < orb_low
        inside_orb = not above_orb and not below_orb

        if inside_orb:
            # Price still in range — no breakout yet
            # Score range compression as setup indicator
            if orb_width > 0 and orb_width < atr * 0.6:
                score += 0.10
                details.append(f"Narrow {orb_source} ORB (${orb_width:.2f} < 0.6×ATR) — breakout loading")
            return score, " | ".join(details) if details else f"Inside {orb_source} ORB range"

        # ── Breakout detected ──
        if above_orb and direction == "bullish":
            # Bullish breakout aligned with prelim direction
            breakout_dist = price - orb_high
            breakout_dist / orb_width if orb_width > 0 else 0

            # Base score: confirmed breakout
            score += 0.50
            details.append(f"Above {orb_source} ORB high ${orb_high:.2f} (+${breakout_dist:.2f})")

            # Volume/flow confirmation
            if flow.cvd_trend == "rising":
                score += 0.25
                details.append("CVD rising confirms breakout")
            if flow.imbalance > 0.58:
                score += 0.15
                details.append(f"Flow imbalance {flow.imbalance:.0%} buy — supports breakout")

            # VWAP alignment
            if levels.vwap > 0 and price > levels.vwap:
                score += 0.15
                details.append("Above VWAP — trend aligned")

            # Narrow range bonus (compressed energy = explosive breakout)
            if orb_width > 0 and orb_width < atr * 0.8:
                score += 0.20
                details.append(f"Narrow range ${orb_width:.2f} — compressed breakout")

        elif below_orb and direction == "bearish":
            # Bearish breakout aligned with prelim direction
            breakout_dist = orb_low - price

            score += 0.50
            details.append(f"Below {orb_source} ORB low ${orb_low:.2f} (-${breakout_dist:.2f})")

            if flow.cvd_trend == "falling":
                score += 0.25
                details.append("CVD falling confirms breakdown")
            if flow.imbalance < 0.42:
                score += 0.15
                details.append(f"Flow imbalance {flow.imbalance:.0%} sell — supports breakdown")

            if levels.vwap > 0 and price < levels.vwap:
                score += 0.15
                details.append("Below VWAP — trend aligned")

            if orb_width > 0 and orb_width < atr * 0.8:
                score += 0.20
                details.append(f"Narrow range ${orb_width:.2f} — compressed breakdown")

        elif above_orb and direction == "bearish":
            # Breakout opposes our direction — headwind
            score -= 0.30
            details.append("Above ORB high but bearish direction — opposing breakout")
        elif below_orb and direction == "bullish":
            score -= 0.30
            details.append("Below ORB low but bullish direction — opposing breakdown")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # B) S/R MODE — ORB levels act as support/resistance all day
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    else:
        proximity = atr * 0.4  # How close to count as "testing" the level

        dist_to_high = abs(price - orb_high)
        dist_to_low = abs(price - orb_low)

        # Price holding above ORB after earlier breakout = trend continuation
        if price > orb_high + proximity:
            if direction == "bullish":
                score += 0.30
                details.append(f"Holding above {orb_source} ORB high ${orb_high:.2f} — trend continuation")
            elif direction == "bearish":
                score -= 0.15
                details.append("Price above ORB high opposes bearish")

        # Price holding below ORB after earlier breakdown
        elif price < orb_low - proximity:
            if direction == "bearish":
                score += 0.30
                details.append(f"Holding below {orb_source} ORB low ${orb_low:.2f} — trend continuation")
            elif direction == "bullish":
                score -= 0.15
                details.append("Price below ORB low opposes bullish")

        # Price testing ORB high from below (resistance) or bouncing off it
        elif dist_to_high <= proximity:
            if direction == "bearish" and flow.cvd_trend in ("falling", "neutral"):
                score += 0.25
                details.append(f"Rejection at {orb_source} ORB high ${orb_high:.2f}")
            elif direction == "bullish" and flow.cvd_trend == "rising":
                score += 0.20
                details.append(f"Testing {orb_source} ORB high ${orb_high:.2f} for breakout")

        # Price testing ORB low from above (support) or breaking down
        elif dist_to_low <= proximity:
            if direction == "bullish" and flow.cvd_trend in ("rising", "neutral"):
                score += 0.25
                details.append(f"Bounce at {orb_source} ORB low ${orb_low:.2f}")
            elif direction == "bearish" and flow.cvd_trend == "falling":
                score += 0.20
                details.append(f"Testing {orb_source} ORB low ${orb_low:.2f} for breakdown")

        # Inside the range during later sessions = mean reversion zone
        elif orb_low < price < orb_high:
            score += 0.05
            details.append(f"Inside {orb_source} ORB range — mean reversion territory")

    return round(score, 3), " | ".join(details) if details else "ORB neutral"


def _score_candle_pattern(
    levels: "MarketLevels",
    flow: "OrderFlowState",
    direction: str,
) -> Tuple[float, str]:
    """
    Factor 20: Price action / candle pattern analysis (max 0.5).

    Uses recent 1-minute bars to detect momentum, exhaustion, and reversals.
    """
    bars = getattr(levels, 'recent_bars', [])
    if not bars or len(bars) < 5:
        return 0.0, "Insufficient bar data"

    score = 0.0
    details = []

    # Last 5 bars analysis
    recent = bars[-5:]
    closes = [b.get('c', b.get('close', 0)) for b in recent]
    opens = [b.get('o', b.get('open', 0)) for b in recent]
    highs = [b.get('h', b.get('high', 0)) for b in recent]
    lows = [b.get('l', b.get('low', 0)) for b in recent]

    if not all(c > 0 for c in closes):
        return 0.0, "Invalid bar data"

    # Consecutive direction bars
    bullish_bars = sum(1 for c, o in zip(closes, opens) if c > o)
    bearish_bars = sum(1 for c, o in zip(closes, opens) if c < o)

    if direction == "bullish":
        if bullish_bars >= 4:
            score += 0.30
            details.append(f"{bullish_bars}/5 green bars — strong momentum")
        elif bullish_bars >= 3:
            score += 0.15
            details.append(f"{bullish_bars}/5 green bars")
        elif bearish_bars >= 4:
            score -= 0.25
            details.append(f"{bearish_bars}/5 red bars oppose bullish")
    elif direction == "bearish":
        if bearish_bars >= 4:
            score += 0.30
            details.append(f"{bearish_bars}/5 red bars — strong momentum")
        elif bearish_bars >= 3:
            score += 0.15
            details.append(f"{bearish_bars}/5 red bars")
        elif bullish_bars >= 4:
            score -= 0.25
            details.append(f"{bullish_bars}/5 green bars oppose bearish")

    # Volume exhaustion on last bar (tiny body, big wicks)
    recent[-1]
    body = abs(closes[-1] - opens[-1])
    total_range = highs[-1] - lows[-1] if highs[-1] > lows[-1] else 0.001
    body_ratio = body / total_range
    if body_ratio < 0.2 and total_range > 0:
        score -= 0.10
        details.append("doji/exhaustion candle")

    return max(-0.30, min(0.5, round(score, 3))), " | ".join(details) if details else "No pattern signal"


def _add_structural_factors(
    factors: List[ConfluenceFactor],
    flow: OrderFlowState,
    levels: MarketLevels,
    session: SessionContext,
    price: float,
):
    """Add HOD/LOD, ORB, pivots, absorption, gap factors (from original engine)."""

    # ── HOD/LOD interaction ──
    if levels.hod > 0 and levels.lod > 0:
        range_size = levels.hod - levels.lod
        if range_size > 0:
            if price >= levels.hod - levels.atr_1m * 0.3:
                if flow.cvd_trend == "rising" and flow.aggressive_buy_pct > 0.6:
                    factors.append(ConfluenceFactor(
                        "HOD Breakout", "bullish", 0.20,
                        f"Testing HOD ${levels.hod:.2f} with aggressive buying ({flow.aggressive_buy_pct:.0%})"
                    ))
                elif flow.volume_exhausted or flow.absorption_bias == "bearish":
                    factors.append(ConfluenceFactor(
                        "HOD Rejection", "bearish", 0.20,
                        f"Failing at HOD ${levels.hod:.2f} — {'exhaustion' if flow.volume_exhausted else 'absorption'}"
                    ))
            elif price <= levels.lod + levels.atr_1m * 0.3:
                if flow.cvd_trend == "falling" and flow.aggressive_sell_pct > 0.6:
                    factors.append(ConfluenceFactor(
                        "LOD Breakdown", "bearish", 0.20,
                        f"Testing LOD ${levels.lod:.2f} with aggressive selling ({flow.aggressive_sell_pct:.0%})"
                    ))
                elif flow.volume_exhausted or flow.absorption_bias == "bullish":
                    factors.append(ConfluenceFactor(
                        "LOD Bounce", "bullish", 0.20,
                        f"Holding LOD ${levels.lod:.2f} — {'exhaustion' if flow.volume_exhausted else 'absorption'}"
                    ))

    # ── ORB — now handled by Factor 21 (composite scoring), display factor removed ──

    # ── Previous day levels / gap fill ──
    if levels.prev_close > 0 and levels.orb_5_low > 0:
        gap = levels.orb_5_low - levels.prev_close
        if abs(gap) > (levels.atr_5m if levels.atr_5m > 0 else 0.50):
            gap_dir = "up" if gap > 0 else "down"
            if gap > 0 and price < levels.orb_5_high and flow.cvd_trend == "falling":
                factors.append(ConfluenceFactor(
                    "Gap Fill", "bearish", 0.15,
                    f"Gap {gap_dir} ${abs(gap):.2f} — filling toward prev close ${levels.prev_close:.2f}"
                ))
            elif gap < 0 and price > levels.orb_5_low and flow.cvd_trend == "rising":
                factors.append(ConfluenceFactor(
                    "Gap Fill", "bullish", 0.15,
                    f"Gap {gap_dir} ${abs(gap):.2f} — filling toward prev close ${levels.prev_close:.2f}"
                ))

    # ── Large trade bias ──
    if flow.large_trade_count >= 2:
        if flow.large_trade_bias == "buy":
            factors.append(ConfluenceFactor(
                "Institutional Buying", "bullish", 0.20,
                f"{flow.large_trade_count} large blocks ({flow.large_trade_volume:,} shares) — net buy bias"
            ))
        elif flow.large_trade_bias == "sell":
            factors.append(ConfluenceFactor(
                "Institutional Selling", "bearish", 0.20,
                f"{flow.large_trade_count} large blocks ({flow.large_trade_volume:,} shares) — net sell bias"
            ))

    # ── Absorption at key levels ──
    if flow.absorption_detected:
        if flow.absorption_bias == "bullish":
            factors.append(ConfluenceFactor(
                "Absorption (Bullish)", "bullish", 0.20,
                f"Heavy selling absorbed at {', '.join(f'${lvl:.2f}' for lvl in flow.absorption_levels[:3])} — support holding"
            ))
        elif flow.absorption_bias == "bearish":
            factors.append(ConfluenceFactor(
                "Absorption (Bearish)", "bearish", 0.20,
                f"Heavy buying absorbed at {', '.join(f'${lvl:.2f}' for lvl in flow.absorption_levels[:3])} — resistance holding"
            ))

    # ── Pivot points ──
    if levels.pivot > 0:
        nearest_pivots = levels.nearby_levels(price, threshold=0.20)
        pivot_names = [n for n, _ in nearest_pivots if n in ("Pivot", "R1", "R2", "S1", "S2")]
        if pivot_names:
            pivot_level = pivot_names[0]
            if pivot_level.startswith("S") and flow.cvd_trend != "falling":
                factors.append(ConfluenceFactor(
                    f"{pivot_level} Support", "bullish", 0.10,
                    f"Testing {pivot_level} support — buying interest present"
                ))
            elif pivot_level.startswith("R") and flow.cvd_trend != "rising":
                factors.append(ConfluenceFactor(
                    f"{pivot_level} Resistance", "bearish", 0.10,
                    f"Testing {pivot_level} resistance — selling pressure present"
                ))


def _add_legacy_options_factors(
    factors: List[ConfluenceFactor],
    options_data: Dict,
    price: float,
):
    """Legacy options factor scoring (used when chain_analytics not available)."""
    pcr = options_data.get("pc_ratio", 1.0)
    max_pain = options_data.get("max_pain", 0)

    if pcr < 0.7:
        factors.append(ConfluenceFactor(
            "Bullish Options Flow", "bullish", 0.10,
            f"Put/Call ratio {pcr:.2f} — heavy call buying"
        ))
    elif pcr > 1.3:
        factors.append(ConfluenceFactor(
            "Bearish Options Flow", "bearish", 0.10,
            f"Put/Call ratio {pcr:.2f} — heavy put buying"
        ))

    if max_pain > 0 and price > 0:
        mp_dist = price - max_pain
        if abs(mp_dist) > 1.0:
            mp_dir = "bearish" if mp_dist > 0 else "bullish"
            factors.append(ConfluenceFactor(
                "Max Pain Pull", mp_dir, 0.10,
                f"Max pain at ${max_pain:.0f}, price ${price:.2f} — gravitational pull {'down' if mp_dist > 0 else 'up'}"
            ))


# ============================================================================
# STRIKE SELECTION
# ============================================================================

def select_strike(
    action: str,
    current_price: float,
    chain: Optional[Dict] = None,
    target_delta: float = 0.30,
) -> Dict[str, Any]:
    """
    Select optimal strike using real options chain data.

    For directional 0DTE plays: target delta 0.30-0.40
    For spreads: target delta 0.22-0.26

    Falls back to price-based estimation when chain unavailable.
    """
    result = {
        "strike": 0.0,
        "expiry": _get_nearest_expiry(),
        "entry_price": 0.0,
        "bid": 0.0,
        "ask": 0.0,
        "delta": None,
        "iv": None,
        "gamma": None,
        "theta": None,
        "volume": 0,
        "open_interest": 0,
        "source": "estimated",
    }

    # Determine which side of the chain to look at
    if action == "BUY_CALL":
        side = "calls"
    elif action == "BUY_PUT":
        side = "puts"
    else:
        return result

    # ── Try real chain data first ──
    if chain and chain.get(side):
        options = chain[side]

        # Filter for reasonable liquidity
        liquid = [
            o for o in options
            if (o.get("volume", 0) or 0) >= 10 or (o.get("open_interest", 0) or 0) >= 50
        ]
        if not liquid:
            liquid = options  # Fall back to all options

        # If we have delta data, select by delta
        with_delta = [o for o in liquid if o.get("delta") is not None]
        if with_delta:
            # Find option closest to target delta
            best = min(with_delta, key=lambda o: abs(abs(o["delta"]) - target_delta))
            bid = best.get("bid", 0) or 0
            ask = best.get("ask", 0) or 0
            # Use ask price for entry (what you'd actually pay), not mid
            entry = ask if ask > 0 else best.get("mid", round((bid + ask) / 2, 2)) if bid and ask else best.get("last", 0)

            # v7: Validate entry — must be > 0 and ask must exist
            if entry <= 0:
                logger.warning(f"[StrikeSelect] Chain delta match but entry={entry} — skipping")
            else:
                result.update({
                    "strike": best["strike"],
                    "entry_price": round(entry, 2),
                    "bid": bid,
                    "ask": ask,
                    "delta": best.get("delta"),
                    "iv": best.get("iv"),
                    "gamma": best.get("gamma"),
                    "theta": best.get("theta"),
                    "volume": best.get("volume", 0),
                    "open_interest": best.get("open_interest", 0),
                    "source": "chain_delta",
                })
                return result

        # No delta data — select by proximity to ~$1 OTM
        target_strike = current_price + 1.0 if action == "BUY_CALL" else current_price - 1.0
        best = min(liquid, key=lambda o: abs(o["strike"] - target_strike))
        bid = best.get("bid", 0) or 0
        ask = best.get("ask", 0) or 0
        entry = ask if ask > 0 else best.get("mid", round((bid + ask) / 2, 2)) if bid and ask else best.get("last", 0)

        if entry <= 0:
            logger.warning(f"[StrikeSelect] Chain strike match but entry={entry} — skipping")
        else:
            result.update({
                "strike": best["strike"],
                "entry_price": round(entry, 2),
                "bid": bid,
                "ask": ask,
                "volume": best.get("volume", 0),
                "open_interest": best.get("open_interest", 0),
                "source": "chain_strike",
            })
            return result

    # ── v8: Estimated fallback when chain unavailable ──
    # Use Black-Scholes-based estimation so signals can still generate.
    # Auto-trader will re-validate with live chain before placing orders.
    # This keeps the signal pipeline flowing for learning/logging even when
    # ThetaData is temporarily unreachable.

    # Estimate ATM-ish strike (round to nearest $1 for SPY)
    if action == "BUY_CALL":
        est_strike = math.ceil(current_price)  # slightly OTM call
    else:
        est_strike = math.floor(current_price)  # slightly OTM put

    # Rough 0DTE option price estimate:
    # ATM 0DTE SPY options typically trade ~$0.50-$3.00 depending on time/vol
    # Use a simple heuristic: ~0.4% of underlying for near-ATM 0DTE
    est_entry = round(current_price * 0.004, 2)
    est_entry = max(est_entry, 0.10)  # Floor at $0.10

    result.update({
        "strike": est_strike,
        "entry_price": est_entry,
        "bid": round(est_entry * 0.85, 2),
        "ask": est_entry,
        "source": "estimated_fallback",
    })
    logger.warning(
        f"[StrikeSelect] No chain data — using estimated fallback: "
        f"strike={est_strike} entry=${est_entry:.2f} (MUST re-validate before trading)"
    )
    return result


def _get_nearest_expiry() -> str:
    """Get nearest available expiry (SPY has daily expirations M-F)."""
    now = datetime.now(ET)
    today = now.date()

    # If market is still open today, use today's expiry (0DTE)
    if now.weekday() < 5 and now.time() < dt_time(16, 0):
        return today.strftime("%Y-%m-%d")

    # Otherwise find next trading day
    day = today + timedelta(days=1)
    for _ in range(7):
        if day.weekday() < 5:
            return day.strftime("%Y-%m-%d")
        day += timedelta(days=1)
    return today.strftime("%Y-%m-%d")


# ============================================================================
# RISK MANAGEMENT
# ============================================================================

def calculate_risk(
    confidence: float,
    entry_price: float,
    levels: MarketLevels,
    session: SessionContext,
    account_balance: float = ACCOUNT_BALANCE,
    iv: float = None,
    delta: float = None,
    direction: str = None,
    gex_data: "Any" = None,
    vol_data: Optional[VolAnalysis] = None,
) -> Dict[str, Any]:
    """
    Dynamic risk sizing based on confidence × volatility × session quality.

    v7: Multi-mode exits (scalp/standard/swing) with adaptive IV/Greeks scaling.
    v8: Level-aware targets/stops — caps exits at key market structure levels
        (HOD/LOD, VWAP bands, pivot points, ORB) so targets don't overshoot
        resistance and stops sit behind support.
    v9: GEX regime strategy switching — fundamentally adjusts targets, stops,
        position sizing, and hold time based on dealer gamma positioning.
    v10: IV vs Realized Vol — options cheap/expensive adjustments.
    """
    # Determine confidence tier
    if confidence >= TIER_TEXTBOOK:
        tier = "TEXTBOOK"
    elif confidence >= TIER_HIGH:
        tier = "HIGH"
    elif confidence >= TIER_VALID:
        tier = "VALID"
    else:
        tier = "DEVELOPING"

    base_risk_pct = RISK_TABLE[tier]

    # Adjust for session quality
    session_mult = 0.5 + session.session_quality * 0.5  # 0.5 - 1.0
    adjusted_risk_pct = base_risk_pct * session_mult

    # Adjust for volatility (higher vol = tighter sizing)
    if levels.realized_vol > 25:
        vol_mult = 0.7
    elif levels.realized_vol > 18:
        vol_mult = 0.85
    elif levels.realized_vol > 12:
        vol_mult = 1.0
    else:
        vol_mult = 1.1

    final_risk_pct = round(adjusted_risk_pct * vol_mult, 2)
    risk_amount = (final_risk_pct / 100.0) * account_balance

    # Max contracts
    if entry_price > 0:
        max_contracts = max(1, int(risk_amount / (entry_price * 100)))
    else:
        max_contracts = 1

    # ── v7: Trade mode-based exits with adaptive IV/Greeks scaling ──
    trade_mode = get_trade_mode()
    mode_params = TRADE_MODE_PARAMS[trade_mode]

    target_pct = mode_params["target_pct"]
    stop_pct = mode_params["stop_pct"]
    max_hold = mode_params["max_hold_minutes"]
    trailing_stop_pct = mode_params["trailing_stop_pct"]

    # ── Adaptive IV scaling ──
    # High IV → wider targets (options move more), tighter stops
    # Low IV → tighter targets, can afford wider stops
    if iv is not None and iv > 0:
        iv_annual = iv if iv > 1.0 else iv * 100  # Normalize to percentage
        if iv_annual > 40:  # High IV regime
            target_pct *= 1.3   # Wider target — options are juicier
            stop_pct *= 0.85    # Tighter stop — moves are faster
        elif iv_annual > 25:  # Normal IV
            pass  # Use base mode params
        elif iv_annual > 15:  # Low IV
            target_pct *= 0.75  # Tighter target — smaller moves
            stop_pct *= 1.1     # Wider stop — slower moves
        else:  # Very low IV
            target_pct *= 0.60
            stop_pct *= 1.2

    # ── Adaptive delta scaling ──
    # Higher delta = more responsive to underlying → adjust accordingly
    if delta is not None:
        abs_delta = abs(delta)
        if abs_delta > 0.50:  # Deep ITM — acts more like stock
            target_pct *= 0.80  # Smaller % moves
            stop_pct *= 0.80
        elif abs_delta < 0.20:  # Far OTM — high leverage
            target_pct *= 1.25  # Bigger % swings
            stop_pct *= 0.75    # Tighter stop needed

    # ── Time-based compression ──
    if session.minutes_to_close < 30:
        # Very late — aggressive compression
        target_pct *= 0.40
        stop_pct *= 0.60
        max_hold = min(max_hold, 5)
    elif session.minutes_to_close < 60:
        target_pct *= 0.65
        stop_pct *= 0.75
        max_hold = min(max_hold, 10)
    elif session.minutes_to_close < 120:
        target_pct *= 0.85
        max_hold = min(max_hold, 20)

    # ── Confidence tier adjustments ──
    if confidence >= TIER_TEXTBOOK:
        target_pct *= 1.15  # Let winners run a bit more
    elif confidence < TIER_VALID:
        target_pct *= 0.80  # Tighter on low-confidence
        stop_pct *= 0.85

    # ── v8: Level-aware target/stop adjustment ──
    # The % target/stop is our starting point. Now check if key market
    # levels sit between price and target — if so, cap/adjust the exit
    # so we don't set targets beyond obvious resistance or stops in
    # front of obvious support.
    #
    # For CALLS: target capped at next resistance above, stop behind nearest support below
    # For PUTS:  target capped at next support below, stop behind nearest resistance above

    pct_target = round(entry_price * (1 + target_pct), 2) if entry_price else 0
    pct_stop = round(entry_price * (1 - stop_pct), 2) if entry_price else 0

    target_price = pct_target
    stop_price = pct_stop
    level_note = ""

    price = levels.current_price
    use_delta = abs(delta) if delta else 0.35  # Default delta for $ move estimation

    if price > 0 and entry_price > 0 and direction:
        is_call = "CALL" in (direction or "").upper()

        # Collect all key levels above and below current price
        resistance_levels = []  # Levels ABOVE current price
        support_levels = []     # Levels BELOW current price

        level_map = {
            "HOD": levels.hod, "LOD": levels.lod,
            "VWAP": levels.vwap,
            "VWAP+1σ": levels.vwap_upper_1, "VWAP-1σ": levels.vwap_lower_1,
            "VWAP+2σ": levels.vwap_upper_2, "VWAP-2σ": levels.vwap_lower_2,
            "R1": levels.r1, "R2": levels.r2,
            "S1": levels.s1, "S2": levels.s2,
            "Pivot": levels.pivot,
            "POC": levels.poc,
            "Prev High": levels.prev_high, "Prev Low": levels.prev_low,
            "ORB 5m High": levels.orb_5_high, "ORB 5m Low": levels.orb_5_low,
        }

        for name, lv in level_map.items():
            if lv <= 0:
                continue
            if lv > price + 0.05:  # At least $0.05 above current price
                resistance_levels.append((name, lv))
            elif lv < price - 0.05:
                support_levels.append((name, lv))

        resistance_levels.sort(key=lambda x: x[1])   # Nearest resistance first
        support_levels.sort(key=lambda x: -x[1])      # Nearest support first

        if is_call:
            # CALL: price rising → resistance = target cap, support = stop anchor
            if resistance_levels:
                nearest_res_name, nearest_res = resistance_levels[0]
                # How much would the option premium change if underlying hits this level?
                # Rough estimate: Δ_option ≈ delta × Δ_underlying (for ATM/near-ATM 0DTE)
                underlying_move = nearest_res - price
                premium_at_level = entry_price + (underlying_move * use_delta)

                # Only cap target if the level-implied target is LOWER than the % target
                if 0 < premium_at_level < pct_target:
                    target_price = round(premium_at_level, 2)
                    level_note = f"Target capped at {nearest_res_name} (${nearest_res:.2f})"

            if support_levels:
                nearest_sup_name, nearest_sup = support_levels[0]
                underlying_drop = price - nearest_sup
                premium_at_support = entry_price - (underlying_drop * use_delta)

                # If support-based stop is TIGHTER than % stop, use support stop
                # (we want to protect capital — use the tighter of the two)
                if premium_at_support > pct_stop:
                    stop_price = round(max(premium_at_support, 0.01), 2)
                    if level_note:
                        level_note += f"; Stop behind {nearest_sup_name} (${nearest_sup:.2f})"
                    else:
                        level_note = f"Stop behind {nearest_sup_name} (${nearest_sup:.2f})"

        else:
            # PUT: price falling → support = target cap, resistance = stop anchor
            if support_levels:
                nearest_sup_name, nearest_sup = support_levels[0]
                underlying_move = price - nearest_sup
                premium_at_level = entry_price + (underlying_move * use_delta)

                if 0 < premium_at_level < pct_target:
                    target_price = round(premium_at_level, 2)
                    level_note = f"Target capped at {nearest_sup_name} (${nearest_sup:.2f})"

            if resistance_levels:
                nearest_res_name, nearest_res = resistance_levels[0]
                underlying_rise = nearest_res - price
                premium_at_resistance = entry_price - (underlying_rise * use_delta)

                if premium_at_resistance > pct_stop:
                    stop_price = round(max(premium_at_resistance, 0.01), 2)
                    if level_note:
                        level_note += f"; Stop behind {nearest_res_name} (${nearest_res:.2f})"
                    else:
                        level_note = f"Stop behind {nearest_res_name} (${nearest_res:.2f})"

    # Safety: target must be above entry, stop must be below entry
    if target_price <= entry_price and pct_target > entry_price:
        target_price = pct_target  # Fall back to % target
        level_note = ""
    if stop_price >= entry_price and pct_stop < entry_price:
        stop_price = pct_stop

    result = {
        "tier": tier,
        "trade_mode": trade_mode,
        "base_risk_pct": base_risk_pct,
        "final_risk_pct": final_risk_pct,
        "risk_amount": round(risk_amount, 2),
        "max_contracts": max_contracts,
        "account_balance": round(account_balance, 2),
        "target_price": target_price,
        "stop_price": max(stop_price, 0.01),
        "pct_target": pct_target,    # Original % target (before level capping)
        "pct_stop": pct_stop,        # Original % stop
        "target_pct": f"+{target_pct:.0%}",
        "stop_pct": f"-{stop_pct:.0%}",
        "trailing_stop_pct": trailing_stop_pct,
        "max_hold_minutes": max_hold,
        "level_note": level_note,    # NEW: explains why target/stop was adjusted
        "session_mult": session_mult,
        "vol_mult": vol_mult,
        "minutes_to_close": session.minutes_to_close,
        "iv_used": iv,
        "delta_used": delta,
    }

    # ── v9: GEX Regime Strategy Switching ──
    # Fundamentally adjust targets, stops, sizing, and hold time based on
    # dealer gamma positioning. This is the core of Step 9.
    if gex_data is not None:
        regime = getattr(gex_data, "regime", "neutral")
        strength = getattr(gex_data, "regime_strength", 0.0)
        spot = getattr(gex_data, "spot", 0)
        cw = getattr(gex_data, "call_wall", 0)
        pw = getattr(gex_data, "put_wall", 0)
        flip = getattr(gex_data, "gex_flip_level", 0)

        profile = get_regime_profile(regime, strength, spot, cw, pw, flip)
        result = apply_regime_to_risk(result, profile)

    # ── v10: IV vs Realized Vol Adjustment ──
    # Layer vol-based adjustments on top of GEX regime adjustments.
    # Cheap options → wider targets, can hold longer
    # Expensive options → tighter targets, shorter holds
    if vol_data is not None:
        result = apply_vol_to_risk(result, vol_data)

    return result
