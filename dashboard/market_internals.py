"""
Market Internals — Synthetic breadth index for market context awareness.

Since true NYSE TICK/ADD/VOLD data requires exchange-level feeds ($$$),
we build a practical proxy from sector ETF + market proxy momentum:

Breadth Universe (11 symbols):
  - Sectors: XLK (Tech 32%), XLF (Financials 13%), XLV (Healthcare 13%),
             XLY (Consumer Disc 10%), XLC (Comms 9%), XLI (Industrials 8%)
  - Market proxies: QQQ (Nasdaq-100), IWM (Russell 2000)
  - Risk gauges: TLT (bonds inverse), GLD (safe haven), HYG (high yield credit)

Signals produced:
  - breadth_score: -1.0 to +1.0 (strong bearish to strong bullish)
  - breadth_divergence: True when SPY direction conflicts with majority of symbols
  - extreme_reading: True when 9+ of 11 symbols align (very strong directional signal)
  - advance_decline_ratio: 0.0-1.0 (fraction of symbols advancing)
  - risk_appetite: -1.0 to +1.0 based on TLT/GLD/HYG positioning

Data source: Alpaca bars API (already subscribed via SIP plan).
"""

import logging
import aiohttp
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ALPACA_DATA_URL = "https://data.alpaca.markets"
ALPACA_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET = os.environ.get("ALPACA_SECRET_KEY", "")
ALPACA_HEADERS = {
    "APCA-API-KEY-ID": ALPACA_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET,
    "Accept": "application/json",
}

# ─── Breadth Universe ─────────────────────────────────────────────────────────
# Symbols that together give us a broad picture of market direction.
# Weight reflects importance for SPY correlation.

BREADTH_UNIVERSE = {
    # Core sector ETFs (cover ~85% of SPY)
    "XLK": {"name": "Technology",       "weight": 0.32, "type": "sector"},
    "XLF": {"name": "Financials",       "weight": 0.13, "type": "sector"},
    "XLV": {"name": "Healthcare",       "weight": 0.13, "type": "sector"},
    "XLY": {"name": "Consumer Disc",    "weight": 0.10, "type": "sector"},
    "XLC": {"name": "Communication",    "weight": 0.09, "type": "sector"},
    "XLI": {"name": "Industrials",      "weight": 0.08, "type": "sector"},

    # Market-cap proxies (broader breadth)
    "QQQ": {"name": "Nasdaq-100",       "weight": 0.15, "type": "market"},
    "IWM": {"name": "Russell 2000",     "weight": 0.10, "type": "market"},

    # Risk gauges (inverse/divergence signals)
    "TLT": {"name": "20Y Treasury",     "weight": 0.08, "type": "risk", "inverse": True},
    "GLD": {"name": "Gold",             "weight": 0.05, "type": "risk", "inverse": True},
    "HYG": {"name": "High Yield Credit","weight": 0.10, "type": "risk", "inverse": False},
}

# Thresholds
ADVANCE_THRESHOLD = 0.03     # +0.03% to count as "advancing" (not flat)
EXTREME_THRESHOLD = 0.82     # 9+ of 11 = extreme reading
DIVERGENCE_THRESHOLD = 0.36  # Fewer than 4 of 11 supporting = divergence


# ─── Result ───────────────────────────────────────────────────────────────────

