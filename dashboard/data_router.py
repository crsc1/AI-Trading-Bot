"""
DataRouter — Single source of truth for all market data.

Rules:
  - Options chain + Greeks: ThetaData ONLY (what we pay for)
  - Stock quote: ThetaData snapshot → Alpaca fallback
  - Historical bars: Alpaca primary → ThetaData EOD fallback
  - Order execution: Alpaca ONLY (our broker)

Every response is tagged with:
  - source: which provider returned the data
  - fetched_at: when the data was fetched (UTC ISO)
  - staleness_ms: how old the data is at read time
"""

import asyncio
import aiohttp
import json as _json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any

from .config import cfg

logger = logging.getLogger(__name__)

# ─── Provider Config ────────────────────────────────────────────────────────

THETA_BASE = cfg.THETA_BASE_URL
ALPACA_DATA_URL = cfg.ALPACA_DATA_URL
ALPACA_KEY = cfg.ALPACA_API_KEY
ALPACA_SECRET = cfg.ALPACA_SECRET_KEY
ALPACA_HEADERS = cfg.ALPACA_HEADERS

# ─── Cache Config ────────────────────────────────────────────────────────────

CHAIN_CACHE_TTL = cfg.CHAIN_CACHE_TTL
QUOTE_CACHE_TTL = cfg.QUOTE_CACHE_TTL
BAR_CACHE_TTL = cfg.BAR_CACHE_TTL

# ─── Health Tracking ─────────────────────────────────────────────────────────

_health = {
    "thetadata": {
        "last_success": 0.0,
        "last_failure": 0.0,
        "consecutive_failures": 0,
        "total_requests": 0,
        "total_failures": 0,
    },
    "alpaca": {
        "last_success": 0.0,
        "last_failure": 0.0,
        "consecutive_failures": 0,
        "total_requests": 0,
        "total_failures": 0,
    },
}


def get_health() -> Dict:
    """Return health stats for all providers."""
    now = time.time()
    result = {}
    for provider, stats in _health.items():
        status = "unknown"
        if stats["total_requests"] > 0:
            if stats["consecutive_failures"] == 0:
                status = "healthy"
            elif stats["consecutive_failures"] < 3:
                status = "degraded"
            else:
                status = "down"
        result[provider] = {**stats, "status": status}
    return result


def _record_success(provider: str):
    _health[provider]["last_success"] = time.time()
    _health[provider]["consecutive_failures"] = 0
    _health[provider]["total_requests"] += 1


def _record_failure(provider: str):
    _health[provider]["last_failure"] = time.time()
    _health[provider]["consecutive_failures"] += 1
    _health[provider]["total_requests"] += 1
    _health[provider]["total_failures"] += 1


# ─── Internal HTTP helpers ────────────────────────────────────────────────────

async def _theta_get(path: str, params: dict = None, timeout: float = None) -> Optional[dict]:
    if timeout is None:
        timeout = cfg.THETA_REQUEST_TIMEOUT
    """GET from ThetaData Terminal with retry.

    Handles both JSON and text/csv responses — some list endpoints (e.g.
    list/expirations) return text/csv even when queried without format=json.
    CSV responses are parsed into {"response": [int, ...]} for uniform handling.
    """
    url = f"{THETA_BASE}{path}"
    for attempt in range(2):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        try:
                            data = _json.loads(text)
                        except _json.JSONDecodeError:
                            # Some endpoints return text/csv (e.g. list/expirations)
                            # Parse simple CSV: newline or comma-separated integers
                            items = []
                            for part in text.replace(",", "\n").split("\n"):
                                part = part.strip()
                                if part.isdigit():
                                    items.append(int(part))
                            data = {"response": items} if items else {}
                            if items:
                                logger.debug(f"[DataRouter] Parsed {len(items)} CSV items from {path}")
                            else:
                                logger.debug(f"[DataRouter] Empty CSV response on {path}")
                        _record_success("thetadata")
                        return data
                    else:
                        logger.warning(f"[DataRouter] ThetaData {resp.status} on {path}")
                        _record_failure("thetadata")
        except Exception as e:
            logger.warning(f"[DataRouter] ThetaData error on {path} (attempt {attempt+1}): {e}")
            _record_failure("thetadata")
            if attempt == 0:
                await asyncio.sleep(0.5)
    return None


