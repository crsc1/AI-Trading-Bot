"""
PositionManager — Single source of truth for all position state.

Absorbs functionality from:
  - position_tracker.py (live P&L, exit triggers, MFE/MAE, Greeks)
  - autonomous_trader.py (exit rules, timing, circuit breakers)
  - paper_trader.py (execution routing)

Rules:
  - ONE writer to the trades table (no race conditions)
  - ONE set of exit rules (not scattered across files)
  - ONE P&L calculation (not three different ones)
  - Uses DataRouter for all market data (no direct API calls)
"""

import asyncio
import aiohttp
import json
import logging
import time
import uuid
from datetime import datetime, timezone, time as dt_time
from collections import deque
from typing import Optional, Dict, List, Callable

from .signal_db import (
    store_signal, mark_signal_traded, mark_signal_rejected,
    store_trade, close_trade, get_open_trades, get_trade_history,
    get_todays_trades,
)
from . import data_router
from .config import cfg
from . import llm_validator
from .session_gate import session_gate
from .dynamic_exit import dynamic_exit_engine

logger = logging.getLogger(__name__)

# ─── Timezone ─────────────────────────────────────────────────────────────────

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except ImportError:
    import pytz
    ET = pytz.timezone("America/New_York")

# ─── Constants ────────────────────────────────────────────────────────────────

ACCOUNT_BALANCE = cfg.ACCOUNT_BALANCE

TIER_ORDER = {"TEXTBOOK": 4, "HIGH": 3, "VALID": 2, "DEVELOPING": 1}

# Alpaca execution
ALPACA_TRADING_URL = cfg.ALPACA_BASE_URL
ALPACA_KEY = cfg.ALPACA_API_KEY
ALPACA_SECRET = cfg.ALPACA_SECRET_KEY
ALPACA_HEADERS = cfg.ALPACA_HEADERS


# ═══════════════════════════════════════════════════════════════════════════════
# EXIT RULES — Single definition, used everywhere
# ═══════════════════════════════════════════════════════════════════════════════

class ExitDecision:
    """Result of an exit check — supports both full and partial exits."""
    __slots__ = ("action", "reason", "qty")

    def __init__(self, action: str, reason: str, qty: int = 0):
        self.action = action   # "full", "partial", or "none"
        self.reason = reason
        self.qty = qty         # contracts to exit (0 = all remaining)

    def __bool__(self):
        return self.action != "none"

    def __str__(self):
        if self.action == "partial":
            return f"{self.reason} (partial: {self.qty})"
        return self.reason


class ExitRules:
    """All exit rules in one place. No more scattered definitions."""

    def __init__(self):
        # Profit / Loss
        self.stop_loss_pct: float = cfg.EXIT_STOP_LOSS_PCT          # -50% of entry
        self.profit_target_pct: float = cfg.EXIT_PROFIT_TARGET_PCT        # +100% of entry
        self.trailing_stop_pct: float = cfg.EXIT_TRAILING_STOP_PCT        # 15% trailing from peak
        self.trailing_stop_activation: float = cfg.EXIT_TRAILING_ACTIVATION_PCT  # Activates after +10% gain

        # Time
        self.max_hold_minutes: int = cfg.EXIT_MAX_HOLD_MINUTES             # 0DTE max hold
        self.no_new_entries_after: dt_time = cfg.NO_NEW_ENTRIES_AFTER  # 2:30 PM ET
        self.close_losers_at: dt_time = cfg.CLOSE_LOSERS_AT       # 2:45 PM ET
        self.hard_exit_time: dt_time = cfg.HARD_EXIT_TIME          # 3:00 PM ET

        # Theta decay
        self.theta_decay_exit: bool = cfg.EXIT_THETA_DECAY_ENABLED          # Exit if theta eating P&L
        self.theta_decay_threshold: float = cfg.EXIT_THETA_DECAY_THRESHOLD   # -3% from theta alone

        # Partial exit / scale-out
        self.partial_exit_enabled: bool = cfg.PARTIAL_EXIT_ENABLED
        self.partial_exit_tiers: list = cfg.PARTIAL_EXIT_TIERS
        self.remainder_trail_pct: float = cfg.PARTIAL_EXIT_REMAINDER_TRAIL_PCT
        self.single_contract_trail_activation: float = cfg.SINGLE_CONTRACT_TRAIL_ACTIVATION

    def check(self, position: Dict) -> Optional[str]:
        """
        Check all exit rules for a position.
        Returns exit_reason string or None if no exit needed.
        For partial exit logic, use check_with_partial() instead.
        """
        decision = self.check_with_partial(position)
        if decision and decision.action == "full":
            return decision.reason
        if decision and decision.action == "partial":
            # Legacy callers only see full exits — partials handled by exit_monitor
            return None
        return None

    def check_with_partial(self, position: Dict) -> Optional[ExitDecision]:
        """
        Check all exit rules, including partial exit tiers.
        Returns ExitDecision or None.
        """
        pnl_pct = position.get("unrealized_pnl_pct", 0)
        hold_minutes = position.get("hold_minutes", 0)
        max_pnl_pct = position.get("max_pnl_pct", 0)
        now_et = datetime.now(ET)
        current_time = now_et.time()
        quantity = int(position.get("quantity", 1))
        remaining = int(position.get("remaining_quantity") or quantity)
        partial_exits_done = position.get("partial_exits_done", [])

        # ── 1. Hard time stop (3:00 PM ET) — always full exit ──
        if current_time >= self.hard_exit_time:
            return ExitDecision("full", "time_stop_0dte")

        # ── 2. Close losers at 2:45 PM — full exit ──
        if current_time >= self.close_losers_at and pnl_pct < 0:
            return ExitDecision("full", "time_stop_losers")

        # ── 3. Stop loss — always full exit ──
        if pnl_pct <= self.stop_loss_pct:
            return ExitDecision("full", "stop_loss")

        # ── 4. Profit target — full exit on remainder ──
        if pnl_pct >= self.profit_target_pct:
            return ExitDecision("full", "profit_target")

        # ── 5. Partial exit scale-out tiers ──
        # Only if: enabled, multi-contract, and we haven't already exited this tier
        if (self.partial_exit_enabled and remaining >= 2 and quantity >= 2):
            completed_labels = {pe.get("reason", "") for pe in partial_exits_done}
            for tier in self.partial_exit_tiers:
                tier_label = tier["label"]
                if tier_label in completed_labels:
                    continue  # Already took this tier
                if pnl_pct >= tier["pnl_pct"]:
                    # Calculate qty to exit: fraction of original quantity, at least 1
                    qty_to_exit = max(1, int(quantity * tier["exit_frac"]))
                    # Don't exit more than remaining - 1 (keep at least 1 for trail)
                    qty_to_exit = min(qty_to_exit, remaining - 1)
                    if qty_to_exit > 0:
                        return ExitDecision("partial", tier_label, qty_to_exit)

        # ── 5b. Dynamic exit: move to breakeven ──
        # When dynamic exit engine sets CAUTION/WARNING, lock in breakeven
        if position.get("_move_to_breakeven") and pnl_pct > 0.005:
            # Dynamic engine says move to breakeven — if we're barely profitable
            # and giving it back, exit now
            if pnl_pct < 0.03 and max_pnl_pct > 0.05:
                return ExitDecision("full", "dynamic_breakeven_protect")

        # ── 6. Trailing stop ──
        # Dynamic exit engine can tighten trailing via _trailing_multiplier (0.5 = 50%)
        trail_mult = position.get("_trailing_multiplier", 1.0)

        # After partial exits, remainder gets a tighter trail
        all_partials_done = False
        if self.partial_exit_enabled and quantity >= 2:
            completed_labels = {pe.get("reason", "") for pe in partial_exits_done}
            all_partials_done = all(
                tier["label"] in completed_labels for tier in self.partial_exit_tiers
            )

        if all_partials_done and remaining > 0 and remaining < quantity:
            # Post-partial remainder: tighter trailing stop
            trail_pct = self.remainder_trail_pct * trail_mult
            trail_activation = self.partial_exit_tiers[-1]["pnl_pct"]  # activate from last tier
            if max_pnl_pct >= trail_activation:
                drawdown = max_pnl_pct - pnl_pct
                if drawdown >= trail_pct:
                    reason = "trailing_stop_remainder"
                    if trail_mult < 1.0:
                        reason += f"_dynamic({trail_mult:.0%})"
                    return ExitDecision("full", reason)
        elif quantity == 1:
            # Single-contract mode: lower trailing activation threshold
            activation = self.single_contract_trail_activation
            effective_trail = self.trailing_stop_pct * trail_mult
            if max_pnl_pct >= activation:
                drawdown = max_pnl_pct - pnl_pct
                if drawdown >= effective_trail:
                    reason = "trailing_stop"
                    if trail_mult < 1.0:
                        reason += f"_dynamic({trail_mult:.0%})"
                    return ExitDecision("full", reason)
        else:
            # Multi-contract but partials not all done yet: standard trailing
            effective_trail = self.trailing_stop_pct * trail_mult
            if max_pnl_pct >= self.trailing_stop_activation:
                drawdown = max_pnl_pct - pnl_pct
                if drawdown >= effective_trail:
                    reason = "trailing_stop"
                    if trail_mult < 1.0:
                        reason += f"_dynamic({trail_mult:.0%})"
                    return ExitDecision("full", reason)

        # ── 7. Max hold time ──
        if hold_minutes >= self.max_hold_minutes:
            return ExitDecision("full", "max_hold_time")

        # ── 8. Theta decay ──
        if self.theta_decay_exit and position.get("greeks_pnl"):
            theta_component = position["greeks_pnl"].get("theta_pnl_pct", 0)
            if theta_component < self.theta_decay_threshold and pnl_pct < 0.05:
                return ExitDecision("full", "theta_decay")

        return None

    def to_dict(self) -> Dict:
        return {
            "stop_loss_pct": self.stop_loss_pct,
            "profit_target_pct": self.profit_target_pct,
            "trailing_stop_pct": self.trailing_stop_pct,
            "trailing_stop_activation": self.trailing_stop_activation,
            "max_hold_minutes": self.max_hold_minutes,
            "no_new_entries_after": self.no_new_entries_after.isoformat(),
            "close_losers_at": self.close_losers_at.isoformat(),
            "hard_exit_time": self.hard_exit_time.isoformat(),
            "partial_exit_enabled": self.partial_exit_enabled,
            "partial_exit_tiers": self.partial_exit_tiers,
            "remainder_trail_pct": self.remainder_trail_pct,
        }

    def update(self, data: Dict):
        for k, v in data.items():
            if hasattr(self, k):
                if k in ("no_new_entries_after", "close_losers_at", "hard_exit_time"):
                    if isinstance(v, str):
                        parts = v.split(":")
                        v = dt_time(int(parts[0]), int(parts[1]))
                setattr(self, k, v)


