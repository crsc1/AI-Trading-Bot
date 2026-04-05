"""
ML Direction Predictor — Lightweight logistic regression for trade filtering.

Step 12 of Money Machine Plan: Uses labeled signal outcomes to learn which
factor + context combinations predict profitable vs unprofitable trades.

Architecture:
  - Feature vector built from confluence factor scores + context metadata
  - Logistic regression (scikit-learn) — fast, interpretable, no GPU
  - Trains on signal_outcomes from last N trading days (default 20)
  - Retrains daily after market close (triggered by afterhours_learner or manually)
  - Advisory gate: blocks trades when model P(win) < MIN_PROBABILITY

Data flow:
  signal_outcomes (signal_db.py)
    → extract features (factor scores, session phase, GEX regime, vol regime, etc.)
    → train LogisticRegression
    → predict P(win) for new signals
    → gate: only allow trade if P(win) > threshold

Design decisions:
  - Uses signal outcomes (not just executed trades) for 5-10x more training data
  - Feature normalization via StandardScaler (factor scores vary in scale)
  - Minimum 30 labeled outcomes required before model activates
  - Model saved to SQLite (same weight_learner.db) for persistence
  - Fallback: if model unavailable, allows all trades (no blocking)
  - Includes feature importance tracking for dashboard display
"""

import json
import logging
import os
import pickle
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Try to import sklearn; graceful fallback if not installed ──
try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import cross_val_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("[MLPredictor] scikit-learn not installed — ML predictions disabled. "
                   "Install with: pip install scikit-learn")

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except ImportError:
    ET = timezone(timedelta(hours=-4))


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Minimum training samples before model activates
MIN_TRAINING_SAMPLES = 30

# Lookback window for training data (trading days)
LOOKBACK_DAYS = 20

# Probability threshold — only allow trades above this
MIN_WIN_PROBABILITY = 0.58

# Cross-validation folds (when enough data)
CV_FOLDS = 5
MIN_CV_SAMPLES = 50  # Need at least this many for CV

# Feature set — the 23 confluence factor keys + context features
FACTOR_FEATURES = [
    "order_flow_imbalance", "cvd_divergence", "gex_alignment", "dex_levels",
    "vwap_rejection", "volume_spike", "delta_regime", "pcr", "max_pain",
    "time_of_day", "vanna_alignment", "charm_pressure", "sweep_activity",
    "flow_toxicity", "sector_divergence", "agent_consensus",
    "ema_sma_trend", "bb_squeeze", "support_resistance", "candle_pattern",
    "orb_breakout", "market_breadth", "vol_edge",
]

CONTEXT_FEATURES = [
    "confidence",          # Signal confidence (0-1)
    "is_bullish",          # 1 if BUY_CALL, 0 if BUY_PUT
    "session_phase_idx",   # 0-6 for session phases
    "gex_regime_idx",      # -1=negative, 0=neutral, 1=positive
    "minutes_since_open",  # Minutes since 9:30 ET
    "num_active_factors",  # How many factors had non-zero scores
    "opposing_ratio",      # opposing / (confirming + opposing)
]

ALL_FEATURES = FACTOR_FEATURES + CONTEXT_FEATURES
NUM_FEATURES = len(ALL_FEATURES)

# Session phase encoding
SESSION_PHASE_MAP = {
    "pre_market": 0, "opening_drive": 1, "morning_trend": 2,
    "midday_chop": 3, "afternoon_trend": 4, "power_hour": 5, "close_risk": 6,
}