async def _alpaca_get(path: str, params: dict = None, timeout: float = None) -> Optional[dict]:
    if timeout is None:
        timeout = cfg.ALPACA_REQUEST_TIMEOUT
    """GET from Alpaca Data API."""
    url = f"{ALPACA_DATA_URL}{path}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=ALPACA_HEADERS,
                                   timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    _record_success("alpaca")
                    return data
                else:
                    body = await resp.text()
                    logger.warning(f"[DataRouter] Alpaca {resp.status} on {path}: {body[:200]}")
                    _record_failure("alpaca")
    except Exception as e:
        logger.warning(f"[DataRouter] Alpaca error on {path}: {e}")
        _record_failure("alpaca")
    return None


# ─── Cache ────────────────────────────────────────────────────────────────────

class _Cache:
    """Simple in-memory TTL cache."""

    def __init__(self):
        self._store: Dict[str, Dict] = {}

    def get(self, key: str, ttl: float) -> Optional[Any]:
        entry = self._store.get(key)
        if entry and (time.time() - entry["ts"]) < ttl:
            return entry["data"]
        return None

    def put(self, key: str, data: Any):
        self._store[key] = {"data": data, "ts": time.time()}

    def invalidate(self, key: str):
        self._store.pop(key, None)

    def clear(self):
        self._store.clear()


_cache = _Cache()


def _tag(data: dict, source: str) -> dict:
    """Tag response with source and timestamp."""
    now = datetime.now(timezone.utc)
    data["_source"] = source
    data["_fetched_at"] = now.isoformat()
    data["_fetched_ts"] = time.time()
    return data


def staleness_ms(data: dict) -> int:
    """How many ms since this data was fetched."""
    ts = data.get("_fetched_ts", 0)
    if ts == 0:
        return 999999
    return int((time.time() - ts) * 1000)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════


async def get_quote(symbol: str = "SPY") -> Dict:
    """
    Get current stock quote (SPY underlying price).

    Source: Alpaca ONLY.
    ThetaData OPTION.STANDARD does NOT include stock quotes — calling
    /v3/stock/* endpoints returns PERMISSION_DENIED on the free stock tier.
    We only use ThetaData for OPTIONS data.

    Returns: {last, bid, ask, bid_size, ask_size, mid, source}
    """
    cache_key = f"quote:{symbol}"
    cached = _cache.get(cache_key, QUOTE_CACHE_TTL)
    if cached:
        return cached

    # Alpaca quote (works on free tier via IEX)
    feed = cfg.ALPACA_DATA_FEED
    alpaca = await _alpaca_get(f"/v2/stocks/{symbol}/quotes/latest", {"feed": feed})
    if alpaca and alpaca.get("quote"):
        q = alpaca["quote"]
        result = _tag({
            "symbol": symbol,
            "bid": float(q.get("bp", 0)),
            "ask": float(q.get("ap", 0)),
            "bid_size": int(q.get("bs", 0)),
            "ask_size": int(q.get("as", 0)),
        }, f"alpaca_{feed}")
        result["mid"] = (result["bid"] + result["ask"]) / 2
        result["last"] = result["mid"]
        _cache.put(cache_key, result)
        return result

    # Last resort: Alpaca latest trade
    alpaca_trade = await _alpaca_get(f"/v2/stocks/{symbol}/trades/latest", {"feed": feed})
    if alpaca_trade and alpaca_trade.get("trade"):
        t = alpaca_trade["trade"]
        price = float(t.get("p", 0))
        result = _tag({
            "symbol": symbol,
            "last": price,
            "bid": price,
            "ask": price,
            "bid_size": 0,
            "ask_size": 0,
            "mid": price,
        }, f"alpaca_{feed}_trade")
        _cache.put(cache_key, result)
        return result

    return _tag({"symbol": symbol, "last": 0, "bid": 0, "ask": 0, "mid": 0, "error": "no_data"}, "none")


