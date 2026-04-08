"""
Brain Chat — WebSocket handler for real-time conversation with Market Brain.

Provides:
- /ws/chat WebSocket endpoint for bidirectional chat
- Chat messages queued for next analysis cycle OR handled immediately
- Brain state broadcast to connected clients
"""

import asyncio
import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from .market_brain import brain

logger = logging.getLogger(__name__)

router = APIRouter()

# Connected WebSocket clients
_clients: Set[WebSocket] = set()

# Message history — replayed on reconnect so no messages are lost
_message_history: List[Dict[str, Any]] = []
_MAX_HISTORY = 50

# Thinking state — True while claude CLI is processing
_thinking: bool = False

# ── Claude Code Bridge ────────────────────────────────────────────────────────
# Routes chat messages through `claude -p` subprocess, giving the chat full
# Claude Code capabilities: file access, bash, web search, codebase context.

_CLAUDE_BIN = shutil.which("claude") or ""
_PROJECT_DIR = str(Path(__file__).parent.parent)

# Persistent session ID — reuses the same Claude Code session for cache hits
_session_id: str = str(uuid.uuid4())
_session_first_msg: bool = True  # First message uses --session-id, subsequent use -r

# Cached market context — refreshed at most every 60s, not every message
_market_context_cache: str = ""
_market_context_ts: float = 0
_MARKET_CONTEXT_TTL = 60  # seconds


async def _call_claude_code(user_message: str) -> Dict[str, Any]:
    """
    Call the claude CLI in print mode with the user's message.
    Returns {"content": str, "duration_ms": int, "input_tokens": int, "output_tokens": int, "cost_usd": float}.
    """
    if not _CLAUDE_BIN:
        logger.warning("[BrainChat] claude CLI not found, falling back to API")
        resp = await brain.chat_immediate(user_message)
        return {"content": resp, "duration_ms": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0}

    # Only fetch market data for market-related questions, and cache it
    global _market_context_cache, _market_context_ts
    import time as _time
    market_keywords = {"spy", "price", "chart", "market", "level", "support", "resistance",
                       "trade", "setup", "flow", "volume", "candle", "bar", "vwap", "ema",
                       "hod", "lod", "open", "close", "high", "low", "bearish", "bullish",
                       "put", "call", "options", "strike", "premium", "gex", "gamma"}
    msg_lower = user_message.lower()
    needs_market = any(kw in msg_lower for kw in market_keywords)

    context = ""
    if needs_market:
        now = _time.time()
        if now - _market_context_ts > _MARKET_CONTEXT_TTL or not _market_context_cache:
            try:
                _market_context_cache = await brain._fetch_chat_context()
                _market_context_ts = now
            except Exception:
                pass
        context = _market_context_cache

    full_prompt = f"{context}\n\n{user_message}" if context else user_message

    try:
        # Strip ANTHROPIC_API_KEY so claude uses Max subscription, not the API key
        clean_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        clean_env["CLAUDE_CODE_ENTRYPOINT"] = "brain-chat"

        global _session_first_msg
        # First message creates the session, subsequent messages resume it
        if _session_first_msg:
            session_args = ["--session-id", _session_id]
            _session_first_msg = False
        else:
            session_args = ["-r", _session_id]

        proc = await asyncio.create_subprocess_exec(
            _CLAUDE_BIN, "-p", "--output-format", "json",
            "--model", "opus",
            *session_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=_PROJECT_DIR,
            env=clean_env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=full_prompt.encode()),
            timeout=120,
        )
        raw = stdout.decode().strip()

        if not raw and stderr:
            logger.warning(f"[BrainChat] claude stderr: {stderr.decode()[:200]}")
            resp = await brain.chat_immediate(user_message)
            return {"content": resp, "duration_ms": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0}

        # Parse JSON output from claude CLI
        try:
            data = json.loads(raw)
            response = data.get("result", raw)
            duration_ms = data.get("duration_ms", 0)
            usage = data.get("usage", {})
            input_tokens = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cost_usd = data.get("total_cost_usd", 0)
        except json.JSONDecodeError:
            response = raw
            duration_ms = 0
            input_tokens = 0
            output_tokens = 0
            cost_usd = 0

        return {
            "content": response,
            "duration_ms": duration_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
        }

    except asyncio.TimeoutError:
        logger.error("[BrainChat] claude CLI timed out (120s)")
        return {"content": "Sorry, that took too long. Try a simpler question.", "duration_ms": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0}
    except Exception as e:
        logger.error(f"[BrainChat] claude CLI error: {e}")
        resp = await brain.chat_immediate(user_message)
        return {"content": resp, "duration_ms": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0}


