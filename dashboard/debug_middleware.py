"""
Debug middleware and logging infrastructure for the trading dashboard.
Logs every request/response with timing, captures errors, and provides
a live debug status endpoint.
"""

import time
import logging
import traceback
from datetime import datetime, timezone
from collections import deque
from typing import Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("dashboard.debug")

# ============================================================================
# IN-MEMORY DEBUG LOG RING BUFFER
# ============================================================================
# Stores last N events for the /api/debug/live endpoint to surface
MAX_EVENTS = 200

_request_log = deque(maxlen=MAX_EVENTS)
_error_log = deque(maxlen=50)
_ws_log = deque(maxlen=100)

# Connection state tracked globally
_connection_state = {
    "alpaca_ws": {"status": "unknown", "last_event": None, "errors": 0, "messages": 0},
    "theta_http": {"status": "unknown", "last_event": None, "errors": 0, "messages": 0},
    "bot_ws": {"status": "unknown", "last_event": None, "errors": 0, "messages": 0},
}

_startup_time = datetime.now(timezone.utc).isoformat()


def log_request(method: str, path: str, status: int, duration_ms: float, error: Optional[str] = None):
    """Log an HTTP request to the ring buffer."""
    entry = {
        "time": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "path": path,
        "status": status,
        "duration_ms": round(duration_ms, 1),
    }
    if error:
        entry["error"] = error
    _request_log.append(entry)


def log_error(source: str, message: str, detail: Optional[str] = None):
    """Log an error event."""
    entry = {
        "time": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "message": message,
    }
    if detail:
        entry["detail"] = detail[:500]  # Truncate long tracebacks
    _error_log.append(entry)
    logger.error(f"[{source}] {message}")


def log_ws_event(connection: str, event: str, detail: Optional[str] = None):
    """Log a WebSocket lifecycle event."""
    entry = {
        "time": datetime.now(timezone.utc).isoformat(),
        "connection": connection,
        "event": event,
    }
    if detail:
        entry["detail"] = detail[:300]
    _ws_log.append(entry)

    # Update connection state
    if connection in _connection_state:
        _connection_state[connection]["last_event"] = entry["time"]
        if event in ("connected", "authenticated", "subscribed"):
            _connection_state[connection]["status"] = "connected"
        elif event in ("disconnected", "closed"):
            _connection_state[connection]["status"] = "disconnected"
        elif event == "error":
            _connection_state[connection]["status"] = "error"
            _connection_state[connection]["errors"] += 1
        elif event == "message":
            _connection_state[connection]["messages"] += 1


def get_debug_snapshot():
    """Return the full debug state for the /api/debug/live endpoint."""
    return {
        "server_uptime_since": _startup_time,
        "connections": dict(_connection_state),
        "recent_requests": list(_request_log)[-30:],  # Last 30
        "recent_errors": list(_error_log)[-20:],       # Last 20
        "recent_ws_events": list(_ws_log)[-30:],       # Last 30
        "stats": {
            "total_requests_logged": len(_request_log),
            "total_errors_logged": len(_error_log),
            "total_ws_events_logged": len(_ws_log),
        },
    }


# ============================================================================
# FASTAPI MIDDLEWARE — logs every request/response with timing
# ============================================================================
class DebugLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs every HTTP request with timing and error capture."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        method = request.method
        path = request.url.path

        # Skip logging for static files and health checks to reduce noise
        skip_log = path.startswith("/static") or path == "/health"

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start) * 1000

            if not skip_log:
                log_request(method, path, response.status_code, duration_ms)
                # Log slow requests
                if duration_ms > 2000:
                    logger.warning(f"SLOW REQUEST: {method} {path} took {duration_ms:.0f}ms")

            return response

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            error_msg = str(exc)
            tb = traceback.format_exc()

            log_request(method, path, 500, duration_ms, error=error_msg)
            log_error("http", f"{method} {path} raised {type(exc).__name__}: {error_msg}", detail=tb)

            raise
