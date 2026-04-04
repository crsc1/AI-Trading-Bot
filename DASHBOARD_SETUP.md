# SPX/SPY Options Trading Bot Dashboard - Setup & Usage Guide

## Project Overview

A professional, real-time web dashboard for monitoring and controlling an SPX/SPY options trading bot. Built with **FastAPI** (backend) and **vanilla HTML/CSS/JavaScript** (frontend) - no frameworks needed.

## Architecture

```
dashboard/
├── __init__.py              (empty init file)
├── app.py                   (FastAPI application entry point)
├── api_routes.py            (REST API endpoints)
├── websocket_handler.py      (WebSocket real-time updates)
└── static/
    └── index.html           (Single-file dashboard UI)
```

## File Descriptions

### 1. **app.py** (116 lines)
Main FastAPI application that:
- Serves the static HTML dashboard
- Mounts the `/static` directory for assets
- Includes all API routes from `api_routes.py`
- Manages WebSocket connections
- Provides CORS middleware for cross-origin requests
- Includes startup/shutdown event hooks to connect to trading engine

**Key endpoints:**
- `GET /` - Serves main dashboard
- `WS /ws` - WebSocket for real-time updates
- `GET /health` - Health check

### 2. **api_routes.py** (483 lines)
REST API endpoints organized by feature:

#### Signals Management
- `GET /api/signals` - Get trading signals (filterable by symbol/direction/confidence)
- `GET /api/signals/latest` - Get most recent signal

#### Trade History
- `GET /api/trades` - Get past trades with date range filter

#### P&L & Performance
- `GET /api/pnl` - Daily P&L summary
- `GET /api/pnl/history` - P&L over time (for charting)

#### Market Data
- `GET /api/market` - Current market snapshot (SPY, SPX, VIX, QQQ)

#### Options Flow (Unusual Activity)
- `GET /api/flow` - Latest options sweeps, blocks, unusual volume

#### Bot Control
- `GET /api/status` - Bot status (running/mode/positions/P&L)
- `POST /api/trade/approve/{signal_id}` - Execute a signal (semi-auto)
- `POST /api/trade/reject/{signal_id}` - Reject a signal

#### Analysis & Patterns
- `GET /api/analysis/yesterday` - Why did SPY/SPX move yesterday?
- `GET /api/patterns` - Current technical patterns
- `GET /api/calendar` - Economic events calendar

#### Settings
- `POST /api/settings` - Update bot configuration

### 3. **websocket_handler.py** (184 lines)
Manages WebSocket connections and real-time broadcasts:

**ConnectionManager class methods:**
- `connect()` - Accept new client connections
- `disconnect()` - Remove disconnected clients
- `broadcast()` - Send message to all connected clients
- `broadcast_signal()` - New trading signal alert
- `broadcast_trade_execution()` - Trade executed notification
- `broadcast_price_update()` - Market price changes
- `broadcast_pnl_update()` - P&L change notification
- `broadcast_options_flow()` - New options flow data
- `broadcast_status_update()` - Bot status change
- `start_heartbeat()` - Keep-alive signal every 30 seconds

### 4. **index.html** (1,645 lines)
Single-file dashboard UI with embedded CSS and JavaScript.

**Design:**
- Dark theme (professional trading UI standard)
- Responsive grid layout
- Real-time WebSocket updates (no page refresh)
- Mobile-friendly

**Sections:**
1. **Header** - Bot status, daily P&L, connection status
2. **Market Snapshot** - Real-time prices (SPY, SPX, VIX, QQQ)
3. **Live Signals** - New trading signals with confidence bars, entry/exit targets
4. **Options Flow** - Unusual activity (sweeps, blocks, large orders)
5. **Risk Dashboard** - Open positions, day trades used, drawdown
6. **Trade History** - Sortable table of past trades
7. **P&L Chart** - Interactive line chart of cumulative P&L
8. **Pattern Analysis** - Technical patterns and market analysis
9. **Economic Calendar** - Upcoming economic events
10. **Toast Notifications** - Real-time alerts

**Color Coding:**
- Green: Calls, bullish, positive P&L, approval buttons
- Red: Puts, bearish, negative P&L, rejection buttons
- Yellow: Caution, unusual activity, forecast indicators
- Blue: Information, details, analysis
- Confidence bars: Red (low) → Yellow (medium) → Green (high)

## Installation & Running

### Prerequisites
```bash
pip install fastapi uvicorn python-multipart
```

### Run the Dashboard
```bash
cd "/sessions/laughing-sweet-hawking/mnt/AI Trading Bot/dashboard"
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Then open your browser to: **http://localhost:8000**

### Production Deployment
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
```

## Integration with Trading Engine

The dashboard is designed to work with a trading engine backend. Key integration points:

### 1. API Routes - Replace Mock Data
Each endpoint in `api_routes.py` has `# TODO:` comments where you should:
- Connect to your trading engine database
- Fetch real signals, trades, prices
- Return live market data instead of mock responses

