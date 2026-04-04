"""
GEX Regime Strategy Switching — Step 9 of Money Machine Plan.

Uses GEX regime (positive/negative/neutral) to fundamentally change how
the bot trades, not just score alignment.

Key insight:
  Positive GEX = market makers dampen moves → mean reversion environment
    → Tighter profit targets, tighter stops
    → Can size up (lower realized vol expected)
    → Prefer fades over breakouts
    → Shorter hold times (range-bound moves are quick)

  Negative GEX = market makers amplify moves → trending environment
    → Wider profit targets, wider stops
    → Size down (higher realized vol expected)
    → Prefer breakouts over fades
    → Longer hold times (let trends run)

  Neutral GEX = no strong dealer positioning → use standard params

Data flow:
  gex_engine.calculate_gex() → GEXResult.regime + regime_strength
  → gex_regime.get_regime_profile() → RegimeProfile
  → Consumed by: calculate_risk(), dynamic_exit, position_manager
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Regime Profile ──────────────────────────────────────────────────────────

@dataclass
class RegimeProfile:
    """
    Parameter modifiers for a specific GEX regime.

    All multipliers are relative to the base trade mode params.
    1.0 = no change, >1.0 = wider/larger, <1.0 = tighter/smaller.
    """
    regime: str = "neutral"          # "positive", "negative", "neutral"
    regime_strength: float = 0.0     # 0-1 from GEXResult

    # Exit parameter multipliers
    target_mult: float = 1.0         # Profit target multiplier
    stop_mult: float = 1.0           # Stop loss multiplier
    trailing_mult: float = 1.0       # Trailing stop multiplier
    max_hold_mult: float = 1.0       # Max hold time multiplier

    # Position sizing multiplier
    size_mult: float = 1.0           # Risk % multiplier (1.0 = standard)

    # Strategy preference
    prefer_trend: bool = True        # True = breakouts, False = fades
    favor_momentum: bool = True      # Weight momentum signals higher

    # Dynamic exit adjustments
    exit_urgency_offset: float = 0.0  # Added to dynamic exit urgency
    tighten_after_minutes: int = 0    # Force tighten trailing after N min

    # Description for logging / dashboard
    label: str = "Standard"
    detail: str = ""

    def to_dict(self) -> Dict:
        return {
            "regime": self.regime,
            "regime_strength": round(self.regime_strength, 3),
            "target_mult": round(self.target_mult, 2),
            "stop_mult": round(self.stop_mult, 2),
            "trailing_mult": round(self.trailing_mult, 2),
            "max_hold_mult": round(self.max_hold_mult, 2),
            "size_mult": round(self.size_mult, 2),
            "prefer_trend": self.prefer_trend,
            "favor_momentum": self.favor_momentum,
            "exit_urgency_offset": round(self.exit_urgency_offset, 2),
            "tighten_after_minutes": self.tighten_after_minutes,
            "label": self.label,
            "detail": self.detail,
        }


# ─── Regime Profiles ─────────────────────────────────────────────────────────
# These are the base profiles. Actual multipliers are interpolated by
# regime_strength (0 = neutral behavior, 1 = full regime effect).

# Negative GEX: market makers amplify moves (trending)
_NEGATIVE_GEX_FULL = RegimeProfile(
    regime="negative",
    regime_strength=1.0,
    target_mult=1.40,      # 40% wider targets — let trends run
    stop_mult=1.25,        # 25% wider stops — accommodate bigger swings
    trailing_mult=1.20,    # Wider trailing — don't get shaken out of trends
    max_hold_mult=1.30,    # Hold longer — trends need time
    size_mult=0.75,        # 25% smaller size — higher vol = more risk per contract
    prefer_trend=True,
    favor_momentum=True,
    exit_urgency_offset=-0.05,  # Less urgent to exit (let trends develop)
    tighten_after_minutes=0,
    label="Negative GEX — Trend Mode",
    detail="Dealers amplifying moves: wider targets/stops, smaller size, favor breakouts",
)

# Positive GEX: market makers dampen moves (mean reversion)
_POSITIVE_GEX_FULL = RegimeProfile(
    regime="positive",
    regime_strength=1.0,
    target_mult=0.75,      # 25% tighter targets — moves get capped by dealers
    stop_mult=0.85,        # 15% tighter stops — tighter ranges
    trailing_mult=0.80,    # Tighter trailing — quick captures in range
    max_hold_mult=0.70,    # Shorter holds — range-bound moves resolve faster
    size_mult=1.15,        # 15% larger size — lower vol = less risk per contract
    prefer_trend=False,
    favor_momentum=False,
    exit_urgency_offset=0.05,   # More urgent to exit (dealer capping kills trends)
    tighten_after_minutes=15,   # Tighten trailing after 15 min (range should resolve)
    label="Positive GEX — Mean Reversion Mode",
    detail="Dealers dampening moves: tighter targets/stops, larger size, favor fades",
)


def _lerp(base: float, full: float, strength: float) -> float:
    """Linear interpolation from base (1.0) toward full value by strength."""
    return base + (full - base) * strength


def get_regime_profile(
    regime: str,
    regime_strength: float,
    spot: float = 0,
    call_wall: float = 0,
    put_wall: float = 0,
    gex_flip: float = 0,
) -> RegimeProfile:
    """
    Build a RegimeProfile from GEX data.

    Interpolates between neutral (all 1.0 multipliers) and the full regime
    profile based on regime_strength. Also considers proximity to key GEX
    levels (call/put walls, flip level).

    Args:
        regime: "positive", "negative", or "neutral" from GEXResult
        regime_strength: 0-1 from GEXResult
        spot: Current SPY price (for wall proximity)
        call_wall: Highest call GEX strike (resistance ceiling)
        put_wall: Highest put GEX strike (support floor)
        gex_flip: Price where GEX transitions pos→neg

    Returns:
        RegimeProfile with interpolated multipliers
    """
    strength = min(1.0, max(0.0, regime_strength))

    if regime == "negative" and strength >= 0.05:
        full = _NEGATIVE_GEX_FULL
        profile = RegimeProfile(
            regime="negative",
            regime_strength=strength,
            target_mult=_lerp(1.0, full.target_mult, strength),
            stop_mult=_lerp(1.0, full.stop_mult, strength),
            trailing_mult=_lerp(1.0, full.trailing_mult, strength),
            max_hold_mult=_lerp(1.0, full.max_hold_mult, strength),
            size_mult=_lerp(1.0, full.size_mult, strength),
            prefer_trend=strength > 0.3,
            favor_momentum=strength > 0.3,
            exit_urgency_offset=_lerp(0.0, full.exit_urgency_offset, strength),
            tighten_after_minutes=0,
            label=full.label if strength > 0.3 else "Mild Negative GEX",
            detail=full.detail if strength > 0.3 else "Mild dealer amplification",
        )

    elif regime == "positive" and strength >= 0.05:
        full = _POSITIVE_GEX_FULL
        profile = RegimeProfile(
            regime="positive",
            regime_strength=strength,
            target_mult=_lerp(1.0, full.target_mult, strength),
            stop_mult=_lerp(1.0, full.stop_mult, strength),
            trailing_mult=_lerp(1.0, full.trailing_mult, strength),
            max_hold_mult=_lerp(1.0, full.max_hold_mult, strength),
            size_mult=_lerp(1.0, full.size_mult, strength),
            prefer_trend=strength < 0.3,
            favor_momentum=strength < 0.3,
            exit_urgency_offset=_lerp(0.0, full.exit_urgency_offset, strength),
            tighten_after_minutes=int(full.tighten_after_minutes * strength),
            label=full.label if strength > 0.3 else "Mild Positive GEX",
            detail=full.detail if strength > 0.3 else "Mild dealer dampening",
        )

    else:
        profile = RegimeProfile(
            regime="neutral",
            regime_strength=strength,
            label="Neutral GEX",
            detail="No strong dealer positioning — standard parameters",
        )

    # ── Wall Proximity Adjustments ──
    # If price is near call wall or put wall, further tighten targets
    # because dealer hedging creates hard resistance/support at walls.
    if spot > 0 and call_wall > 0 and put_wall > 0:
        wall_range = call_wall - put_wall
        if wall_range > 0:
            # How far we are from call wall (0 = at wall, 1 = at put wall)
            pos_in_range = (call_wall - spot) / wall_range
            pos_in_range = min(1.0, max(0.0, pos_in_range))

            # Near call wall (< 20% away) → cap upside targets for calls
            if pos_in_range < 0.20:
                proximity_factor = 1.0 - pos_in_range  # 0.8 to 1.0
                # Reduce target by up to 20% when right at wall
                wall_reduction = 0.80 + 0.20 * (pos_in_range / 0.20)
                profile.target_mult *= wall_reduction
                profile.detail += f" | Near call wall (${call_wall:.0f})"

            # Near put wall (> 80% toward put wall) → cap downside targets for puts
            elif pos_in_range > 0.80:
                proximity_factor = pos_in_range
                wall_reduction = 0.80 + 0.20 * ((1.0 - pos_in_range) / 0.20)
                profile.target_mult *= wall_reduction
                profile.detail += f" | Near put wall (${put_wall:.0f})"

    # ── GEX Flip Level Proximity ──
    # Near the flip level, regime is unstable → use tighter params
    if spot > 0 and gex_flip > 0:
        flip_distance_pct = abs(spot - gex_flip) / spot
        if flip_distance_pct < 0.005:  # Within 0.5% of flip
            # Near flip = regime uncertain, tighten everything
            profile.target_mult *= 0.85
            profile.stop_mult *= 0.85
            profile.detail += f" | Near GEX flip (${gex_flip:.0f})"

    return profile


def apply_regime_to_risk(
    risk_params: Dict,
    profile: RegimeProfile,
) -> Dict:
    """
    Apply a GEX regime profile to the risk/exit parameters from calculate_risk().

    Mutates and returns the risk_params dict with regime-adjusted values.
    Original values are preserved under *_pre_regime keys for logging.

    Args:
        risk_params: Dict from calculate_risk()
        profile: RegimeProfile from get_regime_profile()

    Returns:
        Modified risk_params dict
    """
    if profile.regime == "neutral" and profile.regime_strength < 0.05:
        risk_params["gex_regime"] = profile.to_dict()
        return risk_params

    # Save pre-regime values for logging
    risk_params["_pre_regime_target"] = risk_params.get("target_price", 0)
    risk_params["_pre_regime_stop"] = risk_params.get("stop_price", 0)
    risk_params["_pre_regime_trailing"] = risk_params.get("trailing_stop_pct", 0)
    risk_params["_pre_regime_max_hold"] = risk_params.get("max_hold_minutes", 0)
    risk_params["_pre_regime_contracts"] = risk_params.get("max_contracts", 1)

    entry = risk_params.get("target_price", 0) / (1 + float(risk_params.get("target_pct", "+50%").strip('%+')) / 100) if "target_pct" in risk_params else 0

    # ── Adjust exit parameters ──
    # Adjust target_pct and stop_pct (the % values used by position_manager)
    trailing = risk_params.get("trailing_stop_pct", 0.15)
    risk_params["trailing_stop_pct"] = round(trailing * profile.trailing_mult, 4)

    max_hold = risk_params.get("max_hold_minutes", 25)
    risk_params["max_hold_minutes"] = max(3, int(max_hold * profile.max_hold_mult))

    # Adjust target_price and stop_price
    entry_price = risk_params.get("pct_target", 0) / (1 + 0.5) if risk_params.get("pct_target") else 0

    # More direct: adjust via pct_target and pct_stop which are absolute prices
    pct_target = risk_params.get("pct_target", 0)
    pct_stop = risk_params.get("pct_stop", 0)
    target_price = risk_params.get("target_price", pct_target)
    stop_price = risk_params.get("stop_price", pct_stop)

    if target_price > 0 and stop_price > 0:
        # Compute midpoint (entry estimate)
        # target = entry * (1 + pct), stop = entry * (1 - pct)
        # So entry ≈ (target + stop) / 2 as rough estimate
        entry_est = (target_price + stop_price) / 2

        if entry_est > 0:
            # Scale the distance from entry to target/stop
            target_dist = target_price - entry_est
            stop_dist = entry_est - stop_price

            new_target = entry_est + target_dist * profile.target_mult
            new_stop = entry_est - stop_dist * profile.stop_mult

            risk_params["target_price"] = round(max(new_target, entry_est + 0.01), 2)
            risk_params["stop_price"] = round(max(new_stop, 0.01), 2)

    # ── Adjust position sizing ──
    max_contracts = risk_params.get("max_contracts", 1)
    adjusted = max(1, round(max_contracts * profile.size_mult))
    risk_params["max_contracts"] = adjusted

    risk_amount = risk_params.get("risk_amount", 0)
    risk_params["risk_amount"] = round(risk_amount * profile.size_mult, 2)

    # ── Tighten-after timer ──
    if profile.tighten_after_minutes > 0:
        risk_params["gex_tighten_after_minutes"] = profile.tighten_after_minutes

    # ── Store regime info ──
    risk_params["gex_regime"] = profile.to_dict()

    logger.info(
        f"[GEX Regime] {profile.label} (str={profile.regime_strength:.2f}) — "
        f"target×{profile.target_mult:.2f} stop×{profile.stop_mult:.2f} "
        f"trail×{profile.trailing_mult:.2f} size×{profile.size_mult:.2f}"
    )

    return risk_params


def regime_signal_filter(
    profile: RegimeProfile,
    signal_type: str,
) -> Tuple[bool, str]:
    """
    Check if a signal type is compatible with the current GEX regime.

    Doesn't block trades outright — returns (should_trade, note) where
    the note can be logged as a warning. The confluence engine already
    handles alignment scoring, but this provides an explicit advisory.

    Args:
        profile: RegimeProfile from get_regime_profile()
        signal_type: "momentum", "breakout", "fade", "mean_reversion", etc.

    Returns:
        (compatible: bool, note: str)
    """
    trend_signals = {"momentum", "breakout", "trend", "orb_breakout"}
    reversion_signals = {"fade", "mean_reversion", "range", "rejection"}

    is_trend = signal_type.lower() in trend_signals
    is_reversion = signal_type.lower() in reversion_signals

    if profile.regime == "neutral":
        return True, ""

    if profile.regime == "positive" and profile.regime_strength > 0.4:
        if is_trend:
            return False, (
                f"GEX regime warning: Positive GEX ({profile.regime_strength:.0%}) — "
                f"dealers dampening moves, {signal_type} signal has headwind"
            )
        if is_reversion:
            return True, (
                f"GEX regime boost: Positive GEX favors {signal_type} signal"
            )

    if profile.regime == "negative" and profile.regime_strength > 0.4:
        if is_reversion:
            return False, (
                f"GEX regime warning: Negative GEX ({profile.regime_strength:.0%}) — "
                f"dealers amplifying moves, {signal_type} signal has headwind"
            )
        if is_trend:
            return True, (
                f"GEX regime boost: Negative GEX favors {signal_type} signal"
            )

    return True, ""