async def broadcast(data: Dict[str, Any]) -> None:
    """Broadcast a message to all connected chat clients and store in history."""
    # Store chat messages in history for replay on reconnect
    if data.get("type") == "chat_message":
        _message_history.append(data)
        while len(_message_history) > _MAX_HISTORY:
            _message_history.pop(0)

    if not _clients:
        return
    msg = json.dumps(data)
    disconnected = set()
    for ws in _clients:
        try:
            await ws.send_text(msg)
        except Exception:
            disconnected.add(ws)
    for ws in disconnected:
        _clients.discard(ws)


async def broadcast_brain_state() -> None:
    """Broadcast current Brain state to all clients."""
    await broadcast({
        "type": "brain_state",
        "state": brain.get_state(),
    })


async def broadcast_decision(decision: Dict) -> None:
    """Broadcast a new Brain decision to all clients."""
    await broadcast({
        "type": "brain_decision",
        "decision": decision,
    })

    # If there's a chat response, broadcast that too
    if decision.get("chat_response"):
        await broadcast({
            "type": "chat_message",
            "message": {
                "id": str(uuid.uuid4())[:8],
                "role": "brain",
                "content": decision["chat_response"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "cycle_number": decision.get("cycle", 0),
                    "confidence": decision.get("confidence", 0),
                    "action": decision.get("action", ""),
                },
            },
        })


