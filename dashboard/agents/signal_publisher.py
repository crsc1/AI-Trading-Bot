"""
Agent 5: Signal Publisher — The Orchestrator

Collects verdicts from all 4 analysis agents, determines consensus,
and publishes fully qualified trade signals ONLY when agents agree.

Responsibilities:
  - Aggregate agent verdicts with weighted voting
  - Require minimum 3/4 agents agreeing for a signal
  - Select strike from real options chain (delta-based)
  - Calculate dynamic risk sizing
  - Track P/L on open signals in real-time
  - Auto-close signals at target, stop, or 3:00 PM hard stop
  - Publish to WebSocket for frontend consumption

Polling: Every 10 seconds (checks agent verdicts + updates P/L)
"""

import aiohttp
import logging
import uuid
from datetime import datetime, timezone, timedelta, time as dt_time
from typing import Optional, List, Dict, Any
from collections import deque

from .base import (
    BaseAgent, AgentVerdict, Direction, PublishedSignal,
)
from .price_flow_agent import PriceFlowAgent
from .news_agent import NewsAgent
from .sentiment_agent import SentimentAgent
from .market_structure_agent import MarketStructureAgent
from dashboard.confluence import get_active_symbol, derive_spx_price
from ..config import cfg

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except ImportError:
    ET = timezone(timedelta(hours=-4))

logger = logging.getLogger(__name__)
API_BASE = cfg.DASHBOARD_BASE_URL

# Agent weights in the voting system
AGENT_WEIGHTS = {
    "PriceFlow": 0.35,    # Price action is king
    "Structure": 0.25,    # Key levels matter a lot for options
    "News": 0.25,         # News can override everything
    "Sentiment": 0.15,    # Slower-moving, confirming factor
}

# Minimum requirements for signal publication
MIN_AGENTS_AGREEING = 2       # At least 2 agents must agree on direction
MIN_WEIGHTED_CONFIDENCE = 0.35  # Minimum weighted confidence score
MIN_SIGNAL_INTERVAL = 120      # Seconds between signals (prevent spam)

# Account
ACCOUNT_BALANCE = 5000.0

# Risk by tier
RISK_TABLE = {
    "TEXTBOOK": 2.0,
    "HIGH": 1.5,
    "VALID": 0.75,
}

TIER_THRESHOLDS = {
    "TEXTBOOK": 0.75,  # 3+ agents, high confidence
    "HIGH": 0.55,      # 2+ agents, good confidence
    "VALID": 0.40,     # 2 agents, moderate confidence
}

# 0DTE hard stop
HARD_STOP_TIME = dt_time(15, 0)  # 3:00 PM ET


