"""
LLM Exit Advisor — Claude-driven trade analysis.

Two modes:
  1. DAILY REVIEW (default): Single Claude call at market close (~$0.03-0.05/day).
     Reviews all trades, exit engine performance, and suggests weight adjustments.

  2. REAL-TIME (opt-in, LLM_EXIT_ADVISOR_REALTIME=true): Evaluates open positions
     every N seconds. Expensive (~$30/day at 30s intervals). Reserved for test days.

The DynamicExitEngine handles all real-time exit decisions locally (free, 5s loop).
Claude's role is strategic: daily learning and occasional high-stakes reasoning.
"""

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_ADVISORIES = 200       # Rolling window
REQUEST_TIMEOUT = 12.0     # Real-time mode timeout
DAILY_REVIEW_TIMEOUT = 60.0  # Daily review can take longer

# ── State ─────────────────────────────────────────────────────────────────────
_advisories: deque = deque(maxlen=MAX_ADVISORIES)
_active_advisories: Dict[str, Dict] = {}
_last_eval_time: Dict[str, float] = {}
_daily_reviews: List[Dict] = []  # History of daily reviews

# ── Stats ─────────────────────────────────────────────────────────────────────
_stats = {
    "total_evaluated": 0,
    "hold_count": 0,
    "tighten_count": 0,
    "scale_out_count": 0,
    "exit_count": 0,
    "error_count": 0,
    "total_latency_ms": 0,
    "daily_reviews": 0,
}


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def get_advisory(trade_id: str) -> Optional[Dict]:
    """Get the latest cached advisory for a trade. Used by exit monitor loop."""
    return _active_advisories.get(trade_id)


def get_recent_advisories(limit: int = 50) -> List[Dict]:
    """Return most-recent advisories, newest first."""
    return list(reversed(list(_advisories)))[:limit]


def get_daily_reviews() -> List[Dict]:
    """Return history of daily reviews."""
    return list(_daily_reviews)


def get_stats() -> Dict:
    """Return aggregate advisory statistics."""
    total = _stats["total_evaluated"]
    avg_lat = (_stats["total_latency_ms"] / total) if total > 0 else 0
    return {
        **_stats,
        "avg_latency_ms": round(avg_lat),
        "hold_rate": round(_stats["hold_count"] / total, 3) if total else 0,
        "exit_rate": round(_stats["exit_count"] / total, 3) if total else 0,
    }


def clear_trade(trade_id: str):
    """Remove cached advisory when trade closes."""
    _active_advisories.pop(trade_id, None)
    _last_eval_time.pop(trade_id, None)


def should_evaluate(trade_id: str, interval_s: int = 30) -> bool:
    """Check if enough time has passed since last evaluation for this trade."""
    last = _last_eval_time.get(trade_id, 0)
    return (time.time() - last) >= interval_s


async def evaluate_position(
    position: Dict,
    exit_context: Dict,
    urgency_result: Optional[Dict] = None,
    trade_history: Optional[List[Dict]] = None,
) -> None:
    """
    Fire-and-forget: schedule Claude evaluation of a position.
    Only used in REAL-TIME mode (LLM_EXIT_ADVISOR_REALTIME=true).
    """
    trade_id = position.get("trade_id", "")
    if not trade_id:
        return

    _last_eval_time[trade_id] = time.time()
    asyncio.ensure_future(
        _run_realtime_evaluation(position, exit_context, urgency_result, trade_history)
    )


# ══════════════════════════════════════════════════════════════════════════════
# DAILY REVIEW — Single Claude call at market close (~$0.03-0.05)
# ══════════════════════════════════════════════════════════════════════════════

