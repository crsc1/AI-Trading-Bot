"""
IV vs Realized Vol Analyzer — Step 10 of Money Machine Plan.

Compares implied volatility (from options chain) to realized volatility
(from underlying price bars) to determine whether options are cheap or
expensive. This is the #1 edge in options trading.

Key insight:
  IV > RV → Options are EXPENSIVE (overpriced)
    → Market expects bigger moves than are actually happening
    → For long options: tighter targets (theta headwind stronger)
    → Shorter hold times (time decay eating premium faster)
    → Reduce size (paying premium above fair value)
    → Ideal for selling premium (when we support spreads)

  IV < RV → Options are CHEAP (underpriced)
    → Market expects smaller moves than are actually happening
    → For long options: wider targets (gamma tailwind — moves > priced in)
    → Can hold longer (getting moves for less premium)
    → Can size up (buying below fair value)
    → Ideal for buying premium aggressively

  IV ≈ RV → Fair value
    → Standard parameters, no edge from vol mismatch

Metrics:
  iv_rv_ratio:     atm_iv / realized_vol (>1 = expensive, <1 = cheap)
  vol_premium:     (atm_iv - realized_vol) in vol points
  vol_regime:      "expensive", "cheap", "fair"
  vol_percentile:  where current ratio sits in recent history (0-100)

Data sources:
  ATM IV:        options_analytics.py → atm_iv (from ThetaData chain)
  Realized Vol:  market_levels.py → realized_vol (from 1m bars, annualized)
  IV Rank:       options_analytics.py → iv_rank (52-week context)
"""

import logging
import math
import statistics
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Thresholds ──────────────────────────────────────────────────────────────

# IV/RV ratio thresholds
EXPENSIVE_THRESHOLD = 1.20   # IV 20%+ above RV → options expensive
CHEAP_THRESHOLD = 0.80       # IV 20%+ below RV → options cheap
VERY_EXPENSIVE_THRESHOLD = 1.50  # IV 50%+ above RV → very expensive
VERY_CHEAP_THRESHOLD = 0.65      # IV 35%+ below RV → very cheap

# Minimum values to compute meaningful ratio
MIN_IV = 5.0       # 5% annualized IV minimum
MIN_RV = 3.0       # 3% annualized RV minimum

# Risk parameter multipliers per vol regime
VOL_REGIME_PARAMS = {
    "very_expensive": {
        "target_mult": 0.70,       # 30% tighter targets
        "stop_mult": 0.85,         # 15% tighter stops
        "hold_mult": 0.65,         # 35% shorter holds
        "size_mult": 0.80,         # 20% smaller size
        "trailing_mult": 0.80,     # Tighter trailing
    },
    "expensive": {
        "target_mult": 0.85,       # 15% tighter
        "stop_mult": 0.92,
        "hold_mult": 0.80,
        "size_mult": 0.90,
        "trailing_mult": 0.90,
    },
    "fair": {
        "target_mult": 1.0,
        "stop_mult": 1.0,
        "hold_mult": 1.0,
        "size_mult": 1.0,
        "trailing_mult": 1.0,
    },
    "cheap": {
        "target_mult": 1.15,       # 15% wider targets
        "stop_mult": 1.05,
        "hold_mult": 1.20,         # 20% longer holds
        "size_mult": 1.10,         # 10% larger size
        "trailing_mult": 1.10,
    },
    "very_cheap": {
        "target_mult": 1.30,       # 30% wider targets
        "stop_mult": 1.10,
        "hold_mult": 1.35,         # 35% longer holds
        "size_mult": 1.20,         # 20% larger size
        "trailing_mult": 1.15,
    },
}


# ─── Data Structure ──────────────────────────────────────────────────────────

