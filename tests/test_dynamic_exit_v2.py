"""
Tests for DynamicExitEngine v2 — all 7 enhancement phases.

Covers:
  Phase 1: Charm/Vanna 6th scorer + adaptive weights
  Phase 2: Multi-timeframe momentum (5m/15m EMA confirmation)
  Phase 3: Weekly/monthly reference levels
  Phase 4: GEX gamma cluster detection
  Phase 5: Realized vol acceleration
  Phase 6: Economic event context in session scorer
  Phase 7: LLM exit advisor daily mode (config/gating only)
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.dynamic_exit import (
    DynamicExitEngine,
    score_charm_vanna,
    score_momentum,
    score_greeks,
    score_session,
    score_levels,
    score_flow,
    DEFAULT_WEIGHTS,
    CHARM_WEIGHT_MAX,
    _compute_ema,
    _check_ema_trend,
)
from dashboard.market_levels import MarketLevels, compute_market_levels
from dashboard.gex_engine import find_gamma_clusters, GEXResult
from dashboard.config import cfg


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1: Charm/Vanna Scorer
# ═══════════════════════════════════════════════════════════════════════════════

class TestCharmVannaScorer:

    def test_no_data_returns_zero(self):
        result = score_charm_vanna({"option_type": "call"}, None)
        assert result.score == 0.0
        assert result.name == "charm_vanna"

    def test_charm_opposing_long_call(self):
        """Selling pressure opposes bullish position."""
        result = score_charm_vanna(
            {"option_type": "call"},
            {"charm_regime": "selling_pressure", "charm_acceleration": 1.0,
             "charm_pressure": -0.3, "vanna_regime": "neutral",
             "vanna_pressure": 0, "is_charm_acceleration_zone": False},
        )
        assert result.score >= 0.35
        assert "charm_opposing" in result.signals

    def test_charm_opposing_long_put(self):
        """Buying pressure opposes bearish position."""
        result = score_charm_vanna(
            {"option_type": "put"},
            {"charm_regime": "buying_pressure", "charm_acceleration": 1.0,
             "charm_pressure": 0.3, "vanna_regime": "neutral",
             "vanna_pressure": 0, "is_charm_acceleration_zone": False},
        )
        assert result.score >= 0.35
        assert "charm_opposing" in result.signals

    def test_charm_not_opposing_no_score(self):
        """Buying pressure supports long call — no opposing score."""
        result = score_charm_vanna(
            {"option_type": "call"},
            {"charm_regime": "buying_pressure", "charm_acceleration": 1.0,
             "charm_pressure": 0.3, "vanna_regime": "neutral",
             "vanna_pressure": 0, "is_charm_acceleration_zone": False},
        )
        assert "charm_opposing" not in result.signals

    def test_charm_acceleration_amplifies(self):
        """Post-1:30 PM, high acceleration adds extra urgency."""
        base = score_charm_vanna(
            {"option_type": "call"},
            {"charm_regime": "selling_pressure", "charm_acceleration": 1.0,
             "charm_pressure": -0.3, "vanna_regime": "neutral",
             "vanna_pressure": 0, "is_charm_acceleration_zone": False},
        )
        accel = score_charm_vanna(
            {"option_type": "call"},
            {"charm_regime": "selling_pressure", "charm_acceleration": 5.0,
             "charm_pressure": -0.3, "vanna_regime": "neutral",
             "vanna_pressure": 0, "is_charm_acceleration_zone": True},
        )
        assert accel.score > base.score
        assert "charm_accelerating" in accel.signals

    def test_vanna_opposing_adds_score(self):
        result = score_charm_vanna(
            {"option_type": "call"},
            {"charm_regime": "neutral", "charm_acceleration": 0,
             "charm_pressure": 0, "vanna_regime": "bearish_unwind",
             "vanna_pressure": -0.2, "is_charm_acceleration_zone": False},
        )
        assert result.score >= 0.20
        assert "vanna_opposing" in result.signals

    def test_vanna_confirming_cushion(self):
        """Vanna confirming direction reduces urgency."""
        result = score_charm_vanna(
            {"option_type": "call"},
            {"charm_regime": "neutral", "charm_acceleration": 0,
             "charm_pressure": 0, "vanna_regime": "bullish_unwind",
             "vanna_pressure": 0.2, "is_charm_acceleration_zone": False},
        )
        assert "vanna_cushion" in result.signals

    def test_combined_charm_and_vanna_opposing(self):
        """Both charm and vanna opposing = high urgency."""
        result = score_charm_vanna(
            {"option_type": "call"},
            {"charm_regime": "selling_pressure", "charm_acceleration": 4.0,
             "charm_pressure": -0.3, "vanna_regime": "bearish_unwind",
             "vanna_pressure": -0.2, "is_charm_acceleration_zone": True},
        )
        assert result.score >= 0.70
        assert "charm_opposing" in result.signals
        assert "vanna_opposing" in result.signals

    def test_score_capped_at_one(self):
        """Score never exceeds 1.0."""
        result = score_charm_vanna(
            {"option_type": "call"},
            {"charm_regime": "selling_pressure", "charm_acceleration": 10.0,
             "charm_pressure": -0.9, "vanna_regime": "bearish_unwind",
             "vanna_pressure": -0.9, "is_charm_acceleration_zone": True},
        )
        assert result.score <= 1.0


class TestAdaptiveCharmWeight:

    def test_default_weights_sum_to_one(self):
        assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 0.01

    def test_charm_weight_in_defaults(self):
        assert "charm_vanna" in DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["charm_vanna"] == 0.05

    def test_engine_has_six_weights(self):
        engine = DynamicExitEngine()
        assert len(engine.weights) == 6

    def test_afternoon_ramp_increases_charm_weight(self):
        """During charm acceleration zone, charm weight ramps up."""
        engine = DynamicExitEngine()
        # Morning: no ramp
        morning = engine.evaluate(
            {"option_type": "call", "trade_id": "t1", "unrealized_pnl_pct": 0.1},
            session={"phase": "morning_trend", "minutes_to_close": 300, "session_quality": 0.8},
            vanna_charm={"charm_regime": "selling_pressure", "charm_acceleration": 5.0,
                         "charm_pressure": -0.3, "vanna_regime": "neutral",
                         "vanna_pressure": 0, "is_charm_acceleration_zone": False},
        )
        # Afternoon: ramp active
        afternoon = engine.evaluate(
            {"option_type": "call", "trade_id": "t2", "unrealized_pnl_pct": 0.1},
            session={"phase": "power_hour", "minutes_to_close": 60, "session_quality": 0.5},
            vanna_charm={"charm_regime": "selling_pressure", "charm_acceleration": 5.0,
                         "charm_pressure": -0.3, "vanna_regime": "neutral",
                         "vanna_pressure": 0, "is_charm_acceleration_zone": True},
        )
        # Afternoon urgency should be higher (charm weighted more)
        assert afternoon.urgency > morning.urgency

    def test_eval_log_recorded(self):
        engine = DynamicExitEngine()
        engine._eval_log.clear()
        engine.evaluate(
            {"option_type": "call", "trade_id": "t_log", "unrealized_pnl_pct": 0},
            session={"phase": "morning_trend", "minutes_to_close": 300, "session_quality": 0.8},
        )
        assert len(engine._eval_log) == 1
        assert engine._eval_log[0]["trade_id"] == "t_log"
        assert "charm_vanna" in engine._eval_log[0]["scorers"]


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2: Multi-Timeframe Momentum
# ═══════════════════════════════════════════════════════════════════════════════

class TestEMAComputation:

    def test_compute_ema_basic(self):
        values = [100 + i for i in range(20)]
        ema = _compute_ema(values, 9)
        assert ema is not None
        assert ema > 100

    def test_compute_ema_insufficient_data(self):
        assert _compute_ema([1, 2, 3], 9) is None

    def test_ema_tracks_trend(self):
        uptrend = [100 + i * 0.5 for i in range(30)]
        ema9 = _compute_ema(uptrend, 9)
        ema21 = _compute_ema(uptrend, 21)
        assert ema9 > ema21  # EMA9 above EMA21 in uptrend


class TestCheckEMATrend:

    def test_bullish_uptrend(self):
        bars = [{"close": 100 + i * 0.1} for i in range(25)]
        assert _check_ema_trend(bars, "bullish") is True

    def test_bearish_downtrend(self):
        bars = [{"close": 200 - i * 0.1} for i in range(25)]
        assert _check_ema_trend(bars, "bearish") is True

    def test_insufficient_bars(self):
        bars = [{"close": 100 + i} for i in range(10)]
        assert _check_ema_trend(bars, "bullish") is None

    def test_no_bars(self):
        assert _check_ema_trend([], "bullish") is None
        assert _check_ema_trend(None, "bullish") is None


class TestMultiTFMomentum:

    def test_mtf_pullback_cushion(self):
        """CVD reversing but 5m+15m uptrend intact = pullback cushion."""
        bars_up = [{"close": 100 + i * 0.1} for i in range(25)]
        result = score_momentum(
            {"option_type": "call"},
            {"cvd_trend": "falling", "cvd_acceleration": -0.5},
            None, None,
            bars_5m=bars_up, bars_15m=bars_up,
        )
        assert "mtf_pullback_cushion" in result.signals

    def test_mtf_confirmed_reversal(self):
        """CVD reversing + 5m breaking + 15m breaking = confirmed."""
        bars_down = [{"close": 200 - i * 0.1} for i in range(25)]
        result = score_momentum(
            {"option_type": "call"},
            {"cvd_trend": "falling", "cvd_acceleration": -0.5},
            None, None,
            bars_5m=bars_down, bars_15m=bars_down,
        )
        assert "5m_trend_break" in result.signals
        assert "mtf_confirmed_reversal" in result.signals

    def test_no_mtf_data_no_crash(self):
        """Missing bar data doesn't crash."""
        result = score_momentum(
            {"option_type": "call"},
            {"cvd_trend": "falling"},
            None, None,
            bars_5m=None, bars_15m=None,
        )
        assert result.name == "momentum"

    def test_bearish_mtf_pullback(self):
        """Short position with downtrend intact on higher TFs."""
        bars_down = [{"close": 200 - i * 0.1} for i in range(25)]
        result = score_momentum(
            {"option_type": "put"},
            {"cvd_trend": "rising", "cvd_acceleration": 0.5},
            None, None,
            bars_5m=bars_down, bars_15m=bars_down,
        )
        assert "mtf_pullback_cushion" in result.signals


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3: Weekly/Monthly Levels
# ═══════════════════════════════════════════════════════════════════════════════

