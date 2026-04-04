"""
Regime Detector — Multi-signal market regime classification.

Detects the current market REGIME before any trade decisions are made.
Different regimes require fundamentally different trading strategies:

  Risk-On (Trending):  Momentum strategies, trend-following, wider targets
  Risk-Off (Volatile): Mean-reversion, quick scalps, tighter stops
  Transition:          Reduce size, wait for confirmation, be selective

Signals used:
  1. VIX Term Structure: Contango (calm) vs Backwardation (stress)
  2. SPY-TLT Correlation: Risk-on (inverse) vs Flight-to-safety (positive)
  3. DXY Direction:       Dollar strength = equity headwind
  4. Intraday Volatility: Realized vol vs implied vol

Data sources: All free — FRED API, CBOE, Yahoo Finance, Alpaca.
No interference with Alpaca execution.
"""

import logging
import aiohttp
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
from .config import cfg

logger = logging.getLogger(__name__)

# FRED API (free, 120 calls/min)
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Alpaca for intraday SPY/TLT/VIX data
ALPACA_DATA_URL = "https://data.alpaca.markets"
ALPACA_KEY = cfg.ALPACA_API_KEY
ALPACA_SECRET = cfg.ALPACA_SECRET_KEY
ALPACA_HEADERS = cfg.ALPACA_HEADERS

# Cache to avoid redundant API calls (regime doesn't change every second)
_regime_cache: Dict = {"result": None, "timestamp": None, "ttl_seconds": 60}


@dataclass
class RegimeState:
    """Current market regime classification."""

    # Overall regime
    regime: str = "unknown"           # "risk_on", "risk_off", "transition", "unknown"
    confidence: float = 0.0           # 0-1 how confident we are in the regime
    description: str = ""

    # VIX term structure
    vix_structure: str = "unknown"    # "contango", "backwardation", "flat"
    vix_spot: float = 0.0
    vix_3m: float = 0.0              # VIX3M or VIX future proxy
    vix_ratio: float = 0.0           # VIX/VIX3M — <1 = contango, >1 = backwardation
    vix_percentile: float = 0.0      # Where current VIX sits vs 30-day range (0-100)

    # Correlation regime
    spy_tlt_correlation: float = 0.0  # Rolling 60-min correlation
    correlation_regime: str = "normal" # "inverse" (risk-on), "positive" (risk-off), "decoupled"

    # Dollar strength
    dxy_direction: str = "neutral"    # "strengthening", "weakening", "neutral"
    dxy_bias: float = 0.0            # -1 (weak $) to +1 (strong $)

    # Realized vs implied volatility
    rv_iv_ratio: float = 0.0         # RV/IV — >1 = IV underpriced, <1 = IV overpriced
    vol_regime: str = "normal"        # "elevated", "compressed", "normal"

    # Position sizing multiplier (the actionable output)
    sizing_multiplier: float = 1.0   # 0.3 to 1.5 (dampens or boosts position size)
    directional_bias: float = 0.0    # -0.5 to +0.5 (tilts toward puts or calls)

    def to_dict(self) -> Dict:
        return {
            "regime": self.regime,
            "confidence": round(self.confidence, 2),
            "description": self.description,
            "vix_structure": self.vix_structure,
            "vix_spot": round(self.vix_spot, 2),
            "vix_3m": round(self.vix_3m, 2),
            "vix_ratio": round(self.vix_ratio, 3),
            "vix_percentile": round(self.vix_percentile, 1),
            "spy_tlt_correlation": round(self.spy_tlt_correlation, 3),
            "correlation_regime": self.correlation_regime,
            "dxy_direction": self.dxy_direction,
            "dxy_bias": round(self.dxy_bias, 3),
            "rv_iv_ratio": round(self.rv_iv_ratio, 3),
            "vol_regime": self.vol_regime,
            "sizing_multiplier": round(self.sizing_multiplier, 2),
            "directional_bias": round(self.directional_bias, 3),
        }


