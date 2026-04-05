"""
Signal Engine — Main analysis pipeline (v4: 15-factor scoring).

Combines all analysis components: market structure, order flow, confluence,
GEX/DEX analysis, options analytics, strike selection, risk management,
vanna/charm, regime detection, event calendar, sweep detection, VPIN,
and sector divergence.

v4: 15-factor scoring with regime + event multipliers. Includes
sweep detection, flow toxicity (VPIN), and sector divergence signals.
"""

from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
import logging

from .config import cfg
from .market_levels import MarketLevels, compute_market_levels
from .confluence import (
    OrderFlowState,
    SessionContext,
    ConfluenceFactor,
    analyze_order_flow,
    get_session_context,
    evaluate_confluence,
    select_strike,
    calculate_risk,
    _get_nearest_expiry,
    ACCOUNT_BALANCE,
    SYMBOL,
    TIER_TEXTBOOK,
    TIER_HIGH,
    TIER_VALID,
)
from .gex_engine import calculate_gex, GEXResult
from .options_analytics import analyze_options, store_daily_iv, OptionsAnalytics
from .vanna_charm_engine import calculate_vanna_charm, VannaCharmResult
from .regime_detector import RegimeState
from .event_calendar import EventContext
from .sweep_detector import SweepAnalysis
from .flow_toxicity import VPINState
from .sector_monitor import SectorAnalysis
from .market_internals import MarketBreadth
from .vol_analyzer import VolAnalysis, analyze_vol

logger = logging.getLogger(__name__)


