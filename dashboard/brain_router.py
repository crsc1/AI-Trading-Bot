"""
Brain Router — Model routing for Market Brain.

Routes analysis to Sonnet 4.6 for routine cycles, escalates to Opus 4.6
for actual trade decisions. Manages the Anthropic client and prompt caching.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Models ────────────────────────────────────────────────────────────────────
MODEL_SONNET = "claude-sonnet-4-6"
MODEL_OPUS = "claude-opus-4-6"
MAX_TOKENS_ANALYSIS = 800
MAX_TOKENS_TRADE = 1200


def _get_client():
    """Lazy-init Anthropic client."""
    try:
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return anthropic.Anthropic(api_key=api_key)
    except ImportError:
        raise RuntimeError("anthropic package not installed — run: pip install anthropic")


# ── Stats ─────────────────────────────────────────────────────────────────────
_stats = {
    "sonnet_calls": 0,
    "opus_calls": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_latency_ms": 0,
    "errors": 0,
}


def get_router_stats() -> Dict:
    total = _stats["sonnet_calls"] + _stats["opus_calls"]
    return {
        **_stats,
        "total_calls": total,
        "avg_latency_ms": round(_stats["total_latency_ms"] / total) if total > 0 else 0,
    }


async def call_brain(
    system_prompt: str,
    messages: List[Dict[str, str]],
    escalate: bool = False,
) -> Dict[str, Any]:
    """
    Call Claude with the Brain conversation.

    Args:
        system_prompt: The persistent system prompt (will be cached).
        messages: Conversation messages [{role, content}, ...].
        escalate: If True, use Opus 4.6 (for trade decisions).

    Returns:
        {
            "content": str,        # Raw text response
            "model": str,          # Model used
            "input_tokens": int,
            "output_tokens": int,
            "latency_ms": int,
            "error": str | None,
        }
    """
    model = MODEL_OPUS if escalate else MODEL_SONNET
    max_tokens = MAX_TOKENS_TRADE if escalate else MAX_TOKENS_ANALYSIS

    try:
        client = _get_client()
        t0 = time.monotonic()

        # Use prompt caching for system prompt (saves ~90% on repeated input)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=messages,
        )

        latency_ms = int((time.monotonic() - t0) * 1000)
        content = response.content[0].text if response.content else ""
        input_tokens = response.usage.input_tokens if response.usage else 0
        output_tokens = response.usage.output_tokens if response.usage else 0

        # Update stats
        if escalate:
            _stats["opus_calls"] += 1
        else:
            _stats["sonnet_calls"] += 1
        _stats["total_input_tokens"] += input_tokens
        _stats["total_output_tokens"] += output_tokens
        _stats["total_latency_ms"] += latency_ms

        logger.info(
            f"[BrainRouter] {model} — {input_tokens}in/{output_tokens}out "
            f"— {latency_ms}ms"
        )

        return {
            "content": content,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "error": None,
        }

    except Exception as e:
        _stats["errors"] += 1
        logger.error(f"[BrainRouter] Error calling {model}: {e}")
        return {
            "content": "",
            "model": model,
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_ms": 0,
            "error": str(e),
        }