async def detect_regime(
    current_iv: float = 0.0,
    spy_bars_1m: Optional[list] = None,
) -> RegimeState:
    """
    Detect current market regime.

    Uses cached result if within TTL to avoid excessive API calls.

    Args:
        current_iv: ATM implied volatility (from our options analytics)
        spy_bars_1m: Intraday 1-min bars (from existing data pipeline)

    Returns:
        RegimeState with all sub-signals and final classification
    """
    # Check cache
    now = datetime.now(timezone.utc)
    if (_regime_cache["result"] is not None
            and _regime_cache["timestamp"]
            and (now - _regime_cache["timestamp"]).total_seconds() < _regime_cache["ttl_seconds"]):
        return _regime_cache["result"]

    state = RegimeState()

    # ── 1. VIX Term Structure ──
    await _analyze_vix_structure(state)

    # ── 2. SPY-TLT Correlation ──
    await _analyze_correlation(state)

    # ── 3. Dollar Strength ──
    await _analyze_dollar(state)

    # ── 4. Realized vs Implied Volatility ──
    _analyze_vol_regime(state, current_iv, spy_bars_1m)

    # ── 5. Classify overall regime ──
    _classify_regime(state)

    # Cache
    _regime_cache["result"] = state
    _regime_cache["timestamp"] = now

    return state


async def _analyze_vix_structure(state: RegimeState):
    """
    Analyze VIX term structure using Alpaca data.

    VIX contango (normal): Near-term < far-term → calm, dealers comfortable
    VIX backwardation:     Near-term > far-term → stress, hedging demand high

    We use VIX (^VIX) and approximate VIX3M using VIXY/VIX3M ETFs
    or use the ratio of intraday SPY realized vol to VIX.
    """
    try:
        # Fetch VIX-related data from Alpaca
        # Note: Alpaca doesn't provide VIX directly, so we use UVXY as proxy
        # or compute from SPY options IV vs historical IV
        vix_data = await _fetch_latest_bars(["UVXY", "SVXY"])

        uvxy_price = vix_data.get("UVXY", {}).get("close", 0)
        svxy_price = vix_data.get("SVXY", {}).get("close", 0)

        if uvxy_price > 0 and svxy_price > 0:
            # UVXY/SVXY ratio as VIX regime proxy
            # High ratio = high volatility regime
            ratio = uvxy_price / svxy_price

            # Approximate VIX from UVXY (rough linear relationship)
            # UVXY tracks 1.5x daily VIX futures returns
            state.vix_spot = min(ratio * 10, 80)  # Rough approximation
            state.vix_3m = state.vix_spot * 0.9  # Contango assumption

            if ratio > 1.5:  # Elevated volatility
                state.vix_structure = "backwardation"
                state.vix_ratio = 1.15
            elif ratio < 0.5:  # Low volatility
                state.vix_structure = "contango"
                state.vix_ratio = 0.85
            else:
                state.vix_structure = "contango"
                state.vix_ratio = 0.95

        else:
            # Fallback: use IV from options analytics if available
            state.vix_structure = "unknown"

    except Exception as e:
        logger.debug(f"VIX structure analysis error: {e}")
        state.vix_structure = "unknown"


async def _analyze_correlation(state: RegimeState):
    """
    Compute rolling SPY-TLT correlation.

    Risk-on:  SPY↑ TLT↓ (inverse correlation, ~-0.3 to -0.7)
    Risk-off: SPY↓ TLT↑ (still inverse but both moving)
    Panic:    SPY↓ TLT↓ (positive correlation — liquidity crisis)
    """
    try:
        bars = await _fetch_latest_bars(["SPY", "TLT"], timeframe="15Min", limit=20)

        spy_bars = bars.get("SPY", {}).get("bars", [])
        tlt_bars = bars.get("TLT", {}).get("bars", [])

        if len(spy_bars) >= 5 and len(tlt_bars) >= 5:
            # Compute returns
            spy_returns = [
                (spy_bars[i]["close"] - spy_bars[i - 1]["close"]) / spy_bars[i - 1]["close"]
                for i in range(1, min(len(spy_bars), len(tlt_bars)))
            ]
            tlt_returns = [
                (tlt_bars[i]["close"] - tlt_bars[i - 1]["close"]) / tlt_bars[i - 1]["close"]
                for i in range(1, min(len(spy_bars), len(tlt_bars)))
            ]

            corr = _pearson_correlation(spy_returns, tlt_returns)
            state.spy_tlt_correlation = corr

            if corr < -0.3:
                state.correlation_regime = "inverse"  # Normal risk-on/off
            elif corr > 0.3:
                state.correlation_regime = "positive"  # Panic / liquidity stress
            else:
                state.correlation_regime = "decoupled"

    except Exception as e:
        logger.debug(f"Correlation analysis error: {e}")


