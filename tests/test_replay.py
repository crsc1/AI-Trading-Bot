"""Tests for the signal replay API endpoint."""

import pytest


@pytest.mark.asyncio
async def test_replay_default_date(async_client):
    """Test replay endpoint returns most recent date by default."""
    response = await async_client.get("/api/signals/replay")
    assert response.status_code == 200
    data = response.json()
    assert "signals" in data
    assert "summary" in data
    assert "available_dates" in data


@pytest.mark.asyncio
async def test_replay_specific_date(async_client):
    """Test replay with a specific date."""
    response = await async_client.get("/api/signals/replay?date=2026-04-01")
    assert response.status_code == 200
    data = response.json()
    assert "signals" in data


@pytest.mark.asyncio
async def test_replay_direction_filter(async_client):
    """Test replay with direction filter."""
    response = await async_client.get("/api/signals/replay?direction=BUY_CALL")
    assert response.status_code == 200
    data = response.json()
    # All signals should be BUY_CALL
    for sig in data.get("signals", []):
        assert sig["direction"] == "BUY_CALL"


@pytest.mark.asyncio
async def test_replay_nonexistent_date(async_client):
    """Test replay with a date that has no signals."""
    response = await async_client.get("/api/signals/replay?date=2020-01-01")
    assert response.status_code == 200
    data = response.json()
    assert data["signals"] == []
    assert data["summary"]["total"] == 0
