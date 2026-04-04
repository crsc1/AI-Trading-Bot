"""
Alpaca WebSocket streaming client for Python backend.

Connects to Alpaca SIP WebSocket (wss://stream.data.alpaca.markets/v2/sip)
and streams real-time data to connected dashboard clients via the FastAPI WebSocket.

Channels used (Algo Trader Plus subscription):
  - trades (t)     : Individual trades with exchange, price, size, conditions
  - quotes (q)     : NBBO quotes with bid/ask/size from all exchanges
  - bars (b)       : Minute bars (OHLCV + VWAP + trade count)
  - updatedBars (u): Corrected minute bars when trades are adjusted
  - lulds (l)      : Limit Up/Limit Down bands
  - statuses (s)   : Trading halts/resumptions
"""

import asyncio
import json
import logging
import os
from typing import Optional, Set, Callable, Awaitable

logger = logging.getLogger(__name__)

# Alpaca SIP WebSocket URL (Algo Trader Plus)
ALPACA_WS_URL = os.environ.get(
    "ALPACA_WS_URL", "wss://stream.data.alpaca.markets/v2/sip"
)
ALPACA_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET = os.environ.get("ALPACA_SECRET_KEY", "")


class AlpacaStreamClient:
    """
    Manages persistent WebSocket connection to Alpaca SIP stream.
    Broadcasts received events to registered callbacks.
    """

    def __init__(self):
        self.ws = None
        self.running = False
        self.connected = False
        self.subscribed_symbols: Set[str] = set()
        self._callbacks: list[Callable[[dict], Awaitable[None]]] = []
        self._task: Optional[asyncio.Task] = None
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._connection_limit_hit = False

        # Stats
        self.trades_received = 0
        self.quotes_received = 0
        self.bars_received = 0
        self.lulds_received = 0
        self.halts_received = 0
        self.last_trade_time: Optional[str] = None
        self.last_nbbo: Optional[dict] = None  # {bid, ask, bid_size, ask_size}

    def on_event(self, callback: Callable[[dict], Awaitable[None]]):
        """Register an async callback for all stream events."""
        self._callbacks.append(callback)

    async def _emit(self, event: dict):
        """Send event to all registered callbacks."""
        for cb in self._callbacks:
            try:
                await cb(event)
            except Exception as e:
                logger.error(f"Alpaca WS callback error: {e}")

    async def start(self, symbols: list[str] = None):
        """Start the WebSocket connection in a background task."""
        if self.running:
            return
        if not ALPACA_KEY or not ALPACA_SECRET:
            logger.warning("Alpaca API keys not configured — WS stream disabled")
            return
        self.running = True
        self.subscribed_symbols = set(symbols or ["SPY"])
        self._task = asyncio.create_task(self._run_forever())
        logger.info(f"Alpaca WS stream starting for {self.subscribed_symbols}")

    async def stop(self):
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
        logger.info("Alpaca WS stream stopped")

    async def subscribe(self, symbols: list[str]):
        """Subscribe to additional symbols."""
        new_syms = set(symbols) - self.subscribed_symbols
        if not new_syms:
            return
        self.subscribed_symbols |= new_syms
        if self.ws and self.connected:
            sub_msg = {
                "action": "subscribe",
                "trades": list(new_syms),
                "quotes": list(new_syms),
                "bars": list(new_syms),
                "updatedBars": list(new_syms),
                "lulds": list(new_syms),
                "statuses": list(new_syms),
            }
            try:
                await self.ws.send(json.dumps(sub_msg))
                logger.info(f"Subscribed to additional symbols: {new_syms}")
            except Exception as e:
                logger.error(f"Subscribe error: {e}")

    async def unsubscribe(self, symbols: list[str]):
        """Unsubscribe from symbols."""
        remove_syms = set(symbols) & self.subscribed_symbols
        if not remove_syms:
            return
        self.subscribed_symbols -= remove_syms
        if self.ws and self.connected:
            unsub_msg = {
                "action": "unsubscribe",
                "trades": list(remove_syms),
                "quotes": list(remove_syms),
                "bars": list(remove_syms),
            }
            try:
                await self.ws.send(json.dumps(unsub_msg))
            except Exception as e:
                logger.error(f"Unsubscribe error: {e}")

    async def _run_forever(self):
        """Main loop — connect, authenticate, subscribe, receive, reconnect."""
        import websockets

        while self.running:
            try:
                logger.info(f"Connecting to Alpaca WS: {ALPACA_WS_URL}")
                async with websockets.connect(
                    ALPACA_WS_URL,
                    ping_interval=20,
                    ping_timeout=10,
                    max_size=10 * 1024 * 1024,  # 10MB
                ) as ws:
                    self.ws = ws
                    self._reconnect_delay = 1.0

                    # Step 1: Receive welcome
                    welcome = await ws.recv()
                    welcome_data = json.loads(welcome)
                    logger.info(f"Alpaca WS welcome: {welcome_data}")

                    # Step 2: Authenticate
                    auth_msg = {
                        "action": "auth",
                        "key": ALPACA_KEY,
                        "secret": ALPACA_SECRET,
                    }
                    await ws.send(json.dumps(auth_msg))
                    auth_resp = await ws.recv()
                    auth_data = json.loads(auth_resp)
                    logger.info(f"Alpaca WS auth: {auth_data}")

                    # Check auth success
                    if isinstance(auth_data, list) and auth_data:
                        msg = auth_data[0].get("msg", "")
                        code = auth_data[0].get("code", 0)

                        if msg == "authenticated":
                            # NOTE: Don't set connected=True yet — wait for subscription confirmation
                            self._connection_limit_hit = False
                            logger.info("Alpaca WS authenticated — subscribing...")
                        elif code == 406 or "connection limit" in msg.lower():
                            # Another client (Rust engine) already holds the SIP connection.
                            # Back off with exponential delay — don't spam Alpaca.
                            if not self._connection_limit_hit:
                                logger.warning(
                                    "Alpaca SIP connection limit exceeded — "
                                    "Rust engine likely holds the slot. "
                                    "Python WS will retry with backoff."
                                )
                                self._connection_limit_hit = True
                            self.connected = False
                            wait = min(self._reconnect_delay, self._max_reconnect_delay)
                            self._reconnect_delay = min(wait * 2, self._max_reconnect_delay)
                            await asyncio.sleep(wait)
                            continue
                        else:
                            logger.error(f"Auth failed: {auth_data}")
                            self.connected = False
                            await asyncio.sleep(10)
                            continue

                    # Step 3: Subscribe to all channels
                    syms = list(self.subscribed_symbols)
                    sub_msg = {
                        "action": "subscribe",
                        "trades": syms,
                        "quotes": syms,
                        "bars": syms,
                        "updatedBars": syms,
                        "lulds": syms,
                        "statuses": syms,
                    }
                    await ws.send(json.dumps(sub_msg))
                    sub_resp = await ws.recv()
                    logger.info(f"Alpaca WS subscribed: {sub_resp}")

                    # NOW mark connected — auth AND subscription both succeeded
                    self.connected = True
                    self._reconnect_delay = 5  # Reset backoff on successful connection
                    await self._emit({
                        "type": "stream_status",
                        "status": "connected",
                        "data_source": "LIVE WS — SIP",
                    })

                    # Step 4: Receive loop
                    async for raw_msg in ws:
                        if not self.running:
                            break
                        try:
                            messages = json.loads(raw_msg)
                            if isinstance(messages, list):
                                for msg in messages:
                                    await self._handle_message(msg)
                            else:
                                await self._handle_message(messages)
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON from Alpaca WS: {raw_msg[:200]}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                err_str = str(e).lower()
                logger.error(f"Alpaca WS error: {e}")
                self.connected = False

                # Detect proxy/firewall blocks — stop retrying entirely
                is_proxy_block = (
                    "proxy rejected" in err_str
                    or "403" in err_str
                    or "blocked" in err_str
                    or "forbidden" in err_str
                )

                await self._emit({
                    "type": "stream_status",
                    "status": "proxy_blocked" if is_proxy_block else "disconnected",
                    "error": str(e),
                })

                if is_proxy_block:
                    logger.warning(
                        "Network proxy blocks Alpaca WebSocket — "
                        "stopping WS retries. REST polling will provide price updates."
                    )
                    self.running = False
                    break

                if self.running:
                    logger.info(
                        f"Reconnecting in {self._reconnect_delay}s..."
                    )
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2, self._max_reconnect_delay
                    )

        self.connected = False

    async def _handle_message(self, msg: dict):
        """Process a single Alpaca WebSocket message."""
        msg_type = msg.get("T", "")

        if msg_type == "t":
            # Trade
            self.trades_received += 1
            self.last_trade_time = msg.get("t")
            event = {
                "type": "trade",
                "symbol": msg.get("S", ""),
                "price": msg.get("p", 0),
                "size": msg.get("s", 0),
                "timestamp": msg.get("t", ""),
                "exchange": msg.get("x", ""),
                "conditions": msg.get("c", []),
                "tape": msg.get("z", ""),
                "id": msg.get("i", 0),
            }
            # Classify buy/sell using last NBBO midpoint
            if self.last_nbbo:
                mid = (self.last_nbbo["bid"] + self.last_nbbo["ask"]) / 2
                if event["price"] > mid:
                    event["side"] = "buy"
                elif event["price"] < mid:
                    event["side"] = "sell"
                else:
                    event["side"] = "neutral"
                event["nbbo_mid"] = round(mid, 4)
            await self._emit(event)

        elif msg_type == "q":
            # Quote (NBBO)
            self.quotes_received += 1
            bid = msg.get("bp", 0)
            ask = msg.get("ap", 0)
            if bid > 0 and ask > 0:
                self.last_nbbo = {
                    "bid": bid,
                    "ask": ask,
                    "bid_size": msg.get("bs", 0),
                    "ask_size": msg.get("as", 0),
                }
            event = {
                "type": "quote",
                "symbol": msg.get("S", ""),
                "bid": bid,
                "ask": ask,
                "bid_size": msg.get("bs", 0),
                "ask_size": msg.get("as", 0),
                "timestamp": msg.get("t", ""),
                "bid_exchange": msg.get("bx", ""),
                "ask_exchange": msg.get("ax", ""),
                "conditions": msg.get("c", []),
            }
            await self._emit(event)

        elif msg_type == "b":
            # Minute bar
            self.bars_received += 1
            event = {
                "type": "bar",
                "symbol": msg.get("S", ""),
                "open": msg.get("o", 0),
                "high": msg.get("h", 0),
                "low": msg.get("l", 0),
                "close": msg.get("c", 0),
                "volume": msg.get("v", 0),
                "vwap": msg.get("vw", 0),
                "trade_count": msg.get("n", 0),
                "timestamp": msg.get("t", ""),
            }
            await self._emit(event)

        elif msg_type == "u":
            # Updated/corrected bar
            event = {
                "type": "bar_update",
                "symbol": msg.get("S", ""),
                "open": msg.get("o", 0),
                "high": msg.get("h", 0),
                "low": msg.get("l", 0),
                "close": msg.get("c", 0),
                "volume": msg.get("v", 0),
                "vwap": msg.get("vw", 0),
                "trade_count": msg.get("n", 0),
                "timestamp": msg.get("t", ""),
            }
            await self._emit(event)

        elif msg_type == "l":
            # LULD (Limit Up / Limit Down)
            self.lulds_received += 1
            event = {
                "type": "luld",
                "symbol": msg.get("S", ""),
                "limit_up": msg.get("u", 0),
                "limit_down": msg.get("d", 0),
                "indicator": msg.get("i", ""),
                "timestamp": msg.get("t", ""),
            }
            await self._emit(event)

        elif msg_type == "s":
            # Trading status (halt/resume)
            self.halts_received += 1
            event = {
                "type": "trading_status",
                "symbol": msg.get("S", ""),
                "status_code": msg.get("sc", ""),
                "status_message": msg.get("sm", ""),
                "reason_code": msg.get("rc", ""),
                "reason_message": msg.get("rm", ""),
                "timestamp": msg.get("t", ""),
            }
            await self._emit(event)

        elif msg_type == "c":
            # Trade correction
            event = {
                "type": "trade_correction",
                "symbol": msg.get("S", ""),
                "original_id": msg.get("oi", 0),
                "corrected_price": msg.get("p", 0),
                "corrected_size": msg.get("s", 0),
                "timestamp": msg.get("t", ""),
            }
            await self._emit(event)

        elif msg_type == "x":
            # Trade cancel
            event = {
                "type": "trade_cancel",
                "symbol": msg.get("S", ""),
                "cancel_id": msg.get("i", 0),
                "timestamp": msg.get("t", ""),
            }
            await self._emit(event)

    def get_stats(self) -> dict:
        """Return current streaming stats."""
        if self.connected:
            source = "LIVE WS — SIP"
        elif self._connection_limit_hit:
            source = "Waiting — engine holds SIP slot"
        else:
            source = "disconnected"
        return {
            "connected": self.connected,
            "data_source": source,
            "connection_limit_hit": self._connection_limit_hit,
            "subscribed_symbols": list(self.subscribed_symbols),
            "trades_received": self.trades_received,
            "quotes_received": self.quotes_received,
            "bars_received": self.bars_received,
            "lulds_received": self.lulds_received,
            "halts_received": self.halts_received,
            "last_trade_time": self.last_trade_time,
            "last_nbbo": self.last_nbbo,
        }


# Singleton instance
alpaca_stream = AlpacaStreamClient()
