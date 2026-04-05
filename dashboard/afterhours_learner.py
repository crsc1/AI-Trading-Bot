"""
After-Hours Learning Loop — Batch analysis of daily trades for adaptive learning.

Runs post-market (4:00 PM+ ET) to analyze the day's trades holistically,
identify factor-level patterns, and make batch weight adjustments.

Unlike the per-trade WeightLearner (which adjusts after each trade), this module:
  1. Waits until ALL trades are closed
  2. Analyzes factor-outcome correlations across the full day
  3. Detects regime-specific patterns (e.g., "sweeps worked in low-vol but not high-vol")
  4. Applies a single batch weight update (more stable than per-trade updates)
  5. Generates a daily learning report stored for long-term analysis

This is the "learning while you sleep" component. The bot trades during market
hours with the weights it has, then improves them after hours based on results.

Philosophy: NOT too many restrictions. The bot must constantly learn and adapt.
"""

import asyncio
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone, time as dt_time, timedelta, date
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

AFTERHOURS_START = dt_time(16, 5)   # 4:05 PM ET — 5 min buffer after close
AFTERHOURS_END = dt_time(20, 0)     # 8:00 PM ET — latest analysis window
MIN_TRADES_FOR_ANALYSIS = 2         # Need at least 2 trades to learn from
BATCH_LEARNING_RATE = 0.05          # Slightly more aggressive than per-trade (0.03)
CORRELATION_THRESHOLD = 0.3         # Min correlation to consider a factor predictive
ANALYSIS_DB_NAME = "afterhours_analysis.db"


@dataclass
class FactorDayStats:
    """Per-factor statistics for a single trading day."""
    name: str = ""
    times_fired: int = 0           # How many signals included this factor (score > 10% of max)
    times_correct: int = 0          # How many of those trades were profitable
    times_wrong: int = 0
    avg_score_when_correct: float = 0.0
    avg_score_when_wrong: float = 0.0
    total_pnl_contribution: float = 0.0  # Estimated $ attributed to this factor
    accuracy: float = 0.0           # times_correct / times_fired
    edge: float = 0.0              # accuracy - 0.5 (positive = factor helps, negative = hurts)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "times_fired": self.times_fired,
            "times_correct": self.times_correct,
            "times_wrong": self.times_wrong,
            "accuracy": round(self.accuracy, 3),
            "edge": round(self.edge, 3),
            "avg_score_correct": round(self.avg_score_when_correct, 3),
            "avg_score_wrong": round(self.avg_score_when_wrong, 3),
            "total_pnl_contribution": round(self.total_pnl_contribution, 2),
        }


@dataclass
class DailyLearningReport:
    """Complete daily analysis report."""
    date: str = ""
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    net_pnl: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    factor_stats: List[FactorDayStats] = field(default_factory=list)
    best_factors: List[str] = field(default_factory=list)    # Top 3 factors by edge
    worst_factors: List[str] = field(default_factory=list)   # Bottom 3 factors by edge
    regime_context: Dict = field(default_factory=dict)       # Vol regime, GEX regime, etc.
    weight_adjustments: Dict = field(default_factory=dict)   # {factor: adjustment}
    insights: List[str] = field(default_factory=list)        # Human-readable learnings

    def to_dict(self) -> Dict:
        return {
            "date": self.date,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "net_pnl": round(self.net_pnl, 2),
            "win_rate": round(self.win_rate, 3),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "profit_factor": round(self.profit_factor, 2),
            "factor_stats": [f.to_dict() for f in self.factor_stats],
            "best_factors": self.best_factors,
            "worst_factors": self.worst_factors,
            "regime_context": self.regime_context,
            "weight_adjustments": self.weight_adjustments,
            "insights": self.insights,
        }


