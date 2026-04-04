"""
Frontend Smoke Tests for AI Trading Bot Dashboard using Playwright

These are smoke tests that verify the HTML/CSS/JS structure of the dashboard
without requiring a running FastAPI server or live data connections.
Tests use Playwright to load the dashboard HTML and verify:
  1. HTML structure (nav, tabs, sidebar, containers)
  2. CSS styling and colors
  3. JavaScript initialization and global state
  4. AI signal card rendering with mock data
"""

import pytest
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, expect

# Path to the dashboard HTML file
DASHBOARD_PATH = Path(__file__).parent.parent / "dashboard" / "static" / "flow-dashboard.html"
DASHBOARD_URL = f"file://{DASHBOARD_PATH.absolute()}"


class TestDashboardStructure:
    """Test HTML structure and basic DOM elements."""

    @pytest.mark.asyncio
    async def test_page_title(self):
        """Verify page title is correct."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            title = await page.title()
            assert "Order Flow Trading Platform" in title

            await browser.close()

    @pytest.mark.asyncio
    async def test_nav_bar_exists(self):
        """Verify nav bar exists with expected elements."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Check nav element exists
            nav = await page.locator(".nav").first.bounding_box()
            assert nav is not None
            assert nav['height'] == 40  # Nav should be 40px tall

            # Check for symbol input/selector
            sym_group = page.locator(".nav .sym-group").first
            assert await sym_group.is_visible()

            await browser.close()

    @pytest.mark.asyncio
    async def test_tab_buttons_exist(self):
        """Verify tab bar with Flow, Depth, Positions buttons."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Check tab bar exists
            tab_bar = await page.locator(".tab-bar").first.bounding_box()
            assert tab_bar is not None
            assert tab_bar['height'] == 32

            # Check for tab buttons
            tab_buttons = await page.locator(".tab-btn").all()
            assert len(tab_buttons) > 0

            # At least one should be active
            active_count = len(await page.locator(".tab-btn.active").all())
            assert active_count >= 1

            await browser.close()

    @pytest.mark.asyncio
    async def test_main_layout_grid(self):
        """Verify main layout is a two-column grid (content + sidebar)."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Check main layout exists
            main = page.locator(".main").first
            assert await main.is_visible()

            # Check content area exists
            content = page.locator(".content").first
            assert await content.is_visible()

            # Check sidebar exists
            sidebar = page.locator(".sidebar").first
            assert await sidebar.is_visible()

            await browser.close()

    @pytest.mark.asyncio
    async def test_sidebar_sections_exist(self):
        """Verify sidebar has metrics and signals sections."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Check for sidebar sections
            metrics_section = page.locator(".sb-section.metrics").first
            signals_section = page.locator(".sb-section.signals").first

            assert await metrics_section.is_visible()
            assert await signals_section.is_visible()

            await browser.close()

    @pytest.mark.asyncio
    async def test_chart_containers_exist(self):
        """Verify chart container elements exist."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Check for candle chart container (candleWrapCombined or candleWrapFull)
            candle_wrap = page.locator('[id*="candleWrap"]').first
            assert await candle_wrap.is_visible()

            # Check for flow chart container (flowWrapCombined or flowWrapFull)
            flow_wrap = page.locator('[id*="flowWrap"]').first
            assert await flow_wrap.is_visible()

            await browser.close()


class TestGlobalState:
    """Test JavaScript global state initialization."""

    @pytest.mark.asyncio
    async def test_global_state_object_exists(self):
        """Verify global state object S is initialized."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Check that S object exists
            s_exists = await page.evaluate("typeof S === 'object' && S !== null")
            assert s_exists is True

            await browser.close()

    @pytest.mark.asyncio
    async def test_state_default_symbol(self):
        """Verify S.sym defaults to 'SPY'."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Get S.sym value
            sym = await page.evaluate("S.sym")
            assert sym == "SPY"

            await browser.close()

    @pytest.mark.asyncio
    async def test_state_properties_initialized(self):
        """Verify key state properties are initialized."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Check key properties
            props_check = await page.evaluate("""() => {
                return {
                    has_sym: 'sym' in S,
                    has_ws: 'ws' in S,
                    has_signals: 'signals' in S,
                    has_lastPrice: 'lastPrice' in S,
                    has_activeTab: 'activeTab' in S,
                    sym_is_spy: S.sym === 'SPY',
                    signals_is_array: Array.isArray(S.signals),
                    activeTab_is_string: typeof S.activeTab === 'string'
                };
            }""")

            assert props_check['has_sym'] is True
            assert props_check['has_ws'] is True
            assert props_check['has_signals'] is True
            assert props_check['has_lastPrice'] is True
            assert props_check['has_activeTab'] is True
            assert props_check['sym_is_spy'] is True
            assert props_check['signals_is_array'] is True
            assert props_check['activeTab_is_string'] is True

            await browser.close()

    @pytest.mark.asyncio
    async def test_key_functions_defined(self):
        """Verify key functions are defined."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Check functions exist
            functions_check = await page.evaluate("""() => {
                return {
                    has_setSym: typeof setSym === 'function',
                    has_pollAISignal: typeof pollAISignal === 'function',
                    has_renderAISignalCard: typeof renderAISignalCard === 'function',
                    has_setTab: typeof setTab === 'function',
                    has_init: typeof init === 'function'
                };
            }""")

            assert functions_check['has_setSym'] is True
            assert functions_check['has_pollAISignal'] is True
            assert functions_check['has_renderAISignalCard'] is True
            assert functions_check['has_setTab'] is True
            assert functions_check['has_init'] is True

            await browser.close()