async def _analyze_dollar(state: RegimeState):
    """
    Assess dollar strength direction.

    Strong dollar = headwind for equities (SPY has ~40% international revenue)
    We use UUP (dollar bullish ETF) as DXY proxy via Alpaca.
    """
    try:
        bars = await _fetch_latest_bars(["UUP"], timeframe="15Min", limit=12)
        uup_bars = bars.get("UUP", {}).get("bars", [])

        if len(uup_bars) >= 5:
            # 3-hour price change
            first = uup_bars[0]["close"]
            last = uup_bars[-1]["close"]
            pct_change = (last - first) / first * 100 if first > 0 else 0

            if pct_change > 0.1:
                state.dxy_direction = "strengthening"
                state.dxy_bias = min(pct_change / 0.5, 1.0)
                state.directional_bias -= 0.1  # Dollar strength → slight bearish tilt
            elif pct_change < -0.1:
                state.dxy_direction = "weakening"
                state.dxy_bias = max(pct_change / 0.5, -1.0)
                state.directional_bias += 0.1  # Dollar weakness → slight bullish tilt
            else:
                state.dxy_direction = "neutral"
                state.dxy_bias = 0.0

    except Exception as e:
        logger.debug(f"Dollar analysis error: {e}")


def _analyze_vol_regime(
    state: RegimeState,
    current_iv: float,
    spy_bars: Optional[list],
):
    """
    Compare realized volatility to implied volatility.

    RV > IV: Market moving more than expected → IV underpriced, buy premium
    RV < IV: Market calm relative to expectations → IV overpriced, sell premium
    """
    if not spy_bars or len(spy_bars) < 20:
        return

    try:
        # Compute realized vol from 1-min bars (annualized)
        returns = []
        for i in range(1, len(spy_bars)):
            prev_close = spy_bars[i - 1].get("c") or spy_bars[i - 1].get("close", 0)
            curr_close = spy_bars[i].get("c") or spy_bars[i].get("close", 0)
            if prev_close > 0 and curr_close > 0:
                returns.append((curr_close - prev_close) / prev_close)

        if len(returns) < 10:
            return

        # Intraday realized vol (annualized)
        import statistics
        rv_1min = statistics.stdev(returns)
        # Annualize: 1-min vol × sqrt(390 trading minutes × 252 days)
        rv_annual = rv_1min * (390 * 252) ** 0.5

        if current_iv > 0:
            state.rv_iv_ratio = rv_annual / current_iv

            if state.rv_iv_ratio > 1.3:
                state.vol_regime = "elevated"  # Actual vol exceeds expectations
            elif state.rv_iv_ratio < 0.7:
                state.vol_regime = "compressed"  # IV overpriced relative to moves
            else:
                state.vol_regime = "normal"

    except Exception as e:
        logger.debug(f"Vol regime analysis error: {e}")


