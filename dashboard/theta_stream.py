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
import math
import time
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Callable, Awaitable

from dashboard.flow_toxicity import VPINCalculator

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

        # Quote book: latest bid/ask per (strike, right) for Lee-Ready classification
        # Key: (strike_dollars: float, right: str) → {"bid": float, "ask": float}
        self._quote_book: dict[tuple[float, str], dict[str, float]] = {}

        # Greeks book: computed on quote updates, attached to trades
        # Key: (strike_dollars: float, right: str) → {"iv", "delta", "gamma", "theta", "vega"}
        self._greeks_book: dict[tuple[float, str], dict[str, float]] = {}
        self._underlying_price: float = 0.0  # Latest SPY price for BS model
        self._risk_free_rate: float = 0.045  # ~4.5% Fed funds rate

        # Options VPIN: volume-synchronized flow toxicity from options trades
        # Bucket size = 200 contracts (options trade in smaller lots than equity)
        # 40 buckets = ~8,000 contracts rolling window
        self._options_vpin = VPINCalculator(bucket_size=200, num_buckets=40)

        # Stats
        self.quotes_received = 0
        self.trades_received = 0
        self.status_received = 0
        self.last_quote_time: Optional[float] = None
        self.last_trade_time: Optional[float] = None
        self.last_status_time: Optional[float] = None

    def update_underlying_price(self, price: float):
        """Update SPY price for Greeks computation. Called from market data feed."""
        if price > 0:
            self._underlying_price = price

    def get_options_flow_context(self) -> dict:
        """
        Return a snapshot of options flow state for the signal engine.
        Called every 15s cycle. All data is pre-computed, no latency.
        """
        vpin_state = self._options_vpin.get_state()

        # Compute recent trade stats from the last 60s of trade callbacks
        # We track running totals in _trade_stats (updated on each trade)
        buy_premium = getattr(self, '_recent_buy_premium', 0)
        sell_premium = getattr(self, '_recent_sell_premium', 0)
        total_premium = buy_premium + sell_premium
        call_premium = getattr(self, '_recent_call_premium', 0)
        put_premium = getattr(self, '_recent_put_premium', 0)

        # Sweep count from recent trades
        sweep_count = getattr(self, '_recent_sweep_count', 0)
        high_sms_count = getattr(self, '_recent_high_sms_count', 0)

        return {
            "connected": self.connected,
            "trades_received": self.trades_received,
            # VPIN — flow toxicity (0-1, >0.7 = toxic)
            "vpin": vpin_state.vpin if vpin_state.bucket_count >= 5 else None,
            "vpin_level": vpin_state.toxicity_level,
            # Volume split
            "buy_volume": vpin_state.buy_volume,
            "sell_volume": vpin_state.sell_volume,
            "volume_imbalance": vpin_state.imbalance_ratio,
            # Premium split (from running totals)
            "buy_premium": buy_premium,
            "sell_premium": sell_premium,
            "call_premium": call_premium,
            "put_premium": put_premium,
            "pcr_premium": (put_premium / call_premium) if call_premium > 0 else 1.0,
            # Smart money
            "high_sms_count": high_sms_count,  # trades with SMS >= 70
            "sweep_count": sweep_count,
            # Greeks book
            "greeks_book_size": len(self._greeks_book),
            "underlying_price": self._underlying_price,
        }

    def _update_running_stats(self, event: dict):
        """Update running trade stats for get_options_flow_context(). Called on each trade."""
        premium = event.get("price", 0) * event.get("size", 0) * 100
        side = event.get("side", "mid")
        right = event.get("right", "C")
        sms = event.get("sms", 0)

        if side == "buy":
            self._recent_buy_premium = getattr(self, '_recent_buy_premium', 0) + premium
        elif side == "sell":
            self._recent_sell_premium = getattr(self, '_recent_sell_premium', 0) + premium

        if right == "C":
            self._recent_call_premium = getattr(self, '_recent_call_premium', 0) + premium
        else:
            self._recent_put_premium = getattr(self, '_recent_put_premium', 0) + premium

        if sms >= 70:
            self._recent_high_sms_count = getattr(self, '_recent_high_sms_count', 0) + 1

    _ET = ZoneInfo("America/New_York")

    # Market calendar from Alpaca API. Stores trading days with close times.
    # Alpaca returns ONLY trading days, so any missing date = closed.
    _trading_days: dict[date, int] = {}  # date → close hour (16 or 13)
    _calendar_loaded = False

    async def load_market_calendar(self):
        """
        Fetch NYSE trading calendar from Alpaca API for the current year.
        Call once on startup. Falls back to weekday-only if API is unavailable.
        """
        import aiohttp
        from .config import cfg

        year = datetime.now(self._ET).year
        start = f"{year}-01-01"
        end = f"{year}-12-31"

        try:
            headers = cfg.ALPACA_HEADERS
            base_url = cfg.ALPACA_BASE_URL
            url = f"{base_url}/calendar?start={start}&end={end}"
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        cal = await resp.json()
                        early = 0
                        for entry in cal:
                            d = date.fromisoformat(entry["date"])
                            close_str = entry.get("close", "16:00")
                            close_hour = int(close_str.split(":")[0])
                            self._trading_days[d] = close_hour
                            if close_hour < 16:
                                early += 1
                        self._calendar_loaded = True
                        logger.info(
                            f"Market calendar loaded from Alpaca: "
                            f"{len(self._trading_days)} trading days, "
                            f"{early} early closes for {year}"
                        )
                        return
        except Exception as e:
            logger.warning(f"Alpaca calendar API failed: {e}")

        self._calendar_loaded = False
        logger.info("Calendar not loaded, using weekday-only fallback")

    def _market_close_hour(self, d: date) -> int:
        """Return market close hour for a date (16 normally, 13 on early close)."""
        if self._calendar_loaded:
            return self._trading_days.get(d, 16)
        return 16

    def _is_trading_day(self, d: date) -> bool:
        """Check if a date is a trading day (weekday + not a holiday)."""
        if d.weekday() >= 5:
            return False
        if self._calendar_loaded:
            return d in self._trading_days
        return True  # Fallback: all weekdays are trading days

    def _trading_days_between(self, start: date, end: date) -> int:
        """Count trading days between two dates (exclusive of start, inclusive of end)."""
        from datetime import timedelta
        count = 0
        d = start + timedelta(days=1)
        while d <= end:
            if self._is_trading_day(d):
                count += 1
            d += timedelta(days=1)
        return count

    def _time_to_expiry(self, expiration: int) -> float:
        """
        Convert YYYYMMDD expiration to years remaining using trading time.
        Uses 252 trading days/year. Accounts for weekends, NYSE holidays, and early closes.
        During market hours: fractional day based on time remaining to close.
        Outside market hours: counts only full trading days ahead.
        Minimum 1 minute.
        """
        exp_day = date(
            expiration // 10000,
            (expiration % 10000) // 100,
            expiration % 100,
        )
        close_hour = self._market_close_hour(exp_day)
        exp_date = datetime(
            exp_day.year, exp_day.month, exp_day.day,
            close_hour, 0,
            tzinfo=self._ET,
        )
        now = datetime.now(self._ET)

        # If already past expiry, clamp to 1 minute
        if now >= exp_date:
            return 60 / (252 * 6.5 * 3600)

        today = now.date()

        if today == exp_day:
            # Same day (0DTE): fractional trading day remaining
            market_close = now.replace(hour=close_hour, minute=0, second=0, microsecond=0)
            market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
            trading_secs = (close_hour - 9.5) * 3600  # actual trading seconds this day
            if now < market_open:
                secs_left = trading_secs
            elif now >= market_close:
                secs_left = 60
            else:
                secs_left = max(60, (market_close - now).total_seconds())
            return secs_left / (252 * 6.5 * 3600)

        # Multi-day: count full trading days + today's remaining fraction
        full_trading_days = self._trading_days_between(today, exp_day)

        # Today's remaining fraction (if today is a trading day and market is open)
        today_fraction = 0.0
        if self._is_trading_day(today):
            today_close = self._market_close_hour(today)
            market_close = now.replace(hour=today_close, minute=0, second=0, microsecond=0)
            market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
            if now < market_open:
                today_fraction = 1.0
            elif now < market_close:
                today_fraction = (market_close - now).total_seconds() / (6.5 * 3600)

        total_trading_days = full_trading_days + today_fraction
        return max(60 / (252 * 6.5 * 3600), total_trading_days / 252)

    def _compute_greeks(
        self, strike: float, right: str, mid_price: float, expiration: int
    ) -> Optional[dict[str, float]]:
        """
        Compute IV + Greeks from the option mid-price using Black-Scholes.
        Returns None if IV solver fails (deep OTM, bad data, etc).
        """
        S = self._underlying_price
        if S <= 0 or mid_price <= 0:
            return None

        K = strike
        T = self._time_to_expiry(expiration)
        r = self._risk_free_rate
        cp = right.upper()

        # Intrinsic check
        intrinsic = max(S - K, 0) if cp == 'C' else max(K - S, 0)
        if mid_price < intrinsic - 0.01:
            return None

        # Newton-Raphson IV solver (inline for speed)
        sqrt_T = math.sqrt(T)
        # Brenner-Subrahmanyam initial guess; for 0DTE (T < 1 day) the formula
        # produces extreme values, so fall back to 0.5 (50% vol)
        if T < 1 / 365:
            sigma = 0.5
        else:
            sigma = max(0.01, min(math.sqrt(2 * math.pi / T) * (mid_price / S), 5.0))

        for _ in range(30):  # 30 iterations is plenty for convergence
            sqrt_sigma_T = sigma * sqrt_T
            d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / sqrt_sigma_T
            d2 = d1 - sqrt_sigma_T

            # CDF approximation (Abramowitz & Stegun)
            nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
            nd2 = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))

            if cp == 'C':
                bs_price = S * nd1 - K * math.exp(-r * T) * nd2
            else:
                bs_price = K * math.exp(-r * T) * (1 - nd2) - S * (1 - nd1)

            diff = bs_price - mid_price
            if abs(diff) < 1e-6:
                break

            # Vega
            npd1 = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
            vega_val = S * sqrt_T * npd1
            if vega_val < 1e-12:
                break

            sigma -= diff / vega_val
            sigma = max(0.001, min(sigma, 10.0))

        if not (0.001 < sigma < 10.0):
            return None

        # Compute Greeks with converged sigma
        sqrt_sigma_T = sigma * sqrt_T
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / sqrt_sigma_T
        d2 = d1 - sqrt_sigma_T
        nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
        npd1 = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)

        gamma_val = npd1 / (S * sqrt_sigma_T)
        delta_val = nd1 if cp == 'C' else nd1 - 1
        # Theta: call = -(S*N'(d1)*σ)/(2√T) - r*K*e^(-rT)*N(d2)
        #        put  = -(S*N'(d1)*σ)/(2√T) + r*K*e^(-rT)*N(-d2)
        nd2 = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
        time_decay = -(S * npd1 * sigma) / (2 * sqrt_T)
        if cp == 'C':
            theta_val = (time_decay - r * K * math.exp(-r * T) * nd2) / 365
        else:
            theta_val = (time_decay + r * K * math.exp(-r * T) * (1 - nd2)) / 365

        return {
            "iv": round(sigma, 4),
            "delta": round(delta_val, 4),
            "gamma": round(gamma_val, 6),
            "theta": round(theta_val, 4),
            "vega": round(S * sqrt_T * npd1 / 100, 4),
        }

    def _smart_money_score(
        self,
        size: int,
        side: str,
        gamma: Optional[float],
        strike: float,
    ) -> int:
        """
        GEX-weighted Smart Money Score (0-100) per trade.

        Components:
          - Size (0-30): sqrt-scaled contract count. 50+ contracts = max.
          - Gamma (0-25): high gamma at strike = max market impact zone.
          - Aggression (0-25): buy/sell at bid/ask = urgency = conviction.
          - ATM proximity (0-20): near-the-money = institutional. Deep OTM = retail lottery.

        Returns integer 0-100.
        """
        score = 0.0

        # 1. Size weight (0-30) — sqrt scale, caps at ~50 contracts
        score += min(30, math.sqrt(size) * 4.24)  # sqrt(50)*4.24 ≈ 30

        # 2. Gamma weight (0-25) — normalized against typical ATM 0DTE gamma
        # ATM 0DTE gamma is roughly 0.05-0.15 for SPY options
        if gamma is not None and gamma > 0:
            gamma_norm = min(1.0, gamma / 0.10)  # 0.10 gamma = full score
            score += gamma_norm * 25

        # 3. Aggression (0-25) — buy/sell at quote edge = conviction
        if side == "buy":
            score += 25  # Bought at ask = maximum aggression
        elif side == "sell":
            score += 25  # Sold at bid = maximum aggression
        else:
            score += 8   # Mid = passive, some credit for being there

        # 4. ATM proximity (0-20) — distance from underlying price
        if self._underlying_price > 0:
            distance = abs(strike - self._underlying_price)
            # Full score within $2 of ATM, linear decay to $15
            if distance <= 2:
                score += 20
            elif distance <= 15:
                score += 20 * (1 - (distance - 2) / 13)
            # Beyond $15 OTM = 0 points (lottery ticket territory)

        return min(100, max(0, round(score)))

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
            # Quote data is nested under "quote" key
            quote_data = data.get("quote", {})
            bid = quote_data.get("bid", 0)
            ask = quote_data.get("ask", 0)

            # Skip empty quotes
            if bid == 0 and ask == 0:
                return

            self.quotes_received += 1
            self.last_quote_time = time.time()

            # Update quote book for Lee-Ready classification
            self._quote_book[(strike_dollars, right)] = {
                "bid": bid, "ask": ask,
            }

            # Compute Greeks from mid-price (only if underlying price is known)
            if self._underlying_price > 0 and bid > 0 and ask > 0:
                mid = (bid + ask) / 2
                greeks = self._compute_greeks(
                    strike_dollars, right, mid, expiration
                )
                if greeks:
                    self._greeks_book[(strike_dollars, right)] = greeks

            event = {
                "type": "theta_quote",
                "root": root,
                "expiration": expiration,
                "strike": strike_dollars,
                "right": right,
                "bid": bid,
                "ask": ask,
                "bid_size": quote_data.get("bid_size", 0),
                "ask_size": quote_data.get("ask_size", 0),
                "bid_exchange": quote_data.get("bid_exchange", 0),
                "ask_exchange": quote_data.get("ask_exchange", 0),
                "ms_of_day": quote_data.get("ms_of_day", 0),
                "status": status,
            }
            logger.debug(
                f"ThetaData QUOTE: {root} {expiration} "
                f"${strike_dollars} {right} "
                f"bid={event['bid']} ask={event['ask']}"
            )
            await self._emit_quote(event)

        elif msg_type == "TRADE":
            # Trade data is nested under "trade" key
            trade_data = data.get("trade", {})
            trade_price = trade_data.get("price", 0)
            trade_size = trade_data.get("size", 0)

            # Skip empty/zero trades (can happen on subscription confirm)
            if trade_price <= 0 or trade_size <= 0:
                return

            self.trades_received += 1
            self.last_trade_time = time.time()

            # Lee-Ready trade classification:
            # Compare trade price against latest bid/ask for this contract.
            # At/above ask = buyer-initiated, at/below bid = seller-initiated, else mid.
            quote = self._quote_book.get((strike_dollars, right))
            if quote and quote["ask"] > 0 and quote["bid"] > 0:
                if trade_price >= quote["ask"]:
                    side = "buy"
                elif trade_price <= quote["bid"]:
                    side = "sell"
                else:
                    side = "mid"
            else:
                side = "mid"  # No quote data yet, default to mid

            # Convert ms_of_day to epoch timestamp
            ms_of_day = trade_data.get("ms_of_day", 0)
            trade_date = trade_data.get("date", expiration)

            # Attach Greeks from the Greeks book (computed on latest quote)
            greeks = self._greeks_book.get((strike_dollars, right))

            # Feed options VPIN calculator (uses pre-classified side)
            if quote:
                self._options_vpin.update_quote(quote["bid"], quote["ask"])
            self._options_vpin.add_trade(trade_price, trade_size)
            vpin_state = self._options_vpin.get_state()

            # Smart Money Score (0-100)
            sms = self._smart_money_score(
                trade_size, side,
                greeks["gamma"] if greeks else None,
                strike_dollars,
            )

            event = {
                "type": "theta_trade",
                "root": root,
                "expiration": expiration,
                "strike": strike_dollars,
                "right": right,
                "price": trade_price,
                "size": trade_size,
                "side": side,
                "iv": greeks["iv"] if greeks else None,
                "delta": greeks["delta"] if greeks else None,
                "gamma": greeks["gamma"] if greeks else None,
                "vpin": vpin_state.vpin if vpin_state.bucket_count >= 5 else None,
                "sms": sms,
                "exchange": trade_data.get("exchange", 0),
                "sequence": trade_data.get("sequence", 0),
                "condition": trade_data.get("condition", 0),
                "ms_of_day": ms_of_day,
                "status": status,
            }
            logger.debug(
                f"ThetaData TRADE: {root} {expiration} "
                f"${strike_dollars} {right} "
                f"price={event['price']} size={event['size']}"
            )
            self._update_running_stats(event)
            await self._emit_trade(event)

        else:
            logger.debug(f"ThetaData unknown message type: {msg_type}")

    # ── Auto-subscribe to 0DTE options ────────────────────────────────────

    async def subscribe_trades_per_contract(
        self,
        root: str,
        expiration: int,
        strikes: list[int],
        rights: list[str] = None,
    ):
        """
        Subscribe to option trade updates for specific contracts.
        Standard plan requires per-contract subscriptions (no wildcard).
        """
        if not self.ws or not self.connected:
            logger.warning("ThetaData WS not connected — cannot subscribe to trades")
            return

        rights = rights or ["C", "P"]
        count = 0
        for strike in strikes:
            strike_theta = int(strike * 1000)
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
                    "req_type": "TRADE",
                    "add": True,
                    "id": 0,
                    "contract": contract,
                }
                try:
                    await self.ws.send(json.dumps(msg))
                    count += 1
                except Exception as e:
                    logger.error(f"ThetaData subscribe_trades error: {e}")

        logger.info(
            f"ThetaData TRADE subscriptions sent: {root} {expiration} "
            f"{len(strikes)} strikes x {len(rights)} rights = {count} contracts"
        )

    async def auto_subscribe_0dte(self, root: str = "SPY"):
        """
        Subscribe to today's 0DTE option trades and quotes.

        Gets current SPY price, then subscribes to ±15 strikes
        for both trades and quotes on today's expiration.
        Standard plan: per-contract subscriptions (not wildcard).
        """
        today = int(datetime.now(self._ET).strftime("%Y%m%d"))

        logger.info(f"Auto-subscribing to 0DTE options: {root} exp={today}")

        # Get current price for ATM strikes
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                # Try local market endpoint first, then Alpaca snapshot
                price = 0
                try:
                    async with session.get("http://localhost:8000/api/market") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            price = data.get("spy", {}).get("price", 0)
                except Exception:
                    pass

                if price <= 0:
                    try:
                        from .config import cfg
                        async with session.get(
                            f"https://data.alpaca.markets/v2/stocks/{root}/snapshot",
                            headers=cfg.ALPACA_HEADERS,
                            timeout=aiohttp.ClientTimeout(total=3),
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                price = data.get("latestTrade", {}).get("p", 0)
                    except Exception:
                        pass

                if price > 0:
                    atm = round(price)
                    strikes = list(range(atm - 15, atm + 16))

                    await self.subscribe_trades_per_contract(
                        root, today, strikes, ["C", "P"]
                    )
                    await self.subscribe_quotes(
                        root, today, strikes, ["C", "P"]
                    )

                    logger.info(
                        f"0DTE auto-subscribe complete: {root} exp={today} "
                        f"strikes={atm-15}..{atm+15} "
                        f"({len(strikes)*2} trade + {len(strikes)*2} quote contracts)"
                    )
                else:
                    logger.warning(
                        f"Cannot determine ATM price for {root} 0DTE subscriptions"
                    )
        except Exception as e:
            logger.warning(f"Failed to auto-subscribe 0DTE: {e}")

    # ── Stats ────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return current streaming stats."""
        return {
            "quote_book_size": len(self._quote_book),
            "greeks_book_size": len(self._greeks_book),
            "underlying_price": self._underlying_price,
            "options_vpin": self._options_vpin.get_state().to_dict(),
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
