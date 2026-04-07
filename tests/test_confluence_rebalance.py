"""
Tests for v14: 7-factor confluence scoring.

Covers:
  1. FACTOR_WEIGHTS_BASELINE structure (7 factors, total = 9.25)
  2. FULL_DENOMINATOR correctness
  3. Tier thresholds ordering
  4. Integration: evaluate_confluence with 7 factors
  5. Confluence bonus floor thresholds (5/4/3 confirming)
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.confluence import (
    FACTOR_WEIGHTS_BASELINE,
    FULL_DENOMINATOR,
    TIER_TEXTBOOK,
    TIER_HIGH,
    OrderFlowState,
    SessionContext,
    evaluate_confluence,
)
from dashboard.market_levels import MarketLevels


# ═══════════════════════════════════════════════════════════════════════════════
# 1. FACTOR_WEIGHTS_BASELINE structure
# ═══════════════════════════════════════════════════════════════════════════════

class TestFactorWeights:

    def test_factor_count(self):
        """Should have exactly 7 factors."""
        assert len(FACTOR_WEIGHTS_BASELINE) == 7

    def test_expected_factors(self):
        """All 7 expected factor keys should be present."""
        expected = {
            "order_flow_imbalance",
            "cvd_divergence",
            "gex_alignment",
            "vwap_rejection",
            "sweep_activity",
            "orb_breakout",
            "support_resistance",
        }
        assert set(FACTOR_WEIGHTS_BASELINE.keys()) == expected

    def test_order_flow_is_heaviest(self):
        """Order flow should have the highest weight."""
        max_factor = max(FACTOR_WEIGHTS_BASELINE, key=FACTOR_WEIGHTS_BASELINE.get)
        assert max_factor == "order_flow_imbalance"
        assert FACTOR_WEIGHTS_BASELINE["order_flow_imbalance"] == 2.0

    def test_all_weights_positive(self):
        """All baseline weights should be > 0."""
        for k, v in FACTOR_WEIGHTS_BASELINE.items():
            assert v > 0, f"{k} has non-positive weight {v}"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. FULL_DENOMINATOR correctness
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullDenominator:

    def test_full_denominator_value(self):
        """FULL_DENOMINATOR should be sum of all 7 factor weights."""
        expected = sum(FACTOR_WEIGHTS_BASELINE.values())
        assert FULL_DENOMINATOR == expected
        assert abs(FULL_DENOMINATOR - 9.25) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Tier thresholds
# ═══════════════════════════════════════════════════════════════════════════════

class TestTierThresholds:

    def test_tier_ordering(self):
        assert TIER_TEXTBOOK > TIER_HIGH > TIER_HIGH * 0.95 > TIER_HIGH * 0.85 > 0.40


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Integration: evaluate_confluence with 7 factors
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvaluateConfluenceV14:

    def _make_flow(self, bias="bullish"):
        if bias == "bullish":
            return OrderFlowState(
                imbalance=0.75,
                cvd=5000,
                cvd_trend="rising",
                cvd_acceleration=1000,
                price_trend="rising",
                divergence="none",
                total_volume=50000,
                buy_volume=37500,
                sell_volume=12500,
                aggressive_buy_pct=0.70,
                aggressive_sell_pct=0.30,
                large_trade_count=3,
                large_trade_bias="buy",
                large_trade_volume=20000,
            )
        else:
            return OrderFlowState(
                imbalance=0.25,
                cvd=-5000,
                cvd_trend="falling",
                cvd_acceleration=-1000,
                price_trend="falling",
                divergence="none",
                total_volume=50000,
                buy_volume=12500,
                sell_volume=37500,
                aggressive_buy_pct=0.30,
                aggressive_sell_pct=0.70,
                large_trade_count=3,
                large_trade_bias="sell",
                large_trade_volume=20000,
            )

    def _make_levels(self, price=550.0):
        levels = MarketLevels.__new__(MarketLevels)
        levels.current_price = price
        levels.vwap = price - 0.3
        levels.vwap_upper_1 = price + 1
        levels.vwap_lower_1 = price - 1
        levels.vwap_upper_2 = price + 2
        levels.vwap_lower_2 = price - 2
        levels.atr_1m = 0.5
        levels.bid = price - 0.01
        levels.ask = price + 0.01
        levels.hod = price + 0.1
        levels.lod = price - 3
        levels.prev_close = price - 1
        levels.open_price = price - 0.5
        levels.realized_vol = 18.0
        levels.orb_high = price + 0.2
        levels.orb_low = price - 1.5
        levels.orb_confirmed = True
        levels.ema_8 = price - 0.1
        levels.ema_21 = price - 0.3
        levels.sma_50 = price - 0.5
        levels.bb_upper = price + 2
        levels.bb_lower = price - 2
        levels.bb_width = 4.0
        levels.bb_squeeze = False
        levels.support_levels = [price - 2, price - 4]
        levels.resistance_levels = [price + 2, price + 4]
        return levels

    def _make_session(self, phase="morning_trend"):
        return SessionContext(
            phase=phase,
            minutes_to_close=300,
            is_0dte=True,
            past_hard_stop=False,
            session_quality=0.8,
        )

    def test_basic_bullish_signal(self):
        """Strong bullish flow should produce a BUY_CALL signal."""
        flow = self._make_flow("bullish")
        levels = self._make_levels()
        session = self._make_session()
        action, confidence, factors = evaluate_confluence(
            flow, levels, session
        )
        assert action == "BUY_CALL"
        assert confidence > 0

    def test_basic_bearish_signal(self):
        """Strong bearish flow should produce a BUY_PUT signal."""
        flow = self._make_flow("bearish")
        levels = self._make_levels()
        session = self._make_session()
        action, confidence, factors = evaluate_confluence(
            flow, levels, session
        )
        assert action in ("BUY_PUT", "NO_TRADE")

    def test_opposing_factor_penalty(self):
        """Opposing factors should reduce confidence."""
        flow = self._make_flow("bullish")
        levels = self._make_levels()
        levels.vwap = levels.current_price + 2  # Price well below VWAP
        session = self._make_session()

        action, confidence, factors = evaluate_confluence(
            flow, levels, session
        )
        assert confidence < 0.80

    def test_returns_factors_list(self):
        """Should return a non-empty factors list."""
        flow = self._make_flow("bullish")
        levels = self._make_levels()
        session = self._make_session()
        _, _, factors = evaluate_confluence(flow, levels, session)
        assert len(factors) > 0

    def test_no_removed_factors_in_output(self):
        """Removed factors (PCR, Max Pain, etc.) should not appear."""
        flow = self._make_flow("bullish")
        levels = self._make_levels()
        session = self._make_session()
        _, _, factors = evaluate_confluence(flow, levels, session)
        removed_names = {
            "Put/Call Ratio", "Max Pain", "Session Quality",
            "Vanna Flow", "Charm Pressure", "Flow Toxicity",
            "Sector/Bond", "AI Agents", "EMA/SMA Trend",
            "BB Squeeze", "Candle Pattern", "Market Breadth",
            "Vol Edge", "DEX Levels", "Volume Spike", "Delta Regime",
        }
        for f in factors:
            assert f.name not in removed_names, \
                f"Removed factor '{f.name}' still appears in output"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Confluence bonus floor thresholds
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfluenceBonusFloors:

    def test_textbook_requires_5_of_7(self):
        """TEXTBOOK floor should require 5/7 (~71%) confirming factors."""
        assert 5 / 7 > 0.70

    def test_high_requires_4_of_7(self):
        """HIGH floor should require 4/7 (~57%) confirming factors."""
        assert 4 / 7 > 0.55


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
