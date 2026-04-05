"""
Weight Learner — Adaptive factor weight adjustment from trade outcomes.

After each closed trade, this module analyzes which of the 16 confluence
factors contributed to the outcome (profit or loss) and adjusts weights
using an exponential moving average approach.

How it works:
    1. Trade closes with P&L and factor breakdown
    2. For each factor that scored > 0 in the signal:
       - If trade was profitable: REWARD the factor (increase weight)
       - If trade lost money: PENALIZE the factor (decrease weight)
       - Magnitude scales with P&L size
    3. Apply learning rate and decay to prevent over-fitting
    4. Normalize weights to maintain the same total weight budget
    5. Save updated weights to DB for persistence across restarts

Key design decisions:
    - Slow learning rate (0.01-0.05) to prevent over-reaction to single trades
    - Weight floor/ceiling to prevent any factor from dominating or zeroing out
    - Exponential decay on old trades (recent trades matter more)
    - Weight normalization preserves total signal budget (14.75)
    - Version tracking for A/B testing and rollback
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional
from copy import deepcopy

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

# Default v5 weights (baseline — never modified, used for reset)
BASELINE_WEIGHTS = {
    "order_flow_imbalance": 1.5,
    "cvd_divergence": 1.0,
    "gex_alignment": 1.5,
    "dex_levels": 1.0,
    "vwap_rejection": 1.0,
    "volume_spike": 0.5,
    "delta_regime": 1.0,
    "pcr": 0.5,
    "max_pain": 0.5,
    "time_of_day": 0.5,
    "vanna_alignment": 0.75,
    "charm_pressure": 0.75,
    "sweep_activity": 0.75,
    "flow_toxicity": 0.5,
    "sector_divergence": 0.5,
    "agent_consensus": 1.5,
    # v6: align with config.py FACTOR_WEIGHTS_BASELINE (was missing 7 factors)
    "ema_sma_trend": 0.75,
    "bb_squeeze": 0.75,
    "support_resistance": 1.0,
    "candle_pattern": 0.5,
    "orb_breakout": 1.25,
    "market_breadth": 1.0,
    "vol_edge": 0.75,
}

TOTAL_WEIGHT_BUDGET = sum(BASELINE_WEIGHTS.values())  # 19.75

# Learning parameters
DEFAULT_LEARNING_RATE = 0.03      # How fast weights adapt (0.01 = slow, 0.10 = fast)
MIN_WEIGHT = 0.10                 # No factor goes below this
MAX_WEIGHT = 3.0                  # No factor goes above this
DECAY_FACTOR = 0.95               # How much old adjustments decay per new trade
MIN_TRADES_BEFORE_LEARNING = 5    # Don't adjust until we have this many trades


# ═══════════════════════════════════════════════════════════════════════════
# WEIGHT LEARNER
# ═══════════════════════════════════════════════════════════════════════════

class WeightLearner:
    """
    Adaptive factor weight optimizer.

    Usage:
        learner = WeightLearner()
        weights = learner.get_current_weights()  # Use in confluence engine
        learner.on_trade_closed(signal, pnl, exit_reason)  # After each trade
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        self._db_path = db_path or os.path.join(self._db_dir, "weight_learner.db")
        self._current_weights = deepcopy(BASELINE_WEIGHTS)
        self._version = "v5.0"
        self._learning_rate = DEFAULT_LEARNING_RATE
        self._trade_count = 0
        self._factor_performance: Dict[str, Dict] = {}  # Track per-factor metrics

        self._init_db()
        self._load_latest_weights()

    def _init_db(self):
        os.makedirs(self._db_dir, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS weight_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                version TEXT NOT NULL,
                weights TEXT NOT NULL,
                trigger_event TEXT,
                trade_count INTEGER,
                cumulative_pnl REAL,
                win_rate REAL,
                learning_rate REAL
            );

            CREATE TABLE IF NOT EXISTS factor_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                factor_name TEXT NOT NULL,
                signal_id TEXT,
                factor_score REAL,
                factor_max REAL,
                trade_pnl REAL,
                was_profitable INTEGER,
                contributed INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_fp_factor ON factor_performance(factor_name);
            CREATE INDEX IF NOT EXISTS idx_fp_ts ON factor_performance(timestamp);
            CREATE INDEX IF NOT EXISTS idx_ws_version ON weight_snapshots(version);
        """)
        conn.close()

    def _load_latest_weights(self):
        """Load the most recent weight snapshot from DB, or use baseline."""
        try:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT version, weights, trade_count FROM weight_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
            conn.close()

            if row:
                self._version = row[0]
                saved = json.loads(row[1])
                # Merge with baseline (in case new factors were added)
                for key in BASELINE_WEIGHTS:
                    if key in saved:
                        self._current_weights[key] = saved[key]
                self._trade_count = row[2] or 0
                logger.info(f"Loaded weights {self._version} (trade_count={self._trade_count})")
            else:
                logger.info("No saved weights found, using baseline v5.0")
                self._save_snapshot("initial_load")

        except Exception as e:
            logger.warning(f"Failed to load weights: {e}, using baseline")

    def get_current_weights(self) -> Dict[str, float]:
        """Get the current adaptive weights for use by confluence engine."""
        return deepcopy(self._current_weights)

    def get_version(self) -> str:
        return self._version

    # ── Core Learning Method ──

    async def on_trade_closed(self, trade: Dict, pnl: float, exit_reason: str):
        """
        Called after every trade closes. Adjusts factor weights based on outcome.

        Args:
            trade: Full trade dict (includes signal_id for factor lookup)
            pnl: Realized P&L in dollars
            exit_reason: Why the trade was closed
        """
        self._trade_count += 1

        # Get the original signal's factor breakdown
        signal_factors = self._get_signal_factors(trade.get("signal_id"))
        if not signal_factors:
            logger.warning(f"No factors found for signal {trade.get('signal_id')} — skipping weight update")
            return

        is_profitable = pnl > 0

        # ── Record per-factor performance ──
        self._record_factor_performance(signal_factors, pnl, is_profitable, trade.get("signal_id"))

        # ── Wait for minimum trade count ──
        if self._trade_count < MIN_TRADES_BEFORE_LEARNING:
            logger.info(f"Trade #{self._trade_count}: Need {MIN_TRADES_BEFORE_LEARNING} trades before weight adjustment")
            return

        # ── Calculate weight adjustments ──
        adjustments = self._calculate_adjustments(signal_factors, pnl, is_profitable)

        # ── Apply adjustments ──
        self._apply_adjustments(adjustments)

        # ── Normalize to preserve total budget ──
        self._normalize_weights()

        # ── Bump version ──
        minor = int(self._version.split(".")[-1]) + 1 if "." in self._version else 1
        self._version = f"v5.{minor}"

        # ── Save snapshot ──
        self._save_snapshot(f"trade_closed_{exit_reason}")

        logger.info(
            f"Weights updated → {self._version} | "
            f"Trade P&L: ${pnl:.2f} | "
            f"Adjusted {len(adjustments)} factors"
        )

    def _calculate_adjustments(self, factors: List[Dict], pnl: float, profitable: bool) -> Dict[str, float]:
        """
        Calculate weight adjustments for each factor based on trade outcome.

        Logic:
        - Factors that scored HIGH and trade was profitable → increase weight
        - Factors that scored HIGH and trade lost → decrease weight
        - Factors that scored LOW (didn't fire) are not adjusted
        - Magnitude proportional to P&L size (capped)
        """
        adjustments = {}

        # Normalize PnL to a -1 to +1 signal strength
        # $100 profit/loss → ±1.0 signal
        pnl_signal = max(-1.0, min(1.0, pnl / 100.0))

        for factor in factors:
            name = factor.get("name") or factor.get("factor", "")
            score = factor.get("score", 0)
            max_score = factor.get("max_score") or factor.get("weight", 0)

            if not name or name not in self._current_weights:
                continue

            if max_score <= 0:
                continue

            # Factor contribution ratio (0-1): how much did this factor "fire"?
            contribution = score / max_score if max_score > 0 else 0

            if contribution < 0.1:
                continue  # Factor didn't really fire — skip

            # Adjustment = learning_rate × pnl_signal × contribution
            # Positive pnl_signal + high contribution → increase weight
            # Negative pnl_signal + high contribution → decrease weight
            adj = self._learning_rate * pnl_signal * contribution

            adjustments[name] = adj

        return adjustments

    def _apply_adjustments(self, adjustments: Dict[str, float]):
        """Apply weight adjustments with clamping."""
        for name, adj in adjustments.items():
            current = self._current_weights.get(name, 0)
            new_weight = current + adj

            # Clamp to [MIN_WEIGHT, MAX_WEIGHT]
            new_weight = max(MIN_WEIGHT, min(MAX_WEIGHT, new_weight))
            self._current_weights[name] = round(new_weight, 4)

    def _normalize_weights(self):
        """Normalize weights to maintain the same total budget."""
        current_total = sum(self._current_weights.values())
        if current_total <= 0:
            self._current_weights = deepcopy(BASELINE_WEIGHTS)
            return

        scale = TOTAL_WEIGHT_BUDGET / current_total
        for name in self._current_weights:
            self._current_weights[name] = round(self._current_weights[name] * scale, 4)

    # ── Data Access ──

    def _get_signal_factors(self, signal_id: Optional[str]) -> Optional[List[Dict]]:
        """Get the factor breakdown from the original signal."""
        if not signal_id:
            return None
        try:
            from .signal_db import _get_conn
            conn = _get_conn()
            row = conn.execute("SELECT factors FROM signals WHERE id = ?", (signal_id,)).fetchone()
            conn.close()
            if row:
                factors_str = dict(row).get("factors")
                if factors_str:
                    return json.loads(factors_str) if isinstance(factors_str, str) else factors_str
        except Exception as e:
            logger.warning(f"Factor lookup error: {e}")
        return None

    def _record_factor_performance(self, factors: List[Dict], pnl: float, profitable: bool, signal_id: Optional[str]):
        """Store per-factor performance for analysis."""
        try:
            conn = sqlite3.connect(self._db_path)
            ts = datetime.now(timezone.utc).isoformat()
            for factor in factors:
                name = factor.get("name") or factor.get("factor", "")
                score = factor.get("score", 0)
                max_score = factor.get("max_score") or factor.get("weight", 0)
                contributed = 1 if score > 0 else 0

                conn.execute("""
                    INSERT INTO factor_performance (
                        timestamp, factor_name, signal_id, factor_score, factor_max,
                        trade_pnl, was_profitable, contributed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (ts, name, signal_id, score, max_score, pnl, int(profitable), contributed))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Factor performance record error: {e}")

    def _save_snapshot(self, trigger: str):
        """Save current weights to DB."""
        try:
            conn = sqlite3.connect(self._db_path)

            # Calculate cumulative metrics
            all_perf = conn.execute(
                "SELECT trade_pnl, was_profitable FROM factor_performance GROUP BY signal_id"
            ).fetchall()
            cum_pnl = sum(r[0] for r in all_perf) if all_perf else 0
            wins = sum(1 for r in all_perf if r[1]) if all_perf else 0
            total = len(all_perf) if all_perf else 0
            win_rate = (wins / total * 100) if total > 0 else 0

            conn.execute("""
                INSERT INTO weight_snapshots (
                    timestamp, version, weights, trigger_event,
                    trade_count, cumulative_pnl, win_rate, learning_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                self._version,
                json.dumps(self._current_weights),
                trigger,
                self._trade_count,
                cum_pnl,
                win_rate,
                self._learning_rate,
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Weight snapshot save error: {e}")

    # ── Analysis & Reporting ──

    def get_factor_importance(self) -> List[Dict]:
        """
        Rank factors by their predictive power for profitable trades.

        Returns factors sorted by profit contribution ratio.
        """
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row

            rows = conn.execute("""
                SELECT
                    factor_name,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN was_profitable = 1 THEN 1 ELSE 0 END) as winning_trades,
                    AVG(trade_pnl) as avg_pnl,
                    SUM(trade_pnl) as total_pnl,
                    AVG(factor_score) as avg_score,
                    SUM(CASE WHEN contributed = 1 AND was_profitable = 1 THEN 1 ELSE 0 END) as contrib_wins,
                    SUM(contributed) as total_contributions
                FROM factor_performance
                GROUP BY factor_name
                HAVING total_trades >= 3
                ORDER BY avg_pnl DESC
            """).fetchall()
            conn.close()

            result = []
            for r in rows:
                d = dict(r)
                d["win_rate"] = round(d["winning_trades"] / d["total_trades"] * 100, 1) if d["total_trades"] else 0
                d["current_weight"] = self._current_weights.get(d["factor_name"], 0)
                d["baseline_weight"] = BASELINE_WEIGHTS.get(d["factor_name"], 0)
                d["weight_change_pct"] = round(
                    (d["current_weight"] - d["baseline_weight"]) / d["baseline_weight"] * 100, 1
                ) if d["baseline_weight"] else 0
                result.append(d)

            return result

        except Exception as e:
            logger.warning(f"Factor importance error: {e}")
            return []

    def get_weight_history(self, limit: int = 20) -> List[Dict]:
        """Get the history of weight changes."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM weight_snapshots ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ── Signal Outcome Learning (Option 1) ──

    async def on_signal_outcome(
        self,
        signal_id: str,
        direction: str,
        direction_correct: int,   # 1 = correct, 0 = wrong
        factors_json: str,
        move_pct: float,
    ) -> None:
        """
        Adjust factor weights based on the outcome of a non-traded signal.

        Uses 50% of the normal learning rate — signal outcomes are directional
        evidence but noisier than real trade P&L (no actual fill, no slippage,
        no theta drag). The sign of `pnl_signal` is derived from whether the
        direction was correct and how large the SPY move was.
        """
        import json as _json

        try:
            factors = _json.loads(factors_json) if isinstance(factors_json, str) else factors_json
        except Exception:
            return

        if not factors:
            return

        # Synthesize a pseudo-PnL signal: correct + large move = +1, wrong = -1
        # Clamp move to ±2% for normalization (SPY rarely moves more)
        clamped_move = max(-2.0, min(2.0, move_pct or 0))
        magnitude = abs(clamped_move) / 2.0  # 0–1 scale

        if direction_correct == 1:
            pnl_signal = magnitude           # positive: reward the factors
        else:
            pnl_signal = -magnitude          # negative: penalize the factors

        if abs(pnl_signal) < 0.05:
            return  # Too small to learn from

        # Use half the normal learning rate for signal outcomes
        effective_lr = self._learning_rate * 0.5

        adjustments = {}
        for factor in factors:
            name = factor.get("name") or factor.get("factor", "")
            score = factor.get("score", 0)
            max_score = factor.get("max_score") or factor.get("weight", 0)

            if not name or name not in self._current_weights:
                continue
            if max_score <= 0:
                continue

            contribution = score / max_score if max_score > 0 else 0
            if contribution < 0.1:
                continue

            adjustments[name] = effective_lr * pnl_signal * contribution

        if not adjustments:
            return

        self._apply_adjustments(adjustments)
        self._normalize_weights()

        # Record per-factor performance (re-use existing table; pnl is synthetic)
        synthetic_pnl = pnl_signal * 50   # scale to dollar-ish range for display
        self._record_factor_performance(factors, synthetic_pnl, direction_correct == 1, signal_id)

        logger.debug(
            f"[WeightLearner] Signal outcome: signal={signal_id[:8]} "
            f"correct={direction_correct} move={move_pct:.2f}% "
            f"adjusted {len(adjustments)} factors"
        )

    def reset_to_baseline(self):
        """Reset weights to the original v5 baseline."""
        self._current_weights = deepcopy(BASELINE_WEIGHTS)
        self._version = "v5.0"
        self._save_snapshot("manual_reset")
        logger.info("Weights reset to baseline v5.0")

    def set_learning_rate(self, rate: float):
        """Adjust the learning rate (0.01-0.10 recommended)."""
        self._learning_rate = max(0.001, min(0.20, rate))
        logger.info(f"Learning rate set to {self._learning_rate}")

    def status(self) -> Dict:
        return {
            "version": self._version,
            "trade_count": self._trade_count,
            "learning_rate": self._learning_rate,
            "weights": self._current_weights,
            "baseline_weights": BASELINE_WEIGHTS,
            "weight_changes": {
                k: round(self._current_weights.get(k, 0) - BASELINE_WEIGHTS.get(k, 0), 4)
                for k in BASELINE_WEIGHTS
            },
            "total_budget": round(sum(self._current_weights.values()), 4),
        }
