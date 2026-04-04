"""
Example: How to integrate the Order Flow Visualization system into your FastAPI app.

This is a minimal working example that sets up the order flow dashboard
with both real data (optional) and demo mode simulation.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import order flow components
from dashboard.orderflow_api import include_orderflow_api

# NOTE: This example is outdated. The following imports no longer exist:
# - from data.providers.orderflow_stream import orderflow_stream
# - from data.providers.orderflow_stream import start_orderflow_simulation
# Consider updating this example to use the current orderflow_api interface.

# ============================================================================
# SETUP: Create FastAPI App
# ============================================================================

app = FastAPI(
    title="SPX/SPY Order Flow Visualizer",
    description="Professional order flow visualization with real-time data",
    version="1.0.0"
)

# ============================================================================
# CORS Configuration (if frontend is on different domain)
# ============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# STATIC FILES: Serve the HTML dashboard
# ============================================================================

# Mount static files - assumes dashboard/static/ exists with orderflow.html
try:
    app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")
    logger.info("✓ Static files mounted at /static")
except Exception as e:
    logger.warning(f"⚠ Could not mount static files: {e}")

# ============================================================================
# ORDER FLOW ROUTES: Include all WebSocket and REST endpoints
# ============================================================================

include_orderflow_api(app)
logger.info("✓ Order flow API routes included")

# ============================================================================
# OPTIONAL: Example routes for your app
# ============================================================================

@app.get("/")
async def root():
    """Redirect to order flow dashboard."""
    return {
        "message": "SPX/SPY Order Flow Visualizer",
        "dashboard": "/static/orderflow.html",
        "api": "/api/orderflow"
    }


@app.get("/api/symbols")
async def get_symbols():
    """Return list of available symbols."""
    return {
        "symbols": ["SPY", "SPX", "QQQ"],
        "default": "SPY"
    }


# ============================================================================
# STARTUP/SHUTDOWN HOOKS
# ============================================================================

@app.on_event("startup")
async def startup():
    """Initialize order flow on app startup."""
    logger.info("Starting Order Flow Visualizer...")

    # Optional: Connect to real data source (Polygon.io example)
    # await setup_polygon_connection()

    # Optional: Start demo mode for default symbols
    # await start_orderflow_simulation("SPY")
    # await start_orderflow_simulation("SPX")

    logger.info("✓ Order Flow Visualizer ready")
    logger.info("  Dashboard: http://localhost:8000/static/orderflow.html")
    logger.info("  WebSocket: ws://localhost:8000/ws/orderflow?symbol=SPY")
    logger.info("  API Docs: http://localhost:8000/docs")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    logger.info("Shutting down Order Flow Visualizer...")

    # Note: orderflow_stream module no longer exists
    # Streaming connections are now managed by the orderflow_api module

    logger.info("✓ Shutdown complete")


# ============================================================================
# OPTIONAL: Real Data Connection (Polygon.io Example)
# ============================================================================

"""
To connect real market data, implement this pattern:

from data.providers.orderflow_stream import process_polygon_trade
import websockets
import json

async def setup_polygon_connection():
    '''Connect to Polygon.io WebSocket for real trades.'''
    api_key = "YOUR_POLYGON_API_KEY"

    if not api_key or api_key == "YOUR_POLYGON_API_KEY":
        logger.warning("⚠ Polygon API key not configured. Using demo mode.")
        # Start demo simulation
        await start_orderflow_simulation("SPY")
        await start_orderflow_simulation("SPX")
        return

    # Start background task to connect to Polygon
    asyncio.create_task(polygon_client(api_key))


async def polygon_client(api_key: str):
    '''Connect to Polygon WebSocket and forward trades to order flow stream.'''
    url = f"wss://socket.polygon.io/stocks?apiKey={api_key}"

    while True:
        try:
            async with websockets.connect(url) as ws:
                logger.info(f"Connected to Polygon WebSocket")

                # Subscribe to SPY and SPX
                await ws.send(json.dumps({
                    "action": "subscribe",
                    "params": "T.SPY,T.SPX"
                }))

                async for message in ws:
                    data = json.loads(message)

                    # Process individual trades
                    for trade in data.get("data", []):
                        await process_polygon_trade(trade)

        except Exception as e:
            logger.error(f"Polygon WebSocket error: {e}")
            await asyncio.sleep(5)  # Reconnect after 5 seconds
"""

# ============================================================================
# RUN THE APP
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║     SPX/SPY ORDER FLOW VISUALIZATION - Starting Server         ║
    ╚════════════════════════════════════════════════════════════════╝
    """)

    # Run with: python -m uvicorn examples.orderflow_example:app --reload
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