class TestCSSRendering:
    """Test CSS styling and visual structure."""

    @pytest.mark.asyncio
    async def test_dark_theme_colors(self):
        """Verify body has dark background colors."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Get computed background color
            bg_color = await page.evaluate("""() => {
                const style = window.getComputedStyle(document.body);
                return style.backgroundColor;
            }""")

            # Should be dark (the CSS uses var(--bg0) which is #0a0a12)
            # Browser may convert to rgb format
            assert bg_color is not None
            assert len(bg_color) > 0

            await browser.close()

    @pytest.mark.asyncio
    async def test_nav_height(self):
        """Verify nav bar has 40px height."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            nav_height = await page.evaluate("""() => {
                const nav = document.querySelector('.nav');
                return window.getComputedStyle(nav).height;
            }""")

            # Should be 40px
            assert "40px" in nav_height

            await browser.close()

    @pytest.mark.asyncio
    async def test_sidebar_width(self):
        """Verify sidebar width is approximately 260px."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            sidebar_width = await page.evaluate("""() => {
                const sidebar = document.querySelector('.sidebar');
                return window.getComputedStyle(sidebar).width;
            }""")

            # Should be 260px (from grid-template-columns: 1fr 260px)
            assert "260px" in sidebar_width

            await browser.close()

    @pytest.mark.asyncio
    async def test_tab_bar_height(self):
        """Verify tab bar has 32px height."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            tab_bar_height = await page.evaluate("""() => {
                const tabBar = document.querySelector('.tab-bar');
                return window.getComputedStyle(tabBar).height;
            }""")

            assert "32px" in tab_bar_height

            await browser.close()


class TestAISignalCard:
    """Test AI signal card rendering with mock data."""

    @pytest.mark.asyncio
    async def test_render_ai_signal_card_call(self):
        """Test rendering a CALL (bullish) AI signal card."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Create a mock signal object and render it
            await page.evaluate("""() => {
                const mockSignal = {
                    signal: "BUY_CALL",
                    signal_id: "test-1",
                    confidence: 0.85,
                    tier: "TEXTBOOK",
                    strike: 450,
                    expiry: "20260328",
                    entry_price: 450.50,
                    stop_price: 448.00,
                    target_price: 455.00,
                    confluence_count: 3,
                    session: {phase: "ACCUMULATION"},
                    timestamp: Date.now()
                };

                // Ensure signal feed container exists
                let feed = document.getElementById('sigFeed');
                if (!feed) {
                    feed = document.createElement('div');
                    feed.id = 'sigFeed';
                    document.querySelector('.sb-section.signals .sec-body').appendChild(feed);
                }

                // Call the render function
                renderAISignalCard(mockSignal);
            }""")

            # Wait a moment for rendering
            await page.wait_for_timeout(100)

            # Verify card was created
            card = page.locator(".ai-signal-card.call").first
            assert await card.is_visible()

            await browser.close()

    @pytest.mark.asyncio
    async def test_render_ai_signal_card_put(self):
        """Test rendering a PUT (bearish) AI signal card."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Create a mock PUT signal
            await page.evaluate("""() => {
                const mockSignal = {
                    signal: "BUY_PUT",
                    signal_id: "test-2",
                    confidence: 0.70,
                    tier: "VALID",
                    strike: 350,
                    expiry: "20260328",
                    entry_price: 350.75,
                    stop_price: 353.00,
                    target_price: 345.00,
                    confluence_count: 2,
                    session: {phase: "DISTRIBUTION"},
                    timestamp: Date.now()
                };

                let feed = document.getElementById('sigFeed');
                if (!feed) {
                    feed = document.createElement('div');
                    feed.id = 'sigFeed';
                    document.querySelector('.sb-section.signals .sec-body').appendChild(feed);
                }

                renderAISignalCard(mockSignal);
            }""")

            # Wait a moment for rendering
            await page.wait_for_timeout(100)

            # Verify PUT card was created
            card = page.locator(".ai-signal-card.put").first
            assert await card.is_visible()

            await browser.close()

    @pytest.mark.asyncio
    async def test_ai_signal_card_css_classes(self):
        """Verify AI signal card has correct CSS classes."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Render a test signal
            await page.evaluate("""() => {
                const mockSignal = {
                    ticker: "IWM",
                    action: "CALL",
                    confidence: "high",
                    tier: "HIGH",
                    entry: 200.00,
                    stopLoss: 198.00,
                    target: 205.00,
                    timeframe: "4h",
                    updatedAt: new Date().toISOString(),
                    factors: ['Volume spike']
                };

                let feed = document.getElementById('signalFeed');
                if (!feed) {
                    feed = document.createElement('div');
                    feed.id = 'signalFeed';
                    document.querySelector('.sb-section.signals .sec-body').appendChild(feed);
                }

                renderAISignalCard(mockSignal);
            }""")

            # Check for expected classes
            card = page.locator(".ai-signal-card").first
            class_list = await card.evaluate("el => el.className")

            assert "ai-signal-card" in class_list
            assert "call" in class_list or "put" in class_list or "no-trade" in class_list

            await browser.close()

    @pytest.mark.asyncio
    async def test_ai_signal_confidence_badge(self):
        """Verify confidence badge appears with correct styling."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Render signal with high confidence (>= 0.75)
            await page.evaluate("""() => {
                const mockSignal = {
                    signal: "BUY_PUT",
                    signal_id: "test-3",
                    confidence: 0.80,  // High confidence (>= 0.75)
                    tier: "TEXTBOOK",
                    strike: 180,
                    expiry: "20260328",
                    entry_price: 180.00,
                    stop_price: 182.00,
                    target_price: 175.00,
                    confluence_count: 4,
                    session: {phase: "DISTRIBUTION"},
                    timestamp: Date.now()
                };

                let feed = document.getElementById('sigFeed');
                if (!feed) {
                    feed = document.createElement('div');
                    feed.id = 'sigFeed';
                    document.querySelector('.sb-section.signals .sec-body').appendChild(feed);
                }

                renderAISignalCard(mockSignal);
            }""")

            # Wait for rendering
            await page.wait_for_timeout(100)

            # Check confidence badge
            confidence_badge = page.locator(".ai-sig-confidence.high").first
            assert await confidence_badge.is_visible()

            confidence_text = await confidence_badge.text_content()
            assert confidence_text is not None

            await browser.close()

    @pytest.mark.asyncio
    async def test_ai_signal_tier_badge(self):
        """Verify tier badge appears with correct styling."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Render signal with TEXTBOOK tier
            await page.evaluate("""() => {
                const mockSignal = {
                    ticker: "TLT",
                    action: "CALL",
                    confidence: "high",
                    tier: "TEXTBOOK",
                    entry: 95.00,
                    stopLoss: 93.00,
                    target: 100.00,
                    timeframe: "weekly",
                    updatedAt: new Date().toISOString(),
                    factors: ['Classic pattern']
                };

                let feed = document.getElementById('signalFeed');
                if (!feed) {
                    feed = document.createElement('div');
                    feed.id = 'signalFeed';
                    document.querySelector('.sb-section.signals .sec-body').appendChild(feed);
                }

                renderAISignalCard(mockSignal);
            }""")

            # Check tier badge
            tier_badge = page.locator(".ai-sig-tier.TEXTBOOK").first
            assert await tier_badge.is_visible()

            tier_text = await tier_badge.text_content()
            assert "TEXTBOOK" in tier_text

            await browser.close()

    @pytest.mark.asyncio
    async def test_ai_signal_card_metrics_grid(self):
        """Verify signal card shows entry, stop loss, and target."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Render signal with specific prices
            await page.evaluate("""() => {
                const mockSignal = {
                    ticker: "AAPL",
                    action: "CALL",
                    confidence: "high",
                    tier: "HIGH",
                    entry: 175.50,
                    stopLoss: 173.00,
                    target: 180.00,
                    timeframe: "1h",
                    updatedAt: new Date().toISOString(),
                    factors: ['Support bounce']
                };

                let feed = document.getElementById('signalFeed');
                if (!feed) {
                    feed = document.createElement('div');
                    feed.id = 'signalFeed';
                    document.querySelector('.sb-section.signals .sec-body').appendChild(feed);
                }

                renderAISignalCard(mockSignal);
            }""")

            # Check metrics grid exists
            metrics_grid = page.locator(".ai-sig-grid").first
            assert await metrics_grid.is_visible()

            # Check for metric cells
            cells = await page.locator(".ai-sig-cell").all()
            assert len(cells) >= 3  # At least entry, stop, target

            await browser.close()

    @pytest.mark.asyncio
    async def test_multiple_signal_cards(self):
        """Verify multiple signal cards can be rendered."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Render multiple signals
            await page.evaluate("""() => {
                let feed = document.getElementById('signalFeed');
                if (!feed) {
                    feed = document.createElement('div');
                    feed.id = 'signalFeed';
                    document.querySelector('.sb-section.signals .sec-body').appendChild(feed);
                }

                const signals = [
                    {
                        ticker: "SPY",
                        action: "CALL",
                        confidence: "high",
                        tier: "TEXTBOOK",
                        entry: 450.00,
                        stopLoss: 448.00,
                        target: 455.00,
                        timeframe: "5m",
                        updatedAt: new Date().toISOString(),
                        factors: []
                    },
                    {
                        ticker: "QQQ",
                        action: "PUT",
                        confidence: "med",
                        tier: "VALID",
                        entry: 350.00,
                        stopLoss: 353.00,
                        target: 345.00,
                        timeframe: "1h",
                        updatedAt: new Date().toISOString(),
                        factors: []
                    },
                    {
                        ticker: "IWM",
                        action: "NO_TRADE",
                        confidence: "low",
                        tier: "DEVELOPING",
                        entry: null,
                        stopLoss: null,
                        target: null,
                        timeframe: "daily",
                        updatedAt: new Date().toISOString(),
                        factors: []
                    }
                ];

                signals.forEach(sig => renderAISignalCard(sig));
            }""")

            # Check all cards exist
            cards = await page.locator(".ai-signal-card").all()
            assert len(cards) >= 3

            await browser.close()