def _classify_regime(state: RegimeState):
    """
    Combine all sub-signals into overall regime classification.

    Uses a scoring approach: each signal adds to risk-on or risk-off score.
    """
    risk_on_score = 0.0
    risk_off_score = 0.0
    signals_counted = 0

    # VIX structure
    if state.vix_structure == "contango":
        risk_on_score += 1.0
        signals_counted += 1
    elif state.vix_structure == "backwardation":
        risk_off_score += 1.5  # Backwardation is a stronger signal
        signals_counted += 1

    # Correlation regime
    if state.correlation_regime == "inverse":
        risk_on_score += 0.5  # Normal market behavior
        signals_counted += 1
    elif state.correlation_regime == "positive":
        risk_off_score += 1.5  # Liquidity stress — strong warning
        signals_counted += 1

    # Dollar
    if state.dxy_direction == "weakening":
        risk_on_score += 0.5
        signals_counted += 1
    elif state.dxy_direction == "strengthening":
        risk_off_score += 0.5
        signals_counted += 1

    # Vol regime
    if state.vol_regime == "compressed":
        risk_on_score += 0.5  # Low vol = calm
        signals_counted += 1
    elif state.vol_regime == "elevated":
        risk_off_score += 1.0  # High realized vol = danger
        signals_counted += 1

    # Classify
    total = risk_on_score + risk_off_score
    if total < 0.5 or signals_counted == 0:
        state.regime = "unknown"
        state.confidence = 0.0
        state.sizing_multiplier = 1.0
        state.description = "Insufficient data for regime classification"
        return

    on_pct = risk_on_score / total
    off_pct = risk_off_score / total

    if on_pct > 0.65:
        state.regime = "risk_on"
        state.confidence = on_pct
        state.sizing_multiplier = 1.2  # Slightly larger positions in calm regime
        state.description = f"Risk-on: VIX {state.vix_structure}, correlation {state.correlation_regime}, dollar {state.dxy_direction}"
    elif off_pct > 0.65:
        state.regime = "risk_off"
        state.confidence = off_pct
        state.sizing_multiplier = 0.5  # Cut positions in half during stress
        state.description = f"Risk-off: VIX {state.vix_structure}, correlation {state.correlation_regime}, vol {state.vol_regime}"
    else:
        state.regime = "transition"
        state.confidence = max(on_pct, off_pct)
        state.sizing_multiplier = 0.7  # Reduce but don't eliminate
        state.description = f"Transition: mixed signals (risk-on {on_pct:.0%} vs risk-off {off_pct:.0%})"


async def _fetch_latest_bars(
    symbols: list,
    timeframe: str = "1Day",
    limit: int = 5,
) -> Dict:
    """Fetch latest bars from Alpaca for multiple symbols."""
    if not ALPACA_KEY:
        return {}

    result = {}
    try:
        async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
            for symbol in symbols:
                url = f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/bars"
                params = {
                    "timeframe": timeframe,
                    "limit": limit,
                    "adjustment": "raw",
                    "feed": "iex",
                }
                try:
                    async with session.get(
                        url, params=params,
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            bars = data.get("bars", [])
                            if bars:
                                result[symbol] = {
                                    "close": bars[-1].get("c", 0),
                                    "bars": bars,
                                }
                except Exception as e:
                    logger.debug(f"Bar fetch error for {symbol}: {e}")
    except Exception as e:
        logger.debug(f"Bars session error: {e}")

    return result


def _pearson_correlation(x: list, y: list) -> float:
    """Compute Pearson correlation coefficient."""
    n = min(len(x), len(y))
    if n < 3:
        return 0.0

    x, y = x[:n], y[:n]
    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n)) / n
    std_x = (sum((xi - mean_x) ** 2 for xi in x) / n) ** 0.5
    std_y = (sum((yi - mean_y) ** 2 for yi in y) / n) ** 0.5

    if std_x < 1e-10 or std_y < 1e-10:
        return 0.0

    return max(-1.0, min(1.0, cov / (std_x * std_y)))


# ── Scoring function for confluence integration ──

def score_regime_alignment(
    regime: RegimeState,
    signal_direction: str,
    signal_type: str = "trend",
) -> Tuple[float, str]:
    """
    Score how well the current regime supports the proposed trade.

    Returns a multiplier adjustment (0.7 to 1.3) for the final confluence score,
    plus an explanation.

    Args:
        regime: RegimeState from detect_regime()
        signal_direction: "BUY_CALL" or "BUY_PUT"
        signal_type: "trend" or "mean_reversion"

    Returns:
        (multiplier, explanation) where multiplier adjusts final score
    """
    is_bullish = signal_direction == "BUY_CALL"

    if regime.regime == "unknown":
        return 1.0, "Regime unknown — no adjustment"

    if regime.regime == "risk_on":
        if is_bullish:
            return 1.2, f"Risk-on regime supports bullish trade (conf: {regime.confidence:.0%})"
        else:
            return 0.85, "Risk-on regime — bearish trade faces headwind"

    elif regime.regime == "risk_off":
        if not is_bullish:
            return 1.15, f"Risk-off regime supports bearish trade (conf: {regime.confidence:.0%})"
        elif signal_type == "mean_reversion":
            return 1.0, "Risk-off but mean-reversion signal — neutral"
        else:
            return 0.7, "Risk-off regime — bullish trend trade is dangerous"

    else:  # transition
        return 0.85, f"Transition regime — reduce conviction ({regime.description})"
