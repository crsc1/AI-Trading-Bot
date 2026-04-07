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
from .market_internals import MarketBreadth
from .gex_regime import get_regime_profile, apply_regime_to_risk
from .vol_analyzer import VolAnalysis, apply_vol_to_risk
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

# v14: Simplified to 7 core factors, total = 9.25
# Order flow is the primary driver. Weak/anti-predictive factors removed.
FACTOR_WEIGHTS_BASELINE = cfg.FACTOR_WEIGHTS_BASELINE
FULL_DENOMINATOR = sum(FACTOR_WEIGHTS_BASELINE.values())  # 9.25

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
    regime_state: Optional[Any] = None,
    event_context: Optional[Any] = None,
    sweep_data: Optional[Any] = None,
    # Legacy params kept for backward compat — ignored
    vanna_charm_data: Optional[Any] = None,
    vpin_state: Optional[Any] = None,
    sector_data: Optional[Any] = None,
    agent_verdicts: Optional[Dict[str, Any]] = None,
    breadth_data: Optional[MarketBreadth] = None,
    vol_data: Optional[VolAnalysis] = None,
    trades_source: str = "options_flow",
) -> Tuple[str, float, List[ConfluenceFactor]]:
    """
    Evaluate confluence factors and determine signal direction + confidence.

    v14: Simplified to 7 core factors (from 23). Order flow is the primary
    driver. Removed factors with negative accuracy (PCR, max pain), redundant
    signals (DEX, delta regime), and too-slow macro signals (sectors, breadth).
    Regime and event multipliers still apply post-scoring.

    Returns:
        (action, confidence, factors) where action is BUY_CALL, BUY_PUT, or NO_TRADE
    """
    factors: List[ConfluenceFactor] = []
    price = levels.current_price

    # ━━━━ Determine preliminary direction from flow ━━━━
    prelim_direction = _get_preliminary_direction(flow, levels, session)

    # ━━━━ 7-FACTOR COMPOSITE SCORING ━━━━
    composite_scores: Dict[str, float] = {}

    # ── Factor 1: Order Flow Imbalance (max 2.0) ──
    f1_score, f1_detail = _score_flow_imbalance(flow, prelim_direction)
    composite_scores["order_flow_imbalance"] = max(-0.75, min(2.0, f1_score))
    if abs(f1_score) > 0.1:
        direction = prelim_direction if f1_score > 0 else ("bearish" if prelim_direction == "bullish" else "bullish")
        factors.append(ConfluenceFactor("Order Flow Imbalance", direction, f1_score, f1_detail))

    # ── Factor 2: CVD Divergence (max 1.5) ──
    f2_score, f2_detail = _score_cvd_divergence(flow, prelim_direction)
    composite_scores["cvd_divergence"] = max(-0.50, min(1.5, f2_score))
    if abs(f2_score) > 0.1:
        factors.append(ConfluenceFactor(
            "CVD Divergence",
            "bullish" if flow.divergence == "bullish" else ("bearish" if flow.divergence == "bearish" else "neutral"),
            f2_score, f2_detail
        ))

    # ── Factor 3: GEX Alignment (max 1.5) ──
    if gex_data is not None:
        from .gex_engine import score_gex_alignment
        is_trend = _is_trend_signal(flow, levels, session)
        f3_score, f3_detail = score_gex_alignment(gex_data, prelim_direction, is_trend)
        composite_scores["gex_alignment"] = max(-0.5, min(1.5, f3_score))
        if abs(f3_score) > 0.1:
            factors.append(ConfluenceFactor(
                "GEX Alignment", "neutral", f3_score, f3_detail
            ))

    # ── Factor 4: VWAP Band Rejection (max 1.0) ──
    f4_score, f4_factors = _score_vwap(flow, levels)
    composite_scores["vwap_rejection"] = max(-0.30, min(1.0, f4_score))
    factors.extend(f4_factors)

    # ── Factor 5: Sweep Activity (max 1.0) ──
    if sweep_data is not None:
        try:
            from .sweep_detector import score_sweep_activity
            f5_score, f5_detail = score_sweep_activity(sweep_data, prelim_direction)
            composite_scores["sweep_activity"] = max(-0.30, min(1.0, f5_score))
            if abs(f5_score) > 0.05:
                direction = "bullish" if f5_score > 0 else ("bearish" if f5_score < 0 else "neutral")
                factors.append(ConfluenceFactor(
                    "Sweep Flow", direction, f5_score, f5_detail
                ))
        except Exception as e:
            logger.debug(f"Sweep scoring error: {e}")

    # ── Factor 6: ORB Breakout (max 1.25) ──
    f6_score, f6_detail = _score_orb_breakout(levels, flow, session, prelim_direction)
    composite_scores["orb_breakout"] = max(-0.40, min(1.25, f6_score))
    if abs(f6_score) > 0.05:
        direction = prelim_direction if f6_score > 0 else ("bearish" if prelim_direction == "bullish" else "bullish")
        factors.append(ConfluenceFactor("ORB Breakout", direction, f6_score, f6_detail))

    # ── Factor 7: Support/Resistance levels (max 1.0) ──
    f7_score, f7_detail = _score_support_resistance(flow, levels, session, prelim_direction)
    composite_scores["support_resistance"] = max(-0.40, min(1.0, f7_score))
    if abs(f7_score) > 0.05:
        direction = prelim_direction if f7_score > 0 else ("bearish" if prelim_direction == "bullish" else "bullish")
        factors.append(ConfluenceFactor("S/R Levels", direction, f7_score, f7_detail))

    # ── Legacy structural display factors (HOD/LOD, etc.) ──
    _add_structural_factors(factors, flow, levels, session, price)

    # ── 0DTE Hard Stop (veto) ──
    if session.past_hard_stop and session.is_0dte:
        factors.append(ConfluenceFactor(
            "0DTE Hard Stop", "neutral", -0.50,
            f"Past {ZERO_DTE_HARD_STOP.strftime('%I:%M %p')} ET — NO new 0DTE trades"
        ))

    # ━━━━ ADAPTIVE WEIGHT SCALING — apply learned weights ━━━━
    active_w = get_active_weights()
    for factor_name, base_score in list(composite_scores.items()):
        baseline = FACTOR_WEIGHTS_BASELINE.get(factor_name, 0)
        learned = active_w.get(factor_name, baseline)
        if baseline > 0 and abs(learned - baseline) > 0.001:
            scale = learned / baseline
            composite_scores[factor_name] = base_score * scale

    # ━━━━ ORDER FLOW GATE — flow must not oppose direction ━━━━
    # v14: Relaxed from hard 55% veto to 52% + CVD confirmation.
    # With 7 carefully chosen factors, the gate only needs to prevent
    # trading AGAINST flow, not require overwhelming directional flow.
    # A 52% imbalance with rising CVD is meaningful with 5000+ ticks.
    flow_imbalance = flow.imbalance  # 0.0 to 1.0, 0.5 = balanced
    cvd_confirms_bullish = flow.cvd_trend == "rising"
    cvd_confirms_bearish = flow.cvd_trend == "falling"
    flow_confirms_bullish = flow_imbalance >= 0.52 and (flow_imbalance >= 0.55 or cvd_confirms_bullish)
    flow_confirms_bearish = flow_imbalance <= 0.48 and (flow_imbalance <= 0.45 or cvd_confirms_bearish)
    flow_opposes_bullish = flow_imbalance < 0.48  # Clear selling pressure
    flow_opposes_bearish = flow_imbalance > 0.52  # Clear buying pressure

    # ━━━━ AGGREGATE: determine direction and confidence ━━━━
    bullish_weight = sum(f.weight for f in factors if f.direction == "bullish")
    bearish_weight = sum(f.weight for f in factors if f.direction == "bearish")

    bullish_count = sum(1 for f in factors if f.direction == "bullish")
    bearish_count = sum(1 for f in factors if f.direction == "bearish")

    # Determine direction — flow must not actively oppose
    if bullish_weight > bearish_weight and bullish_count >= 1:
        if flow_confirms_bullish:
            action = "BUY_CALL"
        elif flow_opposes_bullish:
            action = "NO_TRADE"
            factors.append(ConfluenceFactor(
                "Flow Gate", "bearish", 0.0,
                f"Flow imbalance {flow_imbalance:.1%} opposes bullish signal (CVD: {flow.cvd_trend})"
            ))
        else:
            # Flow is neutral (48-52%) — allow if other factors are strong enough
            action = "BUY_CALL"
            factors.append(ConfluenceFactor(
                "Flow Gate", "neutral", -0.05,
                f"Flow neutral {flow_imbalance:.1%} — allowing on factor strength"
            ))
        confirming = bullish_count
        opposing = bearish_count
    elif bearish_weight > bullish_weight and bearish_count >= 1:
        if flow_confirms_bearish:
            action = "BUY_PUT"
        elif flow_opposes_bearish:
            action = "NO_TRADE"
            factors.append(ConfluenceFactor(
                "Flow Gate", "bullish", 0.0,
                f"Flow imbalance {flow_imbalance:.1%} opposes bearish signal (CVD: {flow.cvd_trend})"
            ))
        else:
            action = "BUY_PUT"
            factors.append(ConfluenceFactor(
                "Flow Gate", "neutral", -0.05,
                f"Flow neutral {flow_imbalance:.1%} — allowing on factor strength"
            ))
        confirming = bearish_count
        opposing = bullish_count
    else:
        action = "NO_TRADE"
        confirming = 0
        opposing = 0

    # ── Compute confidence ──
    # v14: Simplified for 7-factor system.
    # Score against active factors only (GEX/sweep may not be available).
    total_composite = sum(max(0, v) for v in composite_scores.values())
    active_keys = [k for k in composite_scores if abs(composite_scores[k]) > 0.03]
    num_active = len(active_keys)
    active_max = sum(FACTOR_WEIGHTS_BASELINE.get(k, 0) for k in active_keys)
    if active_max <= 0:
        active_max = FULL_DENOMINATOR

    if num_active >= 2:
        penalty = 0.06 * opposing

        # Score against active factors' weight budget, not full budget
        pure_score = total_composite / active_max
        raw_confidence = pure_score - penalty

        # Confluence bonus floors — 7 factors, so thresholds are tighter:
        #   5/7 confirming (~71%) AND opposing ≤ 1 → TEXTBOOK
        #   4/7 confirming (~57%) AND opposing ≤ 2 → HIGH
        #   3/7 confirming (~43%) → HIGH * 0.85
        if pure_score >= 0.30:
            if confirming >= 5 and opposing <= 1:
                raw_confidence = max(raw_confidence, TIER_TEXTBOOK)
            elif confirming >= 4 and opposing <= 2:
                raw_confidence = max(raw_confidence, TIER_HIGH * 0.95)
            elif confirming >= 3:
                raw_confidence = max(raw_confidence, TIER_HIGH * 0.85)
    else:
        raw_confidence = 0.0

    confidence = max(0.0, min(1.0, raw_confidence))

    # ── Apply regime multiplier ──
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

    # ── Apply event multiplier ──
    if event_context is not None:
        try:
            from .event_calendar import score_event_context
            event_mult, event_detail = score_event_context(event_context)
            confidence *= event_mult
            if abs(event_mult - 1.0) > 0.05:
                direction = "neutral"
                if event_mult < 0.5:
                    direction = "bearish"
                factors.append(ConfluenceFactor(
                    "Event Calendar", direction, event_mult - 1.0, event_detail
                ))
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
    """Factor 1: Order flow imbalance scoring (max 2.0).

    v14: Tighter thresholds — real trending markets are 52-55%, not 60%+.
    Uses continuous scoring instead of dead zones.
    Also considers aggressive buy/sell percentage for quality.
    """
    imb = flow.imbalance  # 0=all sell, 1=all buy
    agg_buy = getattr(flow, 'aggressive_buy_pct', 0.5)
    agg_sell = getattr(flow, 'aggressive_sell_pct', 0.5)

    if direction == "bullish":
        if imb > 0.52:
            # Continuous score: 0.52 → 0.3, 0.55 → 1.0, 0.60 → 1.5, 0.65+ → 2.0
            base = min(2.0, (imb - 0.50) * 10.0)
            # Bonus for aggressive buying (lifting offers, not passive)
            if agg_buy > 0.60:
                base = min(2.0, base * 1.2)
            return base, f"Buy flow {imb:.0%} (agg={agg_buy:.0%}) confirms bullish"
        elif imb < 0.47:
            # Opposing: sellers dominate
            penalty = min(0.75, (0.50 - imb) * 5.0)
            return -penalty, f"Sell flow {imb:.0%} contradicts bullish"
        return 0.0, f"Balanced flow {imb:.0%}"

    elif direction == "bearish":
        if imb < 0.48:
            base = min(2.0, (0.50 - imb) * 10.0)
            if agg_sell > 0.60:
                base = min(2.0, base * 1.2)
            return base, f"Sell flow {imb:.0%} (agg={agg_sell:.0%}) confirms bearish"
        elif imb > 0.53:
            penalty = min(0.75, (imb - 0.50) * 5.0)
            return -penalty, f"Buy flow {imb:.0%} contradicts bearish"
        return 0.0, f"Balanced flow {imb:.0%}"

    return 0.0, f"Flow imbalance {imb:.0%} (no direction)"


