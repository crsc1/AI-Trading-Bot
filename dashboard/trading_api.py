"""
Trading API routes — Alpaca paper trading account management.

Endpoints:
  /api/trading/account     — Account balance, equity, buying power
  /api/trading/positions   — Open positions (stocks + options) with live P&L
  /api/trading/orders      — Recent orders with status
  /api/trading/history     — Portfolio equity history for P&L chart
"""

from fastapi import APIRouter, Query
from datetime import datetime, timezone
import logging
import aiohttp
from .config import cfg

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trading", tags=["trading"])

ALPACA_TRADING_URL = cfg.ALPACA_BASE_URL
ALPACA_DATA_URL = "https://data.alpaca.markets"
ALPACA_KEY = cfg.ALPACA_API_KEY
ALPACA_SECRET = cfg.ALPACA_SECRET_KEY
ALPACA_HEADERS = cfg.ALPACA_HEADERS


# ============================================================================
# ACCOUNT — balance, equity, buying power
# ============================================================================

@router.get("/account")
async def get_account():
    """
    Get Alpaca paper trading account details.
    Returns equity, cash, buying power, and daily P&L.
    """
    if not ALPACA_KEY:
        return {"error": "ALPACA_API_KEY not configured"}

    try:
        url = f"{ALPACA_TRADING_URL}/account"
        async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {"error": f"Alpaca {resp.status}: {text[:200]}"}
                data = await resp.json()

                equity = float(data.get("equity", 0))
                last_equity = float(data.get("last_equity", 0))
                daily_pnl = round(equity - last_equity, 2) if last_equity else 0
                daily_pnl_pct = (
                    round((daily_pnl / last_equity) * 100, 2) if last_equity else 0
                )

                return {
                    "equity": equity,
                    "cash": float(data.get("cash", 0)),
                    "buying_power": float(data.get("buying_power", 0)),
                    "portfolio_value": float(data.get("portfolio_value", 0)),
                    "last_equity": last_equity,
                    "daily_pnl": daily_pnl,
                    "daily_pnl_pct": daily_pnl_pct,
                    "long_market_value": float(
                        data.get("long_market_value", 0)
                    ),
                    "short_market_value": float(
                        data.get("short_market_value", 0)
                    ),
                    "options_buying_power": float(
                        data.get("options_buying_power", 0)
                    ),
                    "options_market_value": float(
                        data.get("options_market_value", 0)
                    ),
                    "pattern_day_trader": data.get(
                        "pattern_day_trader", False
                    ),
                    "daytrade_count": int(data.get("daytrade_count", 0)),
                    "account_number": data.get("account_number", ""),
                    "status": data.get("status", ""),
                    "trading_blocked": data.get("trading_blocked", False),
                    "account_blocked": data.get("account_blocked", False),
                }
    except Exception as e:
        logger.error(f"Account fetch error: {e}")
        return {"error": str(e)}


# ============================================================================
# POSITIONS — open positions with live P&L
# ============================================================================

@router.get("/positions")
async def get_positions():
    """
    Get all open positions (stocks + options) with live unrealized P&L.
    """
    if not ALPACA_KEY:
        return {"error": "ALPACA_API_KEY not configured", "positions": []}

    try:
        url = f"{ALPACA_TRADING_URL}/positions"
        async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {
                        "error": f"Alpaca {resp.status}: {text[:200]}",
                        "positions": [],
                    }
                raw = await resp.json()

                positions = []
                total_unrealized = 0
                total_market_value = 0

                for pos in raw:
                    symbol = pos.get("symbol", "")
                    asset_class = pos.get("asset_class", "us_equity")

                    qty = float(pos.get("qty", 0))
                    avg_entry = float(pos.get("avg_entry_price", 0))
                    current_price = float(pos.get("current_price", 0))
                    market_value = float(pos.get("market_value", 0))
                    unrealized_pl = float(pos.get("unrealized_pl", 0))
                    unrealized_plpc = float(
                        pos.get("unrealized_plpc", 0)
                    )
                    cost_basis = float(pos.get("cost_basis", 0))
                    side = pos.get("side", "long")

                    # For options, parse the OCC symbol
                    option_info = None
                    if asset_class == "us_option":
                        option_info = _parse_option_symbol(symbol)

                    positions.append(
                        {
                            "symbol": symbol,
                            "asset_class": asset_class,
                            "qty": qty,
                            "side": side,
                            "avg_entry_price": avg_entry,
                            "current_price": current_price,
                            "market_value": market_value,
                            "cost_basis": cost_basis,
                            "unrealized_pl": round(unrealized_pl, 2),
                            "unrealized_plpc": round(
                                unrealized_plpc * 100, 2
                            ),
                            "option_info": option_info,
                        }
                    )

                    total_unrealized += unrealized_pl
                    total_market_value += market_value

                return {
                    "positions": positions,
                    "count": len(positions),
                    "total_unrealized_pl": round(total_unrealized, 2),
                    "total_market_value": round(total_market_value, 2),
                }
    except Exception as e:
        logger.error(f"Positions fetch error: {e}")
        return {"error": str(e), "positions": []}