@dataclass
class MarketBreadth:
    """Synthetic market breadth analysis result."""

    # Core metrics
    breadth_score: float = 0.0        # -1.0 (all bearish) to +1.0 (all bullish)
    advance_decline_ratio: float = 0.5  # 0.0 (all declining) to 1.0 (all advancing)
    advancing_count: int = 0
    declining_count: int = 0
    flat_count: int = 0

    # Signals
    breadth_divergence: bool = False  # SPY up but majority down (or vice versa)
    divergence_direction: str = "none"  # "bearish_div" (SPY up, breadth down) or "bullish_div"
    extreme_reading: bool = False     # 9+ of 11 align
    extreme_direction: str = "none"   # "bullish" or "bearish"

    # Risk appetite (from TLT/GLD/HYG)
    risk_appetite: float = 0.0        # -1.0 (risk off) to +1.0 (risk on)
    risk_signal: str = "neutral"      # "risk_on", "risk_off", "neutral"

    # Per-symbol detail
    symbol_states: Dict[str, Dict] = field(default_factory=dict)

    # SPY reference
    spy_return_pct: float = 0.0

    # Metadata
    timestamp: float = 0.0
    symbols_fetched: int = 0

    def to_dict(self) -> Dict:
        return {
            "breadth_score": round(self.breadth_score, 3),
            "advance_decline_ratio": round(self.advance_decline_ratio, 3),
            "advancing": self.advancing_count,
            "declining": self.declining_count,
            "flat": self.flat_count,
            "breadth_divergence": self.breadth_divergence,
            "divergence_direction": self.divergence_direction,
            "extreme_reading": self.extreme_reading,
            "extreme_direction": self.extreme_direction,
            "risk_appetite": round(self.risk_appetite, 3),
            "risk_signal": self.risk_signal,
            "spy_return_pct": round(self.spy_return_pct, 3),
            "symbols_fetched": self.symbols_fetched,
        }


# ─── Cache ────────────────────────────────────────────────────────────────────

_breadth_cache: Optional[MarketBreadth] = None
_breadth_cache_ts: float = 0
_CACHE_TTL = 30  # seconds — breadth doesn't change that fast


# ─── Main Analysis ────────────────────────────────────────────────────────────

async def analyze_breadth() -> MarketBreadth:
    """
    Fetch recent bars for breadth universe and compute market internals.

    Uses 5-minute bars (last 6 bars = 30 minutes) to measure short-term
    direction across all symbols.

    Returns:
        MarketBreadth with breadth_score, divergence, extreme, risk signals
    """
    global _breadth_cache, _breadth_cache_ts

    now = time.time()
    if _breadth_cache is not None and (now - _breadth_cache_ts) < _CACHE_TTL:
        return _breadth_cache

    result = MarketBreadth(timestamp=now)

    # Fetch bars for all symbols including SPY
    all_symbols = ["SPY"] + list(BREADTH_UNIVERSE.keys())
    bars = await _fetch_multi_bars(all_symbols, timeframe="5Min", limit=6)

    if not bars:
        return result

    # SPY baseline
    spy_bars = bars.get("SPY", [])
    spy_return = _compute_return(spy_bars)
    result.spy_return_pct = spy_return

    # ── Compute per-symbol momentum ──
    advancing = 0
    declining = 0
    flat = 0
    weighted_direction = 0.0
    total_weight = 0.0
    risk_score = 0.0
    risk_weight = 0.0

    for sym, info in BREADTH_UNIVERSE.items():
        sym_bars = bars.get(sym, [])
        if len(sym_bars) < 2:
            flat += 1
            continue

        sym_return = _compute_return(sym_bars)
        is_inverse = info.get("inverse", False)
        weight = info["weight"]
        sym_type = info["type"]

        # For inverse symbols (TLT, GLD): them going DOWN is bullish for SPY
        effective_return = -sym_return if is_inverse else sym_return

        # Classify as advancing/declining/flat
        if effective_return > ADVANCE_THRESHOLD:
            advancing += 1
            state = "advancing"
        elif effective_return < -ADVANCE_THRESHOLD:
            declining += 1
            state = "declining"
        else:
            flat += 1
            state = "flat"

        # Weighted direction score
        # Clamp to ±1% to prevent outliers from dominating
        clamped = max(-1.0, min(1.0, effective_return))
        weighted_direction += clamped * weight
        total_weight += weight

        # Risk appetite (from risk-type symbols)
        if sym_type == "risk":
            risk_score += effective_return * weight
            risk_weight += weight

        result.symbol_states[sym] = {
            "return_pct": round(sym_return, 3),
            "effective_return": round(effective_return, 3),
            "state": state,
            "type": sym_type,
        }

    result.advancing_count = advancing
    result.declining_count = declining
    result.flat_count = flat
    result.symbols_fetched = advancing + declining + flat

    total_counted = advancing + declining + flat
    if total_counted == 0:
        _breadth_cache = result
        _breadth_cache_ts = now
        return result

    # ── Advance/Decline Ratio ──
    result.advance_decline_ratio = advancing / total_counted

    # ── Breadth Score: weighted direction ──
    if total_weight > 0:
        raw_breadth = weighted_direction / total_weight
        result.breadth_score = max(-1.0, min(1.0, raw_breadth * 3.0))  # Scale up for sensitivity

    # ── Extreme Reading ──
    if result.advance_decline_ratio >= EXTREME_THRESHOLD:
        result.extreme_reading = True
        result.extreme_direction = "bullish"
    elif result.advance_decline_ratio <= (1.0 - EXTREME_THRESHOLD):
        result.extreme_reading = True
        result.extreme_direction = "bearish"

    # ── Breadth Divergence ──
    # SPY going one way but majority of breadth symbols disagree
    spy_bullish = spy_return > ADVANCE_THRESHOLD
    spy_bearish = spy_return < -ADVANCE_THRESHOLD

    if spy_bullish and result.advance_decline_ratio < DIVERGENCE_THRESHOLD:
        result.breadth_divergence = True
        result.divergence_direction = "bearish_div"  # SPY up but breadth weak
    elif spy_bearish and result.advance_decline_ratio > (1.0 - DIVERGENCE_THRESHOLD):
        result.breadth_divergence = True
        result.divergence_direction = "bullish_div"  # SPY down but breadth strong

    # ── Risk Appetite ──
    if risk_weight > 0:
        raw_risk = risk_score / risk_weight
        result.risk_appetite = max(-1.0, min(1.0, raw_risk * 3.0))

        if result.risk_appetite > 0.3:
            result.risk_signal = "risk_on"
        elif result.risk_appetite < -0.3:
            result.risk_signal = "risk_off"
        else:
            result.risk_signal = "neutral"

    # Cache
    _breadth_cache = result
    _breadth_cache_ts = now

    return result


