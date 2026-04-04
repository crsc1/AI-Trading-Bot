"""
Sweep Detector — Identifies institutional sweep orders in options flow.

A "sweep" is a large order split across multiple exchanges to fill urgently.
When someone pays the ask simultaneously on 5+ exchanges, they have conviction.

Detection logic:
  1. Fetch recent option trades from ThetaData trade history
  2. Group trades by strike/expiry within 500ms windows
  3. If same strike fills on 2+ exchanges within the window → sweep
  4. Classify as bullish (at ask) or bearish (at bid) based on trade price vs mid
  5. Score by size, urgency (exchange count), and premium paid

What makes sweeps predictive:
  - Urgency: someone paid MORE to fill faster (crossing exchanges vs sitting on one)
  - Size: sweeps >$100K notional have higher signal-to-noise
  - Direction: ask-side sweeps = bullish conviction, bid-side = bearish conviction
  - Persistence: repeated sweeps at same strike = institutional accumulation

Data source: ThetaData bulk trade endpoint (Options Standard plan).
No Alpaca interaction whatsoever.
"""

import logging
import aiohttp
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from .config import cfg

logger = logging.getLogger(__name__)

THETA_BASE = cfg.THETA_BASE_URL

# Detection parameters
SWEEP_WINDOW_MS = 500       # Max time between fills to count as one sweep
MIN_EXCHANGES = 2           # Minimum exchanges hit to qualify as sweep
MIN_TOTAL_SIZE = 50         # Minimum total contracts in sweep
MIN_NOTIONAL = 25000        # Minimum notional value ($)
LOOKBACK_MINUTES = 30       # How far back to scan for sweeps

# Cache
_sweep_cache: Dict = {"result": None, "timestamp": None, "ttl_seconds": 15}


# ── Sweep Tier Thresholds ──
# Research-backed: larger sweeps = higher conviction = better signal
TIER_GOLDEN_NOTIONAL = 1_000_000     # $1M+ → "golden" sweep (institutional block)
TIER_LARGE_NOTIONAL = 100_000        # $100K-$1M → "large" sweep (significant)
TIER_STANDARD_NOTIONAL = MIN_NOTIONAL  # $25K-$100K → "standard" sweep (noise-filtered)
# Below MIN_NOTIONAL ($25K) → discarded entirely

# Cluster detection
CLUSTER_WINDOW_MINUTES = 5   # Max time between sweeps to count as a cluster
CLUSTER_MIN_COUNT = 3        # Min sweeps at same strike to form a cluster


@dataclass
class SweepOrder:
    """Single detected sweep order."""
    strike: float = 0.0
    expiry: str = ""
    option_type: str = ""     # "call" or "put"
    side: str = ""            # "bullish" (at ask) or "bearish" (at bid)
    total_size: int = 0       # Total contracts across all fills
    num_exchanges: int = 0    # How many exchanges were hit
    avg_price: float = 0.0    # Average fill price
    notional: float = 0.0     # Total notional value ($)
    timestamp: str = ""       # First fill timestamp
    premium_ratio: float = 0.0  # Price paid vs mid (>1 = paid up, <1 = got discount)
    tier: str = "standard"    # "golden", "large", or "standard"
    fills: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "strike": self.strike,
            "expiry": self.expiry,
            "option_type": self.option_type,
            "side": self.side,
            "total_size": self.total_size,
            "num_exchanges": self.num_exchanges,
            "avg_price": round(self.avg_price, 4),
            "notional": round(self.notional, 2),
            "timestamp": self.timestamp,
            "premium_ratio": round(self.premium_ratio, 3),
            "tier": self.tier,
        }


@dataclass
class SweepCluster:
    """A cluster of 3+ sweeps at the same strike within a short window — institutional accumulation."""
    strike: float = 0.0
    option_type: str = ""
    side: str = ""
    sweep_count: int = 0
    total_notional: float = 0.0
    total_size: int = 0
    first_time: str = ""
    last_time: str = ""
    avg_tier: str = "standard"

    def to_dict(self) -> Dict:
        return {
            "strike": self.strike,
            "option_type": self.option_type,
            "side": self.side,
            "sweep_count": self.sweep_count,
            "total_notional": round(self.total_notional, 2),
            "total_size": self.total_size,
            "first_time": self.first_time,
            "last_time": self.last_time,
            "avg_tier": self.avg_tier,
        }


