from datetime import datetime, timedelta, timezone

import pytest


def _make_intraday_bars(base_price: float) -> list[dict]:
    base_time = datetime(2026, 4, 9, 14, 30, tzinfo=timezone.utc)
    bars = []
    for i in range(20):
        close = round(base_price + (i * 0.1), 2)
        bars.append(
            {
                "time": (base_time + timedelta(minutes=i)).isoformat(),
                "high": round(close + 0.2, 2),
                "low": round(close - 0.2, 2),
                "close": close,
                "volume": 1000 + (i * 25),
                "vwap": round(close - 0.05, 4),
            }
        )
    return bars


def _make_daily_bars(base_price: float) -> list[dict]:
    base_day = datetime(2026, 4, 7, tzinfo=timezone.utc)
    bars = []
    for i in range(3):
        close = round(base_price + (i * 0.5), 2)
        bars.append(
            {
                "time": (base_day + timedelta(days=i)).isoformat(),
                "high": round(close + 1.0, 2),
                "low": round(close - 1.0, 2),
                "close": close,
            }
        )
    return bars


@pytest.mark.asyncio
async def test_signal_levels_follow_requested_symbol(async_client, monkeypatch):
    from dashboard import signal_api

    requested_symbols = []

    async def fake_fetch_market_data(app_request=None, symbol=None):
        requested_symbols.append(symbol)
        base_price = 600.0 if symbol == "SPY" else 500.0
        return {
            "bars_1m": _make_intraday_bars(base_price),
            "bars_daily": _make_daily_bars(base_price),
            "quote": {
                "bid": round(base_price - 0.05, 2),
                "ask": round(base_price + 0.05, 2),
                "last": base_price,
                "prev_close": round(base_price - 1.0, 2),
            },
            "market": {"price": base_price, "prev_close": round(base_price - 1.0, 2)},
        }

    monkeypatch.setattr(signal_api.engine, "fetch_market_data", fake_fetch_market_data)

    spy_response = await async_client.get("/api/signals/levels?symbol=SPY")
    qqq_response = await async_client.get("/api/signals/levels?symbol=QQQ")

    assert spy_response.status_code == 200
    assert qqq_response.status_code == 200

    spy_levels = spy_response.json()["levels"]
    qqq_levels = qqq_response.json()["levels"]

    assert requested_symbols == ["SPY", "QQQ"]
    assert spy_levels["current_price"] == 600.0
    assert qqq_levels["current_price"] == 500.0
    assert spy_levels["vwap"] != qqq_levels["vwap"]
