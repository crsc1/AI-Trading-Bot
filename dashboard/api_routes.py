"""
REST API routes for the trading dashboard.

Data sources:
  OPTIONS:  ThetaData Standard (SOLE source — quotes, OI, OHLC via OPRA)
            Greeks (delta/theta/vega/rho/IV) from ThetaData first_order endpoint.
            Local Black-Scholes fallback only for gamma (requires Pro greeks/all).
            Alpaca is emergency fallback ONLY if ThetaData Terminal is down.
  EQUITIES: Alpaca Algo Trader Plus — SIP real-time trades, quotes, bars.
  FLOW:     Flow Engine (Rust) — live tick streaming via Alpaca SIP WebSocket.
"""

from fastapi import APIRouter, Query
from datetime import datetime, timedelta
from typing import Optional
import json as _json
import logging
import aiohttp
import os
import re

from .config import cfg

logger = logging.getLogger(__name__)
router = APIRouter()

THETA_BASE = cfg.THETA_BASE_URL
THETA_V2_BASE = cfg.THETA_V2_BASE_URL
ENGINE_BASE = cfg.FLOW_ENGINE_HTTP_URL

# Alpaca API config
ALPACA_DATA_URL = cfg.ALPACA_DATA_URL
ALPACA_TRADING_URL = cfg.ALPACA_BASE_URL
ALPACA_KEY = cfg.ALPACA_API_KEY
ALPACA_SECRET = cfg.ALPACA_SECRET_KEY
ALPACA_HEADERS = cfg.ALPACA_HEADERS


# ============================================================================
# THETADATA CONNECTION STATE — health tracking for diagnostics
# ============================================================================

import asyncio as _asyncio
import time as _time

_theta_health = {
    "last_success": 0.0,
    "last_failure": 0.0,
    "consecutive_failures": 0,
    "total_requests": 0,
    "total_failures": 0,
    "status": "unknown",  # "healthy", "degraded", "down", "unknown"
}


async def _theta_fetch_with_retry(
    url: str,
    params: dict = None,
    max_retries: int = None,
    base_timeout: float = None,
    backoff_factor: float = None,
) -> dict:
    if max_retries is None:
        max_retries = cfg.THETA_RETRY_MAX
    if base_timeout is None:
        base_timeout = cfg.THETA_RETRY_BASE_TIMEOUT
    if backoff_factor is None:
        backoff_factor = cfg.THETA_RETRY_BACKOFF
    """
    Fetch from ThetaData with exponential backoff retry.

    Handles: connection refused, timeouts, 5xx errors.
    Returns parsed JSON on success, empty dict on all retries exhausted.
    Updates _theta_health for diagnostics.
    """
    _theta_health["total_requests"] += 1
    last_err = None

    for attempt in range(max_retries):
        timeout = base_timeout * (backoff_factor ** attempt)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        try:
                            data = _json.loads(text)
                        except _json.JSONDecodeError:
                            # Some endpoints (e.g. list/expirations) return text/csv.
                            # Parse: newline or comma-separated integers.
                            items = []
                            for part in text.replace(",", "\n").split("\n"):
                                part = part.strip()
                                if part.isdigit():
                                    items.append(int(part))
                            data = {"response": items} if items else {}
                            logger.debug(
                                f"[ThetaData] Parsed {len(items)} CSV items from {url}"
                            )
                        _theta_health["last_success"] = _time.time()
                        _theta_health["consecutive_failures"] = 0
                        _theta_health["status"] = "healthy"
                        return data
                    elif resp.status >= 500:
                        last_err = f"HTTP {resp.status}"
                        logger.debug(
                            f"ThetaData {resp.status} (attempt {attempt+1}/{max_retries}): {url}"
                        )
                    else:
                        # 4xx = client error, don't retry
                        body = (await resp.text())[:200]
                        logger.debug(f"ThetaData {resp.status}: {body}")
                        _theta_health["last_failure"] = _time.time()
                        _theta_health["total_failures"] += 1
                        return {}
        except (aiohttp.ClientConnectorError, aiohttp.ClientOSError) as e:
            last_err = f"Connection refused: {e}"
            logger.debug(
                f"ThetaData connection failed (attempt {attempt+1}/{max_retries}): {e}"
            )
        except _asyncio.TimeoutError:
            last_err = f"Timeout after {timeout:.1f}s"
            logger.debug(
                f"ThetaData timeout {timeout:.1f}s (attempt {attempt+1}/{max_retries}): {url}"
            )
        except Exception as e:
            last_err = str(e)
            logger.debug(f"ThetaData fetch error (attempt {attempt+1}/{max_retries}): {e}")

        # Backoff before retry (skip on last attempt)
        if attempt < max_retries - 1:
            delay = 0.5 * (backoff_factor ** attempt)
            await _asyncio.sleep(delay)

    # All retries exhausted
    _theta_health["last_failure"] = _time.time()
    _theta_health["consecutive_failures"] += 1
    _theta_health["total_failures"] += 1

    if _theta_health["consecutive_failures"] >= cfg.THETA_HEALTH_DOWN_AFTER:
        _theta_health["status"] = "down"
    elif _theta_health["consecutive_failures"] >= cfg.THETA_HEALTH_DEGRADED_AFTER:
        _theta_health["status"] = "degraded"

    # Only log at WARNING level (not ERROR) — ThetaData being down is an expected scenario
    # when Terminal isn't running. The health endpoint tracks this state for monitoring.
    if _theta_health["consecutive_failures"] <= 1:
        logger.warning(f"ThetaData unreachable ({max_retries} retries): {last_err}")
    else:
        logger.debug(f"ThetaData still down ({_theta_health['consecutive_failures']} consecutive): {last_err}")
    return {}


# ============================================================================
# HELPERS
# ============================================================================

def _parse_option_symbol(sym: str) -> dict:
    """
    Parse OCC option symbol: SPY250328C00570000
    Format: ROOT + YYMMDD + C/P + STRIKE*1000 (8 digits)
    """
    m = re.match(r'^([A-Z]+)(\d{6})([CP])(\d{8})$', sym)
    if not m:
        return {}
    root, date_str, right, strike_raw = m.groups()
    exp = f"20{date_str[:2]}-{date_str[2:4]}-{date_str[4:6]}"
    strike = int(strike_raw) / 1000.0
    return {"root": root, "expiration": exp, "right": right, "strike": strike}


# ============================================================================
# MARKET DATA — live price (Alpaca primary, any stock)
# ============================================================================

