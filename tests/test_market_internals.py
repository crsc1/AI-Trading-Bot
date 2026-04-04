"""
Tests for Market Internals (Step 8) — synthetic breadth index.

Covers:
  1. MarketBreadth dataclass defaults
  2. score_market_breadth() — bullish/bearish alignment, extreme readings,
     risk appetite, divergence
  3. _compute_return() utility
  4. Integration: breadth in momentum scorer (dynamic_exit)
  5. Edge cases: insufficient data, flat market, all inverse
"""

import sys
import os
import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.market_internals import (
    MarketBreadth,
    score_market_breadth,
    _compute_return,
    BREADTH_UNIVERSE,
    ADVANCE_THRESHOLD,
    EXTREME_THRESHOLD,
    DIVERGENCE_THRESHOLD,
)
from dashboard.dynamic_exit import score_momentum


# ═══════════════════════════════════════════════════════════════════════════════
# 1. MarketBreadth Defaults
# ═══════════════════════════════════════════════════════════════════════════════

class TestMarketBreadthDefaults:

    def test_default_values(self):
        mb = MarketBreadth()
        assert mb.breadth_score == 0.0
        assert mb.advance_decline_ratio == 0.5
        assert mb.breadth_divergence is False
        assert mb.extreme_reading is False
        assert mb.risk_appetite == 0.0
        assert mb.risk_signal == "neutral"
        assert mb.symbols_fetched == 0

    def test_to_dict(self):
        mb = MarketBreadth(breadth_score=0.456, advancing_count=7, declining_count=3)
        d = mb.to_dict()
        assert d["breadth_score"] == 0.456
        assert d["advancing"] == 7
        assert d["declining"] == 3
        assert "breadth_divergence" in d
        assert "risk_signal" in d


# ═══════════════════════════════════════════════════════════════════════════════
# 2. _compute_return
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeReturn:

    def test_normal_return(self):
        bars = [{"c": 100.0}, {"c": 101.0}]
        ret = _compute_return(bars)
        assert abs(ret - 1.0) < 0.001

    def test_negative_return(self):
        bars = [{"c": 100.0}, {"c": 99.0}]
        ret = _compute_return(bars)
        assert abs(ret - (-1.0)) < 0.001

    def test_empty_bars(self):
        assert _compute_return([]) == 0.0

    def test_single_bar(self):
        assert _compute_return([{"c": 100}]) == 0.0

    def test_zero_first_price(self):
        bars = [{"c": 0}, {"c": 100}]
        assert _compute_return(bars) == 0.0

    def test_close_key_fallback(self):
        bars = [{"close": 50.0}, {"close": 55.0}]
        ret = _compute_return(bars)
        assert abs(ret - 10.0) < 0.001


# ═══════════════════════════════════════════════════════════════════════════════
# 3. score_market_breadth — core scoring
# ═══════════════════════════════════════════════════════════════════════════════