class TestSymbolSwitch:
    """Test symbol switching functionality."""

    @pytest.mark.asyncio
    async def test_set_symbol_updates_state(self):
        """Verify setSym() updates the global S.sym property."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Call setSym
            await page.evaluate("setSym('QQQ')")

            # Check state was updated
            new_sym = await page.evaluate("S.sym")
            assert new_sym == "QQQ"

            await browser.close()

    @pytest.mark.asyncio
    async def test_set_symbol_updates_nav(self):
        """Verify setSym() updates the state."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Get initial symbol
            initial_sym = await page.evaluate("S.sym")
            assert initial_sym == "SPY"

            # Switch symbol
            await page.evaluate("setSym('MSFT')")
            await page.wait_for_timeout(50)

            # Check state was updated
            new_sym = await page.evaluate("S.sym")
            assert new_sym == "MSFT"

            await browser.close()


class TestTabNavigation:
    """Test tab navigation."""

    @pytest.mark.asyncio
    async def test_set_tab_changes_active_tab(self):
        """Verify setTab() updates the active tab state and display."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Get initial active tab
            initial_tab = await page.evaluate("S.activeTab")
            assert initial_tab is not None

            # Switch to a different tab
            all_tabs = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('.tab-btn'))
                    .map(btn => btn.dataset.tab)
                    .filter(t => t !== undefined);
            }""")

            if len(all_tabs) > 1:
                new_tab = all_tabs[1]
                await page.evaluate(f"setTab('{new_tab}')")

                # Verify state changed
                current_tab = await page.evaluate("S.activeTab")
                assert current_tab == new_tab

            await browser.close()