Example:
```python
async def get_signals(...):
    # TODO: Fetch from trading engine
    # Replace mock data with: trading_engine.get_signals()
    return signals
```

### 2. WebSocket Broadcasts
From your trading engine, call the broadcast methods:

```python
from websocket_handler import manager

# When a new signal is generated
await manager.broadcast_signal({
    'id': 'sig_001',
    'symbol': 'SPY',
    'direction': 'BUY_CALL',
    'confidence': 78.5,
    # ... other fields
})

# When a trade executes
await manager.broadcast_trade_execution({
    'id': 'trade_001',
    'symbol': 'SPY',
    'status': 'OPEN',
    # ... other fields
})
```

### 3. Startup/Shutdown Hooks
In `app.py`, the `@app.on_event("startup")` and `@app.on_event("shutdown")` functions are called when the server starts/stops:

```python
@app.on_event("startup")
async def startup_event():
    # Connect to trading engine
    # Initialize data feeds
    # Start background monitoring tasks
    pass
```

## Frontend Architecture (JavaScript)

The dashboard JavaScript is organized in sections:

### Constants & Config
```javascript
const API_BASE = '/api';
const WS_URL = `ws://${window.location.host}/ws`;
```

### State Management
```javascript
const state = {
    connected: false,
    signals: [],
    trades: [],
    websocket: null,
    // ... more state
};
```

### Utility Functions
- `formatCurrency()` - Format numbers as USD
- `formatNumber()` - Add comma separators
- `formatPercent()` - Format as percentage
- `getTimeAgo()` - Relative time (2m ago, etc.)
- `showToast()` - Show notifications
- `apiCall()` - Fetch API with error handling

### API Call Functions
- `fetchMarketData()` - Get market prices
- `fetchSignals()` - Get trading signals
- `fetchTrades()` - Get trade history
- `fetchPnLHistory()` - Get P&L for charting
- `fetchBotStatus()` - Get bot status
- `fetchCalendar()` - Get economic events
- `fetchOptionsFlow()` - Get unusual activity
- `fetchAnalysis()` - Get analysis & patterns

### UI Rendering Functions
- `renderSignals()` - Display trading signals
- `renderTrades()` - Display trade history table
- `renderPnLChart()` - Create interactive P&L chart
- `renderOptionsFlow()` - Display options activity
- `updateMarketSnapshot()` - Update market prices
- `updateBotStatus()` - Update bot statistics

### WebSocket Handling
```javascript
connectWebSocket() {
    state.websocket = new WebSocket(WS_URL);
    // Handles: onopen, onmessage, onerror, onclose
}

handleWebSocketMessage(message) {
    // Routes messages by type:
    // - new_signal
    // - trade_executed
    // - price_update
    // - pnl_update
    // - options_flow
    // - status_update
    // - heartbeat
}
```

### Auto-Reconnection
- Automatically reconnects on disconnect
- Exponential backoff (up to 30 seconds)
- Max 5 reconnection attempts

### Auto-Refresh Intervals
- Market data: Every 5 seconds
- All data: Every 30 seconds

## Customization Guide

### Change Colors
Edit CSS variables in `index.html` `<style>` section:
```css
:root {
    --bg-primary: #0f0f23;      /* Main background */
    --accent-green: #27ae60;     /* Bullish/calls color */
    --accent-red: #e74c3c;       /* Bearish/puts color */
    /* ... more colors */
}
```

### Add New Panels
1. Add HTML in the appropriate grid area
2. Create a `fetch*()` function to get data
3. Create a `render*()` function to display it
4. Call both in `loadAllData()` and `initializeDashboard()`
5. Add WebSocket handler in `handleWebSocketMessage()` if real-time updates needed

### Modify Chart
The P&L chart uses Chart.js (v3.9.1):
```javascript
function renderPnLChart(pnlData) {
    state.chartInstance = new Chart(ctx, {
        type: 'line',  // Change to 'bar', 'area', etc.
        data: { ... },
        options: { ... }
    });
}
```

### Change Refresh Intervals
```javascript
// In initializeDashboard()
setInterval(fetchMarketData, 5000);    // Change 5000ms as needed
setInterval(loadAllData, 30000);       // Change 30000ms as needed
```

## API Response Format Examples

All API endpoints return JSON with consistent structure:

### Signal Response
```json
{
    "id": "sig_001",
    "symbol": "SPY",
    "direction": "BUY_CALL",
    "strike": 450.0,
    "expiry": "2026-03-31",
    "confidence": 78.5,
    "entry_price": 2.45,
    "stop_loss": 1.50,
    "target_price": 4.00,
    "reasoning": "Bullish divergence on 4H chart...",
    "risk_reward_ratio": 2.5,
    "timestamp": "2026-03-24T10:30:00"
}
```

### Trade Response
```json
{
    "id": "trade_001",
    "symbol": "SPY",
    "direction": "BUY_CALL",
    "entry_price": 2.45,
    "exit_price": 3.80,
    "entry_time": "2026-03-23T10:30:00",
    "exit_time": "2026-03-23T14:15:00",
    "pnl": 135.0,
    "status": "CLOSED",
    "quantity": 1
}
```

### Market Snapshot Response
```json
{
    "spy": {
        "symbol": "SPY",
        "price": 450.25,
        "change": 1.50,
        "change_percent": 0.33,
        "timestamp": "2026-03-24T10:30:00"
    },
    "spx": { ... },
    "vix": { ... },
    "qqq": { ... }
}
```

## WebSocket Message Types

The WebSocket broadcasts these message types:

```javascript
{
    "type": "connected",        // Initial connection
    "message": "Dashboard connected",
    "timestamp": "..."
}