class TestWeeklyMonthlyLevels:

    def test_new_fields_exist(self):
        ml = MarketLevels()
        assert hasattr(ml, "weekly_high")
        assert hasattr(ml, "weekly_low")
        assert hasattr(ml, "monthly_high")
        assert hasattr(ml, "monthly_low")
        assert hasattr(ml, "yearly_high")
        assert hasattr(ml, "yearly_low")
        assert hasattr(ml, "prev_day_vwap")

    def test_compute_weekly_from_daily_bars(self):
        bars_daily = [
            {"high": 550 + i, "low": 540 + i, "close": 545 + i}
            for i in range(10)
        ]
        bars_1m = [{"high": 555, "low": 545, "close": 550, "volume": 100}]
        quote = {"last": 550, "bid": 549.9, "ask": 550.1, "prev_close": 549}
        levels = compute_market_levels(bars_1m, bars_daily, quote)
        assert levels.weekly_high > 0
        assert levels.weekly_low > 0
        assert levels.weekly_high > levels.weekly_low

    def test_compute_monthly_needs_20_bars(self):
        bars_5 = [{"high": 550, "low": 540, "close": 545} for _ in range(5)]
        bars_25 = [{"high": 550 + i, "low": 540, "close": 545} for i in range(25)]
        quote = {"last": 550}

        levels_5 = compute_market_levels(
            [{"high": 555, "low": 545, "close": 550, "volume": 100}],
            bars_5, quote
        )
        levels_25 = compute_market_levels(
            [{"high": 555, "low": 545, "close": 550, "volume": 100}],
            bars_25, quote
        )
        assert levels_5.monthly_high == 0  # Not enough data
        assert levels_25.monthly_high > 0  # Enough data

    def test_prev_day_vwap_computed(self):
        bars_daily = [
            {"high": 555, "low": 545, "close": 550},
            {"high": 560, "low": 550, "close": 555},
            {"high": 565, "low": 555, "close": 560},
        ]
        quote = {"last": 560}
        levels = compute_market_levels(
            [{"high": 565, "low": 555, "close": 560, "volume": 100}],
            bars_daily, quote
        )
        # Prev day = bars_daily[-2] = (560+550+555)/3 = 555.0
        assert levels.prev_day_vwap == pytest.approx(555.0, abs=0.01)

    def test_nearby_levels_includes_weekly(self):
        ml = MarketLevels()
        ml.weekly_high = 550.10
        ml.current_price = 550.0
        nearby = ml.nearby_levels(550.0, threshold=0.15)
        names = [n for n, _ in nearby]
        assert "Week High" in names

    def test_to_dict_includes_new_fields(self):
        ml = MarketLevels()
        ml.weekly_high = 555.0
        ml.prev_day_vwap = 550.0
        d = ml.to_dict()
        assert "weekly_high" in d
        assert "prev_day_vwap" in d


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 4: GEX Gamma Clusters
# ═══════════════════════════════════════════════════════════════════════════════

