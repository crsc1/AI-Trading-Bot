"""
ThetaData WebSocket streaming client for real-time option quotes and trades.

Connects to the local ThetaData Terminal WebSocket (ws://127.0.0.1:25520/v1/events)
and streams real-time option data to connected dashboard clients via FastAPI WebSocket.

ThetaData Standard plan includes:
  - Up to 10K streaming quote contracts
  - Up to 15K streaming trade contracts

Message types:
  - QUOTE  : Bid/ask updates for subscribed option contracts
  - TRADE  : Execution data (price, size, exchange) for subscribed contracts
  - STATUS : Keepalive heartbeat sent every second

Contract format for options:
  {"security_type": "OPTION", "root": "SPY", "expiration": 20260404,
   "strike": 655000, "right": "C"}

Note: Strike prices are in 1/10th of a cent (e.g., $655 = 655000).
"""

import asyncio
import json
import logging
import time
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


class ThetaStreamClient:
    """
    Manages persistent WebSocket connection to ThetaData Terminal.
    Broadcasts received option events to registered callbacks.

    Only one WebSocket connection to ThetaData is allowed at a time.
    """

    def __init__(self, ws_url: str = "ws://localhost:25520/v1/events"):
        self.ws_url = ws_url
        self.ws = None
        self.running = False
        self.connected = False
        self._task: Optional[asyncio.Task] = None
        self._reconnect_delay = 3.0
        self._max_reconnect_delay = 60.0
        self._max_retries = 10
        self._retry_count = 0

        # Typed callbacks
        self._quote_callbacks: list[Callable[[dict], Awaitable[None]]] = []
        self._trade_callbacks: list[Callable[[dict], Awaitable[None]]] = []
        self._status_callbacks: list[Callable[[dict], Awaitable[None]]] = []

        # Stats
        self.quotes_received = 0
        self.trades_received = 0
        self.status_received = 0
        self.last_quote_time: Optional[float] = None
        self.last_trade_time: Optional[float] = None
        self.last_status_time: Optional[float] = None

    # ── Callback registration ────────────────────────────────────────────

    def on_quote(self, callback: Callable[[dict], Awaitable[None]]):
        """Register an async callback for QUOTE events."""
        self._quote_callbacks.append(callback)

    def on_trade(self, callback: Callable[[dict], Awaitable[None]]):
        """Register an async callback for TRADE events."""
        self._trade_callbacks.append(callback)

    def on_status(self, callback: Callable[[dict], Awaitable[None]]):
        """Register an async callback for STATUS events."""
        self._status_callbacks.append(callback)

    async def _emit_quote(self, event: dict):
        """Send quote event to all registered quote callbacks."""
        for cb in self._quote_callbacks:
            try:
                await cb(event)
            except Exception as e:
                logger.error(f"ThetaData quote callback error: {e}")

    async def _emit_trade(self, event: dict):
        """Send trade event to all registered trade callbacks."""
        for cb in self._trade_callbacks:
            try:
                await cb(event)
            except Exception as e:
                logger.error(f"ThetaData trade callback error: {e}")

    async def _emit_status(self, event: dict):
        """Send status event to all registered status callbacks."""
        for cb in self._status_callbacks:
            try:
                await cb(event)
            except Exception as e:
                logger.error(f"ThetaData status callback error: {e}")

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def connect(self):
        """Start the WebSocket connection in a background task."""
        if self.running:
            return
        self.running = True
        self._retry_count = 0
        self._task = asyncio.create_task(self._run_forever())
        logger.info(f"ThetaData WS stream starting — {self.ws_url}")

    async def disconnect(self):
        """Stop the WebSocket connection."""
        self.running = False
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.connected = False
        logger.info("ThetaData WS stream stopped")

    # ── Subscriptions ────────────────────────────────────────────────────

    async def subscribe_quotes(
        self,
        root: str,
        expiration: int,
        strikes: list[int],
        rights: list[str] = None,
    ):
        """
        Subscribe to option quote updates.

        Args:
            root: Underlying symbol (e.g. "SPY")
            expiration: Expiration date as YYYYMMDD int (e.g. 20260404)
            strikes: List of strike prices in dollars (converted to 1/10th cent)
            rights: List of "C" and/or "P" (defaults to both)
        """
        if not self.ws or not self.connected:
            logger.warning("ThetaData WS not connected — cannot subscribe to quotes")
            return

        rights = rights or ["C", "P"]
        for strike in strikes:
            strike_theta = int(strike * 1000)  # Convert dollars to 1/10th cent
            for right in rights:
                contract = {
                    "security_type": "OPTION",
                    "root": root,
                    "expiration": expiration,
                    "strike": strike_theta,
                    "right": right,
                }
                msg = {
                    "msg_type": "STREAM",
                    "sec_type": "OPTION",
                    "req_type": "QUOTE",
                    "add": True,
                    "id": 0,
                    "contract": contract,
                }
                try:
                    await self.ws.send(json.dumps(msg))
                    logger.debug(
                        f"Subscribed to QUOTE: {root} {expiration} "
                        f"${strike} {right}"
                    )
                except Exception as e:
                    logger.error(f"ThetaData subscribe_quotes error: {e}")

        logger.info(
            f"ThetaData QUOTE subscriptions sent: {root} {expiration} "
            f"{len(strikes)} strikes x {len(rights)} rights"
        )

    async def subscribe_trades(self, root: str, expiration: int):
        """
        Subscribe to option trade updates for all contracts under a root/expiration.

        Args:
            root: Underlying symbol (e.g. "SPY")
            expiration: Expiration date as YYYYMMDD int (e.g. 20260404)
        """
        if not self.ws or not self.connected:
            logger.warning("ThetaData WS not connected — cannot subscribe to trades")
            return

        contract = {
            "security_type": "OPTION",
            "root": root,
            "expiration": expiration,
        }
        msg = {
            "msg_type": "STREAM",
            "sec_type": "OPTION",
            "req_type": "TRADE",
            "add": True,
            "id": 0,
            "contract": contract,
        }
        try:
            await self.ws.send(json.dumps(msg))
            logger.info(f"Subscribed to TRADE: {root} {expiration}")
        except Exception as e:
            logger.error(f"ThetaData subscribe_trades error: {e}")

    # ── Main loop ────────────────────────────────────────────────────────

    async def _run_forever(self):
        """Main loop — connect, receive, reconnect with exponential backoff."""
        import websockets

        while self.running and self._retry_count < self._max_retries:
            try:
                logger.info(f"Connecting to ThetaData WS: {self.ws_url}")
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=30,
                    ping_timeout=15,
                    max_size=10 * 1024 * 1024,  # 10MB
                ) as ws:
                    self.ws = ws
                    self.connected = True
                    self._reconnect_delay = 3.0
                    self._retry_count = 0
                    logger.info("ThetaData WS connected")

                    await self._emit_status({
                        "type": "theta_stream_status",
                        "status": "connected",
                    })

                    # Receive loop
                    async for raw_msg in ws:
                        if not self.running:
                            break
                        try:
                            data = json.loads(raw_msg)
                            await self._handle_message(data)
                        except json.JSONDecodeError:
                            logger.warning(
                                f"Invalid JSON from ThetaData WS: {raw_msg[:200]}"
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ThetaData WS error: {e}")
                self.connected = False
                self._retry_count += 1

                await self._emit_status({
                    "type": "theta_stream_status",
                    "status": "disconnected",
                    "error": str(e),
                    "retry_count": self._retry_count,
                })

                if self._retry_count >= self._max_retries:
                    logger.warning(
                        f"ThetaData WS max retries ({self._max_retries}) reached "
                        "— giving up. REST polling will continue as fallback."
                    )
                    break

                if self.running:
                    wait = min(self._reconnect_delay, self._max_reconnect_delay)
                    logger.info(
                        f"ThetaData WS reconnecting in {wait:.0f}s "
                        f"(attempt {self._retry_count}/{self._max_retries})..."
                    )
                    await asyncio.sleep(wait)
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2, self._max_reconnect_delay
                    )

        self.connected = False

    # ── Message handling ─────────────────────────────────────────────────

    async def _handle_message(self, data: dict):
        """Process a single ThetaData WebSocket message."""
        header = data.get("header", {})
        msg_type = header.get("type", "")
        status = header.get("status", "")

        if msg_type == "STATUS":
            # Keepalive heartbeat — sent every second
            self.status_received += 1
            self.last_status_time = time.time()
            logger.debug(f"ThetaData STATUS keepalive: {status}")
            return

        contract = data.get("contract", {})
        root = contract.get("root", "")
        expiration = contract.get("expiration", 0)
        strike_raw = contract.get("strike", 0)
        right = contract.get("right", "")

        # Convert strike from 1/10th cent to dollars
        strike_dollars = strike_raw / 1000.0

        if msg_type == "QUOTE":
            self.quotes_received += 1
            self.last_quote_time = time.time()

            event = {
                "type": "theta_quote",
                "root": root,
                "expiration": expiration,
                "strike": strike_dollars,
                "right": right,
                "bid": data.get("bid", 0),
                "ask": data.get("ask", 0),
                "bid_size": data.get("bid_size", 0),
                "ask_size": data.get("ask_size", 0),
                "bid_exchange": data.get("bid_exchange", ""),
                "ask_exchange": data.get("ask_exchange", ""),
                "status": status,
            }
            logger.debug(
                f"ThetaData QUOTE: {root} {expiration} "
                f"${strike_dollars} {right} "
                f"bid={event['bid']} ask={event['ask']}"
            )
            await self._emit_quote(event)

        elif msg_type == "TRADE":
            self.trades_received += 1
            self.last_trade_time = time.time()

            event = {
                "type": "theta_trade",
                "root": root,
                "expiration": expiration,
                "strike": strike_dollars,
                "right": right,
                "price": data.get("price", 0),
                "size": data.get("size", 0),
                "exchange": data.get("exchange", ""),
                "sequence": data.get("sequence", 0),
                "conditions": data.get("conditions", []),
                "status": status,
            }
            logger.debug(
                f"ThetaData TRADE: {root} {expiration} "
                f"${strike_dollars} {right} "
                f"price={event['price']} size={event['size']}"
            )
            await self._emit_trade(event)

        else:
            logger.debug(f"ThetaData unknown message type: {msg_type}")

    # ── Stats ────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return current streaming stats."""
        return {
            "connected": self.connected,
            "running": self.running,
            "ws_url": self.ws_url,
            "quotes_received": self.quotes_received,
            "trades_received": self.trades_received,
            "status_received": self.status_received,
            "last_quote_time": self.last_quote_time,
            "last_trade_time": self.last_trade_time,
            "last_status_time": self.last_status_time,
            "retry_count": self._retry_count,
            "max_retries": self._max_retries,
        }


# Singleton instance
theta_stream = ThetaStreamClient()
