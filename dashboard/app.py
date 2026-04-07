"""
FastAPI application for SPX/SPY Options Trading Bot Dashboard
Provides REST API, WebSocket real-time updates, and serves the web UI
"""

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from .config import cfg

# Load .env from project root so API keys are available
load_dotenv(Path(__file__).parent.parent / ".env")

from dashboard.api_routes import router as api_router
from dashboard.trading_api import router as trading_router
from dashboard.signal_api import (
    router as signal_router,
    start_signal_loop, stop_signal_loop,
    start_auto_trader_loop, stop_auto_trader_loop,
)
from dashboard.websocket_handler import ConnectionManager
from dashboard.orderflow_api import include_orderflow_api
from dashboard.alpaca_ws import alpaca_stream
from dashboard.theta_stream import theta_stream
from dashboard.agents.api import router as agents_router, start_agents, stop_agents
from dashboard.pm_api import router as pm_router, init_position_manager
from dashboard.position_manager import PositionManager
from dashboard.flow_subscriber import flow_subscriber
from dashboard.signal_outcome_tracker import outcome_tracker
from dashboard.tick_store import (
    init_tick_db, store_tick, flush_ticks, get_ticks,
    get_tick_stats, prune_old_ticks, get_available_sessions,
)
from dashboard.debug_middleware import (
    DebugLoggingMiddleware,
    get_debug_snapshot,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="SPX/SPY Options Trading Bot Dashboard",
    description="Real-time trading signals and performance monitoring",
    version="1.0.0"
)

# Get the directory paths
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "static"
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

# Custom 404 — redirect browser requests to dashboard, keep JSON for API/WS/static
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    if request.url.path.startswith(("/api/", "/ws", "/static/")):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return RedirectResponse(url="/")

# Debug logging middleware (must be added BEFORE CORS so it wraps all requests)
app.add_middleware(DebugLoggingMiddleware)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (legacy UI)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount new frontend build assets (SolidJS + Vite)
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend_assets")

# Setup templates (if using Jinja2 for dynamic HTML)
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Include API routes
app.include_router(api_router, prefix="/api", tags=["api"])

# Include trading API (positions, orders, account, P&L)
app.include_router(trading_router)

# Include signal API (AI trading signals from order flow)
app.include_router(signal_router)

# Include order flow API (Alpaca trades → volume clouds)
include_orderflow_api(app)

# Include agent orchestration API (5-agent system)
app.include_router(agents_router)

# Include new unified Position Manager API (powers trading.html dashboard)
app.include_router(pm_router)

# Include Market Brain chat WebSocket + REST API
try:
    from .brain_chat import router as brain_ws_router, rest_router as brain_rest_router
    app.include_router(brain_ws_router)
    app.include_router(brain_rest_router)
except ImportError:
    pass  # brain_chat not installed yet

# Include Research Agent API
try:
    from .research_agent import router as research_router, start_research_agent
    app.include_router(research_router)
except ImportError:
    pass  # research_agent not installed yet

# WebSocket connection manager
manager = ConnectionManager()


