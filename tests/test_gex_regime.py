"""
Tests for GEX Regime Strategy Switching (Step 9).

Covers:
  1. RegimeProfile defaults and to_dict()
  2. get_regime_profile() — neutral, positive, negative regimes
  3. Strength interpolation (0 → neutral, 1 → full regime)
  4. Wall proximity adjustments
  5. GEX flip proximity adjustments
  6. apply_regime_to_risk() — parameter modification
  7. regime_signal_filter() — advisory signal compatibility
  8. Integration: dynamic_exit urgency offset
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.gex_regime import (
    RegimeProfile,
    get_regime_profile,
    apply_regime_to_risk,
    regime_signal_filter,
    _lerp,
)
from dashboard.dynamic_exit import DynamicExitEngine


# ═══════════════════════════════════════════════════════════════════════════════
# 1. RegimeProfile Basics
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegimeProfileBasics:

    def test_default_profile(self):
        p = RegimeProfile()
        assert p.regime == "neutral"
        assert p.target_mult == 1.0
        assert p.stop_mult == 1.0
        assert p.size_mult == 1.0
        assert p.trailing_mult == 1.0
        assert p.max_hold_mult == 1.0

    def test_to_dict(self):
        p = RegimeProfile(regime="negative", regime_strength=0.7)
        d = p.to_dict()
        assert d["regime"] == "negative"
        assert d["regime_strength"] == 0.7
        assert "target_mult" in d
        assert "prefer_trend" in d

    def test_lerp_zero(self):
        assert _lerp(1.0, 1.5, 0.0) == 1.0

    def test_lerp_half(self):
        assert abs(_lerp(1.0, 1.5, 0.5) - 1.25) < 0.001

    def test_lerp_full(self):
        assert abs(_lerp(1.0, 1.5, 1.0) - 1.5) < 0.001


# ═══════════════════════════════════════════════════════════════════════════════
# 2. get_regime_profile — Neutral
# ═══════════════════════════════════════════════════════════════════════════════

class TestNeutralRegime:

    def test_neutral_regime(self):
        p = get_regime_profile("neutral", 0.0)
        assert p.regime == "neutral"
        assert p.target_mult == 1.0
        assert p.stop_mult == 1.0
        assert p.size_mult == 1.0

    def test_very_weak_positive(self):
        """Strength < 0.05 should be treated as neutral."""
        p = get_regime_profile("positive", 0.03)
        assert p.regime == "neutral"

    def test_very_weak_negative(self):
        p = get_regime_profile("negative", 0.02)
        assert p.regime == "neutral"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Negative GEX (Trend Mode)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNegativeGEX:

    def test_full_strength_negative(self):
        """Full negative GEX should expand targets and reduce size."""
        p = get_regime_profile("negative", 1.0)
        assert p.regime == "negative"
        assert p.target_mult > 1.2, f"Expected wider targets, got {p.target_mult}"
        assert p.stop_mult > 1.1, f"Expected wider stops, got {p.stop_mult}"
        assert p.size_mult < 0.85, f"Expected smaller size, got {p.size_mult}"
        assert p.trailing_mult > 1.1, f"Expected wider trailing, got {p.trailing_mult}"
        assert p.max_hold_mult > 1.2, f"Expected longer holds, got {p.max_hold_mult}"
        assert p.prefer_trend is True
        assert p.favor_momentum is True

    def test_half_strength_negative(self):
        """Half strength should partially interpolate."""
        p = get_regime_profile("negative", 0.5)
        assert p.regime == "negative"
        assert 1.1 < p.target_mult < 1.4
        assert 0.8 < p.size_mult < 1.0
        assert p.prefer_trend is True

    def test_mild_negative(self):
        """Strength 0.1-0.3 should give mild adjustments."""
        p = get_regime_profile("negative", 0.15)
        assert p.regime == "negative"
        assert 1.0 < p.target_mult < 1.1
        assert p.label == "Mild Negative GEX"
        assert p.prefer_trend is False  # strength < 0.3

    def test_exit_urgency_reduced(self):
        """Negative GEX should make exits less urgent (let trends run)."""
        p = get_regime_profile("negative", 0.8)
        assert p.exit_urgency_offset < 0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Positive GEX (Mean Reversion Mode)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPositiveGEX:

    def test_full_strength_positive(self):
        """Full positive GEX should tighten targets and increase size."""
        p = get_regime_profile("positive", 1.0)
        assert p.regime == "positive"
        assert p.target_mult < 0.85, f"Expected tighter targets, got {p.target_mult}"
        assert p.stop_mult < 0.90, f"Expected tighter stops, got {p.stop_mult}"
        assert p.size_mult > 1.05, f"Expected larger size, got {p.size_mult}"
        assert p.trailing_mult < 0.90, f"Expected tighter trailing, got {p.trailing_mult}"
        assert p.max_hold_mult < 0.80, f"Expected shorter holds, got {p.max_hold_mult}"
        assert p.prefer_trend is False
        assert p.favor_momentum is False

    def test_half_strength_positive(self):
        p = get_regime_profile("positive", 0.5)
        assert p.regime == "positive"
        assert 0.85 < p.target_mult < 1.0
        assert 1.0 < p.size_mult < 1.15

    def test_exit_urgency_increased(self):
        """Positive GEX should make exits more urgent (moves get capped)."""
        p = get_regime_profile("positive", 0.8)
        assert p.exit_urgency_offset > 0

    def test_tighten_after_timer(self):
        """Positive GEX should set a tighten timer."""
        p = get_regime_profile("positive", 1.0)
        assert p.tighten_after_minutes > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Wall Proximity
# ═══════════════════════════════════════════════════════════════════════════════

class TestWallProximity:

    def test_near_call_wall_reduces_target(self):
        """Price near call wall should reduce upside targets."""
        p = get_regime_profile(
            "negative", 0.5,
            spot=599.0, call_wall=600.0, put_wall=580.0,
        )
        # Without wall proximity, target_mult would be ~1.20
        # With spot at 599 (99% of call-to-put range), should be reduced
        assert p.target_mult < get_regime_profile("negative", 0.5).target_mult

    def test_near_put_wall_reduces_target(self):
        """Price near put wall should reduce downside targets."""
        p = get_regime_profile(
            "negative", 0.5,
            spot=581.0, call_wall=600.0, put_wall=580.0,
        )
        assert p.target_mult < get_regime_profile("negative", 0.5).target_mult

    def test_mid_range_no_wall_effect(self):
        """Price in middle of range should not trigger wall proximity."""
        p_mid = get_regime_profile(
            "negative", 0.5,
            spot=590.0, call_wall=600.0, put_wall=580.0,
        )
        p_no_walls = get_regime_profile("negative", 0.5)
        assert abs(p_mid.target_mult - p_no_walls.target_mult) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# 6. GEX Flip Proximity
# ═══════════════════════════════════════════════════════════════════════════════

class TestFlipProximity:

    def test_near_flip_tightens(self):
        """Price near GEX flip level should tighten parameters."""
        p = get_regime_profile(
            "negative", 0.5,
            spot=590.0, call_wall=600.0, put_wall=580.0,
            gex_flip=590.5,  # Within 0.1% of spot
        )
        p_no_flip = get_regime_profile(
            "negative", 0.5,
            spot=590.0, call_wall=600.0, put_wall=580.0,
            gex_flip=0,
        )
        assert p.target_mult < p_no_flip.target_mult
        assert p.stop_mult < p_no_flip.stop_mult

    def test_far_from_flip_no_effect(self):
        """Price far from flip should not trigger tightening."""
        p = get_regime_profile(
            "negative", 0.5,
            spot=590.0, gex_flip=560.0,  # 5% away
        )
        p_no_flip = get_regime_profile("negative", 0.5, spot=590.0)
        assert abs(p.target_mult - p_no_flip.target_mult) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# 7. apply_regime_to_risk
# ═══════════════════════════════════════════════════════════════════════════════

class TestApplyRegimeToRisk:

    def _base_risk(self):
        return {
            "tier": "HIGH",
            "trade_mode": "standard",
            "target_price": 7.50,
            "stop_price": 3.25,
            "pct_target": 7.50,
            "pct_stop": 3.25,
            "target_pct": "+50%",
            "stop_pct": "-35%",
            "trailing_stop_pct": 0.15,
            "max_hold_minutes": 25,
            "max_contracts": 2,
            "risk_amount": 100.0,
        }

    def test_neutral_no_change(self):
        """Neutral regime should not modify risk params."""
        risk = self._base_risk()
        profile = RegimeProfile(regime="neutral", regime_strength=0.0)
        result = apply_regime_to_risk(risk, profile)
        assert result["target_price"] == 7.50
        assert result["max_contracts"] == 2

    def test_negative_widens_targets(self):
        """Negative GEX should widen target_price."""
        risk = self._base_risk()
        profile = get_regime_profile("negative", 0.8)
        result = apply_regime_to_risk(risk, profile)
        assert result["target_price"] > 7.50
        assert result["trailing_stop_pct"] > 0.15
        assert result["max_hold_minutes"] > 25

    def test_positive_tightens_targets(self):
        """Positive GEX should tighten target_price."""
        risk = self._base_risk()
        profile = get_regime_profile("positive", 0.8)
        result = apply_regime_to_risk(risk, profile)
        assert result["target_price"] < 7.50
        assert result["trailing_stop_pct"] < 0.15
        assert result["max_hold_minutes"] < 25

    def test_negative_reduces_size(self):
        """Negative GEX should reduce max_contracts."""
        risk = self._base_risk()
        risk["max_contracts"] = 4
        profile = get_regime_profile("negative", 1.0)
        result = apply_regime_to_risk(risk, profile)
        assert result["max_contracts"] < 4

    def test_positive_increases_size(self):
        """Positive GEX should increase max_contracts."""
        risk = self._base_risk()
        risk["max_contracts"] = 4
        profile = get_regime_profile("positive", 1.0)
        result = apply_regime_to_risk(risk, profile)
        assert result["max_contracts"] >= 4

    def test_min_contracts_one(self):
        """Should never reduce below 1 contract."""
        risk = self._base_risk()
        risk["max_contracts"] = 1
        profile = get_regime_profile("negative", 1.0)
        result = apply_regime_to_risk(risk, profile)
        assert result["max_contracts"] >= 1

    def test_preserves_pre_regime_values(self):
        """Should save pre-regime values for logging."""
        risk = self._base_risk()
        profile = get_regime_profile("negative", 0.8)
        result = apply_regime_to_risk(risk, profile)
        assert "_pre_regime_target" in result
        assert result["_pre_regime_target"] == 7.50

    def test_gex_regime_in_output(self):
        """Result should contain gex_regime dict."""
        risk = self._base_risk()
        profile = get_regime_profile("negative", 0.5)
        result = apply_regime_to_risk(risk, profile)
        assert "gex_regime" in result
        assert result["gex_regime"]["regime"] == "negative"

    def test_positive_tighten_timer(self):
        """Positive GEX should add tighten timer."""
        risk = self._base_risk()
        profile = get_regime_profile("positive", 1.0)
        result = apply_regime_to_risk(risk, profile)
        assert result.get("gex_tighten_after_minutes", 0) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 8. regime_signal_filter
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegimeSignalFilter:

    def test_neutral_allows_everything(self):
        p = RegimeProfile(regime="neutral")
        ok, note = regime_signal_filter(p, "breakout")
        assert ok is True
        assert note == ""

    def test_positive_gex_blocks_breakout(self):
        """Strong positive GEX should warn against breakout signals."""
        p = get_regime_profile("positive", 0.8)
        ok, note = regime_signal_filter(p, "breakout")
        assert ok is False
        assert "headwind" in note

    def test_positive_gex_favors_fade(self):
        """Strong positive GEX should favor fade/mean reversion."""
        p = get_regime_profile("positive", 0.8)
        ok, note = regime_signal_filter(p, "mean_reversion")
        assert ok is True
        assert "boost" in note

    def test_negative_gex_blocks_fade(self):
        """Strong negative GEX should warn against fade signals."""
        p = get_regime_profile("negative", 0.8)
        ok, note = regime_signal_filter(p, "fade")
        assert ok is False
        assert "headwind" in note

    def test_negative_gex_favors_breakout(self):
        """Strong negative GEX should favor breakout signals."""
        p = get_regime_profile("negative", 0.8)
        ok, note = regime_signal_filter(p, "momentum")
        assert ok is True
        assert "boost" in note

    def test_weak_regime_allows_anything(self):
        """Weak regime (< 0.4) should not block any signal."""
        p = get_regime_profile("positive", 0.2)
        ok, _ = regime_signal_filter(p, "breakout")
        assert ok is True

    def test_unknown_signal_type_passes(self):
        p = get_regime_profile("positive", 0.8)
        ok, _ = regime_signal_filter(p, "unknown_type")
        assert ok is True


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Integration: Dynamic Exit Urgency Offset
# ═══════════════════════════════════════════════════════════════════════════════

class TestDynamicExitRegimeIntegration:

    def _make_position(self, option_type="call", pnl_pct=0.1):
        return {
            "option_type": option_type,
            "unrealized_pnl_pct": pnl_pct,
            "entry_price": 5.0,
            "current_price": 5.5,
        }

    def test_no_regime_no_offset(self):
        """Without regime, urgency should have no offset."""
        engine = DynamicExitEngine()
        pos = self._make_position()
        u = engine.evaluate(pos, gex_regime=None)
        assert u.urgency >= 0

    def test_negative_regime_reduces_urgency(self):
        """Negative GEX regime should reduce exit urgency (let trends run)."""
        engine = DynamicExitEngine()
        pos = self._make_position()

        u_no_regime = engine.evaluate(pos, gex_regime=None)
        u_neg_regime = engine.evaluate(
            pos,
            gex_regime={"exit_urgency_offset": -0.05, "regime": "negative"},
        )
        assert u_neg_regime.urgency <= u_no_regime.urgency

    def test_positive_regime_increases_urgency(self):
        """Positive GEX regime should increase exit urgency (moves are capped)."""
        engine = DynamicExitEngine()
        pos = self._make_position()

        u_no_regime = engine.evaluate(pos, gex_regime=None)
        u_pos_regime = engine.evaluate(
            pos,
            gex_regime={"exit_urgency_offset": 0.05, "regime": "positive"},
        )
        assert u_pos_regime.urgency >= u_no_regime.urgency


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
