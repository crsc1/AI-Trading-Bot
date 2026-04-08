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
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from .market_brain import brain

logger = logging.getLogger(__name__)

router = APIRouter()

# Connected WebSocket clients
_clients: Set[WebSocket] = set()


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

                if immediate:
                    # Respond immediately using last snapshot context
                    response = await brain.chat_immediate(user_message)
                    await broadcast({
                        "type": "chat_message",
                        "message": {
                            "id": str(uuid.uuid4())[:8],
                            "role": "brain",
                            "content": response,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    })
                else:
                    # Queue for next analysis cycle (Brain responds with full market context)
                    brain.queue_chat_message(user_message)
                    await broadcast({
                        "type": "chat_queued",
                        "message": "Message queued for next analysis cycle",
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


@rest_router.post("/chat")
async def post_chat(body: Dict[str, Any]):
    """Send a chat message (REST alternative to WebSocket)."""
    message = body.get("message", "").strip()
    if not message:
        return {"error": "Empty message"}

    immediate = body.get("immediate", True)

    if immediate:
        response = await brain.chat_immediate(message)
        return {"response": response}
    else:
        brain.queue_chat_message(message)
        return {"status": "queued"}