@router.get("/market")
async def get_market_snapshot(symbol: str = Query("SPY")):
    """
    Get current price for any stock. Priority:
      1. Flow Engine (live Alpaca SIP ticks)
      2. Alpaca snapshot (direct REST — works even without engine)
      3. ThetaData EOD (last resort, SPY only)
    """
    result = {"spy": None}

    # 1. Live price from flow engine (only for the engine's configured symbol)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{ENGINE_BASE}/stats",
                timeout=aiohttp.ClientTimeout(total=2),
            ) as resp:
                if resp.status == 200:
                    stats = await resp.json()
                    price = stats.get("last_price", 0)
                    if price > 0:
                        result["spy"] = {
                            "symbol": symbol,
                            "price": round(price, 2),
                            "change": 0,
                            "change_percent": 0,
                            "prev_close": 0,
                            "timestamp": datetime.now().isoformat(),
                            "source": stats.get("data_source", "engine"),
                            "ticks": stats.get("ticks_processed", 0),
                        }
    except Exception as e:
        logger.debug(f"Engine stats failed: {e}")

    # 2. Alpaca snapshot — works for ANY stock, gives latest trade + prev close + bid/ask
    if not result["spy"] and ALPACA_KEY:
        try:
            url = f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/snapshot?feed=sip"
            async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        snap = await resp.json()
                        lt = snap.get("latestTrade", {})
                        price = lt.get("p", 0)
                        prev = snap.get("prevDailyBar", {}).get("c", 0)
                        if price > 0:
                            chg = round(price - prev, 2) if prev else 0
                            result["spy"] = {
                                "symbol": symbol,
                                "price": round(price, 2),
                                "change": chg,
                                "change_percent": round((chg / prev) * 100, 2) if prev else 0,
                                "prev_close": prev,
                                "timestamp": lt.get("t", datetime.now().isoformat()),
                                "source": "alpaca_sip",
                                "bid": snap.get("latestQuote", {}).get("bp", 0),
                                "ask": snap.get("latestQuote", {}).get("ap", 0),
                                "bid_size": snap.get("latestQuote", {}).get("bs", 0),
                                "ask_size": snap.get("latestQuote", {}).get("as", 0),
                            }
                    elif resp.status == 403:
                        # SIP not available, try IEX
                        url2 = f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/snapshot?feed=iex"
                        async with session.get(url2, timeout=aiohttp.ClientTimeout(total=3)) as resp2:
                            if resp2.status == 200:
                                snap = await resp2.json()
                                lt = snap.get("latestTrade", {})
                                price = lt.get("p", 0)
                                prev = snap.get("prevDailyBar", {}).get("c", 0)
                                if price > 0:
                                    chg = round(price - prev, 2) if prev else 0
                                    result["spy"] = {
                                        "symbol": symbol,
                                        "price": round(price, 2),
                                        "change": chg,
                                        "change_percent": round((chg / prev) * 100, 2) if prev else 0,
                                        "prev_close": prev,
                                        "timestamp": lt.get("t", datetime.now().isoformat()),
                                        "source": "alpaca_iex",
                                    }
        except Exception as e:
            logger.debug(f"Alpaca snapshot failed: {e}")

    # 3. ThetaData EOD removed — requires STOCK subscription we don't have.
    #    OPTION.STANDARD only covers options endpoints.
    #    If Alpaca also fails, we return no data.

    if not result["spy"]:
        result["error"] = "No data — check Alpaca keys and symbol"

    return result


@router.get("/quote")
async def get_live_quote(symbol: str = Query("SPY"), feed: str = Query("sip")):
    """
    Get real-time NBBO quote from Alpaca SIP for ANY stock.
    """
    if not ALPACA_KEY:
        return {"error": "ALPACA_API_KEY not configured"}

    try:
        url = f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/quotes/latest?feed={feed}"
        async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 403 and feed == "sip":
                    url2 = f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/quotes/latest?feed=iex"
                    async with session.get(url2, timeout=aiohttp.ClientTimeout(total=3)) as resp2:
                        if resp2.status != 200:
                            return {"error": f"Alpaca {resp2.status}"}
                        data = await resp2.json()
                        feed = "iex"
                elif resp.status != 200:
                    return {"error": f"Alpaca {resp.status}"}
                else:
                    data = await resp.json()

                q = data.get("quote", {})
                bid = q.get("bp", 0)
                ask = q.get("ap", 0)
                mid = round((bid + ask) / 2, 4) if bid and ask else 0
                spread = round(ask - bid, 4) if bid and ask else 0
                return {
                    "symbol": symbol,
                    "bid": bid, "ask": ask,
                    "bid_size": q.get("bs", 0), "ask_size": q.get("as", 0),
                    "midpoint": mid, "spread": spread,
                    "timestamp": q.get("t", ""),
                    "source": f"alpaca_{feed}",
                }
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# HISTORICAL BARS — Alpaca primary (any stock, any timeframe)
# ============================================================================

@router.get("/bars")
async def get_historical_bars(
    symbol: str = Query("SPY"),
    timeframe: str = Query("1D", description="1Min, 5Min, 15Min, 1H, 1D"),
    limit: int = Query(365, ge=1, le=5000),
    feed: str = Query("sip"),
    indicators: Optional[str] = Query(None, description="Comma-separated indicators, e.g. ema21,sma50,rsi14,atr14"),
):
    """
    Fetch OHLCV bars from Alpaca for ANY stock.
    Supports all intraday timeframes with Algo Trader Plus.
    Optional ?indicators= param appends server-computed indicator values.
    """
    bars = await _fetch_alpaca_bars(symbol, timeframe, limit, feed)
    if bars is None:
        # Fallback to ThetaData EOD (only daily)
        if timeframe in ("1D", "1Day", "day"):
            bars = await _fetch_theta_eod_bars(symbol, limit)
        else:
            return {"bars": [], "error": f"No data for {symbol} {timeframe}. Check Alpaca subscription."}

    if indicators and bars and bars.get("bars"):
        bars["indicators"] = _compute_bar_indicators(bars["bars"], indicators)

    return bars