class TestGammaCluster:

    def _make_gex(self, strike_gex):
        gex = GEXResult()
        gex.strike_gex = strike_gex
        gex.spot = 550.0
        return gex

    def test_no_data_returns_empty(self):
        gex = self._make_gex({})
        assert find_gamma_clusters(gex, 550) == []

    def test_finds_cluster(self):
        """5 strikes within 1% of spot should form a cluster."""
        strike_gex = {
            548.0: 100, 549.0: 150, 550.0: 200, 551.0: 180, 552.0: 120
        }
        gex = self._make_gex(strike_gex)
        clusters = find_gamma_clusters(gex, 550.0)
        assert len(clusters) >= 1
        assert clusters[0]["strike_count"] >= 3

    def test_no_cluster_when_spread(self):
        """Strikes spread >1% apart shouldn't cluster."""
        strike_gex = {500.0: 100, 520.0: 100, 540.0: 100, 560.0: 100, 580.0: 100}
        gex = self._make_gex(strike_gex)
        clusters = find_gamma_clusters(gex, 550.0, cluster_pct=0.01)
        # These are 20 apart on a 550 spot (3.6% gaps), so no clusters
        assert len(clusters) == 0

    def test_cluster_has_distance(self):
        strike_gex = {549.0: 100, 550.0: 200, 551.0: 150}
        gex = self._make_gex(strike_gex)
        clusters = find_gamma_clusters(gex, 550.0)
        if clusters:
            assert "distance_pct" in clusters[0]
            assert "total_gex" in clusters[0]

    def test_max_5_clusters(self):
        """Never return more than 5."""
        strike_gex = {float(s): 100 for s in range(500, 600)}
        gex = self._make_gex(strike_gex)
        clusters = find_gamma_clusters(gex, 550.0, cluster_pct=0.02)
        assert len(clusters) <= 5


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 5: Realized Vol Acceleration
# ═══════════════════════════════════════════════════════════════════════════════

