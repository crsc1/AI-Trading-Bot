"""
Tests for Step 12: ML Direction Predictor.

Covers:
  1. Feature extraction from signal dicts
  2. Feature count and ordering
  3. Factor name mapping
  4. MLDirectionPredictor predict() fallback behavior
  5. Training with insufficient data
  6. Feature extraction edge cases
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.ml_predictor import (
    extract_features_from_signal,
    _map_factor_name,
    MLDirectionPredictor,
    FACTOR_FEATURES,
    CONTEXT_FEATURES,
    ALL_FEATURES,
    NUM_FEATURES,
    MIN_TRAINING_SAMPLES,
    SESSION_PHASE_MAP,
    GEX_REGIME_MAP,
    SKLEARN_AVAILABLE,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Feature constants
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeatureConstants:

    def test_factor_count(self):
        """Should have 23 factor features matching config."""
        assert len(FACTOR_FEATURES) == 23

    def test_context_count(self):
        """Should have 7 context features."""
        assert len(CONTEXT_FEATURES) == 7

    def test_total_feature_count(self):
        assert NUM_FEATURES == 30  # 23 + 7
        assert NUM_FEATURES == len(ALL_FEATURES)

    def test_session_phase_map_complete(self):
        expected = {"pre_market", "opening_drive", "morning_trend",
                    "midday_chop", "afternoon_trend", "power_hour", "close_risk"}
        assert set(SESSION_PHASE_MAP.keys()) == expected

    def test_gex_regime_map(self):
        assert GEX_REGIME_MAP["negative"] == -1
        assert GEX_REGIME_MAP["neutral"] == 0
        assert GEX_REGIME_MAP["positive"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Feature extraction
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeatureExtraction:

    def _make_signal(self, **overrides):
        """Build a realistic signal dict."""
        signal = {
            "composite_scores": {
                "order_flow_imbalance": 1.2,
                "cvd_divergence": 0.5,
                "gex_alignment": 0.8,
                "dex_levels": 0.3,
                "vwap_rejection": 0.7,
                "volume_spike": 0.3,
                "delta_regime": 0.6,
                "pcr": 0.2,
                "max_pain": 0.1,
                "time_of_day": 0.4,
                "vanna_alignment": 0.3,
                "charm_pressure": 0.2,
                "sweep_activity": 0.5,
                "flow_toxicity": -0.1,
                "sector_divergence": 0.2,
                "agent_consensus": 0.8,
                "ema_sma_trend": 0.4,
                "bb_squeeze": 0.3,
                "support_resistance": 0.6,
                "candle_pattern": 0.2,
                "orb_breakout": 0.9,
                "market_breadth": 0.5,
                "vol_edge": 0.3,
            },
            "confidence": 0.72,
            "signal": "BUY_CALL",
            "session_phase": "morning_trend",
            "gex": {"regime": "negative"},
            "timestamp": "2026-04-03T10:15:00-04:00",
        }
        signal.update(overrides)
        return signal

    def test_basic_extraction(self):
        """Should produce a feature vector of correct length."""
        signal = self._make_signal()
        features = extract_features_from_signal(signal)
        assert features is not None
        assert len(features) == NUM_FEATURES

    def test_factor_scores_extracted(self):
        """First 23 features should be factor scores."""
        signal = self._make_signal()
        features = extract_features_from_signal(signal)
        assert features[0] == 1.2  # order_flow_imbalance
        assert features[1] == 0.5  # cvd_divergence
        assert features[13] == -0.1  # flow_toxicity (negative)

    def test_confidence_feature(self):
        """Feature 23 (index 23) should be confidence."""
        signal = self._make_signal(confidence=0.72)
        features = extract_features_from_signal(signal)
        assert features[23] == 0.72

    def test_is_bullish_feature(self):
        """Feature 24 should be 1.0 for BUY_CALL, 0.0 for BUY_PUT."""
        call_signal = self._make_signal(signal="BUY_CALL")
        put_signal = self._make_signal(signal="BUY_PUT")

        call_features = extract_features_from_signal(call_signal)
        put_features = extract_features_from_signal(put_signal)

        assert call_features[24] == 1.0
        assert put_features[24] == 0.0

    def test_session_phase_feature(self):
        """Feature 25 should encode session phase."""
        signal = self._make_signal(session_phase="morning_trend")
        features = extract_features_from_signal(signal)
        assert features[25] == 2.0  # morning_trend = 2

    def test_gex_regime_feature(self):
        """Feature 26 should encode GEX regime."""
        signal = self._make_signal(gex={"regime": "negative"})
        features = extract_features_from_signal(signal)
        assert features[26] == -1.0

    def test_missing_factors_default_to_zero(self):
        """Missing factor scores should default to 0.0."""
        signal = self._make_signal()
        signal["composite_scores"] = {"order_flow_imbalance": 1.0}  # Only 1 factor
        features = extract_features_from_signal(signal)
        assert features is not None
        assert features[0] == 1.0  # Present
        assert features[1] == 0.0  # Missing → 0

    def test_empty_signal_returns_features(self):
        """Even an empty signal should produce features (all defaults)."""
        features = extract_features_from_signal({})
        assert features is not None
        assert len(features) == NUM_FEATURES

    def test_factors_from_json_string(self):
        """Should handle factors as JSON string (from DB)."""
        signal = {
            "factors": '[{"name": "Order Flow Imbalance", "weight": 1.2}]',
            "confidence": 0.5,
            "signal": "BUY_CALL",
        }
        features = extract_features_from_signal(signal)
        assert features is not None

    def test_num_active_factors_feature(self):
        """Feature 28 should count active factors (|score| > 0.03)."""
        signal = self._make_signal()
        features = extract_features_from_signal(signal)
        # Most composite_scores are > 0.03, so active should be high
        assert features[28] > 10  # At least 10+ active factors

    def test_opposing_ratio_feature(self):
        """Feature 29 should be opposing/(confirming+opposing)."""
        signal = self._make_signal()
        features = extract_features_from_signal(signal)
        # Only flow_toxicity is negative (-0.1), so opposing ratio is low
        assert 0 <= features[29] <= 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Factor name mapping
# ═══════════════════════════════════════════════════════════════════════════════

class TestFactorNameMapping:

    def test_direct_mapping(self):
        assert _map_factor_name("order_flow_imbalance") == "order_flow_imbalance"
        assert _map_factor_name("gex_alignment") == "gex_alignment"

    def test_display_name_mapping(self):
        assert _map_factor_name("vanna_flow") == "vanna_alignment"
        assert _map_factor_name("sweep_flow") == "sweep_activity"
        assert _map_factor_name("ai_agents") == "agent_consensus"
        assert _map_factor_name("s_r_levels") == "support_resistance"
        assert _map_factor_name("session_quality") == "time_of_day"

    def test_vwap_variants(self):
        assert _map_factor_name("vwap_test") == "vwap_rejection"
        assert _map_factor_name("vwap_rejection") == "vwap_rejection"

    def test_unknown_returns_none(self):
        assert _map_factor_name("nonexistent_factor") is None


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Predictor behavior
# ═══════════════════════════════════════════════════════════════════════════════

class TestMLDirectionPredictor:

    def test_predict_without_training(self):
        """Untrained predictor should allow all trades."""
        pred = MLDirectionPredictor.__new__(MLDirectionPredictor)
        pred._model = None
        pred._scaler = None
        pred._trained = False
        pred._min_probability = 0.58

        should_trade, prob, reason = pred.predict({"signal": "BUY_CALL"})
        assert should_trade is True
        assert prob == 0.5
        assert "not trained" in reason.lower()

    def test_stats_untrained(self):
        """Stats of untrained predictor."""
        pred = MLDirectionPredictor.__new__(MLDirectionPredictor)
        pred._model = None
        pred._scaler = None
        pred._trained = False
        pred._train_samples = 0
        pred._train_accuracy = 0
        pred._cv_accuracy = 0
        pred._min_probability = 0.58
        pred._last_train_time = None
        pred._feature_importance = {}

        stats = pred.stats
        assert stats["trained"] is False
        assert stats["train_samples"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Training with insufficient data
# ═══════════════════════════════════════════════════════════════════════════════

class TestMLTraining:

    @pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn not installed")
    def test_training_with_synthetic_data(self):
        """Train on synthetic data to verify pipeline works."""
        import numpy as np

        pred = MLDirectionPredictor.__new__(MLDirectionPredictor)
        pred._db_dir = "/tmp"
        pred._db_path = "/tmp/test_ml.db"
        pred._model = None
        pred._scaler = None
        pred._trained = False
        pred._train_samples = 0
        pred._train_accuracy = 0.0
        pred._cv_accuracy = 0.0
        pred._feature_importance = {}
        pred._last_train_time = None
        pred._min_probability = 0.58

        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        # Generate synthetic feature data
        np.random.seed(42)
        n_samples = 100
        X = np.random.randn(n_samples, NUM_FEATURES)
        y = (X[:, 0] + X[:, 1] > 0).astype(int)  # Simple linear boundary

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        model = LogisticRegression(max_iter=500, random_state=42)
        model.fit(X_scaled, y)

        pred._model = model
        pred._scaler = scaler
        pred._trained = True
        pred._train_samples = n_samples
        pred._train_accuracy = model.score(X_scaled, y)

        # Test prediction
        test_signal = {
            "composite_scores": {k: 0.5 for k in FACTOR_FEATURES},
            "confidence": 0.7,
            "signal": "BUY_CALL",
        }
        should_trade, prob, reason = pred.predict(test_signal)
        assert isinstance(should_trade, bool)
        assert 0 <= prob <= 1
        assert isinstance(reason, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