@dataclass
class VolAnalysis:
    """Result of IV vs Realized Vol comparison."""

    atm_iv: float = 0.0           # Current ATM implied volatility (annualized %)
    realized_vol: float = 0.0     # Current intraday realized vol (annualized %)
    iv_rv_ratio: float = 1.0      # atm_iv / realized_vol
    vol_premium: float = 0.0      # atm_iv - realized_vol (vol points)

    vol_regime: str = "fair"      # "very_expensive", "expensive", "fair", "cheap", "very_cheap"
    iv_rank: float = 50.0         # 0-100 from IV history
    data_quality: str = "good"    # "good", "partial", "insufficient"

    # Multi-timeframe realized vol
    rv_intraday: float = 0.0      # From 1m bars (same session)
    rv_5d: float = 0.0            # 5-day realized vol (from daily bars)
    rv_20d: float = 0.0           # 20-day realized vol (from daily bars)
    vol_term_structure: str = "normal"  # "contango" (rv5 < rv20), "backwardation" (rv5 > rv20)

    # Risk parameter multipliers
    target_mult: float = 1.0
    stop_mult: float = 1.0
    hold_mult: float = 1.0
    size_mult: float = 1.0
    trailing_mult: float = 1.0

    detail: str = ""

    def to_dict(self) -> Dict:
        return {
            "atm_iv": round(self.atm_iv, 2),
            "realized_vol": round(self.realized_vol, 2),
            "iv_rv_ratio": round(self.iv_rv_ratio, 3),
            "vol_premium": round(self.vol_premium, 2),
            "vol_regime": self.vol_regime,
            "iv_rank": round(self.iv_rank, 1),
            "data_quality": self.data_quality,
            "rv_intraday": round(self.rv_intraday, 2),
            "rv_5d": round(self.rv_5d, 2),
            "rv_20d": round(self.rv_20d, 2),
            "vol_term_structure": self.vol_term_structure,
            "target_mult": round(self.target_mult, 3),
            "stop_mult": round(self.stop_mult, 3),
            "hold_mult": round(self.hold_mult, 3),
            "size_mult": round(self.size_mult, 3),
            "trailing_mult": round(self.trailing_mult, 3),
            "detail": self.detail,
        }


# ─── Core Analysis ───────────────────────────────────────────────────────────

def compute_realized_vol_daily(daily_bars: List[Dict], window: int = 20) -> float:
    """
    Compute annualized realized volatility from daily bars.

    Uses log returns × sqrt(252) for annualization.
    Requires at least `window` bars.

    Args:
        daily_bars: List of daily OHLCV bars (need 'close' or 'c' key)
        window: Number of bars for calculation (default 20 = ~1 month)

    Returns:
        Annualized realized vol in %, or 0 if insufficient data
    """
    closes = []
    for bar in daily_bars:
        c = bar.get("close") or bar.get("c", 0)
        if c and c > 0:
            closes.append(c)

    if len(closes) < max(5, window):
        return 0.0

    # Use last `window` closes
    closes = closes[-window:]
    returns = []
    for i in range(1, len(closes)):
        returns.append(math.log(closes[i] / closes[i - 1]))

    if len(returns) < 4:
        return 0.0

    return round(statistics.stdev(returns) * math.sqrt(252) * 100, 2)