# ─── Confluence Scoring ───────────────────────────────────────────────────────

def score_market_breadth(
    breadth: MarketBreadth,
    direction: str,
) -> Tuple[float, str]:
    """
    Score market breadth alignment with proposed trade direction.

    Factor 22: Market Breadth (max 1.0, min -0.40)

    Scoring:
      +0.40: Breadth strongly confirms direction
      +0.25: Breadth moderately confirms
      +0.10: Breadth weakly confirms
       0.00: Neutral / no data
      -0.20: Breadth diverging from direction
      -0.40: Extreme breadth divergence (strong headwind)

    Bonuses:
      +0.25: Extreme reading in our direction
      +0.20: Risk appetite aligns
      +0.15: Risk appetite strongly aligns

    Returns:
        (score, detail_string)
    """
    if breadth.symbols_fetched < 3:
        return 0.0, "Insufficient breadth data"

    is_bullish = direction in ("BUY_CALL", "bullish")
    score = 0.0
    details = []

    # ── Core breadth alignment ──
    bs = breadth.breadth_score

    if is_bullish:
        if bs > 0.5:
            score += 0.40
            details.append(f"Strong breadth confirms bullish ({bs:+.2f})")
        elif bs > 0.2:
            score += 0.25
            details.append(f"Breadth supports bullish ({bs:+.2f})")
        elif bs > 0.05:
            score += 0.10
            details.append(f"Slight breadth tilt bullish ({bs:+.2f})")
        elif bs < -0.3:
            score -= 0.40
            details.append(f"Breadth strongly opposes bullish ({bs:+.2f})")
        elif bs < -0.1:
            score -= 0.20
            details.append(f"Breadth diverges from bullish ({bs:+.2f})")
    else:  # Bearish
        if bs < -0.5:
            score += 0.40
            details.append(f"Strong breadth confirms bearish ({bs:+.2f})")
        elif bs < -0.2:
            score += 0.25
            details.append(f"Breadth supports bearish ({bs:+.2f})")
        elif bs < -0.05:
            score += 0.10
            details.append(f"Slight breadth tilt bearish ({bs:+.2f})")
        elif bs > 0.3:
            score -= 0.40
            details.append(f"Breadth strongly opposes bearish ({bs:+.2f})")
        elif bs > 0.1:
            score -= 0.20
            details.append(f"Breadth diverges from bearish ({bs:+.2f})")

    # ── Extreme reading bonus ──
    if breadth.extreme_reading:
        if (is_bullish and breadth.extreme_direction == "bullish") or \
           (not is_bullish and breadth.extreme_direction == "bearish"):
            score += 0.25
            details.append(f"Extreme breadth {breadth.extreme_direction} ({breadth.advancing_count}A/{breadth.declining_count}D)")
        elif (is_bullish and breadth.extreme_direction == "bearish") or \
             (not is_bullish and breadth.extreme_direction == "bullish"):
            score -= 0.20
            details.append(f"Extreme breadth opposing ({breadth.extreme_direction})")

    # ── Risk appetite alignment ──
    ra = breadth.risk_appetite
    if is_bullish and ra > 0.3:
        score += 0.20
        details.append(f"Risk-on confirms ({ra:+.2f})")
    elif is_bullish and ra < -0.3:
        score -= 0.15
        details.append(f"Risk-off headwind ({ra:+.2f})")
    elif not is_bullish and ra < -0.3:
        score += 0.20
        details.append(f"Risk-off confirms ({ra:+.2f})")
    elif not is_bullish and ra > 0.3:
        score -= 0.15
        details.append(f"Risk-on headwind ({ra:+.2f})")

    # ── Breadth divergence warning ──
    if breadth.breadth_divergence:
        if is_bullish and breadth.divergence_direction == "bearish_div":
            details.append("WARNING: SPY up but breadth weak — potential reversal")
        elif not is_bullish and breadth.divergence_direction == "bullish_div":
            details.append("WARNING: SPY down but breadth strong — potential bounce")

    # Clamp to range
    score = max(-0.40, min(1.0, score))
    detail = " | ".join(details) if details else f"Breadth neutral ({bs:+.2f})"

    return round(score, 3), detail