async def run_daily_review() -> Optional[Dict]:
    """
    Run once at 4:05 PM ET. Reviews the entire trading day.
    Called from afterhours_learner.py.

    Cost: ~$0.03-0.05 (single Claude call with all day's data).

    Returns:
        Dict with weight_suggestions, patterns, grade, reasoning.
        Or None if insufficient data.
    """
    from .config import cfg
    from .signal_db import get_todays_trades, get_trade_history
    from .dynamic_exit import dynamic_exit_engine

    if not cfg.LLM_DAILY_REVIEW_ENABLED or not cfg.ANTHROPIC_API_KEY:
        return None

    # Gather today's data
    trades = get_todays_trades()
    closed_trades = [t for t in trades if t.get("exit_time")]

    if len(closed_trades) < 1:
        logger.info("[DailyReview] No closed trades today — skipping review")
        return None

    # Get eval log from dynamic exit engine
    eval_log = dynamic_exit_engine.get_eval_log()
    eval_summary = _summarize_eval_log(eval_log) if eval_log else {}

    # Get current weights
    current_weights = dynamic_exit_engine.weights.copy()

    # Build review prompt
    prompt = _build_daily_prompt(closed_trades, eval_summary, current_weights)

    t0 = time.monotonic()
    review_id = str(uuid.uuid4())[:8]

    try:
        client = _get_client()
        model = cfg.LLM_DAILY_REVIEW_MODEL

        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: client.messages.create(
                    model=model,
                    max_tokens=cfg.LLM_DAILY_REVIEW_MAX_TOKENS,
                    messages=[{"role": "user", "content": prompt}],
                ),
            ),
            timeout=DAILY_REVIEW_TIMEOUT,
        )

        raw_text = response.content[0].text.strip()
        latency_ms = int((time.monotonic() - t0) * 1000)

        # Strip markdown fences
        if raw_text.startswith("```"):
            raw_text = "\n".join(raw_text.split("\n")[1:])
        if raw_text.endswith("```"):
            raw_text = raw_text.rsplit("```", 1)[0]
        parsed = json.loads(raw_text.strip())

        review = {
            "id": review_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trades_reviewed": len(closed_trades),
            "weight_suggestions": parsed.get("weight_suggestions", {}),
            "patterns_observed": parsed.get("patterns_observed", []),
            "tomorrow_watch": parsed.get("tomorrow_watch", []),
            "grade": parsed.get("grade", "?"),
            "reasoning": parsed.get("reasoning", "")[:1000],
            "model": model,
            "latency_ms": latency_ms,
        }

        _daily_reviews.append(review)
        _stats["daily_reviews"] += 1

        # Persist to DB
        try:
            from .signal_db import store_exit_advisory
            store_exit_advisory({
                "id": review_id,
                "trade_id": "daily_review",
                "timestamp": review["timestamp"],
                "action": f"GRADE_{review['grade']}",
                "confidence": 1.0,
                "key_signals": review["patterns_observed"][:6],
                "reasoning": review["reasoning"],
                "model": model,
                "latency_ms": latency_ms,
            })
        except Exception:
            pass

        logger.info(
            f"[DailyReview] Grade={review['grade']} | "
            f"{len(closed_trades)} trades | latency={latency_ms}ms | "
            f"{review['reasoning'][:100]}"
        )

        return review

    except Exception as e:
        logger.error(f"[DailyReview] Failed: {e}")
        return None


def _summarize_eval_log(eval_log: List[Dict]) -> Dict:
    """Summarize the day's exit engine evaluations for Claude."""
    if not eval_log:
        return {}

    urgencies = [e.get("urgency", 0) for e in eval_log]
    levels = {}
    for e in eval_log:
        level = e.get("level", "HOLD")
        levels[level] = levels.get(level, 0) + 1

    # Per-scorer average
    scorer_avgs = {}
    for e in eval_log:
        for name, score in e.get("scorers", {}).items():
            if name not in scorer_avgs:
                scorer_avgs[name] = []
            scorer_avgs[name].append(score)

    return {
        "total_evaluations": len(eval_log),
        "avg_urgency": round(sum(urgencies) / len(urgencies), 3),
        "max_urgency": round(max(urgencies), 3),
        "level_distribution": levels,
        "scorer_averages": {
            name: round(sum(scores) / len(scores), 3)
            for name, scores in scorer_avgs.items()
        },
    }


