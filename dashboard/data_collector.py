"""
Data Collector — Aggregates all provider data into a structured MarketSnapshot.

Gathers: price, VWAP, levels, order flow state, setups detected, GEX, sweeps,
regime, positions, daily P&L — everything the Market Brain needs in one call.
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MarketSnapshot:
    """Complete market state for one analysis cycle."""
    timestamp: str = ""
    symbol: str = "SPY"

    # Price
    price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    prev_close: float = 0.0
    change_pct: float = 0.0

    # Session
    session_phase: str = ""       # opening_drive, midday_chop, afternoon_trend, etc.
    minutes_to_close: int = 0
    is_0dte: bool = True

    # Levels
    vwap: float = 0.0
    hod: float = 0.0
    lod: float = 0.0
    poc: float = 0.0
    orb_high: float = 0.0
    orb_low: float = 0.0

    # Order flow
    cvd: float = 0.0
    cvd_trend: str = ""           # rising, falling, neutral
    imbalance: float = 0.0        # 0.5 = neutral, >0.5 = buy bias
    large_trade_count: int = 0
    large_trade_bias: str = ""    # buy, sell, neutral
    absorption_detected: bool = False
    absorption_bias: str = ""

    # Regime
    regime: str = ""              # bullish, bearish, neutral
    vix: float = 0.0
    vol_regime: str = ""          # low, medium, high

    # GEX
    gex_regime: str = ""          # positive, negative
    gex_flip: float = 0.0
    max_gamma_strike: float = 0.0

    # Sweeps
    sweep_count: int = 0
    sweep_direction: str = ""     # bullish, bearish, mixed
    sweep_notional: float = 0.0

    # Setups detected
    setups: List[Dict[str, Any]] = field(default_factory=list)

    # Options analytics
    iv_rank: float = 0.0
    pcr: float = 0.0
    max_pain: float = 0.0

    # Options flow (from ThetaData real-time stream)
    options_vpin: float = 0.0
    options_vpin_level: str = ""
    options_pcr_premium: float = 0.0
    options_high_sms_count: int = 0
    options_sweep_count: int = 0
    options_buy_premium: float = 0.0
    options_sell_premium: float = 0.0

    # Positions
    open_positions: List[Dict[str, Any]] = field(default_factory=list)
    daily_pnl: float = 0.0
    daily_trades: int = 0
    daily_wins: int = 0
    daily_losses: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_prompt(self) -> str:
        """Format as structured text for the LLM prompt (~800-1200 tokens)."""
        change_sign = "+" if self.change_pct >= 0 else ""
        lines = [
            f"TIMESTAMP: {self.timestamp}",
            f"PRICE: {self.symbol} ${self.price:.2f} ({change_sign}{self.change_pct:.2f}%)",
            f"BID/ASK: ${self.bid:.2f} / ${self.ask:.2f}",
            f"SESSION: {self.session_phase}, {self.minutes_to_close} min to close, {'0DTE' if self.is_0dte else 'swing'}",
            "",
            f"LEVELS: VWAP ${self.vwap:.2f}, HOD ${self.hod:.2f}, LOD ${self.lod:.2f}, POC ${self.poc:.2f}",
        ]
        if self.orb_high > 0:
            lines.append(f"  ORB: ${self.orb_high:.2f} / ${self.orb_low:.2f}")

        # Order flow
        imb_pct = self.imbalance * 100
        lines.append(f"ORDER FLOW: CVD {self.cvd:+.0f} ({self.cvd_trend}), Imbalance {imb_pct:.0f}% buy")
        if self.large_trade_count > 0:
            lines.append(f"  Large trades: {self.large_trade_count} ({self.large_trade_bias} bias)")
        if self.absorption_detected:
            lines.append(f"  Absorption: {self.absorption_bias}")

        # Regime & vol
        lines.append(f"REGIME: {self.regime}, VIX {self.vix:.1f}, Vol: {self.vol_regime}")

        # GEX
        if self.gex_flip > 0:
            lines.append(f"GEX: {self.gex_regime}, Flip ${self.gex_flip:.2f}, Max gamma ${self.max_gamma_strike:.2f}")

        # Sweeps
        if self.sweep_count > 0:
            lines.append(f"SWEEPS: {self.sweep_count} ({self.sweep_direction}), ${self.sweep_notional/1000:.0f}K notional")

        # Setups
        if self.setups:
            setup_strs = []
            for s in self.setups[:3]:
                setup_strs.append(f"{s.get('name', '?')} (quality {s.get('quality', 0):.2f})")
            lines.append(f"SETUPS: {', '.join(setup_strs)}")
        else:
            lines.append("SETUPS: None detected")

        # Options
        lines.append(f"OPTIONS: IV Rank {self.iv_rank:.0f}, PCR {self.pcr:.2f}, Max Pain ${self.max_pain:.2f}")
        if self.options_vpin > 0:
            lines.append(
                f"OPTIONS FLOW: VPIN {self.options_vpin:.0%} ({self.options_vpin_level}), "
                f"PCR(premium) {self.options_pcr_premium:.2f}, "
                f"SMS70+ {self.options_high_sms_count}, Sweeps {self.options_sweep_count}"
            )
            if self.options_buy_premium > 0 or self.options_sell_premium > 0:
                total = self.options_buy_premium + self.options_sell_premium
                buy_pct = (self.options_buy_premium / total * 100) if total > 0 else 50
                lines.append(
                    f"  Premium: ${self.options_buy_premium/1000:.0f}K buy / ${self.options_sell_premium/1000:.0f}K sell ({buy_pct:.0f}% buy)"
                )

        # Positions & P&L
        if self.open_positions:
            for pos in self.open_positions[:3]:
                pnl = pos.get("unrealized_pnl", 0)
                pnl_pct = pos.get("unrealized_pnl_pct", 0)
                lines.append(
                    f"POSITION: {pos.get('strike', '?')} {pos.get('option_type', '?')} "
                    f"entry ${pos.get('entry_price', 0):.2f}, "
                    f"current ${pos.get('current_price', 0):.2f} "
                    f"({'+'if pnl>=0 else ''}{pnl:.2f}, {pnl_pct:+.1f}%)"
                )
        else:
            lines.append("POSITIONS: None open")

        w_r = f"{self.daily_wins}W/{self.daily_losses}L" if self.daily_trades > 0 else "no trades"
        lines.append(f"DAILY P&L: ${self.daily_pnl:+.2f} ({self.daily_trades} trades, {w_r})")

        return "\n".join(lines)


async def collect_snapshot(engine: Any, signal_history: Any = None) -> MarketSnapshot:
    """
    Collect a full market snapshot from all data providers.
    `engine` is the SignalEngine instance with cached data.
    """
    snap = MarketSnapshot()
    snap.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        # Price from engine's cached quote
        quote = getattr(engine, '_cached_quote', None) or {}
        snap.price = float(quote.get("last", 0) or quote.get("price", 0) or 0)
        snap.bid = float(quote.get("bid", 0) or 0)
        snap.ask = float(quote.get("ask", 0) or 0)
        snap.prev_close = float(quote.get("prev_close", 0) or 0)

        # Fallback: fetch from REST if engine cache is empty
        if snap.price <= 0:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get("http://localhost:8000/api/market", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            spy = data.get("spy", {})
                            snap.price = float(spy.get("price", 0))
                            snap.bid = float(spy.get("bid", 0) or 0)
                            snap.ask = float(spy.get("ask", 0) or 0)
            except Exception:
                pass

        if snap.prev_close > 0 and snap.price > 0:
            snap.change_pct = ((snap.price - snap.prev_close) / snap.prev_close) * 100
    except Exception as e:
        logger.debug(f"[DataCollector] Price error: {e}")

    try:
        # Session context
        from .confluence import get_session_context
        session = get_session_context()
        snap.session_phase = session.phase if session else ""
        snap.minutes_to_close = session.minutes_to_close if session else 0
        snap.is_0dte = session.is_0dte if session else True
    except Exception as e:
        logger.debug(f"[DataCollector] Session error: {e}")

    try:
        # Market levels
        from .market_levels import get_current_levels
        levels = get_current_levels()
        if levels:
            snap.vwap = levels.get("vwap", 0) or 0
            snap.hod = levels.get("hod", 0) or 0
            snap.lod = levels.get("lod", 0) or 0
            snap.poc = levels.get("poc", 0) or 0
            snap.orb_high = levels.get("orb_high", 0) or 0
            snap.orb_low = levels.get("orb_low", 0) or 0

        # Fallback: compute from bars if levels module returned zeros
        if snap.vwap <= 0 and snap.price > 0:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get("http://localhost:8000/api/bars?symbol=SPY&timeframe=5Min&limit=80", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            bars = data.get("bars", [])
                            if bars:
                                highs = [b.get("high", b.get("h", 0)) for b in bars]
                                lows = [b.get("low", b.get("l", 0)) for b in bars]
                                vwaps = [b.get("vwap", 0) for b in bars if b.get("vwap")]
                                snap.hod = max(h for h in highs if h > 0) if any(h > 0 for h in highs) else 0
                                snap.lod = min(l for l in lows if l > 0) if any(l > 0 for l in lows) else 0
                                if vwaps:
                                    snap.vwap = vwaps[-1]  # Most recent bar's VWAP
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"[DataCollector] Levels error: {e}")

    try:
        # Order flow from confluence
        from .confluence import analyze_order_flow
        flow = getattr(engine, '_cached_flow', None)
        if flow:
            snap.cvd = getattr(flow, 'cvd', 0) or 0
            snap.cvd_trend = getattr(flow, 'cvd_trend', '') or ''
            snap.imbalance = getattr(flow, 'imbalance', 0.5) or 0.5
            snap.large_trade_count = getattr(flow, 'large_trade_count', 0) or 0
            snap.large_trade_bias = getattr(flow, 'large_trade_bias', '') or ''
            snap.absorption_detected = getattr(flow, 'absorption_detected', False)
            snap.absorption_bias = getattr(flow, 'absorption_bias', '') or ''
    except Exception as e:
        logger.debug(f"[DataCollector] Flow error: {e}")

    try:
        # Regime
        regime = getattr(engine, '_cached_regime', None)
        if regime:
            snap.regime = getattr(regime, 'classification', '') or ''
            snap.vix = getattr(regime, 'vix_level', 0) or 0
            snap.vol_regime = getattr(regime, 'vix_regime', '') or ''
    except Exception as e:
        logger.debug(f"[DataCollector] Regime error: {e}")

    try:
        # GEX
        gex = getattr(engine, '_cached_gex', None)
        if gex:
            snap.gex_regime = getattr(gex, 'regime', '') or ''
            snap.gex_flip = getattr(gex, 'flip_level', 0) or 0
            snap.max_gamma_strike = getattr(gex, 'max_gamma_strike', 0) or 0
    except Exception as e:
        logger.debug(f"[DataCollector] GEX error: {e}")

    try:
        # Sweeps
        sweeps = getattr(engine, '_cached_sweeps', None)
        if sweeps:
            snap.sweep_count = getattr(sweeps, 'sweep_count', 0) or 0
            snap.sweep_direction = getattr(sweeps, 'aggression_level', '') or ''
            snap.sweep_notional = getattr(sweeps, 'total_notional', 0) or 0
    except Exception as e:
        logger.debug(f"[DataCollector] Sweeps error: {e}")

    try:
        # Setup detection
        from .setup_detector import setup_detector
        if hasattr(setup_detector, 'last_setups') and setup_detector.last_setups:
            for s in setup_detector.last_setups:
                snap.setups.append({
                    "name": getattr(s, 'setup_name', ''),
                    "direction": getattr(s, 'direction', ''),
                    "quality": getattr(s, 'quality', 0),
                    "trigger_price": getattr(s, 'trigger_price', 0),
                    "trigger_detail": getattr(s, 'trigger_detail', ''),
                })
    except Exception as e:
        logger.debug(f"[DataCollector] Setups error: {e}")

    try:
        # Options analytics
        analytics = getattr(engine, '_cached_options_analytics', None)
        if analytics:
            snap.iv_rank = getattr(analytics, 'iv_rank', 0) or 0
            snap.pcr = getattr(analytics, 'pcr', 0) or 0
            snap.max_pain = getattr(analytics, 'max_pain', 0) or 0
    except Exception as e:
        logger.debug(f"[DataCollector] Options analytics error: {e}")

    try:
        # ThetaData real-time options flow
        opts_flow = getattr(engine, '_cached_options_flow', None)
        if opts_flow:
            snap.options_vpin = opts_flow.get("vpin", 0) or 0
            snap.options_vpin_level = opts_flow.get("vpin_level", "")
            snap.options_pcr_premium = opts_flow.get("pcr_premium", 0) or 0
            snap.options_high_sms_count = opts_flow.get("high_sms_count", 0)
            snap.options_sweep_count = opts_flow.get("sweep_count", 0)
            snap.options_buy_premium = opts_flow.get("buy_premium", 0)
            snap.options_sell_premium = opts_flow.get("sell_premium", 0)
    except Exception as e:
        logger.debug(f"[DataCollector] Options flow error: {e}")

    try:
        # Open positions
        from .pm_api import get_positions_data
        positions = get_positions_data()
        if positions:
            snap.open_positions = positions.get("positions", [])
    except Exception as e:
        logger.debug(f"[DataCollector] Positions error: {e}")

    try:
        # Daily P&L
        from .pm_api import get_daily_stats
        stats = get_daily_stats()
        if stats:
            snap.daily_pnl = stats.get("total_pnl", 0) or 0
            snap.daily_trades = stats.get("trades_today", 0) or 0
            snap.daily_wins = stats.get("wins", 0) or 0
            snap.daily_losses = stats.get("losses", 0) or 0
    except Exception as e:
        logger.debug(f"[DataCollector] Daily stats error: {e}")

    return snap
