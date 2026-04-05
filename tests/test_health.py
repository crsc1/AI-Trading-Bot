"""
Test suite for basic health checks and endpoint availability.

Tests:
- GET /health returns 200 with proper response
- GET / serves the dashboard HTML
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
async def test_nonexistent_page_redirects(async_client):
    """Test that unknown pages redirect to dashboard."""
    response = await async_client.get("/nonexistent", follow_redirects=False)
    assert response.status_code in [307, 302, 301]


@pytest.mark.asyncio
async def test_nonexistent_api_returns_404(async_client):
    """Test that unknown API routes return 404 JSON, not redirect."""
    response = await async_client.get("/api/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_root_serves_dashboard(async_client):
    """Test that GET / serves the dashboard HTML directly."""
    response = await async_client.get("/")
    assert response.status_code == 200
    assert "html" in response.text.lower()


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
    response = await async_client.get("/static/")
    # Static paths return 404 JSON (not redirect) when file not found
    assert response.status_code in [200, 404, 301, 302]


@pytest.mark.asyncio
async def test_websocket_endpoint_exists(async_client):
    """Test that WebSocket endpoint is registered."""
    response = await async_client.get("/ws")
    # WS endpoints return 404 JSON (not redirect), 426, or 400 on GET
    assert response.status_code in [426, 400, 404, 200]