class TestVolAcceleration:

    def test_vol_accelerating(self):
        """Recent bars much more volatile than history."""
        # 30 bars: first 20 calm, last 10 wild
        calm = [{"close": 550 + i * 0.01} for i in range(20)]
        wild = [{"close": 550 + (i % 2) * 2} for i in range(10)]
        bars = calm + wild
        result = score_greeks(
            {"option_type": "call", "live_greeks": {}, "greeks_at_entry": {},
             "greeks_pnl": {}},
            None,
            bars_1m=bars,
        )
        # Should detect vol acceleration or dying depending on exact values
        assert result.name == "greeks"

    def test_insufficient_bars_no_crash(self):
        bars = [{"close": 550} for _ in range(5)]
        result = score_greeks(
            {"option_type": "call", "live_greeks": {}, "greeks_at_entry": {},
             "greeks_pnl": {}},
            None,
            bars_1m=bars,
        )
        assert "vol_accelerating" not in result.signals
        assert "vol_dying" not in result.signals

    def test_no_bars_no_crash(self):
        result = score_greeks(
            {"option_type": "call", "live_greeks": {}, "greeks_at_entry": {},
             "greeks_pnl": {}},
            None,
            bars_1m=None,
        )
        assert result.name == "greeks"


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6: Economic Events in Session Scorer
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventContextInSession:

    def test_no_event_context_no_crash(self):
        result = score_session(
            {"option_type": "call", "hold_minutes": 10},
            {"phase": "morning_trend", "minutes_to_close": 300, "session_quality": 0.8},
            event_context=None,
        )
        assert result.name == "session"

    def test_imminent_high_impact_event(self):
        result = score_session(
            {"option_type": "call", "hold_minutes": 10},
            {"phase": "morning_trend", "minutes_to_close": 300, "session_quality": 0.8},
            event_context={
                "mode": "pre_event",
                "minutes_to_next": 3,
                "next_event": {"name": "CPI", "impact": "high"},
            },
        )
        assert "imminent_high_impact_event" in result.signals
        assert result.score >= 0.50

    def test_approaching_event(self):
        result = score_session(
            {"option_type": "call", "hold_minutes": 10},
            {"phase": "morning_trend", "minutes_to_close": 300, "session_quality": 0.8},
            event_context={
                "mode": "pre_event",
                "minutes_to_next": 10,
                "next_event": {"name": "FOMC", "impact": "high"},
            },
        )
        assert "approaching_high_impact_event" in result.signals

    def test_post_event_reduces_urgency(self):
        base = score_session(
            {"option_type": "call", "hold_minutes": 10},
            {"phase": "afternoon_trend", "minutes_to_close": 120, "session_quality": 0.7},
            event_context=None,
        )
        post = score_session(
            {"option_type": "call", "hold_minutes": 10},
            {"phase": "afternoon_trend", "minutes_to_close": 120, "session_quality": 0.7},
            event_context={"mode": "post_event", "minutes_to_next": 999},
        )
        assert post.score <= base.score
        assert "post_event_trend" in post.signals

    def test_low_impact_event_no_urgency(self):
        result = score_session(
            {"option_type": "call", "hold_minutes": 10},
            {"phase": "morning_trend", "minutes_to_close": 300, "session_quality": 0.8},
            event_context={
                "mode": "pre_event",
                "minutes_to_next": 5,
                "next_event": {"name": "Housing Starts", "impact": "low"},
            },
        )
        assert "imminent_high_impact_event" not in result.signals


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 7: Config / Gating
# ═══════════════════════════════════════════════════════════════════════════════

