"""
PositionManager API — Clean REST endpoints for the unified trading dashboard.

These endpoints power the new trading.html dashboard and replace the scattered
position/autotrader endpoints across signal_api.py.

Mount at /api/pm in the main FastAPI app.
"""

from fastapi import APIRouter, Query
from typing import Optional, Dict, Any
import logging

from .position_manager import PositionManager
from . import data_router
from .signal_db import (
    get_open_trades, get_trade_history, get_todays_trades, get_outcome_stats, get_llm_verdict_stats, get_persisted_verdicts,
)
from . import llm_validator
from . import llm_exit_advisor
from .signal_outcome_tracker import outcome_tracker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pm", tags=["position-manager"])

# ── Global instance (created in startup, shared with signal_api.py) ──

_pm: Optional[PositionManager] = None


def init_position_manager(pm: PositionManager):
    """Called at app startup to register the shared PositionManager instance."""
    global _pm
    _pm = pm
    logger.info("[PM API] PositionManager registered")


def get_pm() -> PositionManager:
    if not _pm:
        raise RuntimeError("PositionManager not initialized")
    return _pm


# ═══════════════════════════════════════════════════════════════════════════════
# POSITIONS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/positions")
async def get_positions():
    """Get all open positions with live P&L, Greeks, exit triggers."""
    pm = get_pm()
    positions = await pm.get_positions()
    summary = pm.get_portfolio_summary(positions)

    return {
        "positions": positions,
        "summary": summary,
        "exit_rules": pm.exit_rules.to_dict(),
    }


@router.post("/exit")
async def exit_position(body: Dict[str, Any]):
    """Manually exit a single position."""
    pm = get_pm()
    trade_id = body.get("trade_id")
    if not trade_id:
        return {"error": "trade_id required"}

    # Find the trade
    open_trades = get_open_trades()
    trade = next((t for t in open_trades if t["id"] == trade_id), None)
    if not trade:
        return {"error": f"Trade {trade_id} not found"}

    # Get current price
    positions = await pm.get_positions()
    pos = next((p for p in positions if p["trade_id"] == trade_id), None)
    exit_price = pos["current_price"] if pos else float(trade.get("entry_price", 0))

    success = await pm.exit_trade(trade, exit_price, "manual")
    return {"success": success, "trade_id": trade_id}


@router.post("/close-all")
async def close_all_positions():
    """Close all open positions."""
    pm = get_pm()
    positions = await pm.get_positions()
    results = []

    for pos in positions:
        trade = next(
            (t for t in get_open_trades() if t["id"] == pos["trade_id"]),
            None
        )
        if trade:
            success = await pm.exit_trade(trade, pos["current_price"], "manual_close_all")
            results.append({"trade_id": pos["trade_id"], "success": success})

    return {"closed": results}


# ═══════════════════════════════════════════════════════════════════════════════
# AUTOTRADER CONTROL
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/status")
async def get_status():
    """Get full autotrader status including decisions, daily P&L, weight learner."""
    pm = get_pm()

    # Daily P&L and open positions
    daily_pnl = pm._get_daily_pnl()
    open_positions = len(get_open_trades())

    # Trading hours check
    from datetime import datetime as _dt
    from .confluence import ET
    now_et = _dt.now(ET)
    in_trading_hours = pm.trading_start <= now_et.time() <= pm.trading_end

    # Weight learner + training data (singletons from signal_api)
    wl_status = {}
    td_status = {}
    try:
        from .signal_api import weight_learner, training_collector
        wl_status = weight_learner.status()
        td_status = training_collector.get_stats()
    except Exception:
        pass

    return {
        "enabled": pm.is_enabled,
        "running": pm.is_running,
        "mode": pm.mode,
        "min_tier": pm.min_tier,
        "min_confidence": pm.min_confidence,
        "config": pm.get_config(),
        "decisions": pm.get_decisions(50),
        "stats": pm.get_stats(),
        "data_health": data_router.get_health(),
        "daily_pnl": round(daily_pnl, 2),
        "open_positions": open_positions,
        "in_trading_hours": in_trading_hours,
        "daily_trades": len(get_todays_trades()),
        "weight_learner": wl_status,
        "training_data": td_status,
    }


