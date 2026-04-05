"""
signal_outcome_tracker.py — Records what the market did after every signal.

The system generates 20–40 signals per day but trades only 3–5. This module
tracks the other 35+ "skipped" signals so the WeightLearner can learn from
all the evidence — not just executed trades.

How it works:
  1. Every 5 minutes (market hours only), query signal_outcomes for rows
     that still need a 15-min or 30-min price check.
  2. Fetch current SPY price from the data router.
  3. Compute whether the signal's direction was correct:
       - CALL signal + SPY moved UP   →  direction_correct = 1
       - PUT  signal + SPY moved DOWN →  direction_correct = 1
       - Move < MIN_MOVE_PCT          →  direction_correct = None (ambiguous)
  4. At the 30-min mark, feed the outcome into the WeightLearner so it
     adjusts factor weights using this additional evidence.
  5. Back-fill was_correct on any LLM verdicts for that signal so we can
     track Claude's advisory accuracy over time.

The outcome tracker also creates outcome stubs for new actionable signals —
this is triggered from signal_api.py after each analysis cycle.
"""

import asyncio
import logging
from datetime import datetime, timezone, time as dt_time
from typing import Optional, TYPE_CHECKING

from . import data_router
from .signal_db import (
    get_pending_outcomes,
    update_outcome_checkpoint,
    mark_outcome_weight_adjusted,
    backfill_verdict_outcome,
)

if TYPE_CHECKING:
    from .weight_learner import WeightLearner

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
CHECK_INTERVAL_SECONDS = 300            # Run every 5 minutes
MIN_MOVE_PCT = 0.05                     # Moves < 0.05% are noise — don't call correct/wrong
CHECKPOINT_15_MIN = 15
CHECKPOINT_30_MIN = 30

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except ImportError:
    import pytz
    _ET = pytz.timezone("America/New_York")


def _is_market_hours() -> bool:
    now_et = datetime.now(_ET)
    if now_et.weekday() >= 5:
        return False
    t = now_et.time()
    return dt_time(9, 30) <= t <= dt_time(16, 30)  # slight buffer after close


def _direction_correct(signal_direction: str, spy_at_signal: float, spy_now: float) -> Optional[int]:
    """
    Determine if the signal's direction call was correct.

    Returns:
        1     — direction was correct (move exceeded MIN_MOVE_PCT threshold)
        0     — direction was wrong
        None  — move was too small to call (ambiguous)
    """
    if spy_at_signal <= 0 or spy_now <= 0:
        return None

    move_pct = (spy_now - spy_at_signal) / spy_at_signal * 100

    if abs(move_pct) < MIN_MOVE_PCT:
        return None  # Noise — can't tell

    direction_upper = signal_direction.upper()
    if "CALL" in direction_upper or "BUY" in direction_upper:
        return 1 if move_pct > 0 else 0
    elif "PUT" in direction_upper or "SELL" in direction_upper:
        return 1 if move_pct < 0 else 0

    return None  # Unknown direction format


