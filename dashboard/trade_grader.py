"""
Trade Grader — Post-trade analysis and A/B/C/D/F grading.

Evaluates closed trades on execution quality, not just profitability.
A losing trade can still get an A if it followed the plan perfectly.
A winning trade can get a C if it was sloppy (poor entry, held too long).

Grading Criteria (100-point scale):
  - Plan Adherence (40 pts):  Did entry/exit match the signal's plan?
  - Risk Management (25 pts): Was stop respected? Position sized correctly?
  - Timing (20 pts):          Entry timing, hold duration, exit timing
  - Execution (15 pts):       Slippage, spread capture, fill quality

Grade Scale:
  A  = 90-100  (Textbook execution)
  B  = 75-89   (Good execution, minor issues)
  C  = 60-74   (Acceptable, room for improvement)
  D  = 40-59   (Poor execution, learning opportunity)
  F  = 0-39    (Failed trade — violated rules)

Also computes rolling scorecard metrics:
  - Win rate, profit factor, expectancy
  - Sharpe ratio, Sortino ratio
  - Max drawdown, recovery time
  - Grade distribution over time
"""

import math
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .signal_db import (
    get_trade_history,
    compute_scorecard,
)

logger = logging.getLogger(__name__)


# ── Grade thresholds ──
GRADE_A = 90
GRADE_B = 75
GRADE_C = 60
GRADE_D = 40


def grade_trade(trade: Dict, signal: Optional[Dict] = None) -> Dict:
    """
    Grade a closed trade on execution quality.

    Args:
        trade: Closed trade dict from signal_db (must have exit_time)
        signal: Original signal dict (optional, for plan adherence scoring)

    Returns:
        Dict with grade (A-F), score (0-100), breakdown, and suggestions
    """
    if not trade.get("exit_time"):
        return {"grade": "?", "score": 0, "reason": "Trade still open"}

    scores = {}

    # ── 1. Plan Adherence (40 pts) ──
    scores["plan_adherence"] = _score_plan_adherence(trade, signal)

    # ── 2. Risk Management (25 pts) ──
    scores["risk_management"] = _score_risk_management(trade, signal)

    # ── 3. Timing (20 pts) ──
    scores["timing"] = _score_timing(trade)

    # ── 4. Execution Quality (15 pts) ──
    scores["execution"] = _score_execution(trade, signal)

    # Total score
    total = sum(s["score"] for s in scores.values())
    total = max(0, min(100, total))

    # Assign letter grade
    if total >= GRADE_A:
        grade = "A"
    elif total >= GRADE_B:
        grade = "B"
    elif total >= GRADE_C:
        grade = "C"
    elif total >= GRADE_D:
        grade = "D"
    else:
        grade = "F"

    # Build suggestions
    suggestions = []
    for category, details in scores.items():
        if details.get("suggestions"):
            suggestions.extend(details["suggestions"])

    return {
        "grade": grade,
        "score": round(total, 1),
        "breakdown": {k: {"score": v["score"], "max": v["max"], "detail": v["detail"]}
                      for k, v in scores.items()},
        "suggestions": suggestions[:5],  # Top 5 actionable suggestions
        "pnl": trade.get("pnl", 0),
        "pnl_pct": trade.get("pnl_pct", 0),
        "exit_reason": trade.get("exit_reason", "unknown"),
    }