class TestScoreMarketBreadth:

    def test_insufficient_data(self):
        mb = MarketBreadth(symbols_fetched=2)
        score, detail = score_market_breadth(mb, "bullish")
        assert score == 0.0
        assert "Insufficient" in detail

    def test_strong_bullish_confirms_bullish(self):
        """Strong breadth score (+0.6) should strongly confirm a bullish direction."""
        mb = MarketBreadth(
            breadth_score=0.6,
            advance_decline_ratio=0.8,
            advancing_count=9, declining_count=2,
            symbols_fetched=11,
        )
        score, detail = score_market_breadth(mb, "bullish")
        assert score >= 0.35, f"Expected strong confirmation, got {score}"
        assert "Strong breadth" in detail or "confirms" in detail.lower()

    def test_strong_bearish_confirms_bearish(self):
        """Strong breadth score (-0.6) should confirm a bearish direction."""
        mb = MarketBreadth(
            breadth_score=-0.6,
            advance_decline_ratio=0.2,
            advancing_count=2, declining_count=9,
            symbols_fetched=11,
        )
        score, detail = score_market_breadth(mb, "bearish")
        assert score >= 0.35

    def test_breadth_opposes_bullish(self):
        """Negative breadth should penalize bullish trades."""
        mb = MarketBreadth(
            breadth_score=-0.4,
            advance_decline_ratio=0.2,
            advancing_count=2, declining_count=9,
            symbols_fetched=11,
        )
        score, detail = score_market_breadth(mb, "bullish")
        assert score < 0, f"Expected negative score, got {score}"

    def test_breadth_opposes_bearish(self):
        """Positive breadth should penalize bearish trades."""
        mb = MarketBreadth(
            breadth_score=0.4,
            advance_decline_ratio=0.8,
            advancing_count=9, declining_count=2,
            symbols_fetched=11,
        )
        score, detail = score_market_breadth(mb, "bearish")
        assert score < 0

    def test_neutral_breadth(self):
        """Near-zero breadth should score close to 0."""
        mb = MarketBreadth(
            breadth_score=0.02,
            advance_decline_ratio=0.5,
            advancing_count=5, declining_count=5, flat_count=1,
            symbols_fetched=11,
        )
        score, detail = score_market_breadth(mb, "bullish")
        assert abs(score) <= 0.15, f"Expected near-neutral, got {score}"

    def test_extreme_bullish_bonus(self):
        """Extreme bullish reading should add bonus for bullish trades."""
        mb = MarketBreadth(
            breadth_score=0.7,
            advance_decline_ratio=0.9,
            advancing_count=10, declining_count=1,
            symbols_fetched=11,
            extreme_reading=True,
            extreme_direction="bullish",
        )
        score, detail = score_market_breadth(mb, "bullish")
        # Should get +0.40 (strong) + 0.25 (extreme) = 0.65+
        assert score >= 0.60, f"Expected extreme bonus, got {score}"

    def test_extreme_opposing_penalty(self):
        """Extreme reading opposing our direction should penalize."""
        mb = MarketBreadth(
            breadth_score=-0.7,
            advance_decline_ratio=0.1,
            advancing_count=1, declining_count=10,
            symbols_fetched=11,
            extreme_reading=True,
            extreme_direction="bearish",
        )
        score, detail = score_market_breadth(mb, "bullish")
        assert score < -0.3, f"Expected heavy penalty, got {score}"

    def test_risk_on_confirms_bullish(self):
        """Risk-on environment should boost bullish trades."""
        mb = MarketBreadth(
            breadth_score=0.3,
            advance_decline_ratio=0.7,
            advancing_count=8, declining_count=3,
            symbols_fetched=11,
            risk_appetite=0.5,
            risk_signal="risk_on",
        )
        score, detail = score_market_breadth(mb, "bullish")
        assert score >= 0.40, f"Expected risk-on bonus, got {score}"
        assert "Risk-on" in detail

    def test_risk_off_confirms_bearish(self):
        """Risk-off environment should boost bearish trades."""
        mb = MarketBreadth(
            breadth_score=-0.3,
            advance_decline_ratio=0.3,
            advancing_count=3, declining_count=8,
            symbols_fetched=11,
            risk_appetite=-0.5,
            risk_signal="risk_off",
        )
        score, detail = score_market_breadth(mb, "bearish")
        assert score >= 0.40

    def test_risk_off_headwind_for_bullish(self):
        """Risk-off should create headwind for bullish trades."""
        mb = MarketBreadth(
            breadth_score=0.05,
            advance_decline_ratio=0.5,
            advancing_count=5, declining_count=5,
            symbols_fetched=11,
            risk_appetite=-0.5,
            risk_signal="risk_off",
        )
        score, detail = score_market_breadth(mb, "bullish")
        assert score < 0, f"Expected headwind, got {score}"

    def test_divergence_warning_bearish_div(self):
        """Bearish divergence with bullish direction should produce warning."""
        mb = MarketBreadth(
            breadth_score=-0.15,
            advance_decline_ratio=0.3,
            advancing_count=3, declining_count=8,
            symbols_fetched=11,
            spy_return_pct=0.5,  # SPY up
            breadth_divergence=True,
            divergence_direction="bearish_div",
        )
        score, detail = score_market_breadth(mb, "bullish")
        assert "WARNING" in detail

    def test_score_clamped_to_range(self):
        """Score should never exceed 1.0 or go below -0.40."""
        mb = MarketBreadth(
            breadth_score=0.9,
            advance_decline_ratio=0.95,
            advancing_count=10, declining_count=0, flat_count=1,
            symbols_fetched=11,
            extreme_reading=True,
            extreme_direction="bullish",
            risk_appetite=0.9,
            risk_signal="risk_on",
        )
        score, detail = score_market_breadth(mb, "bullish")
        assert score <= 1.0, f"Score exceeded max: {score}"
        assert score >= -0.40

    def test_BUY_CALL_direction(self):
        """Should accept BUY_CALL as bullish."""
        mb = MarketBreadth(breadth_score=0.6, symbols_fetched=11)
        score, _ = score_market_breadth(mb, "BUY_CALL")
        assert score > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Breadth Universe configuration
