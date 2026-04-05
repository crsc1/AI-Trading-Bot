"""
Order Flow API routes — fetches tick-level trade data from Alpaca and
aggregates into volume-cloud-ready buckets (time bar × price level).

Data source: Alpaca Market Data API v2
  - Historical trades: GET https://data.alpaca.markets/v2/stocks/{symbol}/trades
  - Requires Algo Trader Plus ($99/mo) for full SIP feed;
    falls back to IEX (free) with reduced coverage (~3-5% of volume).

Also accepts live ticks from the flow engine WebSocket for real-time
volume cloud building on the frontend.

Buy/sell classification:
  - Tick rule: if trade price > previous trade price → buy (aggressor lifted the ask).
  - If price < previous → sell (aggressor hit the bid).
  - If price == previous → inherit previous classification.
  - Upgrade path: use quote data (compare trade price to NBBO midpoint) for
    higher accuracy. Add `feed=sip` + quote endpoint when on Algo Trader Plus.
"""

from fastapi import APIRouter, Query
from datetime import datetime, timedelta, timezone
from typing import Optional
import logging
import aiohttp
from .config import cfg

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/orderflow", tags=["orderflow"])

ALPACA_KEY = cfg.ALPACA_API_KEY
ALPACA_SECRET = cfg.ALPACA_SECRET_KEY
ALPACA_DATA_URL = cfg.ALPACA_DATA_URL + "/v2"
ALPACA_PAPER_URL = cfg.ALPACA_BASE_URL

# Rate limit: Alpaca allows 200 req/min on free, higher on paid
ALPACA_HEADERS = cfg.ALPACA_HEADERS

# Cache for last trading day detection
_last_trading_day_cache: dict = {"date": None, "expires": 0}


# ============================================================================
# TRADING CALENDAR — find last trading day (Algo Trader Plus has this data)
# ============================================================================

async def _find_last_trading_day() -> str:
    """
    Find the most recent trading day with data using Alpaca's calendar API.
    Returns YYYY-MM-DD string. Uses caching to avoid repeated API calls.

    During market hours, returns TODAY so we get live intraday bars.
    After market close, returns the most recent completed trading day.
    """
    import time as _time
    now = _time.time()
    if _last_trading_day_cache["date"] and now < _last_trading_day_cache["expires"]:
        return _last_trading_day_cache["date"]

    # Use Eastern Time for market hour detection
    try:
        from zoneinfo import ZoneInfo
        et_now = datetime.now(ZoneInfo("America/New_York"))
    except ImportError:
        # Fallback: assume UTC-4 (EDT) or UTC-5 (EST)
        et_now = datetime.now(timezone(timedelta(hours=-4)))

    today_str = et_now.strftime("%Y-%m-%d")

    # Try Alpaca's trading calendar (available with any plan)
    try:
        start_date = (et_now - timedelta(days=10)).strftime("%Y-%m-%d")
        async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
            url = f"{ALPACA_PAPER_URL}/calendar?start={start_date}&end={today_str}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    cal = await resp.json()
                    if cal:
                        # Calendar includes today if today is a trading day
                        last_day = cal[-1]["date"]

                        # If today is a trading day and market has opened, use today
                        if last_day == today_str and et_now.hour >= 9 and et_now.minute >= 30:
                            result = today_str
                        elif last_day == today_str:
                            # Today is a trading day but market hasn't opened yet —
                            # use previous trading day so we show yesterday's data
                            result = cal[-2]["date"] if len(cal) >= 2 else last_day
                        else:
                            # Today is not a trading day (weekend/holiday), use last one
                            result = last_day

                        _last_trading_day_cache["date"] = result
                        _last_trading_day_cache["expires"] = now + 120  # 2 min cache (shorter for intraday)
                        logger.info(f"Trading day: {result} (today ET: {today_str})")
                        return result
    except Exception as e:
        logger.debug(f"Calendar API failed: {e}")

    # Fallback: walk back from today (ET) skipping weekends
    day = et_now
    for _ in range(7):
        if day.weekday() < 5:  # Mon-Fri
            return day.strftime("%Y-%m-%d")
        day -= timedelta(days=1)
    return today_str


# ============================================================================
# VOLUME CLOUDS — aggregated order flow for bubble chart
# ============================================================================

