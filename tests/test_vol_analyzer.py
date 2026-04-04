"""
Tests for IV vs Realized Vol Analyzer (Step 10).

Covers:
  1. VolAnalysis defaults and to_dict()
  2. compute_realized_vol_daily()
  3. analyze_vol() — regimes, ratio, IV rank interaction
  4. score_vol_edge() — confluence Factor 23
  5. apply_vol_to_risk() — parameter modification
  6. Integration: greeks scorer with vol_regime
  7. Edge cases: insufficient data, decimal IV, extreme ratios
"""

import sys
import os
import math
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.vol_analyzer import (
    VolAnalysis,
    analyze_vol,
    compute_realized_vol_daily,
    score_vol_edge,
    apply_vol_to_risk,
    EXPENSIVE_THRESHOLD,
    CHEAP_THRESHOLD,
    VERY_EXPENSIVE_THRESHOLD,
    VERY_CHEAP_THRESHOLD,
    MIN_IV,
    MIN_RV,
)
from dashboard.dynamic_exit import score_greeks


# ═══════════════════════════════════════════════════════════════════════════════
# 1. VolAnalysis Defaults
# ═══════════════════════════════════════════════════════════════════════════════

class TestVolAnalysisDefaults:

    def test_default_values(self):
        va = VolAnalysis()
        assert va.atm_iv == 0.0
        assert va.realized_vol == 0.0
        assert va.iv_rv_ratio == 1.0
        assert va.vol_regime == "fair"
        assert va.target_mult == 1.0

    def test_to_dict(self):
        va = VolAnalysis(atm_iv=25.0, realized_vol=20.0, iv_rv_ratio=1.25)
        d = va.to_dict()
        assert d["atm_iv"] == 25.0
        assert d["iv_rv_ratio"] == 1.25
        assert "vol_regime" in d
        assert "target_mult" in d