@dataclass
class SweepAnalysis:
    """Aggregate sweep analysis for a symbol."""
    sweeps: List[SweepOrder] = field(default_factory=list)
    clusters: List[SweepCluster] = field(default_factory=list)
    bullish_count: int = 0
    bearish_count: int = 0
    bullish_notional: float = 0.0
    bearish_notional: float = 0.0
    net_sweep_bias: float = 0.0     # -1 to +1 directional bias
    conviction_score: float = 0.0   # 0 to 1 based on size and frequency
    largest_sweep: Optional[SweepOrder] = None

    # Tier counts
    golden_count: int = 0
    large_count: int = 0
    standard_count: int = 0

    def to_dict(self) -> Dict:
        return {
            "sweep_count": len(self.sweeps),
            "bullish_count": self.bullish_count,
            "bearish_count": self.bearish_count,
            "bullish_notional": round(self.bullish_notional, 2),
            "bearish_notional": round(self.bearish_notional, 2),
            "net_sweep_bias": round(self.net_sweep_bias, 3),
            "conviction_score": round(self.conviction_score, 3),
            "largest_sweep": self.largest_sweep.to_dict() if self.largest_sweep else None,
            "sweeps": [s.to_dict() for s in self.sweeps[:10]],  # Top 10
            "tiers": {
                "golden": self.golden_count,
                "large": self.large_count,
                "standard": self.standard_count,
            },
            "clusters": [c.to_dict() for c in self.clusters],
        }


async def detect_sweeps(
    symbol: str = "SPY",
    expiry: Optional[str] = None,
    lookback_minutes: int = LOOKBACK_MINUTES,
) -> SweepAnalysis:
    """
    Detect sweep orders in recent options trades.

    Args:
        symbol: Underlying symbol
        expiry: Specific expiration (YYYYMMDD). If None, uses today (0DTE).
        lookback_minutes: How far back to scan

    Returns:
        SweepAnalysis with detected sweeps and aggregate metrics
    """
    now = datetime.now(timezone.utc)

    # Check cache
    if (_sweep_cache["result"] is not None
            and _sweep_cache["timestamp"]
            and (now - _sweep_cache["timestamp"]).total_seconds() < _sweep_cache["ttl_seconds"]):
        return _sweep_cache["result"]

    # Default to today's expiry (0DTE)
    if not expiry:
        expiry = now.strftime("%Y%m%d")

    # Fetch recent trades from ThetaData
    trades = await _fetch_option_trades(symbol, expiry, lookback_minutes)

    if not trades:
        result = SweepAnalysis()
        _sweep_cache["result"] = result
        _sweep_cache["timestamp"] = now
        return result

    # Detect sweeps from trade data
    sweeps = _identify_sweeps(trades)

    # Build analysis
    result = _build_analysis(sweeps)

    _sweep_cache["result"] = result
    _sweep_cache["timestamp"] = now

    return result


async def _fetch_option_trades(
    symbol: str,
    expiry: str,
    lookback_minutes: int,
) -> List[Dict]:
    """
    Fetch recent option trades from ThetaData.

    Uses the bulk_at_time endpoint for recent trade history.
    Falls back to snapshot trades if bulk not available.
    """
    # Clean expiry format
    exp_clean = expiry.replace("-", "")

    # Calculate start time (milliseconds since midnight ET)
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(minutes=lookback_minutes)

    try:
        async with aiohttp.ClientSession() as session:
            # v3: snapshot/trade endpoint (wildcard strike)
            url = f"{THETA_BASE}/v3/option/snapshot/trade"
            params = {
                "symbol": symbol,
                "expiration": exp_clean,
                "strike": "*",
                "format": "json",
            }

            async with session.get(
                url, params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"ThetaData trade fetch failed: {resp.status}")
                    return []

                data = await resp.json()
                response = data.get("response", [])

                trades = []
                for entry in response:
                    if not isinstance(entry, dict):
                        continue

                    # v3: strike is already in dollars, right is 'call'/'put'
                    cr_v3 = entry.get("right", "")
                    cr = "C" if cr_v3 == "call" else "P"
                    trades.append({
                        "strike": float(entry.get("strike", 0)),
                        "right": cr,
                        "price": float(entry.get("price", 0) or 0),
                        "size": entry.get("size", 0),
                        "exchange": entry.get("exchange", ""),
                        "condition": entry.get("condition", ""),
                        "bid": float(entry.get("bid", 0) or 0),
                        "ask": float(entry.get("ask", 0) or 0),
                        "ms_of_day": entry.get("ms_of_day", 0),
                        "date": entry.get("date", ""),
                    })

                return trades

    except Exception as e:
        logger.debug(f"ThetaData trade fetch error: {e}")
        return []