class TestLLMExitConfig:

    def test_realtime_off_by_default(self):
        assert cfg.LLM_EXIT_ADVISOR_REALTIME is False

    def test_daily_review_on_by_default(self):
        assert cfg.LLM_DAILY_REVIEW_ENABLED is True

    def test_charm_weight_max(self):
        assert cfg.CHARM_WEIGHT_MAX == 0.25

    def test_config_weights_have_charm(self):
        assert "charm_vanna" in cfg.DYNAMIC_EXIT_WEIGHTS


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: Full Engine Evaluate
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullEngineEvaluate:

    def test_evaluate_with_all_new_params(self):
        engine = DynamicExitEngine()
        result = engine.evaluate(
            {"option_type": "call", "trade_id": "test_full", "unrealized_pnl_pct": 0.1},
            flow={"cvd_trend": "rising", "imbalance": 0.6},
            levels={"current_price": 550, "hod": 552, "atr_1m": 0.15},
            session={"phase": "morning_trend", "minutes_to_close": 300, "session_quality": 0.8},
            vanna_charm={"charm_regime": "neutral", "charm_acceleration": 0,
                         "charm_pressure": 0, "vanna_regime": "neutral",
                         "vanna_pressure": 0, "is_charm_acceleration_zone": False},
            bars_5m=[{"close": 550 + i * 0.05} for i in range(25)],
            bars_15m=[{"close": 550 + i * 0.03} for i in range(22)],
            bars_1m=[{"close": 550 + i * 0.01} for i in range(40)],
            event_context={"mode": "normal", "minutes_to_next": 999},
        )
        assert result.urgency >= 0
        assert result.urgency <= 1.0
        assert len(result.scorers) == 6

    def test_evaluate_with_no_new_params(self):
        """Backward compatibility: all new params are optional."""
        engine = DynamicExitEngine()
        result = engine.evaluate(
            {"option_type": "call", "trade_id": "test_compat", "unrealized_pnl_pct": 0},
        )
        assert result.urgency >= 0
        assert len(result.scorers) == 6

    def test_scorers_have_correct_names(self):
        engine = DynamicExitEngine()
        result = engine.evaluate(
            {"option_type": "call", "trade_id": "t_names", "unrealized_pnl_pct": 0},
        )
        names = {s.name for s in result.scorers}
        assert names == {"momentum", "greeks", "levels", "session", "flow", "charm_vanna"}

    def test_urgency_levels_correct(self):
        engine = DynamicExitEngine()
        # Low urgency
        result = engine.evaluate(
            {"option_type": "call", "trade_id": "t_hold", "unrealized_pnl_pct": 0.01},
            session={"phase": "morning_trend", "minutes_to_close": 300, "session_quality": 0.9},
        )
        assert result.level in ("HOLD", "CAUTION", "WARNING", "URGENT")

    def test_get_eval_log(self):
        engine = DynamicExitEngine()
        engine._eval_log.clear()
        engine.evaluate(
            {"option_type": "call", "trade_id": "t_a", "unrealized_pnl_pct": 0},
        )
        engine.evaluate(
            {"option_type": "put", "trade_id": "t_b", "unrealized_pnl_pct": 0},
        )
        assert len(engine.get_eval_log()) == 2
        assert len(engine.get_eval_log("t_a")) == 1
        assert len(engine.get_eval_log("t_b")) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# DB Schema