def analyze_vol(
    atm_iv: float,
    realized_vol: float,
    iv_rank: Optional[float] = None,
    daily_bars: Optional[List[Dict]] = None,
) -> VolAnalysis:
    """
    Compare implied volatility to realized volatility.

    This is the main entry point. Call with ATM IV from options chain
    and realized vol from market levels.

    Args:
        atm_iv: ATM implied volatility (annualized %). Can be decimal
                (e.g. 0.25 = 25%) or percentage (25.0).
        realized_vol: Intraday realized vol (annualized %).
        iv_rank: IV Rank 0-100 from options_analytics (optional context).
        daily_bars: Daily OHLCV bars for multi-timeframe RV (optional).

    Returns:
        VolAnalysis with regime, ratio, and parameter multipliers.
    """
    result = VolAnalysis()

    # Normalize IV to percentage if given as decimal
    if 0 < atm_iv < 1.0:
        atm_iv = atm_iv * 100.0

    result.atm_iv = atm_iv
    result.realized_vol = realized_vol
    result.rv_intraday = realized_vol
    result.iv_rank = iv_rank if iv_rank is not None else 50.0

    # ── Multi-timeframe realized vol ──
    if daily_bars:
        result.rv_5d = compute_realized_vol_daily(daily_bars, window=5)
        result.rv_20d = compute_realized_vol_daily(daily_bars, window=20)

        # Vol term structure
        if result.rv_5d > 0 and result.rv_20d > 0:
            if result.rv_5d > result.rv_20d * 1.15:
                result.vol_term_structure = "backwardation"  # Short-term vol elevated
            elif result.rv_5d < result.rv_20d * 0.85:
                result.vol_term_structure = "contango"  # Short-term vol depressed
            else:
                result.vol_term_structure = "normal"

    # ── Data quality check ──
    if atm_iv < MIN_IV and realized_vol < MIN_RV:
        result.data_quality = "insufficient"
        result.vol_regime = "fair"
        result.detail = f"Insufficient vol data (IV={atm_iv:.1f}%, RV={realized_vol:.1f}%)"
        _apply_params(result)
        return result

    if atm_iv < MIN_IV or realized_vol < MIN_RV:
        result.data_quality = "partial"

    # ── Choose best RV for comparison ──
    # Prefer multi-day RV if available (more stable), fall back to intraday
    best_rv = realized_vol
    rv_source = "intraday"

    if result.rv_5d > MIN_RV:
        # Blend: 60% 5-day, 40% intraday for stability
        best_rv = result.rv_5d * 0.6 + realized_vol * 0.4
        rv_source = "blended (5d+intraday)"
    elif result.rv_20d > MIN_RV:
        best_rv = result.rv_20d * 0.5 + realized_vol * 0.5
        rv_source = "blended (20d+intraday)"

    # ── Compute IV/RV ratio ──
    if best_rv > MIN_RV:
        result.iv_rv_ratio = atm_iv / best_rv
    elif atm_iv > MIN_IV:
        # No good RV data — use IV alone with conservative ratio
        result.iv_rv_ratio = 1.0
        result.data_quality = "partial"
    else:
        result.iv_rv_ratio = 1.0
        result.data_quality = "insufficient"

    result.vol_premium = atm_iv - best_rv

    # ── Classify vol regime ──
    ratio = result.iv_rv_ratio

    if ratio >= VERY_EXPENSIVE_THRESHOLD:
        result.vol_regime = "very_expensive"
    elif ratio >= EXPENSIVE_THRESHOLD:
        result.vol_regime = "expensive"
    elif ratio <= VERY_CHEAP_THRESHOLD:
        result.vol_regime = "very_cheap"
    elif ratio <= CHEAP_THRESHOLD:
        result.vol_regime = "cheap"
    else:
        result.vol_regime = "fair"

    # ── IV Rank context ──
    # High IV Rank + expensive ratio = very strong expensive signal
    # Low IV Rank + cheap ratio = very strong cheap signal
    # Conflicting signals = dampen toward fair
    iv_rank_val = result.iv_rank
    if iv_rank_val is not None:
        if iv_rank_val > 70 and result.vol_regime in ("expensive", "very_expensive"):
            # High IV rank confirms expensive — strengthen
            if result.vol_regime == "expensive":
                result.vol_regime = "very_expensive"
        elif iv_rank_val < 30 and result.vol_regime in ("cheap", "very_cheap"):
            # Low IV rank confirms cheap — strengthen
            if result.vol_regime == "cheap":
                result.vol_regime = "very_cheap"
        elif iv_rank_val < 30 and result.vol_regime in ("expensive", "very_expensive"):
            # Contradiction: IV rank says low but ratio says expensive
            # This means RV is even lower — dampen toward fair
            result.vol_regime = "expensive" if result.vol_regime == "very_expensive" else "fair"
        elif iv_rank_val > 70 and result.vol_regime in ("cheap", "very_cheap"):
            # Contradiction: IV rank says high but ratio says cheap
            # Unusual — RV must be very high — dampen
            result.vol_regime = "cheap" if result.vol_regime == "very_cheap" else "fair"

    # ── Build detail string ──
    detail_parts = [
        f"IV={atm_iv:.1f}% vs RV={best_rv:.1f}% ({rv_source})",
        f"ratio={ratio:.2f}",
        f"regime={result.vol_regime}",
    ]
    if result.vol_term_structure != "normal":
        detail_parts.append(f"term={result.vol_term_structure}")
    if iv_rank_val is not None:
        detail_parts.append(f"IV Rank={iv_rank_val:.0f}%")
    result.detail = " | ".join(detail_parts)

    # ── Apply parameter multipliers ──
    _apply_params(result)

    logger.info(f"[VolAnalyzer] {result.detail}")
    return result


def _apply_params(result: VolAnalysis) -> None:
    """Apply risk parameter multipliers based on vol regime."""
    params = VOL_REGIME_PARAMS.get(result.vol_regime, VOL_REGIME_PARAMS["fair"])
    result.target_mult = params["target_mult"]
    result.stop_mult = params["stop_mult"]
    result.hold_mult = params["hold_mult"]
    result.size_mult = params["size_mult"]
    result.trailing_mult = params["trailing_mult"]


# ─── Confluence Scoring ──────────────────────────────────────────────────────