def _build_daily_prompt(trades: List[Dict], eval_summary: Dict, weights: Dict) -> str:
    """Build the daily review prompt."""
    trades_block = []
    for t in trades:
        pnl = t.get("pnl", 0) or 0
        trades_block.append({
            "direction": t.get("direction", t.get("option_type", "?")),
            "tier": t.get("tier", "?"),
            "entry_price": t.get("entry_price"),
            "exit_price": t.get("exit_price"),
            "pnl": round(float(pnl), 2),
            "pnl_pct": t.get("pnl_pct"),
            "exit_reason": t.get("exit_reason"),
            "hold_minutes": t.get("hold_minutes"),
            "mfe_pct": t.get("mfe_pct"),
            "mae_pct": t.get("mae_pct"),
        })

    total_pnl = sum(t.get("pnl", 0) or 0 for t in trades)
    wins = sum(1 for t in trades_block if t["pnl"] > 0)
    losses = sum(1 for t in trades_block if t["pnl"] < 0)

    return f"""You are reviewing today's 0DTE SPY options trading performance. Analyze every trade and the exit engine's behavior. Be specific and actionable.

TODAY'S TRADES ({len(trades_block)} total, {wins}W/{losses}L, ${total_pnl:.2f}):
{json.dumps(trades_block, indent=2)}

EXIT ENGINE PERFORMANCE:
{json.dumps(eval_summary, indent=2) if eval_summary else "No eval data available"}

CURRENT SCORER WEIGHTS:
{json.dumps(weights, indent=2)}

ACCOUNT: $5K cash, 0DTE SPY options, max 2 positions.

Analyze and respond with ONLY a valid JSON object:
{{
  "weight_suggestions": {{"momentum": 0.XX, "greeks": 0.XX, "levels": 0.XX, "session": 0.XX, "flow": 0.XX, "charm_vanna": 0.XX}},
  "patterns_observed": ["pattern1", "pattern2", ...],
  "tomorrow_watch": ["thing to watch tomorrow", ...],
  "grade": "A/B/C/D/F",
  "reasoning": "2-4 paragraphs. What went right, what went wrong, what to change."
}}

Grading:
- A: Positive P&L, good exits, engine performed well
- B: Break-even or small profit, some missed opportunities
- C: Small losses, fixable issues
- D: Significant losses, systemic problems
- F: Major failures, fundamental changes needed

Weight suggestions must sum to 1.0. Only suggest changes if you see clear evidence — don't change weights for noise. If today's sample is too small, suggest keeping current weights."""


# ══════════════════════════════════════════════════════════════════════════════
# REAL-TIME MODE — Opt-in, expensive (~$30/day at 30s intervals)
# ══════════════════════════════════════════════════════════════════════════════

def _get_client():
    """Build Anthropic client — lazy init."""
    try:
        import anthropic
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return anthropic.Anthropic(api_key=api_key)
    except ImportError:
        raise RuntimeError("anthropic package not installed — run: pip install anthropic")