async def _fetch_alpaca_bars(symbol: str, timeframe: str, limit: int, feed: str):
    """Fetch bars from Alpaca Market Data API v2 for any stock."""
    if not ALPACA_KEY or not ALPACA_SECRET:
        return None

    tf_map = {
        "1Min": "1Min", "5Min": "5Min", "15Min": "15Min",
        "1H": "1Hour", "1D": "1Day",
        "1Hour": "1Hour", "1Day": "1Day", "day": "1Day",
    }
    alpaca_tf = tf_map.get(timeframe, timeframe)

    # Calculate start date — tight window to avoid fetching weeks of data
    if alpaca_tf == "1Day":
        start_dt = datetime.now() - timedelta(days=min(limit * 2, 730))
    elif alpaca_tf == "1Hour":
        start_dt = datetime.now() - timedelta(days=min(limit // 7 + 3, 60))
    elif alpaca_tf == "15Min":
        start_dt = datetime.now() - timedelta(days=min(limit // 26 + 2, 30))
    elif alpaca_tf == "5Min":
        start_dt = datetime.now() - timedelta(days=min(limit // 78 + 2, 14))
    else:  # 1Min
        start_dt = datetime.now() - timedelta(days=min(limit // 390 + 2, 7))

    start = start_dt.strftime("%Y-%m-%dT00:00:00Z")

    try:
        url = f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/bars"
        params = {
            "timeframe": alpaca_tf,
            "start": start,
            "feed": feed,
            "limit": min(limit, 10000),
            "adjustment": "all",  # Include both split AND dividend adjustments
            "sort": "desc",  # Newest first — ensures we always get the most recent bars
        }
        async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 403 and feed == "sip":
                    params["feed"] = "iex"
                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp2:
                        if resp2.status != 200:
                            return None
                        data = await resp2.json()
                        feed = "iex"
                elif resp.status != 200:
                    return None
                else:
                    data = await resp.json()

                bars = data.get("bars", [])
                if not bars:
                    return None

                formatted = []
                for bar in bars:
                    ts = bar.get("t", "")
                    if not ts:
                        continue
                    if alpaca_tf == "1Day":
                        time_val = ts[:10]
                    else:
                        try:
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            time_val = int(dt.timestamp())
                        except Exception:
                            continue

                    formatted.append({
                        "time": time_val,
                        "open": bar["o"], "high": bar["h"],
                        "low": bar["l"], "close": bar["c"],
                        "volume": bar.get("v", 0),
                        "vwap": bar.get("vw", 0),
                        "trade_count": bar.get("n", 0),
                    })

                # Reverse to ascending order (API returns desc for freshness)
                formatted.reverse()

                if len(formatted) > limit:
                    formatted = formatted[-limit:]

                return {
                    "bars": formatted, "symbol": symbol,
                    "timeframe": timeframe, "source": f"alpaca_{feed}",
                    "count": len(formatted),
                }
    except Exception as e:
        logger.debug(f"Alpaca bars failed: {e}")
        return None


async def _fetch_theta_eod_bars(symbol: str, limit: int):
    """ThetaData EOD bars — DISABLED. Requires STOCK subscription we don't have.
    OPTION.STANDARD only covers /v3/option/* endpoints.
    Use Alpaca for all stock/bar data instead."""
    logger.debug("[api_routes] _fetch_theta_eod_bars skipped — no STOCK subscription")
    return {"bars": [], "error": "ThetaData stock endpoints disabled (OPTION.STANDARD only)"}


def _compute_bar_indicators(bars: list, indicators_str: str) -> dict:
    """Compute requested indicators from bar data.

    Args:
        bars: List of bar dicts with open/high/low/close/volume keys.
        indicators_str: Comma-separated indicator specs, e.g. "ema21,sma50,rsi14,atr14"

    Returns:
        Dict mapping indicator name to list of values (same length as bars, None-padded).
    """
    import re as _re

    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    n = len(closes)
    result = {}

    for spec in indicators_str.split(","):
        spec = spec.strip().lower()
        m = _re.match(r"(ema|sma|rsi|atr)(\d+)", spec)
        if not m:
            continue
        kind, period = m.group(1), int(m.group(2))
        if period < 1 or period > 500:
            continue

        if kind == "ema":
            vals = _calc_ema(closes, period)
        elif kind == "sma":
            vals = _calc_sma(closes, period)
        elif kind == "rsi":
            vals = _calc_rsi(closes, period)
        elif kind == "atr":
            vals = _calc_atr(highs, lows, closes, period)
        else:
            continue

        # Pad to match bar count (None for bars where indicator isn't computed yet)
        padded = [None] * (n - len(vals)) + vals
        result[spec] = [round(v, 4) if v is not None else None for v in padded]

    return result


def _calc_ema(data: list, period: int) -> list:
    if len(data) < period:
        return []
    k = 2 / (period + 1)
    ema = [sum(data[:period]) / period]
    for i in range(period, len(data)):
        ema.append(data[i] * k + ema[-1] * (1 - k))
    return ema


def _calc_sma(data: list, period: int) -> list:
    if len(data) < period:
        return []
    result = []
    s = sum(data[:period])
    result.append(s / period)
    for i in range(period, len(data)):
        s += data[i] - data[i - period]
        result.append(s / period)
    return result


def _calc_rsi(data: list, period: int) -> list:
    if len(data) < period + 1:
        return []
    avg_gain = avg_loss = 0.0
    for i in range(1, period + 1):
        d = data[i] - data[i - 1]
        if d > 0:
            avg_gain += d
        else:
            avg_loss -= d
    avg_gain /= period
    avg_loss /= period
    result = [100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)]
    for i in range(period + 1, len(data)):
        d = data[i] - data[i - 1]
        avg_gain = (avg_gain * (period - 1) + (d if d > 0 else 0)) / period
        avg_loss = (avg_loss * (period - 1) + (-d if d < 0 else 0)) / period
        result.append(100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss))
    return result


def _calc_atr(highs: list, lows: list, closes: list, period: int) -> list:
    if len(closes) < 2:
        return []
    tr = []
    for i in range(1, len(closes)):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    if len(tr) < period:
        return []
    atr = sum(tr[:period]) / period
    result = [atr]
    for i in range(period, len(tr)):
        atr = (atr * (period - 1) + tr[i]) / period
        result.append(atr)
    return result


# ============================================================================
# ENGINE STATUS
# ============================================================================

@router.get("/status")
async def get_bot_status():
    """Get engine connection status."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ENGINE_BASE}/health", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                if resp.status == 200:
                    h = await resp.json()
                    return {"running": h.get("engine_running", False), "data_source": h.get("data_source", "unknown")}
    except Exception:
        pass
    return {"running": False, "data_source": "disconnected"}


# ============================================================================
# OPTIONS — ThetaData primary (Standard plan: quotes, OI, OHLC via OPRA)
#            Alpaca = emergency fallback only
# ============================================================================

_exp_cache: dict = {"data": None, "symbol": None, "expires": 0}


@router.get("/data/health")
async def get_data_health():
    """
    Data source health check — shows connection status for ThetaData, Alpaca, and Engine.
    Poll this from the dashboard to show connection indicators.
    """
    theta_status = dict(_theta_health)

    # Quick ThetaData ping — use OPTIONS endpoint, NOT stock (we only have OPTION.STANDARD)
    theta_reachable = False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{THETA_BASE}/v3/option/list/expirations",
                params={"symbol": "SPY"},
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                theta_reachable = resp.status == 200
                if theta_reachable:
                    theta_status["status"] = "healthy"
                    theta_status["last_success"] = _time.time()
                    theta_status["consecutive_failures"] = 0
    except Exception:
        theta_reachable = False
        theta_status["status"] = "down" if theta_status["consecutive_failures"] >= 3 else "degraded"

    # Alpaca connectivity
    alpaca_reachable = False
    if ALPACA_KEY:
        try:
            async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
                async with session.get(
                    f"{ALPACA_TRADING_URL}/account",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    alpaca_reachable = resp.status == 200
        except Exception:
            pass

    # Rust engine connectivity
    engine_reachable = False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{ENGINE_BASE}/stats",
                timeout=aiohttp.ClientTimeout(total=2),
            ) as resp:
                engine_reachable = resp.status == 200
    except Exception:
        pass

    return {
        "thetadata": {
            "reachable": theta_reachable,
            **theta_status,
        },
        "alpaca": {
            "reachable": alpaca_reachable,
            "has_credentials": bool(ALPACA_KEY),
        },
        "engine": {
            "reachable": engine_reachable,
        },
    }


@router.get("/options/expirations")
async def get_options_expirations(root: str = Query("SPY")):
    """
    List option expiration dates. ThetaData first, Alpaca fallback.
    """
    import time as _time
    now = _time.time()

    if _exp_cache["symbol"] == root and _exp_cache["data"] and now < _exp_cache["expires"]:
        return _exp_cache["data"]

    # 1. ThetaData v3 — primary source
    # Endpoint: /v3/option/list/expirations  param: "symbol" (v3 REST API)
    # Returns: {"response": [[20260331, 20260401, ...]] or [20260331, 20260401, ...]}
    # Dates are YYYYMMDD integers — convert to YYYY-MM-DD strings
    data = await _theta_fetch_with_retry(
        f"{THETA_BASE}/v3/option/list/expirations",
        params={"symbol": root},
        max_retries=3,
        base_timeout=5.0,
    )
    if data and data.get("response"):
        result_dates = []
        for row in data["response"]:
            if isinstance(row, list):
                for d in row:
                    ds = str(d).strip()
                    if len(ds) == 8 and ds.isdigit():
                        result_dates.append(f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}")
            elif isinstance(row, (int, float)):
                ds = str(int(row))
                if len(ds) == 8:
                    result_dates.append(f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}")
            elif isinstance(row, str) and len(row.strip()) == 8:
                ds = row.strip()
                result_dates.append(f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}")
        if result_dates:
            result = {"root": root, "expirations": sorted(result_dates), "source": "thetadata"}
            _exp_cache.update({"data": result, "symbol": root, "expires": now + 300})
            return result

    # 2. Fallback: Alpaca contracts API (only if ThetaData is down)
    # NOTE: Alpaca caps at 100 contracts per page. SPY has 500+ strikes per exp,
    # so fetching all contracts is very slow. Filter to a single ATM strike
    # to efficiently get just the unique expiration dates.
    if ALPACA_KEY:
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            far_date = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
            url = f"{ALPACA_TRADING_URL}/options/contracts"

            # Get current price to find ATM strike
            atm_strike = None
            try:
                snap_url = f"{ALPACA_DATA_URL}/v2/stocks/{root}/snapshot?feed=sip"
                async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
                    async with session.get(snap_url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                        if resp.status == 200:
                            snap = await resp.json()
                            price = snap.get("latestTrade", {}).get("p", 0)
                            if price > 0:
                                step = 5 if price > 100 else 1
                                atm_strike = round(price / step) * step
            except Exception:
                pass

            params = {
                "underlying_symbols": root,
                "status": "active",
                "limit": 100,
                "type": "call",
                "expiration_date_gte": today,
                "expiration_date_lte": far_date,
            }
            if atm_strike:
                params["strike_price_gte"] = str(atm_strike)
                params["strike_price_lte"] = str(atm_strike)

            exps = set()
            async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
                for _ in range(20):
                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status != 200:
                            break
                        data = await resp.json()
                        for c in data.get("option_contracts", []):
                            exp = c.get("expiration_date", "")
                            if exp:
                                exps.add(exp)
                        npt = data.get("next_page_token")
                        if not npt:
                            break
                        params["page_token"] = npt

            if exps:
                logger.warning("Using Alpaca fallback for expirations — ThetaData unavailable")
                result = {"root": root, "expirations": sorted(list(exps)), "source": "alpaca_fallback"}
                _exp_cache.update({"data": result, "symbol": root, "expires": now + 300})
                return result
        except Exception as e:
            logger.debug(f"Alpaca contracts API also failed: {e}")

    return {"root": root, "expirations": [], "error": "No expiration data available"}


@router.get("/options/chain")
async def get_options_chain(
    root: str = Query("SPY"),
    exp: str = Query(..., description="YYYY-MM-DD"),
    right: Optional[str] = Query(None, description="C or P"),
):
    """
    Options chain — ThetaData is the sole options data source.
    Provides: Greeks, IV, OI, bid/ask quotes, OHLC, tick-level OPRA data.
    Alpaca is only used as emergency fallback if ThetaData Terminal is down.
    """
    # 1. ThetaData — complete options data (Greeks, IV, OI, quotes, OHLC)
    try:
        theta_chain = await _fetch_theta_chain(root, exp, right)
        if theta_chain and not theta_chain.get("error") and (theta_chain.get("calls") or theta_chain.get("puts")):
            return theta_chain
    except Exception as e:
        logger.warning(f"ThetaData chain failed: {e}")

    # 2. Emergency fallback: Alpaca (only if ThetaData is completely unavailable)
    if ALPACA_KEY:
        try:
            alpaca_chain = await _fetch_alpaca_chain(root, exp, right)
            if alpaca_chain and (alpaca_chain.get("calls") or alpaca_chain.get("puts")):
                alpaca_chain["source"] = "alpaca_fallback"
                logger.warning("Using Alpaca fallback for options chain — ThetaData unavailable")
                return alpaca_chain
        except Exception as e:
            logger.debug(f"Alpaca fallback also failed: {e}")

    return {"root": root, "expiration": exp, "calls": [], "puts": [],
            "error": "No options data available", "source": "none"}



async def _fetch_alpaca_chain(root: str, exp: str, right: Optional[str]) -> dict:
    """
    Fetch options chain from Alpaca snapshots API (OPRA feed with Algo Trader Plus).

    Alpaca snapshot fields (verified from live API):
      latestQuote: {ap, as, ax, bp, bs, bx, c, t}  (ask/bid price/size)
      latestTrade: {c, p, s, t, x}                  (price, size)
      dailyBar: {c, h, l, n, o, t, v, vw}           (OHLCV)
      minuteBar: {c, h, l, n, o, t, v, vw}

    NOTE: Alpaca does NOT provide greeks or IV in option snapshots.
          Those come from ThetaData fallback when available.
    """
    url = f"{ALPACA_DATA_URL}/v1beta1/options/snapshots/{root}"
    params = {
        "feed": "opra",  # Use OPRA (Algo Trader Plus) for real-time options
        "limit": 500,
        "expiration_date": exp,
    }
    if right and isinstance(right, str) and right in ("C", "P"):
        params["type"] = "call" if right == "C" else "put"

    all_snapshots = {}

    try:
        async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
            for _ in range(10):
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 403:
                        # OPRA not available, fall back to indicative
                        logger.info("OPRA feed 403, falling back to indicative")
                        params["feed"] = "indicative"
                        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp2:
                            if resp2.status != 200:
                                return {}
                            data = await resp2.json()
                            all_snapshots.update(data.get("snapshots", {}))
                            npt = data.get("next_page_token")
                            if not npt:
                                break
                            params["page_token"] = npt
                            continue
                    if resp.status != 200:
                        logger.debug(f"Alpaca options snapshots {resp.status}: {(await resp.text())[:200]}")
                        return {}

                    data = await resp.json()
                    snapshots = data.get("snapshots", {})
                    all_snapshots.update(snapshots)

                    npt = data.get("next_page_token")
                    if not npt:
                        break
                    params["page_token"] = npt
    except Exception as e:
        logger.debug(f"Alpaca options fetch error: {e}")
        return {}

    if not all_snapshots:
        return {}

    # Also try to get OI from contracts API (snapshots don't include it)
    oi_map = {}
    try:
        contracts_url = f"{ALPACA_TRADING_URL}/options/contracts"
        c_params = {
            "underlying_symbols": root,
            "status": "active",
            "expiration_date": exp,
            "limit": 100,
        }
        async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
            for _ in range(10):
                async with session.get(contracts_url, params=c_params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        break
                    data = await resp.json()
                    for c in data.get("option_contracts", []):
                        sym = c.get("symbol", "")
                        oi = c.get("open_interest")
                        if sym and oi is not None:
                            oi_map[sym] = int(oi) if oi else 0
                    npt = data.get("next_page_token")
                    if not npt:
                        break
                    c_params["page_token"] = npt
    except Exception:
        pass  # OI is optional

    calls, puts = [], []
    for sym, snap in all_snapshots.items():
        parsed = _parse_option_symbol(sym)
        if not parsed:
            continue

        lq = snap.get("latestQuote", {})
        lt = snap.get("latestTrade", {})
        db = snap.get("dailyBar", {})
        greeks = snap.get("greeks", {}) or {}

        bid = lq.get("bp", 0) or 0
        ask = lq.get("ap", 0) or 0
        last = lt.get("p", 0) or 0
        mid = round((bid + ask) / 2, 2) if bid and ask else last

        entry = {
            "symbol": sym,
            "strike": parsed["strike"],
            "right": parsed["right"],
            "expiration": parsed["expiration"],
            "bid": bid,
            "ask": ask,
            "last": last,
            "mid": mid,
            "volume": db.get("v", 0) or 0,
            "open_interest": oi_map.get(sym, 0),
            # Alpaca Algo Trader Plus provides Greeks + IV in option snapshots
            "iv": snap.get("impliedVolatility") or greeks.get("iv"),
            "delta": greeks.get("delta"),
            "gamma": greeks.get("gamma"),
            "theta": greeks.get("theta"),
            "vega": greeks.get("vega"),
        }

        if parsed["right"] == "C":
            calls.append(entry)
        else:
            puts.append(entry)

    calls.sort(key=lambda x: x["strike"])
    puts.sort(key=lambda x: x["strike"])

    return {"root": root, "expiration": exp, "calls": calls, "puts": puts, "source": "alpaca_opra"}


async def _fetch_theta_chain(root: str, exp: str, right: Optional[str]) -> dict:
    """Primary: fetch options chain from ThetaData v3 API (Options Standard plan).

    Uses /v3/option/snapshot/greeks/first_order with strike_range — ONE API call
    instead of the old per-contract loop (strikes list + 60 parallel calls).

    Standard plan confirmed endpoints:
      - /v3/option/snapshot/greeks/first_order ✔ (delta/theta/vega/rho/IV + bid/ask)
      - /v3/option/snapshot/greeks/all ✘ (Pro only — has gamma, higher order)

    ThetaData v3 correct params (confirmed docs.thetadata.us):
      symbol (not root), expiration (YYYYMMDD), strike in dollars,
      right=call/put/both (not C/P), prices in dollars (no /100 needed)
    """
    # Map caller's right (C/P/None) to ThetaData v3 right format
    right_map = {"C": "call", "P": "put"}
    td_right = right_map.get(right, "both")

    # ThetaData v3 requires YYYYMMDD
    exp_td = exp.replace("-", "")

    # Get underlying price for context (used in logging; first_order returns it too)
    current_price = 0.0
    try:
        async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
            feed = os.environ.get("ALPACA_DATA_FEED", "iex")
            snap_url = f"{ALPACA_DATA_URL}/v2/stocks/{root}/quotes/latest?feed={feed}"
            async with session.get(snap_url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    snap = await resp.json()
                    q = snap.get("quote", {})
                    bp, ap = float(q.get("bp", 0)), float(q.get("ap", 0))
                    if bp > 0 and ap > 0:
                        current_price = (bp + ap) / 2
                    elif bp > 0:
                        current_price = bp
    except Exception:
        pass

    try:
        # ── Single call: first_order greeks with strike_range ──────────────
        # Standard plan endpoint. Returns ATM ±15 contracts for calls + puts
        # in one request: real delta/theta/vega/rho/IV + bid/ask/underlying_price
        data = await _theta_fetch_with_retry(
            f"{THETA_BASE}/v3/option/snapshot/greeks/first_order",
            params={
                "symbol": root,
                "expiration": exp_td,
                "right": td_right,
                "strike_range": cfg.THETA_STRIKE_RANGE,
                "format": "json",
            },
            max_retries=2,
            base_timeout=8.0,
        )

        raw_response = data.get("response") if data else None

        # ThetaData "no data" sentinels: None, [], or [[]] (one empty inner array)
        def _is_empty(r) -> bool:
            if not r:
                return True
            if isinstance(r, list) and len(r) == 1 and isinstance(r[0], list) and not r[0]:
                return True
            return False

        if not data or _is_empty(raw_response):
            if raw_response is not None:
                logger.info(
                    f"[ThetaChain] first_order: no live data for {root} exp={exp} "
                    f"(market closed / expiration expired or not-yet-active). "
                    f"Sentinel: {str(raw_response)[:80]}"
                )
            else:
                logger.warning(
                    f"[ThetaChain] No first_order response for {root} exp={exp}. "
                    f"Raw: {str(data)[:200]}"
                )
            return {"error": "No chain data (market closed or no live quotes)", "root": root, "calls": [], "puts": []}

        items = raw_response
        if not isinstance(items, list):
            items = [items] if items else []

        calls, puts = [], []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                # ThetaData first_order response is NESTED:
                #   item["contract"] = {"symbol": "SPY", "strike": 661.0,
                #                       "right": "PUT"/"CALL", "expiration": "2026-04-01"}
                #   item["data"]     = [{"underlying_price": 649.97, "delta": -1.0,
                #                        "implied_vol": ..., "theta": ..., "vega": ...,
                #                        "rho": ..., "bid": ..., "ask": ...}]
                contract = item.get("contract", {})
                data_arr = item.get("data", [])
                d = data_arr[0] if isinstance(data_arr, list) and data_arr else {}

                right_raw = str(contract.get("right", "")).upper()
                # "CALL" / "C" → "C",  "PUT" / "P" → "P"
                if right_raw in ("CALL", "C"):
                    right_letter = "C"
                elif right_raw in ("PUT", "P"):
                    right_letter = "P"
                else:
                    logger.debug(f"[ThetaChain] Unknown right '{right_raw}', skipping")
                    continue

                strike = float(contract.get("strike", 0))
                bid = float(d.get("bid", 0) or 0)
                ask = float(d.get("ask", 0) or 0)
                mid = round((bid + ask) / 2, 4) if (bid + ask) > 0 else bid

                resp_ul = d.get("underlying_price")
                if resp_ul and current_price == 0:
                    current_price = float(resp_ul)

                def _f(key):
                    v = d.get(key)
                    return float(v) if v is not None else None

                # Build OCC symbol: SPY250331C00570000
                try:
                    from datetime import datetime as _dt
                    _exp_dt = _dt.strptime(exp, "%Y-%m-%d")
                    _exp_str = _exp_dt.strftime("%y%m%d")
                    _strike_int = int(strike * 1000)
                    occ_sym = f"{root:<6}{_exp_str}{right_letter}{_strike_int:08d}"
                except Exception:
                    occ_sym = f"{root}{exp.replace('-', '')}{right_letter}{int(strike)}"

                entry = {
                    "symbol": occ_sym,
                    "strike": strike,
                    "right": right_letter,
                    "bid": bid, "ask": ask, "mid": mid, "last": mid,
                    "volume": 0,          # not in first_order
                    "open_interest": 0,
                    "iv": _f("implied_vol") or _f("implied_volatility"),
                    "delta": _f("delta"),
                    "gamma": None,        # Pro only (greeks/all)
                    "theta": _f("theta"),
                    "vega": _f("vega"),
                    "rho": _f("rho"),
                    "underlying_price": float(resp_ul) if resp_ul else current_price,
                    "timestamp": item.get("timestamp") or d.get("timestamp"),
                }

                if right_letter == "C":
                    calls.append(entry)
                else:
                    puts.append(entry)
            except (ValueError, TypeError, KeyError) as e:
                logger.debug(f"[ThetaChain] Skipping item ({e}): {str(item)[:100]}")
                continue

        calls.sort(key=lambda x: x["strike"])
        puts.sort(key=lambda x: x["strike"])

        if len(calls) == 0 and len(puts) == 0 and items:
            # Items were present but all filtered — log first item for diagnosis
            logger.warning(
                f"[ThetaChain] first_order: {len(items)} items received but all skipped. "
                f"First item type={type(items[0]).__name__}, value={str(items[0])[:150]}"
            )

        # ── Enrich with Open Interest from ThetaData snapshot ────────────────
        # The first_order endpoint does NOT include OI — we fetch it separately.
        # OI is essential for GEX/DEX calculations (Factors 3 & 4) and max pain.
        # OPRA reports OI ~06:30 ET daily — reflects prior day's close.
        oi_enriched = 0
        try:
            oi_data = await _theta_fetch_with_retry(
                f"{THETA_BASE}/v3/option/snapshot/open_interest",
                params={
                    "symbol": root,
                    "expiration": exp_td,
                    "right": "both",
                    "format": "json",
                },
                max_retries=1,
                base_timeout=5.0,
            )
            oi_response = oi_data.get("response") if oi_data else None
            if oi_response and isinstance(oi_response, list):
                # Build strike→OI lookup from response
                oi_map = {}
                for oi_item in oi_response:
                    if not isinstance(oi_item, dict):
                        continue
                    oi_contract = oi_item.get("contract", {})
                    oi_data_arr = oi_item.get("data", [])
                    oi_d = oi_data_arr[0] if isinstance(oi_data_arr, list) and oi_data_arr else {}
                    oi_strike = float(oi_contract.get("strike", 0))
                    oi_right = str(oi_contract.get("right", "")).upper()
                    oi_val = int(oi_d.get("open_interest", 0) or 0)
                    if oi_strike > 0 and oi_val > 0:
                        oi_map[(oi_strike, oi_right)] = oi_val

                # Apply to chain entries
                for c in calls:
                    oi = oi_map.get((c["strike"], "CALL"), 0) or oi_map.get((c["strike"], "C"), 0)
                    if oi > 0:
                        c["open_interest"] = oi
                        oi_enriched += 1
                for p in puts:
                    oi = oi_map.get((p["strike"], "PUT"), 0) or oi_map.get((p["strike"], "P"), 0)
                    if oi > 0:
                        p["open_interest"] = oi
                        oi_enriched += 1

                if oi_enriched:
                    logger.info(f"[ThetaChain] OI enriched: {oi_enriched} contracts from snapshot/open_interest")
        except Exception as e:
            logger.debug(f"[ThetaChain] OI enrichment failed (non-critical): {e}")

        logger.info(
            f"[ThetaChain] Built via first_order: {len(calls)} calls, "
            f"{len(puts)} puts for {root} exp={exp} ul={current_price:.2f}"
            f"{f' (OI: {oi_enriched} enriched)' if oi_enriched else ' (no OI data)'}"
        )

        return {
            "root": root, "expiration": exp,
            "calls": calls, "puts": puts,
            "underlying_price": current_price,
            "source": "thetadata",
        }

    except Exception as e:
        logger.error(f"[ThetaChain] Error building chain: {e}")
        return {"error": str(e), "root": root, "calls": [], "puts": []}


@router.get("/options/snapshot")
async def get_options_snapshot(root: str = Query("SPY"), exp: str = Query(...)):
    """P/C ratio, max pain, total volume."""
    chain = await get_options_chain(root=root, exp=exp, right=None)
    if "error" in chain and not chain.get("calls") and not chain.get("puts"):
        return chain
    calls, puts = chain.get("calls", []), chain.get("puts", [])
    tc = sum(c.get("volume", 0) or 0 for c in calls)
    tp = sum(p.get("volume", 0) or 0 for p in puts)
    mp = _calc_max_pain(calls, puts)
    return {
        "root": root, "expiration": chain.get("expiration"),
        "call_volume": tc, "put_volume": tp,
        "pc_ratio": round(tp / tc, 3) if tc else 0,
        "max_pain": mp,
        "source": chain.get("source", "unknown"),
    }


def _calc_max_pain(calls: list, puts: list) -> float:
    """
    Calculate max pain: the strike at which option holders lose the most money
    (i.e. total intrinsic value of all open contracts is minimized).
    For each candidate strike K:
      - call pain = sum of max(0, K - call_strike) * call_OI  (calls ITM)
      - put pain  = sum of max(0, put_strike - K) * put_OI   (puts ITM)
    Max pain = strike K that minimizes call_pain + put_pain.
    """
    call_oi = {c["strike"]: (c.get("open_interest", 0) or 0) for c in calls}
    put_oi = {p["strike"]: (p.get("open_interest", 0) or 0) for p in puts}
    strikes = sorted(set(call_oi.keys()) | set(put_oi.keys()))
    if not strikes:
        return 0

    min_pain = float("inf")
    best_strike = strikes[0]
    for k in strikes:
        pain = 0
        for s, oi in call_oi.items():
            if k > s:
                pain += (k - s) * oi
        for s, oi in put_oi.items():
            if k < s:
                pain += (s - k) * oi
        if pain < min_pain:
            min_pain = pain
            best_strike = k
    return best_strike


# ============================================================================
# SYMBOL SEARCH — Alpaca asset lookup (any stock)
# ============================================================================

_assets_cache: dict = {"data": None, "expires": 0}


@router.get("/search")
async def search_symbols(q: str = Query(..., min_length=1, max_length=10)):
    """Search for stock symbols via Alpaca assets API."""
    import time as _time
    now = _time.time()

    if not ALPACA_KEY:
        return {"results": []}

    # Cache all assets for 30 minutes (it's a large list but doesn't change often)
    if not _assets_cache["data"] or now > _assets_cache["expires"]:
        try:
            url = f"{ALPACA_TRADING_URL}/assets"
            params = {"status": "active", "asset_class": "us_equity"}
            async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        _assets_cache["data"] = await resp.json()
                        _assets_cache["expires"] = now + 1800
        except Exception as e:
            return {"results": [], "error": str(e)}

    if not _assets_cache["data"]:
        return {"results": []}

    q_upper = q.upper()
    matches = [
        {"symbol": a["symbol"], "name": a.get("name", ""), "exchange": a.get("exchange", "")}
        for a in _assets_cache["data"]
        if a.get("tradable") and (
            a["symbol"].startswith(q_upper) or q_upper in a.get("name", "").upper()[:50]
        )
    ][:20]

    return {"results": matches}


# ============================================================================
# IMPLIED VOLATILITY — ThetaData v2 historical IV
# ============================================================================

@router.get("/api/theta/iv/history")
async def get_iv_history(
    root: str = "SPY",
    exp: str = None,       # YYYYMMDD
    strike: float = None,  # dollars, we convert to 1/10th cent
    right: str = "C",
    start_date: str = None,  # YYYYMMDD
    end_date: str = None,    # YYYYMMDD
    interval: int = 60000,   # 1-minute default
):
    """
    Fetch historical implied volatility from ThetaData v2 API.

    Strike is in dollars (e.g. 170.0) — converted to 1/10th cent for the API.
    Dates default to last 30 days if not provided.
    """
    if not exp or strike is None:
        return {"error": "exp (YYYYMMDD) and strike (dollars) are required", "data": []}

    # Default date range: last 30 days
    today = datetime.now()
    if not end_date:
        end_date = today.strftime("%Y%m%d")
    if not start_date:
        start_date = (today - timedelta(days=30)).strftime("%Y%m%d")

    # Convert strike from dollars to 1/10th cent (multiply by 1000)
    strike_tenth_cent = int(strike * 1000)

    params = {
        "root": root,
        "exp": int(exp),
        "strike": strike_tenth_cent,
        "right": right.upper(),
        "start_date": int(start_date),
        "end_date": int(end_date),
        "ivl": interval,
        "rth": "true",
    }

    data = await _theta_fetch_with_retry(
        f"{THETA_V2_BASE}/v2/hist/option/implied_volatility",
        params=params,
        max_retries=3,
        base_timeout=8.0,
    )

    if not data or not data.get("response"):
        return {"root": root, "strike": strike, "right": right, "data": [], "source": "thetadata_v2"}

    # Response fields per ThetaData docs:
    # [ms_of_day, bid, bid_implied_vol, midpoint, implied_vol, ask, ask_implied_vol,
    #  iv_error, ms_of_day2, underlying_price, date]
    rows = data["response"]
    result = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 11:
            continue
        ms_of_day = row[0]
        date_int = row[10]
        # Build timestamp from date + ms_of_day
        ds = str(int(date_int))
        if len(ds) != 8:
            continue
        hours = ms_of_day // 3_600_000
        minutes = (ms_of_day % 3_600_000) // 60_000
        seconds = (ms_of_day % 60_000) // 1000
        timestamp = f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}T{hours:02d}:{minutes:02d}:{seconds:02d}"

        result.append({
            "timestamp": timestamp,
            "bid_iv": row[2],
            "mid_iv": row[4],
            "ask_iv": row[6],
            "underlying_price": row[9],
            "date": f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}",
        })

    return {
        "root": root,
        "strike": strike,
        "right": right,
        "exp": exp,
        "interval": interval,
        "count": len(result),
        "data": result,
        "source": "thetadata_v2",
    }


async def get_iv_percentile(root: str, current_iv: float, lookback_days: int = 252) -> dict:
    """
    Calculate IV rank and IV percentile for a given root symbol.

    Fetches IV history for the ATM option over the lookback period and computes:
      - iv_rank: (current - min) / (max - min)
      - iv_percentile: % of days where IV was lower than current
      - iv_high, iv_low, iv_mean: summary stats

    Uses a near-term ATM call as the reference contract.
    """
    today = datetime.now()
    end_date = today.strftime("%Y%m%d")
    start_date = (today - timedelta(days=lookback_days)).strftime("%Y%m%d")

    # Get current SPY price for ATM strike via Alpaca (reuse existing pattern)
    atm_strike = None
    if ALPACA_KEY:
        try:
            url = f"{ALPACA_DATA_URL}/v2/stocks/{root}/quotes/latest"
            async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=3.0)) as resp:
                    if resp.status == 200:
                        qdata = await resp.json()
                        quote = qdata.get("quote", qdata)
                        mid = (quote.get("ap", 0) + quote.get("bp", 0)) / 2
                        if mid > 0:
                            atm_strike = round(mid)
        except Exception:
            pass

    if not atm_strike:
        return {"error": "Could not determine ATM strike", "iv_rank": None, "iv_percentile": None}

    # Find the nearest expiration (use existing expirations endpoint logic)
    exp_data = await _theta_fetch_with_retry(
        f"{THETA_BASE}/v3/option/list/expirations",
        params={"symbol": root},
        max_retries=2,
        base_timeout=5.0,
    )
    nearest_exp = None
    if exp_data and exp_data.get("response"):
        today_int = int(today.strftime("%Y%m%d"))
        for row in exp_data["response"]:
            candidates = row if isinstance(row, list) else [row]
            for d in candidates:
                d_int = int(d)
                if d_int >= today_int:
                    if nearest_exp is None or d_int < nearest_exp:
                        nearest_exp = d_int

    if not nearest_exp:
        return {"error": "No expiration found", "iv_rank": None, "iv_percentile": None}

    # Fetch historical IV using the v2 API (daily interval for percentile calc)
    strike_tenth_cent = int(atm_strike * 1000)
    params = {
        "root": root,
        "exp": nearest_exp,
        "strike": strike_tenth_cent,
        "right": "C",
        "start_date": int(start_date),
        "end_date": int(end_date),
        "ivl": 0,  # end-of-day ticks
        "rth": "true",
    }

    data = await _theta_fetch_with_retry(
        f"{THETA_V2_BASE}/v2/hist/option/implied_volatility",
        params=params,
        max_retries=3,
        base_timeout=10.0,
    )

    if not data or not data.get("response"):
        return {"error": "No IV history available", "iv_rank": None, "iv_percentile": None}

    # Extract daily mid-IV values (one per unique date)
    daily_ivs = {}
    for row in data["response"]:
        if not isinstance(row, list) or len(row) < 11:
            continue
        iv = row[4]  # midpoint implied_vol
        date_int = row[10]
        if iv is not None and iv > 0:
            daily_ivs[date_int] = iv  # last value per date wins

    iv_values = list(daily_ivs.values())
    if not iv_values:
        return {"error": "No valid IV data points", "iv_rank": None, "iv_percentile": None}

    iv_high = max(iv_values)
    iv_low = min(iv_values)
    iv_mean = sum(iv_values) / len(iv_values)

    # IV Rank: where current IV sits in the min-max range
    iv_range = iv_high - iv_low
    iv_rank = ((current_iv - iv_low) / iv_range) if iv_range > 0 else 0.5

    # IV Percentile: % of days where IV was lower than current
    days_below = sum(1 for v in iv_values if v < current_iv)
    iv_percentile = days_below / len(iv_values)

    return {
        "iv_rank": round(iv_rank, 4),
        "iv_percentile": round(iv_percentile, 4),
        "iv_high": round(iv_high, 6),
        "iv_low": round(iv_low, 6),
        "iv_mean": round(iv_mean, 6),
        "lookback_days": lookback_days,
        "data_points": len(iv_values),
    }


# ============================================================================
# THETADATA v2 — Historical Option Quotes
# ============================================================================

async def get_spread_analysis(
    root: str, exp: str, strike: float, right: str, date: str,
) -> dict:
    """
    Fetch 1-minute quote data for a single day and return spread statistics.

    Args:
        root: Underlying symbol (e.g. "SPY")
        exp: Expiration date YYYYMMDD
        strike: Strike price in dollars (e.g. 420.0)
        right: "C" or "P"
        date: Date YYYYMMDD to analyze

    Returns dict with: avg_spread, max_spread, min_spread, avg_bid_size,
    avg_ask_size, liquidity_score (0-100).
    """
    strike_thetadata = int(strike * 1000)

    data = await _theta_fetch_with_retry(
        f"{THETA_V2_BASE}/v2/hist/option/quote",
        params={
            "root": root,
            "exp": int(exp),
            "strike": strike_thetadata,
            "right": right.upper(),
            "start_date": int(date),
            "end_date": int(date),
            "ivl": 60000,  # 1-minute bars
            "rth": "true",
        },
        max_retries=3,
        base_timeout=8.0,
    )

    response = data.get("response", [])
    # v2 response is a list of arrays:
    # [ms_of_day, bid_size, bid_exchange, bid, bid_condition,
    #  ask_size, ask_exchange, ask, ask_condition, date]
    empty_result = {
        "avg_spread": 0, "max_spread": 0, "min_spread": 0,
        "avg_bid_size": 0, "avg_ask_size": 0, "liquidity_score": 0,
        "sample_count": 0,
    }
    if not response or not isinstance(response, list):
        return empty_result

    spreads = []
    bid_sizes = []
    ask_sizes = []
    mid_sum = 0.0

    for row in response:
        if not isinstance(row, list) or len(row) < 10:
            continue
        bid = row[3]
        ask = row[7]
        bid_size = row[1]
        ask_size = row[5]
        if bid is None or ask is None or bid <= 0 or ask <= 0:
            continue
        spreads.append(round(ask - bid, 4))
        bid_sizes.append(bid_size)
        ask_sizes.append(ask_size)
        mid_sum += (bid + ask) / 2

    if not spreads:
        return empty_result

    n = len(spreads)
    avg_spread = round(sum(spreads) / n, 4)
    max_spread = round(max(spreads), 4)
    min_spread = round(min(spreads), 4)
    avg_bid_size = round(sum(bid_sizes) / n, 1)
    avg_ask_size = round(sum(ask_sizes) / n, 1)

    # Liquidity score: 0-100 based on tight spread + high size
    # Spread component (0-50): tighter = better; 10%+ of mid = 0 pts
    avg_mid = mid_sum / n
    spread_pct = avg_spread / max(avg_mid, 0.01)
    spread_score = max(0, min(50, 50 * (1 - spread_pct / 0.10)))

    # Size component (0-50): higher avg size = better; 100+ contracts = max
    avg_size = (avg_bid_size + avg_ask_size) / 2
    size_score = max(0, min(50, 50 * min(avg_size / 100, 1.0)))

    liquidity_score = round(spread_score + size_score)

    return {
        "avg_spread": avg_spread,
        "max_spread": max_spread,
        "min_spread": min_spread,
        "avg_bid_size": avg_bid_size,
        "avg_ask_size": avg_ask_size,
        "liquidity_score": liquidity_score,
        "sample_count": n,
    }


@router.get("/api/theta/quotes/history")
async def get_option_quote_history(
    root: str = "SPY",
    exp: str = None,       # YYYYMMDD
    strike: float = None,  # dollars (e.g. 420.0)
    right: str = "C",
    start_date: str = None,  # YYYYMMDD
    end_date: str = None,    # YYYYMMDD
    interval: int = 60000,   # 1min default (ms)
):
    """
    Fetch historical option quote data from ThetaData v2 API.

    Converts strike from dollars to 1/10th cent format.
    Returns clean JSON with bid/ask, spread, and midpoint.
    """
    if strike is None or exp is None:
        return {"error": "Both 'exp' (YYYYMMDD) and 'strike' (dollars) are required"}

    # Default date range: last 5 days → today
    today = datetime.now()
    if end_date is None:
        end_date = today.strftime("%Y%m%d")
    if start_date is None:
        start_date = (today - timedelta(days=5)).strftime("%Y%m%d")

    # Convert strike from dollars to 1/10th cent (ThetaData format)
    strike_thetadata = int(strike * 1000)

    data = await _theta_fetch_with_retry(
        f"{THETA_V2_BASE}/v2/hist/option/quote",
        params={
            "root": root,
            "exp": int(exp),
            "strike": strike_thetadata,
            "right": right.upper(),
            "start_date": int(start_date),
            "end_date": int(end_date),
            "ivl": interval,
            "rth": "true",
        },
        max_retries=3,
        base_timeout=8.0,
    )

    meta = {
        "root": root, "exp": exp, "strike": strike, "right": right,
        "start_date": start_date, "end_date": end_date,
        "interval_ms": interval, "source": "thetadata_v2",
    }

    if not data:
        return {"quotes": [], "meta": {**meta, "count": 0}}

    # v2 response format — each row is:
    # [ms_of_day, bid_size, bid_exchange, bid, bid_condition,
    #  ask_size, ask_exchange, ask, ask_condition, date]
    response = data.get("response", [])
    if not response:
        return {"quotes": [], "meta": {**meta, "count": 0}}

    quotes = []
    for row in response:
        if not isinstance(row, list) or len(row) < 10:
            continue

        ms_of_day = row[0]
        bid_size = row[1]
        bid = row[3]
        ask_size = row[5]
        ask = row[7]
        date_val = row[9]

        if bid is None or ask is None:
            continue

        spread = round(ask - bid, 4) if bid > 0 and ask > 0 else 0
        mid = round((bid + ask) / 2, 4) if bid > 0 and ask > 0 else 0

        # Convert ms_of_day to HH:MM:SS
        if isinstance(ms_of_day, (int, float)) and ms_of_day > 0:
            total_seconds = int(ms_of_day / 1000)
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            time_str = str(ms_of_day)

        # Format date YYYYMMDD → YYYY-MM-DD
        date_str = str(date_val) if date_val else ""
        if len(date_str) == 8 and date_str.isdigit():
            date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

        quotes.append({
            "timestamp": f"{date_str}T{time_str}" if date_str else time_str,
            "bid": bid,
            "bid_size": bid_size,
            "ask": ask,
            "ask_size": ask_size,
            "spread": spread,
            "mid": mid,
            "date": date_str,
        })

    return {"quotes": quotes, "meta": {**meta, "count": len(quotes)}}


@router.get("/api/theta/quotes/spread-analysis")
async def get_spread_analysis_endpoint(
    root: str = "SPY",
    exp: str = None,       # YYYYMMDD
    strike: float = None,  # dollars
    right: str = "C",
    date: str = None,      # YYYYMMDD (single day)
):
    """
    Analyze bid/ask spread quality for a specific option on a given day.

    Returns spread statistics and a liquidity score (0-100).
    """
    if strike is None or exp is None:
        return {"error": "Both 'exp' (YYYYMMDD) and 'strike' (dollars) are required"}

    if date is None:
        date = datetime.now().strftime("%Y%m%d")

    analysis = await get_spread_analysis(root, exp, strike, right, date)

    return {
        "analysis": analysis,
        "meta": {
            "root": root, "exp": exp, "strike": strike,
            "right": right, "date": date, "source": "thetadata_v2",
        },
    }