def _score_plan_adherence(trade: Dict, signal: Optional[Dict]) -> Dict:
    """
    Score how well the trade followed the signal's plan.
    Max 40 points.
    """
    score = 0.0
    max_score = 40.0
    details = []
    suggestions = []

    exit_reason = trade.get("exit_reason", "unknown")
    pnl = trade.get("pnl", 0) or 0

    # Exit adherence (20 pts)
    if exit_reason in ("profit_target", "stop_loss"):
        score += 20
        details.append(f"Exited at planned level ({exit_reason})")
    elif exit_reason == "time_stop_0dte":
        score += 15
        details.append("Time stop triggered (acceptable for 0DTE)")
    elif exit_reason == "manual":
        score += 10
        details.append("Manual exit — plan partially followed")
        suggestions.append("Let stops/targets work. Manual exits often leave money on the table.")
    elif exit_reason == "theta_decay":
        score += 5
        details.append("Exited on theta decay — late exit")
        suggestions.append("Consider tighter time stops to avoid excessive theta decay.")
    else:
        score += 5
        details.append(f"Unplanned exit ({exit_reason})")

    # Direction correctness (10 pts)
    if pnl > 0:
        score += 10
        details.append("Profitable — correct direction read")
    elif pnl == 0:
        score += 5
        details.append("Breakeven")
    else:
        # Check MFE — if trade was profitable at some point
        mfe = trade.get("max_favorable", 0) or 0
        if mfe > abs(pnl) * 0.5:
            score += 3
            details.append(f"Direction was right (MFE ${mfe:.2f}) but gave back gains")
            suggestions.append("Consider trailing stops when trade reaches 50%+ of target.")
        else:
            details.append("Direction incorrect or insufficient move")

    # Signal match (10 pts) — if we have the original signal
    if signal:
        signal_tier = signal.get("tier", "DEVELOPING")
        if signal_tier in ("TEXTBOOK", "HIGH"):
            score += 10
            details.append(f"High-quality signal ({signal_tier})")
        elif signal_tier == "VALID":
            score += 7
            details.append("Valid signal — adequate quality")
        else:
            score += 3
            details.append(f"Low-quality signal ({signal_tier})")
            suggestions.append("Prefer TEXTBOOK or HIGH tier signals for best results.")
    else:
        score += 5  # No signal to compare — neutral

    return {
        "score": min(score, max_score),
        "max": max_score,
        "detail": "; ".join(details),
        "suggestions": suggestions,
    }


def _score_risk_management(trade: Dict, signal: Optional[Dict]) -> Dict:
    """
    Score risk management discipline.
    Max 25 points.
    """
    score = 0.0
    max_score = 25.0
    details = []
    suggestions = []

    pnl = trade.get("pnl", 0) or 0
    mae = trade.get("max_adverse", 0) or 0
    mfe = trade.get("max_favorable", 0) or 0
    entry_price = trade.get("entry_price", 0) or 0
    quantity = trade.get("quantity", 1) or 1
    position_cost = entry_price * quantity * 100

    # Stop-loss discipline (10 pts)
    exit_reason = trade.get("exit_reason", "")
    if pnl < 0:
        if exit_reason == "stop_loss":
            score += 10
            details.append("Stop-loss honored — disciplined exit")
        elif mae > 0 and position_cost > 0:
            loss_pct = mae / position_cost
            if loss_pct < 0.03:  # Less than 3% of position
                score += 8
                details.append(f"Small loss ({loss_pct:.1%} of position)")
            elif loss_pct < 0.05:
                score += 5
                details.append(f"Moderate loss ({loss_pct:.1%} of position)")
                suggestions.append("Tighten stops to limit losses to <3% of position.")
            else:
                score += 2
                details.append(f"Large loss ({loss_pct:.1%} of position)")
                suggestions.append("Stop was too wide or not respected. Review risk limits.")
        else:
            score += 5  # Default for losses without MAE data
    else:
        score += 10  # Winner — no stop needed
        details.append("Profitable trade — risk managed successfully")

    # MFE/MAE ratio (10 pts) — measures how well gains were captured
    if mfe > 0 and mae > 0:
        mfe_mae_ratio = mfe / mae
        if mfe_mae_ratio > 3:
            score += 10
            details.append(f"Excellent MFE/MAE ratio: {mfe_mae_ratio:.1f}")
        elif mfe_mae_ratio > 2:
            score += 8
            details.append(f"Good MFE/MAE ratio: {mfe_mae_ratio:.1f}")
        elif mfe_mae_ratio > 1:
            score += 5
            details.append(f"Adequate MFE/MAE ratio: {mfe_mae_ratio:.1f}")
        else:
            score += 2
            details.append(f"Poor MFE/MAE ratio: {mfe_mae_ratio:.1f}")
            suggestions.append("Drawdown exceeded gains — consider tighter risk or better entries.")
    elif mfe > 0:
        score += 7
        details.append("Had favorable move, no significant drawdown")
    else:
        score += 3

    # Position sizing (5 pts)
    if signal:
        planned_contracts = signal.get("max_contracts", 0)
        actual_contracts = quantity
        if planned_contracts and actual_contracts <= planned_contracts:
            score += 5
            details.append("Position sized per plan")
        elif planned_contracts and actual_contracts > planned_contracts:
            score += 2
            details.append("Oversized position")
            suggestions.append("Stick to signal's recommended position size.")
    else:
        score += 3

    return {
        "score": min(score, max_score),
        "max": max_score,
        "detail": "; ".join(details),
        "suggestions": suggestions,
    }