@router.get("/clouds")
async def get_volume_clouds(
    symbol: str = Query("SPY"),
    bar_minutes: int = Query(5, ge=1, le=60, description="Time bar duration in minutes"),
    date: Optional[str] = Query(None, description="YYYY-MM-DD (default: today or last trading day)"),
    min_volume: int = Query(0, ge=0, description="Minimum total volume to include a cell"),
    feed: str = Query("sip", description="Alpaca feed: 'sip' (Algo Trader Plus) or 'iex' (free)"),
):
    """
    Build volume clouds for the bubble chart using Alpaca's bars API.

    Uses 1-minute OHLCV bars (efficient — covers the full trading day in one call)
    instead of individual trades (SPY has millions/day, would only get first few seconds).

    Each bar becomes a bubble:
      - x: bar time
      - y: VWAP (volume-weighted average price) from OHLC
      - size: volume
      - color: green if close > open (buy pressure), red if close < open (sell pressure)

    Bars are grouped into larger time windows (bar_minutes) when requested.
    Multiple price levels per window are created from the high-low range.
    """
    # Determine date range
    if date:
        try:
            day_str = date
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD."}
    else:
        day_str = await _find_last_trading_day()

    # Market hours: 9:30 - 16:00 ET (13:30 - 20:00 UTC during EDT, 14:30 - 21:00 UTC during EST)
    # Use UTC timestamps for Alpaca API to avoid timezone offset issues.
    try:
        from zoneinfo import ZoneInfo
        et_tz = ZoneInfo("America/New_York")
    except ImportError:
        et_tz = timezone(timedelta(hours=-4))

    # Parse day_str and compute market open/close in UTC
    day_date = datetime.strptime(day_str, "%Y-%m-%d")
    market_open_et = day_date.replace(hour=9, minute=30, second=0, tzinfo=et_tz)
    market_close_et = day_date.replace(hour=16, minute=0, second=0, tzinfo=et_tz)
    start_str = market_open_et.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    et_now = datetime.now(et_tz)
    today_et = et_now.strftime("%Y-%m-%d")

    if day_str == today_et and et_now.hour < 16 and et_now.hour >= 9:
        # Market is open — fetch bars up to now
        end_str = et_now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.info(f"Live intraday: fetching bars from 09:30 to {et_now.strftime('%H:%M')} ET")
    else:
        end_str = market_close_et.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Fetch 1-minute bars from Alpaca (covers full day efficiently)
    bars = await _fetch_alpaca_bars_for_clouds(symbol, start_str, end_str, feed)

    # Auto-fallback: if SIP fails, try IEX
    if isinstance(bars, dict) and "error" in bars and feed == "sip":
        logger.info("SIP bars failed — falling back to IEX")
        bars = await _fetch_alpaca_bars_for_clouds(symbol, start_str, end_str, "iex")
        if not isinstance(bars, dict):
            feed = "iex"

    if isinstance(bars, dict) and "error" in bars:
        return bars

    if not bars:
        return {
            "clouds": [], "meta": {"symbol": symbol, "date": day_str,
            "trade_count": 0, "bar_minutes": bar_minutes},
            "warning": f"No bars for {day_str}. Market may have been closed."
        }

    # Aggregate 1-min bars into volume cloud cells
    clouds = _bars_to_clouds(bars, bar_minutes, min_volume)

    total_vol = sum(b.get("v", 0) for b in bars)

    return {
        "clouds": clouds["cells"],
        "bars_summary": clouds["bars_summary"],
        "meta": {
            "symbol": symbol,
            "date": day_str,
            "trade_count": len(bars),
            "total_volume": total_vol,
            "bar_minutes": bar_minutes,
            "feed": feed,
            "price_range": clouds["price_range"],
        }
    }


