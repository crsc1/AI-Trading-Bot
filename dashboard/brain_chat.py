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

# ── Claude Code Bridge ────────────────────────────────────────────────────────
# Routes chat messages through `claude -p` subprocess, giving the chat full
# Claude Code capabilities: file access, bash, web search, codebase context.

_CLAUDE_BIN = shutil.which("claude") or ""
_PROJECT_DIR = str(Path(__file__).parent.parent)

# Rolling conversation context for the claude CLI
_chat_turns: List[str] = []
_MAX_CHAT_CONTEXT = 10  # Keep last N exchanges for context


async def _call_claude_code(user_message: str) -> str:
    """
    Call the claude CLI in print mode with the user's message.
    Includes recent conversation history and live market context as a preamble.
    """
    if not _CLAUDE_BIN:
        logger.warning("[BrainChat] claude CLI not found, falling back to API")
        return await brain.chat_immediate(user_message)

    # Build context preamble
    preamble_parts = []

    # Conversation history
    if _chat_turns:
        preamble_parts.append("Recent conversation:")
        for turn in _chat_turns[-_MAX_CHAT_CONTEXT:]:
            preamble_parts.append(turn)
        preamble_parts.append("")

    # Fetch live market data inline
    try:
        context = await brain._fetch_chat_context()
        if context:
            preamble_parts.append(context)
            preamble_parts.append("")
    except Exception:
        pass

    preamble = "\n".join(preamble_parts)
    full_prompt = f"{preamble}\nUser: {user_message}" if preamble else user_message

    try:
        # Strip ANTHROPIC_API_KEY so claude uses Max subscription, not the API key
        clean_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        clean_env["CLAUDE_CODE_ENTRYPOINT"] = "brain-chat"

        proc = await asyncio.create_subprocess_exec(
            _CLAUDE_BIN, "-p", "--output-format", "text",
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
        response = stdout.decode().strip()

        if not response and stderr:
            logger.warning(f"[BrainChat] claude stderr: {stderr.decode()[:200]}")
            return await brain.chat_immediate(user_message)

        # Store turn for context
        _chat_turns.append(f"User: {user_message}")
        _chat_turns.append(f"Assistant: {response[:500]}")
        while len(_chat_turns) > _MAX_CHAT_CONTEXT * 2:
            _chat_turns.pop(0)

        return response

    except asyncio.TimeoutError:
        logger.error("[BrainChat] claude CLI timed out (120s)")
        return "Sorry, that took too long. Try a simpler question."
    except Exception as e:
        logger.error(f"[BrainChat] claude CLI error: {e}")
        return await brain.chat_immediate(user_message)


async def broadcast(data: Dict[str, Any]) -> None:
    """Broadcast a message to all connected chat clients."""
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
    await ws.accept()
    _clients.add(ws)
    logger.info(f"[BrainChat] Client connected ({len(_clients)} total)")

    # Send current state on connect
    try:
        await ws.send_text(json.dumps({
            "type": "brain_state",
            "state": brain.get_state(),
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

                # Decide: immediate response or queue for next cycle
                immediate = data.get("immediate", False)

                # Route through Claude Code CLI for full capabilities
                response = await _call_claude_code(user_message)
                await broadcast({
                    "type": "chat_message",
                    "message": {
                        "id": str(uuid.uuid4())[:8],
                        "role": "brain",
                        "content": response,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
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

    model = "Claude Code" if _CLAUDE_BIN else "claude-opus-4-6 (API)"
    return {"sources": sources, "model": model}


@rest_router.post("/chat")
async def post_chat(body: Dict[str, Any]):
    """Send a chat message (REST alternative to WebSocket)."""
    message = body.get("message", "").strip()
    if not message:
        return {"error": "Empty message"}

    response = await _call_claude_code(message)
    return {"response": response}
