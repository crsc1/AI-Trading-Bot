"""
LLM Validator — Phase 2.

Advisory layer that runs Claude Sonnet on every tradeable signal.
Non-blocking: fires async, does NOT gate execution.
Stores last N verdicts for display in the AI Agent tab.

Architecture:
  Signal arrives → position_manager enters trade (or skips) normally
                 → fire-and-forget: validate_signal_async(signal, context)
                 → verdict stored in _verdicts deque
                 → GET /api/llm/verdicts returns recent verdicts

Verdict schema:
  {
    "id": str,
    "signal_id": str,
    "timestamp": ISO8601,
    "signal_direction": str,
    "signal_tier": str,
    "signal_confidence": float,
    "verdict": "APPROVE" | "CAUTION" | "REJECT",
    "verdict_confidence": float,      # 0.0 – 1.0
    "reasoning": str,
    "key_factors": [str],             # bullet points
    "would_block": bool,              # what it WOULD do if this were a hard gate
    "model": str,
    "latency_ms": int,
    "error": str | None
  }
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
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 512          # Short, structured response — keep latency low
MAX_VERDICTS = 100        # Rolling window of stored verdicts
REQUEST_TIMEOUT = 15.0    # Seconds — advisory so we can afford some latency

# ── Singleton deque — shared across all callers ───────────────────────────────
_verdicts: deque = deque(maxlen=MAX_VERDICTS)

# ── Stats ─────────────────────────────────────────────────────────────────────
_stats = {
    "total_validated": 0,
    "approve_count": 0,
    "caution_count": 0,
    "reject_count": 0,
    "error_count": 0,
    "total_latency_ms": 0,
}


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def get_verdicts(limit: int = 50) -> List[Dict]:
    """Return most-recent verdicts, newest first."""
    return list(reversed(list(_verdicts)))[:limit]


def get_stats() -> Dict:
    """Return aggregate validation statistics."""
    total = _stats["total_validated"]
    avg_lat = (_stats["total_latency_ms"] / total) if total > 0 else 0
    return {
        **_stats,
        "avg_latency_ms": round(avg_lat),
        "approve_rate": round(_stats["approve_count"] / total, 3) if total else 0,
        "reject_rate": round(_stats["reject_count"] / total, 3) if total else 0,
    }


async def validate_signal_async(
    signal: Dict,
    market_context: Optional[Dict] = None,
    trade_history: Optional[List[Dict]] = None,
    open_positions: Optional[List[Dict]] = None,
) -> None:
    """
    Fire-and-forget validator. Schedules validation as a background task.
    Returns immediately — does NOT await the result.
    """
    asyncio.ensure_future(_run_validation(signal, market_context, trade_history, open_positions))


# ══════════════════════════════════════════════════════════════════════════════
# INTERNAL IMPLEMENTATION
# ══════════════════════════════════════════════════════════════════════════════

def _get_client():
    """Build Anthropic client — lazy init so import never crashes at startup."""
    try:
        import anthropic
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return anthropic.Anthropic(api_key=api_key)
    except ImportError:
        raise RuntimeError("anthropic package not installed — run: pip install anthropic")


def _build_prompt(
    signal: Dict,
    market_context: Optional[Dict],
    trade_history: Optional[List[Dict]],
    open_positions: Optional[List[Dict]],
) -> str:
    """
    Build a compact, structured prompt that gives Claude exactly what it needs.
    Token-efficient: no fluff, no repetition, structured JSON blocks.
    """

    # ── Signal block ──────────────────────────────────────────────────────────
    direction = signal.get("signal", "UNKNOWN")
    tier = signal.get("tier", "UNKNOWN")
    confidence = signal.get("confidence", signal.get("final_confidence", 0))
    strike = signal.get("strike")
    entry = signal.get("entry_price")
    target = signal.get("target_price")
    stop = signal.get("stop_price")
    factors = signal.get("top_factors", signal.get("confluence_factors", []))
    if factors and isinstance(factors[0], dict):
        factor_names = [f.get("name", f.get("factor", "?")) for f in factors]
    else:
        factor_names = factors
    confluence_count = signal.get("confluence_count", len(factor_names))

    sig_block = {
        "direction": direction,
        "tier": tier,
        "confidence": round(float(confidence), 3),
        "strike": strike,
        "entry_price": entry,
        "target_price": target,
        "stop_price": stop,
        "confluence_count": confluence_count,
        "top_factors": factor_names[:8],
    }

    # ── Market context block ──────────────────────────────────────────────────
    mkt_block = {}
    if market_context:
        mkt_block = {
            "price": market_context.get("price"),
            "iv": market_context.get("iv"),
            "iv_rank": market_context.get("iv_rank"),
            "iv_percentile": market_context.get("iv_percentile"),
            "liquidity_score": market_context.get("liquidity_score"),
            "regime": market_context.get("regime"),
            "session_phase": market_context.get("session_phase"),
            "vpin": market_context.get("vpin"),
            "gex": market_context.get("gex"),
            "minutes_to_expiry": market_context.get("minutes_to_expiry"),
        }

    # ── Recent trade history block ────────────────────────────────────────────
    hist_block = []
    if trade_history:
        for t in trade_history[:5]:
            pnl = t.get("pnl", 0) or 0
            hist_block.append({
                "result": "WIN" if pnl > 0 else "LOSS",
                "pnl": round(float(pnl), 2),
                "tier": t.get("tier"),
                "direction": t.get("direction", t.get("option_type", "?")),
                "exit_reason": t.get("exit_reason"),
                "hold_min": t.get("hold_minutes"),
            })

    # ── Open positions block ──────────────────────────────────────────────────
    pos_block = []
    if open_positions:
        for p in open_positions[:5]:
            pos_block.append({
                "direction": "CALL" if p.get("right") == "C" or "call" in str(p.get("option_type", "")).lower() else "PUT",
                "unrealized_pnl": round(float(p.get("unrealized_pnl", 0) or 0), 2),
                "hold_minutes": round(float(p.get("hold_minutes", 0) or 0), 1),
                "delta": p.get("live_greeks", {}).get("delta"),
            })

    # ── Prompt assembly ───────────────────────────────────────────────────────
    prompt = f"""You are an expert 0DTE SPY options trader reviewing a signal from an algorithmic trading system.

