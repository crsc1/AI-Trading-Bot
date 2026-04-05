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

    Also accumulates real tick data and flow events into a rolling buffer
    that the signal pipeline can query via get_flow_state() to build
    an OrderFlowState from actual market data instead of synthetic trades.
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

        # ── Real flow data accumulation (for confluence scoring) ──
        # Rolling buffer of real classified ticks from Rust engine (last 5 min)
        self._ticks: deque = deque(maxlen=10000)
        # Latest footprint snapshot
        self._latest_footprint: Optional[dict] = None
        # Latest CVD values
        self._latest_cvd: Optional[dict] = None
        # Rolling imbalance events
        self._imbalances: deque = deque(maxlen=100)
        # Large trade events
        self._large_trades: deque = deque(maxlen=50)
        # Absorption events (with held status)
        self._absorption_events: deque = deque(maxlen=50)

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
        Accumulates all events for flow state. Returns a trigger context dict
        if a fast condition fires, else None.
        """
        etype = event.get("type")
        now = time.monotonic()

        # ── Accumulate all events for real flow state ──
        if etype == "tick":
            self._ticks.append({
                "price": event.get("price", 0),
                "size": event.get("size", 0),
                "side": event.get("side", "unknown"),
                "ts": now,
            })

        elif etype == "footprint":
            self._latest_footprint = event

        elif etype == "cvd":
            self._latest_cvd = event

        elif etype == "imbalance":
            self._imbalances.append({**event, "_ts": now})

        elif etype == "large_trade":
            self._large_trades.append({**event, "_ts": now})

        elif etype == "absorption":
            self._absorption_events.append({**event, "_ts": now})

        # ── Fast-path trigger detection (existing logic) ──
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

    # ── Real flow state for confluence scoring ────────────────────────────

    def get_real_trades(self, window_seconds: int = 300) -> list:
        """
        Return real classified ticks from the Rust engine for the last N seconds.
        Format matches what analyze_order_flow() expects: {price, size, side, timestamp}.
        Returns empty list if no real data available (Rust engine not connected).
        """
        if not self._connected or not self._ticks:
            return []

        cutoff = time.monotonic() - window_seconds
        trades = []
        for tick in self._ticks:
            if tick["ts"] >= cutoff:
                trades.append({
                    "price": tick["price"],
                    "size": tick["size"],
                    "side": tick["side"],
                    "timestamp": str(tick["ts"]),
                    "exchange": "RUST_ENGINE",
                })
        return trades

    def get_flow_context(self) -> Optional[dict]:
        """
        Return structured flow context from the Rust engine for enriching signals.
        Includes latest CVD, footprint summary, recent imbalances, absorptions.
        Returns None if Rust engine is not connected or no data.
        """
        if not self._connected:
            return None

        now = time.monotonic()
        window = 300  # 5 minutes

        # Count recent imbalances by side
        recent_imbalances = [
            e for e in self._imbalances if e.get("_ts", 0) > now - window
        ]
        imb_buy = sum(1 for e in recent_imbalances if e.get("side") == "buy")
        imb_sell = sum(1 for e in recent_imbalances if e.get("side") == "sell")

        # Recent absorptions (held only)
        recent_absorptions = [
            e for e in self._absorption_events
            if e.get("_ts", 0) > now - window and e.get("held", False)
        ]
        abs_buy = sum(1 for e in recent_absorptions if e.get("side") == "bid")
        abs_sell = sum(1 for e in recent_absorptions if e.get("side") == "ask")

        # Recent large trades
        recent_large = [
            e for e in self._large_trades if e.get("_ts", 0) > now - window
        ]
        large_buy = sum(e.get("size", 0) for e in recent_large if e.get("side") == "buy")
        large_sell = sum(e.get("size", 0) for e in recent_large if e.get("side") == "sell")

        return {
            "cvd": self._latest_cvd,
            "footprint": self._latest_footprint,
            "imbalance_buy_count": imb_buy,
            "imbalance_sell_count": imb_sell,
            "imbalance_stacked_max": max(
                (e.get("stacked", 0) for e in recent_imbalances), default=0
            ),
            "absorption_bid_count": abs_buy,
            "absorption_ask_count": abs_sell,
            "large_trade_buy_vol": large_buy,
            "large_trade_sell_vol": large_sell,
            "tick_count": len(self._ticks),
            "connected": True,
        }

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