class SignalOutcomeTracker:
    """
    Background task that fills in signal outcome data after each signal ages.
    """

    def __init__(self):
        self._weight_learner: Optional["WeightLearner"] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._checked_count = 0
        self._correct_count = 0
        self._wrong_count = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self, weight_learner: "WeightLearner") -> None:
        """Start the outcome tracker. Called from app.py startup."""
        self._weight_learner = weight_learner
        self._running = True
        self._task = asyncio.ensure_future(self._run_loop())
        logger.info("[OutcomeTracker] Started — checking non-traded signals every 5min")

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[OutcomeTracker] Stopped")

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def _run_loop(self):
        """Run outcome checks every CHECK_INTERVAL_SECONDS."""
        # Slight startup delay so the server is fully up before first check
        await asyncio.sleep(30)

        while self._running:
            try:
                if _is_market_hours():
                    await self._process_pending()
            except Exception as e:
                logger.error(f"[OutcomeTracker] Loop error: {e}")

            try:
                await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break

    async def _process_pending(self):
        """Check all outcome rows that still need a 15-min or 30-min price."""
        pending = get_pending_outcomes(max_age_hours=2)
        if not pending:
            return

        # Fetch current SPY price once for the whole batch
        try:
            quote = await data_router.get_quote("SPY")
            spy_now = quote.get("last") or quote.get("price") or quote.get("mid") or 0
        except Exception as e:
            logger.debug(f"[OutcomeTracker] Failed to fetch SPY quote: {e}")
            return

        if not spy_now or spy_now <= 0:
            logger.debug("[OutcomeTracker] No valid SPY price — skipping cycle")
            return

        now_utc = datetime.now(timezone.utc)
        processed = 0

        for row in pending:
            try:
                created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                age_minutes = (now_utc - created_at).total_seconds() / 60
                spy_at_signal = row["spy_price_at_signal"]
                signal_id = row["signal_id"]
                direction = row["direction"]
                factors_json = row.get("factors")

                # ── 15-minute checkpoint ───────────────────────────────────
                if age_minutes >= CHECKPOINT_15_MIN and not row["checked_15min"]:
                    move_pct = (
                        (spy_now - spy_at_signal) / spy_at_signal * 100
                        if spy_at_signal > 0 else 0
                    )
                    correct_15 = _direction_correct(direction, spy_at_signal, spy_now)
                    update_outcome_checkpoint(
                        signal_id, 15, spy_now, correct_15, move_pct
                    )
                    processed += 1
                    self._checked_count += 1
                    if correct_15 == 1:
                        self._correct_count += 1
                    elif correct_15 == 0:
                        self._wrong_count += 1

                # ── 30-minute checkpoint ───────────────────────────────────
                if age_minutes >= CHECKPOINT_30_MIN and not row["checked_30min"]:
                    move_pct = (
                        (spy_now - spy_at_signal) / spy_at_signal * 100
                        if spy_at_signal > 0 else 0
                    )
                    correct_30 = _direction_correct(direction, spy_at_signal, spy_now)
                    update_outcome_checkpoint(
                        signal_id, 30, spy_now, correct_30, move_pct
                    )

                    # ── Feed into WeightLearner ────────────────────────────
                    if (
                        correct_30 is not None
                        and not row.get("weight_adjusted")
                        and self._weight_learner
                        and factors_json
                    ):
                        await self._feed_to_weight_learner(
                            signal_id, direction, correct_30, factors_json, move_pct
                        )
                        mark_outcome_weight_adjusted(signal_id)

                    # ── Back-fill LLM verdict outcome ──────────────────────
                    if correct_30 is not None:
                        try:
                            backfill_verdict_outcome(signal_id, correct_30)
                        except Exception as e:
                            logger.debug(f"[OutcomeTracker] Verdict backfill error: {e}")

                    processed += 1

            except Exception as e:
                logger.debug(f"[OutcomeTracker] Error processing {row.get('signal_id')}: {e}")

        if processed:
            logger.info(
                f"[OutcomeTracker] Processed {processed} checkpoints | "
                f"Total checked={self._checked_count} "
                f"correct={self._correct_count} wrong={self._wrong_count}"
            )

    async def _feed_to_weight_learner(
        self,
        signal_id: str,
        direction: str,
        correct: int,
        factors_json: str,
        move_pct: float,
    ) -> None:
        """
        Pass a signal outcome into the WeightLearner.

        Signal outcomes are less reliable than trade outcomes (no real fill,
        theoretical P&L only), so we use a reduced magnitude — 50% of the
        normal trade-based learning rate.
        """
        try:
            await self._weight_learner.on_signal_outcome(
                signal_id=signal_id,
                direction=direction,
                direction_correct=correct,
                factors_json=factors_json,
                move_pct=move_pct,
            )
        except Exception as e:
            logger.warning(f"[OutcomeTracker] WeightLearner feed error: {e}")

    # ── Stats ─────────────────────────────────────────────────────────────────

    @property
    def stats(self) -> dict:
        total = self._correct_count + self._wrong_count
        return {
            "running": self._running and self._task is not None and not self._task.done(),
            "total_checked": self._checked_count,
            "correct": self._correct_count,
            "wrong": self._wrong_count,
            "accuracy_pct": round(self._correct_count / total * 100, 1) if total else None,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

outcome_tracker = SignalOutcomeTracker()