@app.get("/")
async def get_root():
    """Serve the dashboard — new SolidJS frontend if built, else legacy UI."""
    new_index = FRONTEND_DIST / "index.html"
    if new_index.exists():
        return FileResponse(
            str(new_index),
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return FileResponse(
        str(STATIC_DIR / "flow-dashboard.html"),
        media_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/reference")
async def get_reference():
    """SPA route — serve same index.html for client-side routing."""
    new_index = FRONTEND_DIST / "index.html"
    if new_index.exists():
        return FileResponse(
            str(new_index),
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return RedirectResponse(url="/")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)
    try:
        while True:
            # Receive messages from client (for heartbeat/keep-alive)
            data = await websocket.receive_text()
            logger.debug(f"Received: {data}")
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await manager.disconnect(websocket)


@app.on_event("startup")
async def startup_event():
    """
    Startup event — check if Rust engine holds the Alpaca SIP slot.
    Only start Python WS stream if engine is NOT connected.
    """
    logger.info("Dashboard startup — checking Rust engine status...")

    # Initialize tick persistence (SQLite)
    init_tick_db()
    prune_old_ticks()  # Clean up old data on startup
    logger.info("Tick store initialized and pruned")

    # Register callback to broadcast stream events to dashboard WebSocket clients
    # AND persist trade ticks to SQLite for replay/backtesting
    async def broadcast_stream_event(event: dict):
        """Forward Alpaca stream events to connected dashboard clients + persist trades."""
        await manager.broadcast(event)

        # Persist trade ticks to SQLite (non-blocking — buffered writes)
        if event.get("type") == "trade" and event.get("price"):
            ts_ms = int(event.get("timestamp_ms", 0))
            if not ts_ms:
                # Parse ISO timestamp to ms
                try:
                    from datetime import datetime
                    ts_str = event.get("timestamp", "")
                    if ts_str:
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        ts_ms = int(dt.timestamp() * 1000)
                except Exception:
                    import time
                    ts_ms = int(time.time() * 1000)

            # Alpaca sends conditions as a list — serialize for SQLite
            raw_cond = event.get("conditions")
            cond_str = ",".join(str(c) for c in raw_cond) if isinstance(raw_cond, list) else raw_cond

            store_tick(
                ts_ms=ts_ms,
                symbol=event.get("symbol", "SPY"),
                price=event["price"],
                size=event.get("size", 1),
                side=event.get("side", "neutral"),
                exchange=event.get("exchange"),
                conditions=cond_str,
                nbbo_mid=event.get("nbbo_mid"),
            )

    alpaca_stream.on_event(broadcast_stream_event)

    # Get symbols from env or default to SPY
    symbols_str = os.environ.get("TRADING_SYMBOLS", '["SPY"]')
    try:
        import json as _json
        symbols = _json.loads(symbols_str)
    except Exception:
        symbols = ["SPY"]

    # Check if Rust engine is actively running AND receiving fresh data.
    # If the engine has stale data (e.g. from a previous session), start Python stream.
    engine_active = False
    try:
        import aiohttp
        from datetime import datetime, timezone, timedelta
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{cfg.FLOW_ENGINE_HTTP_URL}/stats", timeout=aiohttp.ClientTimeout(total=cfg.FLOW_ENGINE_STATS_TIMEOUT)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    ticks = data.get("ticks_processed", 0)
                    source = data.get("data_source", "")
                    last_ts = data.get("timestamp", "")
                    logger.info(f"Rust engine detected: source={source}, ticks={ticks}")

                    # Engine is active only if it has a data source AND its last
                    # heartbeat timestamp is recent (within configured stale threshold).  Old stats from a
                    # previous trading session (stale last_price, millions of
                    # ticks_processed) should NOT block the Python stream.
                    if source:
                        try:
                            ts = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                            age = datetime.now(timezone.utc) - ts
                            if age < timedelta(seconds=cfg.FLOW_ENGINE_HEARTBEAT_STALE):
                                engine_active = True
                            else:
                                logger.warning(
                                    f"Engine heartbeat is {age.total_seconds():.0f}s old — "
                                    "treating as stale"
                                )
                        except Exception:
                            # If we can't parse the timestamp, assume stale
                            engine_active = ticks > 0 and source != ""
    except Exception:
        logger.info("Rust engine not detected on port 8081")

    if engine_active:
        logger.info(
            "Rust engine is actively streaming — "
            "Python WS stream will stay idle. REST polling provides fallback data."
        )
    else:
        logger.info("No active Rust engine — starting Python Alpaca SIP stream...")
        await alpaca_stream.start(symbols)
        logger.info(f"Alpaca SIP stream started for: {symbols}")

    # ── ThetaData WebSocket streaming (opt-in via THETA_STREAM_ENABLED) ──
    if cfg.THETA_STREAM_ENABLED:
        logger.info("ThetaData WebSocket streaming enabled — starting...")
        theta_stream.ws_url = cfg.THETA_WS_URL

        # Broadcast theta quote events to dashboard WebSocket clients
        async def broadcast_theta_quote(event: dict):
            await manager.broadcast(event)

        # Broadcast theta trade events (for sweep detection / order flow)
        async def broadcast_theta_trade(event: dict):
            await manager.broadcast(event)

        # Broadcast connection status changes
        async def broadcast_theta_status(event: dict):
            await manager.broadcast(event)

        theta_stream.on_quote(broadcast_theta_quote)
        theta_stream.on_trade(broadcast_theta_trade)
        theta_stream.on_status(broadcast_theta_status)

        await theta_stream.connect()
        logger.info(f"ThetaData WS stream started — {cfg.THETA_WS_URL}")
    else:
        logger.info(
            "ThetaData WS streaming disabled (set THETA_STREAM_ENABLED=true to enable). "
            "REST polling continues as primary data source."
        )

    # Start the 5-agent orchestration system
    start_agents()
    logger.info("Agent orchestration system started (5 agents active)")

    # Start background signal analysis loop — feeds live trades into confluence engine
    start_signal_loop()
    logger.info("Signal analysis loop started (every 15s)")

    # Initialize autonomous trader loop (starts in disabled state — user must enable via UI/API)
    await start_auto_trader_loop()
    logger.info("Autonomous trader loop initialized (enable via /api/signals/auto-trade/start)")

    # ── NEW: Initialize unified PositionManager ──
    # This replaces the scattered position tracking across multiple files.
    # It starts in disabled state — user enables via the new trading dashboard.
    from dashboard.signal_api import signal_history, weight_learner
    from dashboard.confluence import refresh_weights

    async def _pm_trade_closed(trade_id: str):
        """Callback when PositionManager closes a trade — feed to weight learner."""
        try:
            from dashboard.signal_db import get_trade_history
            trades = get_trade_history(limit=5)
            trade = next((t for t in trades if t["id"] == trade_id), None)
            if trade:
                pnl = float(trade.get("pnl", 0) or 0)
                await weight_learner.on_trade_closed(trade, pnl, trade.get("exit_reason", ""))
                refresh_weights()
        except Exception as e:
            logger.warning(f"PM trade closed callback error: {e}")

    pm = PositionManager(
        mode=os.environ.get("TRADING_MODE", "simulation"),
        on_trade_closed=_pm_trade_closed,
    )
    init_position_manager(pm)
    await pm.start(signal_history)
    logger.info("PositionManager initialized (enable via /api/pm/enable or new dashboard)")

    # Start event-driven fast path — subscribes to Rust WS, detects sweep/CVD clusters
    await flow_subscriber.start(pm)
    logger.info("FlowSubscriber started (fast-path entry via Rust WebSocket)")

    # Start signal outcome tracker — records what SPY did after every non-traded signal
    await outcome_tracker.start(weight_learner)
    logger.info("SignalOutcomeTracker started (checks skipped signals at 15min + 30min)")

    # Train ML direction predictor from historical outcomes (Step 12)
    try:
        from dashboard.ml_predictor import ml_predictor
        result = ml_predictor.train()
        logger.info(f"ML Direction Predictor: {result.get('status')} "
                     f"({result.get('samples', 0)} samples)")
    except Exception as e:
        logger.debug(f"ML Predictor startup training skipped: {e}")

    # Start Research Agent (background scraping + analysis every 30 min)
    try:
        from dashboard.research_agent import start_research_agent
        start_research_agent()
        logger.info("Research Agent started (runs every 30 min)")
    except Exception as e:
        logger.debug(f"Research Agent startup skipped: {e}")

    # Log frontend status
    if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
        logger.info(f"New SolidJS frontend served from {FRONTEND_DIST}")
    else:
        logger.info("New frontend not built — serving legacy UI. Run: cd frontend && npm run build")

    # Log Market Brain status
    if cfg.USE_MARKET_BRAIN:
        logger.info("Market Brain ENABLED — LLM-powered analysis active")
    else:
        logger.info("Market Brain disabled — using legacy signal pipeline (set USE_MARKET_BRAIN=true to enable)")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event - stop Alpaca stream, agents, signal loop, and cleanup."""
    logger.info("Dashboard shutdown — stopping PM, agents, signal loop, auto-trader, and Alpaca stream...")
    # Stop new PositionManager
    from dashboard.pm_api import get_pm
    try:
        pm = get_pm()
        await pm.stop()
    except Exception:
        pass
    await stop_auto_trader_loop()
    stop_signal_loop()
    stop_agents()
    await flow_subscriber.stop()
    await outcome_tracker.stop()
    flush_ticks()  # Flush any buffered ticks to SQLite before exit
    await alpaca_stream.stop()
    await theta_stream.disconnect()
    # Stop Research Agent
    try:
        from dashboard.research_agent import stop_research_agent
        stop_research_agent()
    except Exception:
        pass
    logger.info("Dashboard shutdown complete.")


@app.get("/trading")
async def get_trading_redirect():
    """Legacy URL — redirect to unified dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=301)


@app.get("/flow")
async def get_flow_redirect():
    """Legacy URL — redirect to unified dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=301)


@app.get("/api/theta/eod")
async def theta_eod_proxy(
    symbol: str = "SPY",
    start_date: str = "",
    end_date: str = "",
):
    """
    ThetaData EOD proxy — DISABLED.
    We only have OPTION.STANDARD which does NOT include /v3/stock/* endpoints.
    Use Alpaca for stock price data.
    """
    return {
        "error": "ThetaData stock endpoints disabled — OPTION.STANDARD plan only covers options data. Use Alpaca bars instead.",
        "response": [],
    }


# ── Tick Store REST Endpoints ──
# Provides tick persistence, replay, and session history

@app.get("/api/ticks")
async def api_get_ticks(
    symbol: str = "SPY",
    start_ms: int = 0,
    end_ms: int = 0,
    limit: int = 50000,
):
    """
    Retrieve persisted ticks for a symbol within a time range.
    Used for session replay and historical analysis.
    """
    return {
        "ticks": get_ticks(
            symbol=symbol,
            start_ms=start_ms if start_ms > 0 else None,
            end_ms=end_ms if end_ms > 0 else None,
            limit=min(limit, 100000),
        ),
        "symbol": symbol,
    }


@app.get("/api/ticks/stats")
async def api_tick_stats(symbol: str = "SPY"):
    """Get summary statistics for stored ticks."""
    return get_tick_stats(symbol)


@app.get("/api/ticks/sessions")
async def api_tick_sessions(symbol: str = "SPY"):
    """List available trading sessions for replay."""
    return {"sessions": get_available_sessions(symbol), "symbol": symbol}


@app.get("/debug")
async def get_debug_page():
    """Serve the debug dashboard HTML"""
    return FileResponse(
        str(STATIC_DIR / "debug.html"),
        media_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/api/debug/live")
async def debug_live():
    """
    Live debug endpoint — returns all recent requests, errors, WebSocket events,
    and connection states. Poll this from the debug panel.
    """
    return get_debug_snapshot()


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "trading-bot-dashboard"
    }


@app.get("/api/stream/stats")
async def stream_stats():
    """Return Alpaca WebSocket stream stats (connected, counts, NBBO, LULD)."""
    return alpaca_stream.get_stats()


@app.post("/api/stream/subscribe")
async def stream_subscribe(symbols: list[str]):
    """Subscribe to additional symbols on the Alpaca stream."""
    await alpaca_stream.subscribe(symbols)
    return {"subscribed": list(alpaca_stream.subscribed_symbols)}


@app.post("/api/stream/unsubscribe")
async def stream_unsubscribe(symbols: list[str]):
    """Unsubscribe from symbols on the Alpaca stream."""
    await alpaca_stream.unsubscribe(symbols)
    return {"subscribed": list(alpaca_stream.subscribed_symbols)}


@app.post("/api/stream/start")
async def stream_start():
    """Manually start the Alpaca SIP WebSocket stream (use when Rust engine is stopped)."""
    if alpaca_stream.running:
        return {"status": "already_running", "connected": alpaca_stream.connected}
    symbols_str = os.environ.get("TRADING_SYMBOLS", '["SPY"]')
    try:
        import json as _json
        symbols = _json.loads(symbols_str)
    except Exception:
        symbols = ["SPY"]
    await alpaca_stream.start(symbols)
    return {"status": "started", "symbols": symbols}


@app.post("/api/stream/stop")
async def stream_stop():
    """Stop the Alpaca SIP WebSocket stream (use before starting Rust engine)."""
    await alpaca_stream.stop()
    return {"status": "stopped"}


@app.get("/api/theta-stream/stats")
async def theta_stream_stats():
    """Return ThetaData WebSocket stream stats."""
    return theta_stream.get_stats()


@app.post("/api/theta-stream/start")
async def theta_stream_start():
    """Manually start the ThetaData WebSocket stream."""
    if theta_stream.running:
        return {"status": "already_running", "connected": theta_stream.connected}
    theta_stream.ws_url = cfg.THETA_WS_URL
    await theta_stream.connect()
    return {"status": "started", "ws_url": cfg.THETA_WS_URL}


@app.post("/api/theta-stream/stop")
async def theta_stream_stop():
    """Stop the ThetaData WebSocket stream."""
    await theta_stream.disconnect()
    return {"status": "stopped"}


@app.post("/api/admin/reload")
async def admin_reload():
    """
    Hot-reload route modules without full server restart.
    Reimports api_routes and orderflow_api to pick up code changes.
    """
    import importlib
    import dashboard.api_routes as _ar
    import dashboard.orderflow_api as _of

    # Reload the modules
    importlib.reload(_ar)
    importlib.reload(_of)

    # Re-register routes by replacing the router includes
    # Remove old routes and re-add
    new_api_router = _ar.router
    new_of_router = _of.router if hasattr(_of, 'router') else None

    # Clear stale route entries and re-include
    app.router.routes = [
        r for r in app.router.routes
        if not (hasattr(r, 'path') and (
            str(getattr(r, 'path', '')).startswith('/api/market') or
            str(getattr(r, 'path', '')).startswith('/api/bars') or
            str(getattr(r, 'path', '')).startswith('/api/options') or
            str(getattr(r, 'path', '')).startswith('/api/quote') or
            str(getattr(r, 'path', '')).startswith('/api/status') or
            str(getattr(r, 'path', '')).startswith('/api/search') or
            str(getattr(r, 'path', '')).startswith('/api/orderflow')
        ))
    ]
    app.include_router(new_api_router, prefix="/api", tags=["api"])
    if new_of_router:
        app.include_router(new_of_router, prefix="/api/orderflow", tags=["orderflow"])

    return {"status": "reloaded", "message": "Modules reimported. Code changes are now live."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "dashboard.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[str(Path(__file__).parent)],
        reload_includes=["*.py"],   # Only watch Python files — prevents restart when HTML/CSS/JS edited
        reload_excludes=["__pycache__"],
    )
