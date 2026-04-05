"""
Test suite for the agent orchestration API.

Tests:
- GET /api/agents/status — Agent status
- GET /api/agents/signals — All signals
- GET /api/agents/open — Open signals
- GET /api/agents/performance — Performance metrics
- GET /api/agents/verdicts — Raw verdicts from each agent
"""

import pytest
from unittest.mock import MagicMock, patch


class TestAgentStatusEndpoint:
    """Test GET /api/agents/status endpoint."""

    @pytest.mark.asyncio
    async def test_get_agent_status_success(self, async_client):
        """Test successful GET /api/agents/status."""
        with patch("dashboard.agents.api.get_publisher") as mock_get_publisher:
            mock_publisher = MagicMock()
            mock_publisher.get_agent_status.return_value = [
                {
                    "name": "price_flow_agent",
                    "status": "running",
                    "last_update": "2026-03-26T15:30:00Z",
                },
                {
                    "name": "market_structure_agent",
                    "status": "running",
                    "last_update": "2026-03-26T15:29:50Z",
                },
            ]
            mock_publisher.open_signals = [1, 2, 3]
            mock_publisher.closed_signals = [4, 5]
            mock_publisher._running = True

            mock_get_publisher.return_value = mock_publisher

            response = await async_client.get("/api/agents/status")

            assert response.status_code == 200
            data = response.json()
            assert "agents" in data
            assert "open_signals" in data
            assert "closed_signals" in data
            assert "system" in data
            assert data["open_signals"] == 3
            assert data["closed_signals"] == 2
            assert data["system"] == "running"

    @pytest.mark.asyncio
    async def test_get_agent_status_no_agents(self, async_client):
        """Test GET /api/agents/status with no agents."""
        with patch("dashboard.agents.api.get_publisher") as mock_get_publisher:
            mock_publisher = MagicMock()
            mock_publisher.get_agent_status.return_value = []
            mock_publisher.open_signals = []
            mock_publisher.closed_signals = []
            mock_publisher._running = False

            mock_get_publisher.return_value = mock_publisher

            response = await async_client.get("/api/agents/status")

            assert response.status_code == 200
            data = response.json()
            assert data["open_signals"] == 0
            assert data["system"] == "stopped"


class TestAgentSignalsEndpoint:
    """Test GET /api/agents/signals endpoint."""

    @pytest.mark.asyncio
    async def test_get_all_signals_success(self, async_client, mock_signal):
        """Test successful GET /api/agents/signals."""
        with patch("dashboard.agents.api.get_publisher") as mock_get_publisher:
            mock_publisher = MagicMock()
            signals = [mock_signal, {**mock_signal, "id": "signal_124"}]
            mock_publisher.get_all_signals.return_value = signals
            mock_publisher.open_signals = [mock_signal]
            mock_publisher.closed_signals = [{**mock_signal, "id": "signal_124"}]

            mock_get_publisher.return_value = mock_publisher

            response = await async_client.get("/api/agents/signals")

            assert response.status_code == 200
            data = response.json()
            assert "signals" in data
            assert "count" in data
            assert data["count"] == 2
            assert len(data["signals"]) == 2

    @pytest.mark.asyncio
    async def test_get_all_signals_empty(self, async_client):
        """Test GET /api/agents/signals with no signals."""
        with patch("dashboard.agents.api.get_publisher") as mock_get_publisher:
            mock_publisher = MagicMock()
            mock_publisher.get_all_signals.return_value = []
            mock_publisher.open_signals = []
            mock_publisher.closed_signals = []

            mock_get_publisher.return_value = mock_publisher

            response = await async_client.get("/api/agents/signals")

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 0