def _score_cvd_divergence(flow: OrderFlowState, direction: str) -> Tuple[float, str]:
    """Factor 2: CVD divergence + trend scoring (max 1.5).

    v14: Divergence is the strongest signal (hidden buying/selling).
    CVD trend confirmation also scores meaningfully, scaled by acceleration.
    """
    accel = getattr(flow, 'cvd_acceleration', 0)

    # Divergence = strongest CVD signal
    if flow.divergence == "bullish" and direction == "bullish":
        return 1.5, f"Bullish divergence — price {flow.price_trend} but CVD {flow.cvd_trend} (hidden buying)"
    elif flow.divergence == "bearish" and direction == "bearish":
        return 1.5, f"Bearish divergence — price {flow.price_trend} but CVD {flow.cvd_trend} (hidden selling)"
    elif flow.divergence == "bullish" and direction == "bearish":
        return -0.5, "Bullish divergence contradicts bearish signal"
    elif flow.divergence == "bearish" and direction == "bullish":
        return -0.5, "Bearish divergence contradicts bullish signal"

    # CVD trend confirms direction — scale by acceleration
    if direction == "bullish" and flow.cvd_trend == "rising":
        base = 0.6
        if accel > 500:
            base = min(1.0, 0.6 + accel / 5000)
        return base, f"CVD rising (accel={accel:+.0f}) confirms bullish"
    elif direction == "bearish" and flow.cvd_trend == "falling":
        base = 0.6
        if accel < -500:
            base = min(1.0, 0.6 + abs(accel) / 5000)
        return base, f"CVD falling (accel={accel:+.0f}) confirms bearish"

    # CVD opposes direction
    if direction == "bullish" and flow.cvd_trend == "falling":
        return -0.3, f"CVD falling opposes bullish"
    elif direction == "bearish" and flow.cvd_trend == "rising":
        return -0.3, f"CVD rising opposes bearish"

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