{
    "type": "new_signal",       // New trading signal
    "data": { signal object },
    "timestamp": "..."
}

{
    "type": "trade_executed",   // Trade executed
    "data": { trade object },
    "timestamp": "..."
}

{
    "type": "price_update",     // Price changed
    "data": { price object },
    "timestamp": "..."
}

{
    "type": "pnl_update",       // P&L changed
    "data": { pnl data },
    "timestamp": "..."
}

{
    "type": "options_flow",     // New options activity
    "data": { flow data },
    "timestamp": "..."
}

{
    "type": "status_update",    // Bot status changed
    "data": { status object },
    "timestamp": "..."
}

{
    "type": "heartbeat",        // Keep-alive (every 30s)
    "timestamp": "..."
}
```

## Features Checklist

- ✅ Real-time WebSocket updates
- ✅ Auto-reconnect on disconnect
- ✅ Market snapshot (SPY, SPX, VIX, QQQ)
- ✅ Live trading signals with confidence bars
- ✅ Signal approval/rejection (semi-auto mode)
- ✅ Trade history with filtering
- ✅ P&L tracking and charting
- ✅ Options flow detection (sweeps, blocks)
- ✅ Economic calendar
- ✅ Pattern analysis
- ✅ Risk dashboard (open positions, day trades)
- ✅ Toast notifications
- ✅ Sound alerts for high-confidence signals
- ✅ Dark theme
- ✅ Mobile responsive
- ✅ No external UI framework (vanilla JS)

## Common Tasks

### Add a New Metric to Header
In `index.html`, add to `.header-info`:
```html
<div class="header-item">
    <span class="header-label">Win Rate</span>
    <span class="header-value" id="win-rate">72%</span>
</div>
```

Then in JavaScript:
```javascript
document.getElementById('win-rate').textContent = '72%';
```

### Sound Notifications
Already implemented! Called automatically for signals with confidence > 75%.
Located in `playNotificationSound()` function.

### Add More Signals to Display
Edit `renderSignals()` - currently shows first 5:
```javascript
container.innerHTML = signals.slice(0, 5).map(signal => ...)
```
Change `5` to desired number.

### Change Auto-Refresh Timing
Edit intervals in `initializeDashboard()`:
```javascript
setInterval(fetchMarketData, 5000);    // 5 seconds
setInterval(loadAllData, 30000);       // 30 seconds
```

### Add More Market Symbols
Edit market snapshot HTML and add fetch logic:
```javascript
const data = {
    spy: { ... },
    spx: { ... },
    vix: { ... },
    qqq: { ... },
    btc: { ... }  // Add new symbol
};
```

## Troubleshooting

### Dashboard loads but shows "Loading..."
1. Check browser console for errors (F12)
2. Verify API endpoints are returning data
3. Check `/api/health` endpoint responds

### WebSocket not connecting
1. Verify server is running: `http://localhost:8000`
2. Check WebSocket URL: `ws://localhost:8000/ws`
3. Look for CORS errors in console
4. Check firewall isn't blocking WebSocket

### Real-time updates not appearing
1. WebSocket may be disconnected (check status badge)
2. Check browser console for JavaScript errors
3. Verify trading engine is broadcasting to WebSocket

### Charts not displaying
1. Check Chart.js CDN is loading (look in Network tab)
2. Verify `pnl_chart` canvas element exists in HTML
3. Check P&L data is being returned from API

## Performance Tips

- Dashboard is lightweight - <2MB total size
- Uses vanilla JavaScript - no framework overhead
- WebSocket for real-time reduces polling overhead
- Auto-refresh intervals are configurable
- Chart.js is loaded from CDN for minimal local storage

## Security Notes

- CORS is open (`allow_origins=["*"]`) - restrict in production
- WebSocket has no authentication - add token-based auth in production
- Consider HTTPS/WSS for production deployments
- Add rate limiting to API endpoints
- Validate all user inputs before sending to trading engine

## Next Steps

1. Replace mock data in `api_routes.py` with real trading engine integration
2. Implement startup/shutdown hooks in `app.py`
3. Add authentication/authorization
4. Customize colors and branding
5. Add more analysis panels as needed
6. Deploy to production server

---

**Version:** 1.0.0
**Last Updated:** March 24, 2026
**Author:** AI Trading Bot Team