def _identify_sweeps(trades: List[Dict]) -> List[SweepOrder]:
    """
    Identify sweep orders from raw trade data.

    Groups trades by (strike, right) within SWEEP_WINDOW_MS time windows.
    Sweeps must hit MIN_EXCHANGES different exchanges.
    """
    if not trades:
        return []

    # Group by (strike, right)
    grouped = defaultdict(list)
    for t in trades:
        key = (t["strike"], t["right"])
        grouped[key].append(t)

    sweeps = []

    for (strike, right), strike_trades in grouped.items():
        if not strike_trades:
            continue

        # Sort by time
        sorted_trades = sorted(strike_trades, key=lambda t: t.get("ms_of_day", 0))

        # Sliding window to detect multi-exchange fills
        window_start = 0
        for i in range(len(sorted_trades)):
            # Move window start forward if outside window
            while (window_start < i and
                   sorted_trades[i]["ms_of_day"] - sorted_trades[window_start]["ms_of_day"] > SWEEP_WINDOW_MS):
                window_start += 1

            # Check window from window_start to i
            window = sorted_trades[window_start:i + 1]

            # Count unique exchanges in window
            exchanges = set(t.get("exchange", "") for t in window if t.get("exchange"))
            total_size = sum(t.get("size", 0) for t in window)

            if len(exchanges) >= MIN_EXCHANGES and total_size >= MIN_TOTAL_SIZE:
                # Calculate sweep details
                prices = [t["price"] for t in window if t["price"] > 0]
                bids = [t["bid"] for t in window if t["bid"] > 0]
                asks = [t["ask"] for t in window if t["ask"] > 0]

                if not prices:
                    continue

                avg_price = sum(p * s for p, s in zip(
                    [t["price"] for t in window],
                    [t["size"] for t in window]
                )) / total_size if total_size > 0 else 0

                mid = ((sum(bids) / len(bids)) + (sum(asks) / len(asks))) / 2 if bids and asks else avg_price

                # Classify direction
                if mid > 0:
                    premium_ratio = avg_price / mid
                    side = "bullish" if premium_ratio > 1.0 else "bearish"
                else:
                    premium_ratio = 1.0
                    side = "bullish" if right == "C" else "bearish"

                notional = avg_price * total_size * 100  # Options multiplier

                if notional >= MIN_NOTIONAL:
                    # Assign tier based on notional size
                    if notional >= TIER_GOLDEN_NOTIONAL:
                        tier = "golden"
                    elif notional >= TIER_LARGE_NOTIONAL:
                        tier = "large"
                    else:
                        tier = "standard"

                    sweep = SweepOrder(
                        strike=strike,
                        expiry=window[0].get("date", ""),
                        option_type="call" if right == "C" else "put",
                        side=side,
                        total_size=total_size,
                        num_exchanges=len(exchanges),
                        avg_price=avg_price,
                        notional=notional,
                        timestamp=str(window[0].get("ms_of_day", 0)),
                        premium_ratio=premium_ratio,
                        tier=tier,
                    )
                    sweeps.append(sweep)

                    # Skip past this window to avoid double-counting
                    window_start = i + 1

    # Sort by notional (largest first)
    sweeps.sort(key=lambda s: s.notional, reverse=True)

    return sweeps


