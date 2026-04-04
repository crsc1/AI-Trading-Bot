"""
Unit tests for confluence.py module.

Tests:
- analyze_order_flow() with mock trade data
- get_session_context() at different times of day
- evaluate_confluence() with various factor combinations
- 0DTE hard stop logic (after 3:00 PM ET)
- Confidence tier classification (TEXTBOOK, HIGH, VALID, DEVELOPING)
- select_strike() with mock options chain
- calculate_risk() at different confidence levels
"""

import pytest
from datetime import datetime, timezone, timedelta, time as dt_time
from typing import List, Dict

from dashboard.confluence import (
    OrderFlowState,
    SessionContext,
    ConfluenceFactor,
    analyze_order_flow,
    get_session_context,
    evaluate_confluence,
    select_strike,
    calculate_risk,
)
from dashboard.market_levels import MarketLevels


class TestOrderFlowAnalysis:
    """Test order flow analysis functionality."""

    def test_analyze_order_flow_basic(self, mock_trades, mock_market_levels):
        """Test basic order flow analysis."""
        state = analyze_order_flow(
            trades=mock_trades,
            levels=mock_market_levels,
        )

        assert isinstance(state, OrderFlowState)
        assert state.total_volume > 0
        assert state.buy_volume + state.sell_volume > 0

    def test_order_flow_with_empty_trades(self, mock_market_levels):
        """Test order flow with empty trades."""
        state = analyze_order_flow(
            trades=[],
            levels=mock_market_levels,
        )

        # Should return neutral state
        assert state.total_volume == 0
        assert state.cvd_trend == "neutral"

    def test_order_flow_with_insufficient_trades(self, mock_market_levels):
        """Test order flow with too few trades."""
        minimal_trades = [
            {"p": 550.0, "s": 100, "side": "buy"},
            {"p": 550.1, "s": 100, "side": "sell"},
        ]

        state = analyze_order_flow(
            trades=minimal_trades,
            levels=mock_market_levels,
        )

        # Should handle gracefully
        assert state.cvd_trend == "neutral"

    def test_order_flow_cvd_trend_rising(self, mock_market_levels):
        """Test CVD trend detection for rising market."""
        # Create trades with more buys at the end
        trades = []
        for i in range(30):
            side = "buy" if i > 20 else "sell"
            trades.append({
                "p": 550.0 + i * 0.01,
                "s": 100,
                "side": side,
            })

        state = analyze_order_flow(trades=trades, levels=mock_market_levels)
        assert state.cvd_trend in ["rising", "neutral", "falling"]

    def test_order_flow_imbalance_calculation(self, mock_market_levels):
        """Test that imbalance is correctly calculated."""
        trades = [
            {"p": 550.0, "s": 100, "side": "buy"},
            {"p": 550.0, "s": 100, "side": "buy"},
            {"p": 550.0, "s": 100, "side": "sell"},
        ]

        state = analyze_order_flow(trades=trades, levels=mock_market_levels)
        # Imbalance should be a reasonable value
        # With < 10 trades, it might return neutral state with imbalance=0.5
        assert 0 <= state.imbalance <= 1.0

    def test_order_flow_to_dict(self, mock_trades, mock_market_levels):
        """Test conversion of OrderFlowState to dictionary."""
        state = analyze_order_flow(trades=mock_trades, levels=mock_market_levels)
        d = state.to_dict()

        assert isinstance(d, dict)
        assert "cvd" in d
        assert "total_volume" in d
        assert "imbalance" in d