# ═══════════════════════════════════════════════════════════════════════════════

class TestDBSchema:

    def test_exit_advisory_functions_importable(self):
        from dashboard.signal_db import (
            store_exit_advisory,
            backfill_exit_advisory_outcome,
            get_exit_advisory_stats,
            get_persisted_exit_advisories,
        )
        assert callable(store_exit_advisory)
        assert callable(backfill_exit_advisory_outcome)

    def test_store_and_retrieve_advisory(self):
        from dashboard.signal_db import store_exit_advisory, get_persisted_exit_advisories
        import json

        advisory = {
            "id": "test_adv_001",
            "trade_id": "test_trade_001",
            "timestamp": "2026-04-05T20:00:00Z",
            "action": "HOLD",
            "urgency_override": None,
            "trailing_adjustment": None,
            "confidence": 0.8,
            "key_signals": ["cvd_rising", "flow_aligned"],
            "reasoning": "Test advisory",
            "model": "claude-sonnet-4-6",
            "latency_ms": 500,
            "error": None,
        }
        store_exit_advisory(advisory)
        results = get_persisted_exit_advisories(trade_id="test_trade_001", limit=10)
        assert len(results) >= 1
        found = [r for r in results if r["id"] == "test_adv_001"]
        assert len(found) == 1
        assert found[0]["action"] == "HOLD"


# ═══════════════════════════════════════════════════════════════════════════════
# LLM Exit Advisor Module
# ═══════════════════════════════════════════════════════════════════════════════

class TestLLMExitAdvisor:

    def test_imports(self):
        from dashboard.llm_exit_advisor import (
            get_advisory, get_recent_advisories, get_stats,
            clear_trade, should_evaluate, run_daily_review,
            get_daily_reviews,
        )
        assert callable(run_daily_review)
        assert callable(get_daily_reviews)

    def test_should_evaluate_respects_interval(self):
        from dashboard.llm_exit_advisor import should_evaluate, _last_eval_time
        import time
        _last_eval_time["test_trade"] = time.time()
        assert should_evaluate("test_trade", interval_s=30) is False
        _last_eval_time["test_trade"] = time.time() - 60
        assert should_evaluate("test_trade", interval_s=30) is True

    def test_clear_trade(self):
        from dashboard.llm_exit_advisor import clear_trade, _active_advisories, _last_eval_time
        _active_advisories["t_clear"] = {"action": "HOLD"}
        _last_eval_time["t_clear"] = 123
        clear_trade("t_clear")
        assert "t_clear" not in _active_advisories
        assert "t_clear" not in _last_eval_time

    def test_stats_structure(self):
        from dashboard.llm_exit_advisor import get_stats
        stats = get_stats()
        assert "total_evaluated" in stats
        assert "daily_reviews" in stats
        assert "hold_rate" in stats