@router.post("/enable")
async def enable_autotrader():
    """Enable autotrading."""
    pm = get_pm()
    pm.enable()
    return {"enabled": True}


@router.post("/disable")
async def disable_autotrader():
    """Disable autotrading."""
    pm = get_pm()
    pm.disable()
    return {"enabled": False}


@router.post("/config")
async def update_config(body: Dict[str, Any]):
    """Update autotrader configuration (risk limits, tier, confidence)."""
    pm = get_pm()
    pm.update_config(body)
    return {"config": pm.get_config()}


@router.get("/settings")
async def get_settings():
    """Return full paper trading settings for the Settings panel."""
    pm = get_pm()
    from .config import cfg
    return {
        "mode": "simulation",
        "account_balance": cfg.ACCOUNT_BALANCE,
        "risk": {
            "max_daily_loss": pm.risk.max_daily_loss,
            "max_open_positions": pm.risk.max_open_positions,
            "max_trades_per_day": pm.risk.max_trades_per_day,
            "max_risk_per_trade_pct": pm.risk.max_risk_per_trade_pct,
            "min_seconds_between_trades": pm.risk.min_seconds_between_trades,
            "daily_loss_throttle": pm.risk.daily_loss_throttle,
        },
        "min_tier": pm.min_tier,
        "min_confidence": pm.min_confidence,
        "exit_rules": pm.exit_rules.to_dict(),
        "trading_start": pm.trading_start.isoformat() if hasattr(pm, 'trading_start') else "09:35",
        "trading_end": pm.trading_end.isoformat() if hasattr(pm, 'trading_end') else "15:55",
        "dynamic_exit": {
            "enabled": getattr(pm, '_dex_enabled', getattr(cfg, 'DYNAMIC_EXIT_ENABLED', False)),
            "w_momentum": getattr(cfg, 'DEX_W_MOMENTUM', 0.25),
            "w_greeks": getattr(cfg, 'DEX_W_GREEKS', 0.20),
            "w_levels": getattr(cfg, 'DEX_W_LEVELS', 0.20),
            "w_session": getattr(cfg, 'DEX_W_SESSION', 0.15),
            "w_flow": getattr(cfg, 'DEX_W_FLOW', 0.20),
        },
        "fast_path": {
            "enabled": getattr(cfg, 'FAST_PATH_ENABLED', False),
            "min_tier": getattr(cfg, 'FAST_PATH_MIN_TIER', 'HIGH'),
            "min_confidence": getattr(cfg, 'FAST_PATH_MIN_CONFIDENCE', 0.65),
            "cooldown_seconds": getattr(cfg, 'FAST_PATH_COOLDOWN_SECONDS', 60),
        },
        "llm_validator": {
            "enabled": getattr(cfg, 'LLM_VALIDATOR_ENABLED', False),
            "min_tier": getattr(cfg, 'LLM_VALIDATOR_MIN_TIER', 'HIGH'),
        },
        "api_limits": _get_api_usage(),
        "data": {
            "theta_enabled": getattr(cfg, 'THETA_ENABLED', True),
            "theta_base_url": getattr(cfg, 'THETA_BASE_URL', 'http://localhost:25510'),
            "theta_ws_url": getattr(cfg, 'THETA_WS_URL', 'ws://localhost:25520/v1/events'),
            "theta_stream_enabled": getattr(cfg, 'THETA_STREAM_ENABLED', True),
            "alpaca_data_feed": getattr(cfg, 'ALPACA_DATA_FEED', 'sip'),
            "python_alpaca_ws_enabled": getattr(cfg, 'PYTHON_ALPACA_WS_ENABLED', False),
            "flow_engine_url": getattr(cfg, 'FLOW_ENGINE_HTTP_URL', 'http://localhost:8081'),
        },
    }


@router.post("/settings")
async def update_settings(body: Dict[str, Any]):
    """
    Save paper trading settings from the Settings panel.

    Accepted top-level keys:
      risk              dict   (max_daily_loss, max_open_positions, etc.)
      exit_rules        dict   (stop_loss_pct, profit_target_pct, etc.)
      min_tier          str    (DEVELOPING | VALID | HIGH | TEXTBOOK)
      min_confidence    float
    """
    pm = get_pm()
    # Handle API limit updates
    if "api_limits" in body:
        from .llm_rate_limiter import rate_limiter
        rate_limiter.update_limits(body["api_limits"])
    pm.update_config(body)
    return {"ok": True, "config": pm.get_config()}


