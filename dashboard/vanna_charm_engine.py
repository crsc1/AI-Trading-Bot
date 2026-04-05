"""
Vanna & Charm Engine — Second-order dealer flow analysis for 0DTE.

Vanna (∂delta/∂IV) — How dealer delta changes when IV moves:
  - When IV drops (e.g. after CPI release), positive vanna options lose delta
  - Dealers who hedged that delta must unwind → creates buying pressure
  - Negative aggregate vanna + falling IV = bullish dealer flow
  - This is the "IV crush trade" — one of the most reliable 0DTE setups

Charm (∂delta/∂time) — How dealer delta decays over time:
  - As expiration approaches, OTM options lose delta faster
  - Dealers who hedged that delta must unwind → directional flow
  - On 0DTE, charm accelerates dramatically after 1:30 PM ET
  - Charm flows from calls create selling pressure (dealers sell to unhedge)
  - Charm flows from puts create buying pressure (dealers buy to unhedge)
  - This is the PRIMARY driver of 1:30-3:00 PM moves on expiration day

Architecture:
  - Computes vanna/charm from the existing merged chain (Alpaca + ThetaData)
  - No new API calls — same chain data that gex_engine.py uses
  - Produces per-strike and aggregate vanna/charm exposure
  - Scoring functions for confluence integration

Data flow:
  api_routes.py (chain) → vanna_charm_engine.py → confluence.py
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
import math
import logging

logger = logging.getLogger(__name__)

CONTRACT_MULT = 100


@dataclass
class VannaCharmResult:
    """Aggregate vanna & charm exposure analysis."""

    # Vanna exposure
    net_vanna: float = 0.0          # Net dealer vanna (call + put)
    call_vanna: float = 0.0
    put_vanna: float = 0.0
    vanna_regime: str = "neutral"   # "bullish_unwind", "bearish_unwind", "neutral"
    vanna_pressure: float = 0.0     # -1 to +1 directional bias from vanna

    # Charm exposure
    net_charm: float = 0.0          # Net dealer charm (delta decay rate)
    call_charm: float = 0.0
    put_charm: float = 0.0
    charm_regime: str = "neutral"   # "buying_pressure", "selling_pressure", "neutral"
    charm_pressure: float = 0.0     # -1 to +1 directional bias from charm
    charm_acceleration: float = 0.0 # How fast charm is increasing (0DTE accelerates)

    # Key levels
    vanna_flip_strike: float = 0.0  # Strike where vanna exposure flips sign
    max_charm_strike: float = 0.0   # Strike with highest charm impact

    # Per-strike data
    strike_vanna: Dict[float, float] = field(default_factory=dict)
    strike_charm: Dict[float, float] = field(default_factory=dict)

    # Time context
    hours_to_expiry: float = 0.0
    is_charm_acceleration_zone: bool = False  # True if past 1:30 PM ET

    spot: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "net_vanna": round(self.net_vanna, 2),
            "call_vanna": round(self.call_vanna, 2),
            "put_vanna": round(self.put_vanna, 2),
            "vanna_regime": self.vanna_regime,
            "vanna_pressure": round(self.vanna_pressure, 4),
            "net_charm": round(self.net_charm, 2),
            "call_charm": round(self.call_charm, 2),
            "put_charm": round(self.put_charm, 2),
            "charm_regime": self.charm_regime,
            "charm_pressure": round(self.charm_pressure, 4),
            "charm_acceleration": round(self.charm_acceleration, 4),
            "vanna_flip_strike": self.vanna_flip_strike,
            "max_charm_strike": self.max_charm_strike,
            "hours_to_expiry": round(self.hours_to_expiry, 3),
            "is_charm_acceleration_zone": self.is_charm_acceleration_zone,
            "spot": self.spot,
            "strike_count": len(self.strike_vanna),
        }


def calculate_vanna_charm(
    calls: List[Dict],
    puts: List[Dict],
    spot: float,
    hours_to_expiry: Optional[float] = None,
) -> VannaCharmResult:
    """
    Compute aggregate vanna and charm exposure from options chain.

    Vanna approximation (from chain data):
      vanna ≈ vega / spot × (1 - d1²/sigma²)
      Simplified: vanna ≈ delta_change_per_IV_change
      Practical: We use the chain's delta and vega to estimate vanna per strike

    Charm approximation:
      charm = -∂delta/∂t ≈ -theta_delta_component
      For calls: charm ≈ -(r × e^(-q×T) × N(d1) - theta_correction)
      Simplified: charm ≈ delta × (1/T) for OTM options
      As T→0 (0DTE), charm explodes for near-ATM options

    Args:
        calls: List of call option dicts from merged chain
        puts: List of put option dicts from merged chain
        spot: Current underlying price
        hours_to_expiry: Override hours to expiry (auto-calculated if None)

    Returns:
        VannaCharmResult with aggregate and per-strike analysis
    """
    result = VannaCharmResult(spot=spot)

    if not spot or spot <= 0:
        return result

    # Compute hours to expiry
    if hours_to_expiry is None:
        hours_to_expiry = _estimate_hours_to_expiry()
    result.hours_to_expiry = hours_to_expiry

    # Check if we're in charm acceleration zone (past 1:30 PM ET)
    result.is_charm_acceleration_zone = _is_charm_acceleration_zone()

    # Time to expiry in years (minimum 1 minute)
    t_years = max(hours_to_expiry / (365.25 * 24), 1 / (365.25 * 24 * 60))

    # Process calls
    for opt in calls:
        strike = opt.get("strike", 0)
        oi = opt.get("open_interest", 0) or 0
        delta = opt.get("delta", 0) or 0
        gamma = opt.get("gamma", 0) or 0
        vega = opt.get("vega", 0) or 0
        iv = opt.get("iv", 0) or 0

        if not strike or strike <= 0 or oi <= 0:
            continue

        # Compute per-contract vanna and charm
        v = _compute_vanna(delta, gamma, vega, iv, spot, strike, t_years, "call")
        c = _compute_charm(delta, gamma, t_years, spot, strike, iv, "call")

        # Dealer exposure: dealers are SHORT calls → flip sign
        # Dealer vanna = -OI × vanna × contract_mult
        dealer_vanna = -oi * v * CONTRACT_MULT
        dealer_charm = -oi * c * CONTRACT_MULT

        result.call_vanna += dealer_vanna
        result.call_charm += dealer_charm
        result.strike_vanna[strike] = result.strike_vanna.get(strike, 0) + dealer_vanna
        result.strike_charm[strike] = result.strike_charm.get(strike, 0) + dealer_charm

    # Process puts
    for opt in puts:
        strike = opt.get("strike", 0)
        oi = opt.get("open_interest", 0) or 0
        delta = opt.get("delta", 0) or 0
        gamma = opt.get("gamma", 0) or 0
        vega = opt.get("vega", 0) or 0
        iv = opt.get("iv", 0) or 0

        if not strike or strike <= 0 or oi <= 0:
            continue

        v = _compute_vanna(delta, gamma, vega, iv, spot, strike, t_years, "put")
        c = _compute_charm(delta, gamma, t_years, spot, strike, iv, "put")

        # Dealer exposure: dealers are SHORT puts → flip sign
        dealer_vanna = -oi * v * CONTRACT_MULT
        dealer_charm = -oi * c * CONTRACT_MULT

        result.put_vanna += dealer_vanna
        result.put_charm += dealer_charm
        result.strike_vanna[strike] = result.strike_vanna.get(strike, 0) + dealer_vanna
        result.strike_charm[strike] = result.strike_charm.get(strike, 0) + dealer_charm

    # Aggregate
    result.net_vanna = result.call_vanna + result.put_vanna
    result.net_charm = result.call_charm + result.put_charm

    # Determine vanna regime
    result.vanna_regime, result.vanna_pressure = _classify_vanna_regime(result)

    # Determine charm regime
    result.charm_regime, result.charm_pressure, result.charm_acceleration = _classify_charm_regime(result, t_years)

    # Find vanna flip strike
    result.vanna_flip_strike = _find_flip_strike(result.strike_vanna, spot)

    # Find max charm strike
    if result.strike_charm:
        result.max_charm_strike = max(
            result.strike_charm.keys(),
            key=lambda k: abs(result.strike_charm[k])
        )

    return result


def _compute_vanna(
    delta: float, gamma: float, vega: float, iv: float,
    spot: float, strike: float, t_years: float, opt_type: str,
) -> float:
    """
    Estimate vanna (∂delta/∂sigma) for a single option.

    Vanna = vega / spot × (1 - d1 / sigma)
    Approximation when we have delta/gamma/vega from chain:
      vanna ≈ vega × (1 - delta²) / (spot × iv × sqrt(T))

    For practical purposes: vanna tells us how much delta shifts
    when IV changes by 1 point.
    """
    if not iv or iv <= 0 or not vega:
        return 0.0

    try:
        sqrt_t = math.sqrt(t_years) if t_years > 0 else 0.001

        # d1 approximation from delta
        # For calls: N(d1) ≈ delta, so d1 ≈ N_inv(delta)
        # For puts: N(d1) ≈ delta + 1, so d1 ≈ N_inv(delta + 1)
        # Simplified: use vega / (spot × iv × sqrt_t) as vanna proxy
        if spot > 0 and sqrt_t > 0:
            vanna = vega / (spot * iv * sqrt_t)

            # Flip sign for puts (put vanna has opposite directional impact)
            if opt_type == "put":
                vanna = -abs(vanna)

            return vanna
        return 0.0

    except (ValueError, ZeroDivisionError):
        return 0.0


def _compute_charm(
    delta: float, gamma: float, t_years: float,
    spot: float, strike: float, iv: float, opt_type: str,
) -> float:
    """
    Estimate charm (∂delta/∂time) for a single option.

    Charm = -∂delta/∂t
    Approximation: charm ≈ -gamma × spot × iv / (2 × sqrt(T))
      + correction for drift

    Key behavior:
      - Near ATM: charm is maximum (delta changing fastest)
      - OTM: charm pulls delta toward 0 (options dying)
      - ITM: charm pulls delta toward ±1 (options becoming stock)
      - As T→0: charm explodes (0DTE afternoon effect)
    """
    if not gamma or t_years <= 0:
        return 0.0

    try:
        sqrt_t = math.sqrt(t_years)

        # Charm ≈ -gamma × S × sigma / (2 × sqrt(T))
        # This captures the delta-decay component
        sigma = iv if iv and iv > 0 else 0.20

        charm = -gamma * spot * sigma / (2 * sqrt_t)

        # For 0DTE, add acceleration factor when T < 1 hour
        if t_years < 1 / (365.25 * 24):  # Less than 1 hour
            # Charm accelerates hyperbolically as expiry approaches
            accel = min(1.0 / (t_years * 365.25 * 24), 10.0)  # Cap at 10x
            charm *= (1 + accel * 0.1)

        return charm

    except (ValueError, ZeroDivisionError):
        return 0.0


def _classify_vanna_regime(result: VannaCharmResult) -> Tuple[str, float]:
    """
    Classify vanna flow regime and directional pressure.

    When aggregate dealer vanna is negative and IV is falling:
      → Dealers unwind delta hedges → buying pressure → bullish
    When aggregate dealer vanna is positive and IV is rising:
      → Dealers add delta hedges → selling pressure → bearish
    """
    net = result.net_vanna
    total_abs = abs(result.call_vanna) + abs(result.put_vanna)

    if total_abs < 1e-6:
        return "neutral", 0.0

    # Normalize pressure to -1..+1
    # Positive net_vanna = dealers have positive vanna exposure
    #   → If IV drops, they lose delta → must buy → bullish
    # Negative net_vanna = dealers have negative vanna exposure
    #   → If IV drops, they gain delta → must sell → bearish

    pressure = net / total_abs  # Normalized -1 to +1
    pressure = max(-1.0, min(1.0, pressure))

    if pressure > 0.2:
        regime = "bullish_unwind"  # IV drop → dealer buying
    elif pressure < -0.2:
        regime = "bearish_unwind"  # IV drop → dealer selling
    else:
        regime = "neutral"

    return regime, pressure


def _classify_charm_regime(
    result: VannaCharmResult, t_years: float
) -> Tuple[str, float, float]:
    """
    Classify charm flow regime.

    When net dealer charm is positive → delta is decaying toward calls
      → Dealers must sell underlying to unhedge → selling pressure
    When net dealer charm is negative → delta is decaying toward puts
      → Dealers must buy underlying to unhedge → buying pressure

    Charm acceleration = how fast this is changing (critical for 0DTE PM)
    """
    net = result.net_charm
    total_abs = abs(result.call_charm) + abs(result.put_charm)

    if total_abs < 1e-6:
        return "neutral", 0.0, 0.0

    pressure = net / total_abs
    pressure = max(-1.0, min(1.0, pressure))

    # Acceleration factor: charm impact grows as T shrinks
    # For 0DTE: T < 6.5/8766 ≈ 0.00074 years
    acceleration = 0.0
    if t_years > 0:
        hours = t_years * 365.25 * 24
        if hours < 4:  # Less than 4 hours to expiry
            acceleration = 1.0 / max(hours, 0.1)  # Inverse of hours
            acceleration = min(acceleration, 10.0)  # Cap at 10

    if pressure > 0.15:
        regime = "selling_pressure"  # Call delta decay → dealer selling
    elif pressure < -0.15:
        regime = "buying_pressure"   # Put delta decay → dealer buying
    else:
        regime = "neutral"

    return regime, pressure, acceleration


def _find_flip_strike(strike_data: Dict[float, float], spot: float) -> float:
    """Find strike where vanna exposure flips sign (near spot)."""
    if not strike_data:
        return 0.0

    sorted_strikes = sorted(strike_data.keys())
    # Look for sign change near spot
    best_flip = 0.0
    min_dist = float("inf")

    for i in range(len(sorted_strikes) - 1):
        s1, s2 = sorted_strikes[i], sorted_strikes[i + 1]
        v1, v2 = strike_data[s1], strike_data[s2]

        if v1 * v2 < 0:  # Sign change
            # Linear interpolation
            if abs(v2 - v1) > 1e-10:
                flip = s1 + (s2 - s1) * abs(v1) / abs(v2 - v1)
            else:
                flip = (s1 + s2) / 2

            dist = abs(flip - spot)
            if dist < min_dist:
                min_dist = dist
                best_flip = flip

    return round(best_flip, 2)


def _estimate_hours_to_expiry() -> float:
    """Estimate hours to market close (4:00 PM ET) for 0DTE."""
    try:
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
    except ImportError:
        ET = timezone(timedelta(hours=-4))

    now_et = datetime.now(ET)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)

    if now_et >= market_close:
        return 0.0  # Market closed

    remaining = (market_close - now_et).total_seconds() / 3600
    return max(remaining, 1 / 60)  # Minimum 1 minute


def _is_charm_acceleration_zone() -> bool:
    """Check if current time is past 1:30 PM ET (charm acceleration zone)."""
    try:
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
    except ImportError:
        ET = timezone(timedelta(hours=-4))

    now_et = datetime.now(ET)
    return now_et.hour >= 13 and now_et.minute >= 30 or now_et.hour >= 14


# ── Scoring functions for confluence integration ──

def score_vanna_alignment(
    vc: VannaCharmResult,
    signal_direction: str,
) -> Tuple[float, str]:
    """
    Score vanna alignment with proposed trade direction.

    Max 0.75 points (part of expanded confluence scoring).

    Args:
        vc: VannaCharmResult from calculate_vanna_charm()
        signal_direction: "BUY_CALL" or "BUY_PUT"

    Returns:
        (score, explanation) where score is -0.25 to 0.75
    """
    is_bullish = signal_direction == "BUY_CALL"
    pressure = vc.vanna_pressure

    if is_bullish and pressure > 0.3:
        score = 0.75
        explain = f"Strong vanna support: dealer buying pressure ({vc.vanna_regime})"
    elif is_bullish and pressure > 0.1:
        score = 0.4
        explain = "Moderate vanna support: mild bullish dealer flow"
    elif not is_bullish and pressure < -0.3:
        score = 0.75
        explain = f"Strong vanna support: dealer selling pressure ({vc.vanna_regime})"
    elif not is_bullish and pressure < -0.1:
        score = 0.4
        explain = "Moderate vanna support: mild bearish dealer flow"
    elif abs(pressure) < 0.1:
        score = 0.0
        explain = "Vanna neutral — no directional dealer flow"
    else:
        score = -0.25
        explain = "Vanna opposing: dealer flow against trade direction"

    return score, explain


def score_charm_pressure(
    vc: VannaCharmResult,
    signal_direction: str,
) -> Tuple[float, str]:
    """
    Score charm alignment with proposed trade direction.

    Max 0.75 points. Charm weight increases after 1:30 PM ET
    (when it becomes the dominant 0DTE force).

    Returns:
        (score, explanation) where score is -0.25 to 0.75
    """
    is_bullish = signal_direction == "BUY_CALL"
    pressure = vc.charm_pressure
    in_accel = vc.is_charm_acceleration_zone

    # Charm is more important after 1:30 PM
    weight_mult = 1.5 if in_accel else 1.0

    if is_bullish and vc.charm_regime == "buying_pressure":
        base = 0.5 if abs(pressure) > 0.3 else 0.3
        score = min(base * weight_mult, 0.75)
        explain = f"Charm buying pressure {'(accelerating!)' if in_accel else ''}: dealer delta decay → buying"
    elif not is_bullish and vc.charm_regime == "selling_pressure":
        base = 0.5 if abs(pressure) > 0.3 else 0.3
        score = min(base * weight_mult, 0.75)
        explain = f"Charm selling pressure {'(accelerating!)' if in_accel else ''}: dealer delta decay → selling"
    elif vc.charm_regime == "neutral":
        score = 0.0
        explain = "Charm neutral — balanced delta decay"
    else:
        score = -0.25 * weight_mult
        score = max(score, -0.25)
        explain = "Charm opposing: dealer flow against trade direction"

    return round(score, 3), explain