def score_vol_edge(
    vol: VolAnalysis,
    direction: str,
) -> Tuple[float, str]:
    """
    Score the volatility edge for confluence Factor 23.

    When options are cheap (IV < RV), buying premium has a structural
    edge — the market is underpricing the moves. This confirms any
    directional signal.

    When options are expensive (IV > RV), buying premium has a headwind.
    This doesn't veto the trade but reduces conviction.

    Args:
        vol: VolAnalysis from analyze_vol()
        direction: "bullish", "bearish", "BUY_CALL", "BUY_PUT"

    Returns:
        (score, detail) where score is -0.30 to +0.75
    """
    if vol.data_quality == "insufficient":
        return 0.0, "IV/RV data insufficient"

    regime = vol.vol_regime
    score = 0.0
    details = []

    # ── Base score from regime ──
    if regime == "very_cheap":
        score = 0.60
        details.append("Options very cheap — strong gamma edge for long premium")
    elif regime == "cheap":
        score = 0.35
        details.append("Options cheap — gamma working for long premium")
    elif regime == "very_expensive":
        score = -0.25
        details.append("Options very expensive — theta headwind for long premium")
    elif regime == "expensive":
        score = -0.12
        details.append("Options expensive — mild theta headwind")
    else:
        score = 0.0
        details.append("Options fairly priced")

    # ── Vol term structure bonus ──
    if vol.vol_term_structure == "backwardation" and regime in ("cheap", "very_cheap"):
        # Short-term vol rising + cheap IV = explosive move likely underpriced
        score += 0.15
        details.append("Vol backwardation confirms cheap options")
    elif vol.vol_term_structure == "contango" and regime in ("expensive", "very_expensive"):
        # Short-term vol falling + expensive IV = options even more overpriced
        score -= 0.05
        details.append("Vol contango confirms expensive options")

    # Clamp
    score = max(-0.30, min(0.75, score))

    return score, " | ".join(details)


def apply_vol_to_risk(
    risk_params: Dict,
    vol: VolAnalysis,
) -> Dict:
    """
    Apply IV vs RV vol analysis to risk/exit parameters.

    Called after calculate_risk() and apply_regime_to_risk() to layer
    vol-based adjustments on top.

    Args:
        risk_params: Dict from calculate_risk()
        vol: VolAnalysis from analyze_vol()

    Returns:
        Modified risk_params dict
    """
    if vol.data_quality == "insufficient":
        risk_params["vol_analysis"] = vol.to_dict()
        return risk_params

    # Save pre-vol values
    risk_params["_pre_vol_target"] = risk_params.get("target_price", 0)
    risk_params["_pre_vol_trailing"] = risk_params.get("trailing_stop_pct", 0)

    # ── Adjust target and stop distances ──
    target_price = risk_params.get("target_price", 0)
    stop_price = risk_params.get("stop_price", 0)

    if target_price > 0 and stop_price > 0:
        entry_est = (target_price + stop_price) / 2
        if entry_est > 0:
            target_dist = target_price - entry_est
            stop_dist = entry_est - stop_price

            new_target = entry_est + target_dist * vol.target_mult
            new_stop = entry_est - stop_dist * vol.stop_mult

            risk_params["target_price"] = round(max(new_target, entry_est + 0.01), 2)
            risk_params["stop_price"] = round(max(new_stop, 0.01), 2)

    # ── Adjust trailing stop ──
    trailing = risk_params.get("trailing_stop_pct", 0.15)
    risk_params["trailing_stop_pct"] = round(trailing * vol.trailing_mult, 4)

    # ── Adjust hold time ──
    max_hold = risk_params.get("max_hold_minutes", 25)
    risk_params["max_hold_minutes"] = max(3, int(max_hold * vol.hold_mult))

    # ── Adjust position sizing ──
    max_contracts = risk_params.get("max_contracts", 1)
    adjusted = max(1, round(max_contracts * vol.size_mult))
    risk_params["max_contracts"] = adjusted

    risk_amount = risk_params.get("risk_amount", 0)
    risk_params["risk_amount"] = round(risk_amount * vol.size_mult, 2)

    # Store vol analysis
    risk_params["vol_analysis"] = vol.to_dict()

    logger.info(
        f"[VolAnalyzer] {vol.vol_regime} — "
        f"target×{vol.target_mult:.2f} stop×{vol.stop_mult:.2f} "
        f"hold×{vol.hold_mult:.2f} size×{vol.size_mult:.2f}"
    )

    return risk_params