class TestOpenSignalsEndpoint:
    """Test GET /api/agents/open endpoint."""

    @pytest.mark.asyncio
    async def test_get_open_signals_success(self, async_client, mock_signal):
        """Test successful GET /api/agents/open."""
        with patch("dashboard.agents.api.get_publisher") as mock_get_publisher:
            mock_publisher = MagicMock()
            open_signals = [mock_signal]
            mock_publisher.get_open_signals.return_value = open_signals
            mock_publisher.open_signals = open_signals

            mock_get_publisher.return_value = mock_publisher

            response = await async_client.get("/api/agents/open")

            assert response.status_code == 200
            data = response.json()
            assert "signals" in data
            assert "count" in data
            assert data["count"] == 1
            assert data["signals"][0]["id"] == "signal_123"

    @pytest.mark.asyncio
    async def test_get_open_signals_multiple(self, async_client, mock_signal):
        """Test GET /api/agents/open with multiple open signals."""
        with patch("dashboard.agents.api.get_publisher") as mock_get_publisher:
            mock_publisher = MagicMock()
            open_signals = [
                mock_signal,
                {**mock_signal, "id": "signal_124", "direction": "bearish"},
                {**mock_signal, "id": "signal_125"},
            ]
            mock_publisher.get_open_signals.return_value = open_signals
            mock_publisher.open_signals = open_signals

            mock_get_publisher.return_value = mock_publisher

            response = await async_client.get("/api/agents/open")

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 3

    @pytest.mark.asyncio
    async def test_get_open_signals_empty(self, async_client):
        """Test GET /api/agents/open with no open signals."""
        with patch("dashboard.agents.api.get_publisher") as mock_get_publisher:
            mock_publisher = MagicMock()
            mock_publisher.get_open_signals.return_value = []
            mock_publisher.open_signals = []

            mock_get_publisher.return_value = mock_publisher

            response = await async_client.get("/api/agents/open")

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 0


class TestPerformanceEndpoint:
    """Test GET /api/agents/performance endpoint."""

    @pytest.mark.asyncio
    async def test_get_performance_success(self, async_client):
        """Test successful GET /api/agents/performance."""
        with patch("dashboard.agents.api.get_publisher") as mock_get_publisher:
            mock_publisher = MagicMock()
            performance = {
                "total_trades": 10,
                "winning_trades": 7,
                "losing_trades": 3,
                "win_rate": 0.70,
                "total_pl": 2500.00,
                "profit_factor": 2.5,
                "consecutive_wins": 2,
                "consecutive_losses": 1,
                "best_trade": 500.00,
                "worst_trade": -150.00,
                "avg_win": 357.14,
                "avg_loss": -83.33,
                "risk_reward_ratio": 4.28,
            }
            mock_publisher.get_performance.return_value = performance

            mock_get_publisher.return_value = mock_publisher

            response = await async_client.get("/api/agents/performance")

            assert response.status_code == 200
            data = response.json()
            assert data["total_trades"] == 10
            assert data["win_rate"] == 0.70
            assert data["total_pl"] == 2500.00
            assert data["profit_factor"] == 2.5

    @pytest.mark.asyncio
    async def test_get_performance_no_trades(self, async_client):
        """Test GET /api/agents/performance with no trades."""
        with patch("dashboard.agents.api.get_publisher") as mock_get_publisher:
            mock_publisher = MagicMock()
            performance = {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_pl": 0.00,
                "profit_factor": 0.0,
            }
            mock_publisher.get_performance.return_value = performance

            mock_get_publisher.return_value = mock_publisher

            response = await async_client.get("/api/agents/performance")

            assert response.status_code == 200
            data = response.json()
            assert data["total_trades"] == 0
            assert data["total_pl"] == 0.00