def _get_api_usage() -> dict:
    try:
        from .llm_rate_limiter import rate_limiter
        return rate_limiter.get_usage()
    except Exception:
        return {"total_calls_today": 0, "global_limit": 0, "features": {}}


@router.post("/reset")
async def reset_paper_account():
    """
    Reset the paper trading account: wipe all open trades and today's closed
    trades so the P&L counter restarts from $0.

    Open positions are force-closed at their last known price (or entry price),
    then all trade rows for today are soft-deleted from the DB.
    """
    pm = get_pm()

    # Close all open positions at current price first
    open_trades = get_open_trades()
    closed = []
    for trade in open_trades:
        try:
            positions = await pm.get_positions()
            pos = next((p for p in positions if p["trade_id"] == trade["id"]), None)
            exit_price = pos["current_price"] if pos else float(trade.get("entry_price", 0))
            await pm.exit_trade(trade, exit_price, "reset")
            closed.append(trade["id"])
        except Exception as e:
            logger.warning(f"[reset] Could not close trade {trade['id']}: {e}")

    # Wipe today's trade rows from the database
    from datetime import date
    import sqlite3 as _sqlite3
    from .signal_db import DB_PATH as _DB_PATH
    today = date.today().isoformat()
    try:
        conn = _sqlite3.connect(_DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        cur = conn.cursor()
        cur.execute("DELETE FROM trades WHERE entry_time LIKE ?", (f"{today}%",))
        deleted = cur.rowcount
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[reset] DB wipe error: {e}")
        deleted = 0

    # Reset internal seen-signal cache so the bot doesn't skip signals it already saw
    pm._seen_signal_ids.clear()

    logger.info(f"[reset] Paper account reset — closed {len(closed)} open, deleted {deleted} rows")
    return {
        "ok": True,
        "closed_positions": len(closed),
        "deleted_rows": deleted,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DATA HEALTH
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/data-health")
async def get_data_health():
    """Get health status of all data providers."""
    return data_router.get_health()


# ═══════════════════════════════════════════════════════════════════════════════
# LLM VALIDATOR ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/llm/verdicts")
async def get_llm_verdicts(limit: int = Query(50, ge=1, le=100)):
    """Return recent LLM validator verdicts, newest first."""
    from .config import cfg
    return {
        "verdicts": llm_validator.get_verdicts(limit=limit),
        "stats": llm_validator.get_stats(),
        "enabled": cfg.LLM_VALIDATOR_ENABLED,
        "model": cfg.LLM_VALIDATOR_MODEL,
        "has_api_key": bool(cfg.ANTHROPIC_API_KEY),
    }


@router.post("/llm/validate")
async def validate_signal_now(body: Dict[str, Any]):
    """
    Manually trigger LLM validation on a signal payload.
    Useful for testing the validator or re-validating past signals.
    Returns verdict_id — poll /api/pm/llm/verdicts to see the result.
    """
    import uuid as _uuid
    from .signal_db import get_open_trades
    from . import data_router as _dr

    signal = body.get("signal", body)  # Accept bare signal or {signal: ...}
    if "id" not in signal:
        signal["id"] = str(_uuid.uuid4())

    # Gather context
    open_pos = get_open_trades()
    recent_trades = get_trade_history(limit=5)
    try:
        mkt = await _dr.get_quote("SPY")
    except Exception:
        mkt = {}

    await llm_validator.validate_signal_async(signal, market_context=mkt,
                                              trade_history=recent_trades,
                                              open_positions=open_pos)
    return {"status": "queued", "signal_id": signal["id"]}


# ═══════════════════════════════════════════════════════════════════════════════
# LLM EXIT ADVISOR ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/llm/exit-advisories")
async def get_exit_advisories(
    trade_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Return recent exit advisories, newest first. Optionally filter by trade_id."""
    from .config import cfg
    from .signal_db import get_persisted_exit_advisories

    advisories = llm_exit_advisor.get_recent_advisories(limit=limit)

    # If trade_id specified, also include DB history
    db_advisories = []
    if trade_id:
        db_advisories = get_persisted_exit_advisories(trade_id=trade_id, limit=limit)

    return {
        "advisories": advisories if not trade_id else db_advisories,
        "active": {
            tid: adv for tid, adv in llm_exit_advisor._active_advisories.items()
        },
        "stats": llm_exit_advisor.get_stats(),
        "enabled": cfg.LLM_EXIT_ADVISOR_ENABLED,
        "model": cfg.LLM_EXIT_ADVISOR_MODEL,
        "interval_s": cfg.LLM_EXIT_ADVISOR_INTERVAL_S,
        "hard_gate": cfg.LLM_EXIT_ADVISOR_HARD_GATE,
    }


@router.get("/llm/exit-stats")
async def get_exit_advisor_stats(lookback_days: int = Query(default=30, ge=1, le=90)):
    """Exit advisor quality: how did trades perform after each advisory type?"""
    from .signal_db import get_exit_advisory_stats
    return get_exit_advisory_stats(lookback_days=lookback_days)


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNAL STATS (Option 3)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/signal-stats")
async def get_signal_stats(lookback_days: int = Query(default=30, ge=1, le=90)):
    """
    Signal quality analytics panel — powers the Signals tab stats section.

    Returns:
    - outcome_stats:    Signal accuracy by tier (15-min + 30-min) for non-traded signals
    - llm_stats:        Claude's advisory accuracy — when it said REJECT, was it right?
    - outcome_tracker:  Live status of the background outcome-checking loop
    - weight_learner:   Summary from the WeightLearner showing how weights have drifted
    """
    # Signal direction accuracy from outcome tracker
    try:
        outcome_stats = get_outcome_stats(lookback_days=lookback_days)
    except Exception as e:
        logger.warning(f"[signal-stats] outcome_stats error: {e}")
        outcome_stats = {"by_tier": []}

    # LLM verdict accuracy (once outcomes are known)
    try:
        llm_stats = get_llm_verdict_stats(lookback_days=lookback_days)
    except Exception as e:
        logger.warning(f"[signal-stats] llm_stats error: {e}")
        llm_stats = {"by_verdict": []}

    # Recent persisted LLM verdicts (survives restarts)
    try:
        recent_verdicts = get_persisted_verdicts(limit=20)
    except Exception as e:
        logger.warning(f"[signal-stats] recent_verdicts error: {e}")
        recent_verdicts = []

    # Outcome tracker runtime stats
    tracker_stats = outcome_tracker.stats

    # Weight learner drift summary
    weight_drift = {}
    try:
        get_pm()
        from .signal_api import weight_learner as _wl
        ws = _wl.status()
        drifts = ws.get("weight_changes", {})
        # Surface only the top movers (largest absolute drift)
        sorted_drifts = sorted(drifts.items(), key=lambda x: abs(x[1]), reverse=True)
        weight_drift = {
            "version": ws.get("version"),
            "trade_count": ws.get("trade_count"),
            "top_movers": [
                {"factor": k, "drift": round(v, 4)}
                for k, v in sorted_drifts[:8]
                if abs(v) > 0.001
            ],
        }
    except Exception:
        pass

    # ML Direction Predictor stats (Step 12)
    ml_stats = {}
    try:
        from .ml_predictor import ml_predictor
        ml_stats = ml_predictor.stats
        ml_stats["feature_importance"] = ml_predictor.get_feature_importance(top_n=10)
    except Exception:
        ml_stats = {"available": False, "trained": False}

    return {
        "lookback_days": lookback_days,
        "outcome_stats": outcome_stats,
        "llm_stats": llm_stats,
        "recent_verdicts": recent_verdicts,
        "outcome_tracker": tracker_stats,
        "weight_drift": weight_drift,
        "ml_predictor": ml_stats,
    }


@router.post("/ml-retrain")
async def retrain_ml_predictor():
    """Manually trigger ML direction predictor retraining."""
    try:
        from .ml_predictor import ml_predictor
        result = ml_predictor.train()
        return {"status": "ok", "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD ROUTE
# ═══════════════════════════════════════════════════════════════════════════════

from fastapi.responses import FileResponse
import os

@router.get("/dashboard", include_in_schema=False)
async def serve_dashboard():
    """Serve the new unified trading dashboard."""
    html_path = os.path.join(os.path.dirname(__file__), "static", "trading.html")
    return FileResponse(html_path, media_type="text/html")
