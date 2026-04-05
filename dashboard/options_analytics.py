"""
Options Analytics — IV Rank, Put/Call Ratio, Max Pain, Volume Spike.

Companion module to gex_engine.py. Provides the remaining options-derived
metrics needed by the enhanced 10-factor confluence engine.

All data comes from the existing chain/snapshot endpoints
(Alpaca pricing + ThetaData Greeks/OI). No new API calls.

Includes an IV history tracker that stores daily ATM IV to SQLite
for IV Rank / IV Percentile calculation over rolling windows.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone
import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

# Path for IV history database (lightweight, local)
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
IV_DB_PATH = os.path.join(_DB_DIR, "iv_history.db")


@dataclass
class OptionsAnalytics:
    """Aggregated options analytics for signal scoring."""

    # Put/Call Ratio
    pc_ratio_volume: float = 1.0     # put_vol / call_vol
    pc_ratio_oi: float = 1.0         # put_OI / call_OI
    total_call_volume: int = 0
    total_put_volume: int = 0
    total_call_oi: int = 0
    total_put_oi: int = 0

    # IV metrics
    atm_iv: float = 0.0             # Implied vol of ATM option
    iv_rank: Optional[float] = None  # 0-100, where current IV sits in 52-week range
    iv_percentile: Optional[float] = None  # % of days IV was below current level

    # Max Pain
    max_pain: float = 0.0

    # Volume spike
    volume_ratio: float = 1.0       # today_vol / avg_vol (if available)

    def to_dict(self) -> Dict:
        return {
            "pc_ratio_volume": round(self.pc_ratio_volume, 3),
            "pc_ratio_oi": round(self.pc_ratio_oi, 3),
            "total_call_volume": self.total_call_volume,
            "total_put_volume": self.total_put_volume,
            "total_call_oi": self.total_call_oi,
            "total_put_oi": self.total_put_oi,
            "atm_iv": round(self.atm_iv, 4) if self.atm_iv else 0,
            "iv_rank": round(self.iv_rank, 1) if self.iv_rank is not None else None,
            "iv_percentile": round(self.iv_percentile, 1) if self.iv_percentile is not None else None,
            "max_pain": self.max_pain,
            "volume_ratio": round(self.volume_ratio, 2),
        }


def analyze_options(
    calls: List[Dict],
    puts: List[Dict],
    spot: float,
    symbol: str = "SPY",
) -> OptionsAnalytics:
    """
    Compute all options analytics from chain data.

    Args:
        calls: Call entries from merged chain (Alpaca + ThetaData)
        puts: Put entries from merged chain
        spot: Current underlying price (from Alpaca quote)
        symbol: Underlying symbol for IV history lookup

    Returns:
        OptionsAnalytics with all computed metrics
    """
    result = OptionsAnalytics()

    # ── Put/Call Ratio ──
    result.total_call_volume = sum(c.get("volume", 0) or 0 for c in calls)
    result.total_put_volume = sum(p.get("volume", 0) or 0 for p in puts)
    result.total_call_oi = sum(c.get("open_interest", 0) or 0 for c in calls)
    result.total_put_oi = sum(p.get("open_interest", 0) or 0 for p in puts)

    if result.total_call_volume > 0:
        result.pc_ratio_volume = result.total_put_volume / result.total_call_volume
    if result.total_call_oi > 0:
        result.pc_ratio_oi = result.total_put_oi / result.total_call_oi

    # ── ATM IV ──
    result.atm_iv = _get_atm_iv(calls, puts, spot)

    # ── IV Rank / Percentile (from stored history) ──
    if result.atm_iv > 0:
        iv_rank, iv_pct = get_iv_rank(symbol, result.atm_iv)
        result.iv_rank = iv_rank
        result.iv_percentile = iv_pct

    # ── Max Pain ──
    result.max_pain = calc_max_pain(calls, puts)

    return result


def _get_atm_iv(calls: List[Dict], puts: List[Dict], spot: float) -> float:
    """Get ATM implied volatility (average of nearest call + put IV)."""
    if spot <= 0:
        return 0.0

    # Find call closest to ATM with IV
    call_iv = _nearest_iv(calls, spot)
    put_iv = _nearest_iv(puts, spot)

    if call_iv and put_iv:
        return (call_iv + put_iv) / 2
    return call_iv or put_iv or 0.0


def _nearest_iv(options: List[Dict], spot: float) -> Optional[float]:
    """Find IV of the option closest to ATM that has IV data."""
    with_iv = [o for o in options if o.get("iv") is not None and o.get("iv", 0) > 0]
    if not with_iv:
        return None
    nearest = min(with_iv, key=lambda o: abs(o.get("strike", 0) - spot))
    return nearest.get("iv")


def calc_max_pain(calls: List[Dict], puts: List[Dict]) -> float:
    """
    Calculate max pain: strike where option holders lose the most.
    Identical logic to api_routes._calc_max_pain but operates on
    the standard chain format.
    """
    call_oi = {c["strike"]: (c.get("open_interest", 0) or 0) for c in calls if "strike" in c}
    put_oi = {p["strike"]: (p.get("open_interest", 0) or 0) for p in puts if "strike" in p}
    strikes = sorted(set(call_oi.keys()) | set(put_oi.keys()))

    if not strikes:
        return 0.0

    min_pain = float("inf")
    best_strike = strikes[0]

    for k in strikes:
        pain = 0.0
        for s, oi in call_oi.items():
            if k > s:
                pain += (k - s) * oi
        for s, oi in put_oi.items():
            if k < s:
                pain += (s - k) * oi
        if pain < min_pain:
            min_pain = pain
            best_strike = k

    return best_strike


# ============================================================================
# PUT/CALL RATIO SCORING
# ============================================================================

def score_pcr(
    analytics: OptionsAnalytics,
    signal_direction: str,
) -> Tuple[float, str]:
    """
    Score put/call ratio as a contrarian indicator.

    Extreme fear (high PCR) + bullish signal = contrarian buy
    Extreme greed (low PCR) + bearish signal = contrarian sell

    Returns:
        (score, explanation) where score is -0.2 to 0.5
    """
    pcr = analytics.pc_ratio_volume

    if signal_direction == "bullish":
        if pcr > 1.2:
            return 0.5, f"PCR {pcr:.2f} (extreme fear) — contrarian bullish"
        elif pcr > 1.0:
            return 0.2, f"PCR {pcr:.2f} (elevated fear) — slight bullish edge"
        elif pcr < 0.7:
            return -0.2, f"PCR {pcr:.2f} (extreme greed) — crowded long, caution"
        return 0.0, f"PCR {pcr:.2f} (neutral)"

    elif signal_direction == "bearish":
        if pcr < 0.7:
            return 0.5, f"PCR {pcr:.2f} (extreme greed) — contrarian bearish"
        elif pcr < 0.85:
            return 0.2, f"PCR {pcr:.2f} (low fear) — slight bearish edge"
        elif pcr > 1.2:
            return -0.2, f"PCR {pcr:.2f} (extreme fear) — crowded short, caution"
        return 0.0, f"PCR {pcr:.2f} (neutral)"

    return 0.0, f"PCR {pcr:.2f}"


# ============================================================================
# MAX PAIN SCORING
# ============================================================================

def score_max_pain(
    analytics: OptionsAnalytics,
    spot: float,
    signal_direction: str,
    is_0dte: bool = True,
) -> Tuple[float, str]:
    """
    Score max pain gravitational pull.
    Max pain is strongest on expiration day (0DTE).

    Returns:
        (score, explanation) where score is -0.3 to 0.5
    """
    mp = analytics.max_pain
    if mp <= 0 or spot <= 0:
        return 0.0, "No max pain data"

    # Max pain pull is less relevant for non-0DTE
    if not is_0dte:
        return 0.0, f"Max pain ${mp:.0f} (non-0DTE, less relevant)"

    dist = spot - mp  # Positive = above max pain, negative = below

    if signal_direction == "bullish":
        if dist < -0.50:
            # Below max pain, bullish signal pushes toward it → favorable
            return 0.5, f"Max pain ${mp:.0f}, price ${spot:.2f} below — gravitational pull up"
        elif dist > 1.0:
            # Above max pain, bullish signal pushes further away → unfavorable
            return -0.3, f"Max pain ${mp:.0f}, price ${spot:.2f} above — gravitational pull down"
        return 0.1, f"Max pain ${mp:.0f}, price near — neutral pull"

    elif signal_direction == "bearish":
        if dist > 0.50:
            # Above max pain, bearish signal pushes toward it → favorable
            return 0.5, f"Max pain ${mp:.0f}, price ${spot:.2f} above — gravitational pull down"
        elif dist < -1.0:
            # Below max pain, bearish signal pushes further away → unfavorable
            return -0.3, f"Max pain ${mp:.0f}, price ${spot:.2f} below — gravitational pull up"
        return 0.1, f"Max pain ${mp:.0f}, price near — neutral pull"

    return 0.0, f"Max pain ${mp:.0f}"


# ============================================================================
# IV RANK / IV PERCENTILE
# ============================================================================

def _ensure_iv_db():
    """Create the IV history table if it doesn't exist."""
    os.makedirs(_DB_DIR, exist_ok=True)
    try:
        conn = sqlite3.connect(IV_DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS iv_history (
                date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                atm_iv REAL NOT NULL,
                PRIMARY KEY (date, symbol)
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not initialize IV database: {e}")


def store_daily_iv(symbol: str, atm_iv: float, date_str: Optional[str] = None):
    """
    Store today's ATM IV for IV Rank calculation.
    Called once per day after market open (e.g., after first signal evaluation).
    """
    if atm_iv <= 0:
        return

    _ensure_iv_db()
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        conn = sqlite3.connect(IV_DB_PATH)
        conn.execute(
            "INSERT OR REPLACE INTO iv_history (date, symbol, atm_iv) VALUES (?, ?, ?)",
            (date_str, symbol, atm_iv),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not store IV: {e}")


def get_iv_rank(
    symbol: str,
    current_iv: float,
    lookback_days: int = 252,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Calculate IV Rank and IV Percentile from stored history.

    IV Rank = (current - 52wk_low) / (52wk_high - 52wk_low) × 100
    IV Percentile = % of days where IV was below current level

    Returns:
        (iv_rank, iv_percentile) — both 0-100 or None if insufficient data
    """
    _ensure_iv_db()

    try:
        conn = sqlite3.connect(IV_DB_PATH)
        rows = conn.execute(
            "SELECT atm_iv FROM iv_history WHERE symbol = ? ORDER BY date DESC LIMIT ?",
            (symbol, lookback_days),
        ).fetchall()
        conn.close()
    except Exception:
        return None, None

    if len(rows) < 20:
        # Need at least 20 days of data for meaningful rank
        return None, None

    ivs = [r[0] for r in rows]
    iv_min = min(ivs)
    iv_max = max(ivs)

    # IV Rank
    iv_range = iv_max - iv_min
    if iv_range > 0:
        iv_rank = ((current_iv - iv_min) / iv_range) * 100.0
    else:
        iv_rank = 50.0

    # IV Percentile
    below_count = sum(1 for iv in ivs if iv < current_iv)
    iv_percentile = (below_count / len(ivs)) * 100.0

    return iv_rank, iv_percentile


def score_iv_rank(
    analytics: OptionsAnalytics,
) -> Tuple[float, str]:
    """
    Score IV Rank for signal quality.
    Very high IV = options expensive (bad for buying)
    Very low IV = options cheap (good for buying)

    Returns:
        (score, explanation) — score is informational, used as veto check
    """
    if analytics.iv_rank is None:
        return 0.0, "IV Rank unavailable (insufficient history)"

    rank = analytics.iv_rank
    if rank > 90:
        return -0.5, f"IV Rank {rank:.0f}% — extremely elevated, options very expensive"
    elif rank > 75:
        return -0.2, f"IV Rank {rank:.0f}% — elevated IV, premium expensive"
    elif rank < 20:
        return 0.3, f"IV Rank {rank:.0f}% — low IV, options cheap"
    elif rank < 40:
        return 0.1, f"IV Rank {rank:.0f}% — below average IV"

    return 0.0, f"IV Rank {rank:.0f}% — average"
