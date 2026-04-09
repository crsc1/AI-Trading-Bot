"""
Sector Monitor — Sector divergence detection + bond yield lead-lag.

SPY is a weighted basket. When its heaviest components diverge, SPY follows:
  - XLK (Tech, ~32% of SPY): If XLK rolling over while SPY flat → SPY follows down
  - XLF (Financials, ~13%): Diverges on rate-related news → leading indicator
  - XLE (Energy, ~3.5%): Oil shock proxy → risk-off signal when crashing

Bond Yield Lead-Lag:
  - TLT (20+ Year Treasury): Inverse to rates
  - 10Y yields lead SPY by 5-30 min on macro data days
  - TLT down 1%+ before SPY reacts → expect SPY down within 30 min
  - TLT up while SPY flat → expect SPY catch-up rally

Data source: Alpaca bars API (already have access).
Fetches 15-min bars for sector ETFs, computes relative strength.
"""

import logging
import aiohttp
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
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

# All 11 GICS sector ETFs and their approximate SPY weight
SECTORS = {
    "XLK": {"name": "Technology", "spy_weight": 0.32},
    "XLF": {"name": "Financials", "spy_weight": 0.13},
    "XLV": {"name": "Health Care", "spy_weight": 0.12},
    "XLY": {"name": "Consumer Disc.", "spy_weight": 0.10},
    "XLC": {"name": "Comm Services", "spy_weight": 0.09},
    "XLI": {"name": "Industrials", "spy_weight": 0.09},
    "XLP": {"name": "Consumer Staples", "spy_weight": 0.06},
    "XLE": {"name": "Energy", "spy_weight": 0.035},
    "XLU": {"name": "Utilities", "spy_weight": 0.025},
    "XLRE": {"name": "Real Estate", "spy_weight": 0.025},
    "XLB": {"name": "Materials", "spy_weight": 0.025},
}

# Bond ETF for yield proxy
BOND_ETF = "TLT"

# Cache
_sector_cache: Dict = {"result": None, "timestamp": None, "ttl_seconds": 60}


@dataclass
class SectorDivergence:
    """Divergence analysis for a single sector."""
    symbol: str = ""
    name: str = ""
    spy_weight: float = 0.0
    sector_return_pct: float = 0.0
    spy_return_pct: float = 0.0
    relative_strength: float = 0.0    # Sector return - SPY return
    is_diverging: bool = False
    divergence_direction: str = "none"  # "leading_up", "leading_down", "lagging", "none"

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "spy_weight": self.spy_weight,
            "sector_return_pct": round(self.sector_return_pct, 3),
            "spy_return_pct": round(self.spy_return_pct, 3),
            "relative_strength": round(self.relative_strength, 3),
            "is_diverging": self.is_diverging,
            "divergence_direction": self.divergence_direction,
        }


@dataclass
class SectorAnalysis:
    """Complete sector divergence and bond yield analysis."""

    sectors: List[SectorDivergence] = field(default_factory=list)

    # Bond/yield signal
    tlt_return_pct: float = 0.0
    bond_signal: str = "neutral"     # "risk_on" (TLT down), "risk_off" (TLT up), "neutral"
    bond_diverging: bool = False     # TLT and SPY moving same direction (unusual)

    # Aggregate
    sector_bias: float = 0.0         # -1 to +1 from sector divergences
    bond_bias: float = 0.0           # -1 to +1 from bond signal
    composite_bias: float = 0.0      # Weighted combo
    divergence_count: int = 0        # Number of diverging sectors

    def to_dict(self) -> Dict:
        return {
            "sectors": [s.to_dict() for s in self.sectors],
            "tlt_return_pct": round(self.tlt_return_pct, 3),
            "bond_signal": self.bond_signal,
            "bond_diverging": self.bond_diverging,
            "sector_bias": round(self.sector_bias, 3),
            "bond_bias": round(self.bond_bias, 3),
            "composite_bias": round(self.composite_bias, 3),
            "divergence_count": self.divergence_count,
        }