async def _fetch_alpaca_bars_for_clouds(
    symbol: str, start: str, end: str, feed: str = "sip"
) -> list | dict:
    """
    Fetch 1-minute bars from Alpaca for volume cloud building.
    Returns list of bar dicts: {t, o, h, l, c, v, n, vw}
    """
    if not ALPACA_KEY or not ALPACA_SECRET:
        return {"error": "ALPACA_API_KEY / ALPACA_SECRET_KEY not set in .env"}

    all_bars: list = []
    page_token: Optional[str] = None
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/bars"

    try:
        async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
            for _ in range(20):  # safety cap
                params = {
                    "timeframe": "1Min",
                    "start": start,
                    "end": end,
                    "feed": feed,
                    "limit": 10000,
                    "adjustment": "split",
                    "sort": "asc",
                }
                if page_token:
                    params["page_token"] = page_token

                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 403:
                        return {"error": f"Alpaca 403 — '{feed}' feed not available on your plan."}
                    if resp.status != 200:
                        return {"error": f"Alpaca {resp.status}: {(await resp.text())[:200]}"}

                    data = await resp.json()
                    bars = data.get("bars") or []
                    all_bars.extend(bars)

                    page_token = data.get("next_page_token")
                    if not page_token:
                        break

    except aiohttp.ClientError as e:
        return {"error": f"Alpaca connection error: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}

    return all_bars


def _bars_to_clouds(bars: list, bar_minutes: int, min_volume: int) -> dict:
    """
    Convert 1-minute Alpaca bars into volume cloud cells for the bubble chart.

    Prismadic-style: ONE bubble per bar at (timestamp, VWAP).
    Each bar = one point on the flowing trail. No splitting into multiple
    price levels at the same timestamp (that causes vertical stacking).

    The trail flows because each bar has a unique time position and
    the VWAP drifts up/down with price action.
    """
    if not bars:
        return {"cells": [], "bars_summary": [], "price_range": [0, 0]}

    cells = []
    bars_summary = []
    min_price = float("inf")
    max_price = 0.0
    running_vol = 0

    for bar in bars:
        ts_str = bar.get("t", "")
        if not ts_str:
            continue

        o, high, low, c = bar.get("o", 0), bar.get("h", 0), bar.get("l", 0), bar.get("c", 0)
        vol = bar.get("v", 0)
        vwap = bar.get("vw", 0) or round((o + high + low + c) / 4, 2)

        if vol <= 0 or high <= 0:
            continue

        # Parse timestamp — keep the bar's native 1-min timestamp
        try:
            ts_clean = ts_str.replace("Z", "+00:00")
            if "." in ts_clean:
                parts = ts_clean.split(".")
                frac = parts[1].split("+")[0].split("-")[0][:6]
                tz_part = "+" + parts[1].split("+")[1] if "+" in parts[1] else "-" + parts[1].split("-")[-1]
                ts_clean = f"{parts[0]}.{frac}{tz_part}"
            dt = datetime.fromisoformat(ts_clean)
        except (ValueError, IndexError):
            continue

        bar_key = dt.isoformat()
        min_price = min(min_price, low)
        max_price = max(max_price, high)

        # Buy/sell classification from OHLCV
        bar_range = high - low if high > low else 0.01
        if vwap > 0 and bar_range > 0:
            vwap_offset = (c - vwap) / bar_range
            buy_ratio = 0.5 + min(max(vwap_offset, -0.25), 0.25)
        elif c > o:
            buy_ratio = 0.60
        elif c < o:
            buy_ratio = 0.40
        else:
            buy_ratio = 0.50
        buy_vol = int(vol * buy_ratio)
        sell_vol = vol - buy_vol
        delta = buy_vol - sell_vol

        running_vol += vol

        # ONE bubble per bar at VWAP — this creates the flowing trail
        if vol >= min_volume:
            cells.append({
                "time": bar_key,
                "price": round(vwap, 2),
                "total_vol": vol,
                "buy_vol": buy_vol,
                "sell_vol": sell_vol,
                "delta": delta,
                "pct_of_bar": 100,
                "delta_ratio": round(delta / vol, 3) if vol else 0,
            })

        bars_summary.append({
            "time": bar_key,
            "total_vol": vol,
            "buy_vol": buy_vol,
            "sell_vol": sell_vol,
            "delta": delta,
            "levels": 1,
        })

    return {
        "cells": cells,
        "bars_summary": bars_summary,
        "price_range": [min_price, max_price],
    }


@router.get("/trades/recent")
async def get_recent_trades(
    symbol: str = Query("SPY"),
    limit: int = Query(500, ge=1, le=10000),
    feed: str = Query("sip"),
    minutes: int = Query(5, ge=1, le=60, description="How many minutes back to fetch"),
):
    """
    Fetch the most recent N trades from Alpaca SIP feed.
    Used as live polling fallback when the Rust engine WS isn't connected.
    With Algo Trader Plus, this gives full SIP data from all US exchanges.
    """
    now = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=minutes)).isoformat()
    end = now.isoformat()

    trades = await _fetch_alpaca_trades(symbol, start, end, feed, limit=limit)

    # Auto-fallback from SIP to IEX if needed
    if isinstance(trades, dict) and "error" in trades and feed == "sip":
        logger.warning(f"SIP trades failed: {trades.get('error', '?')} — trying IEX fallback")
        trades = await _fetch_alpaca_trades(symbol, start, end, "iex", limit=limit)
        if not isinstance(trades, dict):
            feed = "iex"

    if isinstance(trades, dict) and "error" in trades:
        return trades

    # Classify trades with tick rule
    classified = _classify_trades(trades[-limit:])

    return {
        "trades": classified,
        "count": len(classified),
        "symbol": symbol,
        "feed": feed,
        "live": True,
    }