# ─── Network ──────────────────────────────────────────────────────────────────

async def _fetch_multi_bars(
    symbols: List[str],
    timeframe: str = "5Min",
    limit: int = 6,
) -> Dict[str, List]:
    """Fetch bars for multiple symbols from Alpaca multi-bars endpoint."""
    if not ALPACA_KEY:
        return {}

    result = {}
    try:
        async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
            symbol_str = ",".join(symbols)
            url = f"{ALPACA_DATA_URL}/v2/stocks/bars"
            params = {
                "symbols": symbol_str,
                "timeframe": timeframe,
                "limit": limit,
                "adjustment": "raw",
                "feed": "iex",  # Free tier — use "sip" if paid
            }

            async with session.get(
                url, params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    bars_by_symbol = data.get("bars", {})
                    for sym, bars in bars_by_symbol.items():
                        result[sym] = bars
                else:
                    logger.debug(f"Breadth bars fetch failed: {resp.status}")

    except Exception as e:
        logger.debug(f"Breadth bars fetch error: {e}")

    return result


def _compute_return(bars: List[Dict]) -> float:
    """Compute % return from first to last bar close."""
    if len(bars) < 2:
        return 0.0
    first = bars[0].get("c", 0) or bars[0].get("close", 0)
    last = bars[-1].get("c", 0) or bars[-1].get("close", 0)
    if first <= 0:
        return 0.0
    return ((last - first) / first) * 100
