"""
GEX/DEX Engine — Gamma & Delta Exposure Analysis.

Calculates aggregate dealer positioning from options chain data.
Consumes the options chain from api_routes.py (ThetaData quotes + OI + first_order Greeks).
Does NOT call any external APIs — purely analytical math on existing data.

Key concepts:
  GEX (Gamma Exposure):
    - Measures how much dealers need to hedge per $1 move in underlying
    - Positive GEX = dealers short gamma → they dampen moves (buy dips, sell rips)
    - Negative GEX = dealers long gamma → they amplify moves
    - Call Wall = strike with highest call GEX → resistance ceiling
    - Put Wall = strike with highest put GEX → support floor

  DEX (Delta Exposure):
    - Measures aggregate dealer delta (directional exposure)
    - DEX flip level = price where aggregate dealer delta crosses zero
    - Above flip → dealers sell (resistance), below flip → dealers buy (support)

  Gamma Profile:
    - Per-strike GEX shows where dealers concentrate hedging activity
    - Cluster of high GEX = "magnet" zone where price gravitates

Data flow:
  api_routes.py (ThetaData chain + first_order Greeks) → gex_engine.py → confluence.py
  No interference with Alpaca order flow or execution.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple
import logging

logger = logging.getLogger(__name__)

# Contract multiplier for equity options
CONTRACT_MULT = 100


@dataclass
class GEXResult:
    """Complete GEX/DEX analysis for a single expiration."""

    # Aggregate metrics
    net_gex: float = 0.0            # Net gamma exposure ($)
    call_gex: float = 0.0           # Total call GEX
    put_gex: float = 0.0            # Total put GEX
    net_dex: float = 0.0            # Net delta exposure
    call_dex: float = 0.0
    put_dex: float = 0.0

    # Key levels
    call_wall: float = 0.0          # Strike with highest call GEX → resistance
    put_wall: float = 0.0           # Strike with highest (abs) put GEX → support
    gex_flip_level: float = 0.0     # Price where GEX transitions pos→neg
    max_gamma_strike: float = 0.0   # Strike with highest total gamma concentration

    # Regime
    regime: str = "neutral"         # "positive" (range), "negative" (trend), "neutral"
    regime_strength: float = 0.0    # 0-1 how strong the regime is

    # Per-strike data for visualization
    strike_gex: Dict[float, float] = field(default_factory=dict)
    strike_dex: Dict[float, float] = field(default_factory=dict)

    # Spot price used for calculation
    spot: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "net_gex": round(self.net_gex, 2),
            "call_gex": round(self.call_gex, 2),
            "put_gex": round(self.put_gex, 2),
            "net_dex": round(self.net_dex, 2),
            "call_dex": round(self.call_dex, 2),
            "put_dex": round(self.put_dex, 2),
            "call_wall": self.call_wall,
            "put_wall": self.put_wall,
            "gex_flip_level": self.gex_flip_level,
            "max_gamma_strike": self.max_gamma_strike,
            "regime": self.regime,
            "regime_strength": round(self.regime_strength, 3),
            "spot": self.spot,
            "strike_gex": {str(k): round(v, 2) for k, v in self.strike_gex.items()},
            "strike_dex": {str(k): round(v, 2) for k, v in self.strike_dex.items()},
        }


def calculate_gex(
    calls: List[Dict],
    puts: List[Dict],
    spot: float,
) -> GEXResult:
    """
    Calculate GEX/DEX from options chain data.

    Expects the merged chain format from api_routes.py where each entry has:
      - strike: float
      - gamma: float (from ThetaData, may be None)
      - delta: float (from ThetaData, may be None)
      - open_interest: int
      - volume: int (optional, used for weighting)

    The chain data comes from the existing /api/options/chain endpoint
    which merges Alpaca pricing with ThetaData Greeks.
    This function does NOT call any external APIs.

    Args:
        calls: List of call option entries from chain
        puts: List of put option entries from chain
        spot: Current underlying price (from Alpaca quote)

    Returns:
        GEXResult with all computed metrics
    """
    result = GEXResult(spot=spot)

    if not spot or spot <= 0:
        return result

    # ── Per-strike GEX/DEX ──
    call_gex_by_strike: Dict[float, float] = {}
    put_gex_by_strike: Dict[float, float] = {}
    call_dex_by_strike: Dict[float, float] = {}
    put_dex_by_strike: Dict[float, float] = {}

    for c in calls:
        strike = c.get("strike", 0)
        gamma = c.get("gamma")
        delta_val = c.get("delta")
        oi = c.get("open_interest", 0) or 0

        if not strike or oi <= 0:
            continue

        if gamma is not None and gamma != 0:
            # GEX formula: OI × gamma × spot² × 0.01 × contract_multiplier
            # The 0.01 converts from per-$1 move to per-1% move (standard convention)
            # Dealers are typically SHORT calls → positive GEX (they buy on dips)
            gex = oi * gamma * spot * spot * 0.01 * CONTRACT_MULT
            call_gex_by_strike[strike] = gex
            result.call_gex += gex

        if delta_val is not None:
            # DEX: OI × delta × contract_multiplier
            # Dealers SHORT calls → negative delta exposure (they hedge by buying stock)
            dex = oi * delta_val * CONTRACT_MULT
            call_dex_by_strike[strike] = dex
            result.call_dex += dex

    for p in puts:
        strike = p.get("strike", 0)
        gamma = p.get("gamma")
        delta_val = p.get("delta")
        oi = p.get("open_interest", 0) or 0

        if not strike or oi <= 0:
            continue

        if gamma is not None and gamma != 0:
            # Dealers SHORT puts → negative GEX (they sell on rallies, amplifying moves)
            # Put gamma contribution is negative from dealer perspective
            gex = -oi * gamma * spot * spot * 0.01 * CONTRACT_MULT
            put_gex_by_strike[strike] = gex
            result.put_gex += gex

        if delta_val is not None:
            # Dealers SHORT puts → positive delta exposure (they hedge by selling stock)
            # Put delta is negative, dealer is short → -1 × negative = positive
            dex = -oi * delta_val * CONTRACT_MULT
            put_dex_by_strike[strike] = dex
            result.put_dex += dex

    # ── Net aggregates ──
    result.net_gex = result.call_gex + result.put_gex
    result.net_dex = result.call_dex + result.put_dex

    # ── Combined per-strike ──
    all_strikes = sorted(set(call_gex_by_strike.keys()) | set(put_gex_by_strike.keys()))
    for s in all_strikes:
        result.strike_gex[s] = call_gex_by_strike.get(s, 0) + put_gex_by_strike.get(s, 0)

    all_dex_strikes = sorted(set(call_dex_by_strike.keys()) | set(put_dex_by_strike.keys()))
    for s in all_dex_strikes:
        result.strike_dex[s] = call_dex_by_strike.get(s, 0) + put_dex_by_strike.get(s, 0)

    # ── Call Wall (highest positive GEX strike) ──
    if call_gex_by_strike:
        result.call_wall = max(call_gex_by_strike, key=call_gex_by_strike.get)

    # ── Put Wall (highest absolute negative GEX strike) ──
    if put_gex_by_strike:
        result.put_wall = min(put_gex_by_strike, key=put_gex_by_strike.get)

    # ── Max gamma strike (highest total |GEX| concentration) ──
    if result.strike_gex:
        result.max_gamma_strike = max(result.strike_gex, key=lambda s: abs(result.strike_gex[s]))

    # ── GEX Flip Level ──
    # Find strike where cumulative GEX crosses zero (above = positive GEX regime, below = negative)
    result.gex_flip_level = _find_flip_level(result.strike_gex, spot)

    # ── Regime classification ──
    if result.net_gex > 0:
        result.regime = "positive"
    elif result.net_gex < 0:
        result.regime = "negative"
    else:
        result.regime = "neutral"

    # Regime strength: how far from neutral
    # Normalize by total absolute GEX
    total_abs = abs(result.call_gex) + abs(result.put_gex)
    if total_abs > 0:
        result.regime_strength = min(1.0, abs(result.net_gex) / total_abs)

    return result


def _find_flip_level(strike_gex: Dict[float, float], spot: float) -> float:
    """
    Find the price level where GEX flips from positive to negative.
    Uses linear interpolation between strikes near the zero crossing.
    """
    if not strike_gex:
        return spot

    sorted_strikes = sorted(strike_gex.keys())
    if len(sorted_strikes) < 2:
        return spot

    # Walk from low to high, find where cumulative GEX crosses zero
    cumulative = 0.0
    prev_strike = sorted_strikes[0]
    prev_cum = 0.0

    for s in sorted_strikes:
        cumulative += strike_gex[s]
        if prev_cum <= 0 < cumulative or prev_cum >= 0 > cumulative:
            # Zero crossing between prev_strike and s
            if abs(cumulative - prev_cum) > 0:
                # Linear interpolation
                frac = abs(prev_cum) / abs(cumulative - prev_cum)
                return round(prev_strike + frac * (s - prev_strike), 2)
        prev_strike = s
        prev_cum = cumulative

    # No crossing found — return spot
    return spot


def score_gex_alignment(
    gex: GEXResult,
    signal_direction: str,
    is_trend_signal: bool = True,
) -> Tuple[float, str]:
    """
    Score how well the GEX regime aligns with the proposed signal.

    Args:
        gex: GEXResult from calculate_gex()
        signal_direction: "bullish" or "bearish"
        is_trend_signal: True if signal expects a move (breakout),
                        False if signal expects mean reversion (fade)

    Returns:
        (score, explanation) where score is -0.5 to 1.5
    """
    if gex.regime == "neutral" or gex.regime_strength < 0.1:
        return 0.0, "GEX neutral — no dealer positioning edge"

    # ── Negative GEX + Trend Signal = Dealers amplify your move ──
    if gex.regime == "negative" and is_trend_signal:
        score = min(1.5, 0.5 + gex.regime_strength)
        return score, (
            f"Negative GEX ({gex.regime_strength:.0%} strength) — "
            f"dealers amplifying moves, favorable for trend signal"
        )

    # ── Positive GEX + Mean Reversion = Dealers push price back to range ──
    if gex.regime == "positive" and not is_trend_signal:
        score = min(1.5, 0.5 + gex.regime_strength)
        return score, (
            f"Positive GEX ({gex.regime_strength:.0%} strength) — "
            f"dealers dampening moves, favorable for mean reversion"
        )

    # ── Positive GEX + Trend Signal = Dealers fight your trade ──
    if gex.regime == "positive" and is_trend_signal:
        score = max(-0.5, -0.3 * gex.regime_strength)
        return score, (
            f"Positive GEX ({gex.regime_strength:.0%} strength) — "
            f"dealers dampening moves, headwind for trend signal"
        )

    # ── Negative GEX + Mean Reversion = Dealers push past your fade ──
    if gex.regime == "negative" and not is_trend_signal:
        score = max(-0.5, -0.3 * gex.regime_strength)
        return score, (
            f"Negative GEX ({gex.regime_strength:.0%} strength) — "
            f"dealers amplifying moves, headwind for fade signal"
        )

    return 0.0, "GEX inconclusive"


def score_dex_levels(
    gex: GEXResult,
    signal_direction: str,
) -> Tuple[float, str]:
    """
    Score signal alignment with DEX levels (call wall / put wall boundaries).

    Args:
        gex: GEXResult from calculate_gex()
        signal_direction: "bullish" or "bearish"

    Returns:
        (score, explanation) where score is -0.3 to 1.0
    """
    spot = gex.spot
    if spot <= 0 or (gex.call_wall <= 0 and gex.put_wall <= 0):
        return 0.0, "Insufficient DEX data"

    call_wall = gex.call_wall
    put_wall = gex.put_wall
    explanation_parts = []

    # Distance to walls as fraction of the range
    wall_range = call_wall - put_wall if call_wall > put_wall else 1.0
    dist_to_call = (call_wall - spot) / wall_range if wall_range > 0 else 0
    dist_to_put = (spot - put_wall) / wall_range if wall_range > 0 else 0

    score = 0.0

    if signal_direction == "bullish":
        # Bullish near put wall = support (good), bullish near call wall = resistance (bad)
        if dist_to_put < 0.2 and put_wall > 0:
            score += 0.5
            explanation_parts.append(f"near put wall ${put_wall:.0f} (support)")
        if dist_to_call < 0.2 and call_wall > 0:
            score -= 0.3
            explanation_parts.append(f"near call wall ${call_wall:.0f} (resistance)")

        # Signal pushes toward max pain / center = favorable
        if 0.3 < dist_to_put < 0.7:
            score += 0.3
            explanation_parts.append("price in dealer neutral zone")

    elif signal_direction == "bearish":
        # Bearish near call wall = resistance bounce (good), bearish near put wall (bad)
        if dist_to_call < 0.2 and call_wall > 0:
            score += 0.5
            explanation_parts.append(f"near call wall ${call_wall:.0f} (resistance)")
        if dist_to_put < 0.2 and put_wall > 0:
            score -= 0.3
            explanation_parts.append(f"near put wall ${put_wall:.0f} (support)")

        if 0.3 < dist_to_call < 0.7:
            score += 0.3
            explanation_parts.append("price in dealer neutral zone")

    # Clamp
    score = max(-0.3, min(1.0, score))
    explanation = f"DEX: {', '.join(explanation_parts)}" if explanation_parts else "DEX neutral"

    return score, explanation