# ═══════════════════════════════════════════════════════════════════════════════
# RISK MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class RiskManager:
    """Centralized risk checks before any trade entry."""

    def __init__(self):
        self.max_daily_loss: float = cfg.MAX_DAILY_LOSS          # Hard circuit breaker
        self.daily_loss_throttle: float = cfg.DAILY_LOSS_THROTTLE       # Reduce to TEXTBOOK only
        self.max_open_positions: int = cfg.MAX_OPEN_POSITIONS
        self.max_trades_per_day: int = cfg.MAX_TRADES_PER_DAY             # 0 = unlimited
        self.max_risk_per_trade_pct: float = cfg.MAX_RISK_PER_TRADE_PCT     # % of account
        self.min_seconds_between_trades: int = cfg.MIN_SECONDS_BETWEEN_TRADES
        self._last_trade_time: float = 0

    def check_entry(
        self,
        signal: Dict,
        open_positions: List[Dict],
        daily_pnl: float,
    ) -> Optional[str]:
        """
        Pre-entry risk check. Returns rejection reason or None if OK.
        """
        datetime.now(ET)

        # Circuit breaker
        if daily_pnl <= -self.max_daily_loss:
            return f"circuit_breaker: daily loss ${abs(daily_pnl):.0f} >= ${self.max_daily_loss:.0f}"

        # Max positions
        if len(open_positions) >= self.max_open_positions:
            return f"max_positions: {len(open_positions)} >= {self.max_open_positions}"

        # Throttle mode: only TEXTBOOK if losing
        if daily_pnl <= -self.daily_loss_throttle:
            tier = signal.get("tier", "DEVELOPING")
            if TIER_ORDER.get(tier, 0) < TIER_ORDER["TEXTBOOK"]:
                return f"throttled: daily loss ${abs(daily_pnl):.0f}, only TEXTBOOK allowed"

        # Trade frequency
        now_ts = time.time()
        if (now_ts - self._last_trade_time) < self.min_seconds_between_trades:
            return f"cooldown: {int(now_ts - self._last_trade_time)}s < {self.min_seconds_between_trades}s"

        # Max daily trades
        if self.max_trades_per_day > 0:
            todays = get_todays_trades()
            if len(todays) >= self.max_trades_per_day:
                return f"max_daily_trades: {len(todays)} >= {self.max_trades_per_day}"

        # Per-trade risk check: position cost vs max allowed
        entry_price = signal.get("entry_price", 0)
        max_contracts = signal.get("max_contracts", 1)
        if entry_price > 0 and self.max_risk_per_trade_pct > 0:
            position_cost = entry_price * max_contracts * 100  # options multiplier
            max_risk_dollars = cfg.STARTING_CAPITAL * self.max_risk_per_trade_pct
            if position_cost > max_risk_dollars:
                return (
                    f"risk_per_trade: ${position_cost:.0f} > "
                    f"{self.max_risk_per_trade_pct*100:.1f}% of ${cfg.STARTING_CAPITAL:.0f} "
                    f"(${max_risk_dollars:.0f})"
                )

        return None

    def record_trade(self):
        self._last_trade_time = time.time()

    def to_dict(self) -> Dict:
        return {
            "max_daily_loss": self.max_daily_loss,
            "daily_loss_throttle": self.daily_loss_throttle,
            "max_open_positions": self.max_open_positions,
            "max_trades_per_day": self.max_trades_per_day,
            "max_risk_per_trade_pct": self.max_risk_per_trade_pct,
            "min_seconds_between_trades": self.min_seconds_between_trades,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# POSITION MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class PositionManager:
    """
    Single source of truth for all positions.

    Responsibilities:
      1. Entry execution (simulation or Alpaca paper)
      2. Live P&L tracking with chain prices from DataRouter
      3. Exit rule enforcement (one set of rules)
      4. MFE/MAE tracking
      5. Database writes (single writer)
    """

    def __init__(
        self,
        mode: str = "simulation",
        on_trade_closed: Optional[Callable] = None,
    ):
        # Always run as simulation (paper trading). Alpaca paper mode removed.
        self.mode = "simulation"
        self.exit_rules = ExitRules()
        self.risk = RiskManager()
        self.on_trade_closed = on_trade_closed

        # Autotrader state
        self._enabled = False
        self._running = False
        self._signal_ref = None
        self._seen_signal_ids: set = set()

        # Chain price cache (updated each cycle)
        self._chain_cache: Dict = {}
        self._chain_updated_at: float = 0

        # Dynamic exit context cache (updated every 10s)
        self._exit_ctx_cache: Dict = {}
        self._exit_ctx_ts: float = 0

        # Background tasks
        self._monitor_task: Optional[asyncio.Task] = None
        self._signal_task: Optional[asyncio.Task] = None

        # Decision log
        self._decisions: deque = deque(maxlen=cfg.DECISION_LOG_MAX)

        # Config
        self.min_tier: str = cfg.PM_MIN_TIER
        self.min_confidence: float = cfg.PM_MIN_CONFIDENCE
        self.trading_start: dt_time = cfg.TRADING_START
        self.trading_end: dt_time = cfg.TRADING_END

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Decision Logging ──────────────────────────────────────────────────

    def _log_decision(self, action: str, reason: str, signal: Dict = None, **extra):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "reason": reason,
        }
        if signal:
            entry["signal_tier"] = signal.get("tier")
            entry["signal_confidence"] = signal.get("confidence")
            entry["signal_direction"] = signal.get("signal")
        entry.update(extra)
        self._decisions.append(entry)

    def get_decisions(self, limit: int = 50) -> List[Dict]:
        # deque doesn't support slice notation — convert to list first
        return list(reversed(list(self._decisions)[-limit:]))

    def get_stats(self) -> Dict:
        total = len(self._decisions)
        entered = sum(1 for d in self._decisions if d["action"] == "TRADE_ENTERED")
        exited = sum(1 for d in self._decisions if d["action"] == "TRADE_EXITED")
        skipped = sum(1 for d in self._decisions if d["action"] == "SKIPPED")
        return {
            "total_decisions": total,
            "trades_entered": entered,
            "trades_exited": exited,
            "signals_skipped": skipped,
        }

    # ── Autotrader Lifecycle ──────────────────────────────────────────────

    def enable(self) -> bool:
        self._enabled = True
        self._log_decision("TRADING_ENABLED", "User enabled autotrading")
        logger.info("[PositionManager] Autotrading ENABLED")
        return True

    def disable(self) -> bool:
        self._enabled = False
        self._log_decision("TRADING_DISABLED", "User disabled autotrading")
        logger.info("[PositionManager] Autotrading DISABLED")
        return True

    async def start(self, signal_history_ref):
        """Start the background monitoring loops."""
        if self._running:
            return
        self._signal_ref = signal_history_ref
        self._running = True

        # Start exit monitor (checks positions every 5s)
        self._monitor_task = asyncio.create_task(self._exit_monitor_loop())
        # Start signal consumer (checks for new signals every 3s)
        self._signal_task = asyncio.create_task(self._signal_consumer_loop())

        self._log_decision("LOOP_STARTED", "Background loops started")
        logger.info("[PositionManager] Background loops started")

    async def stop(self):
        """Stop all background loops."""
        self._running = False
        self._enabled = False
        for task in [self._monitor_task, self._signal_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._log_decision("LOOP_STOPPED", "Background loops stopped")
        logger.info("[PositionManager] Background loops stopped")

    # ── Signal Consumer Loop ──────────────────────────────────────────────

    async def _signal_consumer_loop(self):
        """Watch signal history for new tradeable signals."""
        while self._running:
            try:
                await asyncio.sleep(3)

                if not self._enabled:
                    continue

                now_et = datetime.now(ET)
                if not (self.trading_start <= now_et.time() <= self.trading_end):
                    continue

                if not self._signal_ref:
                    continue

                # Find newest unprocessed signal
                for signal in reversed(list(self._signal_ref)):
                    sig_id = signal.get("id")
                    if not sig_id or sig_id in self._seen_signal_ids:
                        continue

                    # Check if tradeable
                    direction = signal.get("signal", "NO_TRADE")
                    if direction == "NO_TRADE":
                        self._seen_signal_ids.add(sig_id)
                        continue

                    tier = signal.get("tier", "DEVELOPING")
                    confidence = signal.get("confidence", 0)

                    if TIER_ORDER.get(tier, 0) < TIER_ORDER.get(self.min_tier, 0):
                        self._seen_signal_ids.add(sig_id)
                        self._log_decision("SKIPPED", f"Tier {tier} < {self.min_tier}", signal)
                        continue

                    if confidence < self.min_confidence:
                        self._seen_signal_ids.add(sig_id)
                        self._log_decision("SKIPPED", f"Confidence {confidence:.3f} < {self.min_confidence}", signal)
                        continue

                    # Risk check
                    open_pos = get_open_trades()
                    daily_pnl = self._get_daily_pnl()
                    risk_reject = self.risk.check_entry(signal, open_pos, daily_pnl)
                    if risk_reject:
                        self._seen_signal_ids.add(sig_id)
                        self._log_decision("REJECTED", risk_reject, signal)
                        mark_signal_rejected(sig_id, risk_reject)
                        continue

                    # Session gate — smart session-aware filtering
                    # During midday chop, requires override checklist (key levels,
                    # multi-TF alignment, volume, tier). Other sessions pass through.
                    gate_allowed, gate_reason = session_gate.check(signal)
                    if not gate_allowed:
                        self._seen_signal_ids.add(sig_id)
                        self._log_decision("SESSION_GATED", gate_reason, signal)
                        mark_signal_rejected(sig_id, gate_reason)
                        continue

                    # No new entries after cutoff
                    if now_et.time() >= self.exit_rules.no_new_entries_after:
                        self._seen_signal_ids.add(sig_id)
                        self._log_decision("SKIPPED", "Past no-new-entries cutoff", signal)
                        continue

                    # ── ML Direction Predictor (advisory gate) ─────────────
                    # Blocks trades when P(win) < threshold. Gracefully allows
                    # all trades if model not trained or sklearn not installed.
                    try:
                        from .ml_predictor import ml_predictor
                        ml_allow, ml_prob, ml_reason = ml_predictor.predict(signal)
                        signal["ml_win_probability"] = round(ml_prob, 3)
                        signal["ml_reason"] = ml_reason
                        if not ml_allow:
                            self._seen_signal_ids.add(sig_id)
                            self._log_decision("ML_BLOCKED", ml_reason, signal)
                            mark_signal_rejected(sig_id, ml_reason)
                            continue
                    except Exception as _ml_err:
                        logger.debug(f"[PM] ML predictor error: {_ml_err}")

                    # ── LLM Validator (advisory, non-blocking) ──────────────
                    # Fire-and-forget: does not gate execution, result stored
                    # in llm_validator._verdicts for the AI Agent tab.
                    if cfg.LLM_VALIDATOR_ENABLED and cfg.ANTHROPIC_API_KEY:
                        try:
                            mkt_ctx = {}
                            try:
                                sym = signal.get("symbol", "SPY")
                                mkt_ctx = await data_router.get_quote(sym)
                            except Exception:
                                pass
                            recent_trades = get_trade_history(limit=5)
                            open_pos = get_open_trades()
                            await llm_validator.validate_signal_async(
                                signal,
                                market_context=mkt_ctx,
                                trade_history=recent_trades,
                                open_positions=open_pos,
                            )
                        except Exception as _e:
                            logger.debug(f"[PM] LLM validator fire error: {_e}")

                    # Execute!
                    result = await self.enter_trade(signal)
                    self._seen_signal_ids.add(sig_id)  # Mark seen AFTER processing
                    if result.get("action") == "entered":
                        self._log_decision("TRADE_ENTERED", f"Entered {direction}", signal,
                                           trade_id=result.get("trade_id"))
                    else:
                        self._log_decision("REJECTED", result.get("error", "unknown"), signal)

                    break  # Process one signal per cycle

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PositionManager] Signal consumer error: {e}")
                await asyncio.sleep(5)

    # ── Fast Path Entry ───────────────────────────────────────────────────

    async def fast_evaluate(self, trigger_context: dict) -> None:
        """
        Called by FlowSubscriber when a high-conviction event cluster fires.

        Searches signal_history for the most recent unprocessed signal that
        matches the trigger direction and hasn't aged out. If found, it runs
        the full risk gate and enters immediately — bypassing the 15s wait.

        Args:
            trigger_context: dict with keys:
                - trigger (str):    "SWEEP_CLUSTER" | "LARGE_CVD_SPIKE" | etc.
                - direction (str):  "CALL" or "PUT"
                - count / delta_1m / cvd_at_flip (optional extras)
        """
        if not self._enabled:
            return

        now_et = datetime.now(ET)
        if not (self.trading_start <= now_et.time() <= self.trading_end):
            return

        if now_et.time() >= self.exit_rules.no_new_entries_after:
            return

        if not self._signal_ref:
            return

        direction_key = trigger_context.get("direction", "")  # "CALL" or "PUT"
        max_age = cfg.FAST_PATH_SIGNAL_MAX_AGE_SECONDS
        min_tier = cfg.FAST_PATH_MIN_TIER
        min_conf = cfg.FAST_PATH_MIN_CONFIDENCE

        candidate = None
        for signal in reversed(list(self._signal_ref)):
            sig_id = signal.get("id")
            if not sig_id or sig_id in self._seen_signal_ids:
                continue

            sig_direction = signal.get("signal", "NO_TRADE")
            if sig_direction == "NO_TRADE":
                continue

            # Direction must align with the fast trigger
            if direction_key not in sig_direction:
                continue

            # Signal must be fresh
            try:
                ts_str = signal.get("timestamp") or signal.get("generated_at", "")
                sig_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                age_s = (datetime.now(timezone.utc) - sig_ts).total_seconds()
                if age_s > max_age:
                    continue
            except Exception:
                continue

            # Must meet fast-path tier/confidence minimums
            tier = signal.get("tier", "DEVELOPING")
            confidence = signal.get("confidence", 0)
            if TIER_ORDER.get(tier, 0) < TIER_ORDER.get(min_tier, 0):
                continue
            if confidence < min_conf:
                continue

            candidate = signal
            break

        if not candidate:
            logger.debug(
                f"[PM fast_evaluate] No matching signal for {trigger_context['trigger']} "
                f"direction={direction_key}"
            )
            return

        sig_id = candidate.get("id")

        # Full risk gate (same as normal consumer)
        open_pos = get_open_trades()
        daily_pnl = self._get_daily_pnl()
        risk_reject = self.risk.check_entry(candidate, open_pos, daily_pnl)
        if risk_reject:
            self._seen_signal_ids.add(sig_id)
            self._log_decision("FAST_REJECTED", risk_reject, candidate,
                               trigger=trigger_context["trigger"])
            mark_signal_rejected(sig_id, risk_reject)
            return

        # Session gate — smart session-aware filtering (same as normal path)
        gate_allowed, gate_reason = session_gate.check(candidate)
        if not gate_allowed:
            self._seen_signal_ids.add(sig_id)
            self._log_decision("FAST_SESSION_GATED", gate_reason, candidate,
                               trigger=trigger_context["trigger"])
            mark_signal_rejected(sig_id, gate_reason)
            return

        # ML Direction Predictor (advisory gate — same as normal path)
        try:
            from .ml_predictor import ml_predictor
            ml_allow, ml_prob, ml_reason = ml_predictor.predict(candidate)
            candidate["ml_win_probability"] = round(ml_prob, 3)
            if not ml_allow:
                self._seen_signal_ids.add(sig_id)
                self._log_decision("FAST_ML_BLOCKED", ml_reason, candidate,
                                   trigger=trigger_context["trigger"])
                mark_signal_rejected(sig_id, ml_reason)
                return
        except Exception as _ml_err:
            logger.debug(f"[PM fast] ML predictor error: {_ml_err}")

        # LLM Validator (advisory, fire-and-forget — same as normal path)
        if cfg.LLM_VALIDATOR_ENABLED and cfg.ANTHROPIC_API_KEY:
            try:
                mkt_ctx = {}
                try:
                    sym = candidate.get("symbol", "SPY")
                    mkt_ctx = await data_router.get_quote(sym)
                except Exception:
                    pass
                asyncio.ensure_future(
                    llm_validator.validate_signal_async(
                        candidate,
                        market_context=mkt_ctx,
                        trade_history=get_trade_history(limit=5),
                        open_positions=open_pos,
                    )
                )
            except Exception as _e:
                logger.debug(f"[PM fast_evaluate] LLM fire error: {_e}")

        logger.info(
            f"[PM fast_evaluate] FAST ENTRY — trigger={trigger_context['trigger']} "
            f"direction={direction_key} signal_id={sig_id}"
        )
        result = await self.enter_trade(candidate)
        self._seen_signal_ids.add(sig_id)  # Mark seen AFTER processing
        if result.get("action") == "entered":
            self._log_decision(
                "FAST_TRADE_ENTERED",
                f"Fast-path entry via {trigger_context['trigger']}",
                candidate,
                trade_id=result.get("trade_id"),
                trigger=trigger_context,
            )
        else:
            self._log_decision(
                "FAST_REJECTED",
                result.get("error", "unknown"),
                candidate,
                trigger=trigger_context["trigger"],
            )

    # ── Exit Monitor Loop ─────────────────────────────────────────────────

    async def _exit_monitor_loop(self):
        """Check open positions for exit triggers every 5 seconds."""
        while self._running:
            try:
                await asyncio.sleep(5)

                open_trades = get_open_trades()
                if not open_trades:
                    continue

                # Update chain prices
                await self._refresh_chain()

                # Get current underlying price
                quote = await data_router.get_quote("SPY")
                underlying_price = quote.get("last", 0) or quote.get("mid", 0)

                # Fetch market context for dynamic exit engine (once per cycle)
                exit_context = await self._fetch_exit_context() if cfg.DYNAMIC_EXIT_ENABLED else {}

                for trade in open_trades:
                    position = self._compute_position(trade, underlying_price)

                    # Update MFE/MAE in DB
                    self._update_mfe_mae(trade, position)

                    # Check exit rules (only auto-exit if enabled)
                    if self._enabled:
                        # ── Dynamic Exit Engine — composite urgency scoring ──
                        if cfg.DYNAMIC_EXIT_ENABLED and exit_context:
                            urgency = dynamic_exit_engine.evaluate(
                                position,
                                flow=exit_context.get("flow"),
                                levels=exit_context.get("levels"),
                                session=exit_context.get("session"),
                                gex=exit_context.get("gex"),
                                breadth=exit_context.get("breadth"),
                                gex_regime=exit_context.get("gex_regime"),
                                vol_regime=exit_context.get("vol_regime"),
                            )

                            # URGENT → force immediate full exit
                            if urgency.force_exit:
                                exit_price = position.get("current_price", trade["entry_price"])
                                reason = f"dynamic_exit_urgent ({urgency.urgency:.2f})"
                                await self.exit_trade(trade, exit_price, reason)
                                self._log_decision("DYNAMIC_EXIT", urgency.detail,
                                                   trade_id=trade["id"])
                                continue

                            # WARNING/CAUTION → tighten trailing stop for this check
                            if urgency.trailing_multiplier < 1.0:
                                position["_trailing_multiplier"] = urgency.trailing_multiplier
                            if urgency.move_to_breakeven:
                                position["_move_to_breakeven"] = True

                        # ── Standard exit rules (with partial exit support) ──
                        decision = self.exit_rules.check_with_partial(position)
                        if decision:
                            exit_price = position.get("current_price", trade["entry_price"])

                            if decision.action == "partial":
                                await self._execute_partial_exit(
                                    trade, exit_price, decision.reason, decision.qty
                                )
                                self._log_decision(
                                    "PARTIAL_EXIT", f"{decision.reason}: {decision.qty} contracts @ ${exit_price:.2f}",
                                    trade_id=trade["id"]
                                )
                            else:
                                # Full exit — close remaining position
                                await self.exit_trade(trade, exit_price, decision.reason)
                                self._log_decision("TRADE_EXITED", decision.reason,
                                                   trade_id=trade["id"])

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PositionManager] Exit monitor error: {e}")
                await asyncio.sleep(5)

    # ── Partial Exit Execution ────────────────────────────────────────────

    async def _execute_partial_exit(
        self, trade: Dict, exit_price: float, reason: str, qty: int
    ):
        """
        Sell a partial quantity of the position.
        - Sends partial sell to Alpaca
        - Records partial exit in DB
        - Does NOT close the trade — remaining quantity stays open
        """
        from .signal_db import record_partial_exit

        trade_id = trade["id"]
        entry_price = float(trade.get("entry_price", 0))
        pnl_partial = (exit_price - entry_price) * 100 * qty  # options multiplier

        # Execute on Alpaca
        if trade.get("mode") == "alpaca_paper":
            success = await self._execute_alpaca_exit(trade, qty=qty)
            if not success:
                logger.error(f"[PositionManager] Partial exit Alpaca failed for {trade_id}")
                return

        # Record in DB
        new_remaining = record_partial_exit(trade_id, qty, exit_price, reason, pnl_partial)

        logger.info(
            f"[PositionManager] PARTIAL EXIT {trade_id} | {reason} | "
            f"{qty} contracts @ ${exit_price:.2f} | P&L=${pnl_partial:.2f} | "
            f"remaining={new_remaining}"
        )

    # ── Chain Refresh ─────────────────────────────────────────────────────

    async def _refresh_chain(self):
        """Refresh options chain data from DataRouter."""
        if (time.time() - self._chain_updated_at) < 15:  # Max every 15s
            return

        try:
            exp_today = datetime.now().strftime("%Y-%m-%d")
            chain = await data_router.get_options_chain("SPY", exp_today)

            if chain and not chain.get("error"):
                # Index by (strike, right) for fast lookup
                self._chain_cache = {}
                for c in chain.get("calls", []):
                    key = (c["strike"], "C")
                    self._chain_cache[key] = c
                for p in chain.get("puts", []):
                    key = (p["strike"], "P")
                    self._chain_cache[key] = p
                self._chain_updated_at = time.time()
        except Exception as e:
            logger.debug(f"[PositionManager] Chain refresh error: {e}")

    # ── Dynamic Exit Context ─────────────────────────────────────────────

    async def _fetch_exit_context(self) -> Dict:
        """
        Fetch market context for the dynamic exit engine.
        Returns dict with flow, levels, session, gex — all as plain dicts.
        Cached 10s to avoid hammering APIs.
        """
        now = time.time()
        if hasattr(self, "_exit_ctx_cache") and (now - self._exit_ctx_ts) < 10:
            return self._exit_ctx_cache

        ctx = {}
        try:
            # Get bars for market levels
            bars_data = await data_router.get_bars("SPY", "1Min", 60)
            bars_1m = bars_data.get("bars", []) if bars_data else []

            bars_daily_data = await data_router.get_bars("SPY", "1Day", 5)
            bars_daily = bars_daily_data.get("bars", []) if bars_daily_data else []

            quote = await data_router.get_quote("SPY")

            # Compute market levels
            if bars_1m:
                from .market_levels import compute_market_levels
                levels = compute_market_levels(bars_1m, bars_daily, quote)
                ctx["levels"] = levels.to_dict()

            # Get session context
            from .confluence import get_session_context
            session = get_session_context()
            ctx["session"] = session.to_dict() if hasattr(session, "to_dict") else {
                "phase": session.phase, "minutes_to_close": session.minutes_to_close,
                "session_quality": session.session_quality,
            }

            # Get flow state from Rust engine (via HTTP)
            try:
                flow_url = f"{cfg.FLOW_ENGINE_HTTP_URL}/stats"
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(flow_url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                        if resp.status == 200:
                            flow_data = await resp.json()
                            ctx["flow"] = {
                                "cvd_trend": flow_data.get("cvd_trend", "neutral"),
                                "cvd_acceleration": flow_data.get("cvd_acceleration", 0),
                                "imbalance": flow_data.get("imbalance", 0.5),
                                "volume_exhausted": flow_data.get("volume_exhausted", False),
                                "exhaustion_strength": flow_data.get("exhaustion_strength", 0),
                                "large_trade_count": flow_data.get("large_trade_count", 0),
                                "large_trade_bias": flow_data.get("large_trade_bias", "neutral"),
                                "absorption_detected": flow_data.get("absorption_detected", False),
                                "absorption_bias": flow_data.get("absorption_bias", "neutral"),
                                "divergence": flow_data.get("divergence", "none"),
                            }
            except Exception:
                pass  # Flow data is best-effort

            # Get market breadth for momentum assessment
            try:
                from .market_internals import analyze_breadth
                breadth = await analyze_breadth()
                if breadth and breadth.symbols_fetched >= 3:
                    ctx["breadth"] = breadth.to_dict()
            except Exception:
                pass  # Breadth is best-effort

            # Get IV vs Realized Vol analysis
            try:
                from .vol_analyzer import analyze_vol
                from .options_analytics import analyze_options
                chain_for_vol = await data_router.get_options_chain("SPY")
                if chain_for_vol and bars_1m:
                    calls_v = chain_for_vol.get("calls", [])
                    puts_v = chain_for_vol.get("puts", [])
                    spot_v = chain_for_vol.get("underlying_price", 0)
                    if calls_v or puts_v:
                        analytics = analyze_options(calls_v, puts_v, spot_v, "SPY")
                        if analytics and analytics.atm_iv > 0:
                            rv = ctx.get("levels", {}).get("realized_vol", 0)
                            if rv <= 0 and levels:
                                rv = levels.realized_vol if hasattr(levels, "realized_vol") else 0
                            vol = analyze_vol(
                                atm_iv=analytics.atm_iv,
                                realized_vol=rv,
                                iv_rank=analytics.iv_rank,
                                daily_bars=bars_daily,
                            )
                            if vol:
                                ctx["vol_regime"] = vol.to_dict()
            except Exception:
                pass  # Vol analysis is best-effort

            # Get GEX data
            try:
                from .gex_engine import calculate_gex
                chain = await data_router.get_options_chain("SPY")
                if chain and chain.get("calls"):
                    gex = calculate_gex(
                        chain.get("calls", []),
                        chain.get("puts", []),
                        chain.get("underlying_price", 0),
                    )
                    if gex:
                        ctx["gex"] = gex.to_dict() if hasattr(gex, "to_dict") else {
                            "call_wall": getattr(gex, "call_wall", 0),
                            "put_wall": getattr(gex, "put_wall", 0),
                            "regime": getattr(gex, "regime", "neutral"),
                        }
                        # v9: Build GEX regime profile for dynamic exit
                        try:
                            from .gex_regime import get_regime_profile
                            profile = get_regime_profile(
                                gex.regime, gex.regime_strength,
                                gex.spot, gex.call_wall, gex.put_wall,
                                gex.gex_flip_level,
                            )
                            ctx["gex_regime"] = profile.to_dict()
                        except Exception:
                            pass
            except Exception:
                pass  # GEX is best-effort

        except Exception as e:
            logger.debug(f"[PositionManager] Exit context fetch error: {e}")

        self._exit_ctx_cache = ctx
        self._exit_ctx_ts = now
        return ctx

    # ── P&L Computation (SINGLE implementation) ───────────────────────────

    def _compute_position(self, trade: Dict, underlying_price: float) -> Dict:
        """
        Compute live position state from a trade record.
        This is THE ONLY P&L calculation in the system.
        """
        entry_price = float(trade.get("entry_price", 0))
        strike = float(trade.get("strike", 0))
        option_type = trade.get("option_type", "call").upper()
        right = "C" if "call" in option_type.lower() or option_type == "C" else "P"
        quantity = int(trade.get("quantity", 1))
        expiry = trade.get("expiry", "")

        # Entry time and hold duration
        entry_time = trade.get("entry_time", "")
        hold_minutes = 0
        if entry_time:
            try:
                et = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
                hold_minutes = (datetime.now(timezone.utc) - et).total_seconds() / 60
            except Exception:
                pass

        # Look up current option price from chain
        current_price = entry_price  # Fallback
        price_source = "entry_fallback"
        live_greeks = {}

        # Fuzzy strike match — float precision (e.g. 450.5 vs 450.50) can cause exact-key miss
        chain_entry = self._chain_cache.get((strike, right))
        if chain_entry is None:
            for (c_strike, c_right), c_entry in self._chain_cache.items():
                if c_right == right and abs(c_strike - strike) < 0.02:
                    chain_entry = c_entry
                    break
        if chain_entry:
            mid = chain_entry.get("mid", 0)
            if mid > 0:
                current_price = mid
                price_source = "chain_mid"
            elif chain_entry.get("bid", 0) > 0:
                current_price = (chain_entry["bid"] + chain_entry.get("ask", chain_entry["bid"])) / 2
                price_source = "chain_bid_ask"

            live_greeks = {k: v for k, v in {
                "delta": chain_entry.get("delta"),
                "gamma": chain_entry.get("gamma"),
                "theta": chain_entry.get("theta"),
                "vega": chain_entry.get("vega"),
                "iv": chain_entry.get("iv"),
            }.items() if v is not None}
        else:
            # Black-Scholes fallback
            if underlying_price > 0 and strike > 0 and expiry:
                greeks = data_router._compute_greeks(
                    underlying_price, strike, right, expiry, entry_price
                )
                if greeks:
                    live_greeks = greeks
                    # Rough reprice
                    delta = greeks.get("delta", 0.5)
                    price_move = underlying_price - (entry_price / abs(delta) if delta != 0 else underlying_price)
                    current_price = max(0.01, entry_price + delta * price_move * 0.3)
                    price_source = "black_scholes"

        # P&L
        pnl_per_contract = (current_price - entry_price) * 100  # Options: 100 shares per contract
        unrealized_pnl = pnl_per_contract * quantity
        unrealized_pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0

        # MFE/MAE tracking
        max_favorable = float(trade.get("max_favorable", 0))
        max_adverse = float(trade.get("max_adverse", 0))
        max_pnl_pct = max_favorable / (entry_price * 100 * quantity) if entry_price > 0 else 0

        # Target and stop from signal
        greeks_at_entry = {}
        try:
            _g_raw = trade.get("greeks_at_entry", "{}")
            greeks_at_entry = json.loads(_g_raw) if isinstance(_g_raw, str) else (_g_raw or {})
            if not isinstance(greeks_at_entry, dict):
                greeks_at_entry = {}
        except (json.JSONDecodeError, TypeError):
            pass

        # Greeks P&L decomposition
        greeks_pnl = self._decompose_greeks_pnl(
            trade, underlying_price, current_price, hold_minutes, live_greeks
        )

        return {
            "trade_id": trade["id"],
            "signal_id": trade.get("signal_id"),
            "mode": trade.get("mode", self.mode),
            "symbol": trade.get("symbol", "SPY"),
            "strike": strike,
            "expiry": expiry,
            "option_type": option_type,
            "right": right,
            "quantity": quantity,
            "entry_price": entry_price,
            "current_price": current_price,
            "underlying_price": underlying_price,
            "tier": trade.get("tier", ""),

            # P&L
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 4),
            "pnl_per_contract": round(pnl_per_contract, 2),

            # Excursions
            "max_favorable": max_favorable,
            "max_adverse": max_adverse,
            "max_pnl_pct": max_pnl_pct,

            # Time
            "entry_time": entry_time,
            "hold_minutes": round(hold_minutes, 1),

            # Greeks
            "live_greeks": live_greeks,
            "greeks_pnl": greeks_pnl,
            "greeks_at_entry": greeks_at_entry,

            # Partial exit tracking
            "remaining_quantity": int(trade.get("remaining_quantity") or quantity),
            "partial_exits_done": json.loads(trade.get("partial_exits", "[]") or "[]"),

            # Meta
            "price_source": price_source,
            "bid": chain_entry.get("bid") if chain_entry else None,
            "ask": chain_entry.get("ask") if chain_entry else None,
        }

    def _decompose_greeks_pnl(
        self,
        trade: Dict,
        current_underlying: float,
        current_option_price: float,
        hold_minutes: float,
        live_greeks: Dict,
    ) -> Dict:
        """Decompose P&L into delta, gamma, theta, vega components."""
        try:
            _g_raw = trade.get("greeks_at_entry", "{}")
            greeks_at_entry = json.loads(_g_raw) if isinstance(_g_raw, str) else (_g_raw or {})
            if not isinstance(greeks_at_entry, dict):
                greeks_at_entry = {}
        except (json.JSONDecodeError, TypeError):
            return {}

        entry_delta = greeks_at_entry.get("delta", 0)
        entry_iv = greeks_at_entry.get("iv", 0)
        entry_price = float(trade.get("entry_price", 0))

        if not entry_delta or entry_price <= 0:
            return {}

        # Estimate underlying at entry (rough)
        strike = float(trade.get("strike", 0))
        if strike <= 0:
            return {}

        # Use entry delta to estimate underlying move
        underlying_at_entry = strike + entry_price / abs(entry_delta) if entry_delta != 0 else strike
        ds = current_underlying - underlying_at_entry

        delta_pnl = entry_delta * ds * 100
        gamma_pnl = 0.5 * greeks_at_entry.get("gamma", 0) * ds * ds * 100
        theta_pnl = greeks_at_entry.get("theta", 0) * (hold_minutes / (24 * 60)) * 100
        vega_pnl = 0
        if live_greeks.get("iv") and entry_iv:
            iv_change = live_greeks["iv"] - entry_iv
            vega_pnl = greeks_at_entry.get("vega", 0) * iv_change * 100

        total = delta_pnl + gamma_pnl + theta_pnl + vega_pnl

        return {
            "delta_pnl": round(delta_pnl, 2),
            "gamma_pnl": round(gamma_pnl, 2),
            "theta_pnl": round(theta_pnl, 2),
            "vega_pnl": round(vega_pnl, 2),
            "total_greeks_pnl": round(total, 2),
            "theta_pnl_pct": round(theta_pnl / (entry_price * 100), 4) if entry_price > 0 else 0,
        }

    def _update_mfe_mae(self, trade: Dict, position: Dict):
        """Update max favorable / adverse excursion in DB."""
        pnl = position["unrealized_pnl"]
        current_mfe = float(trade.get("max_favorable", 0))
        current_mae = float(trade.get("max_adverse", 0))

        new_mfe = max(current_mfe, pnl) if pnl > 0 else current_mfe
        new_mae = min(current_mae, pnl) if pnl < 0 else current_mae

        if new_mfe != current_mfe or new_mae != current_mae:
            try:
                from .signal_db import _get_conn
                conn = _get_conn()
                conn.execute(
                    "UPDATE trades SET max_favorable=?, max_adverse=? WHERE id=?",
                    (new_mfe, new_mae, trade["id"])
                )
                conn.commit()
                conn.close()
            except Exception as e:
                logger.debug(f"[PositionManager] MFE/MAE update error: {e}")

    # ── Entry Execution ───────────────────────────────────────────────────

    async def enter_trade(self, signal: Dict) -> Dict:
        """
        Execute a trade entry. Single entry point for all trades.

        Returns: {action: "entered"|"rejected"|"error", trade_id, error}
        """
        direction = signal.get("signal", "NO_TRADE")
        if direction == "NO_TRADE":
            return {"action": "no_trade", "error": "NO_TRADE signal"}

        # Store the signal
        sig_id = signal.get("id") or str(uuid.uuid4())[:12]
        try:
            store_signal(signal)
        except Exception:
            pass

        # Risk check
        open_pos = get_open_trades()
        daily_pnl = self._get_daily_pnl()
        risk_reject = self.risk.check_entry(signal, open_pos, daily_pnl)
        if risk_reject:
            mark_signal_rejected(sig_id, risk_reject)
            return {"action": "rejected", "error": risk_reject}

        # Validate signal has required fields
        entry_price = signal.get("entry_price", 0)
        if not entry_price or entry_price <= 0:
            mark_signal_rejected(sig_id, "no_entry_price")
            return {"action": "rejected", "error": "Missing entry price"}

        # Build trade record
        option_type = "call" if "CALL" in direction else "put"
        trade_id = str(uuid.uuid4())[:12]

        greeks_at_entry = {
            "delta": signal.get("option_delta"),
            "iv": signal.get("option_iv"),
            "gamma": signal.get("option_gamma"),
            "theta": signal.get("option_theta"),
            "vega": signal.get("option_vega"),
        }

        trade = {
            "id": trade_id,
            "signal_id": sig_id,
            "mode": self.mode,
            "entry_time": datetime.now(timezone.utc).isoformat(),
            "entry_price": entry_price,
            "quantity": signal.get("max_contracts", 1),
            "strike": signal.get("strike", 0),
            "expiry": signal.get("expiry", ""),
            "option_type": option_type,
            "symbol": signal.get("symbol", "SPY"),
            "tier": signal.get("tier", "VALID"),
            "greeks_at_entry": json.dumps(greeks_at_entry),
        }

        # Execute based on mode
        if self.mode == "alpaca_paper":
            success = await self._execute_alpaca_entry(signal, trade)
            if not success:
                mark_signal_rejected(sig_id, "alpaca_execution_failed")
                return {"action": "error", "error": "Alpaca execution failed"}

        # Store in DB
        try:
            store_trade(trade)
            mark_signal_traded(sig_id)
            self.risk.record_trade()
        except Exception as e:
            logger.error(f"[PositionManager] DB store error: {e}")
            return {"action": "error", "error": str(e)}

        logger.info(
            f"[PositionManager] ENTERED {direction} | strike={trade['strike']} "
            f"| entry=${entry_price:.2f} | qty={trade['quantity']} | mode={self.mode}"
        )

        return {"action": "entered", "trade_id": trade_id, "signal_id": sig_id}

    async def _execute_alpaca_entry(self, signal: Dict, trade: Dict) -> bool:
        """Place a limit order on Alpaca paper account."""
        try:
            occ = self._build_occ_symbol(trade)
            entry_price = trade["entry_price"]

            payload = {
                "symbol": occ,
                "qty": str(trade["quantity"]),
                "side": "buy",
                "type": "limit",
                "time_in_force": "day",
                "limit_price": str(round(entry_price * 1.02, 2)),  # 2% above mid
                "client_order_id": f"ai_signal_{trade['id']}",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{ALPACA_TRADING_URL}/orders",
                    headers=ALPACA_HEADERS,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        # Store Alpaca order ID
                        _g = trade.get("greeks_at_entry", "{}")
                        greeks = json.loads(_g) if isinstance(_g, str) else (_g or {})
                        if not isinstance(greeks, dict):
                            greeks = {}
                        greeks["alpaca_order_id"] = data.get("id")
                        trade["greeks_at_entry"] = json.dumps(greeks)
                        logger.info(f"[PositionManager] Alpaca order placed: {data.get('id')}")
                        return True
                    else:
                        body = await resp.text()
                        logger.error(f"[PositionManager] Alpaca order failed {resp.status}: {body}")
                        return False
        except Exception as e:
            logger.error(f"[PositionManager] Alpaca entry error: {e}")
            return False

    # ── Exit Execution ────────────────────────────────────────────────────

    async def exit_trade(
        self,
        trade: Dict,
        exit_price: float,
        exit_reason: str = "manual",
        greeks_at_exit: Dict = None,
    ) -> bool:
        """
        Execute a trade exit. Single exit point for all trades.
        Handles remaining quantity after partial exits.
        """
        trade_id = trade["id"]
        entry_price = float(trade.get("entry_price", 0))
        quantity = int(trade.get("quantity", 1))
        remaining = int(trade.get("remaining_quantity") or quantity)

        # Calculate P&L for remaining contracts
        pnl_per_contract = (exit_price - entry_price) * 100
        remaining_pnl = pnl_per_contract * remaining

        # Add P&L from any partial exits already taken
        partial_exits = json.loads(trade.get("partial_exits", "[]") or "[]")
        partial_pnl = sum(pe.get("pnl", 0) for pe in partial_exits)
        total_pnl = remaining_pnl + partial_pnl

        # Blended exit price for reporting (weighted average)
        total_exit_qty = remaining
        weighted_exit = exit_price * remaining
        for pe in partial_exits:
            pe_qty = pe.get("qty", 0)
            weighted_exit += pe.get("price", exit_price) * pe_qty
            total_exit_qty += pe_qty
        blended_exit = weighted_exit / total_exit_qty if total_exit_qty > 0 else exit_price

        pnl_pct = (blended_exit - entry_price) / entry_price if entry_price > 0 else 0

        # Execute Alpaca close if needed (sells remaining)
        if trade.get("mode") == "alpaca_paper":
            await self._execute_alpaca_exit(trade)

        # Close in DB
        exit_data = {
            "exit_time": datetime.now(timezone.utc).isoformat(),
            "exit_price": exit_price,
            "pnl": round(total_pnl, 2),
            "pnl_pct": round(pnl_pct, 4),
            "exit_reason": exit_reason,
            "greeks_at_exit": json.dumps(greeks_at_exit or {}),
        }

        try:
            close_trade(trade_id, exit_data)
        except Exception as e:
            logger.error(f"[PositionManager] DB close error: {e}")
            return False

        logger.info(
            f"[PositionManager] EXITED {trade_id} | reason={exit_reason} "
            f"| P&L=${total_pnl:.2f} ({pnl_pct:+.1%}) | hold={trade.get('hold_minutes', '?')}min"
        )

        # Grade the trade
        try:
            from .trade_grader import grade_and_store
            grade_and_store(trade_id)
        except Exception:
            pass

        # Notify weight learner
        if self.on_trade_closed:
            try:
                self.on_trade_closed(trade_id)
            except Exception:
                pass

        return True

    async def _execute_alpaca_exit(self, trade: Dict, qty: int = None) -> bool:
        """Close position on Alpaca. If qty is None, sells all remaining."""
        try:
            occ = self._build_occ_symbol(trade)
            sell_qty = qty or int(trade.get("remaining_quantity") or trade.get("quantity", 1))
            payload = {
                "symbol": occ,
                "qty": str(sell_qty),
                "side": "sell",
                "type": "market",
                "time_in_force": "day",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{ALPACA_TRADING_URL}/orders",
                    headers=ALPACA_HEADERS,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 201):
                        logger.info(f"[PositionManager] Alpaca exit order placed for {trade['id']}")
                        return True
                    else:
                        body = await resp.text()
                        logger.error(f"[PositionManager] Alpaca exit failed {resp.status}: {body}")
                        return False
        except Exception as e:
            logger.error(f"[PositionManager] Alpaca exit error: {e}")
            return False

    def _build_occ_symbol(self, trade: Dict) -> str:
        """Build OCC options symbol from trade record."""
        root = trade.get("symbol", "SPY")
        expiry = trade.get("expiry", "")
        option_type = trade.get("option_type", "call")
        strike = float(trade.get("strike", 0))

        right = "C" if "call" in option_type.lower() else "P"

        try:
            exp_dt = datetime.strptime(expiry, "%Y-%m-%d")
            exp_str = exp_dt.strftime("%y%m%d")
        except Exception:
            exp_str = datetime.now().strftime("%y%m%d")

        strike_int = int(strike * 1000)
        return f"{root:<6}{exp_str}{right}{strike_int:08d}"

    # ── Public Query Methods ──────────────────────────────────────────────

    async def get_positions(self) -> List[Dict]:
        """Get all open positions with live P&L."""
        open_trades = get_open_trades()
        if not open_trades:
            return []

        await self._refresh_chain()
        quote = await data_router.get_quote("SPY")
        underlying_price = quote.get("last", 0) or quote.get("mid", 0)

        positions = []
        for trade in open_trades:
            pos = self._compute_position(trade, underlying_price)
            positions.append(pos)

        return positions

    async def get_exit_triggers(self) -> List[Dict]:
        """Check which positions should be exited."""
        positions = await self.get_positions()
        triggers = []
        for pos in positions:
            reason = self.exit_rules.check(pos)
            if reason:
                triggers.append({
                    "trade_id": pos["trade_id"],
                    "exit_reason": reason,
                    "exit_price": pos["current_price"],
                    "position": pos,
                })
        return triggers

    def get_portfolio_summary(self, positions: List[Dict]) -> Dict:
        """Aggregate portfolio metrics."""
        if not positions:
            return {
                "open_count": 0,
                "total_unrealized_pnl": 0,
                "total_cost_basis": 0,
                "calls_count": 0,
                "puts_count": 0,
                "avg_hold_minutes": 0,
                "portfolio_delta": 0,
                "portfolio_theta": 0,
                "worst_position": None,
                "best_position": None,
            }

        total_pnl = sum(p["unrealized_pnl"] for p in positions)
        total_cost = sum(p["entry_price"] * p["quantity"] * 100 for p in positions)
        calls = sum(1 for p in positions if p["right"] == "C")
        puts = sum(1 for p in positions if p["right"] == "P")
        avg_hold = sum(p["hold_minutes"] for p in positions) / len(positions)

        # Portfolio Greeks
        port_delta = sum(
            (p["live_greeks"].get("delta") or 0) * p["quantity"] * 100
            for p in positions
        )
        port_theta = sum(
            (p["live_greeks"].get("theta") or 0) * p["quantity"] * 100
            for p in positions
        )

        sorted_by_pnl = sorted(positions, key=lambda p: p["unrealized_pnl"])

        return {
            "open_count": len(positions),
            "total_unrealized_pnl": round(total_pnl, 2),
            "total_cost_basis": round(total_cost, 2),
            "calls_count": calls,
            "puts_count": puts,
            "avg_hold_minutes": round(avg_hold, 1),
            "portfolio_delta": round(port_delta, 2),
            "portfolio_theta": round(port_theta, 2),
            "worst_position": {
                "trade_id": sorted_by_pnl[0]["trade_id"],
                "pnl": sorted_by_pnl[0]["unrealized_pnl"],
            },
            "best_position": {
                "trade_id": sorted_by_pnl[-1]["trade_id"],
                "pnl": sorted_by_pnl[-1]["unrealized_pnl"],
            },
        }

    def _get_daily_pnl(self) -> float:
        """Get today's realized + unrealized P&L."""
        try:
            todays = get_todays_trades()
            realized = sum(float(t.get("pnl", 0) or 0) for t in todays if t.get("exit_time"))
            return realized
        except Exception:
            return 0.0

    # ── Config ────────────────────────────────────────────────────────────

    def get_config(self) -> Dict:
        return {
            "enabled": self._enabled,
            "mode": self.mode,
            "min_tier": self.min_tier,
            "min_confidence": self.min_confidence,
            "trading_start": self.trading_start.isoformat(),
            "trading_end": self.trading_end.isoformat(),
            "exit_rules": self.exit_rules.to_dict(),
            "risk": self.risk.to_dict(),
        }

    def update_config(self, data: Dict):
        # mode is locked to "simulation" — ignore any mode changes
        if "min_tier" in data:
            self.min_tier = data["min_tier"]
        if "min_confidence" in data:
            self.min_confidence = float(data["min_confidence"])
        if "exit_rules" in data:
            self.exit_rules.update(data["exit_rules"])
        if "risk" in data:
            for k, v in data["risk"].items():
                if hasattr(self.risk, k):
                    setattr(self.risk, k, v)
        logger.info(f"[PositionManager] Config updated: {list(data.keys())}")