# ═══════════════════════════════════════════════════════════════════════════════
# 2. compute_realized_vol_daily
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeRealizedVolDaily:

    def _make_daily_bars(self, n=25, base=500.0, daily_ret_pct=1.0):
        """Generate synthetic daily bars with ~daily_ret_pct moves."""
        import random
        random.seed(42)
        bars = []
        price = base
        for _ in range(n):
            bars.append({"close": price})
            price *= (1 + random.gauss(0, daily_ret_pct / 100))
        return bars

    def test_sufficient_data(self):
        bars = self._make_daily_bars(25, daily_ret_pct=1.0)
        rv = compute_realized_vol_daily(bars, window=20)
        assert rv > 0
        # ~1% daily moves → ~16% annualized (sqrt(252))
        assert 8 < rv < 30, f"RV={rv} outside expected range"

    def test_insufficient_data(self):
        bars = self._make_daily_bars(3)
        rv = compute_realized_vol_daily(bars, window=20)
        assert rv == 0.0

    def test_5_day_window(self):
        bars = self._make_daily_bars(10, daily_ret_pct=2.0)
        rv5 = compute_realized_vol_daily(bars, window=5)
        assert rv5 > 0

    def test_uses_close_or_c_key(self):
        bars = [{"c": 100 + i * 0.5} for i in range(25)]
        rv = compute_realized_vol_daily(bars, window=20)
        assert rv > 0

    def test_zero_prices_filtered(self):
        bars = [{"close": 0}] * 5 + [{"close": 100 + i * 0.3} for i in range(25)]
        rv = compute_realized_vol_daily(bars, window=20)
        assert rv > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. analyze_vol — regime classification
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalyzeVol:

    def test_expensive_regime(self):
        """IV 30% vs RV 20% → ratio 1.5 → expensive."""
        va = analyze_vol(atm_iv=30.0, realized_vol=20.0)
        assert va.vol_regime in ("expensive", "very_expensive")
        assert va.iv_rv_ratio > 1.0
        assert va.vol_premium > 0

    def test_cheap_regime(self):
        """IV 15% vs RV 25% → ratio 0.6 → cheap."""
        va = analyze_vol(atm_iv=15.0, realized_vol=25.0)
        assert va.vol_regime in ("cheap", "very_cheap")
        assert va.iv_rv_ratio < 1.0
        assert va.vol_premium < 0

    def test_fair_regime(self):
        """IV ≈ RV → fair."""
        va = analyze_vol(atm_iv=20.0, realized_vol=19.0)
        assert va.vol_regime == "fair"
        assert 0.9 < va.iv_rv_ratio < 1.1

    def test_very_expensive(self):
        """IV 45% vs RV 20% → ratio 2.25 → very expensive."""
        va = analyze_vol(atm_iv=45.0, realized_vol=20.0)
        assert va.vol_regime == "very_expensive"

    def test_very_cheap(self):
        """IV 10% vs RV 20% → ratio 0.5 → very cheap."""
        va = analyze_vol(atm_iv=10.0, realized_vol=20.0)
        assert va.vol_regime in ("cheap", "very_cheap")

    def test_decimal_iv_normalized(self):
        """IV passed as 0.25 (decimal) should be normalized to 25%."""
        va = analyze_vol(atm_iv=0.25, realized_vol=20.0)
        assert va.atm_iv == 25.0
        assert va.iv_rv_ratio > 1.0

    def test_insufficient_data(self):
        """Very low IV and RV → insufficient."""
        va = analyze_vol(atm_iv=2.0, realized_vol=1.0)
        assert va.data_quality == "insufficient"
        assert va.vol_regime == "fair"
        assert va.target_mult == 1.0

    def test_partial_data(self):
        """Only IV available, RV too low."""
        va = analyze_vol(atm_iv=20.0, realized_vol=1.0)
        assert va.data_quality == "partial"

    def test_iv_rank_confirms_expensive(self):
        """High IV Rank + expensive ratio → strengthened to very_expensive."""
        va = analyze_vol(atm_iv=28.0, realized_vol=22.0, iv_rank=80)
        assert va.vol_regime == "very_expensive"

    def test_iv_rank_confirms_cheap(self):
        """Low IV Rank + cheap ratio → strengthened to very_cheap."""
        va = analyze_vol(atm_iv=15.0, realized_vol=22.0, iv_rank=20)
        assert va.vol_regime == "very_cheap"

    def test_iv_rank_contradicts_expensive(self):
        """Low IV Rank + expensive ratio → dampened."""
        va = analyze_vol(atm_iv=28.0, realized_vol=22.0, iv_rank=20)
        # Should be dampened from expensive → fair
        assert va.vol_regime in ("fair", "expensive")

    def test_iv_rank_contradicts_cheap(self):
        """High IV Rank + cheap ratio → dampened."""
        va = analyze_vol(atm_iv=15.0, realized_vol=22.0, iv_rank=80)
        assert va.vol_regime in ("fair", "cheap")

    def test_with_daily_bars(self):
        """Should compute multi-timeframe RV from daily bars."""
        import random
        random.seed(42)
        daily = []
        p = 500
        for _ in range(25):
            daily.append({"close": p})
            p *= (1 + random.gauss(0, 0.01))

        va = analyze_vol(atm_iv=20.0, realized_vol=15.0, daily_bars=daily)
        assert va.rv_5d > 0 or va.rv_20d > 0

    def test_parameter_multipliers_expensive(self):
        """Expensive regime should have tight multipliers."""
        va = analyze_vol(atm_iv=35.0, realized_vol=20.0)
        assert va.target_mult < 1.0
        assert va.hold_mult < 1.0
        assert va.size_mult < 1.0

    def test_parameter_multipliers_cheap(self):
        """Cheap regime should have wide multipliers."""
        va = analyze_vol(atm_iv=12.0, realized_vol=20.0)
        assert va.target_mult > 1.0
        assert va.hold_mult > 1.0
        assert va.size_mult > 1.0

    def test_parameter_multipliers_fair(self):
        """Fair regime should have 1.0 multipliers."""
        va = analyze_vol(atm_iv=20.0, realized_vol=19.0)
        assert va.target_mult == 1.0
        assert va.hold_mult == 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. score_vol_edge — Factor 23
# ═══════════════════════════════════════════════════════════════════════════════

class TestScoreVolEdge:

    def test_cheap_positive_score(self):
        """Cheap options should give positive score (gamma edge)."""
        va = analyze_vol(atm_iv=12.0, realized_vol=20.0)
        score, detail = score_vol_edge(va, "bullish")
        assert score > 0.2
        assert "cheap" in detail.lower()

    def test_expensive_negative_score(self):
        """Expensive options should give negative score."""
        va = analyze_vol(atm_iv=35.0, realized_vol=20.0)
        score, detail = score_vol_edge(va, "bullish")
        assert score < 0
        assert "expensive" in detail.lower()

    def test_fair_near_zero(self):
        """Fair pricing should score ~0."""
        va = analyze_vol(atm_iv=20.0, realized_vol=19.0)
        score, detail = score_vol_edge(va, "bullish")
        assert abs(score) < 0.05

    def test_insufficient_data_zero(self):
        """Insufficient data should return 0."""
        va = VolAnalysis(data_quality="insufficient")
        score, detail = score_vol_edge(va, "bullish")
        assert score == 0.0

    def test_score_clamped(self):
        """Score should be clamped to [-0.30, 0.75]."""
        va = analyze_vol(atm_iv=8.0, realized_vol=30.0)  # Very cheap
        score, _ = score_vol_edge(va, "bullish")
        assert score <= 0.75
        assert score >= -0.30

    def test_direction_agnostic(self):
        """Vol edge applies equally to calls and puts."""
        va = analyze_vol(atm_iv=12.0, realized_vol=20.0)
        s_bull, _ = score_vol_edge(va, "bullish")
        s_bear, _ = score_vol_edge(va, "bearish")
        assert abs(s_bull - s_bear) < 0.01  # Same score