@router.get("/large-trades")
async def get_large_trades_api(
    symbol: str = Query("SPY"),
    date: Optional[str] = Query(None),
    min_size: int = Query(5000, ge=100),
    feed: str = Query("sip"),
):
    """Fetch today's large trades (potential sweeps/blocks)."""
    if date:
        day = datetime.strptime(date, "%Y-%m-%d")
    else:
        day = datetime.now()

    # Use proper timezone-aware UTC timestamps (same pattern as volume clouds)
    try:
        from zoneinfo import ZoneInfo
        et_tz = ZoneInfo("America/New_York")
    except ImportError:
        et_tz = timezone(timedelta(hours=-4))
    day_date = day.replace(hour=0, minute=0, second=0, microsecond=0)
    start_str = day_date.replace(hour=9, minute=30, tzinfo=et_tz).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = day_date.replace(hour=16, minute=0, tzinfo=et_tz).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    trades = await _fetch_alpaca_trades(symbol, start_str, end_str, feed)
    if isinstance(trades, dict) and "error" in trades:
        return trades

    large = [t for t in trades if t.get("s", 0) >= min_size]
    classified = _classify_trades(large)

    return {
        "trades": classified[-200:],  # cap output size
        "count": len(large),
        "total_large_volume": sum(t.get("s", 0) for t in large),
        "symbol": symbol,
    }


# ============================================================================
# INTERNAL — Alpaca trade fetching (paginated)
# ============================================================================