async def analyze_sectors(
    spy_return_pct: Optional[float] = None,
) -> SectorAnalysis:
    """
    Analyze sector divergences and bond yield signals.

    Args:
        spy_return_pct: Override SPY return if already known (avoids extra fetch)

    Returns:
        SectorAnalysis with per-sector divergences and bond signal
    """
    now = datetime.now(timezone.utc)

    # Check cache
    if (_sector_cache["result"] is not None
            and _sector_cache["timestamp"]
            and (now - _sector_cache["timestamp"]).total_seconds() < _sector_cache["ttl_seconds"]):
        return _sector_cache["result"]

    result = SectorAnalysis()

    # Fetch bars for all symbols
    symbols = ["SPY"] + list(SECTORS.keys()) + [BOND_ETF]
    bars = await _fetch_multi_bars(symbols, timeframe="15Min", limit=12)

    # Get SPY return
    spy_bars = bars.get("SPY", [])
    if spy_return_pct is None and len(spy_bars) >= 2:
        spy_return_pct = _compute_return(spy_bars)

    if spy_return_pct is None:
        spy_return_pct = 0.0

    # ── Sector divergences ──
    for etf, info in SECTORS.items():
        sector_bars = bars.get(etf, [])
        if len(sector_bars) < 2:
            continue

        sector_return = _compute_return(sector_bars)
        rel_strength = sector_return - spy_return_pct

        div = SectorDivergence(
            symbol=etf,
            name=info["name"],
            spy_weight=info["spy_weight"],
            sector_return_pct=sector_return,
            spy_return_pct=spy_return_pct,
            relative_strength=rel_strength,
        )

        # Detect meaningful divergence (>0.15% relative strength)
        if abs(rel_strength) > 0.15:
            div.is_diverging = True
            result.divergence_count += 1

            if rel_strength > 0.15:
                div.divergence_direction = "leading_up"
            elif rel_strength < -0.15:
                div.divergence_direction = "leading_down"

        result.sectors.append(div)

    # ── Sector composite bias ──
    # Weighted by SPY weight — XLK diverging matters more than XLE
    weighted_divergence = 0.0
    total_weight = 0.0
    for s in result.sectors:
        if s.is_diverging:
            weighted_divergence += s.relative_strength * s.spy_weight
            total_weight += s.spy_weight

    if total_weight > 0:
        result.sector_bias = max(-1.0, min(1.0, weighted_divergence / total_weight * 10))

    # ── Bond signal ──
    tlt_bars = bars.get(BOND_ETF, [])
    if len(tlt_bars) >= 2:
        result.tlt_return_pct = _compute_return(tlt_bars)

        # TLT inverse to yields: TLT down = yields up = typically equity negative
        if result.tlt_return_pct < -0.2:
            result.bond_signal = "risk_on" if spy_return_pct > 0 else "risk_off"
            result.bond_bias = -0.3  # Yields rising = headwind
        elif result.tlt_return_pct > 0.2:
            result.bond_signal = "risk_off" if spy_return_pct < 0 else "risk_on"
            result.bond_bias = 0.3   # Yields falling = tailwind
        else:
            result.bond_signal = "neutral"

        # Check if TLT and SPY moving same direction (unusual — stress signal)
        if (result.tlt_return_pct > 0.1 and spy_return_pct > 0.1) or \
           (result.tlt_return_pct < -0.1 and spy_return_pct < -0.1):
            result.bond_diverging = True  # Both moving same way = correlation breakdown

    # ── Composite bias ──
    result.composite_bias = (result.sector_bias * 0.6 + result.bond_bias * 0.4)
    result.composite_bias = max(-1.0, min(1.0, result.composite_bias))

    # Cache
    _sector_cache["result"] = result
    _sector_cache["timestamp"] = now

    return result


async def _fetch_multi_bars(
    symbols: List[str],
    timeframe: str = "15Min",
    limit: int = 12,
) -> Dict[str, List]:
    """Fetch bars for multiple symbols from Alpaca."""
    if not ALPACA_KEY:
        return {}

    result = {}
    try:
        async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
            # Use multibars endpoint for efficiency
            symbol_str = ",".join(symbols)
            url = f"{ALPACA_DATA_URL}/v2/stocks/bars"
            params = {
                "symbols": symbol_str,
                "timeframe": timeframe,
                "limit": limit,
                "adjustment": "raw",
                "feed": "iex",
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
                    logger.debug(f"Alpaca multi-bars failed: {resp.status}")

    except Exception as e:
        logger.debug(f"Sector bars fetch error: {e}")

    return result


def _compute_return(bars: List[Dict]) -> float:
    """Compute percentage return from first to last bar."""
    if len(bars) < 2:
        return 0.0

    first_close = bars[0].get("c", 0) or bars[0].get("close", 0)
    last_close = bars[-1].get("c", 0) or bars[-1].get("close", 0)

    if first_close <= 0:
        return 0.0

    return ((last_close - first_close) / first_close) * 100


# ── Scoring function for confluence integration ──

def score_sector_divergence(
    analysis: SectorAnalysis,
    signal_direction: str,
) -> Tuple[float, str]:
    """
    Score sector divergence + bond signal alignment with proposed trade.

    Max 0.5 points. This is a confirmation/warning signal.

    When XLK is leading SPY up and signal is BUY_CALL → confirmation.
    When TLT is crashing and signal is BUY_CALL → warning (yields spiking).

    Returns:
        (score, explanation)
    """
    is_bullish = signal_direction == "BUY_CALL"
    composite = analysis.composite_bias

    details = []

    # Sector component
    if analysis.divergence_count > 0:
        leading_sectors = [s for s in analysis.sectors if s.is_diverging]
        for s in leading_sectors:
            if s.divergence_direction == "leading_up":
                details.append(f"{s.symbol} leading up ({s.relative_strength:+.2f}%)")
            elif s.divergence_direction == "leading_down":
                details.append(f"{s.symbol} leading down ({s.relative_strength:+.2f}%)")

    # Bond component
    if analysis.bond_diverging:
        details.append("TLT-SPY correlation breakdown (stress)")

    if not details:
        return 0.0, "No sector divergences or bond signals"

    # Score based on alignment
    if is_bullish and composite > 0.2:
        score = min(0.5, composite * 0.5)
        explain = f"Sectors confirm bullish: {'; '.join(details)}"
    elif not is_bullish and composite < -0.2:
        score = min(0.5, abs(composite) * 0.5)
        explain = f"Sectors confirm bearish: {'; '.join(details)}"
    elif abs(composite) < 0.1:
        score = 0.0
        explain = f"Sector signals mixed: {'; '.join(details)}"
    else:
        score = max(-0.25, -abs(composite) * 0.25)
        explain = f"Sectors opposing trade: {'; '.join(details)}"

    if analysis.bond_diverging:
        score -= 0.1  # Correlation breakdown is a warning
        explain += " | TLT correlation breakdown"

    return round(max(-0.25, min(0.5, score)), 3), explain