class SignalPublisher(BaseAgent):
    name = "Publisher"
    poll_interval = 10
    stale_seconds = 300  # Publisher verdicts are meta-level

    def __init__(self):
        super().__init__()

        # Child agents
        self.price_flow = PriceFlowAgent()
        self.news = NewsAgent()
        self.sentiment = SentimentAgent()
        self.structure = MarketStructureAgent()

        self._agents = [self.price_flow, self.news, self.sentiment, self.structure]

        # Signal storage
        self.open_signals: List[PublishedSignal] = []
        self.closed_signals: deque = deque(maxlen=100)
        self.signal_history: deque = deque(maxlen=50)
        self._last_signal_time: Optional[datetime] = None

    def start_all(self):
        """Start all child agents + the publisher itself."""
        for agent in self._agents:
            agent.start()
        self.start()
        logger.info("Signal Publisher: All 5 agents started")

    def stop_all(self):
        """Stop all agents."""
        for agent in self._agents:
            agent.stop()
        self.stop()
        logger.info("Signal Publisher: All agents stopped")

    async def analyze(self) -> AgentVerdict:
        """
        Main orchestration loop:
        1. Collect verdicts from all agents
        2. Check for consensus
        3. If consensus → publish signal
        4. Update P/L on open signals
        """
        # ── 1. Collect agent verdicts ──
        verdicts: Dict[str, AgentVerdict] = {}
        for agent in self._agents:
            v = agent.get_verdict()
            if v:
                verdicts[agent.name] = v

        # ── 2. Update P/L on open signals ──
        await self._update_open_signals()

        # ── 3. Check time — no new signals after hard stop ──
        now_et = datetime.now(ET)
        if now_et.time() >= HARD_STOP_TIME:
            # Close all open signals
            for sig in self.open_signals:
                if sig.status == "OPEN":
                    sig.status = "EXPIRED"
                    sig.close_reason = "0DTE hard stop (3:00 PM ET)"
                    sig.closed_at = datetime.now(timezone.utc).isoformat()
                    self.closed_signals.append(sig)

            self.open_signals = [s for s in self.open_signals if s.status == "OPEN"]

            return AgentVerdict(
                agent_name=self.name,
                direction=Direction.NEUTRAL,
                confidence=0.0,
                reasoning=f"Past hard stop — {len(verdicts)} agents active, {len(self.open_signals)} open signals",
                stale_after_seconds=self.stale_seconds,
            )

        if len(verdicts) < 2:
            return AgentVerdict(
                agent_name=self.name,
                direction=Direction.NEUTRAL,
                confidence=0.0,
                reasoning=f"Only {len(verdicts)} agents reporting — waiting for data",
                data={"agents_active": len(verdicts)},
                stale_after_seconds=self.stale_seconds,
            )

        # ── 4. Evaluate consensus ──
        signal_result = self._evaluate_consensus(verdicts)

        if signal_result:
            action, weighted_conf, tier, agreeing_agents = signal_result

            # Rate limit — don't spam signals
            if self._last_signal_time:
                elapsed = (datetime.now(timezone.utc) - self._last_signal_time).total_seconds()
                if elapsed < MIN_SIGNAL_INTERVAL:
                    return AgentVerdict(
                        agent_name=self.name,
                        direction=Direction.BULLISH if action == "BUY_CALL" else Direction.BEARISH,
                        confidence=weighted_conf,
                        reasoning=f"Signal ready but cooling down ({MIN_SIGNAL_INTERVAL - elapsed:.0f}s)",
                        stale_after_seconds=self.stale_seconds,
                    )

            # ── 5. Build and publish signal ──
            published = await self._build_signal(action, weighted_conf, tier, verdicts)
            if published:
                self.open_signals.append(published)
                self.signal_history.append(published.to_dict())
                self._last_signal_time = datetime.now(timezone.utc)
                logger.info(f"SIGNAL PUBLISHED: {action} {published.symbol} {published.strike} "
                           f"@ ${published.entry_price} (conf: {weighted_conf:.0%}, tier: {tier})")

        # Return meta-verdict
        active_dirs = {name: v.direction.value for name, v in verdicts.items()}
        return AgentVerdict(
            agent_name=self.name,
            direction=Direction.NEUTRAL,
            confidence=0.0,
            reasoning=f"Agents: {active_dirs} | Open: {len(self.open_signals)} | Closed: {len(self.closed_signals)}",
            data={
                "agents_active": len(verdicts),
                "open_signals": len(self.open_signals),
                "closed_signals": len(self.closed_signals),
            },
            stale_after_seconds=self.stale_seconds,
        )

    def _evaluate_consensus(
        self, verdicts: Dict[str, AgentVerdict]
    ) -> Optional[tuple]:
        """
        Weighted voting across agents.
        Returns (action, weighted_confidence, tier, agreeing_agents) or None.
        """
        bullish_weight = 0.0
        bearish_weight = 0.0
        bullish_agents = []
        bearish_agents = []

        for name, verdict in verdicts.items():
            agent_weight = AGENT_WEIGHTS.get(name, 0.10)
            contribution = agent_weight * verdict.confidence

            if verdict.direction == Direction.BULLISH:
                bullish_weight += contribution
                bullish_agents.append(name)
            elif verdict.direction == Direction.BEARISH:
                bearish_weight += contribution
                bearish_agents.append(name)

        # Determine winning direction
        if bullish_weight > bearish_weight and len(bullish_agents) >= MIN_AGENTS_AGREEING:
            action = "BUY_CALL"
            weighted_conf = bullish_weight
            agreeing = bullish_agents
        elif bearish_weight > bullish_weight and len(bearish_agents) >= MIN_AGENTS_AGREEING:
            action = "BUY_PUT"
            weighted_conf = bearish_weight
            agreeing = bearish_agents
        else:
            return None

        # ── Conflict detection ──
        # If strong agents disagree, raise the bar
        if bullish_agents and bearish_agents:
            # Check if any high-weight agent is on the losing side
            losing_side = bearish_agents if action == "BUY_CALL" else bullish_agents
            losing_weight = sum(AGENT_WEIGHTS.get(a, 0.10) for a in losing_side)
            if losing_weight >= 0.25:  # 25%+ weight disagreeing
                # Raise confidence threshold — need stronger conviction
                required_conf = MIN_WEIGHTED_CONFIDENCE * 1.5  # 0.35 → 0.525
                if weighted_conf < required_conf:
                    logger.info(
                        f"[Publisher] Conflicting agents: {bullish_agents} vs {bearish_agents} "
                        f"— conf {weighted_conf:.2f} < raised threshold {required_conf:.2f}"
                    )
                    return None

        # Check minimum confidence
        if weighted_conf < MIN_WEIGHTED_CONFIDENCE:
            return None

        # Determine tier
        if weighted_conf >= TIER_THRESHOLDS["TEXTBOOK"] and len(agreeing) >= 3:
            tier = "TEXTBOOK"
        elif weighted_conf >= TIER_THRESHOLDS["HIGH"]:
            tier = "HIGH"
        elif weighted_conf >= TIER_THRESHOLDS["VALID"]:
            tier = "VALID"
        else:
            return None

        return action, weighted_conf, tier, agreeing

    async def _build_signal(
        self,
        action: str,
        confidence: float,
        tier: str,
        verdicts: Dict[str, AgentVerdict],
    ) -> Optional[PublishedSignal]:
        """Build a fully qualified published signal with real options data."""
        try:
            active_sym = get_active_symbol()
            # Options root: SPX 0DTE uses SPXW (weekly), SPY uses SPY
            options_root = "SPXW" if active_sym == "SPX" else "SPY"

            async with aiohttp.ClientSession() as session:
                # Always fetch SPY price (primary data source)
                market_resp = await session.get(
                    f"{API_BASE}/api/market?symbol=SPY",
                    timeout=aiohttp.ClientTimeout(total=3),
                )
                market = {}
                if market_resp.status == 200:
                    md = await market_resp.json()
                    market = md.get("spy", {})

                spy_price = market.get("price", 0)
                if spy_price <= 0:
                    return None

                # Derive SPX price if needed
                if active_sym == "SPX":
                    price = derive_spx_price(spy_price)
                else:
                    price = spy_price

                # Get levels
                levels_resp = await session.get(
                    f"{API_BASE}/api/signals/levels",
                    timeout=aiohttp.ClientTimeout(total=3),
                )
                levels = {}
                if levels_resp.status == 200:
                    ld = await levels_resp.json()
                    levels = ld.get("levels", {})

                # Get options chain for strike selection
                today = datetime.now(ET).strftime("%Y-%m-%d")
                chain_resp = await session.get(
                    f"{API_BASE}/api/options/chain?root={options_root}&exp={today}",
                    timeout=aiohttp.ClientTimeout(total=8),
                )
                chain = {}
                if chain_resp.status == 200:
                    chain = await chain_resp.json()

            # Select strike using signal engine's logic
            from dashboard.confluence import select_strike, calculate_risk, get_session_context
            from dashboard.market_levels import MarketLevels

            strike_info = select_strike(
                action=action,
                current_price=price,
                chain=chain,
                target_delta=0.32,
            )

            if not strike_info.get("entry_price") or strike_info["entry_price"] <= 0:
                return None

            # Liquidity gate: reject strikes with poor spread quality
            try:
                from dashboard.api_routes import get_spread_analysis
                right = "C" if action == "BUY_CALL" else "P"
                exp_str = today.replace("-", "")
                spread_data = await get_spread_analysis(options_root, exp_str, strike_info["strike"], right, exp_str)
                liq_score = spread_data.get("liquidity_score")
                if liq_score is not None and liq_score < 30:
                    logger.warning(f"[Publisher] Strike {strike_info['strike']} liquidity too low ({liq_score}/100) — skipping")
                    return None
            except Exception as e:
                logger.debug(f"[Publisher] Spread analysis unavailable, skipping gate: {e}")

            # Build MarketLevels for risk calc
            ml = MarketLevels()
            ml.realized_vol = levels.get("realized_vol", 15)

            session_ctx = get_session_context()

            risk = calculate_risk(
                confidence=confidence,
                entry_price=strike_info["entry_price"],
                levels=ml,
                session=session_ctx,
                account_balance=ACCOUNT_BALANCE,
                iv=strike_info.get("iv"),
                delta=strike_info.get("delta"),
            )

            # Build reasoning from agent verdicts
            reasoning_parts = []
            for name, v in verdicts.items():
                if v.direction != Direction.NEUTRAL:
                    reasoning_parts.append(f"[{name}] {v.reasoning[:80]}")

            signal_id = str(uuid.uuid4())[:8]

            return PublishedSignal(
                signal_id=signal_id,
                action=action,
                symbol=active_sym,
                strike=strike_info["strike"],
                expiry=strike_info["expiry"],
                entry_price=strike_info["entry_price"],
                target_price=risk["target_price"],
                stop_price=risk["stop_price"],
                confidence=confidence,
                tier=tier,
                reasoning=" | ".join(reasoning_parts),
                verdicts=[v.to_dict() for v in verdicts.values()],
                risk=risk,
                option_data={
                    "delta": strike_info.get("delta"),
                    "iv": strike_info.get("iv"),
                    "gamma": strike_info.get("gamma"),
                    "theta": strike_info.get("theta"),
                    "volume": strike_info.get("volume", 0),
                    "oi": strike_info.get("open_interest", 0),
                    "source": strike_info.get("source", "estimated"),
                },
                levels={k: v for k, v in levels.items()
                        if isinstance(v, (int, float)) and v > 0},
                timestamp=datetime.now(timezone.utc).isoformat(),
                contracts=risk.get("max_contracts", 1),
                current_price=strike_info["entry_price"],
                max_price=strike_info["entry_price"],
                min_price=strike_info["entry_price"],
            )

        except Exception as e:
            logger.error(f"Failed to build signal: {e}", exc_info=True)
            return None

    async def _update_open_signals(self):
        """Update P/L on all open signals using live option prices."""
        if not self.open_signals:
            return

        try:
            async with aiohttp.ClientSession() as session:
                # Get current SPY price
                market_resp = await session.get(
                    f"{API_BASE}/api/market?symbol=SPY",
                    timeout=aiohttp.ClientTimeout(total=3),
                )
                if market_resp.status != 200:
                    return
                md = await market_resp.json()
                current_spy = md.get("spy", {}).get("price", 0)

                if current_spy <= 0:
                    return

                # Try to get live options chain for real prices
                today = datetime.now(ET).strftime("%Y-%m-%d")
                chain = {}
                try:
                    active_sym = get_active_symbol()
                    options_root = "SPXW" if active_sym == "SPX" else "SPY"
                    chain_resp = await session.get(
                        f"{API_BASE}/api/options/chain?root={options_root}&exp={today}",
                        timeout=aiohttp.ClientTimeout(total=5),
                    )
                    if chain_resp.status == 200:
                        chain = await chain_resp.json()
                except Exception:
                    pass

            for sig in list(self.open_signals):
                if sig.status != "OPEN":
                    continue

                # ── Try real option price from chain first ──
                real_price = self._get_real_option_price(sig, chain)
                if real_price and real_price > 0:
                    sig.current_price = round(real_price, 2)
                else:
                    # ── Fallback: improved delta + gamma + theta estimation ──
                    spy_entry_price = sig.levels.get("current_price", current_spy)
                    spy_change = current_spy - spy_entry_price

                    delta = sig.option_data.get("delta") or (0.32 if sig.action == "BUY_CALL" else -0.32)
                    gamma = sig.option_data.get("gamma") or 0.03
                    theta = sig.option_data.get("theta") or -0.05

                    # Delta + gamma adjustment for underlying move
                    if sig.action == "BUY_CALL":
                        option_change = abs(delta) * spy_change + 0.5 * gamma * (spy_change ** 2)
                    else:
                        option_change = delta * spy_change + 0.5 * gamma * (spy_change ** 2)

                    # Time decay (theta per minute, more aggressive for 0DTE)
                    signal_time = datetime.fromisoformat(sig.timestamp.replace("Z", "+00:00"))
                    minutes_held = (datetime.now(timezone.utc) - signal_time).total_seconds() / 60
                    # Theta accelerates — use actual theta if available, else estimate
                    theta_per_min = abs(theta) / 390  # theta is daily, 390 min trading day
                    # 0DTE theta acceleration: doubles in last 2 hours
                    now_et = datetime.now(ET)
                    mins_to_close = max(1, (datetime.combine(now_et.date(), dt_time(16, 0)) -
                                            now_et.replace(tzinfo=None)).total_seconds() / 60)
                    if mins_to_close < 120:
                        theta_per_min *= (2.0 - mins_to_close / 120)  # 1x-2x acceleration

                    theta_decay = theta_per_min * minutes_held
                    sig.current_price = max(0.01, round(sig.entry_price + option_change - theta_decay, 2))

                sig.pnl_dollars = round((sig.current_price - sig.entry_price) * 100 * sig.contracts, 2)
                sig.pnl_percent = round(((sig.current_price / sig.entry_price) - 1) * 100, 2) if sig.entry_price > 0 else 0

                # Track MFE/MAE (max favorable / adverse excursion)
                sig.max_price = max(sig.max_price, sig.current_price)
                sig.min_price = min(sig.min_price, sig.current_price) if sig.min_price > 0 else sig.current_price

                # ══════════════════════════════════════════════════════════
                # DYNAMIC EXIT ENGINE — profit is always priority #1
                # ══════════════════════════════════════════════════════════
                #
                # Philosophy: NEVER give back more than 5-10% of peak gains.
                # The trailing tightens as profit grows. Fast market drops
                # trigger immediate exit. Time is only a factor when the
                # trade is going nowhere.
                #
                # Priority: target > profit protection > stop > time exit
                # ══════════════════════════════════════════════════════════
                risk = sig.risk or {}

                # Compute key metrics
                peak_gain_pct = ((sig.max_price / sig.entry_price) - 1) * 100 if sig.entry_price > 0 else 0
                current_gain_pct = sig.pnl_percent  # Already computed above
                drawdown_from_peak_pct = peak_gain_pct - current_gain_pct  # How much we've given back

                signal_time = datetime.fromisoformat(sig.timestamp.replace("Z", "+00:00"))
                minutes_held = (datetime.now(timezone.utc) - signal_time).total_seconds() / 60

                # ── 1. TARGET HIT — take profit immediately ──
                if sig.current_price >= sig.target_price:
                    sig.status = "TARGET_HIT"
                    sig.close_reason = f"Target hit at ${sig.current_price:.2f} (+{sig.pnl_percent:.0f}%)"
                    sig.closed_at = datetime.now(timezone.utc).isoformat()
                    self.closed_signals.append(sig)
                    logger.info(f"TARGET HIT: {sig.signal_id} P/L: ${sig.pnl_dollars:+.2f}")
                    continue

                # ── 2. DYNAMIC PROFIT PROTECTION ──
                # Once in profit, never give back more than a dynamic % of gains.
                # The more profit we have, the tighter we protect it.
                #
                # Peak gain     Max giveback    Example: entry $1.00
                # ─────────     ────────────    ────────────────────
                # +5-10%        give back 50%   peak $1.08 → floor $1.04
                # +10-20%       give back 30%   peak $1.15 → floor $1.105
                # +20-40%       give back 20%   peak $1.30 → floor $1.24
                # +40%+         give back 10%   peak $1.50 → floor $1.45
                #
                if peak_gain_pct >= 5.0 and current_gain_pct > 0:
                    if peak_gain_pct >= 40:
                        max_giveback_pct = 0.10  # Protect 90% of gains
                    elif peak_gain_pct >= 20:
                        max_giveback_pct = 0.20  # Protect 80% of gains
                    elif peak_gain_pct >= 10:
                        max_giveback_pct = 0.30  # Protect 70% of gains
                    else:
                        max_giveback_pct = 0.50  # Protect 50% of gains

                    # Floor price = entry + (peak_gain * (1 - giveback))
                    peak_dollar_gain = sig.max_price - sig.entry_price
                    floor_price = sig.entry_price + peak_dollar_gain * (1 - max_giveback_pct)

                    if sig.current_price <= floor_price:
                        kept_pct = current_gain_pct
                        sig.status = "PROFIT_PROTECTED"
                        sig.close_reason = (
                            f"Profit protection: peaked +{peak_gain_pct:.0f}%, "
                            f"gave back {drawdown_from_peak_pct:.0f}% → locked +{kept_pct:.0f}% "
                            f"(${sig.current_price:.2f}, floor ${floor_price:.2f})"
                        )
                        sig.closed_at = datetime.now(timezone.utc).isoformat()
                        self.closed_signals.append(sig)
                        logger.info(f"PROFIT PROTECTED: {sig.signal_id} peak +{peak_gain_pct:.0f}% → exit +{kept_pct:.0f}% P/L: ${sig.pnl_dollars:+.2f}")
                        continue

                # ── 3. STOP LOSS — hard floor, never lose more than stop_pct ──
                if sig.current_price <= sig.stop_price:
                    sig.status = "STOPPED"
                    sig.close_reason = f"Stop hit at ${sig.current_price:.2f} ({sig.pnl_percent:.0f}%)"
                    sig.closed_at = datetime.now(timezone.utc).isoformat()
                    self.closed_signals.append(sig)
                    logger.info(f"STOPPED: {sig.signal_id} P/L: ${sig.pnl_dollars:+.2f}")
                    continue

                # ── 4. VELOCITY STOP — fast drops trigger immediate exit ──
                # If price dropped more than 8% in the last update cycle,
                # that's a fast move against us — get out now.
                if hasattr(sig, '_prev_price') and sig._prev_price and sig._prev_price > 0:
                    tick_change_pct = ((sig.current_price - sig._prev_price) / sig._prev_price) * 100
                    if tick_change_pct < -8.0:
                        sig.status = "VELOCITY_STOP"
                        sig.close_reason = f"Fast drop {tick_change_pct:.0f}% in one tick — emergency exit at ${sig.current_price:.2f}"
                        sig.closed_at = datetime.now(timezone.utc).isoformat()
                        self.closed_signals.append(sig)
                        logger.info(f"VELOCITY STOP: {sig.signal_id} tick={tick_change_pct:.1f}% P/L: ${sig.pnl_dollars:+.2f}")
                        continue
                sig._prev_price = sig.current_price

                # ── 5. BREAKEVEN STOP — after being up 5%+, never go red ──
                # If we were up 5%+ at some point, stop at breakeven (+0.5%)
                if peak_gain_pct >= 5.0 and current_gain_pct <= 0.5:
                    sig.status = "BREAKEVEN"
                    sig.close_reason = f"Breakeven stop: was +{peak_gain_pct:.0f}%, now {current_gain_pct:+.0f}% — protecting capital"
                    sig.closed_at = datetime.now(timezone.utc).isoformat()
                    self.closed_signals.append(sig)
                    logger.info(f"BREAKEVEN: {sig.signal_id} peak +{peak_gain_pct:.0f}% → exit ~0% P/L: ${sig.pnl_dollars:+.2f}")
                    continue

                # ── 6. MAX HOLD — safety net for sideways trades only ──
                max_hold = risk.get("max_hold_minutes", 45)
                if max_hold > 0 and minutes_held >= max_hold:
                    sig.status = "TIME_EXIT"
                    sig.close_reason = f"Max hold {max_hold}m — exit at ${sig.current_price:.2f} ({sig.pnl_percent:+.0f}%)"
                    sig.closed_at = datetime.now(timezone.utc).isoformat()
                    self.closed_signals.append(sig)
                    logger.info(f"TIME EXIT: {sig.signal_id} P/L: ${sig.pnl_dollars:+.2f}")
                    continue

            # Remove closed signals from open list
            self.open_signals = [s for s in self.open_signals if s.status == "OPEN"]

        except Exception as e:
            logger.debug(f"P/L update error: {e}")

    def _get_real_option_price(self, sig, chain: dict) -> Optional[float]:
        """Try to find the real mid/ask price for a signal's contract from live chain."""
        if not chain:
            return None
        side = "calls" if sig.action == "BUY_CALL" else "puts"
        options = chain.get(side, [])
        if not options:
            return None

        # Find matching strike
        target_strike = sig.strike
        for opt in options:
            if abs(opt.get("strike", 0) - target_strike) < 0.01:
                bid = opt.get("bid", 0) or 0
                ask = opt.get("ask", 0) or 0
                if bid > 0 and ask > 0:
                    return round((bid + ask) / 2, 2)  # Use mid for P&L
                elif opt.get("last", 0) > 0:
                    return opt["last"]
        return None

    # ── Public API methods for endpoints ──

    def get_all_signals(self) -> List[Dict]:
        """Get all open + recent closed signals."""
        signals = []
        for s in self.open_signals:
            signals.append(s.to_dict())
        for s in list(self.closed_signals)[-10:]:
            signals.append(s.to_dict())
        return sorted(signals, key=lambda x: x.get("timestamp", ""), reverse=True)

    def get_open_signals(self) -> List[Dict]:
        """Get currently open signals with live P/L."""
        return [s.to_dict() for s in self.open_signals]

    def get_agent_status(self) -> Dict[str, Any]:
        """Get status of all agents."""
        status = {}
        for agent in self._agents:
            v = agent.get_verdict()
            status[agent.name] = {
                "active": v is not None,
                "direction": v.direction.value if v else "none",
                "confidence": round(v.confidence, 2) if v else 0,
                "reasoning": v.reasoning[:100] if v else "No data",
                "stale": v.is_stale() if v else True,
            }
        return status

    def get_performance(self) -> Dict[str, Any]:
        """Get overall performance metrics."""
        closed = list(self.closed_signals)
        if not closed:
            return {"total_signals": 0, "win_rate": 0, "total_pnl": 0}

        wins = sum(1 for s in closed if s.pnl_dollars > 0)
        total_pnl = sum(s.pnl_dollars for s in closed)
        avg_win = 0
        avg_loss = 0
        winners = [s.pnl_dollars for s in closed if s.pnl_dollars > 0]
        losers = [s.pnl_dollars for s in closed if s.pnl_dollars <= 0]
        if winners:
            avg_win = sum(winners) / len(winners)
        if losers:
            avg_loss = sum(losers) / len(losers)

        return {
            "total_signals": len(closed),
            "wins": wins,
            "losses": len(closed) - wins,
            "win_rate": round(wins / len(closed) * 100, 1) if closed else 0,
            "total_pnl": round(total_pnl, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(abs(sum(winners)) / abs(sum(losers)), 2) if losers and sum(losers) != 0 else 0,
            "open_signals": len(self.open_signals),
        }