def _build_analysis(sweeps: List[SweepOrder]) -> SweepAnalysis:
    """Build aggregate analysis from detected sweeps, including tier counts and clusters."""
    result = SweepAnalysis(sweeps=sweeps)

    if not sweeps:
        return result

    for s in sweeps:
        if s.side == "bullish":
            result.bullish_count += 1
            result.bullish_notional += s.notional
        else:
            result.bearish_count += 1
            result.bearish_notional += s.notional

        # Count by tier
        if s.tier == "golden":
            result.golden_count += 1
        elif s.tier == "large":
            result.large_count += 1
        else:
            result.standard_count += 1

    total_notional = result.bullish_notional + result.bearish_notional
    if total_notional > 0:
        result.net_sweep_bias = (result.bullish_notional - result.bearish_notional) / total_notional

    # Conviction score (0-1): tier-weighted
    # Golden sweeps count 3x, large count 2x, standard count 1x
    weighted_count = result.golden_count * 3 + result.large_count * 2 + result.standard_count
    count_score = min(weighted_count / 15, 1.0)  # 15 weighted = max
    notional_score = min(total_notional / 5_000_000, 1.0)  # $5M+ = max
    # Golden sweep presence is a strong signal by itself
    golden_bonus = min(result.golden_count * 0.15, 0.3)
    result.conviction_score = min(1.0, count_score * 0.35 + notional_score * 0.5 + golden_bonus + 0.15 * min(len(result.clusters), 2))

    result.largest_sweep = sweeps[0] if sweeps else None

    # Detect clusters (3+ sweeps at same strike within CLUSTER_WINDOW_MINUTES)
    result.clusters = _detect_clusters(sweeps)

    # Re-compute conviction with clusters now populated
    result.conviction_score = min(1.0,
        count_score * 0.35 + notional_score * 0.5 + golden_bonus + 0.15 * min(len(result.clusters), 2)
    )

    return result


def _detect_clusters(sweeps: List[SweepOrder]) -> List[SweepCluster]:
    """
    Detect clusters: 3+ sweeps at the same strike within CLUSTER_WINDOW_MINUTES.

    Clusters indicate institutional accumulation — they didn't just sweep once,
    they came back multiple times at the same strike. This is the strongest
    order flow signal available.
    """
    if len(sweeps) < CLUSTER_MIN_COUNT:
        return []

    # Group sweeps by (strike, option_type)
    groups: Dict[Tuple[float, str], List[SweepOrder]] = defaultdict(list)
    for s in sweeps:
        groups[(s.strike, s.option_type)].append(s)

    clusters = []
    for (strike, opt_type), group in groups.items():
        if len(group) < CLUSTER_MIN_COUNT:
            continue

        # Sort by timestamp (ms_of_day)
        sorted_group = sorted(group, key=lambda s: int(s.timestamp) if s.timestamp.isdigit() else 0)

        # Sliding window: check if CLUSTER_MIN_COUNT sweeps fit within CLUSTER_WINDOW_MINUTES
        window_ms = CLUSTER_WINDOW_MINUTES * 60 * 1000
        for i in range(len(sorted_group) - CLUSTER_MIN_COUNT + 1):
            window_end = i + CLUSTER_MIN_COUNT - 1
            # Extend window as far as possible
            while (window_end + 1 < len(sorted_group) and
                   _ts_diff_ms(sorted_group[i], sorted_group[window_end + 1]) <= window_ms):
                window_end += 1

            cluster_sweeps = sorted_group[i:window_end + 1]
            if len(cluster_sweeps) >= CLUSTER_MIN_COUNT:
                # Determine dominant side
                bull_n = sum(1 for s in cluster_sweeps if s.side == "bullish")
                bear_n = len(cluster_sweeps) - bull_n
                dominant_side = "bullish" if bull_n >= bear_n else "bearish"

                # Best tier in cluster
                tier_rank = {"golden": 3, "large": 2, "standard": 1}
                best_tier = max(cluster_sweeps, key=lambda s: tier_rank.get(s.tier, 0)).tier

                cluster = SweepCluster(
                    strike=strike,
                    option_type=opt_type,
                    side=dominant_side,
                    sweep_count=len(cluster_sweeps),
                    total_notional=sum(s.notional for s in cluster_sweeps),
                    total_size=sum(s.total_size for s in cluster_sweeps),
                    first_time=cluster_sweeps[0].timestamp,
                    last_time=cluster_sweeps[-1].timestamp,
                    avg_tier=best_tier,
                )
                clusters.append(cluster)
                break  # One cluster per (strike, opt_type) — take the best

    # Sort clusters by total notional (most significant first)
    clusters.sort(key=lambda c: c.total_notional, reverse=True)
    return clusters


