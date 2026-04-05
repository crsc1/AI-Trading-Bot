"""
Autonomous Trader — Self-executing trading loop with risk management.

This module bridges the gap between signal generation and trade execution.
Instead of requiring manual POST /api/signals/trade calls, the autonomous
trader watches signal_history and auto-executes when conditions are met.

Architecture:
    Signal Loop (15s) → signal_history deque
                              ↓
    Autonomous Trader (5s) → checks latest signal
                              ↓
    If tradeable (tier ≥ threshold, risk limits ok):
        → PaperTrader.process_signal()
        → Position opened
                              ↓
    Exit Monitor (5s) → checks open positions
                              ↓
    If exit trigger hit (target, stop, time):
        → PaperTrader.exit_trade()
        → Trade graded
        → Weight learner notified

Safety:
    - Paper trading ONLY (uses PaperTrader)
    - Daily loss circuit breaker: $150 hard stop (3% of $5K)
    - Daily loss throttle: at $75, reduce size 50% + TEXTBOOK only
    - IV-scaled position sizing (0x-1.5x based on VIX percentile)
    - Time-of-day confidence multiplier (peak: 9:50-10:30 AM)
    - Staged time exits: 2:30 PM tighten, 2:45 PM close losers, 3:00 PM close ALL
    - Trailing stop with activation threshold (+10% → 15% trail)
    - Max concurrent positions (2)
    - Can be stopped instantly via API
    - Every decision logged for audit
"""

import asyncio
import logging
import json
from datetime import datetime, timezone, time as dt_time
from typing import Dict, List, Optional, Callable
from collections import deque

from .signal_db import get_open_trades, get_todays_trades
from .trade_grader import grade_trade
from .config import cfg

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

class AutoTraderConfig:
    """Runtime-adjustable configuration for the autonomous trader."""

    def __init__(self):
        # ── Execution Settings ──
        self.enabled: bool = False              # Master kill switch
        self.mode: str = "alpaca_paper"         # "simulation" or "alpaca_paper"
        self.min_tier: str = "VALID"            # Minimum tier to auto-trade (lowered for paper trading)
        self.min_confidence: float = 0.42      # Minimum confidence (matches confluence Gate 5 floor)

        # ── Risk Limits ──
        self.max_daily_loss: float = 150.0       # $150 = 3% of $5K (hard circuit breaker)
        self.daily_loss_throttle: float = 75.0   # At $75 loss, reduce size 50% + TEXTBOOK only
        self.max_open_positions: int = 2         # Max simultaneous positions
        self.max_trades_per_day: int = 0         # 0 = unlimited trades per day
        self.max_risk_per_trade_pct: float = 1.0 # % of account per trade (base, before IV scaling)

        # ── Timing ──
        self.trading_start: dt_time = dt_time(9, 50)    # Wait for opening range (research: 9:50 optimal)
        self.trading_end: dt_time = dt_time(15, 0)       # 0DTE hard stop (force close ALL)
        self.no_new_entries_after: dt_time = dt_time(14, 30)  # No new entries after 2:30 PM
        self.close_losers_at: dt_time = dt_time(14, 45)       # Close any losing position at 2:45 PM
        self.tighten_stops_at: dt_time = dt_time(14, 30)      # Tighten trailing stops after 2:30 PM
        self.min_seconds_between_trades: int = 60        # Cooldown between entries
        self.exit_check_interval: int = 5                # Seconds between exit checks

        # ── Exit Rules (Dynamic Exit Engine) ──
        self.auto_exit_profit_target: bool = True
        self.auto_exit_stop_loss: bool = True
        self.auto_exit_time_stop: bool = True     # Close all at 3:00 PM ET
        self.trailing_stop_pct: float = 0.15      # 15% trailing stop (activates at +10% profit)
        self.trailing_stop_activation: float = 0.10  # Trailing stop activates at +10% gain
        self.max_hold_minutes: int = 45           # Max hold time (0DTE optimal)

        # ── IV-Scaled Position Sizing ──
        # Base risk = max_risk_per_trade_pct, scaled by IV rank:
        #   IV 0-20%  → 1.5x (low vol, range-bound, safe)
        #   IV 21-50% → 1.0x (normal)
        #   IV 51-80% → 0.5x (high vol, wider swings)
        #   IV 81%+   → 0.0x (extreme vol, skip day)
        self.iv_scaling_enabled: bool = True

        # ── Learning ──
        self.learn_from_trades: bool = True       # Feed closed trades to weight learner
        self.log_all_decisions: bool = True        # Verbose decision logging

    TIER_ORDER = {"TEXTBOOK": 4, "HIGH": 3, "VALID": 2, "DEVELOPING": 1}

    def meets_tier(self, tier: str) -> bool:
        """Check if a signal tier meets the minimum threshold."""
        return self.TIER_ORDER.get(tier, 0) >= self.TIER_ORDER.get(self.min_tier, 0)

    def to_dict(self) -> Dict:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "min_tier": self.min_tier,
            "min_confidence": self.min_confidence,
            "max_daily_loss": self.max_daily_loss,
            "daily_loss_throttle": self.daily_loss_throttle,
            "max_open_positions": self.max_open_positions,
            "max_trades_per_day": self.max_trades_per_day,
            "max_risk_per_trade_pct": self.max_risk_per_trade_pct,
            "trading_start": self.trading_start.strftime("%H:%M"),
            "trading_end": self.trading_end.strftime("%H:%M"),
            "no_new_entries_after": self.no_new_entries_after.strftime("%H:%M"),
            "close_losers_at": self.close_losers_at.strftime("%H:%M"),
            "min_seconds_between_trades": self.min_seconds_between_trades,
            "auto_exit_profit_target": self.auto_exit_profit_target,
            "auto_exit_stop_loss": self.auto_exit_stop_loss,
            "auto_exit_time_stop": self.auto_exit_time_stop,
            "trailing_stop_pct": self.trailing_stop_pct,
            "trailing_stop_activation": self.trailing_stop_activation,
            "max_hold_minutes": self.max_hold_minutes,
            "iv_scaling_enabled": self.iv_scaling_enabled,
            "learn_from_trades": self.learn_from_trades,
        }

    def update(self, data: Dict) -> None:
        """Update config from a dict (partial update supported)."""
        for key, val in data.items():
            if hasattr(self, key):
                # Handle time fields
                if key in ("trading_start", "trading_end", "no_new_entries_after",
                          "close_losers_at", "tighten_stops_at") and isinstance(val, str):
                    h, m = val.split(":")
                    setattr(self, key, dt_time(int(h), int(m)))
                else:
                    setattr(self, key, val)