SIGNAL:
{json.dumps(sig_block, indent=2)}

MARKET CONDITIONS:
{json.dumps(mkt_block, indent=2) if mkt_block else "Not available"}

RECENT TRADES (last {len(hist_block)}):
{json.dumps(hist_block, indent=2) if hist_block else "No recent trades"}

OPEN POSITIONS ({len(pos_block)} open):
{json.dumps(pos_block, indent=2) if pos_block else "None"}

ACCOUNT CONSTRAINTS:
- $5K cash account, no spreads, single-leg options only
- Max 2 simultaneous positions
- 0DTE SPY calls/puts exclusively
- Order flow + key levels edge

Evaluate this signal and respond with ONLY a valid JSON object in this exact format:
{{
  "verdict": "APPROVE" | "CAUTION" | "REJECT",
  "verdict_confidence": 0.0-1.0,
  "would_block": true/false,
  "key_factors": ["factor1", "factor2", "factor3"],
  "reasoning": "2-3 sentence explanation"
}}

Rules for verdict:
- APPROVE: Signal looks solid, good risk/reward, fits current conditions
- CAUTION: Signal has merit but has one or more yellow flags
- REJECT: Signal has significant red flags (wrong regime, overextended, poor R/R, chasing)

would_block = true only if you would NOT take this trade with real money right now."""

    return prompt


async def _run_validation(
    signal: Dict,
    market_context: Optional[Dict],
    trade_history: Optional[List[Dict]],
    open_positions: Optional[List[Dict]],
) -> None:
    """Execute the Claude validation call and store verdict."""
    sig_id = signal.get("id", str(uuid.uuid4()))
    verdict_id = str(uuid.uuid4())[:8]
    t0 = time.monotonic()

    verdict: Dict[str, Any] = {
        "id": verdict_id,
        "signal_id": sig_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signal_direction": signal.get("signal", "UNKNOWN"),
        "signal_tier": signal.get("tier", "UNKNOWN"),
        "signal_confidence": round(float(signal.get("confidence", signal.get("final_confidence", 0))), 3),
        "verdict": "PENDING",
        "verdict_confidence": 0.0,
        "reasoning": "",
        "key_factors": [],
        "would_block": False,
        "model": MODEL,
        "latency_ms": 0,
        "error": None,
    }

    try:
        from .llm_rate_limiter import rate_limiter
        if not rate_limiter.can_call("validator"):
            verdict["verdict"] = "SKIPPED"
            verdict["reasoning"] = "Daily API call limit reached"
            verdict["latency_ms"] = 0
            _verdicts.append(verdict)
            return

        client = _get_client()
        prompt = _build_prompt(signal, market_context, trade_history, open_positions)
        rate_limiter.record_call("validator")

        # Run blocking SDK call in a thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    messages=[{"role": "user", "content": prompt}],
                ),
            ),
            timeout=REQUEST_TIMEOUT,
        )

        raw_text = response.content[0].text.strip()
        latency_ms = int((time.monotonic() - t0) * 1000)

        # Parse JSON response
        # Strip any markdown fences if the model added them
        if raw_text.startswith("```"):
            raw_text = "\n".join(raw_text.split("\n")[1:])
        if raw_text.endswith("```"):
            raw_text = raw_text.rsplit("```", 1)[0]
        parsed = json.loads(raw_text.strip())

        v = parsed.get("verdict", "CAUTION").upper()
        if v not in ("APPROVE", "CAUTION", "REJECT"):
            v = "CAUTION"

        verdict.update({
            "verdict": v,
            "verdict_confidence": max(0.0, min(1.0, float(parsed.get("verdict_confidence", 0.5)))),
            "reasoning": str(parsed.get("reasoning", ""))[:500],
            "key_factors": [str(f) for f in parsed.get("key_factors", [])[:6]],
            "would_block": bool(parsed.get("would_block", False)),
            "latency_ms": latency_ms,
        })

        # Update stats
        _stats["total_validated"] += 1
        _stats["total_latency_ms"] += latency_ms
        if v == "APPROVE":
            _stats["approve_count"] += 1
        elif v == "CAUTION":
            _stats["caution_count"] += 1
        else:
            _stats["reject_count"] += 1

        logger.info(
            f"[LLMValidator] {v} ({verdict['verdict_confidence']:.0%}) "
            f"sig={sig_id[:8]} latency={latency_ms}ms | {verdict['reasoning'][:80]}"
        )

    except asyncio.TimeoutError:
        verdict.update({"verdict": "CAUTION", "error": "Timeout", "latency_ms": int((time.monotonic() - t0) * 1000)})
        _stats["error_count"] += 1
        logger.warning(f"[LLMValidator] Timeout for signal {sig_id[:8]}")

    except json.JSONDecodeError as e:
        verdict.update({"verdict": "CAUTION", "error": f"JSON parse error: {e}", "latency_ms": int((time.monotonic() - t0) * 1000)})
        _stats["error_count"] += 1
        logger.warning(f"[LLMValidator] JSON parse error for signal {sig_id[:8]}: {e}")

    except Exception as e:
        verdict.update({"verdict": "CAUTION", "error": str(e), "latency_ms": int((time.monotonic() - t0) * 1000)})
        _stats["error_count"] += 1
        logger.error(f"[LLMValidator] Validation failed for signal {sig_id[:8]}: {e}")

    finally:
        _verdicts.append(verdict)
        # Persist to SQLite so verdicts survive restarts and can be back-filled
        # with was_correct once the signal outcome is known (Option 2).
        try:
            from .signal_db import store_llm_verdict
            store_llm_verdict(verdict)
        except Exception as _e:
            logger.debug(f"[LLMValidator] Verdict persist error: {_e}")