class SignalEngine:
    """
    Production signal engine that combines all analysis components.
    Fetches data server-side and produces fully qualified trading signals.
    """

    def __init__(self, symbol: str = SYMBOL):
        self.symbol = symbol
        self._bars_1m_cache: List[Dict] = []
        self._bars_daily_cache: List[Dict] = []
        self._chain_cache: Optional[Dict] = None
        self._options_snapshot_cache: Optional[Dict] = None

    async def fetch_market_data(self, app_request=None) -> Dict[str, Any]:
        """
        Fetch all required market data from internal API endpoints.
        This runs server-side, so no external network needed from frontend.
        """
        import aiohttp

        base = cfg.DASHBOARD_BASE_URL
        data = {
            "bars_1m": [],
            "bars_daily": [],
            "quote": {},
            "market": {},
            "chain": {},
            "options_snapshot": {},
        }

        try:
            async with aiohttp.ClientSession() as session:
                # Fetch all data in parallel
                import asyncio

                async def fetch_json(url):
                    try:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=cfg.SIGNAL_FETCH_TIMEOUT)) as resp:
                            if resp.status == 200:
                                return await resp.json()
                    except Exception as e:
                        logger.debug(f"Fetch {url} failed: {e}")
                    return None

                # Determine today's expiry for options
                expiry = _get_nearest_expiry()

                results = await asyncio.gather(
                    fetch_json(f"{base}/api/bars?symbol={self.symbol}&timeframe=1Min&limit={cfg.SIGNAL_BARS_1M_LIMIT}"),
                    fetch_json(f"{base}/api/bars?symbol={self.symbol}&timeframe=1D&limit={cfg.SIGNAL_BARS_DAILY_LIMIT}"),
                    fetch_json(f"{base}/api/market?symbol={self.symbol}"),
                    fetch_json(f"{base}/api/quote?symbol={self.symbol}"),
                    fetch_json(f"{base}/api/options/chain?root={self.symbol}&exp={expiry}"),
                    fetch_json(f"{base}/api/options/snapshot?root={self.symbol}&exp={expiry}"),
                    return_exceptions=True,
                )

                bars_1m_resp, bars_daily_resp, market_resp, quote_resp, chain_resp, snap_resp = results

                if bars_1m_resp and not isinstance(bars_1m_resp, Exception):
                    data["bars_1m"] = bars_1m_resp.get("bars", [])
                if bars_daily_resp and not isinstance(bars_daily_resp, Exception):
                    data["bars_daily"] = bars_daily_resp.get("bars", [])
                if market_resp and not isinstance(market_resp, Exception):
                    data["market"] = market_resp.get("spy") or {}
                if quote_resp and not isinstance(quote_resp, Exception):
                    data["quote"] = quote_resp
                if chain_resp and not isinstance(chain_resp, Exception):
                    data["chain"] = chain_resp
                if snap_resp and not isinstance(snap_resp, Exception):
                    data["options_snapshot"] = snap_resp

        except Exception as e:
            logger.error(f"Failed to fetch market data: {e}")

        return data

    def analyze(
        self,
        trades: List[Dict],
        quote: Dict,
        options_data: Optional[Dict] = None,
        bars_1m: Optional[List[Dict]] = None,
        bars_daily: Optional[List[Dict]] = None,
        chain: Optional[Dict] = None,
        account_balance: float = ACCOUNT_BALANCE,
    ) -> Dict[str, Any]:
        """
        Full analysis pipeline: levels -> flow -> context -> GEX/DEX -> confluence -> signal.

        v2: Now computes GEX/DEX and options analytics from chain data
        and passes them to evaluate_confluence() for 10-factor scoring.
        """
        try:
            # ── 1. Validate minimum data (with diagnostic tracking) ──
            self._last_diagnostics = {}

            if not trades or len(trades) < cfg.SIGNAL_MIN_TRADES:
                reason = f"Insufficient trade data ({len(trades) if trades else 0}/{cfg.SIGNAL_MIN_TRADES} required)"
                self._last_diagnostics = {
                    "blocked_at": "gate_1_trades",
                    "reason": reason,
                    "trade_count": len(trades) if trades else 0,
                }
                logger.info(f"[SignalEngine] Gate 1 BLOCKED: {reason}")
                return self._no_trade(reason)

            price = quote.get("last", 0) or quote.get("price", 0)
            if price <= 0:
                self._last_diagnostics = {
                    "blocked_at": "gate_2_quote",
                    "reason": "No valid price data",
                    "quote_keys": list(quote.keys()) if quote else [],
                }
                logger.info(f"[SignalEngine] Gate 2 BLOCKED: No valid price — quote={quote}")
                return self._no_trade("No valid price data")

            # ── 2. Compute market structure levels ──
            levels = compute_market_levels(
                bars_1m=bars_1m or self._bars_1m_cache,
                bars_daily=bars_daily or self._bars_daily_cache,
                quote=quote,
            )
            levels.current_price = price

            # Update cache
            if bars_1m:
                self._bars_1m_cache = bars_1m
            if bars_daily:
                self._bars_daily_cache = bars_daily

            # ── 3. Analyze order flow ──
            flow = analyze_order_flow(trades, levels)

            # ── 4. Get session context ──
            session = get_session_context()

            # ── 4b. Compute GEX/DEX from chain data (v2) ──
            gex_data: Optional[GEXResult] = None
            chain_analytics: Optional[OptionsAnalytics] = None
            chain_to_use = chain or self._chain_cache

            if chain_to_use and price > 0:
                calls = chain_to_use.get("calls", [])
                puts = chain_to_use.get("puts", [])
                logger.debug(
                    f"[SignalEngine] Chain data: {len(calls)} calls, {len(puts)} puts, "
                    f"source={'param' if chain else 'cache'}"
                )

                if calls or puts:
                    try:
                        gex_data = calculate_gex(calls, puts, price)
                    except Exception as e:
                        logger.debug(f"GEX calculation failed: {e}")

                    try:
                        chain_analytics = analyze_options(calls, puts, price, self.symbol)
                        # Store daily IV for IV Rank history (once per day, idempotent)
                        if chain_analytics and chain_analytics.atm_iv > 0:
                            store_daily_iv(self.symbol, chain_analytics.atm_iv)
                    except Exception as e:
                        logger.debug(f"Options analytics failed: {e}")

            # ── 4c. Compute vanna/charm from chain data (v3) ──
            vanna_charm_data: Optional[VannaCharmResult] = None
            if chain_to_use and price > 0:
                calls = chain_to_use.get("calls", [])
                puts = chain_to_use.get("puts", [])
                if calls or puts:
                    try:
                        vanna_charm_data = calculate_vanna_charm(calls, puts, price)
                    except Exception as e:
                        logger.debug(f"Vanna/charm calculation failed: {e}")

            # ── 4d. Detect market regime (v3, async-safe sync wrapper) ──
            regime_state: Optional[RegimeState] = None
            # Regime detection is async; store cached result from signal_api layer
            # or use a sync fallback
            regime_state = getattr(self, '_cached_regime', None)

            # ── 4e. Get event context (v3, sync wrapper) ──
            event_ctx: Optional[EventContext] = None
            event_ctx = getattr(self, '_cached_event_context', None)

            # ── 4f. Get sweep analysis (v4, cached from signal_api) ──
            sweep_data: Optional[SweepAnalysis] = getattr(self, '_cached_sweeps', None)

            # ── 4g. Get VPIN state (v4, cached from signal_api) ──
            vpin_state: Optional[VPINState] = getattr(self, '_cached_vpin', None)

            # ── 4h. Get sector divergence (v4, cached from signal_api) ──
            sector_data: Optional[SectorAnalysis] = getattr(self, '_cached_sectors', None)

            # ── 4i. Get agent verdicts (v5, cached from signal_api) ──
            agent_verdicts: Optional[dict] = getattr(self, '_cached_agent_verdicts', None)

            # ── 4j. Get market breadth (v8, cached from signal_api) ──
            breadth_data: Optional[MarketBreadth] = getattr(self, '_cached_breadth', None)

            # ── 4k. Compute IV vs Realized Vol (v10) ──
            vol_data: Optional[VolAnalysis] = None
            if chain_analytics and chain_analytics.atm_iv > 0 and levels.realized_vol > 0:
                try:
                    vol_data = analyze_vol(
                        atm_iv=chain_analytics.atm_iv,
                        realized_vol=levels.realized_vol,
                        iv_rank=chain_analytics.iv_rank,
                        daily_bars=bars_daily,
                    )
                except Exception as e:
                    logger.debug(f"Vol analysis failed: {e}")

            # ── 4l. IV Rank veto via ThetaData (v11) ──
            iv_rank_value = None
            if chain_analytics and chain_analytics.iv_rank is not None:
                iv_rank_value = chain_analytics.iv_rank / 100.0  # normalize 0-100 → 0-1
            if iv_rank_value is not None and iv_rank_value > 0.80:
                logger.info(f"[SignalEngine] IV rank veto: {iv_rank_value:.0%} > 80% — options overpriced, skipping")
                return self._no_trade(f"IV rank {iv_rank_value:.0%} exceeds 80% threshold — options overpriced")

            # ── 5. Evaluate confluence (v10: 23-factor + regime + events + agents) ──
            action, confidence, factors = evaluate_confluence(
                flow, levels, session, options_data,
                gex_data=gex_data,
                chain_analytics=chain_analytics,
                vanna_charm_data=vanna_charm_data,
                regime_state=regime_state,
                event_context=event_ctx,
                sweep_data=sweep_data,
                vpin_state=vpin_state,
                sector_data=sector_data,
                agent_verdicts=agent_verdicts,
                breadth_data=breadth_data,
                vol_data=vol_data,
            )

            # ── 6. If no trade, return early ──
            if action == "NO_TRADE":
                bull_f = sum(1 for f in factors if f.direction == "bullish")
                bear_f = sum(1 for f in factors if f.direction == "bearish")
                total_f = len(factors)
                self._last_diagnostics = {
                    "blocked_at": "gate_5_confluence",
                    "reason": f"Confluence returned NO_TRADE (conf={confidence:.3f})",
                    "confidence": round(confidence, 3),
                    "bull_factors": bull_f,
                    "bear_factors": bear_f,
                    "total_factors": total_f,
                    "chain_available": bool(chain_to_use),
                    "factor_names": [f.name for f in factors],
                }
                logger.info(
                    f"[SignalEngine] Gate 5 NO_TRADE: conf={confidence:.3f} "
                    f"bull={bull_f} bear={bear_f} total={total_f} "
                    f"factors=[{', '.join(f.name for f in factors[:6])}...]"
                )
                return self._build_signal(
                    action="NO_TRADE",
                    confidence=confidence,
                    levels=levels,
                    flow=flow,
                    session=session,
                    factors=factors,
                    reason=self._no_trade_reason(factors, flow, session),
                    gex_data=gex_data,
                    chain_analytics=chain_analytics,
                )

            # ── 7. Select strike from real chain ──
            strike_info = select_strike(
                action=action,
                current_price=price,
                chain=chain or self._chain_cache,
                target_delta=cfg.TARGET_DELTA,
            )
            if chain:
                self._chain_cache = chain

            # ── 7b. Block signal if no valid strike/entry (no chain data) ──
            chain_used = chain or self._chain_cache
            chain_calls = len(chain_used.get("calls", [])) if chain_used else 0
            chain_puts = len(chain_used.get("puts", [])) if chain_used else 0

            if not strike_info or not strike_info.get("strike") or strike_info.get("entry_price", 0) <= 0:
                no_chain_reason = (
                    f"No valid options chain for {action} — strike selection returned "
                    f"strike={strike_info.get('strike', 0) if strike_info else 0}, "
                    f"entry={strike_info.get('entry_price', 0) if strike_info else 0}, "
                    f"source={strike_info.get('source', 'none') if strike_info else 'none'}"
                )
                self._last_diagnostics = {
                    "blocked_at": "gate_4_strike",
                    "reason": no_chain_reason,
                    "action": action,
                    "confidence": round(confidence, 3),
                    "chain_calls": chain_calls,
                    "chain_puts": chain_puts,
                    "chain_source": "param" if chain else ("cache" if self._chain_cache else "none"),
                    "strike_info": strike_info,
                }
                logger.warning(f"[SignalEngine] Gate 4 BLOCKED: {no_chain_reason} "
                              f"(chain: {chain_calls}C/{chain_puts}P)")
                return self._build_signal(
                    action="NO_TRADE",
                    confidence=confidence,
                    levels=levels,
                    flow=flow,
                    session=session,
                    factors=factors,
                    reason=no_chain_reason,
                    gex_data=gex_data,
                    chain_analytics=chain_analytics,
                )

            # ── 7c. Spread quality / liquidity gate (v11: ThetaData) ──
            try:
                from .api_routes import get_spread_analysis
                import asyncio
                expiry_str = strike_info.get("expiry", _get_nearest_expiry()).replace("-", "")
                right = "C" if action == "BUY_CALL" else "P"
                loop = asyncio.get_event_loop()
                spread_data = loop.run_until_complete(
                    get_spread_analysis(self.symbol, expiry_str, strike_info["strike"], right, expiry_str)
                ) if not loop.is_running() else {}
                liq_score = spread_data.get("liquidity_score")
                avg_spread = spread_data.get("avg_spread", 0)
                mid_price = strike_info.get("entry_price", 1)
                spread_pct = (avg_spread / mid_price * 100) if mid_price > 0 else 0
                if liq_score is not None and (liq_score < 30 or spread_pct > 5.0):
                    logger.warning(f"[SignalEngine] Liquidity gate: score={liq_score}, spread={spread_pct:.1f}% — skipping")
                    return self._no_trade(f"Poor liquidity: score={liq_score}/100, spread={spread_pct:.1f}% of mid")
            except Exception as e:
                logger.debug(f"[SignalEngine] Spread analysis unavailable, skipping gate: {e}")

            # Signal passed all gates!
            self._last_diagnostics = {
                "blocked_at": None,
                "status": "SIGNAL_GENERATED",
                "action": action,
                "confidence": round(confidence, 3),
                "strike": strike_info.get("strike"),
                "entry_price": strike_info.get("entry_price"),
                "chain_calls": chain_calls,
                "chain_puts": chain_puts,
            }
            logger.info(
                f"[SignalEngine] SIGNAL PASSED ALL GATES: {action} "
                f"conf={confidence:.3f} strike={strike_info.get('strike')} "
                f"entry=${strike_info.get('entry_price', 0):.2f}"
            )

            # ── 8. Calculate risk (v10: GEX regime + IV/RV vol adjustment) ──
            risk = calculate_risk(
                confidence=confidence,
                entry_price=strike_info["entry_price"],
                levels=levels,
                session=session,
                account_balance=account_balance,
                iv=strike_info.get("iv"),
                delta=strike_info.get("delta"),
                direction=action,  # BUY_CALL or BUY_PUT — for level-aware exits
                gex_data=gex_data,  # v9: regime-based target/stop/size adjustment
                vol_data=vol_data,  # v10: IV vs RV cheap/expensive adjustment
            )

            # ── 9. Build final signal ──
            return self._build_signal(
                action=action,
                confidence=confidence,
                levels=levels,
                flow=flow,
                session=session,
                factors=factors,
                strike_info=strike_info,
                risk=risk,
                gex_data=gex_data,
                chain_analytics=chain_analytics,
            )

        except Exception as e:
            logger.error(f"Signal engine error: {e}", exc_info=True)
            return self._no_trade(f"Analysis error: {str(e)}")

    def _build_signal(
        self,
        action: str,
        confidence: float,
        levels: MarketLevels,
        flow: OrderFlowState,
        session: SessionContext,
        factors: List[ConfluenceFactor],
        strike_info: Optional[Dict] = None,
        risk: Optional[Dict] = None,
        reason: Optional[str] = None,
        gex_data: Optional[Any] = None,
        chain_analytics: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Construct the final signal response object (v2: includes GEX/DEX data)."""

        # Determine confidence tier name
        if confidence >= TIER_TEXTBOOK:
            tier = "TEXTBOOK"
        elif confidence >= TIER_HIGH:
            tier = "HIGH"
        elif confidence >= TIER_VALID:
            tier = "VALID"
        else:
            tier = "DEVELOPING"

        # Build human-readable reasoning
        if not reason:
            bull_factors = [f for f in factors if f.direction == "bullish"]
            bear_factors = [f for f in factors if f.direction == "bearish"]
            active = bull_factors if action == "BUY_CALL" else bear_factors

            reason_parts = []
            for f in active[:4]:
                reason_parts.append(f"{f.name}: {f.detail}")
            if len(active) > 4:
                reason_parts.append(f"+{len(active) - 4} more confirming factors")

            reason = " | ".join(reason_parts) if reason_parts else "Developing setup"

        signal = {
            "signal": action,
            "symbol": self.symbol,
            "confidence": round(confidence, 3),
            "tier": tier,
            "timestamp": datetime.now(timezone.utc).isoformat(),

            # Strike & pricing
            "strike": strike_info["strike"] if strike_info else None,
            "expiry": strike_info["expiry"] if strike_info else _get_nearest_expiry(),
            "entry_price": strike_info["entry_price"] if strike_info else None,
            "bid": strike_info.get("bid") if strike_info else None,
            "ask": strike_info.get("ask") if strike_info else None,
            "option_delta": strike_info.get("delta") if strike_info else None,
            "option_iv": strike_info.get("iv") if strike_info else None,
            "strike_source": strike_info.get("source", "none") if strike_info else "none",

            # Risk management
            "target_price": risk["target_price"] if risk else None,
            "stop_price": risk["stop_price"] if risk else None,
            "risk_pct": risk["final_risk_pct"] if risk else 0,
            "max_contracts": risk["max_contracts"] if risk else 0,
            "risk_management": risk or {},

            # Reasoning
            "reasoning": reason,
            "confluence_count": sum(1 for f in factors if f.direction in ("bullish", "bearish")),
            "factors": [
                {"name": f.name, "direction": f.direction,
                 "weight": round(f.weight, 2), "detail": f.detail}
                for f in factors
            ],

            # Market context
            "session": session.to_dict(),
            "levels": levels.to_dict(),

            # Order flow summary
            "indicators": {
                "cvd": flow.cvd,
                "cvd_trend": flow.cvd_trend,
                "price_trend": flow.price_trend,
                "divergence": flow.divergence,
                "imbalance": round(flow.imbalance, 3),
                "aggressive_buy_pct": round(flow.aggressive_buy_pct, 3),
                "aggressive_sell_pct": round(flow.aggressive_sell_pct, 3),
                "large_trades": flow.large_trade_count,
                "large_trade_bias": flow.large_trade_bias,
                "absorption": flow.absorption_detected,
                "exhaustion": flow.volume_exhausted,
                "total_volume": flow.total_volume,
            },

            # v2: GEX/DEX analysis (from ThetaData Greeks + OI, computed locally)
            "gex": gex_data.to_dict() if gex_data else None,

            # v2: Options analytics (IV Rank, PCR, Max Pain — from chain data)
            "options_analytics": chain_analytics.to_dict() if chain_analytics else None,
        }

        return signal

    def _no_trade(self, reason: str) -> Dict[str, Any]:
        """Quick NO_TRADE signal."""
        return {
            "signal": "NO_TRADE",
            "symbol": self.symbol,
            "confidence": 0.0,
            "tier": "DEVELOPING",
            "reasoning": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strike": None, "expiry": _get_nearest_expiry(),
            "entry_price": None, "target_price": None, "stop_price": None,
            "risk_pct": 0, "max_contracts": 0,
            "confluence_count": 0, "factors": [],
            "risk_management": {},
            "session": get_session_context().to_dict(),
            "levels": {},
            "indicators": {
                "cvd": 0, "cvd_trend": "neutral", "price_trend": "neutral",
                "divergence": "none", "imbalance": 0.5,
                "aggressive_buy_pct": 0, "aggressive_sell_pct": 0,
                "large_trades": 0, "large_trade_bias": "neutral",
                "absorption": False, "exhaustion": False, "total_volume": 0,
            },
        }

    def get_diagnostics(self) -> Dict[str, Any]:
        """Return last signal pipeline diagnostics for debugging."""
        diag = getattr(self, '_last_diagnostics', {})
        return {
            "last_gate_result": diag,
            "chain_cached": self._chain_cache is not None,
            "chain_cache_calls": len(self._chain_cache.get("calls", [])) if self._chain_cache else 0,
            "chain_cache_puts": len(self._chain_cache.get("puts", [])) if self._chain_cache else 0,
            "bars_1m_cached": len(self._bars_1m_cache),
            "bars_daily_cached": len(self._bars_daily_cache),
            "regime": getattr(self, '_cached_regime', None) is not None,
            "sweeps": getattr(self, '_cached_sweeps', None) is not None,
            "vpin": getattr(self, '_cached_vpin', None) is not None,
            "sectors": getattr(self, '_cached_sectors', None) is not None,
            "agents": getattr(self, '_cached_agent_verdicts', None) is not None,
        }

    def _no_trade_reason(
        self,
        factors: List[ConfluenceFactor],
        flow: OrderFlowState,
        session: SessionContext,
    ) -> str:
        """Generate human-readable reason for NO_TRADE."""
        from .confluence import ZERO_DTE_HARD_STOP

        reasons = []

        if session.past_hard_stop:
            reasons.append(f"Past 0DTE hard stop ({ZERO_DTE_HARD_STOP.strftime('%I:%M %p')} ET)")
        if session.session_quality < 0.3:
            reasons.append(f"Low-quality session ({session.phase.replace('_', ' ')})")

        bull_count = sum(1 for f in factors if f.direction == "bullish")
        bear_count = sum(1 for f in factors if f.direction == "bearish")

        if bull_count < 2 and bear_count < 2:
            reasons.append("Insufficient confluence (need 2+ confirming factors)")
        elif bull_count > 0 and bear_count > 0:
            reasons.append(f"Mixed signals ({bull_count} bullish vs {bear_count} bearish)")

        if flow.divergence == "none" and not flow.absorption_detected and flow.large_trade_count == 0:
            reasons.append("No strong order flow pattern detected")

        return " | ".join(reasons) if reasons else "No qualified setup — watching"