# ═══════════════════════════════════════════════════════════════════════════
# DECISION LOG — every decision the AI makes is recorded for learning
# ═══════════════════════════════════════════════════════════════════════════

class DecisionLog:
    """Circular buffer of trading decisions for audit and learning."""

    def __init__(self, maxlen: int = 200):
        self._log: deque = deque(maxlen=maxlen)

    def record(self, action: str, reason: str, signal: Optional[Dict] = None, extra: Optional[Dict] = None):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "reason": reason,
            "signal_tier": signal.get("tier") if signal else None,
            "signal_confidence": signal.get("confidence") if signal else None,
            "signal_direction": signal.get("signal") if signal else None,
            **(extra or {}),
        }
        self._log.append(entry)
        if action in ("TRADE_ENTERED", "TRADE_EXITED", "ERROR"):
            logger.info(f"AUTO-TRADER [{action}]: {reason}")
        else:
            logger.debug(f"AUTO-TRADER [{action}]: {reason}")

    def recent(self, limit: int = 50) -> List[Dict]:
        return list(self._log)[-limit:]

    def stats(self) -> Dict:
        """Quick stats from the decision log."""
        entries = list(self._log)
        trades_entered = sum(1 for e in entries if e["action"] == "TRADE_ENTERED")
        trades_exited = sum(1 for e in entries if e["action"] == "TRADE_EXITED")
        skipped = sum(1 for e in entries if e["action"] == "SKIPPED")
        errors = sum(1 for e in entries if e["action"] == "ERROR")
        return {
            "total_decisions": len(entries),
            "trades_entered": trades_entered,
            "trades_exited": trades_exited,
            "signals_skipped": skipped,
            "errors": errors,
        }


# ═══════════════════════════════════════════════════════════════════════════
# AUTONOMOUS TRADER — the core auto-execution engine
# ═══════════════════════════════════════════════════════════════════════════