def _score_timing(trade: Dict) -> Dict:
    """
    Score entry and exit timing.
    Max 20 points.
    """
    score = 0.0
    max_score = 20.0
    details = []
    suggestions = []

    # Hold duration (10 pts) — optimal is 15-45 min for 0DTE
    hold_minutes = 0
    try:
        entry_dt = datetime.fromisoformat(trade.get("entry_time", ""))
        exit_dt = datetime.fromisoformat(trade.get("exit_time", ""))
        hold_minutes = (exit_dt - entry_dt).total_seconds() / 60
    except (ValueError, TypeError):
        pass

    if hold_minutes > 0:
        if 10 <= hold_minutes <= 45:
            score += 10
            details.append(f"Optimal hold time: {hold_minutes:.0f}min")
        elif 5 <= hold_minutes <= 60:
            score += 7
            details.append(f"Acceptable hold time: {hold_minutes:.0f}min")
        elif hold_minutes < 5:
            score += 4
            details.append(f"Very short hold: {hold_minutes:.0f}min")
            suggestions.append("Scalping (<5min) has lower edge. Let trades develop.")
        else:
            score += 3
            details.append(f"Extended hold: {hold_minutes:.0f}min")
            suggestions.append("Holding 0DTE options >60min adds theta risk. Consider tighter time stops.")
    else:
        score += 5

    # Capture efficiency (10 pts) — how much of the available move was captured
    pnl = trade.get("pnl", 0) or 0
    mfe = trade.get("max_favorable", 0) or 0

    if mfe > 0 and pnl > 0:
        capture_ratio = pnl / mfe
        if capture_ratio > 0.8:
            score += 10
            details.append(f"Excellent capture: {capture_ratio:.0%} of peak")
        elif capture_ratio > 0.6:
            score += 8
            details.append(f"Good capture: {capture_ratio:.0%} of peak")
        elif capture_ratio > 0.4:
            score += 5
            details.append(f"Moderate capture: {capture_ratio:.0%} of peak")
            suggestions.append("You captured less than half the available move. Consider scaling out.")
        else:
            score += 3
            details.append(f"Poor capture: {capture_ratio:.0%} of peak")
            suggestions.append("Exited too late — gains reversed. Use trailing stops at 50% of target.")
    elif pnl > 0:
        score += 6
        details.append("Profitable, but no MFE data for capture analysis")
    elif pnl < 0 and mfe > 0:
        score += 2
        details.append(f"Had ${mfe:.2f} MFE but ended with loss — timing issue")
        suggestions.append("Trade was right but exit was wrong. Use profit-taking rules.")
    else:
        score += 3

    return {
        "score": min(score, max_score),
        "max": max_score,
        "detail": "; ".join(details),
        "suggestions": suggestions,
    }


def _score_execution(trade: Dict, signal: Optional[Dict]) -> Dict:
    """
    Score execution quality (slippage, fill quality).
    Max 15 points.
    """
    score = 0.0
    max_score = 15.0
    details = []
    suggestions = []

    entry_price = trade.get("entry_price", 0)

    if signal:
        planned_entry = signal.get("entry_price", 0)
        if planned_entry and entry_price:
            slippage = abs(entry_price - planned_entry) / planned_entry
            if slippage < 0.01:  # Less than 1% slippage
                score += 10
                details.append(f"Minimal slippage: {slippage:.2%}")
            elif slippage < 0.03:
                score += 7
                details.append(f"Moderate slippage: {slippage:.2%}")
            elif slippage < 0.05:
                score += 4
                details.append(f"High slippage: {slippage:.2%}")
                suggestions.append("Entry slippage >3%. Use limit orders closer to mid-price.")
            else:
                score += 2
                details.append(f"Excessive slippage: {slippage:.2%}")
                suggestions.append("Slippage >5% indicates poor fill. Check liquidity before entering.")
        else:
            score += 7
    else:
        score += 7  # No signal to compare

    # Mode bonus (5 pts)
    mode = trade.get("mode", "simulation")
    if mode == "alpaca_paper":
        score += 5
        details.append("Real paper fills (Alpaca)")
    else:
        score += 5
        details.append("Simulation mode (theoretical)")

    return {
        "score": min(score, max_score),
        "max": max_score,
        "detail": "; ".join(details),
        "suggestions": suggestions,
    }


