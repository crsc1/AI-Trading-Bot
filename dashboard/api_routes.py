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
):
    """
    Fetch OHLCV bars from Alpaca for ANY stock.
    Supports all intraday timeframes with Algo Trader Plus.
    """
    bars = await _fetch_alpaca_bars(symbol, timeframe, limit, feed)
    if bars is not None:
        return bars

    # Fallback to ThetaData EOD (only daily)
    if timeframe in ("1D", "1Day", "day"):
        return await _fetch_theta_eod_bars(symbol, limit)

    return {"bars": [], "error": f"No data for {symbol} {timeframe}. Check Alpaca subscription."}


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