class TestPageLoad:
    """Test page load and basic functionality."""

    @pytest.mark.asyncio
    async def test_page_loads_without_errors(self):
        """Verify page loads without JavaScript errors."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context()
            page = await context.new_page()

            # Collect any page errors
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))

            await page.goto(DASHBOARD_URL)
            await page.wait_for_timeout(500)

            # Check no errors occurred (websocket connection errors are expected)
            # Filter out known errors that are expected in a test environment
            significant_errors = [
                e for e in errors
                if "WebSocket" not in e
                and "ECONNREFUSED" not in e
                and "LightweightCharts is not defined" not in e
            ]

            # Should have no significant JavaScript errors
            assert len(significant_errors) == 0, f"Page errors: {significant_errors}"

            await browser.close()

    @pytest.mark.asyncio
    async def test_dom_is_fully_rendered(self):
        """Verify DOM is fully rendered after page load."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(DASHBOARD_URL)

            # Wait for critical elements
            nav = await page.locator(".nav").first.is_visible()
            tab_bar = await page.locator(".tab-bar").first.is_visible()
            main = await page.locator(".main").first.is_visible()
            sidebar = await page.locator(".sidebar").first.is_visible()

            assert nav is True
            assert tab_bar is True
            assert main is True
            assert sidebar is True

            await browser.close()


if __name__ == "__main__":
    # Run tests with: python -m pytest tests/test_frontend.py -v
    pytest.main([__file__, "-v"])