class AutonomousTrader:
    """
    Watches the signal engine output and auto-executes trades.

    Lifecycle:
        trader = AutonomousTrader(paper_trader, config)
        await trader.start(signal_history_ref)
        ...
        await trader.stop()

    The trader does NOT generate signals — it consumes them from signal_history.
    """

    def __init__(
        self,
        paper_trader,              # PaperTrader instance
        position_tracker,          # PositionTracker instance
        config: Optional[AutoTraderConfig] = None,
        on_trade_closed: Optional[Callable] = None,  # Callback for weight learner
    ):
        self.trader = paper_trader
        self.tracker = position_tracker
        self.config = config or AutoTraderConfig()
        self.decisions = DecisionLog()
        self._on_trade_closed = on_trade_closed

        # Internal state
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._signal_ref = None          # Reference to signal_history deque
        self._last_signal_id = None      # Avoid double-trading same signal
        self._last_trade_time = None     # Cooldown tracking
        self._daily_pnl: float = 0.0     # Running daily P&L
        self._daily_trades: int = 0      # Running trade count
        self._session_start = None       # When the trader was started

        # Dynamic Exit Engine state — track peak prices per trade
        self._peak_prices: Dict[str, float] = {}   # trade_id → highest option price seen
        self._prev_prices: Dict[str, float] = {}   # trade_id → previous tick price (velocity)

    @property
    def is_running(self) -> bool:
        """True if the background loop is active (regardless of enabled state)."""
        return self._running and self._task is not None and not self._task.done()

    @property
    def is_enabled(self) -> bool:
        """True if the trader is actively processing signals."""
        return self.config.enabled and self.is_running

    # ── Lifecycle ──

    async def start(self, signal_history_ref: deque):
        """
        Start the background loop. Called once at app startup.
        The loop runs continuously; actual trading is gated by config.enabled.
        """
        if self.is_running:
            # Already running — just update the signal reference if needed
            if signal_history_ref is not None:
                self._signal_ref = signal_history_ref
            logger.debug("AutonomousTrader loop already running")
            return

        self._signal_ref = signal_history_ref
        self._running = True
        self._session_start = datetime.now(timezone.utc)
        self._reset_daily_counters()

        self._task = asyncio.create_task(self._main_loop())
        self.decisions.record("LOOP_STARTED", "Background loop started (trading disabled until user enables)")
        logger.info(f"AutonomousTrader loop STARTED — mode={self.config.mode}")

    def enable(self):
        """Enable trading — called by the START button."""
        if not self.is_running:
            logger.warning("Cannot enable: background loop not running")
            return False
        self.config.enabled = True
        self._reset_daily_counters()
        self.decisions.record(
            "TRADING_ENABLED",
            f"Trading enabled (mode={self.config.mode}, min_tier={self.config.min_tier}, "
            f"min_conf={self.config.min_confidence})",
        )
        logger.info(
            f"AutonomousTrader ENABLED — mode={self.config.mode}, "
            f"threshold={self.config.min_tier}/{self.config.min_confidence}"
        )
        return True

    def disable(self):
        """Disable trading — called by the STOP button. Loop keeps running."""
        was_enabled = self.config.enabled
        self.config.enabled = False
        if was_enabled:
            self.decisions.record("TRADING_DISABLED", "Trading disabled by user")
            logger.info("AutonomousTrader DISABLED (loop still running)")
        return True

    async def stop(self):
        """Fully stop the background loop. Called at app shutdown."""
        self.config.enabled = False
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.decisions.record("LOOP_STOPPED", "Background loop stopped")
        logger.info("AutonomousTrader loop STOPPED")

    # ── Main Loop ──

    async def _main_loop(self):
        """
        Primary execution loop — runs continuously.

        CRITICAL: Exit checks ALWAYS run (even when disabled) so that
        open positions are protected by stop-losses and time exits.
        New signal evaluation only runs when enabled.
        """
        logger.info("Auto-trader main loop started")
        try:
            while self._running:
                try:
                    # ALWAYS check exits — positions need protection even when disabled
                    await self._check_exits()

                    # Only check for new signals when enabled
                    if self.config.enabled:
                        await self._check_signals()
                except Exception as e:
                    self.decisions.record("ERROR", f"Loop error: {e}")
                    logger.error(f"Auto-trader loop error: {e}", exc_info=True)

                await asyncio.sleep(self.config.exit_check_interval)
        except asyncio.CancelledError:
            logger.info("Auto-trader main loop cancelled")

    # ── Signal Evaluation ──

    async def _check_signals(self):
        """Check for new tradeable signals and execute if conditions are met."""
        if not self._signal_ref:
            return

        # Get latest signal
        if not self._signal_ref:
            return
        signal = self._signal_ref[-1] if self._signal_ref else None
        if not signal:
            return

        # Build a unique ID for dedup
        sig_id = signal.get("id") or signal.get("timestamp", "")
        if sig_id == self._last_signal_id:
            return  # Already evaluated this signal

        self._last_signal_id = sig_id
        direction = signal.get("signal", "NO_TRADE")

        # ── Gate 1: Is it a trade signal? ──
        if direction == "NO_TRADE":
            return

        # ── Gate 2: Tier + confidence threshold ──
        tier = signal.get("tier", "DEVELOPING")
        confidence = signal.get("confidence", 0)

        if not self.config.meets_tier(tier):
            self.decisions.record("SKIPPED", f"Tier {tier} below minimum {self.config.min_tier}", signal)
            return

        if confidence < self.config.min_confidence:
            self.decisions.record("SKIPPED", f"Confidence {confidence:.2f} below minimum {self.config.min_confidence}", signal)
            return

        # ── Gate 3: Trading hours + no-new-entries cutoff ──
        if not self._in_trading_hours():
            self.decisions.record("SKIPPED", "Outside trading hours", signal)
            return

        # Time gate: no new entries after 2:30 PM ET (gamma risk)
        try:
            from .confluence import ET
            now_et = datetime.now(ET).time()
            if now_et >= self.config.no_new_entries_after:
                self.decisions.record("SKIPPED", f"No new entries after {self.config.no_new_entries_after.strftime('%H:%M')} ET (gamma risk)", signal)
                return
        except Exception:
            pass

        # ── Gate 4: Daily loss circuit breaker ──
        if self.config.max_daily_loss > 0 and self._daily_pnl <= -self.config.max_daily_loss:
            self.decisions.record("HALTED", f"CIRCUIT BREAKER: Daily loss ${self._daily_pnl:.2f} hit limit -${self.config.max_daily_loss:.0f}", signal)
            return

        # Throttle: at 50% of daily loss limit, require TEXTBOOK only + log warning
        if self.config.daily_loss_throttle > 0 and self._daily_pnl <= -self.config.daily_loss_throttle:
            if tier != "TEXTBOOK":
                self.decisions.record("SKIPPED", f"Daily loss throttle active (${self._daily_pnl:.2f}): only TEXTBOOK tier allowed", signal)
                return
            self.decisions.record("THROTTLED", f"Daily loss throttle: accepting TEXTBOOK signal despite ${self._daily_pnl:.2f} drawdown", signal)

        if self.config.max_trades_per_day > 0 and self._daily_trades >= self.config.max_trades_per_day:
            self.decisions.record("SKIPPED", f"Max daily trades ({self.config.max_trades_per_day}) reached", signal)
            return

        # ── Gate 4b: IV-based position sizing check ──
        if self.config.iv_scaling_enabled:
            iv_scale = self._get_iv_scale_factor()
            if iv_scale <= 0:
                self.decisions.record("SKIPPED", "IV rank >80%: extreme volatility, skipping day", signal)
                return

        # ── Gate 5: Position limits ──
        open_trades = get_open_trades()
        if len(open_trades) >= self.config.max_open_positions:
            self.decisions.record("SKIPPED", f"Max open positions ({self.config.max_open_positions}) reached", signal)
            return

        # ── Gate 6: Cooldown ──
        if self._last_trade_time:
            elapsed = (datetime.now(timezone.utc) - self._last_trade_time).total_seconds()
            if elapsed < self.config.min_seconds_between_trades:
                self.decisions.record("SKIPPED", f"Cooldown ({elapsed:.0f}s < {self.config.min_seconds_between_trades}s)", signal)
                return

        # ── Gate 7: Don't enter if we already have a position in the same direction ──
        for t in open_trades:
            existing_type = t.get("option_type", "")
            new_type = "call" if direction == "BUY_CALL" else "put"
            if existing_type == new_type:
                self.decisions.record("SKIPPED", f"Already have an open {new_type} position", signal)
                return

        # ── Gate 8: News circuit breaker — pause entries on BREAKING news ──
        try:
            from .agents.news_agent import get_news_circuit_breaker
            cb = get_news_circuit_breaker()
            if cb.get("active"):
                cb_direction = cb.get("direction", "")
                cb_headline = (cb.get("headline") or "")[:80]
                # Block ALL entries on BREAKING, or entries against the news direction
                self.decisions.record(
                    "SKIPPED",
                    f"News circuit breaker active [{cb.get('urgency')}]: {cb_headline}",
                    signal,
                )
                # If we have open positions and news is against them, force exit
                if open_trades and cb_direction:
                    for t in open_trades:
                        opt_type = t.get("option_type", "")
                        # Bearish news + holding calls = bad; bullish news + holding puts = bad
                        should_exit = (
                            (cb_direction == "bearish" and opt_type == "call") or
                            (cb_direction == "bullish" and opt_type == "put")
                        )
                        if should_exit:
                            await self._execute_exit(t, f"news_circuit_breaker_{cb_direction}")
                return
        except ImportError:
            pass  # news_agent not available — skip this gate

        # ── Gate 9: Re-validate estimated strikes with live chain ──
        strike_source = signal.get("strike_source", "")
        if strike_source == "estimated_fallback":
            self.decisions.record(
                "REVALIDATE",
                "Signal uses estimated strike — fetching live chain to validate",
                signal,
            )
            validated = await self._revalidate_strike(signal)
            if validated:
                signal = validated
                self.decisions.record(
                    "VALIDATED",
                    f"Strike re-validated: {signal.get('strike')} @ ${signal.get('entry_price', 0):.2f} "
                    f"(source={signal.get('strike_source')})",
                    signal,
                )
            else:
                self.decisions.record(
                    "SKIPPED",
                    "Cannot validate estimated strike — chain still unavailable",
                    signal,
                )
                return

        # ═══ ALL GATES PASSED — EXECUTE TRADE ═══
        await self._execute_signal(signal, open_trades)

    async def _execute_signal(self, signal: Dict, open_trades: List[Dict]):
        """Execute a signal through the paper trader with IV-scaled sizing."""
        try:
            # Apply IV scaling and time confidence to the signal
            iv_scale = self._get_iv_scale_factor() if self.config.iv_scaling_enabled else 1.0
            time_mult = self._get_time_confidence_multiplier()

            # Throttle sizing if in daily loss throttle zone
            throttle_mult = 0.5 if (self.config.daily_loss_throttle > 0
                                     and self._daily_pnl <= -self.config.daily_loss_throttle) else 1.0

            effective_risk_pct = self.config.max_risk_per_trade_pct * iv_scale * throttle_mult
            effective_confidence = signal.get("confidence", 0) * time_mult

            # Inject the scaled values into the signal for the paper trader
            signal_with_scaling = {
                **signal,
                "confidence": min(effective_confidence, 1.0),
                "_iv_scale": iv_scale,
                "_time_mult": time_mult,
                "_throttle_mult": throttle_mult,
                "_effective_risk_pct": round(effective_risk_pct, 3),
            }

            self.decisions.record(
                "SIZING",
                f"IV scale={iv_scale:.1f}x, time={time_mult:.1f}x, throttle={throttle_mult:.1f}x "
                f"→ risk={effective_risk_pct:.2f}% (base={self.config.max_risk_per_trade_pct}%)",
                signal,
            )

            # Use the paper trader's full pipeline (validation + execution)
            result = await self.trader.process_signal(
                signal=signal_with_scaling,
                open_trades=open_trades,
                daily_pnl=self._daily_pnl,
            )

            action = result.get("action", "none")

            if action == "entered":
                self._last_trade_time = datetime.now(timezone.utc)
                self._daily_trades += 1
                self.decisions.record(
                    "TRADE_ENTERED",
                    f"{signal.get('signal')} {signal.get('strike')} "
                    f"(tier={signal.get('tier')}, conf={signal.get('confidence', 0):.2f})",
                    signal,
                    {"trade_id": result.get("trade_id")},
                )
            elif action == "rejected":
                reason = result.get("validation", {}).get("reject_reason", "unknown")
                self.decisions.record("REJECTED", f"Validation rejected: {reason}", signal)
            else:
                self.decisions.record("SKIPPED", f"Paper trader returned action={action}", signal)

        except Exception as e:
            self.decisions.record("ERROR", f"Execution error: {e}", signal)
            logger.error(f"Auto-execute error: {e}", exc_info=True)

    # ── Strike Re-validation ──

    async def _revalidate_strike(self, signal: Dict) -> Optional[Dict]:
        """
        When a signal was generated with an estimated fallback strike,
        fetch fresh chain data and re-select the strike with real prices.
        Returns updated signal or None if chain still unavailable.
        """
        import aiohttp
        try:
            action = signal.get("signal", "")
            expiry = signal.get("expiry", "")
            symbol = signal.get("symbol", "SPY")
            root = "SPXW" if symbol == "SPX" else symbol

            async with aiohttp.ClientSession() as session:
                url = f"{cfg.DASHBOARD_BASE_URL}/api/options/chain?root={root}&exp={expiry}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        return None
                    chain = await resp.json()

            if not chain:
                return None

            side = "calls" if action == "BUY_CALL" else "puts"
            options = chain.get(side, [])
            if not options:
                return None

            # Re-run strike selection with real chain
            from .confluence import select_strike
            price = signal.get("levels", {}).get("current_price", 0)
            if price <= 0:
                # Try quote endpoint
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{cfg.DASHBOARD_BASE_URL}/api/quote?symbol={symbol}",
                        timeout=aiohttp.ClientTimeout(total=3),
                    ) as resp:
                        if resp.status == 200:
                            q = await resp.json()
                            price = q.get("last", 0) or q.get("price", 0)
                if price <= 0:
                    return None

            strike_info = select_strike(
                action=action,
                current_price=price,
                chain=chain,
                target_delta=0.32,
            )

            if not strike_info or strike_info.get("entry_price", 0) <= 0:
                return None

            # Update signal with real strike data
            updated = {**signal}
            updated["strike"] = strike_info["strike"]
            updated["entry_price"] = strike_info["entry_price"]
            updated["bid"] = strike_info.get("bid", 0)
            updated["ask"] = strike_info.get("ask", 0)
            updated["option_delta"] = strike_info.get("delta")
            updated["option_iv"] = strike_info.get("iv")
            updated["strike_source"] = strike_info.get("source", "revalidated")

            logger.info(
                f"[AutoTrader] Strike re-validated: {strike_info['strike']} "
                f"@ ${strike_info['entry_price']:.2f} (was estimated)"
            )
            return updated

        except Exception as e:
            logger.warning(f"[AutoTrader] Strike re-validation failed: {e}")
            return None

    # ── Exit Monitoring ──

    async def _check_exits(self):
        """Check open positions for exit triggers."""
        open_trades = get_open_trades()
        if not open_trades:
            return

        for trade in open_trades:
            exit_reason = self._evaluate_exit(trade)
            if exit_reason:
                await self._execute_exit(trade, exit_reason)

    # ── Tier-Adaptive Exit Parameters ──
    # Higher-conviction signals get more room to breathe; lower tiers get tighter stops.
    # Format: {tier: (stop_loss_pct, profit_target_pct, velocity_threshold_pct)}
    TIER_EXIT_PARAMS = {
        "TEXTBOOK": {"stop_pct": 0.40, "target_pct": 0.30, "velocity_thresh": 10.0, "trail_activation": 0.08},
        "HIGH":     {"stop_pct": 0.30, "target_pct": 0.20, "velocity_thresh": 8.0,  "trail_activation": 0.10},
        "VALID":    {"stop_pct": 0.20, "target_pct": 0.15, "velocity_thresh": 6.0,  "trail_activation": 0.12},
        "DEVELOPING": {"stop_pct": 0.15, "target_pct": 0.10, "velocity_thresh": 5.0, "trail_activation": 0.15},
    }

    def _get_tier_exit_params(self, trade: Dict) -> Dict:
        """Get tier-adaptive exit parameters for a trade based on its entry signal tier."""
        tier = trade.get("tier") or trade.get("signal_tier", "HIGH")
        return self.TIER_EXIT_PARAMS.get(tier, self.TIER_EXIT_PARAMS["HIGH"])

    def _evaluate_exit(self, trade: Dict) -> Optional[str]:
        """
        Dynamic Exit Engine — 7-level priority system with tier-adaptive parameters.

        Priority order:
          1. TARGET HIT — immediate profit take (highest priority)
          2. PROFIT_PROTECTED — dynamic giveback tiers
          3. STOPPED — hard stop loss floor (tier-scaled)
          4. VELOCITY_STOP — fast drop in one tick (tier-scaled threshold)
          5. BREAKEVEN — if was ever up 5%+, never go red
          5b. TRAILING_STOP — with tier-scaled activation
          6. TIME_EXIT — max hold / 0DTE hard stop (last resort)

        Tier scaling:
          TEXTBOOK: -40% stop / +30% target / 10% velocity (most room)
          HIGH:     -30% stop / +20% target / 8% velocity
          VALID:    -20% stop / +15% target / 6% velocity
          DEVELOPING: -15% stop / +10% target / 5% velocity (tightest)

        Returns exit reason string, or None if no exit needed.
        """
        entry_price = trade.get("entry_price", 0)
        if entry_price <= 0:
            return None

        current_price = self._estimate_current_price(trade)
        if current_price is None:
            return None

        trade_id = trade.get("id", "")
        pnl_pct = ((current_price - entry_price) / entry_price) * 100

        # Get tier-adaptive parameters
        tier_params = self._get_tier_exit_params(trade)

        # Track peak price for this trade
        prev_peak = self._peak_prices.get(trade_id, entry_price)
        if current_price > prev_peak:
            self._peak_prices[trade_id] = current_price
        peak_price = self._peak_prices.get(trade_id, entry_price)

        # Compute gains from entry and from peak
        peak_gain_pct = ((peak_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
        current_gain_pct = pnl_pct
        (peak_price - entry_price) * 100 * trade.get("quantity", 1)

        # Target / stop from signal (override with tier-adaptive if signal didn't set them)
        target_price = self._get_signal_target(trade)
        stop_price = self._get_signal_stop(trade)

        # If no explicit target/stop from the signal, compute tier-adaptive ones
        if not target_price:
            target_price = entry_price * (1 + tier_params["target_pct"])
        if not stop_price:
            stop_price = entry_price * (1 - tier_params["stop_pct"])

        # ═══ PRIORITY 1: TARGET HIT — immediate profit take ═══
        if self.config.auto_exit_profit_target and target_price:
            if current_price >= target_price:
                self._cleanup_trade_state(trade_id)
                return "profit_target"

        # ═══ PRIORITY 2: DYNAMIC PROFIT PROTECTION ═══
        # Never give back more than X% of peak gains:
        #   peak +5-10%  → max 50% giveback
        #   peak +10-20% → max 30% giveback
        #   peak +20-40% → max 20% giveback
        #   peak +40%+   → max 10% giveback
        if peak_gain_pct >= 5.0 and current_gain_pct > 0:
            if peak_gain_pct >= 40:
                max_giveback = 0.10
            elif peak_gain_pct >= 20:
                max_giveback = 0.20
            elif peak_gain_pct >= 10:
                max_giveback = 0.30
            else:
                max_giveback = 0.50

            floor_price = entry_price + (peak_price - entry_price) * (1 - max_giveback)
            if current_price <= floor_price:
                self.decisions.record(
                    "EXIT_SIGNAL",
                    f"Profit protection: peak +{peak_gain_pct:.1f}%, now +{current_gain_pct:.1f}%, "
                    f"floor=${floor_price:.2f} (max {max_giveback*100:.0f}% giveback)",
                    extra={"trade_id": trade_id},
                )
                self._cleanup_trade_state(trade_id)
                return "profit_protected"

        # ═══ PRIORITY 3: HARD STOP LOSS (tier-adaptive) ═══
        if self.config.auto_exit_stop_loss and stop_price:
            if current_price <= stop_price:
                self._cleanup_trade_state(trade_id)
                return "stop_loss"

        # ═══ PRIORITY 4: VELOCITY STOP — fast drop in one tick (tier-adaptive) ═══
        velocity_thresh = tier_params["velocity_thresh"]
        prev_price = self._prev_prices.get(trade_id)
        self._prev_prices[trade_id] = current_price
        if prev_price and prev_price > 0:
            tick_drop_pct = ((prev_price - current_price) / prev_price) * 100
            if tick_drop_pct > velocity_thresh:
                self.decisions.record(
                    "EXIT_SIGNAL",
                    f"Velocity stop: dropped {tick_drop_pct:.1f}% in one tick "
                    f"(${prev_price:.2f} → ${current_price:.2f}, tier threshold={velocity_thresh}%)",
                    extra={"trade_id": trade_id},
                )
                self._cleanup_trade_state(trade_id)
                return "velocity_stop"

        # ═══ PRIORITY 5: BREAKEVEN STOP — if was ever up 5%+, never go red ═══
        if peak_gain_pct >= 5.0 and current_gain_pct <= 0.5:
            breakeven_price = entry_price * 1.005  # Exit at +0.5% (small buffer)
            if current_price <= breakeven_price:
                self._cleanup_trade_state(trade_id)
                return "breakeven_stop"

        # ═══ PRIORITY 5b: TRAILING STOP WITH TIER-ADAPTIVE ACTIVATION ═══
        tier_trail_activation = tier_params["trail_activation"]
        if self.config.trailing_stop_pct > 0:
            if peak_gain_pct >= tier_trail_activation * 100:
                # Trail is active — check if we've dropped too far from peak
                trail_pct = self.config.trailing_stop_pct
                # Tighten trail at higher profits
                if peak_gain_pct >= 25:
                    trail_pct = min(trail_pct, 0.10)  # 10% at +25%
                trail_floor = peak_price * (1 - trail_pct)
                if current_price <= trail_floor and current_gain_pct > 0:
                    self.decisions.record(
                        "EXIT_SIGNAL",
                        f"Trailing stop: peak +{peak_gain_pct:.1f}%, trail {trail_pct*100:.0f}%, "
                        f"floor=${trail_floor:.2f}, now=${current_price:.2f}",
                        extra={"trade_id": trade_id},
                    )
                    self._cleanup_trade_state(trade_id)
                    return "trailing_stop"

        # ═══ PRIORITY 6: TIME EXITS (staged for gamma risk) ═══
        if self.config.auto_exit_time_stop:
            from .confluence import ET
            now_et = datetime.now(ET).time()

            # 6a. 3:00 PM — force close ALL (unchanged)
            if now_et >= self.config.trading_end:
                self._cleanup_trade_state(trade_id)
                return "time_stop_0dte"

            # 6b. 2:45 PM — close any position that's NOT in profit
            if now_et >= self.config.close_losers_at and current_gain_pct <= 0:
                self.decisions.record(
                    "EXIT_SIGNAL",
                    f"2:45 PM loser exit: position at {current_gain_pct:.1f}% — closing before gamma spike",
                    extra={"trade_id": trade_id},
                )
                self._cleanup_trade_state(trade_id)
                return "time_stop_close_losers"

            # 6c. 2:30 PM — tighten stops on winning positions (trail at 10%)
            if now_et >= self.config.tighten_stops_at and current_gain_pct > 0:
                tight_floor = peak_price * 0.90  # 10% trail in final window
                if current_price <= tight_floor:
                    self._cleanup_trade_state(trade_id)
                    return "time_stop_tightened_trail"

        # 6d. Max hold time
        if self.config.max_hold_minutes > 0:
            entry_time = trade.get("entry_time", "")
            if entry_time:
                try:
                    entry_dt = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
                    hold_minutes = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 60
                    if hold_minutes >= self.config.max_hold_minutes:
                        self._cleanup_trade_state(trade_id)
                        return "max_hold_time"
                except (ValueError, TypeError):
                    pass

        return None

    def _cleanup_trade_state(self, trade_id: str):
        """Remove tracking state for a closed trade."""
        self._peak_prices.pop(trade_id, None)
        self._prev_prices.pop(trade_id, None)

    def _estimate_current_price(self, trade: Dict) -> Optional[float]:
        """
        Get estimated current option price.

        In simulation mode, uses Black-Scholes from position tracker.
        In paper mode, would use Alpaca position data.
        """
        # Use the position tracker's cached prices
        positions = self.tracker.get_live_positions()
        trade_id = trade.get("id")
        for pos in positions:
            # position_tracker returns "trade_id" not "id"
            if pos.get("trade_id") == trade_id:
                return pos.get("current_price") or pos.get("mark_price")

        # Fallback: estimate from entry price (no movement)
        return trade.get("entry_price")

    def _get_signal_target(self, trade: Dict) -> Optional[float]:
        """Get the profit target from the original signal."""
        sig_id = trade.get("signal_id")
        if not sig_id:
            return None
        conn = None
        try:
            from .signal_db import _get_conn
            conn = _get_conn()
            row = conn.execute("SELECT target_price FROM signals WHERE id = ?", (sig_id,)).fetchone()
            return dict(row).get("target_price") if row else None
        except Exception:
            return None
        finally:
            if conn:
                try: conn.close()
                except Exception: pass

    def _get_signal_stop(self, trade: Dict) -> Optional[float]:
        """Get the stop loss from the original signal."""
        sig_id = trade.get("signal_id")
        if not sig_id:
            return None
        conn = None
        try:
            from .signal_db import _get_conn
            conn = _get_conn()
            row = conn.execute("SELECT stop_price FROM signals WHERE id = ?", (sig_id,)).fetchone()
            return dict(row).get("stop_price") if row else None
        except Exception:
            return None
        finally:
            if conn:
                try: conn.close()
                except Exception: pass

    async def _execute_exit(self, trade: Dict, reason: str):
        """Execute a trade exit and process the result."""
        try:
            current_price = self._estimate_current_price(trade) or trade.get("entry_price", 0)

            success = await self.trader.exit_trade(
                trade=trade,
                exit_price=current_price,
                exit_reason=reason,
            )

            if success:
                # Calculate P&L
                entry_price = trade.get("entry_price", 0)
                quantity = trade.get("quantity", 1)
                pnl = (current_price - entry_price) * 100 * quantity
                self._daily_pnl += pnl

                self.decisions.record(
                    "TRADE_EXITED",
                    f"Exit {trade.get('option_type')} @ ${current_price:.2f} "
                    f"(reason={reason}, P&L=${pnl:.2f})",
                    extra={"trade_id": trade.get("id"), "pnl": pnl, "reason": reason},
                )

                # Grade the trade
                try:
                    trade_for_grade = {**trade, "exit_price": current_price, "exit_reason": reason, "pnl": pnl}
                    grade_result = grade_trade(trade_for_grade)
                    logger.info(f"Trade graded: {grade_result.get('grade', '?')} (score={grade_result.get('score', 0):.0f})")
                except Exception as e:
                    logger.warning(f"Grading failed: {e}")

                # Notify weight learner
                if self.config.learn_from_trades and self._on_trade_closed:
                    try:
                        await self._on_trade_closed(trade, pnl, reason)
                    except Exception as e:
                        logger.warning(f"Weight learner callback error: {e}")

        except Exception as e:
            self.decisions.record("ERROR", f"Exit error: {e}", extra={"trade_id": trade.get("id")})
            logger.error(f"Auto-exit error: {e}", exc_info=True)

    # ── Helpers ──

    def _in_trading_hours(self) -> bool:
        """Check if current ET time is within trading hours."""
        try:
            from .confluence import ET
            now_et = datetime.now(ET).time()
            return self.config.trading_start <= now_et <= self.config.trading_end
        except Exception:
            return False

    def _get_iv_scale_factor(self) -> float:
        """
        Get position size multiplier based on current IV rank.

        IV-scaled sizing (research-backed):
          IV 0-20%  → 1.5x (low vol, range-bound)
          IV 21-50% → 1.0x (normal)
          IV 51-80% → 0.5x (high vol, wider swings)
          IV 81%+   → 0.0x (extreme vol, SKIP DAY)
        """
        try:
            # Get VIX percentile from the signal engine's cached regime
            from .signal_api import engine
            regime = getattr(engine, '_cached_regime', None)
            if not regime:
                return 1.0  # No regime data — use base size

            regime_dict = regime.to_dict() if hasattr(regime, 'to_dict') else {}
            # vix_percentile is 0-100 (where current VIX sits vs 30-day range)
            vix_pct = regime_dict.get('vix_percentile', 30)
            iv_rank = vix_pct / 100.0  # Normalize to 0-1

            if iv_rank >= 0.81:
                return 0.0   # Extreme vol — skip entirely
            elif iv_rank >= 0.51:
                return 0.5   # High vol — half size
            elif iv_rank >= 0.21:
                return 1.0   # Normal — base size
            else:
                return 1.5   # Low vol — 1.5x size
        except Exception:
            return 1.0  # Default if regime detector unavailable

    def _get_time_confidence_multiplier(self) -> float:
        """
        Time-of-day confidence multiplier (research-backed).

        Peak entry window: 9:50-10:30 AM (opening range established).
        Steady: 10:30 AM-2:00 PM.
        Declining: 2:00 PM+ (gamma building).
        """
        try:
            from .confluence import ET
            now_et = datetime.now(ET).time()

            if now_et < dt_time(9, 50):
                return 0.7   # Pre-opening range
            elif now_et < dt_time(10, 30):
                return 1.2   # PEAK: opening range set
            elif now_et < dt_time(14, 0):
                return 1.0   # Steady theta capture
            elif now_et < dt_time(14, 30):
                return 0.5   # Gamma building
            else:
                return 0.0   # No new entries
        except Exception:
            return 1.0

    def _reset_daily_counters(self):
        """Reset daily P&L and trade counters."""
        # Calculate from today's actual trades
        todays = get_todays_trades()
        closed = [t for t in todays if t.get("exit_time")]
        self._daily_pnl = sum(t.get("pnl", 0) for t in closed)
        self._daily_trades = len(todays)
        logger.info(f"Daily counters reset: pnl=${self._daily_pnl:.2f}, trades={self._daily_trades}")

    def status(self) -> Dict:
        """Current status of the autonomous trader."""
        return {
            "running": self.is_running,
            "enabled": self.config.enabled,
            "mode": self.config.mode,
            "session_start": self._session_start.isoformat() if self._session_start else None,
            "daily_pnl": round(self._daily_pnl, 2),
            "daily_trades": self._daily_trades,
            "open_positions": len(get_open_trades()),
            "in_trading_hours": self._in_trading_hours(),
            "last_trade_time": self._last_trade_time.isoformat() if self._last_trade_time else None,
            "config": self.config.to_dict(),
            "decision_stats": self.decisions.stats(),
        }


# ═══════════════════════════════════════════════════════════════════════════
# TRAINING DATA COLLECTOR — stores enriched data for future ML pipeline
# ═══════════════════════════════════════════════════════════════════════════

class TrainingDataCollector:
    """
    Collects and stores training data for future ML model training.

    Every signal + outcome pair is stored with full factor breakdown,
    market context, and result. This is the raw material for:
    1. Supervised learning (factor → outcome prediction)
    2. Reinforcement learning (reward = P&L)
    3. Factor importance analysis
    """

    def __init__(self, db_path: Optional[str] = None):
        import os
        self._db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        self._db_path = db_path or os.path.join(self._db_dir, "training_data.db")
        self._init_db()

    def _init_db(self):
        import sqlite3
        import os
        os.makedirs(self._db_dir, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS training_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                signal_id TEXT,
                trade_id TEXT,

                -- Signal features (inputs)
                direction TEXT,
                confidence REAL,
                tier TEXT,
                factors TEXT,           -- JSON: full factor breakdown with scores

                -- Market context at signal time
                spy_price REAL,
                iv_rank REAL,
                gex_regime TEXT,
                session_phase TEXT,
                vix REAL,
                pcr REAL,
                vwap_distance REAL,     -- price distance from VWAP in %

                -- Strike selection
                strike REAL,
                expiry TEXT,
                option_type TEXT,
                delta REAL,
                entry_price REAL,
                target_price REAL,
                stop_price REAL,

                -- Outcome (labels) — filled after trade closes
                was_traded INTEGER DEFAULT 0,
                pnl REAL,
                pnl_pct REAL,
                exit_reason TEXT,
                hold_minutes REAL,
                max_favorable REAL,
                max_adverse REAL,
                grade TEXT,
                grade_score REAL,

                -- Factor-level outcome attribution
                factor_scores TEXT,     -- JSON: which factors contributed to win/loss

                -- Weight snapshot at time of signal
                weight_version TEXT,
                weights_snapshot TEXT    -- JSON: factor weights used for this signal
            );

            CREATE TABLE IF NOT EXISTS weight_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                version TEXT NOT NULL,
                weights TEXT NOT NULL,       -- JSON: full weight dict
                trigger TEXT,               -- "trade_closed", "manual", "daily_reset"
                metrics TEXT                -- JSON: performance metrics at this point
            );

            CREATE INDEX IF NOT EXISTS idx_ts_timestamp ON training_samples(timestamp);
            CREATE INDEX IF NOT EXISTS idx_ts_traded ON training_samples(was_traded);
            CREATE INDEX IF NOT EXISTS idx_ts_direction ON training_samples(direction);
            CREATE INDEX IF NOT EXISTS idx_wh_version ON weight_history(version);
        """)
        conn.close()

    def record_signal(self, signal: Dict, weights: Dict) -> Optional[int]:
        """Record a signal as a training sample (outcome filled later)."""
        import sqlite3
        conn = None
        try:
            conn = sqlite3.connect(self._db_path)

            factors = signal.get("factors", [])
            signal.get("indicators", {})
            levels = signal.get("levels", {})
            options = signal.get("options_analytics", {})

            # Extract VWAP distance
            spy_price = signal.get("price") or signal.get("spot_price", 0)
            vwap = levels.get("vwap", 0)
            vwap_dist = ((spy_price - vwap) / vwap * 100) if vwap and spy_price else 0

            conn.execute("""
                INSERT INTO training_samples (
                    timestamp, signal_id, direction, confidence, tier, factors,
                    spy_price, iv_rank, gex_regime, session_phase, vix, pcr, vwap_distance,
                    strike, expiry, option_type, delta, entry_price, target_price, stop_price,
                    weight_version, weights_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                signal.get("id"),
                signal.get("signal"),
                signal.get("confidence"),
                signal.get("tier"),
                json.dumps(factors),
                spy_price,
                options.get("iv_rank"),
                signal.get("gex", {}).get("regime") if isinstance(signal.get("gex"), dict) else signal.get("gex_regime"),
                signal.get("session", {}).get("phase") if isinstance(signal.get("session"), dict) else None,
                None,  # VIX — would need separate fetch
                options.get("pcr"),
                round(vwap_dist, 4),
                signal.get("strike"),
                signal.get("expiry"),
                "call" if signal.get("signal") == "BUY_CALL" else "put" if signal.get("signal") == "BUY_PUT" else None,
                signal.get("option_delta"),
                signal.get("entry_price"),
                signal.get("target_price"),
                signal.get("stop_price"),
                "v1",  # Will be dynamic once weight learner is running
                json.dumps(weights),
            ))

            row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.commit()
            return row_id

        except Exception as e:
            logger.warning(f"Training data record error: {e}")
            return None
        finally:
            if conn:
                try: conn.close()
                except Exception: pass

    def record_outcome(self, signal_id: str, trade_data: Dict):
        """Fill in the outcome columns for a completed trade."""
        import sqlite3
        conn = None
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                UPDATE training_samples SET
                    trade_id = ?,
                    was_traded = 1,
                    pnl = ?,
                    pnl_pct = ?,
                    exit_reason = ?,
                    hold_minutes = ?,
                    max_favorable = ?,
                    max_adverse = ?,
                    grade = ?,
                    grade_score = ?
                WHERE signal_id = ?
            """, (
                trade_data.get("id"),
                trade_data.get("pnl"),
                trade_data.get("pnl_pct"),
                trade_data.get("exit_reason"),
                trade_data.get("hold_minutes"),
                trade_data.get("max_favorable"),
                trade_data.get("max_adverse"),
                trade_data.get("grade"),
                trade_data.get("grade_score"),
                signal_id,
            ))
            conn.commit()
        except Exception as e:
            logger.warning(f"Training outcome record error: {e}")
        finally:
            if conn:
                try: conn.close()
                except Exception: pass

    def record_weights(self, version: str, weights: Dict, trigger: str, metrics: Optional[Dict] = None):
        """Snapshot the current factor weights."""
        import sqlite3
        conn = None
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                INSERT INTO weight_history (timestamp, version, weights, trigger, metrics)
                VALUES (?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                version,
                json.dumps(weights),
                trigger,
                json.dumps(metrics) if metrics else None,
            ))
            conn.commit()
        except Exception as e:
            logger.warning(f"Weight history record error: {e}")
        finally:
            if conn:
                try: conn.close()
                except Exception: pass

    def get_training_data(self, traded_only: bool = True, limit: int = 1000) -> List[Dict]:
        """Get training samples for ML pipeline."""
        import sqlite3
        conn = None
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            where = "WHERE was_traded = 1 AND pnl IS NOT NULL" if traded_only else ""
            rows = conn.execute(
                f"SELECT * FROM training_samples {where} ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Training data fetch error: {e}")
            return []
        finally:
            if conn:
                try: conn.close()
                except Exception: pass

    def get_stats(self) -> Dict:
        """Get training data statistics."""
        import sqlite3
        conn = None
        try:
            conn = sqlite3.connect(self._db_path)
            total = conn.execute("SELECT COUNT(*) FROM training_samples").fetchone()[0]
            traded = conn.execute("SELECT COUNT(*) FROM training_samples WHERE was_traded = 1").fetchone()[0]
            profitable = conn.execute("SELECT COUNT(*) FROM training_samples WHERE pnl > 0").fetchone()[0]
            weight_versions = conn.execute("SELECT COUNT(DISTINCT version) FROM weight_history").fetchone()[0]
            return {
                "total_samples": total,
                "traded_samples": traded,
                "profitable_trades": profitable,
                "win_rate": (profitable / traded * 100) if traded > 0 else 0,
                "weight_versions": weight_versions,
            }
        except Exception:
            return {"total_samples": 0}
        finally:
            if conn:
                try: conn.close()
                except Exception: pass