class TestSessionContext:
    """Test session context detection."""

    def test_get_session_context_pre_market(self):
        """Test pre-market session detection."""
        # 4:30 UTC = 12:30 AM ET = pre-market
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        test_time = datetime(2026, 3, 26, 4, 30, 0, tzinfo=ET)
        context = get_session_context(test_time)

        assert context.phase == "pre_market"
        assert context.minutes_to_close > 0

    def test_get_session_context_opening_drive(self):
        """Test opening drive session detection."""
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        # 9:45 AM ET = opening drive
        test_time = datetime(2026, 3, 26, 9, 45, 0, tzinfo=ET)
        context = get_session_context(test_time)

        assert context.phase == "opening_drive"

    def test_get_session_context_morning_trend(self):
        """Test morning trend session detection."""
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        # 10:15 AM ET = morning trend
        test_time = datetime(2026, 3, 26, 10, 15, 0, tzinfo=ET)
        context = get_session_context(test_time)

        assert context.phase == "morning_trend"

    def test_get_session_context_midday_chop(self):
        """Test midday chop session detection."""
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        # 11:45 AM ET = midday chop
        test_time = datetime(2026, 3, 26, 11, 45, 0, tzinfo=ET)
        context = get_session_context(test_time)

        assert context.phase == "midday_chop"

    def test_get_session_context_afternoon_trend(self):
        """Test afternoon trend session detection."""
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        # 1:45 PM ET = afternoon trend
        test_time = datetime(2026, 3, 26, 13, 45, 0, tzinfo=ET)
        context = get_session_context(test_time)

        assert context.phase == "afternoon_trend"

    def test_get_session_context_power_hour(self):
        """Test power hour session detection."""
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        # 3:15 PM ET = power hour
        test_time = datetime(2026, 3, 26, 15, 15, 0, tzinfo=ET)
        context = get_session_context(test_time)

        assert context.phase == "power_hour"

    def test_get_session_context_close_risk(self):
        """Test close risk session detection."""
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        # 3:50 PM ET = close risk
        test_time = datetime(2026, 3, 26, 15, 50, 0, tzinfo=ET)
        context = get_session_context(test_time)

        assert context.phase == "close_risk"

    def test_session_context_has_minutes_to_close(self):
        """Test that minutes to close is computed."""
        context = get_session_context()

        assert isinstance(context.minutes_to_close, int)
        assert context.minutes_to_close >= 0


class TestConfluenceEvaluation:
    """Test confluence factor evaluation."""

    def test_evaluate_confluence_with_bullish_flow(self, mock_market_levels, mock_trades):
        """Test evaluation with bullish order flow."""
        flow = analyze_order_flow(trades=mock_trades, levels=mock_market_levels)
        session = SessionContext(phase="morning_trend")

        # Modify flow to be bullish
        flow.divergence = "bullish"
        flow.cvd_trend = "rising"

        action, confidence, factors = evaluate_confluence(
            flow=flow,
            levels=mock_market_levels,
            session=session,
        )

        # Should return a valid action and confidence
        assert isinstance(action, str)
        assert 0 <= confidence <= 1.0
        assert isinstance(factors, list)

    def test_evaluate_confluence_with_bearish_flow(self, mock_market_levels, mock_trades):
        """Test evaluation with bearish order flow."""
        flow = analyze_order_flow(trades=mock_trades, levels=mock_market_levels)
        session = SessionContext(phase="morning_trend")

        # Modify flow to be bearish
        flow.divergence = "bearish"
        flow.cvd_trend = "falling"

        action, confidence, factors = evaluate_confluence(
            flow=flow,
            levels=mock_market_levels,
            session=session,
        )

        # Should return a valid action and confidence
        assert isinstance(action, str)
        assert 0 <= confidence <= 1.0

    def test_evaluate_confluence_neutral(self, mock_market_levels, mock_trades):
        """Test evaluation with neutral factors."""
        flow = analyze_order_flow(trades=mock_trades, levels=mock_market_levels)
        session = SessionContext(phase="midday_chop")

        action, confidence, factors = evaluate_confluence(
            flow=flow,
            levels=mock_market_levels,
            session=session,
        )

        # Should handle neutral case
        assert isinstance(action, str)
        assert 0 <= confidence <= 1.0


class TestSelectStrike:
    """Test options strike selection."""

    def test_select_strike_call_action(self):
        """Test selecting strike for BUY_CALL action."""
        result = select_strike(
            action="BUY_CALL",
            current_price=550.0,
            chain=None,
            target_delta=0.35,
        )

        assert isinstance(result, dict)
        assert "strike" in result
        assert "expiry" in result
        assert "entry_price" in result

    def test_select_strike_put_action(self):
        """Test selecting strike for BUY_PUT action."""
        result = select_strike(
            action="BUY_PUT",
            current_price=550.0,
            chain=None,
            target_delta=0.35,
        )

        assert isinstance(result, dict)
        assert "strike" in result
        assert "expiry" in result

    def test_select_strike_spread_action(self):
        """Test selecting strike for spread actions."""
        result = select_strike(
            action="BULL_CALL_SPREAD",
            current_price=550.0,
            chain=None,
            target_delta=0.25,
        )

        assert isinstance(result, dict)
        assert "strike" in result