async def _fetch_alpaca_trades(
    symbol: str,
    start: str,
    end: str,
    feed: str = "sip",
    limit: int = 10000,
) -> list | dict:
    """
    Fetch trades from Alpaca, handling pagination via page_token.
    Returns list of raw trade dicts or {"error": ...}.
    """
    if not ALPACA_KEY or not ALPACA_SECRET:
        return {"error": "ALPACA_API_KEY / ALPACA_SECRET_KEY not set in .env"}

    all_trades: list = []
    page_token: Optional[str] = None
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/trades"
    max_pages = 50  # safety cap (~500K trades max)

    try:
        async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
            for _ in range(max_pages):
                params = {
                    "start": start,
                    "end": end,
                    "feed": feed,
                    "limit": min(limit, 10000),
                    "sort": "asc",
                }
                if page_token:
                    params["page_token"] = page_token

                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 403:
                        return {"error": f"Alpaca 403 Forbidden — your plan may not include '{feed}' feed. Try feed=iex (free)."}
                    if resp.status == 422:
                        return {"error": f"Alpaca 422 — invalid parameters: {await resp.text()}"}
                    if resp.status != 200:
                        return {"error": f"Alpaca {resp.status}: {await resp.text()[:300]}"}

                    data = await resp.json()
                    trades = data.get("trades") or []
                    all_trades.extend(trades)

                    page_token = data.get("next_page_token")
                    if not page_token or len(all_trades) >= limit:
                        break

    except aiohttp.ClientError as e:
        return {"error": f"Alpaca connection error: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}

    return all_trades[:limit]


# ============================================================================
# INTERNAL — Trade classification (tick rule)
# ============================================================================

def _classify_trades(trades: list) -> list:
    """
    Classify each trade as buy/sell using the tick rule.
    Alpaca trade format: {"t": timestamp, "p": price, "s": size, "x": exchange, "c": [conditions]}
    """
    classified = []
    prev_price = 0.0
    prev_side = "neutral"

    for t in trades:
        price = t.get("p", 0)
        size = t.get("s", 0)
        ts = t.get("t", "")

        if price <= 0 or size <= 0:
            continue

        # Tick rule classification
        if price > prev_price:
            side = "buy"
        elif price < prev_price:
            side = "sell"
        else:
            side = prev_side  # inherit if flat

        classified.append({
            "t": ts,
            "p": round(price, 2),
            "s": size,
            "side": side,
            "x": t.get("x", ""),
        })

        prev_price = price
        prev_side = side

    return classified


# ============================================================================
# INTERNAL — Aggregate into volume cloud cells
# ============================================================================

def _aggregate_clouds(trades: list, bar_minutes: int, min_volume: int) -> dict:
    """
    Group classified trades into (time_bar, price_level) cells.
    Returns cells list + bar summaries for the frontend.
    """
    if not trades:
        return {"cells": [], "bars_summary": [], "price_range": [0, 0]}

    # Buckets: key = (bar_start_iso, price_rounded)
    buckets: dict = {}
    bar_totals: dict = {}  # bar_start -> total_vol

    min_price = float("inf")
    max_price = 0.0

    for t in trades:
        ts_str = t["t"]
        price = t["p"]
        size = t["s"]
        side = t["side"]

        # Parse timestamp and compute bar start
        try:
            # Alpaca timestamps: "2026-03-25T10:30:00.123456789Z" or similar
            ts_clean = ts_str.replace("Z", "+00:00")
            if "." in ts_clean:
                # Truncate nanoseconds to microseconds
                parts = ts_clean.split(".")
                frac = parts[1].split("+")[0].split("-")[0][:6]
                tz_part = "+" + parts[1].split("+")[1] if "+" in parts[1] else "-" + parts[1].split("-")[-1]
                ts_clean = f"{parts[0]}.{frac}{tz_part}"
            dt = datetime.fromisoformat(ts_clean)
        except (ValueError, IndexError):
            continue

        # Round to bar start
        total_minutes = dt.hour * 60 + dt.minute
        bar_start_min = (total_minutes // bar_minutes) * bar_minutes
        bar_h, bar_m = divmod(bar_start_min, 60)
        bar_time = dt.replace(hour=bar_h, minute=bar_m, second=0, microsecond=0)
        bar_key = bar_time.isoformat()

        # Price level (round to nearest cent)
        price_level = round(price, 2)
        cell_key = (bar_key, price_level)

        min_price = min(min_price, price_level)
        max_price = max(max_price, price_level)

        if cell_key not in buckets:
            buckets[cell_key] = {"buy": 0, "sell": 0, "neutral": 0, "total": 0}
        buckets[cell_key][side] += size
        buckets[cell_key]["total"] += size

        bar_totals[bar_key] = bar_totals.get(bar_key, 0) + size

    # Convert to list for JSON
    cells = []
    for (bar_key, price_level), vol in buckets.items():
        if vol["total"] < min_volume:
            continue
        bar_total = bar_totals.get(bar_key, 1)
        delta = vol["buy"] - vol["sell"]
        cells.append({
            "time": bar_key,
            "price": price_level,
            "total_vol": vol["total"],
            "buy_vol": vol["buy"],
            "sell_vol": vol["sell"],
            "delta": delta,
            "pct_of_bar": round(vol["total"] / bar_total * 100, 2) if bar_total else 0,
            # Delta ratio: -1 (all sell) to +1 (all buy)
            "delta_ratio": round(delta / vol["total"], 3) if vol["total"] else 0,
        })

    # Bar summaries for the frontend
    bars_summary = []
    for bar_key in sorted(bar_totals.keys()):
        bar_cells = [c for c in cells if c["time"] == bar_key]
        buy_total = sum(c["buy_vol"] for c in bar_cells)
        sell_total = sum(c["sell_vol"] for c in bar_cells)
        bars_summary.append({
            "time": bar_key,
            "total_vol": bar_totals[bar_key],
            "buy_vol": buy_total,
            "sell_vol": sell_total,
            "delta": buy_total - sell_total,
            "levels": len(bar_cells),
        })

    return {
        "cells": cells,
        "bars_summary": bars_summary,
        "price_range": [min_price, max_price],
    }


# ============================================================================
# INTEGRATION
# ============================================================================

def include_orderflow_api(app):
    """Include order flow API routes in FastAPI app."""
    app.include_router(router)