async def get_options_chain(
    root: str = "SPY",
    expiration: str = None,
    strikes_around_atm: int = None,
) -> Dict:
    if strikes_around_atm is None:
        strikes_around_atm = cfg.THETA_STRIKE_RANGE
    """
    Get options chain with REAL Greeks from ThetaData Standard plan.

    Uses /v3/option/snapshot/greeks/first_order with strike_range — ONE API call:
      - Replaces: fetch strikes list + 60 parallel per-contract calls (quote+OI+ohlc)
      - Provides: real delta/theta/vega/rho/IV from ThetaData (not Black-Scholes)
      - Prices already in dollars — no /100 conversion

    ThetaData v3 correct params (confirmed from docs.thetadata.us):
      symbol (not root), expiration (YYYYMMDD, not exp),
      strike in dollars (not millidollars), right=call/put/both (not C/P)

    Returns: {
        root, expiration,
        calls: [{symbol, strike, bid, ask, mid, iv, delta, theta, vega, rho, underlying_price}],
        puts: [...same...],
        underlying_price, source
    }
    """
    if not expiration:
        expiration = datetime.now().strftime("%Y-%m-%d")

    cache_key = f"chain:{root}:{expiration}"
    cached = _cache.get(cache_key, CHAIN_CACHE_TTL)
    if cached:
        return cached

    # ThetaData v3 requires YYYYMMDD format
    exp_td = expiration.replace("-", "")

    # Fallback underlying price (first_order response includes underlying_price too)
    quote = await get_quote(root)
    underlying_price = float(quote.get("last", 0) or quote.get("mid", 0))

    # ── Single call: first_order greeks with strike_range ──────────────────
    # Standard plan endpoint. Returns ATM ±strike_range contracts for both
    # calls and puts with full Greeks + IV in one shot.
    # Docs: docs.thetadata.us/operations/option_snapshot_greeks_first_order.html
    data = await _theta_get("/v3/option/snapshot/greeks/first_order", {
        "symbol": root,
        "expiration": exp_td,
        "right": "both",
        "strike_range": strikes_around_atm,
        "format": "json",
    })

    raw_response = data.get("response") if data else None

    # ThetaData "no data" sentinels: None, [], or [[]] (one empty inner array)
    def _is_empty(r) -> bool:
        if not r:
            return True
        if isinstance(r, list) and len(r) == 1 and isinstance(r[0], list) and not r[0]:
            return True
        return False

    if not data or _is_empty(raw_response):
        # [[]] is ThetaData's way of saying "no live snapshot" (market closed / no quotes)
        if raw_response is not None:
            logger.info(
                f"[DataRouter] first_order: no live data for {root} exp={expiration} "
                f"(market may be closed or expiration is expired/not-yet-active). "
                f"Response sentinel: {str(raw_response)[:80]}"
            )
        else:
            logger.warning(
                f"[DataRouter] No first_order response for {root} exp={expiration}. "
                f"Raw: {str(data)[:200]}"
            )
        return _tag({
            "root": root, "expiration": expiration,
            "calls": [], "puts": [],
            "underlying_price": underlying_price,
            "error": "no_chain_data",
        }, "none")

    calls, puts = [], []
    items = raw_response
    if not isinstance(items, list):
        items = [items] if items else []

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
                logger.debug(f"[DataRouter] Unknown right '{right_raw}', skipping")
                continue

            strike = float(contract.get("strike", 0))
            bid = float(d.get("bid", 0) or 0)
            ask = float(d.get("ask", 0) or 0)
            mid = round((bid + ask) / 2, 4) if (bid + ask) > 0 else bid

            # Use underlying price from response (fresher than our quote lookup)
            resp_ul = d.get("underlying_price")
            if resp_ul and underlying_price == 0:
                underlying_price = float(resp_ul)

            def _f(key):
                v = d.get(key)
                return float(v) if v is not None else None

            # ── Greeks validation bounds ──
            # Clamp to sane ranges so downstream consumers never see garbage
            raw_iv = _f("implied_vol") or _f("implied_volatility")
            raw_delta = _f("delta")
            raw_theta = _f("theta")
            raw_vega = _f("vega")
            raw_rho = _f("rho")

            iv = max(0.01, min(raw_iv, 5.0)) if raw_iv is not None else None
            delta = max(-1.0, min(raw_delta, 1.0)) if raw_delta is not None else None
            theta = raw_theta  # always negative, no practical clamp needed
            vega = max(0.0, raw_vega) if raw_vega is not None else None
            rho_val = raw_rho  # small magnitude, no clamp needed

            entry = {
                "symbol": _build_occ_symbol(root, expiration, right_letter, strike),
                "strike": strike,
                "right": right_letter.lower(),   # "call" or "put" (lowercase for consumers)
                "right_letter": right_letter,     # "C" or "P"
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "last": mid,
                "volume": 0,          # not in first_order
                "open_interest": 0,
                "iv": iv,
                "delta": delta,
                "gamma": None,        # Pro only (greeks/all endpoint)
                "theta": theta,
                "vega": vega,
                "rho": rho_val,
                "underlying_price": float(resp_ul) if resp_ul else underlying_price,
                "timestamp": item.get("timestamp") or d.get("timestamp"),
            }

            if right_letter == "C":
                calls.append(entry)
            else:
                puts.append(entry)
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"[DataRouter] Skipping chain item ({e}): {str(item)[:100]}")
            continue

    calls.sort(key=lambda x: x["strike"])
    puts.sort(key=lambda x: x["strike"])

    logger.info(
        f"[DataRouter] Chain built via first_order: {len(calls)} calls, "
        f"{len(puts)} puts for {root} exp={expiration} ul={underlying_price:.2f}"
    )

    result = _tag({
        "root": root,
        "expiration": expiration,
        "calls": calls,
        "puts": puts,
        "underlying_price": underlying_price,
        "strike_count": max(len(calls), len(puts)),
    }, "thetadata")

    _cache.put(cache_key, result)
    return result