@router.websocket("/ws/chat")
async def chat_websocket(ws: WebSocket):
    """
    WebSocket endpoint for chatting with Market Brain.

    Client sends: {"type": "chat", "message": "Why are you bullish?"}
    Server sends:
        - {"type": "chat_message", "message": {...}}
        - {"type": "brain_state", "state": {...}}
        - {"type": "brain_decision", "decision": {...}}
    """
    global _thinking
    await ws.accept()
    _clients.add(ws)
    logger.info(f"[BrainChat] Client connected ({len(_clients)} total)")

    # Send current state on connect (lightweight, no bulk replay)
    try:
        await ws.send_text(json.dumps({
            "type": "brain_state",
            "state": brain.get_state(),
        }))
        if _thinking:
            await ws.send_text(json.dumps({"type": "thinking", "active": True}))
        # Send message count so client knows if it needs to fetch history
        await ws.send_text(json.dumps({
            "type": "history_available",
            "count": len(_message_history),
        }))
    except Exception:
        pass

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")

            if msg_type == "chat":
                user_message = data.get("message", "").strip()
                if not user_message:
                    continue

                # Broadcast user message to all clients
                user_msg = {
                    "id": str(uuid.uuid4())[:8],
                    "role": "user",
                    "content": user_message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await broadcast({
                    "type": "chat_message",
                    "message": user_msg,
                })

                # Broadcast thinking state
                _thinking = True
                await broadcast({"type": "thinking", "active": True})

                # Route through Claude Code CLI for full capabilities
                result = await _call_claude_code(user_message)

                _thinking = False
                await broadcast({"type": "thinking", "active": False})
                await broadcast({
                    "type": "chat_message",
                    "message": {
                        "id": str(uuid.uuid4())[:8],
                        "role": "brain",
                        "content": result["content"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "metadata": {
                            "duration_ms": result["duration_ms"],
                            "input_tokens": result["input_tokens"],
                            "output_tokens": result["output_tokens"],
                            "cost_usd": result["cost_usd"],
                        },
                    },
                })

            elif msg_type == "get_state":
                await ws.send_text(json.dumps({
                    "type": "brain_state",
                    "state": brain.get_state(),
                }))

            elif msg_type == "get_decisions":
                limit = data.get("limit", 20)
                await ws.send_text(json.dumps({
                    "type": "brain_decisions",
                    "decisions": brain.get_recent_decisions(limit),
                }))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[BrainChat] WebSocket error: {e}")
    finally:
        _clients.discard(ws)
        logger.info(f"[BrainChat] Client disconnected ({len(_clients)} total)")


# ── REST endpoints for non-WebSocket access ──────────────────────────────────

rest_router = APIRouter(prefix="/api/brain", tags=["brain"])


@rest_router.get("/state")
async def get_brain_state():
    """Get current Brain state."""
    return brain.get_state()


@rest_router.get("/decisions")
async def get_brain_decisions(limit: int = 20):
    """Get recent Brain decisions."""
    return {"decisions": brain.get_recent_decisions(limit)}


@rest_router.get("/sources")
async def get_brain_sources():
    """Return live data source status for the Agent UI."""
    import aiohttp
    sources = []

    try:
        async with aiohttp.ClientSession() as session:
            # Market price
            try:
                async with session.get("http://localhost:8000/api/market", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        spy = data.get("spy", {})
                        price = spy.get("price", 0)
                        if price > 0:
                            sources.append({
                                "name": "SPY Price",
                                "status": "live",
                                "detail": f"${price:.2f}",
                                "source": spy.get("source", "unknown"),
                            })
                        else:
                            sources.append({"name": "SPY Price", "status": "offline", "detail": "No data"})
            except Exception:
                sources.append({"name": "SPY Price", "status": "error", "detail": "API unreachable"})

            # Bars / chart data
            try:
                async with session.get("http://localhost:8000/api/bars?symbol=SPY&timeframe=5Min&limit=1", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        bars = data.get("bars", [])
                        if bars:
                            sources.append({
                                "name": "Chart Bars",
                                "status": "live",
                                "detail": f"5-min candles from {data.get('source', 'Alpaca')}",
                            })
                        else:
                            sources.append({"name": "Chart Bars", "status": "offline", "detail": "No bars"})
            except Exception:
                sources.append({"name": "Chart Bars", "status": "error"})

            # Alpaca stream
            try:
                async with session.get("http://localhost:8000/api/stream/stats", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("connected"):
                            sources.append({
                                "name": "Live Stream",
                                "status": "live",
                                "detail": f"{data.get('trades_received', 0):,} trades",
                            })
                        else:
                            sources.append({"name": "Live Stream", "status": "offline", "detail": "Market closed"})
            except Exception:
                sources.append({"name": "Live Stream", "status": "offline"})

            # ThetaData options
            try:
                async with session.get("http://localhost:8000/api/theta-stream/stats", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("connected"):
                            sources.append({
                                "name": "Options Flow",
                                "status": "live",
                                "detail": f"{data.get('trades_received', 0):,} trades",
                            })
                        else:
                            sources.append({"name": "Options Flow", "status": "offline", "detail": "ThetaData disconnected"})
            except Exception:
                pass

    except Exception:
        pass

    model = "Claude Code (Opus 4.6)" if _CLAUDE_BIN else "claude-opus-4-6 (API)"
    return {"sources": sources, "model": model}


@rest_router.get("/signals/recent")
async def get_recent_signals(limit: int = 20):
    """Return recent signals from the non-LLM engine for the BrainFeed."""
    from .signal_api import signal_history
    signals = []
    for s in reversed(list(signal_history)):
        if len(signals) >= limit:
            break
        if s.get("signal") != "NO_TRADE":
            signals.append({
                "id": s.get("id"),
                "action": s.get("signal"),
                "confidence": s.get("confidence", 0),
                "tier": s.get("tier", "?"),
                "reasoning": s.get("reasoning", ""),
                "setup_name": s.get("setup_name", ""),
                "timestamp": s.get("timestamp", ""),
            })
    return {"signals": signals}


@rest_router.get("/chat/history")
async def get_chat_history():
    """Return chat message history for clients that need to catch up."""
    return {"messages": list(_message_history)}


@rest_router.get("/moments/recent")
async def get_recent_moments(limit: int = 20):
    """Return recent market moments for the Brain feed."""
    from .market_moments import moments_db
    return {"moments": moments_db.get_recent(limit=limit)}


@rest_router.get("/moments/stats")
async def get_moments_stats():
    """Return summary stats for the moments DB."""
    from .market_moments import moments_db
    return moments_db.get_stats()


@rest_router.get("/moments/similar")
async def get_similar_moments():
    """Return similar past moments for the current market state."""
    from .market_moments import moments_db
    from .data_collector import collect_snapshot
    try:
        # We need the engine for snapshot collection
        from .signal_api import engine
        snapshot = await collect_snapshot(engine)
        similar = moments_db.find_similar(snapshot=snapshot, limit=5)
        return {"moments": similar}
    except Exception as e:
        return {"moments": [], "error": str(e)}


@rest_router.get("/moments/pattern-edge")
async def get_pattern_edge(setup: str = None, regime: str = None, phase: str = None):
    """Return historical edge for a pattern combination."""
    from .market_moments import moments_db
    edge = moments_db.get_pattern_edge(setup_name=setup, regime=regime, session_phase=phase)
    return {"edge": edge}


@rest_router.post("/chat")
async def post_chat(body: Dict[str, Any]):
    """Send a chat message (REST alternative to WebSocket)."""
    message = body.get("message", "").strip()
    if not message:
        return {"error": "Empty message"}

    result = await _call_claude_code(message)
    return {
        "response": result["content"],
        "duration_ms": result["duration_ms"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "cost_usd": result["cost_usd"],
    }