def grade_and_store(trade: Dict, signal: Optional[Dict] = None) -> Dict:
    """
    Grade a trade and update its grade in the database.

    Args:
        trade: Closed trade dict
        signal: Original signal (optional)

    Returns:
        Grade result dict
    """
    result = grade_trade(trade, signal)

    # Update the trade's grade in the DB
    trade_id = trade.get("id")
    if trade_id and result.get("grade"):
        from .signal_db import _get_conn
        conn = _get_conn()
        conn.execute(
            "UPDATE trades SET grade = ? WHERE id = ?",
            (result["grade"], trade_id),
        )
        conn.commit()
        conn.close()

    return result


def compute_advanced_scorecard(
    trades: Optional[List[Dict]] = None,
    lookback_days: int = 30,
) -> Dict:
    """
    Extended scorecard with Sharpe, Sortino, max drawdown, and grade distribution.

    Args:
        trades: List of closed trades (if None, uses last N days)
        lookback_days: Number of days to look back

    Returns:
        Dict with all performance metrics
    """
    if trades is None:
        trades = get_trade_history(limit=500)

    # Filter to lookback window
    datetime.now(timezone.utc).isoformat()[:10]  # Today
    # For simplicity, use all provided trades (caller can pre-filter)

    basic = compute_scorecard(trades)

    closed = [t for t in trades if t.get("exit_time")]
    if not closed:
        return {**basic, "sharpe": 0, "sortino": 0, "max_drawdown": 0,
                "max_drawdown_pct": 0, "avg_grade_score": 0,
                "consecutive_wins": 0, "consecutive_losses": 0}

    # P&L series for Sharpe/Sortino
    pnls = [t.get("pnl", 0) or 0 for t in closed]
    n = len(pnls)

    # Sharpe ratio (annualized, assuming 252 trading days)
    mean_pnl = sum(pnls) / n if n > 0 else 0
    std_pnl = _stdev(pnls) if n > 1 else 0
    sharpe = (mean_pnl / std_pnl * math.sqrt(252)) if std_pnl > 0 else 0

    # Sortino ratio (only downside deviation)
    negative_pnls = [p for p in pnls if p < 0]
    downside_dev = _stdev(negative_pnls) if len(negative_pnls) > 1 else 0
    sortino = (mean_pnl / downside_dev * math.sqrt(252)) if downside_dev > 0 else 0

    # Max drawdown
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    # Consecutive wins/losses
    max_consec_wins = 0
    max_consec_losses = 0
    current_wins = 0
    current_losses = 0
    for pnl in pnls:
        if pnl > 0:
            current_wins += 1
            current_losses = 0
            max_consec_wins = max(max_consec_wins, current_wins)
        elif pnl < 0:
            current_losses += 1
            current_wins = 0
            max_consec_losses = max(max_consec_losses, current_losses)
        else:
            current_wins = 0
            current_losses = 0

    # Average grade score
    grade_scores = {"A": 95, "B": 82, "C": 67, "D": 50, "F": 25}
    grades = [grade_scores.get(t.get("grade", "?"), 50) for t in closed if t.get("grade")]
    avg_grade = sum(grades) / len(grades) if grades else 0

    return {
        **basic,
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round((max_dd / peak * 100) if peak > 0 else 0, 2),
        "avg_grade_score": round(avg_grade, 1),
        "consecutive_wins": max_consec_wins,
        "consecutive_losses": max_consec_losses,
        "total_closed": n,
        "mean_pnl": round(mean_pnl, 2),
    }


def _stdev(values: List[float]) -> float:
    """Standard deviation (population)."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)