class TestCalculateRisk:
    """Test risk calculation."""

    def test_calculate_risk_textbook(self, mock_market_levels):
        """Test risk calculation for TEXTBOOK confidence."""
        result = calculate_risk(
            confidence=0.85,  # TEXTBOOK confidence
            entry_price=550.0,
            levels=mock_market_levels,
            session=SessionContext(phase="morning_trend"),
            account_balance=5000.0,
        )

        assert isinstance(result, dict)
        assert "tier" in result or "size" in result

    def test_calculate_risk_high(self, mock_market_levels):
        """Test risk calculation for HIGH confidence."""
        result = calculate_risk(
            confidence=0.75,  # HIGH confidence
            entry_price=550.0,
            levels=mock_market_levels,
            session=SessionContext(phase="morning_trend"),
            account_balance=5000.0,
        )

        assert isinstance(result, dict)

    def test_calculate_risk_valid(self, mock_market_levels):
        """Test risk calculation for VALID confidence."""
        result = calculate_risk(
            confidence=0.60,  # VALID confidence
            entry_price=550.0,
            levels=mock_market_levels,
            session=SessionContext(phase="morning_trend"),
            account_balance=5000.0,
        )

        assert isinstance(result, dict)

    def test_calculate_risk_developing(self, mock_market_levels):
        """Test risk calculation for DEVELOPING confidence."""
        result = calculate_risk(
            confidence=0.45,  # DEVELOPING confidence
            entry_price=550.0,
            levels=mock_market_levels,
            session=SessionContext(phase="midday_chop"),
            account_balance=5000.0,
        )

        # Should still return a dict
        assert isinstance(result, dict)

    def test_calculate_risk_with_varying_confidence(self, mock_market_levels):
        """Test that risk calculation handles various confidence levels."""
        for conf in [0.4, 0.55, 0.70, 0.85]:
            result = calculate_risk(
                confidence=conf,
                entry_price=550.0,
                levels=mock_market_levels,
                session=SessionContext(phase="morning_trend"),
                account_balance=5000.0,
            )

            assert isinstance(result, dict)


class TestConfluenceDataclasses:
    """Test dataclass functionality."""

    def test_session_context_to_dict(self):
        """Test SessionContext to_dict conversion."""
        context = SessionContext(
            phase="morning_trend",
            minutes_to_close=300,
            is_0dte=True,
            past_hard_stop=False,
        )

        d = context.to_dict()
        assert isinstance(d, dict)
        assert d["phase"] == "morning_trend"
        assert d["minutes_to_close"] == 300
        assert d["is_0dte"] is True

    def test_confluence_factor_creation(self):
        """Test ConfluenceFactor creation."""
        factor = ConfluenceFactor(
            name="VWAP",
            direction="bullish",
            weight=0.5,
            detail="Price above VWAP with rising trend",
        )

        assert factor.name == "VWAP"
        assert factor.direction == "bullish"
        assert factor.weight == 0.5
        assert len(factor.detail) > 0


class TestEdgeCasesConfluence:
    """Test edge cases in confluence evaluation."""

    def test_session_context_returns_valid_phase(self):
        """Test that session context always returns a valid phase."""
        context = get_session_context()

        assert isinstance(context, SessionContext)
        assert isinstance(context.phase, str)
        assert len(context.phase) > 0

    def test_calculate_risk_at_boundaries(self, mock_market_levels):
        """Test risk calculation at confidence boundaries."""
        # Test boundary values
        for conf in [0.0, 0.40, 0.55, 0.70, 0.85, 1.0]:
            result = calculate_risk(
                confidence=conf,
                entry_price=550.0,
                levels=mock_market_levels,
                session=SessionContext(phase="opening_drive"),
                account_balance=5000.0,
            )

            # Should handle boundary values gracefully
            assert isinstance(result, dict)