# ═══════════════════════════════════════════════════════════════════════════════
# 5. apply_vol_to_risk
# ═══════════════════════════════════════════════════════════════════════════════

class TestApplyVolToRisk:

    def _base_risk(self):
        return {
            "target_price": 7.50,
            "stop_price": 3.25,
            "trailing_stop_pct": 0.15,
            "max_hold_minutes": 25,
            "max_contracts": 2,
            "risk_amount": 100.0,
        }

    def test_insufficient_no_change(self):
        risk = self._base_risk()
        va = VolAnalysis(data_quality="insufficient")
        result = apply_vol_to_risk(risk, va)
        assert result["target_price"] == 7.50
        assert result["max_contracts"] == 2

    def test_expensive_tightens(self):
        risk = self._base_risk()
        va = analyze_vol(atm_iv=35.0, realized_vol=20.0)
        result = apply_vol_to_risk(risk, va)
        assert result["target_price"] < 7.50
        assert result["max_hold_minutes"] < 25
        assert result["trailing_stop_pct"] < 0.15

    def test_cheap_widens(self):
        risk = self._base_risk()
        va = analyze_vol(atm_iv=12.0, realized_vol=20.0)
        result = apply_vol_to_risk(risk, va)
        assert result["target_price"] > 7.50
        assert result["max_hold_minutes"] > 25

    def test_preserves_pre_values(self):
        risk = self._base_risk()
        va = analyze_vol(atm_iv=35.0, realized_vol=20.0)
        result = apply_vol_to_risk(risk, va)
        assert "_pre_vol_target" in result
        assert result["_pre_vol_target"] == 7.50

    def test_vol_analysis_in_output(self):
        risk = self._base_risk()
        va = analyze_vol(atm_iv=20.0, realized_vol=19.0)
        result = apply_vol_to_risk(risk, va)
        assert "vol_analysis" in result

    def test_min_contracts_one(self):
        risk = self._base_risk()
        risk["max_contracts"] = 1
        va = analyze_vol(atm_iv=35.0, realized_vol=20.0)
        result = apply_vol_to_risk(risk, va)
        assert result["max_contracts"] >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Integration: Greeks scorer with vol_regime
# ═══════════════════════════════════════════════════════════════════════════════

class TestGreeksVolRegimeIntegration:

    def _make_position(self, option_type="call"):
        return {
            "option_type": option_type,
            "unrealized_pnl_pct": 0.1,
            "live_greeks": {},
            "greeks_at_entry": {},
            "greeks_pnl": {},
            "hold_minutes": 10,
        }

    def test_no_vol_regime_no_crash(self):
        pos = self._make_position()
        result = score_greeks(pos, vol_regime=None)
        assert result.name == "greeks"

    def test_expensive_adds_urgency(self):
        pos = self._make_position()
        result_none = score_greeks(pos, vol_regime=None)
        result_exp = score_greeks(pos, vol_regime={
            "vol_regime": "very_expensive", "iv_rv_ratio": 1.6,
        })
        assert result_exp.score > result_none.score
        assert "vol_expensive" in result_exp.signals

    def test_cheap_reduces_urgency(self):
        """Cheap options should reduce greeks urgency (gamma cushion)."""
        # Need some base urgency to reduce
        pos = self._make_position()
        pos["live_greeks"] = {"theta": -0.10, "iv": 0.20, "delta": 0.30}
        pos["greeks_at_entry"] = {"theta": -0.04, "iv": 0.25, "delta": 0.40}
        pos["greeks_pnl"] = {"theta_pnl_pct": -0.08}

        result_none = score_greeks(pos, vol_regime=None)
        result_cheap = score_greeks(pos, vol_regime={
            "vol_regime": "very_cheap", "iv_rv_ratio": 0.6,
        })
        assert result_cheap.score <= result_none.score

    def test_fair_no_change(self):
        pos = self._make_position()
        result_none = score_greeks(pos, vol_regime=None)
        result_fair = score_greeks(pos, vol_regime={
            "vol_regime": "fair", "iv_rv_ratio": 1.0,
        })
        assert abs(result_fair.score - result_none.score) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Thresholds
# ═══════════════════════════════════════════════════════════════════════════════

class TestThresholds:

    def test_threshold_ordering(self):
        assert VERY_CHEAP_THRESHOLD < CHEAP_THRESHOLD < 1.0
        assert 1.0 < EXPENSIVE_THRESHOLD < VERY_EXPENSIVE_THRESHOLD

    def test_min_values(self):
        assert MIN_IV > 0
        assert MIN_RV > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