def _parse_option_symbol(sym: str) -> dict:
    """Parse OCC option symbol: SPY250328C00570000"""
    import re

    m = re.match(r"^([A-Z]+)(\d{6})([CP])(\d{8})$", sym)
    if not m:
        return {}
    root, date_str, right, strike_raw = m.groups()
    exp = f"20{date_str[:2]}-{date_str[2:4]}-{date_str[4:6]}"
    strike = int(strike_raw) / 1000.0
    return {
        "root": root,
        "expiration": exp,
        "right": "Call" if right == "C" else "Put",
        "strike": strike,
    }


# ============================================================================
# ORDERS — recent orders with status
# ============================================================================

@router.get("/orders")
async def get_orders(
    status: str = Query("all", description="open, closed, all"),
    limit: int = Query(50, ge=1, le=500),
):
    """
    Get recent orders from Alpaca paper account.
    """
    if not ALPACA_KEY:
        return {"error": "ALPACA_API_KEY not configured", "orders": []}

    try:
        url = f"{ALPACA_TRADING_URL}/orders"
        params = {
            "status": status,
            "limit": limit,
            "direction": "desc",
            "nested": "true",
        }
        async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {
                        "error": f"Alpaca {resp.status}: {text[:200]}",
                        "orders": [],
                    }
                raw = await resp.json()

                orders = []
                for o in raw:
                    filled_qty = float(o.get("filled_qty", 0) or 0)
                    filled_avg = float(
                        o.get("filled_avg_price", 0) or 0
                    )
                    qty = float(o.get("qty", 0) or 0)

                    order = {
                        "id": o.get("id", ""),
                        "symbol": o.get("symbol", ""),
                        "asset_class": o.get("asset_class", "us_equity"),
                        "side": o.get("side", ""),
                        "type": o.get("type", ""),
                        "time_in_force": o.get("time_in_force", ""),
                        "qty": qty,
                        "filled_qty": filled_qty,
                        "limit_price": float(
                            o.get("limit_price", 0) or 0
                        ),
                        "stop_price": float(
                            o.get("stop_price", 0) or 0
                        ),
                        "filled_avg_price": filled_avg,
                        "status": o.get("status", ""),
                        "created_at": o.get("created_at", ""),
                        "filled_at": o.get("filled_at", ""),
                        "canceled_at": o.get("canceled_at", ""),
                        "order_class": o.get("order_class", ""),
                    }

                    # For options, parse the OCC symbol
                    if order["asset_class"] == "us_option":
                        order["option_info"] = _parse_option_symbol(
                            order["symbol"]
                        )

                    # Legs for bracket/OCO orders
                    legs = o.get("legs")
                    if legs:
                        order["legs"] = [
                            {
                                "id": leg.get("id", ""),
                                "symbol": leg.get("symbol", ""),
                                "side": leg.get("side", ""),
                                "qty": float(leg.get("qty", 0) or 0),
                                "type": leg.get("type", ""),
                                "status": leg.get("status", ""),
                                "filled_avg_price": float(
                                    leg.get("filled_avg_price", 0) or 0
                                ),
                            }
                            for leg in legs
                        ]

                    orders.append(order)

                return {"orders": orders, "count": len(orders)}
    except Exception as e:
        logger.error(f"Orders fetch error: {e}")
        return {"error": str(e), "orders": []}


# ============================================================================
# PORTFOLIO HISTORY — equity curve for P&L chart
# ============================================================================

@router.get("/history")
async def get_portfolio_history(
    period: str = Query("1W", description="1D, 1W, 1M, 3M, 1A"),
    timeframe: str = Query("1D", description="1Min, 5Min, 15Min, 1H, 1D"),
):
    """
    Get portfolio equity history for P&L chart.
    """
    if not ALPACA_KEY:
        return {"error": "ALPACA_API_KEY not configured"}

    try:
        url = f"{ALPACA_TRADING_URL}/account/portfolio/history"
        params = {"period": period, "timeframe": timeframe}
        async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {"error": f"Alpaca {resp.status}: {text[:200]}"}
                data = await resp.json()

                timestamps = data.get("timestamp", [])
                equities = data.get("equity", [])
                pnls = data.get("profit_loss", [])
                pnl_pcts = data.get("profit_loss_pct", [])

                points = []
                for i, ts in enumerate(timestamps):
                    if ts is None:
                        continue
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    points.append(
                        {
                            "time": dt.strftime("%Y-%m-%d")
                            if timeframe == "1D"
                            else int(ts),
                            "equity": equities[i]
                            if i < len(equities) and equities[i]
                            else None,
                            "pnl": pnls[i]
                            if i < len(pnls) and pnls[i]
                            else None,
                            "pnl_pct": pnl_pcts[i]
                            if i < len(pnl_pcts) and pnl_pcts[i]
                            else None,
                        }
                    )

                base_value = float(data.get("base_value", 0))
                return {
                    "points": points,
                    "base_value": base_value,
                    "timeframe": data.get("timeframe", timeframe),
                }
    except Exception as e:
        logger.error(f"Portfolio history error: {e}")
        return {"error": str(e)}