async def get_bars(
    symbol: str = "SPY",
    timeframe: str = "1Min",
    limit: int = 30,
    feed: str = None,
) -> Dict:
    """
    Get historical price bars.
    Priority: Alpaca → ThetaData EOD fallback (for daily only)
    Returns: {bars: [{time, open, high, low, close, volume, vwap}], source}
    """
    cache_key = f"bars:{symbol}:{timeframe}:{limit}"
    cached = _cache.get(cache_key, BAR_CACHE_TTL)
    if cached:
        return cached

    if not feed:
        feed = os.environ.get("ALPACA_DATA_FEED", "iex")

    # Map timeframe to Alpaca format
    tf_map = {"1m": "1Min", "1Min": "1Min", "5m": "5Min", "5Min": "5Min",
              "15m": "15Min", "15Min": "15Min", "1h": "1Hour", "1Hour": "1Hour",
              "1d": "1Day", "1D": "1Day", "1Day": "1Day"}
    alpaca_tf = tf_map.get(timeframe, timeframe)

    # Calculate start time
    if "Day" in alpaca_tf:
        start = (datetime.now(timezone.utc) - timedelta(days=limit * 2)).strftime("%Y-%m-%dT00:00:00Z")
    else:
        start = (datetime.now(timezone.utc) - timedelta(hours=max(limit * 2, 8))).strftime("%Y-%m-%dT00:00:00Z")

    alpaca = await _alpaca_get(f"/v2/stocks/{symbol}/bars", {
        "timeframe": alpaca_tf,
        "start": start,
        "limit": limit,
        "feed": feed,
        "adjustment": "raw",
    })

    if alpaca and alpaca.get("bars"):
        bars = []
        for b in alpaca["bars"][-limit:]:
            bars.append({
                "time": b.get("t", ""),
                "open": float(b.get("o", 0)),
                "high": float(b.get("h", 0)),
                "low": float(b.get("l", 0)),
                "close": float(b.get("c", 0)),
                "volume": int(b.get("v", 0)),
                "vwap": float(b.get("vw", 0)),
            })
        result = _tag({
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": bars,
            "count": len(bars),
        }, f"alpaca_{feed}")
        _cache.put(cache_key, result)
        return result

    return _tag({
        "symbol": symbol, "timeframe": timeframe,
        "bars": [], "count": 0, "error": "no_data",
    }, "none")