# ═══════════════════════════════════════════════════════════════════════════════

class TestBreadthUniverse:

    def test_has_11_symbols(self):
        assert len(BREADTH_UNIVERSE) == 11

    def test_all_have_required_fields(self):
        for sym, info in BREADTH_UNIVERSE.items():
            assert "name" in info, f"{sym} missing name"
            assert "weight" in info, f"{sym} missing weight"
            assert "type" in info, f"{sym} missing type"
            assert info["type"] in ("sector", "market", "risk"), f"{sym} has invalid type"

    def test_sectors_present(self):
        sectors = [s for s, i in BREADTH_UNIVERSE.items() if i["type"] == "sector"]
        assert len(sectors) == 6

    def test_risk_gauges_present(self):
        risk = [s for s, i in BREADTH_UNIVERSE.items() if i["type"] == "risk"]
        assert len(risk) == 3

    def test_inverse_symbols(self):
        inverse = [s for s, i in BREADTH_UNIVERSE.items() if i.get("inverse")]
        assert len(inverse) == 2  # TLT and GLD
        assert "TLT" in inverse
        assert "GLD" in inverse


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Integration: breadth in dynamic_exit momentum scorer
# ═══════════════════════════════════════════════════════════════════════════════

class TestMomentumBreadthIntegration:

    def _make_position(self, option_type="call", pnl_pct=0.1):
        return {
            "option_type": option_type,
            "unrealized_pnl_pct": pnl_pct,
            "entry_price": 5.0,
            "current_price": 5.0 * (1 + pnl_pct),
        }

    def test_no_breadth_no_crash(self):
        """Momentum scorer works fine without breadth data."""
        pos = self._make_position()
        result = score_momentum(pos, None, None, None)
        assert result.name == "momentum"
        assert result.score >= 0

    def test_breadth_opposing_bullish(self):
        """Bearish breadth should add urgency to bullish position exit."""
        pos = self._make_position("call")
        breadth = {"breadth_score": -0.5, "breadth_divergence": False}
        result = score_momentum(pos, None, None, breadth)
        assert "breadth_opposing" in result.signals
        assert result.score >= 0.15

    def test_breadth_opposing_bearish(self):
        """Bullish breadth should add urgency to bearish position exit."""
        pos = self._make_position("put")
        breadth = {"breadth_score": 0.5, "breadth_divergence": False}
        result = score_momentum(pos, None, None, breadth)
        assert "breadth_opposing" in result.signals

    def test_breadth_divergence_bullish(self):
        """Bearish divergence should add urgency to long position."""
        pos = self._make_position("call")
        breadth = {
            "breadth_score": -0.1,
            "breadth_divergence": True,
            "divergence_direction": "bearish_div",
        }
        result = score_momentum(pos, None, None, breadth)
        assert "breadth_divergence" in result.signals
        assert result.score >= 0.1

    def test_breadth_confirming_no_penalty(self):
        """Breadth confirming our direction should not add urgency."""
        pos = self._make_position("call")
        breadth = {
            "breadth_score": 0.5,
            "breadth_divergence": False,
        }
        result = score_momentum(pos, None, None, breadth)
        assert "breadth_opposing" not in result.signals
        assert "breadth_divergence" not in result.signals

    def test_combined_flow_and_breadth(self):
        """Both flow reversal and breadth opposition should stack."""
        pos = self._make_position("call")
        flow = {
            "cvd_trend": "falling",
            "cvd_acceleration": -0.5,
            "volume_exhausted": False,
        }
        breadth = {
            "breadth_score": -0.5,
            "breadth_divergence": True,
            "divergence_direction": "bearish_div",
        }
        result = score_momentum(pos, flow, None, breadth)
        # Should have both CVD and breadth signals
        assert "cvd_reversing" in result.signals
        assert "breadth_opposing" in result.signals
        assert result.score >= 0.50


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Thresholds
# ═══════════════════════════════════════════════════════════════════════════════

class TestThresholds:

    def test_advance_threshold_reasonable(self):
        assert 0.01 <= ADVANCE_THRESHOLD <= 0.10

    def test_extreme_threshold_reasonable(self):
        # 9+ of 11 symbols
        assert 0.75 <= EXTREME_THRESHOLD <= 0.95

    def test_divergence_threshold_reasonable(self):
        # Fewer than 4 of 11 supporting
        assert 0.25 <= DIVERGENCE_THRESHOLD <= 0.50


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
