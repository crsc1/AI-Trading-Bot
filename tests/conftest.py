"""
Pytest configuration and shared fixtures for API tests.

Provides:
- async_client: AsyncClient connected to FastAPI app
- Mock data fixtures for bars, quotes, options chains
"""

import pytest
import pytest_asyncio
from typing import List, Dict
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import os
import sys

# Ensure project is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set required environment variables before importing app
os.environ.setdefault("ALPACA_API_KEY", "test_key")
os.environ.setdefault("ALPACA_SECRET_KEY", "test_secret")
os.environ.setdefault("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")
os.environ.setdefault("NEWSAPI_KEY", "test_newsapi")


@pytest_asyncio.fixture
async def async_client():
    """
    Create an AsyncClient connected to the FastAPI app.

    Mocks Alpaca connections and external dependencies.
    """
    from httpx import AsyncClient, ASGITransport

    # Mock Alpaca trading client
    with patch("dashboard.app.os.getenv") as mock_getenv:
        mock_getenv.return_value = "test_value"

        # Import app after mocking
        from dashboard.app import app

        # Mock agent startup
        with patch("dashboard.app.start_agents") as mock_start:
            mock_start.return_value = None

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client


@pytest.fixture
def mock_bar_data_1m() -> List[Dict]:
    """1-minute bar data for market structure tests."""
    base_time = datetime(2026, 3, 26, 9, 30, 0, tzinfo=timezone.utc)
    bars = []

    for i in range(20):
        time = base_time + timedelta(minutes=i)
        # Simulate realistic SPY price movement
        base_price = 550.0
        price_offset = 0.1 * (i - 10)  # Trend upward

        bars.append({
            "t": time.isoformat(),
            "time": time,
            "o": round(base_price + price_offset, 2),
            "h": round(base_price + price_offset + 0.25, 2),
            "l": round(base_price + price_offset - 0.15, 2),
            "c": round(base_price + price_offset + 0.10, 2),
            "v": 100000 + i * 5000,
            "vw": round(base_price + price_offset, 4),  # Volume weighted price
            "n": 500 + i * 50,  # Trade count
        })

    return bars


@pytest.fixture
def mock_bar_data_daily() -> List[Dict]:
    """Daily bar data for pivot point and market level tests."""
    bars = []
    base_time = datetime(2026, 3, 25, 0, 0, 0, tzinfo=timezone.utc)

    for i in range(3):
        day = base_time - timedelta(days=2 - i)
        bars.append({
            "t": day.isoformat(),
            "time": day,
            "o": 549.50 - i * 0.5,
            "h": 550.75 - i * 0.3,
            "l": 548.25 - i * 0.7,
            "c": 549.80 - i * 0.4,
            "v": 50000000 + i * 1000000,
            "vw": 549.50 - i * 0.4,
            "n": 250000 + i * 10000,
        })

    return bars


@pytest.fixture
def mock_quote() -> Dict:
    """Current quote data."""
    return {
        "bid": 549.95,
        "ask": 550.05,
        "last": 550.00,
        "price": 550.00,
        "prev_close": 549.50,
        "bid_size": 500,
        "ask_size": 400,
        "update_time": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def mock_options_chain() -> List[Dict]:
    """Mock SPY options chain data."""
    expiration = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    strikes = []
    current_price = 550.0

    for strike in range(530, 571, 5):
        # Call option
        strikes.append({
            "symbol": f"SPY {expiration[2:4]}{expiration[5:7]}{expiration[8:10]}C{strike}",
            "strike": strike,
            "type": "call",
            "expiration": expiration,
            "bid": max(current_price - strike, 0) + 0.25,
            "ask": max(current_price - strike, 0) + 0.50,
            "last": max(current_price - strike, 0) + 0.35,
            "volume": 500 + strike * 10,
            "open_interest": 1000 + strike * 20,
            "iv": 0.25 + (strike - current_price) * 0.001,
            "delta": min(1.0, max(0.0, 0.5 + (current_price - strike) * 0.02)),
            "gamma": 0.02,
            "theta": -0.05,
            "vega": 0.15,
        })

        # Put option
        strikes.append({
            "symbol": f"SPY {expiration[2:4]}{expiration[5:7]}{expiration[8:10]}P{strike}",
            "strike": strike,
            "type": "put",
            "expiration": expiration,
            "bid": max(strike - current_price, 0) + 0.25,
            "ask": max(strike - current_price, 0) + 0.50,
            "last": max(strike - current_price, 0) + 0.35,
            "volume": 300 + strike * 5,
            "open_interest": 800 + strike * 15,
            "iv": 0.25 + (current_price - strike) * 0.001,
            "delta": max(-1.0, min(0.0, -0.5 - (current_price - strike) * 0.02)),
            "gamma": 0.02,
            "theta": -0.05,
            "vega": 0.15,
        })

    return strikes


@pytest.fixture
def mock_trades() -> List[Dict]:
    """Mock tick-level trade data for order flow analysis."""
    base_time = datetime(2026, 3, 26, 9, 30, 0, tzinfo=timezone.utc)
    trades = []

    for i in range(50):
        time = base_time + timedelta(milliseconds=i * 100)
        # Simulate trading with slight upward bias
        side = "buy" if i % 3 < 2 else "sell"

        trades.append({
            "t": time.isoformat(),
            "time": time,
            "p": round(550.0 + i * 0.02, 2),
            "price": round(550.0 + i * 0.02, 2),
            "s": 100 + i % 50,
            "size": 100 + i % 50,
            "side": side,
            "exchange": "SMART",
            "conditions": "regular_trade",
        })

    return trades


@pytest.fixture
def mock_position() -> Dict:
    """Mock trading position."""
    return {
        "symbol": "SPY",
        "qty": 100,
        "avg_fill_price": 549.50,
        "market_value": 55000.00,
        "cost_basis": 54950.00,
        "unrealized_pl": 50.00,
        "unrealized_plpc": 0.0009,
        "current_price": 550.00,
        "side": "long",
    }


@pytest.fixture
def mock_account() -> Dict:
    """Mock trading account info."""
    return {
        "id": "test_account_123",
        "account_number": "123456",
        "buying_power": 100000.00,
        "cash": 50000.00,
        "portfolio_value": 150000.00,
        "multiplier": "2",
        "account_type": "margin",
        "status": "ACTIVE",
        "created_at": "2020-01-01T00:00:00Z",
        "shorting_enabled": True,
        "day_trading_buying_power": 100000.00,
        "regt_buying_power": 75000.00,
        "daytrader": False,
    }


@pytest.fixture
def mock_market_levels(mock_bar_data_1m, mock_bar_data_daily, mock_quote):
    """Create pre-computed market levels."""
    from dashboard.market_levels import compute_market_levels

    return compute_market_levels(
        bars_1m=mock_bar_data_1m,
        bars_daily=mock_bar_data_daily,
        quote=mock_quote,
    )


@pytest.fixture
def mock_signal() -> Dict:
    """Mock trading signal."""
    return {
        "id": "signal_123",
        "symbol": "SPY",
        "direction": "bullish",
        "confidence": 0.75,
        "entry_price": 550.00,
        "target_price": 552.00,
        "stop_price": 548.50,
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "expiration": "2026-03-27",
        "dte": 1,
        "strike": 550,
        "contract_type": "call",
        "strategy": "long_call",
        "confluences": ["VWAP", "ORB_Breakout", "CVD_Rising"],
        "order_flow_bias": "bullish",
        "risk_score": 0.25,
    }


pytest_plugins = ["pytest_asyncio"]