async def _run_realtime_evaluation(
    position: Dict,
    exit_context: Dict,
    urgency_result: Optional[Dict],
    trade_history: Optional[List[Dict]],
) -> None:
    """Execute real-time Claude evaluation (opt-in mode only)."""
    from .config import cfg
    from .llm_rate_limiter import rate_limiter

    if not rate_limiter.can_call("exit_advisor"):
        logger.debug("[ExitAdvisor] Daily API call limit reached, skipping")
        return

    trade_id = position.get("trade_id", "")
    advisory_id = str(uuid.uuid4())[:8]
    t0 = time.monotonic()

    model = cfg.LLM_EXIT_ADVISOR_MODEL
    rate_limiter.record_call("exit_advisor")

    advisory: Dict[str, Any] = {
        "id": advisory_id,
        "trade_id": trade_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "HOLD",
        "urgency_override": None,
        "trailing_adjustment": None,
        "confidence": 0.0,
        "key_signals": [],
        "reasoning": "",
        "model": model,
        "latency_ms": 0,
        "error": None,
        "_eval_time": time.time(),
    }

    try:
        client = _get_client()

        # Compact prompt for real-time (keep tokens low)
        flow = exit_context.get("flow", {})
        session = exit_context.get("session", {})
        urgency_block = urgency_result or {"urgency": 0, "level": "N/A"}
        direction = position.get("direction", position.get("option_type", "?"))

        prompt = f"""0DTE SPY position review. Quick decision needed.

Position: {direction} | P&L: {position.get('unrealized_pnl_pct', 0):.1%} | Hold: {position.get('hold_minutes', 0):.0f}min | Max: {position.get('max_pnl_pct', 0):.1%}
Flow: CVD {flow.get('cvd_trend', '?')}, imbalance {flow.get('imbalance', 0.5):.0%}, absorption={flow.get('absorption_detected', False)}
Session: {session.get('phase', '?')}, {session.get('minutes_to_close', '?')}min left
Engine urgency: {urgency_block.get('urgency', 0):.2f} ({urgency_block.get('level', '?')})

JSON only: {{"action":"HOLD|TIGHTEN|SCALE_OUT|EXIT","trailing_adjustment":null|0.1-1.0,"confidence":0-1,"key_signals":[],"reasoning":"1-2 sentences"}}"""

        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: client.messages.create(
                    model=model, max_tokens=256,
                    messages=[{"role": "user", "content": prompt}],
                ),
            ),
            timeout=REQUEST_TIMEOUT,
        )

        raw_text = response.content[0].text.strip()
        latency_ms = int((time.monotonic() - t0) * 1000)

        if raw_text.startswith("```"):
            raw_text = "\n".join(raw_text.split("\n")[1:])
        if raw_text.endswith("```"):
            raw_text = raw_text.rsplit("```", 1)[0]
        parsed = json.loads(raw_text.strip())

        action = parsed.get("action", "HOLD").upper()
        if action not in ("HOLD", "TIGHTEN", "SCALE_OUT", "EXIT"):
            action = "HOLD"

        trailing_adj = parsed.get("trailing_adjustment")
        if trailing_adj is not None:
            trailing_adj = max(0.1, min(1.0, float(trailing_adj)))

        advisory.update({
            "action": action,
            "urgency_override": parsed.get("urgency_override"),
            "trailing_adjustment": trailing_adj,
            "confidence": max(0.0, min(1.0, float(parsed.get("confidence", 0.5)))),
            "key_signals": [str(s) for s in parsed.get("key_signals", [])[:6]],
            "reasoning": str(parsed.get("reasoning", ""))[:300],
            "latency_ms": latency_ms,
        })

        _stats["total_evaluated"] += 1
        _stats["total_latency_ms"] += latency_ms
        action_key = f"{action.lower()}_count"
        if action_key in _stats:
            _stats[action_key] += 1

        logger.info(
            f"[ExitAdvisor] {action} (conf={advisory['confidence']:.0%}) "
            f"trade={trade_id[:8]} latency={latency_ms}ms"
        )

    except Exception as e:
        advisory.update({"error": str(e), "latency_ms": int((time.monotonic() - t0) * 1000)})
        _stats["error_count"] += 1
        logger.error(f"[ExitAdvisor] Evaluation failed for trade {trade_id[:8]}: {e}")

    finally:
        _active_advisories[trade_id] = advisory
        _advisories.append(advisory)

        try:
            from .signal_db import store_exit_advisory
            store_exit_advisory(advisory)
        except Exception:
            pass