async def get_expirations(root: str = "SPY") -> Dict:
    """Get available option expirations from ThetaData."""
    cache_key = f"expirations:{root}"
    cached = _cache.get(cache_key, cfg.EXPIRATION_CACHE_TTL)
    if cached:
        return cached

    data = await _theta_get("/v3/option/list/expirations", {"symbol": root})
    if data and data.get("response"):
        expirations = []
        for row in data["response"]:
            if isinstance(row, list):
                for d in row:
                    try:
                        ds = str(d)
                        expirations.append(f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}")
                    except Exception:
                        continue
            elif isinstance(row, (int, str)):
                ds = str(row)
                if len(ds) == 8:
                    expirations.append(f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}")

        result = _tag({"root": root, "expirations": sorted(expirations)}, "thetadata")
        _cache.put(cache_key, result)
        return result

    return _tag({"root": root, "expirations": [], "error": "no_data"}, "none")


# ─── Greeks Computation ───────────────────────────────────────────────────────

def _compute_greeks(
    underlying: float,
    strike: float,
    right: str,
    expiration: str,
    option_price: Optional[float] = None,
) -> Dict:
    """Compute Greeks via Black-Scholes. Returns empty dict on failure."""
    try:
        from utils.greeks import calculate_greeks, calculate_iv
        import math

        # Time to expiry in years
        exp_dt = datetime.strptime(expiration, "%Y-%m-%d").replace(
            hour=16, minute=0, tzinfo=timezone.utc
        )
        now = datetime.now(timezone.utc)
        tte = max((exp_dt - now).total_seconds() / (365.25 * 24 * 3600), 1e-6)

        r = 0.05  # risk-free rate
        is_call = right.upper() == "C"

        # Calculate IV from market price if available
        iv = 0.30  # default
        if option_price and option_price > 0.01 and underlying > 0:
            try:
                computed_iv = calculate_iv(
                    option_price, underlying, strike, tte, r, is_call
                )
                if computed_iv and 0.01 < computed_iv < 5.0:
                    iv = computed_iv
            except Exception:
                pass

        greeks = calculate_greeks(underlying, strike, tte, r, iv, is_call)
        return {
            "iv": round(iv, 4),
            "delta": round(greeks.get("delta", 0), 4),
            "gamma": round(greeks.get("gamma", 0), 6),
            "theta": round(greeks.get("theta", 0), 4),
            "vega": round(greeks.get("vega", 0), 4),
        }
    except Exception as e:
        logger.debug(f"[DataRouter] Greeks computation failed: {e}")
        return {}


# ─── OCC Symbol Builder ──────────────────────────────────────────────────────

def _build_occ_symbol(root: str, expiration: str, right: str, strike: float) -> str:
    """Build OCC options symbol: SPY250331C00570000"""
    exp_dt = datetime.strptime(expiration, "%Y-%m-%d")
    exp_str = exp_dt.strftime("%y%m%d")
    strike_int = int(strike * 1000)
    return f"{root:<6}{exp_str}{right.upper()}{strike_int:08d}"


# ─── Convenience ──────────────────────────────────────────────────────────────

def clear_cache():
    """Clear all cached data (call after config changes)."""
    _cache.clear()
    logger.info("[DataRouter] Cache cleared")
