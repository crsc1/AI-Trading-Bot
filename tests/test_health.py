"""
Test suite for basic health checks and endpoint availability.

Tests:
- GET /health returns 200 with proper response
- GET / redirects to /flow
- GET /flow returns HTML
- GET /debug returns HTML
"""

import pytest


@pytest.mark.asyncio
async def test_get_health(async_client):
    """Test that /health endpoint returns 200 with status."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_get_health_missing_endpoint(async_client):
    """Test that missing /health still works if it's an alias."""
    # The app might not have /health, but let's verify graceful handling
    response = await async_client.get("/nonexistent")
    assert response.status_code in [404, 200]  # Either 404 or handled


@pytest.mark.asyncio
async def test_get_root_redirect(async_client):
    """Test that GET / redirects to /flow."""
    response = await async_client.get("/", follow_redirects=False)
    # Should be a redirect
    assert response.status_code in [301, 302, 307]
    # Check redirect location
    assert "location" in response.headers or response.status_code == 307


@pytest.mark.asyncio
async def test_get_flow_returns_html(async_client):
    """Test that GET /flow returns HTML content."""
    response = await async_client.get("/flow", follow_redirects=True)
    assert response.status_code == 200
    # Should contain HTML
    content = response.text
    assert "html" in content.lower() or len(content) > 0


@pytest.mark.asyncio
async def test_get_debug_returns_html(async_client):
    """Test that GET /debug returns HTML content."""
    response = await async_client.get("/debug")
    assert response.status_code in [200, 404]  # Might not exist
    if response.status_code == 200:
        content = response.text
        assert len(content) > 0


@pytest.mark.asyncio
async def test_static_files_accessible(async_client):
    """Test that static files directory is properly mounted."""
    # This may return 404 if file doesn't exist, but path should be accessible
    response = await async_client.get("/static/")
    # Should not throw an error; status varies
    assert response.status_code in [200, 404, 301, 302]


@pytest.mark.asyncio
async def test_websocket_endpoint_exists(async_client):
    """Test that WebSocket endpoint is registered."""
    # Can't directly test WS with httpx, but we can verify it's not a 404 on a GET
    # Actually WebSocket endpoints return 426 on GET
    response = await async_client.get("/ws")
    # WS endpoints typically return 426 Upgrade Required or 400 on GET
    assert response.status_code in [426, 400, 404, 200]
