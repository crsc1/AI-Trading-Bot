"""
flow_subscriber.py — Real-time subscriber to the Rust flow engine WebSocket.

Maintains rolling event windows and detects high-conviction fast triggers:
  - SWEEP_CLUSTER:      N+ sweeps same direction within 60s
  - LARGE_CVD_SPIKE:    1-minute CVD delta exceeds threshold
  - ABSORPTION_CLUSTER: N+ held absorptions same direction within 60s
  - DELTA_FLIP:         CVD side flips (bullish→bearish or vice versa)

When triggered, calls pm.fast_evaluate(trigger_context) which enters a
trade immediately without waiting for the next 15s analysis cycle.

Uses aiohttp (already a project dependency — no new packages needed).
"""

import asyncio
import json
import logging
import time
from collections import deque
from typing import Optional, TYPE_CHECKING

import aiohttp

from .config import cfg

if TYPE_CHECKING:
    from .position_manager import PositionManager

logger = logging.getLogger(__name__)


class FlowSubscriber:
    """
    Connects to ws://localhost:8081/ws (Rust flow engine) and fires
    fast_evaluate() on PositionManager when a high-conviction event
    cluster is detected.
    """

    def __init__(self):
        self._pm: Optional["PositionManager"] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # Rolling event windows — each entry: (monotonic_ts, side_str)
        self._sweeps: deque = deque()
        self._absorptions: deque = deque()

        # Trigger accounting
        self._last_trigger_ts: float = 0.0
        self._trigger_count = 0
        self._connected = False

    # ── Window helpers ────────────────────────────────────────────────────

    def _prune(self, q: deque, window: int) -> None:
        """Drop entries older than `window` seconds."""
        cutoff = time.monotonic() - window
        while q and q[0][0] < cutoff:
            q.popleft()

    # ── Trigger detection ─────────────────────────────────────────────────

    def _check_sweep_cluster(self) -> Optional[dict]:
        window = cfg.FAST_PATH_WINDOW_SECONDS
        self._prune(self._sweeps, window)
        n = cfg.FAST_PATH_SWEEP_CLUSTER_MIN
        if len(self._sweeps) < n:
            return None
        buy = sum(1 for _, s in self._sweeps if s == "buy")
        sell = len(self._sweeps) - buy
        if buy >= n:
            return {"trigger": "SWEEP_CLUSTER", "direction": "CALL", "count": buy}
        if sell >= n:
            return {"trigger": "SWEEP_CLUSTER", "direction": "PUT", "count": sell}
        return None

    def _check_absorption_cluster(self) -> Optional[dict]:
        window = cfg.FAST_PATH_WINDOW_SECONDS
        self._prune(self._absorptions, window)
        n = cfg.FAST_PATH_ABSORPTION_CLUSTER_MIN
        if len(self._absorptions) < n:
            return None
        buy = sum(1 for _, s in self._absorptions if s == "buy")
        sell = len(self._absorptions) - buy
        if buy >= n:
            return {"trigger": "ABSORPTION_CLUSTER", "direction": "CALL", "count": buy}
        if sell >= n:
            return {"trigger": "ABSORPTION_CLUSTER", "direction": "PUT", "count": sell}
        return None

    # ── Event router ──────────────────────────────────────────────────────

    def _handle_event(self, event: dict) -> Optional[dict]:
        """
        Route one deserialized FlowEvent.
        Returns a trigger context dict if a fast condition fires, else None.
        """
        etype = event.get("type")
        now = time.monotonic()

        if etype == "sweep":
            side = event.get("side", "")
            self._sweeps.append((now, side))
            return self._check_sweep_cluster()

        if etype == "absorption":
            side = event.get("side", "")
            held = event.get("held", False)
            if held:  # Only count absorptions where the level actually held
                self._absorptions.append((now, side))
                return self._check_absorption_cluster()

        if etype == "cvd":
            delta_1m = event.get("delta_1m", 0)
            threshold = cfg.FAST_PATH_CVD_SPIKE_THRESHOLD
            if abs(delta_1m) >= threshold:
                direction = "CALL" if delta_1m > 0 else "PUT"
                return {
                    "trigger": "LARGE_CVD_SPIKE",
                    "direction": direction,
                    "delta_1m": delta_1m,
                }

        if etype == "delta_flip":
            to_side = event.get("to", "")
            direction = "CALL" if to_side == "buy" else "PUT"
            return {
                "trigger": "DELTA_FLIP",
                "direction": direction,
                "cvd_at_flip": event.get("cvd_at_flip", 0),
            }

        return None

    # ── Main loop ─────────────────────────────────────────────────────────

    async def _connect_and_listen(self):
        """WebSocket loop with exponential-backoff reconnection."""
        url = cfg.FLOW_ENGINE_WS_URL
        reconnect_delay = 2.0

        while self._running:
            self._connected = False
            try:
                timeout = aiohttp.ClientTimeout(total=None, connect=5.0)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.ws_connect(
                        url,
                        heartbeat=20.0,
                        receive_timeout=None,
                    ) as ws:
                        self._connected = True
                        reconnect_delay = 2.0
                        logger.info(
                            "[FlowSubscriber] Connected to Rust flow engine — "
                            "fast path ACTIVE"
                        )

                        async for msg in ws:
                            if not self._running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    event = json.loads(msg.data)
                                except json.JSONDecodeError:
                                    continue

                                trigger = self._handle_event(event)
                                if trigger and self._pm:
                                    now = time.monotonic()
                                    if now - self._last_trigger_ts >= cfg.FAST_PATH_COOLDOWN_SECONDS:
                                        self._last_trigger_ts = now
                                        self._trigger_count += 1
                                        logger.info(
                                            f"[FlowSubscriber] Fast trigger "
                                            f"#{self._trigger_count}: {trigger}"
                                        )
                                        asyncio.ensure_future(
                                            self._pm.fast_evaluate(trigger)
                                        )

                            elif msg.type in (
                                aiohttp.WSMsgType.CLOSED,
                                aiohttp.WSMsgType.ERROR,
                            ):
                                break

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    logger.debug(
                        f"[FlowSubscriber] WS disconnected: {e} — "
                        f"retry in {reconnect_delay:.1f}s"
                    )
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 1.5, 30.0)

        self._connected = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self, pm: "PositionManager") -> None:
        """Start the subscriber. Called once from app.py startup."""
        if not cfg.FAST_PATH_ENABLED:
            logger.info("[FlowSubscriber] Fast path disabled via config — skipped")
            return
        self._pm = pm
        self._running = True
        self._task = asyncio.ensure_future(self._connect_and_listen())
        logger.info("[FlowSubscriber] Started (connecting to Rust WS in background)")

    async def stop(self) -> None:
        """Graceful shutdown — called from app.py shutdown_event."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[FlowSubscriber] Stopped")

    # ── Stats (for AI Agent tab) ──────────────────────────────────────────

    @property
    def stats(self) -> dict:
        """Snapshot of current subscriber state for the dashboard."""
        self._prune(self._sweeps, cfg.FAST_PATH_WINDOW_SECONDS)
        self._prune(self._absorptions, cfg.FAST_PATH_WINDOW_SECONDS)
        last_ago = (
            round(time.monotonic() - self._last_trigger_ts, 1)
            if self._last_trigger_ts > 0
            else None
        )
        return {
            "enabled": cfg.FAST_PATH_ENABLED,
            "connected": self._connected,
            "total_triggers": self._trigger_count,
            "sweeps_in_window": len(self._sweeps),
            "absorptions_in_window": len(self._absorptions),
            "last_trigger_ago_s": last_ago,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

flow_subscriber = FlowSubscriber()