def _ts_diff_ms(s1: SweepOrder, s2: SweepOrder) -> int:
    """Get time difference in ms between two sweeps."""
    try:
        t1 = int(s1.timestamp) if s1.timestamp.isdigit() else 0
        t2 = int(s2.timestamp) if s2.timestamp.isdigit() else 0
        return abs(t2 - t1)
    except (ValueError, TypeError):
        return 0


# ── Scoring function for confluence integration ──

def score_sweep_activity(
    analysis: SweepAnalysis,
    signal_direction: str,
) -> Tuple[float, str]:
    """
    Score sweep activity alignment with proposed trade direction.

    Tier-weighted scoring:
      - Golden sweeps ($1M+): 0.75 max (institutional block = strongest signal)
      - Large sweeps ($100K-$1M): 0.50 max
      - Standard sweeps ($25K-$100K): 0.30 max
      - Cluster bonus: +0.10 per aligned cluster (max +0.20)

    Returns:
        (score, explanation) where score is -0.30 to 0.95
    """
    if not analysis.sweeps:
        return 0.0, "No sweep activity detected"

    is_bullish = signal_direction == "BUY_CALL"
    bias = analysis.net_sweep_bias
    conviction = analysis.conviction_score

    # Determine alignment
    aligned = (is_bullish and bias > 0.3) or (not is_bullish and bias < -0.3)
    opposing = (is_bullish and bias < -0.3) or (not is_bullish and bias > 0.3)

    if aligned:
        # Tier-weighted base score
        golden_score = min(analysis.golden_count * 0.25, 0.75)
        large_score = min(analysis.large_count * 0.15, 0.50)
        standard_score = min(analysis.standard_count * 0.05, 0.30)
        base = max(golden_score, large_score, standard_score)

        # Cluster bonus: institutional accumulation at aligned strikes
        aligned_clusters = [c for c in analysis.clusters
                          if (c.side == "bullish") == is_bullish]
        cluster_bonus = min(len(aligned_clusters) * 0.10, 0.20)

        score = min(0.95, base + cluster_bonus)

        parts = []
        if analysis.golden_count:
            parts.append(f"{analysis.golden_count} golden ($1M+)")
        if analysis.large_count:
            parts.append(f"{analysis.large_count} large")
        if analysis.standard_count:
            parts.append(f"{analysis.standard_count} std")
        tier_desc = ", ".join(parts)

        dir_label = "Bullish" if is_bullish else "Bearish"
        align_count = analysis.bullish_count if is_bullish else analysis.bearish_count
        align_notional = analysis.bullish_notional if is_bullish else analysis.bearish_notional
        explain = (f"{dir_label} sweeps confirm: {align_count} sweeps [{tier_desc}], "
                   f"${align_notional:,.0f} notional")
        if aligned_clusters:
            explain += f" + {len(aligned_clusters)} cluster(s)"

    elif opposing:
        # Opposing sweeps: penalty scales with tier
        penalty = conviction * 0.30
        if analysis.golden_count > 0:
            penalty = max(penalty, 0.25)  # Golden opposing = strong warning
        score = -min(0.30, penalty)
        explain = f"Sweep flow opposes trade: bias {bias:+.2f}"
        if analysis.golden_count:
            explain += f" (includes {analysis.golden_count} golden sweep(s) — caution)"

    else:
        score = 0.0
        explain = "Mixed sweep activity — no clear direction"

    return round(score, 3), explain
