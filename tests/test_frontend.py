"""
Frontend smoke tests for the current Solid/Vite SPA.

These tests intentionally exercise the new app shell instead of the retired
legacy dashboard HTML. A lightweight Vite dev server is started for the
session, and Playwright checks the rendered UI with backend API calls mocked.
"""

from __future__ import annotations

import os
import socket
import ssl
import subprocess
import time
import urllib.request
from contextlib import closing
from pathlib import Path

import pytest
from playwright.async_api import Browser, Page, async_playwright


PROJECT_ROOT = Path(__file__).parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 4173
FRONTEND_URL = f"https://{FRONTEND_HOST}:{FRONTEND_PORT}"


def _is_port_open(host: str, port: int) -> bool:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def _wait_for_http(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    ssl_context = ssl._create_unverified_context()
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1, context=ssl_context):
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for frontend server at {url}")


@pytest.fixture(scope="session")
def frontend_server():
    """Start a Vite dev server for the SPA under test."""
    if _is_port_open(FRONTEND_HOST, FRONTEND_PORT):
        _wait_for_http(FRONTEND_URL)
        yield FRONTEND_URL
        return

    env = os.environ.copy()
    env["BROWSER"] = "none"
    env["CI"] = "1"

    proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "--host", FRONTEND_HOST, "--port", str(FRONTEND_PORT), "--strictPort"],
        cwd=FRONTEND_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_http(FRONTEND_URL)
        yield FRONTEND_URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


@pytest.fixture
async def browser() -> Browser:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            yield browser
        finally:
            await browser.close()


@pytest.fixture
async def page(browser: Browser, frontend_server: str) -> Page:
    context = await browser.new_context(ignore_https_errors=True)
    page = await context.new_page()

    async def handle_api(route):
        path = route.request.url.split("/api/", 1)[1]
        body = {}

        if path.startswith("bars"):
            body = {"bars": []}
        elif path.startswith("quote"):
            body = {"bid": 0, "ask": 0, "last": 0}
        elif path.startswith("options/expirations"):
            body = {"response": []}
        elif path.startswith("options/chain"):
            body = {"calls": [], "puts": []}
        elif path.startswith("options/snapshot"):
            body = {}
        elif path.startswith("signals/volatility-advisor"):
            body = {}
        elif path.startswith("signals/levels"):
            body = {"levels": {}}
        elif path.startswith("signals/gex"):
            body = {}
        elif path.startswith("signals/sectors"):
            body = {}
        elif path.startswith("signals/events"):
            body = {}
        elif path.startswith("orderflow/clouds"):
            body = {"clouds": [], "bars_summary": [], "meta": {}}
        elif path.startswith("brain/scanner/alerts"):
            body = {"alerts": []}
        elif path.startswith("brain/scanner/stats"):
            body = {"subscribed_symbols": [], "total_alerts": 0}

        await route.fulfill(status=200, content_type="application/json", body=__import__("json").dumps(body))

    await page.route("**/api/**", handle_api)
    await page.goto(frontend_server, wait_until="domcontentloaded")
    yield page
    await page.close()
    await context.close()


@pytest.mark.asyncio
async def test_app_shell_renders(page: Page):
    await page.wait_for_selector('[data-testid="app-shell"]')
    assert await page.title() == "AI Trading Bot"
    assert await page.get_by_test_id("sidebar").is_visible()
    assert await page.get_by_test_id("status-bar").is_visible()
    assert await page.get_by_test_id("ticker-selector").inner_text() == "SPY▾"
    assert await page.get_by_test_id("dashboard-title").inner_text() == "Dashboard"


@pytest.mark.asyncio
async def test_sidebar_contains_current_spa_routes(page: Page):
    for test_id in [
        "nav-dashboard",
        "nav-charts",
        "nav-flow",
        "nav-agent",
        "nav-scanner",
        "nav-reference",
    ]:
        assert await page.get_by_test_id(test_id).is_visible()


@pytest.mark.asyncio
async def test_sidebar_toggle_expands_labels(page: Page):
    if not await page.get_by_test_id("nav-dashboard").get_by_text("Dashboard", exact=True).is_visible():
        await page.get_by_test_id("sidebar-toggle").click()
        await page.wait_for_timeout(150)
    assert await page.get_by_test_id("nav-dashboard").get_by_text("Dashboard", exact=True).is_visible()
    assert await page.get_by_test_id("nav-agent").get_by_text("AI Research", exact=True).is_visible()


@pytest.mark.asyncio
async def test_route_navigation_uses_current_pages(page: Page):
    await page.get_by_test_id("nav-scanner").click()
    await page.wait_for_url(f"{FRONTEND_URL}/scanner")
    assert await page.get_by_text("Scanner Workspace", exact=True).is_visible()

    await page.get_by_test_id("nav-reference").click()
    await page.wait_for_url(f"{FRONTEND_URL}/reference")
    assert await page.get_by_text("Options Chain", exact=True).is_visible()
    assert await page.get_by_text("Key Levels", exact=True).is_visible()

    await page.get_by_test_id("nav-agent").click()
    await page.wait_for_url(f"{FRONTEND_URL}/agent")
    assert await page.get_by_test_id("agent-tab-brain").is_visible()
    assert await page.get_by_test_id("agent-tab-chat").is_visible()


@pytest.mark.asyncio
async def test_dashboard_empty_states_render_without_backend(page: Page):
    dashboard = page.get_by_test_id("dashboard-page")
    assert await dashboard.get_by_text("No open positions", exact=True).is_visible()
    assert await dashboard.get_by_text("No signals yet", exact=True).is_visible()


@pytest.mark.asyncio
async def test_ticker_selector_can_switch_symbols(page: Page):
    await page.get_by_test_id("ticker-selector").click()
    await page.get_by_test_id("ticker-input").fill("AMD")
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(200)
    assert "AMD" in await page.get_by_test_id("ticker-selector").inner_text()


@pytest.mark.asyncio
async def test_flow_view_toggle_switches_modes(page: Page):
    await page.get_by_test_id("nav-flow").click()
    await page.wait_for_url(f"{FRONTEND_URL}/flow")
    assert await page.get_by_test_id("flow-view-options").is_visible()
    await page.get_by_test_id("flow-view-equity").click()
    assert await page.get_by_test_id("flow-view-equity").is_visible()