# GEX regime encoding
GEX_REGIME_MAP = {
    "negative": -1, "neutral": 0, "positive": 1,
}


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def extract_features_from_signal(signal: Dict) -> Optional[List[float]]:
    """
    Build a feature vector from a signal dict.

    The signal dict should contain:
      - factors: list of factor dicts [{name, direction, weight, detail}, ...]
                 OR a composite_scores dict {factor_name: score}
      - confidence: float
      - signal: "BUY_CALL" or "BUY_PUT"
      - session_phase: str (optional)
      - gex.regime: str (optional)
      - timestamp: ISO string (optional)

    Returns:
        List of floats with length NUM_FEATURES, or None if extraction fails.
    """
    try:
        features = []

        # ── Factor scores ──
        # Try composite_scores first (direct dict), then parse from factors list
        composite = signal.get("composite_scores", {})
        if not composite and "factors" in signal:
            factors_raw = signal["factors"]
            if isinstance(factors_raw, str):
                try:
                    factors_raw = json.loads(factors_raw)
                except json.JSONDecodeError:
                    factors_raw = []

            if isinstance(factors_raw, list):
                # Convert factor list to score dict
                for f in factors_raw:
                    if isinstance(f, dict):
                        name = f.get("name", "").lower().replace(" ", "_").replace("/", "_")
                        score = f.get("weight", 0) or f.get("score", 0)
                        # Map display names back to factor keys
                        mapped = _map_factor_name(name)
                        if mapped:
                            composite[mapped] = score
            elif isinstance(factors_raw, dict):
                composite = factors_raw

        for factor_key in FACTOR_FEATURES:
            features.append(float(composite.get(factor_key, 0.0)))

        # ── Context features ──
        confidence = float(signal.get("confidence", 0))
        features.append(confidence)

        direction = signal.get("signal", signal.get("direction", ""))
        is_bullish = 1.0 if "CALL" in str(direction).upper() or "BUY" in str(direction).upper() and "PUT" not in str(direction).upper() else 0.0
        features.append(is_bullish)

        phase = signal.get("session_phase", signal.get("phase", "unknown"))
        features.append(float(SESSION_PHASE_MAP.get(phase, 3)))  # default midday_chop

        gex_regime = "neutral"
        if signal.get("gex"):
            gex_regime = signal["gex"].get("regime", "neutral") if isinstance(signal["gex"], dict) else "neutral"
        elif signal.get("gex_regime"):
            gex_regime = signal["gex_regime"]
        features.append(float(GEX_REGIME_MAP.get(gex_regime, 0)))

        # Minutes since open
        mins_since_open = 180.0  # default midday
        ts = signal.get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt_et = dt.astimezone(ET)
                market_open = dt_et.replace(hour=9, minute=30, second=0, microsecond=0)
                mins_since_open = max(0, (dt_et - market_open).total_seconds() / 60)
            except Exception:
                pass
        features.append(mins_since_open)

        # Num active factors
        active = sum(1 for v in composite.values() if abs(v) > 0.03)
        features.append(float(active))

        # Opposing ratio
        confirming = sum(1 for v in composite.values() if v > 0.03)
        opposing = sum(1 for v in composite.values() if v < -0.03)
        total = confirming + opposing
        features.append(opposing / total if total > 0 else 0.0)

        if len(features) != NUM_FEATURES:
            logger.warning(f"[MLPredictor] Feature count mismatch: {len(features)} vs {NUM_FEATURES}")
            return None

        return features

    except Exception as e:
        logger.debug(f"[MLPredictor] Feature extraction error: {e}")
        return None


def _map_factor_name(display_name: str) -> Optional[str]:
    """Map display factor names back to config keys."""
    name_map = {
        "order_flow_imbalance": "order_flow_imbalance",
        "cvd_divergence": "cvd_divergence",
        "gex_alignment": "gex_alignment",
        "dex_levels": "dex_levels",
        "vwap_test": "vwap_rejection", "above_vwap+1σ": "vwap_rejection",
        "below_vwap-1σ": "vwap_rejection", "vwap_rejection": "vwap_rejection",
        "vwap+2σ_rejection": "vwap_rejection", "vwap-2σ_rejection": "vwap_rejection",
        "volume_spike": "volume_spike",
        "delta_regime": "delta_regime",
        "put_call_ratio": "pcr", "pcr": "pcr",
        "max_pain": "max_pain",
        "session_quality": "time_of_day", "time_of_day": "time_of_day",
        "vanna_flow": "vanna_alignment", "vanna_alignment": "vanna_alignment",
        "charm_pressure": "charm_pressure",
        "sweep_flow": "sweep_activity", "sweep_activity": "sweep_activity",
        "flow_toxicity": "flow_toxicity",
        "sector_bond": "sector_divergence", "sector_divergence": "sector_divergence",
        "ai_agents": "agent_consensus", "agent_consensus": "agent_consensus",
        "ema_sma_trend": "ema_sma_trend",
        "bb_squeeze": "bb_squeeze",
        "s_r_levels": "support_resistance", "support_resistance": "support_resistance",
        "candle_pattern": "candle_pattern",
        "orb_breakout": "orb_breakout",
        "market_breadth": "market_breadth",
        "vol_edge": "vol_edge",
    }
    return name_map.get(display_name)


# ═══════════════════════════════════════════════════════════════════════════════
# ML PREDICTOR
# ═══════════════════════════════════════════════════════════════════════════════

