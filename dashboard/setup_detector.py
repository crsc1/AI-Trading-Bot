"""
Setup Detector — Pattern-based trade entries for 0DTE SPY options.

Replaces the factor-scoring confluence system. Instead of averaging 7 abstract
scores, this detects specific chart setups (VWAP bounce, HOD break, etc.)
and fires when confirmed by order flow.

NO_TRADE is the default. A setup fires only when a specific pattern is confirmed.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import deque
import time
import logging

from .market_levels import MarketLevels
from .confluence import OrderFlowState, SessionContext

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SetupSignal:
    """A detected setup ready for execution."""
    setup_name: str           # "VWAP_BOUNCE", "HOD_BREAK", etc.
    direction: str            # "BUY_CALL" or "BUY_PUT"
    quality: float            # 0.0-1.0 (how clean the setup is)
    trigger_price: float      # Price at which setup triggered
    invalidation_price: float # Price at which setup is dead
    trigger_detail: str       # "Price bounced from VWAP $657.30, now $657.55"
    flow_detail: str          # "Imbalance 62% buy, CVD rising"
    invalidation_detail: str  # "Invalid if price < $657.10"


@dataclass
class SetupState:
    """Persisted between 15s cycles. Tracks developing setups."""
    # Price history (last 20 cycles = 5 min)
    price_history: deque = field(default_factory=lambda: deque(maxlen=20))

    # VWAP approach tracking
    vwap_touch_ts: float = 0.0
    vwap_touch_price: float = 0.0
    vwap_approach_side: str = ""  # "above" or "below"

    # HOD/LOD tracking
    hod_prev: float = 0.0
    lod_prev: float = 0.0
    hod_break_ts: float = 0.0
    lod_break_ts: float = 0.0
    hod_break_level: float = 0.0  # The old HOD that was broken
    lod_break_level: float = 0.0

    # ORB tracking
    orb_break_ts: float = 0.0
    orb_break_direction: str = ""
    orb_break_level: float = 0.0

    # Absorption tracking
    last_absorption_ts: float = 0.0
    last_absorption_level: float = 0.0
    last_absorption_bias: str = ""

    # EMA pullback tracking (trend continuation)
    ema9_touch_ts: float = 0.0
    ema9_touch_price: float = 0.0

    # Chop zone: tracks how many times absorption fires near a price level
    # Key = price rounded to nearest $0.25, Value = (count, last_ts)
    absorption_level_tests: Dict[float, Tuple[int, float]] = field(default_factory=dict)

    # Pin detection: track how long price stays in a tight range
    pin_range_start_ts: float = 0.0  # When tight range started
    pin_detected: bool = False

    # Cycle counter
    cycle_count: int = 0


# ═══════════════════════════════════════════════════════════════════════════════
# SETUP DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _atr(levels: MarketLevels) -> float:
    """Get ATR_1m, fallback to 0.50 if unavailable."""
    atr = getattr(levels, 'atr_1m', 0) or 0
    return max(atr, 0.10)  # Floor at $0.10


def _flow_confirms_bullish(flow: OrderFlowState, strict: bool = True) -> bool:
    threshold = 0.55 if strict else 0.52
    return flow.imbalance >= threshold


def _flow_confirms_bearish(flow: OrderFlowState, strict: bool = True) -> bool:
    threshold = 0.45 if strict else 0.48
    return flow.imbalance <= threshold


def _flow_summary(flow: OrderFlowState) -> str:
    parts = [f"imb={flow.imbalance:.0%}"]
    if flow.cvd_trend != "neutral":
        parts.append(f"CVD {flow.cvd_trend}")
    if flow.large_trade_count > 0:
        parts.append(f"{flow.large_trade_count} large ({flow.large_trade_bias})")
    if flow.absorption_detected:
        parts.append(f"absorption ({flow.absorption_bias})")
    return ", ".join(parts)


# ── Setup 1: VWAP Bounce ─────────────────────────────────────────────────────

def _check_vwap_bounce(
    levels: MarketLevels, flow: OrderFlowState, session: SessionContext,
    state: SetupState, flow_ctx: Optional[dict],
) -> Optional[SetupSignal]:
    """Price pulls back to VWAP, holds, bounces with flow confirmation."""
    price = levels.current_price
    vwap = getattr(levels, 'vwap', 0)
    atr = _atr(levels)
    now = time.monotonic()

    if not vwap or vwap <= 0:
        return None

    dist_to_vwap = abs(price - vwap)
    touch_zone = 0.3 * atr

    # Track VWAP touch
    if dist_to_vwap <= touch_zone:
        if state.vwap_touch_ts == 0 or (now - state.vwap_touch_ts) > 120:
            # New touch
            state.vwap_touch_ts = now
            state.vwap_touch_price = price
            state.vwap_approach_side = "above" if price >= vwap else "below"
        return None  # Still at VWAP, not bouncing yet

    # Check for bounce — need a prior touch within last 3 cycles (45s)
    if state.vwap_touch_ts == 0 or (now - state.vwap_touch_ts) > 45:
        return None

    bounce_dist = 0.2 * atr

    # Bullish bounce: approached from above (pullback), now moving up
    if price > vwap + bounce_dist:
        if not (_flow_confirms_bullish(flow) and flow.cvd_trend == "rising"):
            return None

        quality = 0.50
        if flow.imbalance >= 0.60:
            quality += 0.15
        if flow.large_trade_bias == "buy":
            quality += 0.15
        if session.phase in ("opening_drive", "morning_trend"):
            quality += 0.10
        # Bonus if near POC
        poc = getattr(levels, 'poc', 0)
        if poc and abs(vwap - poc) < atr:
            quality += 0.10
        quality = min(1.0, quality)

        inv_price = vwap - 0.5 * atr
        return SetupSignal(
            setup_name="VWAP_BOUNCE",
            direction="BUY_CALL",
            quality=quality,
            trigger_price=price,
            invalidation_price=inv_price,
            trigger_detail=f"Bounced from VWAP ${vwap:.2f}, now ${price:.2f} (+${price-vwap:.2f})",
            flow_detail=_flow_summary(flow),
            invalidation_detail=f"Invalid below ${inv_price:.2f} (VWAP - 0.5*ATR)",
        )

    # Bearish bounce: approached from below, now moving down
    if price < vwap - bounce_dist:
        if not (_flow_confirms_bearish(flow) and flow.cvd_trend == "falling"):
            return None

        quality = 0.50
        if flow.imbalance <= 0.40:
            quality += 0.15
        if flow.large_trade_bias == "sell":
            quality += 0.15
        if session.phase in ("opening_drive", "morning_trend"):
            quality += 0.10
        quality = min(1.0, quality)

        inv_price = vwap + 0.5 * atr
        return SetupSignal(
            setup_name="VWAP_BOUNCE",
            direction="BUY_PUT",
            quality=quality,
            trigger_price=price,
            invalidation_price=inv_price,
            trigger_detail=f"Rejected from VWAP ${vwap:.2f}, now ${price:.2f} (-${vwap-price:.2f})",
            flow_detail=_flow_summary(flow),
            invalidation_detail=f"Invalid above ${inv_price:.2f} (VWAP + 0.5*ATR)",
        )

    return None


# ── Setup 2: HOD Break ───────────────────────────────────────────────────────

def _check_hod_break(
    levels: MarketLevels, flow: OrderFlowState, session: SessionContext,
    state: SetupState, flow_ctx: Optional[dict],
) -> Optional[SetupSignal]:
    """Price breaks above HOD with volume and flow confirmation."""
    price = levels.current_price
    hod = getattr(levels, 'hod', 0)
    atr = _atr(levels)
    now = time.monotonic()

    if not hod or hod <= 0:
        return None

    # Detect new HOD break
    if state.hod_prev > 0 and hod > state.hod_prev + 0.05:
        # HOD just increased — a break happened
        state.hod_break_ts = now
        state.hod_break_level = state.hod_prev

    # Check if we have a recent break (within 60s)
    if state.hod_break_ts == 0 or (now - state.hod_break_ts) > 60:
        return None

    # Price must be above the old HOD by at least $0.10
    if price <= state.hod_break_level + 0.10:
        return None

    # Flow confirmation: at least 2 of 3
    confirms = 0
    if _flow_confirms_bullish(flow):
        confirms += 1
    if flow.cvd_trend == "rising":
        confirms += 1
    if flow.large_trade_bias == "buy":
        confirms += 1

    if confirms < 2:
        return None

    quality = 0.50
    if flow.total_volume > 0:
        quality += 0.15  # Volume present
    vwap = getattr(levels, 'vwap', 0)
    if vwap and price > vwap:
        quality += 0.15  # Above VWAP
    orb_high = getattr(levels, 'orb_30_high', 0) or getattr(levels, 'orb_high', 0)
    if orb_high and price > orb_high:
        quality += 0.10  # Also above ORB
    if session.phase in ("opening_drive", "morning_trend"):
        quality += 0.10
    quality = min(1.0, quality)

    inv_price = state.hod_break_level - 0.05
    return SetupSignal(
        setup_name="HOD_BREAK",
        direction="BUY_CALL",
        quality=quality,
        trigger_price=price,
        invalidation_price=inv_price,
        trigger_detail=f"Broke HOD ${state.hod_break_level:.2f}, now ${price:.2f} (+${price-state.hod_break_level:.2f})",
        flow_detail=_flow_summary(flow),
        invalidation_detail=f"Invalid below old HOD ${inv_price:.2f}",
    )


# ── Setup 3: LOD Break ───────────────────────────────────────────────────────

def _check_lod_break(
    levels: MarketLevels, flow: OrderFlowState, session: SessionContext,
    state: SetupState, flow_ctx: Optional[dict],
) -> Optional[SetupSignal]:
    """Price breaks below LOD with volume and flow confirmation."""
    price = levels.current_price
    lod = getattr(levels, 'lod', 0)
    atr = _atr(levels)
    now = time.monotonic()

    if not lod or lod <= 0:
        return None

    # Detect new LOD break
    if state.lod_prev > 0 and lod < state.lod_prev - 0.05:
        state.lod_break_ts = now
        state.lod_break_level = state.lod_prev

    if state.lod_break_ts == 0 or (now - state.lod_break_ts) > 60:
        return None

    if price >= state.lod_break_level - 0.10:
        return None

    confirms = 0
    if _flow_confirms_bearish(flow):
        confirms += 1
    if flow.cvd_trend == "falling":
        confirms += 1
    if flow.large_trade_bias == "sell":
        confirms += 1

    if confirms < 2:
        return None

    quality = 0.50
    if flow.total_volume > 0:
        quality += 0.15
    vwap = getattr(levels, 'vwap', 0)
    if vwap and price < vwap:
        quality += 0.15
    if session.phase in ("opening_drive", "morning_trend"):
        quality += 0.10
    quality = min(1.0, quality)

    inv_price = state.lod_break_level + 0.05
    return SetupSignal(
        setup_name="LOD_BREAK",
        direction="BUY_PUT",
        quality=quality,
        trigger_price=price,
        invalidation_price=inv_price,
        trigger_detail=f"Broke LOD ${state.lod_break_level:.2f}, now ${price:.2f} (-${state.lod_break_level-price:.2f})",
        flow_detail=_flow_summary(flow),
        invalidation_detail=f"Invalid above old LOD ${inv_price:.2f}",
    )


# ── Setup 4: ORB Breakout ────────────────────────────────────────────────────

def _check_orb_breakout(
    levels: MarketLevels, flow: OrderFlowState, session: SessionContext,
    state: SetupState, flow_ctx: Optional[dict],
) -> Optional[SetupSignal]:
    """Price breaks above/below 30-min ORB with flow confirmation."""
    price = levels.current_price
    atr = _atr(levels)
    now = time.monotonic()

    orb_high = getattr(levels, 'orb_30_high', 0) or getattr(levels, 'orb_high', 0)
    orb_low = getattr(levels, 'orb_30_low', 0) or getattr(levels, 'orb_low', 0)
    orb_confirmed = getattr(levels, 'orb_confirmed', False)

    if not orb_high or not orb_low or not orb_confirmed:
        return None

    # Must be past the opening range period
    if session.phase == "opening_drive":
        return None

    # Bullish ORB breakout
    if price > orb_high + 0.15:
        if state.orb_break_direction != "above" or (now - state.orb_break_ts) > 90:
            state.orb_break_ts = now
            state.orb_break_direction = "above"
            state.orb_break_level = orb_high

        confirms = 0
        if flow.cvd_trend == "rising":
            confirms += 1
        if _flow_confirms_bullish(flow):
            confirms += 1
        if not flow.absorption_detected or flow.absorption_bias != "bearish":
            confirms += 1

        if confirms < 2:
            return None

        quality = 0.50
        orb_width = orb_high - orb_low
        atr_5m = getattr(levels, 'atr_5m', atr * 2.2)
        if orb_width > 0 and orb_width < 0.8 * atr_5m:
            quality += 0.20  # Narrow ORB = explosive
        vwap = getattr(levels, 'vwap', 0)
        if vwap and price > vwap:
            quality += 0.15
        if flow.imbalance >= 0.60:
            quality += 0.15
        quality = min(1.0, quality)

        inv_price = orb_high - 0.05
        return SetupSignal(
            setup_name="ORB_BREAKOUT",
            direction="BUY_CALL",
            quality=quality,
            trigger_price=price,
            invalidation_price=inv_price,
            trigger_detail=f"Broke ORB high ${orb_high:.2f}, now ${price:.2f} (+${price-orb_high:.2f})",
            flow_detail=_flow_summary(flow),
            invalidation_detail=f"Invalid below ORB high ${inv_price:.2f}",
        )

    # Bearish ORB breakout
    if price < orb_low - 0.15:
        if state.orb_break_direction != "below" or (now - state.orb_break_ts) > 90:
            state.orb_break_ts = now
            state.orb_break_direction = "below"
            state.orb_break_level = orb_low

        confirms = 0
        if flow.cvd_trend == "falling":
            confirms += 1
        if _flow_confirms_bearish(flow):
            confirms += 1
        if not flow.absorption_detected or flow.absorption_bias != "bullish":
            confirms += 1

        if confirms < 2:
            return None

        quality = 0.50
        orb_width = orb_high - orb_low
        atr_5m = getattr(levels, 'atr_5m', atr * 2.2)
        if orb_width > 0 and orb_width < 0.8 * atr_5m:
            quality += 0.20
        vwap = getattr(levels, 'vwap', 0)
        if vwap and price < vwap:
            quality += 0.15
        if flow.imbalance <= 0.40:
            quality += 0.15
        quality = min(1.0, quality)

        inv_price = orb_low + 0.05
        return SetupSignal(
            setup_name="ORB_BREAKOUT",
            direction="BUY_PUT",
            quality=quality,
            trigger_price=price,
            invalidation_price=inv_price,
            trigger_detail=f"Broke ORB low ${orb_low:.2f}, now ${price:.2f} (-${orb_low-price:.2f})",
            flow_detail=_flow_summary(flow),
            invalidation_detail=f"Invalid above ORB low ${inv_price:.2f}",
        )

    return None


# ── Setup 5: Absorption Reversal ─────────────────────────────────────────────

def _check_absorption_reversal(
    levels: MarketLevels, flow: OrderFlowState, session: SessionContext,
    state: SetupState, flow_ctx: Optional[dict],
) -> Optional[SetupSignal]:
    """Heavy selling absorbed at support → reversal up, or vice versa."""
    price = levels.current_price
    atr = _atr(levels)
    now = time.monotonic()

    if not flow.absorption_detected:
        return None

    # Track fresh absorption
    abs_levels = getattr(flow, 'absorption_levels', [])
    abs_bias = flow.absorption_bias
    if abs_levels:
        state.last_absorption_ts = now
        state.last_absorption_level = abs_levels[0]
        state.last_absorption_bias = abs_bias

    # ── Mega-block direction flip (fix #2) ──
    # If 500K+ buy volume against bearish absorption, flip to bullish (and vice versa)
    if flow_ctx and state.last_absorption_bias:
        mega_buy = flow_ctx.get('large_trade_buy_vol', 0) or 0
        mega_sell = flow_ctx.get('large_trade_sell_vol', 0) or 0
        if state.last_absorption_bias == "bearish" and mega_buy >= 500_000:
            logger.info(
                f"[SetupDetector] Absorption flip: bearish→bullish on {mega_buy:,} share buy block"
            )
            state.last_absorption_bias = "bullish"
        elif state.last_absorption_bias == "bullish" and mega_sell >= 500_000:
            logger.info(
                f"[SetupDetector] Absorption flip: bullish→bearish on {mega_sell:,} share sell block"
            )
            state.last_absorption_bias = "bearish"

    # Need fresh absorption (within 60s)
    if state.last_absorption_ts == 0 or (now - state.last_absorption_ts) > 60:
        return None

    abs_lvl = state.last_absorption_level

    # ── Chop zone detection (fix #1) ──
    # Suppress if the same price zone has been tested 10+ times
    level_key = round(abs_lvl * 4) / 4  # Round to nearest $0.25
    test_count, _last_test_ts = state.absorption_level_tests.get(level_key, (0, 0))
    if test_count >= 10:
        logger.info(
            f"[SetupDetector] Chop zone: ${abs_lvl:.2f} tested {test_count}x, suppressing"
        )
        return None
    # Record this test
    state.absorption_level_tests[level_key] = (test_count + 1, now)
    # Expire old entries (>30 min)
    state.absorption_level_tests = {
        k: v for k, v in state.absorption_level_tests.items()
        if now - v[1] < 1800
    }

    # Bullish absorption: selling absorbed at support, price reversing up
    if state.last_absorption_bias == "bullish" and price > abs_lvl + 0.15:
        # CVD should have shifted — no longer falling
        if flow.cvd_trend == "falling":
            return None
        # Flow at least neutral
        if flow.imbalance < 0.48:
            return None

        quality = 0.60  # Absorption is high conviction
        # Bonus: level coincides with VWAP, POC, or pivot
        vwap = getattr(levels, 'vwap', 0)
        poc = getattr(levels, 'poc', 0)
        s1 = getattr(levels, 's1', 0)
        for ref in [vwap, poc, s1]:
            if ref and abs(abs_lvl - ref) < 0.3 * atr:
                quality += 0.15
                break
        # Multiple absorptions at same area
        if flow_ctx:
            abs_count = flow_ctx.get('absorption_bid_count', 0)
            if abs_count >= 2:
                quality += 0.15
            # Mega-block bonus (fix #3): 100K+ share trades are high conviction
            if (flow_ctx.get('large_trade_buy_vol', 0) or 0) >= 100_000:
                quality += 0.10
        if getattr(flow, 'volume_exhausted', False):
            quality += 0.10
        quality = min(1.0, quality)

        inv_price = abs_lvl - 0.3 * atr
        return SetupSignal(
            setup_name="ABSORPTION_REVERSAL",
            direction="BUY_CALL",
            quality=quality,
            trigger_price=price,
            invalidation_price=inv_price,
            trigger_detail=f"Selling absorbed at ${abs_lvl:.2f}, reversing up to ${price:.2f}",
            flow_detail=_flow_summary(flow),
            invalidation_detail=f"Invalid below ${inv_price:.2f} (absorption level broke)",
        )

    # Bearish absorption: buying absorbed at resistance, price reversing down
    if state.last_absorption_bias == "bearish" and price < abs_lvl - 0.15:
        if flow.cvd_trend == "rising":
            return None
        if flow.imbalance > 0.52:
            return None

        quality = 0.60
        vwap = getattr(levels, 'vwap', 0)
        poc = getattr(levels, 'poc', 0)
        r1 = getattr(levels, 'r1', 0)
        for ref in [vwap, poc, r1]:
            if ref and abs(abs_lvl - ref) < 0.3 * atr:
                quality += 0.15
                break
        if flow_ctx:
            abs_count = flow_ctx.get('absorption_ask_count', 0)
            if abs_count >= 2:
                quality += 0.15
            # Mega-block bonus (fix #3): 100K+ share trades are high conviction
            if (flow_ctx.get('large_trade_sell_vol', 0) or 0) >= 100_000:
                quality += 0.10
        if getattr(flow, 'volume_exhausted', False):
            quality += 0.10
        quality = min(1.0, quality)

        inv_price = abs_lvl + 0.3 * atr
        return SetupSignal(
            setup_name="ABSORPTION_REVERSAL",
            direction="BUY_PUT",
            quality=quality,
            trigger_price=price,
            invalidation_price=inv_price,
            trigger_detail=f"Buying absorbed at ${abs_lvl:.2f}, reversing down to ${price:.2f}",
            flow_detail=_flow_summary(flow),
            invalidation_detail=f"Invalid above ${inv_price:.2f} (absorption level broke)",
        )

    return None


# ── Setup 6: Trend Continuation ──────────────────────────────────────────────

def _check_trend_continuation(
    levels: MarketLevels, flow: OrderFlowState, session: SessionContext,
    state: SetupState, flow_ctx: Optional[dict],
) -> Optional[SetupSignal]:
    """Trend established, price pulls back to EMA9, bounces with flow."""
    price = levels.current_price
    atr = _atr(levels)
    now = time.monotonic()

    vwap = getattr(levels, 'vwap', 0)
    ema9 = getattr(levels, 'ema_9', 0) or getattr(levels, 'ema_8', 0)
    ema21 = getattr(levels, 'ema_21', 0)

    if not vwap or not ema9 or not ema21:
        return None

    touch_zone = 0.3 * atr

    # Bullish trend: price > VWAP, price > EMA21, EMA9 > EMA21
    if price > vwap and price > ema21 and ema9 > ema21:
        # Track EMA9 touch
        if abs(price - ema9) <= touch_zone:
            state.ema9_touch_ts = now
            state.ema9_touch_price = price
            return None  # At EMA9, waiting for bounce

        # Check for bounce from recent touch
        if state.ema9_touch_ts == 0 or (now - state.ema9_touch_ts) > 45:
            return None

        if price <= ema9 + 0.15:
            return None  # Not bouncing yet

        # Flow confirmation (lower bar — trend is already confirmed structurally)
        if flow.imbalance < 0.52 or flow.cvd_trend == "falling":
            return None

        quality = 0.50
        if flow.large_trade_bias == "buy":
            quality += 0.15
        if session.phase in ("morning_trend", "afternoon_trend"):
            quality += 0.10
        # Price between VWAP and VWAP+1σ (healthy position)
        vwap_u1 = getattr(levels, 'vwap_upper_1', 0)
        if vwap_u1 and vwap < price < vwap_u1:
            quality += 0.10
        quality = min(1.0, quality)

        inv_price = ema21
        return SetupSignal(
            setup_name="TREND_CONTINUATION",
            direction="BUY_CALL",
            quality=quality,
            trigger_price=price,
            invalidation_price=inv_price,
            trigger_detail=f"Uptrend pullback to EMA9 ${ema9:.2f}, bounced to ${price:.2f}",
            flow_detail=_flow_summary(flow),
            invalidation_detail=f"Invalid below EMA21 ${inv_price:.2f}",
        )

    # Bearish trend: price < VWAP, price < EMA21, EMA9 < EMA21
    if price < vwap and price < ema21 and ema9 < ema21:
        if abs(price - ema9) <= touch_zone:
            state.ema9_touch_ts = now
            state.ema9_touch_price = price
            return None

        if state.ema9_touch_ts == 0 or (now - state.ema9_touch_ts) > 45:
            return None

        if price >= ema9 - 0.15:
            return None

        if flow.imbalance > 0.48 or flow.cvd_trend == "rising":
            return None

        quality = 0.50
        if flow.large_trade_bias == "sell":
            quality += 0.15
        if session.phase in ("morning_trend", "afternoon_trend"):
            quality += 0.10
        vwap_l1 = getattr(levels, 'vwap_lower_1', 0)
        if vwap_l1 and vwap > price > vwap_l1:
            quality += 0.10
        quality = min(1.0, quality)

        inv_price = ema21
        return SetupSignal(
            setup_name="TREND_CONTINUATION",
            direction="BUY_PUT",
            quality=quality,
            trigger_price=price,
            invalidation_price=inv_price,
            trigger_detail=f"Downtrend pullback to EMA9 ${ema9:.2f}, rejected to ${price:.2f}",
            flow_detail=_flow_summary(flow),
            invalidation_detail=f"Invalid above EMA21 ${inv_price:.2f}",
        )

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# SETUP DETECTOR
# ═══════════════════════════════════════════════════════════════════════════════

# Ordered by priority: absorption (rare, high conviction) first, trend cont last
_SETUP_CHECKS = [
    _check_absorption_reversal,
    _check_hod_break,
    _check_lod_break,
    _check_orb_breakout,
    _check_vwap_bounce,
    _check_trend_continuation,
]


class SetupDetector:
    """Detects specific trading setups from real-time market data."""

    def __init__(self):
        self._state = SetupState()

    def detect(
        self,
        levels: MarketLevels,
        flow: OrderFlowState,
        session: SessionContext,
        flow_context: Optional[dict] = None,
    ) -> Optional[SetupSignal]:
        """
        Run all setup detectors. Returns the highest-quality triggered setup,
        or None if no setup fires.

        Called every 15 seconds from _run_analysis_cycle().
        """
        self._update_state(levels)

        # ── Pin detection (fix #5) ──
        # Suppress all entries when price is pinned in a tight range
        if self._is_pinned(levels):
            logger.info(
                f"[SetupDetector] Pin detected: price stuck in tight range, suppressing all setups"
            )
            return None

        candidates = []
        for check_fn in _SETUP_CHECKS:
            try:
                result = check_fn(levels, flow, session, self._state, flow_context)
                if result is not None:
                    candidates.append(result)
            except Exception as e:
                logger.debug(f"Setup check {check_fn.__name__} error: {e}")

        if not candidates:
            return None

        best = max(candidates, key=lambda s: s.quality)

        # ── Late-day theta filter (fix #4) ──
        # After 2:30 PM (90 min to close) require higher quality.
        # After 3:00 PM (60 min to close) require 0.85 or HOD/LOD break only.
        mtc = session.minutes_to_close
        if 0 < mtc <= 60:
            # Last hour: only HOD/LOD breaks or quality >= 0.85
            if best.setup_name not in ("HOD_BREAK", "LOD_BREAK") and best.quality < 0.85:
                logger.info(
                    f"[SetupDetector] Late-day filter: {best.setup_name} quality "
                    f"{best.quality:.2f} < 0.85 with {mtc}min to close, suppressing"
                )
                return None
        elif 0 < mtc <= 90:
            # After 2:30: require quality >= 0.75
            if best.quality < 0.75:
                logger.info(
                    f"[SetupDetector] Late-day filter: {best.setup_name} quality "
                    f"{best.quality:.2f} < 0.75 with {mtc}min to close, suppressing"
                )
                return None

        logger.info(
            f"[SetupDetector] {best.setup_name} {best.direction} "
            f"quality={best.quality:.2f} — {best.trigger_detail}"
        )
        return best

    def _is_pinned(self, levels: MarketLevels) -> bool:
        """
        Detect if price is pinned in a tight range (fix #5).

        Pinned = price range < 0.5 * ATR for 30+ minutes (120 cycles at 15s).
        This catches dealer pinning near round strikes where options premium
        just bleeds theta without directional movement.
        """
        s = self._state
        now = time.monotonic()
        atr = _atr(levels)
        pin_threshold = 0.5 * atr
        pin_duration = 1800  # 30 minutes in seconds

        # Need at least 10 cycles of history to evaluate
        if len(s.price_history) < 10:
            s.pin_detected = False
            return False

        # Check price range over the history window
        recent_prices = [p for ts, p in s.price_history if now - ts < pin_duration]
        if len(recent_prices) < 10:
            s.pin_detected = False
            return False

        price_range = max(recent_prices) - min(recent_prices)

        if price_range < pin_threshold:
            if s.pin_range_start_ts == 0:
                s.pin_range_start_ts = now
            elif now - s.pin_range_start_ts >= pin_duration:
                s.pin_detected = True
                return True
        else:
            # Range expanded, reset
            s.pin_range_start_ts = 0
            s.pin_detected = False

        return False

    def _update_state(self, levels: MarketLevels):
        """Update cycle-persistent state."""
        self._state.cycle_count += 1
        price = levels.current_price
        now = time.monotonic()

        # Track price history
        self._state.price_history.append((now, price))

        # Track HOD/LOD for break detection (update AFTER checking for breaks)
        hod = getattr(levels, 'hod', 0) or 0
        lod = getattr(levels, 'lod', 0) or 0
        if hod > 0:
            self._state.hod_prev = hod
        if lod > 0:
            self._state.lod_prev = lod

    def get_state_summary(self) -> dict:
        """For diagnostics/display."""
        s = self._state
        now = time.monotonic()
        # Chop zone: show most-tested levels
        chop_levels = {
            f"${k:.2f}": v[0]
            for k, v in s.absorption_level_tests.items()
            if v[0] >= 2
        }
        return {
            "cycle_count": s.cycle_count,
            "vwap_touch_age_s": round(now - s.vwap_touch_ts, 1) if s.vwap_touch_ts else None,
            "hod_break_age_s": round(now - s.hod_break_ts, 1) if s.hod_break_ts else None,
            "lod_break_age_s": round(now - s.lod_break_ts, 1) if s.lod_break_ts else None,
            "orb_break": s.orb_break_direction or None,
            "absorption_bias": s.last_absorption_bias or None,
            "ema9_touch_age_s": round(now - s.ema9_touch_ts, 1) if s.ema9_touch_ts else None,
            "chop_levels": chop_levels if chop_levels else None,
            "pin_detected": s.pin_detected,
        }


# Module-level singleton
setup_detector = SetupDetector()