# ═══════════════════════════════════════════════════════════════════════════
# AFTER-HOURS LEARNING ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class AfterHoursLearner:
    """
    Batch after-hours analysis and learning.

    Runs as a background task after market close. Analyzes the full day's
    trades, identifies which factors were predictive, and adjusts weights
    for the next trading day.

    Usage:
        learner = AfterHoursLearner(weight_learner)
        await learner.start()  # Starts background monitoring
        ...
        await learner.stop()
    """

    def __init__(self, weight_learner=None, training_collector=None):
        self._weight_learner = weight_learner
        self._training_collector = training_collector
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_analysis_date: Optional[str] = None  # Prevent double-analysis

        # DB for storing daily reports
        db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        os.makedirs(db_dir, exist_ok=True)
        self._db_path = os.path.join(db_dir, ANALYSIS_DB_NAME)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS daily_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                report TEXT NOT NULL,
                weight_adjustments TEXT,
                pre_weights TEXT,
                post_weights TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS learning_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                insight_type TEXT NOT NULL,
                factor_name TEXT,
                description TEXT NOT NULL,
                metric_value REAL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_dr_date ON daily_reports(date);
            CREATE INDEX IF NOT EXISTS idx_li_date ON learning_insights(date);
        """)
        conn.close()

    # ── Lifecycle ──

    async def start(self):
        """Start the background after-hours monitoring loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("AfterHoursLearner started — waiting for market close")

    async def stop(self):
        """Stop the background loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("AfterHoursLearner stopped")

    async def _monitor_loop(self):
        """
        Background loop that waits for after-hours window and triggers analysis.

        Checks every 5 minutes. When it detects the after-hours window AND
        today hasn't been analyzed yet, runs the full analysis pipeline.
        """
        while self._running:
            try:
                if self._should_run_analysis():
                    today_str = date.today().isoformat()
                    logger.info(f"After-hours analysis starting for {today_str}")
                    report = await self.run_daily_analysis(today_str)
                    if report:
                        self._last_analysis_date = today_str
                        logger.info(
                            f"After-hours analysis complete: "
                            f"{report.total_trades} trades, "
                            f"win_rate={report.win_rate:.1%}, "
                            f"net_pnl=${report.net_pnl:.2f}, "
                            f"{len(report.weight_adjustments)} weights adjusted"
                        )
            except Exception as e:
                logger.error(f"After-hours analysis error: {e}", exc_info=True)

            await asyncio.sleep(300)  # Check every 5 minutes

    def _should_run_analysis(self) -> bool:
        """Check if we should run the after-hours analysis now."""
        try:
            from .confluence import ET
            now_et = datetime.now(ET)
            current_time = now_et.time()
            today_str = now_et.date().isoformat()

            # Are we in the after-hours window?
            if not (AFTERHOURS_START <= current_time <= AFTERHOURS_END):
                return False

            # Have we already analyzed today?
            if self._last_analysis_date == today_str:
                return False

            # Check DB too (in case of restarts)
            try:
                conn = sqlite3.connect(self._db_path)
                row = conn.execute(
                    "SELECT date FROM daily_reports WHERE date = ?", (today_str,)
                ).fetchone()
                conn.close()
                if row:
                    self._last_analysis_date = today_str
                    return False
            except Exception:
                pass

            return True

        except Exception:
            return False

    # ── Core Analysis Pipeline ──

    async def run_daily_analysis(self, date_str: Optional[str] = None) -> Optional[DailyLearningReport]:
        """
        Run the full daily analysis pipeline.

        Steps:
          1. Fetch all of today's closed trades
          2. Fetch the factor breakdown for each trade's signal
          3. Compute per-factor accuracy and edge
          4. Identify best/worst factors
          5. Calculate batch weight adjustments
          6. Apply adjustments to weight learner
          7. Store report and insights

        Can be called manually via API for backtesting or forced re-analysis.
        """
        if not date_str:
            date_str = date.today().isoformat()

        # Step 1: Get today's trades
        trades = self._get_days_trades(date_str)
        closed_trades = [t for t in trades if t.get("exit_time") and t.get("pnl") is not None]

        if len(closed_trades) < MIN_TRADES_FOR_ANALYSIS:
            logger.info(f"Only {len(closed_trades)} closed trades — need {MIN_TRADES_FOR_ANALYSIS} for analysis")
            return None

        # Step 2: Enrich trades with signal factor data
        enriched = self._enrich_with_factors(closed_trades)

        # Step 3: Compute factor statistics
        factor_stats = self._compute_factor_stats(enriched)

        # Step 4: Build the report
        report = self._build_report(date_str, closed_trades, factor_stats)

        # Step 5: Calculate and apply batch weight adjustments
        if self._weight_learner:
            pre_weights = self._weight_learner.get_current_weights()
            adjustments = self._calculate_batch_adjustments(factor_stats)
            report.weight_adjustments = adjustments

            if adjustments:
                self._apply_batch_adjustments(adjustments)
                post_weights = self._weight_learner.get_current_weights()

                # Store the weights snapshot
                self._store_report(date_str, report, pre_weights, post_weights)

                logger.info(f"Batch weight adjustment: {len(adjustments)} factors updated")
                for factor, adj in sorted(adjustments.items(), key=lambda x: abs(x[1]), reverse=True)[:5]:
                    direction = "↑" if adj > 0 else "↓"
                    logger.info(f"  {factor}: {direction} {abs(adj):.4f} (new: {post_weights.get(factor, 0):.4f})")
            else:
                self._store_report(date_str, report, pre_weights, pre_weights)
        else:
            self._store_report(date_str, report, {}, {})

        # Step 6: Store individual insights
        self._store_insights(date_str, report)

        return report

    def _get_days_trades(self, date_str: str) -> List[Dict]:
        """Fetch all trades for a given date."""
        try:
            from .signal_db import _get_conn
            conn = _get_conn()
            rows = conn.execute(
                "SELECT * FROM trades WHERE date(entry_time) = ? ORDER BY entry_time",
                (date_str,)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to fetch day's trades: {e}")
            return []

    def _enrich_with_factors(self, trades: List[Dict]) -> List[Dict]:
        """Add signal factor breakdown to each trade."""
        enriched = []
        try:
            from .signal_db import _get_conn
            conn = _get_conn()

            for trade in trades:
                sig_id = trade.get("signal_id")
                factors = []
                if sig_id:
                    row = conn.execute(
                        "SELECT factors, confidence, tier FROM signals WHERE id = ?",
                        (sig_id,)
                    ).fetchone()
                    if row:
                        row_dict = dict(row)
                        factors_raw = row_dict.get("factors")
                        if factors_raw and isinstance(factors_raw, str):
                            try:
                                factors = json.loads(factors_raw)
                            except (json.JSONDecodeError, TypeError):
                                factors = []
                        trade["signal_confidence"] = row_dict.get("confidence")
                        trade["signal_tier"] = row_dict.get("tier")

                trade["factors"] = factors
                enriched.append(trade)

            conn.close()
        except Exception as e:
            logger.warning(f"Factor enrichment error: {e}")
            enriched = trades

        return enriched

    def _compute_factor_stats(self, enriched_trades: List[Dict]) -> List[FactorDayStats]:
        """Compute per-factor accuracy and edge from enriched trade data."""
        factor_data: Dict[str, Dict] = {}  # factor_name → {correct_scores, wrong_scores, pnl_sum}

        for trade in enriched_trades:
            pnl = trade.get("pnl", 0)
            profitable = pnl > 0
            factors = trade.get("factors", [])

            for factor in factors:
                name = factor.get("name") or factor.get("factor", "")
                score = factor.get("score", 0)
                max_score = factor.get("max_score") or factor.get("weight", 0)

                if not name or max_score <= 0:
                    continue

                contribution = score / max_score if max_score > 0 else 0
                if contribution < 0.1:
                    continue  # Factor didn't meaningfully fire

                if name not in factor_data:
                    factor_data[name] = {
                        "correct_scores": [],
                        "wrong_scores": [],
                        "pnl_contributions": [],
                    }

                if profitable:
                    factor_data[name]["correct_scores"].append(contribution)
                else:
                    factor_data[name]["wrong_scores"].append(contribution)

                # Attribute PnL proportionally to this factor's contribution
                total_score = sum(
                    f.get("score", 0) for f in factors
                    if (f.get("score", 0) > 0 and f.get("max_score", 0) > 0)
                )
                pnl_share = (score / total_score * pnl) if total_score > 0 else 0
                factor_data[name]["pnl_contributions"].append(pnl_share)

        # Build FactorDayStats
        stats = []
        for name, data in factor_data.items():
            correct = len(data["correct_scores"])
            wrong = len(data["wrong_scores"])
            total = correct + wrong

            if total == 0:
                continue

            stat = FactorDayStats(
                name=name,
                times_fired=total,
                times_correct=correct,
                times_wrong=wrong,
                avg_score_when_correct=(sum(data["correct_scores"]) / correct) if correct > 0 else 0,
                avg_score_when_wrong=(sum(data["wrong_scores"]) / wrong) if wrong > 0 else 0,
                total_pnl_contribution=sum(data["pnl_contributions"]),
                accuracy=correct / total if total > 0 else 0,
                edge=(correct / total - 0.5) if total > 0 else 0,
            )
            stats.append(stat)

        # Sort by edge (best performing first)
        stats.sort(key=lambda s: s.edge, reverse=True)
        return stats

    def _build_report(
        self,
        date_str: str,
        trades: List[Dict],
        factor_stats: List[FactorDayStats],
    ) -> DailyLearningReport:
        """Build the complete daily learning report with insights."""
        wins = [t for t in trades if (t.get("pnl") or 0) > 0]
        losses = [t for t in trades if (t.get("pnl") or 0) <= 0]

        gross_profit = sum(t.get("pnl", 0) for t in wins)
        gross_loss = abs(sum(t.get("pnl", 0) for t in losses))

        report = DailyLearningReport(
            date=date_str,
            total_trades=len(trades),
            wins=len(wins),
            losses=len(losses),
            net_pnl=sum(t.get("pnl", 0) for t in trades),
            win_rate=len(wins) / len(trades) if trades else 0,
            avg_win=gross_profit / len(wins) if wins else 0,
            avg_loss=-gross_loss / len(losses) if losses else 0,
            profit_factor=gross_profit / gross_loss if gross_loss > 0 else float('inf'),
            factor_stats=factor_stats,
        )

        # Best and worst factors (by edge)
        report.best_factors = [s.name for s in factor_stats[:3] if s.edge > 0]
        report.worst_factors = [s.name for s in factor_stats[-3:] if s.edge < 0]

        # Get regime context
        report.regime_context = self._get_regime_context()

        # Generate human-readable insights
        report.insights = self._generate_insights(report, factor_stats)

        return report

    def _calculate_batch_adjustments(self, factor_stats: List[FactorDayStats]) -> Dict[str, float]:
        """
        Calculate batch weight adjustments based on daily factor performance.

        More measured than per-trade updates:
        - Only adjusts factors with clear statistical edge (or negative edge)
        - Uses the full day's data for more stable estimates
        - Caps maximum adjustment per factor per day
        """
        adjustments = {}

        for stat in factor_stats:
            if stat.times_fired < 2:
                continue  # Not enough data for this factor today

            # Edge must be meaningful (> CORRELATION_THRESHOLD or < -CORRELATION_THRESHOLD)
            if abs(stat.edge) < CORRELATION_THRESHOLD:
                continue  # Factor was roughly 50/50 — no clear signal

            # Adjustment = learning_rate × edge × log(times_fired)
            # More occurrences = more confidence in the edge
            import math
            confidence_scale = min(math.log2(stat.times_fired + 1), 3.0)  # Cap at ~8 fires
            adj = BATCH_LEARNING_RATE * stat.edge * confidence_scale

            # Cap maximum daily adjustment at ±0.15
            adj = max(-0.15, min(0.15, adj))

            adjustments[stat.name] = round(adj, 4)

        return adjustments

    def _apply_batch_adjustments(self, adjustments: Dict[str, float]):
        """Apply batch adjustments through the weight learner."""
        if not self._weight_learner:
            return

        # Direct weight manipulation (bypass per-trade pipeline)
        for factor, adj in adjustments.items():
            if factor in self._weight_learner._current_weights:
                current = self._weight_learner._current_weights[factor]
                new_val = max(0.10, min(3.0, current + adj))
                self._weight_learner._current_weights[factor] = round(new_val, 4)

        # Normalize and save
        self._weight_learner._normalize_weights()
        self._weight_learner._version = self._weight_learner._version.rstrip("0123456789") + \
            str(int(self._weight_learner._version.split(".")[-1] or 0) + 1)
        self._weight_learner._save_snapshot("afterhours_batch_analysis")

    def _get_regime_context(self) -> Dict:
        """Get the current regime context for the report."""
        try:
            from .signal_api import engine
            regime = getattr(engine, '_cached_regime', None)
            if regime and hasattr(regime, 'to_dict'):
                return regime.to_dict()
        except Exception:
            pass
        return {}

    def _generate_insights(
        self,
        report: DailyLearningReport,
        factor_stats: List[FactorDayStats],
    ) -> List[str]:
        """Generate human-readable learning insights from the day's analysis."""
        insights = []

        # Overall performance insight
        if report.win_rate >= 0.6:
            insights.append(
                f"Strong day: {report.win_rate:.0%} win rate across {report.total_trades} trades, "
                f"net ${report.net_pnl:.2f}"
            )
        elif report.win_rate < 0.4 and report.total_trades >= 3:
            insights.append(
                f"Challenging day: {report.win_rate:.0%} win rate across {report.total_trades} trades, "
                f"net ${report.net_pnl:.2f} — review factor alignment"
            )

        # Best factor insights
        for stat in factor_stats[:3]:
            if stat.edge > CORRELATION_THRESHOLD and stat.times_fired >= 2:
                insights.append(
                    f"Strong factor: {stat.name} fired {stat.times_fired}x with "
                    f"{stat.accuracy:.0%} accuracy (edge: +{stat.edge:.0%}) — increasing weight"
                )

        # Worst factor insights
        for stat in factor_stats:
            if stat.edge < -CORRELATION_THRESHOLD and stat.times_fired >= 2:
                insights.append(
                    f"Weak factor: {stat.name} fired {stat.times_fired}x with only "
                    f"{stat.accuracy:.0%} accuracy (edge: {stat.edge:.0%}) — decreasing weight"
                )

        # Regime-specific insight
        regime = report.regime_context
        if regime:
            vol_regime = regime.get("vol_regime", "unknown")
            insights.append(f"Regime context: {vol_regime} volatility environment")

        # Profit factor insight
        if report.profit_factor < 1.0 and report.total_trades >= 3:
            insights.append(
                f"Profit factor {report.profit_factor:.2f} < 1.0 — losses outweigh wins. "
                f"Avg win ${report.avg_win:.2f} vs avg loss ${report.avg_loss:.2f}"
            )
        elif report.profit_factor > 2.0:
            insights.append(
                f"Excellent profit factor {report.profit_factor:.2f} — "
                f"avg win ${report.avg_win:.2f} is {report.avg_win / abs(report.avg_loss):.1f}x avg loss"
                if report.avg_loss != 0 else
                "Excellent profit factor — no losses today"
            )

        return insights

    # ── Storage ──

    def _store_report(
        self,
        date_str: str,
        report: DailyLearningReport,
        pre_weights: Dict,
        post_weights: Dict,
    ):
        """Persist the daily report to the analysis DB."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                INSERT OR REPLACE INTO daily_reports
                (date, report, weight_adjustments, pre_weights, post_weights, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                date_str,
                json.dumps(report.to_dict()),
                json.dumps(report.weight_adjustments),
                json.dumps(pre_weights),
                json.dumps(post_weights),
                datetime.now(timezone.utc).isoformat(),
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to store daily report: {e}")

    def _store_insights(self, date_str: str, report: DailyLearningReport):
        """Store individual insights for querying."""
        try:
            conn = sqlite3.connect(self._db_path)
            now = datetime.now(timezone.utc).isoformat()

            for insight in report.insights:
                conn.execute("""
                    INSERT INTO learning_insights (date, insight_type, description, created_at)
                    VALUES (?, ?, ?, ?)
                """, (date_str, "daily_analysis", insight, now))

            # Store factor-level insights
            for stat in report.factor_stats:
                if abs(stat.edge) >= CORRELATION_THRESHOLD:
                    conn.execute("""
                        INSERT INTO learning_insights
                        (date, insight_type, factor_name, description, metric_value, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        date_str,
                        "factor_edge",
                        stat.name,
                        f"{stat.name}: {stat.accuracy:.0%} accuracy ({stat.times_fired} fires, edge {stat.edge:+.0%})",
                        stat.edge,
                        now,
                    ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to store insights: {e}")

    # ── API Methods ──

    def get_latest_report(self) -> Optional[Dict]:
        """Get the most recent daily analysis report."""
        try:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT report FROM daily_reports ORDER BY date DESC LIMIT 1"
            ).fetchone()
            conn.close()
            if row:
                return json.loads(row[0])
        except Exception as e:
            logger.warning(f"Failed to fetch latest report: {e}")
        return None

    def get_report_history(self, limit: int = 30) -> List[Dict]:
        """Get recent daily reports for trend analysis."""
        try:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT date, report FROM daily_reports ORDER BY date DESC LIMIT ?",
                (limit,)
            ).fetchall()
            conn.close()
            return [{"date": r[0], **json.loads(r[1])} for r in rows]
        except Exception:
            return []

    def get_factor_trend(self, factor_name: str, days: int = 30) -> List[Dict]:
        """Get a factor's edge trend over recent days — useful for detecting long-term drift."""
        try:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute("""
                SELECT date, metric_value FROM learning_insights
                WHERE factor_name = ? AND insight_type = 'factor_edge'
                ORDER BY date DESC LIMIT ?
            """, (factor_name, days)).fetchall()
            conn.close()
            return [{"date": r[0], "edge": r[1]} for r in rows]
        except Exception:
            return []

    def get_cumulative_insights(self, days: int = 7) -> List[str]:
        """Get all insights from the last N days."""
        try:
            conn = sqlite3.connect(self._db_path)
            cutoff = (date.today() - timedelta(days=days)).isoformat()
            rows = conn.execute("""
                SELECT description FROM learning_insights
                WHERE date >= ? ORDER BY date DESC, id DESC
            """, (cutoff,)).fetchall()
            conn.close()
            return [r[0] for r in rows]
        except Exception:
            return []

    def status(self) -> Dict:
        """Current status of the after-hours learner."""
        return {
            "running": self._running,
            "last_analysis_date": self._last_analysis_date,
            "latest_report": self.get_latest_report(),
        }