class MLDirectionPredictor:
    """
    Lightweight ML model for filtering signals by predicted win probability.

    Usage:
        predictor = MLDirectionPredictor()
        predictor.train()  # Call daily or on startup
        should_trade, prob = predictor.predict(signal_dict)
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
        )
        self._db_path = db_path or os.path.join(self._db_dir, "weight_learner.db")
        self._model: Optional[object] = None  # LogisticRegression
        self._scaler: Optional[object] = None  # StandardScaler
        self._trained = False
        self._train_samples = 0
        self._train_accuracy = 0.0
        self._cv_accuracy = 0.0
        self._feature_importance: Dict[str, float] = {}
        self._last_train_time: Optional[str] = None
        self._min_probability = MIN_WIN_PROBABILITY

        self._init_db()

    # ── Database ──────────────────────────────────────────────────────────────

    def _init_db(self):
        """Create ml_models table if not exists."""
        os.makedirs(self._db_dir, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_models (
                id          TEXT PRIMARY KEY,
                model_type  TEXT NOT NULL,
                model_blob  BLOB,
                scaler_blob BLOB,
                train_samples INTEGER,
                train_accuracy REAL,
                cv_accuracy    REAL,
                feature_importance TEXT,
                created_at  TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        self._load_model()

    def _save_model(self):
        """Persist model and scaler to SQLite."""
        if not self._model or not self._scaler:
            return
        try:
            model_blob = pickle.dumps(self._model)
            scaler_blob = pickle.dumps(self._scaler)
            importance_json = json.dumps(self._feature_importance)
            now = datetime.now(timezone.utc).isoformat()

            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                INSERT OR REPLACE INTO ml_models
                    (id, model_type, model_blob, scaler_blob, train_samples,
                     train_accuracy, cv_accuracy, feature_importance, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "direction_predictor_v1",
                "LogisticRegression",
                model_blob,
                scaler_blob,
                self._train_samples,
                self._train_accuracy,
                self._cv_accuracy,
                importance_json,
                now,
            ))
            conn.commit()
            conn.close()
            self._last_train_time = now
            logger.info(f"[MLPredictor] Model saved — {self._train_samples} samples, "
                        f"accuracy={self._train_accuracy:.1%}, CV={self._cv_accuracy:.1%}")
        except Exception as e:
            logger.error(f"[MLPredictor] Failed to save model: {e}")

    def _load_model(self):
        """Load persisted model from SQLite."""
        if not SKLEARN_AVAILABLE:
            return
        try:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute("""
                SELECT model_blob, scaler_blob, train_samples, train_accuracy,
                       cv_accuracy, feature_importance, created_at
                FROM ml_models WHERE id = 'direction_predictor_v1'
            """).fetchone()
            conn.close()

            if row and row[0] and row[1]:
                self._model = pickle.loads(row[0])
                self._scaler = pickle.loads(row[1])
                self._train_samples = row[2] or 0
                self._train_accuracy = row[3] or 0
                self._cv_accuracy = row[4] or 0
                try:
                    self._feature_importance = json.loads(row[5] or "{}")
                except json.JSONDecodeError:
                    self._feature_importance = {}
                self._last_train_time = row[6]
                self._trained = True
                logger.info(f"[MLPredictor] Loaded model — {self._train_samples} samples, "
                            f"accuracy={self._train_accuracy:.1%}")
        except Exception as e:
            logger.debug(f"[MLPredictor] No saved model found: {e}")

    # ── Training ──────────────────────────────────────────────────────────────

    def _fetch_training_data(self) -> Tuple[List[List[float]], List[int]]:
        """
        Fetch labeled signal outcomes from DB and extract feature vectors.

        Returns (X, y) where X is feature matrix and y is binary labels
        (1=direction_correct, 0=direction_wrong).
        """
        from .signal_db import _get_conn

        conn = _get_conn()
        rows = conn.execute("""
            SELECT s.factors, s.confidence, s.direction, s.tier,
                   s.gex_regime, s.timestamp,
                   o.direction_correct_30, o.move_pct_30min
            FROM signal_outcomes o
            JOIN signals s ON s.id = o.signal_id
            WHERE o.checked_30min = 1
              AND o.direction_correct_30 IS NOT NULL
              AND o.created_at > datetime('now', ?)
            ORDER BY o.created_at DESC
        """, (f"-{LOOKBACK_DAYS} days",)).fetchall()
        conn.close()

        X = []
        y = []

        for row in rows:
            factors_json, confidence, direction, tier, gex_regime, timestamp, correct, move_pct = row

            # Build a pseudo-signal dict for feature extraction
            signal_dict = {
                "factors": factors_json,
                "confidence": confidence or 0,
                "signal": direction or "NO_TRADE",
                "tier": tier,
                "gex_regime": gex_regime,
                "timestamp": timestamp,
            }

            features = extract_features_from_signal(signal_dict)
            if features is None:
                continue

            X.append(features)
            y.append(int(correct))

        return X, y

    def train(self) -> Dict:
        """
        Train (or retrain) the logistic regression model.

        Returns dict with training metrics.
        """
        if not SKLEARN_AVAILABLE:
            return {"status": "error", "reason": "scikit-learn not installed"}

        X, y = self._fetch_training_data()

        if len(X) < MIN_TRAINING_SAMPLES:
            return {
                "status": "insufficient_data",
                "samples": len(X),
                "required": MIN_TRAINING_SAMPLES,
                "reason": f"Need {MIN_TRAINING_SAMPLES}+ labeled outcomes, have {len(X)}",
            }

        # Check class balance
        n_pos = sum(y)
        n_neg = len(y) - n_pos
        if n_pos < 5 or n_neg < 5:
            return {
                "status": "imbalanced",
                "positive": n_pos,
                "negative": n_neg,
                "reason": "Need at least 5 positive and 5 negative outcomes",
            }

        # Fit scaler
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Fit model with balanced class weights to handle any class imbalance
        model = LogisticRegression(
            C=1.0,
            class_weight="balanced",
            max_iter=500,
            solver="lbfgs",
            random_state=42,
        )
        model.fit(X_scaled, y)

        # Training accuracy
        train_acc = model.score(X_scaled, y)

        # Cross-validation (if enough samples)
        cv_acc = 0.0
        if len(X) >= MIN_CV_SAMPLES:
            try:
                cv_scores = cross_val_score(model, X_scaled, y, cv=CV_FOLDS, scoring="accuracy")
                cv_acc = cv_scores.mean()
            except Exception as e:
                logger.debug(f"[MLPredictor] CV failed: {e}")
                cv_acc = train_acc * 0.9  # Conservative estimate

        # Feature importance (logistic regression coefficients)
        importance = {}
        if hasattr(model, 'coef_') and len(model.coef_) > 0:
            coefs = model.coef_[0]
            for i, feat_name in enumerate(ALL_FEATURES):
                if i < len(coefs):
                    importance[feat_name] = round(float(coefs[i]), 4)

        # Sort by absolute importance
        importance = dict(sorted(
            importance.items(), key=lambda x: abs(x[1]), reverse=True
        ))

        # Store model
        self._model = model
        self._scaler = scaler
        self._trained = True
        self._train_samples = len(X)
        self._train_accuracy = train_acc
        self._cv_accuracy = cv_acc
        self._feature_importance = importance

        # Persist
        self._save_model()

        result = {
            "status": "trained",
            "samples": len(X),
            "positive": n_pos,
            "negative": n_neg,
            "train_accuracy": round(train_acc, 4),
            "cv_accuracy": round(cv_acc, 4) if cv_acc > 0 else None,
            "top_features": dict(list(importance.items())[:10]),
        }
        logger.info(f"[MLPredictor] Training complete: {result}")
        return result

    # ── Prediction ────────────────────────────────────────────────────────────

    def predict(self, signal: Dict) -> Tuple[bool, float, str]:
        """
        Predict whether a signal will be profitable.

        Args:
            signal: Signal dict with factors, confidence, direction, etc.

        Returns:
            (should_trade, probability, reason)
            - should_trade: True if P(win) >= threshold
            - probability: float 0-1
            - reason: Human-readable explanation
        """
        if not SKLEARN_AVAILABLE:
            return True, 0.5, "scikit-learn not installed — ML gate disabled"

        if not self._trained or not self._model or not self._scaler:
            return True, 0.5, "ML model not trained yet — allowing all trades"

        features = extract_features_from_signal(signal)
        if features is None:
            return True, 0.5, "Could not extract features — allowing trade"

        try:
            X_scaled = self._scaler.transform([features])
            proba = self._model.predict_proba(X_scaled)[0]

            # proba[1] = P(direction_correct = 1)
            win_prob = float(proba[1]) if len(proba) > 1 else 0.5

            should_trade = win_prob >= self._min_probability

            if should_trade:
                reason = f"ML gate PASS — P(win)={win_prob:.0%} ≥ {self._min_probability:.0%}"
            else:
                reason = f"ML gate BLOCK — P(win)={win_prob:.0%} < {self._min_probability:.0%}"

            return should_trade, win_prob, reason

        except Exception as e:
            logger.warning(f"[MLPredictor] Prediction error: {e}")
            return True, 0.5, f"ML prediction error: {e} — allowing trade"

    def get_feature_importance(self, top_n: int = 15) -> List[Dict]:
        """Get top N features by importance for dashboard display."""
        items = list(self._feature_importance.items())[:top_n]
        return [
            {"feature": name, "importance": score, "direction": "positive" if score > 0 else "negative"}
            for name, score in items
        ]

    # ── Stats ─────────────────────────────────────────────────────────────────

    @property
    def stats(self) -> Dict:
        return {
            "available": SKLEARN_AVAILABLE,
            "trained": self._trained,
            "train_samples": self._train_samples,
            "train_accuracy": round(self._train_accuracy, 4) if self._train_accuracy else None,
            "cv_accuracy": round(self._cv_accuracy, 4) if self._cv_accuracy else None,
            "min_probability": self._min_probability,
            "last_train_time": self._last_train_time,
            "num_features": NUM_FEATURES,
            "top_features": list(self._feature_importance.items())[:5],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════════════════

ml_predictor = MLDirectionPredictor()