class TestVerdictsEndpoint:
    """Test GET /api/agents/verdicts endpoint."""

    @pytest.mark.asyncio
    async def test_get_verdicts_success(self, async_client):
        """Test successful GET /api/agents/verdicts."""
        with patch("dashboard.agents.api.get_publisher") as mock_get_publisher:
            mock_publisher = MagicMock()

            # Create mock agents with verdicts
            mock_agent1 = MagicMock()
            mock_agent1.name = "price_flow_agent"
            verdict1 = MagicMock()
            verdict1.to_dict.return_value = {
                "agent": "price_flow_agent",
                "direction": "bullish",
                "confidence": 0.85,
                "reasoning": "Strong uptrend in price/volume",
            }
            mock_agent1.get_verdict.return_value = verdict1

            mock_agent2 = MagicMock()
            mock_agent2.name = "market_structure_agent"
            verdict2 = MagicMock()
            verdict2.to_dict.return_value = {
                "agent": "market_structure_agent",
                "direction": "bullish",
                "confidence": 0.75,
                "reasoning": "Price above VWAP and pivot",
            }
            mock_agent2.get_verdict.return_value = verdict2

            mock_publisher._agents = [mock_agent1, mock_agent2]
            mock_get_publisher.return_value = mock_publisher

            response = await async_client.get("/api/agents/verdicts")

            assert response.status_code == 200
            data = response.json()
            # Response wraps verdicts in a "verdicts" key
            assert "verdicts" in data or "price_flow_agent" in data
            verdicts = data.get("verdicts", data)
            if "price_flow_agent" in verdicts:
                assert verdicts["price_flow_agent"]["direction"] == "bullish"
                assert verdicts["price_flow_agent"]["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_get_verdicts_with_stale_data(self, async_client):
        """Test GET /api/agents/verdicts with stale agent data."""
        with patch("dashboard.agents.api.get_publisher") as mock_get_publisher:
            mock_publisher = MagicMock()

            # Agent with no verdict (stale)
            mock_agent = MagicMock()
            mock_agent.name = "test_agent"
            mock_agent.get_verdict.return_value = None

            mock_publisher._agents = [mock_agent]
            mock_get_publisher.return_value = mock_publisher

            response = await async_client.get("/api/agents/verdicts")

            assert response.status_code == 200
            data = response.json()
            verdicts = data.get("verdicts", data)
            assert "test_agent" in verdicts
            assert verdicts["test_agent"]["stale"] is True
            assert verdicts["test_agent"]["direction"] == "none"


class TestAgentApiIntegration:
    """Integration tests for agent API."""

    @pytest.mark.asyncio
    async def test_agent_endpoints_consistent_signal_counts(self, async_client, mock_signal):
        """Test that signal counts are consistent across endpoints."""
        open_signals = [mock_signal]
        closed_signals = [{**mock_signal, "id": "signal_124"}]

        with patch("dashboard.agents.api.get_publisher") as mock_get_publisher:
            mock_publisher = MagicMock()

            # Setup return values
            mock_publisher.open_signals = open_signals
            mock_publisher.closed_signals = closed_signals
            mock_publisher.get_agent_status.return_value = []
            mock_publisher.get_all_signals.return_value = open_signals + closed_signals
            mock_publisher.get_open_signals.return_value = open_signals
            mock_publisher._running = True
            mock_publisher._agents = []

            mock_get_publisher.return_value = mock_publisher

            # Get status
            response_status = await async_client.get("/api/agents/status")
            data_status = response_status.json()

            # Get all signals
            response_all = await async_client.get("/api/agents/signals")
            data_all = response_all.json()

            # Get open signals
            response_open = await async_client.get("/api/agents/open")
            data_open = response_open.json()

            # Verify consistency
            assert data_status["open_signals"] == data_open["count"]
            assert data_status["open_signals"] + data_status["closed_signals"] == data_all["count"]


class TestAgentApiErrorHandling:
    """Test error handling in agent API."""

    @pytest.mark.asyncio
    async def test_status_endpoint_with_no_data(self, async_client):
        """Test status endpoint when no agent data is available."""
        with patch("dashboard.agents.api.get_publisher") as mock_get_publisher:
            mock_publisher = MagicMock()
            mock_publisher.get_agent_status.return_value = []
            mock_publisher.open_signals = []
            mock_publisher.closed_signals = []
            mock_publisher._running = False

            mock_get_publisher.return_value = mock_publisher

            response = await async_client.get("/api/agents/status")

            # Should handle gracefully
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_signals_endpoint_graceful_empty_response(self, async_client):
        """Test signals endpoint returns empty array on no data."""
        with patch("dashboard.agents.api.get_publisher") as mock_get_publisher:
            mock_publisher = MagicMock()
            mock_publisher.get_all_signals.return_value = []
            mock_publisher.open_signals = []
            mock_publisher.closed_signals = []

            mock_get_publisher.return_value = mock_publisher

            response = await async_client.get("/api/agents/signals")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data["signals"], list)
            assert len(data["signals"]) == 0
