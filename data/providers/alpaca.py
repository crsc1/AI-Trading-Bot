"""
Alpaca Markets data provider.

Provides real-time and historical market data via Alpaca's Data API v2:
- Real-time stock quotes and trades (no 15-min delay on paper accounts)
- Historical OHLCV bars (minute, hour, day)
- Snapshots (latest trade, quote, minute bar in one call)
- Multi-symbol batch quotes

Alpaca Data API docs: https://docs.alpaca.markets/reference/stocklatestquotes

NOTE: Alpaca uses a SEPARATE base URL for market data (data.alpaca.markets)
      vs trading (paper-api.alpaca.markets). This provider uses the data API.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from data.providers.base import BaseDataProvider

logger = logging.getLogger(__name__)


class AlpacaDataProvider(BaseDataProvider):
    """
    Alpaca Markets API client for real-time and historical market data.

    Authentication: Uses APCA-API-KEY-ID and APCA-API-SECRET-KEY headers.
    Rate limits: 200 requests/minute on free tier.
    """

    # Alpaca data API (same for paper and live)
    BASE_URL = "https://data.alpaca.markets"
    DEFAULT_RATE_LIMIT = 3  # ~200/min = ~3.3/sec, stay safe

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize Alpaca data provider.

        Args:
            api_key: Alpaca API Key ID (APCA-API-KEY-ID)
            secret_key: Alpaca Secret Key (APCA-API-SECRET-KEY)
            **kwargs: Additional arguments passed to BaseDataProvider
        """
        super().__init__(api_key=api_key, **kwargs)
        self.secret_key = secret_key

        if not self.api_key or not self.secret_key:
            logger.warning(
                "Alpaca API key or secret not provided. Provider will not function."
            )

    async def _get_session(self):
        """
        Override to inject Alpaca auth headers into the session.
        """
        import aiohttp

        if self._session is None or self._session.closed:
            headers = {
                "APCA-API-KEY-ID": self.api_key or "",
                "APCA-API-SECRET-KEY": self.secret_key or "",
                "Accept": "application/json",
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def fetch_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch the latest quote for a symbol.

        Uses Alpaca's /v2/stocks/{symbol}/quotes/latest endpoint.

        Args:
            symbol: Ticker symbol (e.g., 'SPY')

        Returns:
            Dict with price, bid, ask, volume, timestamp
        """
        if not self.api_key or not self.secret_key:
            logger.error("Cannot fetch quote: Alpaca credentials not set")
            return {}

        try:
            response = await self._request(
                "GET",
                f"/v2/stocks/{symbol}/quotes/latest",
                params={"feed": os.environ.get("ALPACA_DATA_FEED", "sip")},  # IEX is free, SIP requires paid plan
                use_cache=False,
            )

            if "quote" in response:
                q = response["quote"]
                bid = q.get("bp", 0)
                ask = q.get("ap", 0)
                mid = (bid + ask) / 2 if bid and ask else bid or ask

                return {
                    "symbol": symbol,
                    "price": mid,
                    "bid": bid,
                    "ask": ask,
                    "bid_size": q.get("bs", 0),
                    "ask_size": q.get("as", 0),
                    "timestamp": q.get("t", ""),
                    "source": "alpaca",
                }

            logger.warning(f"No quote data for {symbol} from Alpaca")
            return {}

        except Exception as e:
            logger.error(f"Error fetching Alpaca quote for {symbol}: {e}")
            return {}

    async def fetch_latest_trade(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch the latest trade for a symbol.

        Args:
            symbol: Ticker symbol (e.g., 'SPY')

        Returns:
            Dict with price, size, timestamp, exchange
        """
        if not self.api_key or not self.secret_key:
            return {}

        try:
            response = await self._request(
                "GET",
                f"/v2/stocks/{symbol}/trades/latest",
                params={"feed": os.environ.get("ALPACA_DATA_FEED", "sip")},
                use_cache=False,
            )

            if "trade" in response:
                t = response["trade"]
                return {
                    "symbol": symbol,
                    "price": t.get("p", 0),
                    "size": t.get("s", 0),
                    "timestamp": t.get("t", ""),
                    "exchange": t.get("x", ""),
                    "source": "alpaca",
                }

            return {}

        except Exception as e:
            logger.error(f"Error fetching Alpaca trade for {symbol}: {e}")
            return {}

    async def fetch_snapshot(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch a full snapshot for a symbol (latest trade, quote, and minute bar).

        This is the most efficient single call for getting current market state.

        Args:
            symbol: Ticker symbol (e.g., 'SPY')

        Returns:
            Dict with latest trade, quote, minute bar, daily bar, prev daily bar
        """
        if not self.api_key or not self.secret_key:
            return {}

        try:
            response = await self._request(
                "GET",
                f"/v2/stocks/{symbol}/snapshot",
                params={"feed": os.environ.get("ALPACA_DATA_FEED", "sip")},
                use_cache=False,
            )

            if not response:
                return {}

            result = {"symbol": symbol, "source": "alpaca"}

            # Latest trade
            if "latestTrade" in response:
                t = response["latestTrade"]
                result["last_trade"] = {
                    "price": t.get("p", 0),
                    "size": t.get("s", 0),
                    "timestamp": t.get("t", ""),
                }

            # Latest quote
            if "latestQuote" in response:
                q = response["latestQuote"]
                result["last_quote"] = {
                    "bid": q.get("bp", 0),
                    "ask": q.get("ap", 0),
                    "bid_size": q.get("bs", 0),
                    "ask_size": q.get("as", 0),
                }

            # Minute bar
            if "minuteBar" in response:
                bar = response["minuteBar"]
                result["minute_bar"] = {
                    "open": bar.get("o", 0),
                    "high": bar.get("h", 0),
                    "low": bar.get("l", 0),
                    "close": bar.get("c", 0),
                    "volume": bar.get("v", 0),
                    "timestamp": bar.get("t", ""),
                }

            # Daily bar
            if "dailyBar" in response:
                bar = response["dailyBar"]
                result["daily_bar"] = {
                    "open": bar.get("o", 0),
                    "high": bar.get("h", 0),
                    "low": bar.get("l", 0),
                    "close": bar.get("c", 0),
                    "volume": bar.get("v", 0),
                    "timestamp": bar.get("t", ""),
                }

            # Previous daily bar
            if "prevDailyBar" in response:
                bar = response["prevDailyBar"]
                result["prev_daily_bar"] = {
                    "open": bar.get("o", 0),
                    "high": bar.get("h", 0),
                    "low": bar.get("l", 0),
                    "close": bar.get("c", 0),
                    "volume": bar.get("v", 0),
                    "timestamp": bar.get("t", ""),
                }

            return result

        except Exception as e:
            logger.error(f"Error fetching Alpaca snapshot for {symbol}: {e}")
            return {}

    async def fetch_multi_snapshot(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Fetch snapshots for multiple symbols in one call.

        Args:
            symbols: List of ticker symbols (e.g., ['SPY', 'QQQ', 'IWM'])

        Returns:
            Dict keyed by symbol, each containing snapshot data
        """
        if not self.api_key or not self.secret_key:
            return {}

        try:
            response = await self._request(
                "GET",
                "/v2/stocks/snapshots",
                params={
                    "symbols": ",".join(symbols),
                    "feed": os.environ.get("ALPACA_DATA_FEED", "sip"),
                },
                use_cache=False,
            )

            results = {}
            for sym, data in response.items():
                results[sym] = {
                    "symbol": sym,
                    "source": "alpaca",
                }

                if "latestTrade" in data:
                    t = data["latestTrade"]
                    results[sym]["price"] = t.get("p", 0)
                    results[sym]["timestamp"] = t.get("t", "")

                if "latestQuote" in data:
                    q = data["latestQuote"]
                    results[sym]["bid"] = q.get("bp", 0)
                    results[sym]["ask"] = q.get("ap", 0)

                if "dailyBar" in data:
                    bar = data["dailyBar"]
                    results[sym]["open"] = bar.get("o", 0)
                    results[sym]["high"] = bar.get("h", 0)
                    results[sym]["low"] = bar.get("l", 0)
                    results[sym]["close"] = bar.get("c", 0)
                    results[sym]["volume"] = bar.get("v", 0)

                if "prevDailyBar" in data:
                    prev = data["prevDailyBar"]
                    prev_close = prev.get("c", 0)
                    curr_price = results[sym].get("price", 0)
                    if prev_close and curr_price:
                        change = curr_price - prev_close
                        change_pct = (change / prev_close) * 100
                        results[sym]["change"] = round(change, 2)
                        results[sym]["change_percent"] = round(change_pct, 2)
                        results[sym]["prev_close"] = prev_close

            return results

        except Exception as e:
            logger.error(f"Error fetching Alpaca multi-snapshot: {e}")
            return {}

    async def fetch_historical_bars(
        self,
        symbol: str,
        timeframe: str = "1Min",
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical OHLCV bars.

        Args:
            symbol: Ticker symbol (e.g., 'SPY')
            timeframe: Bar timeframe ('1Min', '5Min', '15Min', '1Hour', '1Day')
            start: Start time (RFC3339 or YYYY-MM-DD)
            end: End time (RFC3339 or YYYY-MM-DD)
            limit: Maximum bars to return (max 10000)

        Returns:
            List of OHLCV bar dicts
        """
        if not self.api_key or not self.secret_key:
            return []

        if not start:
            start = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

        params = {
            "timeframe": timeframe,
            "start": start,
            "limit": limit,
            "feed": os.environ.get("ALPACA_DATA_FEED", "sip"),
            "adjustment": "split",
        }
        if end:
            params["end"] = end

        try:
            response = await self._request(
                "GET",
                f"/v2/stocks/{symbol}/bars",
                params=params,
                use_cache=True,
            )

            bars = []
            if "bars" in response and response["bars"]:
                for bar in response["bars"]:
                    bars.append({
                        "timestamp": bar.get("t"),
                        "open": bar.get("o"),
                        "high": bar.get("h"),
                        "low": bar.get("l"),
                        "close": bar.get("c"),
                        "volume": bar.get("v"),
                        "vwap": bar.get("vw"),
                        "trade_count": bar.get("n"),
                    })

            logger.info(f"Fetched {len(bars)} {timeframe} bars for {symbol} from Alpaca")
            return bars

        except Exception as e:
            logger.error(f"Error fetching Alpaca bars for {symbol}: {e}")
            return []
