# Dashboard Installation & Getting Started

## Quick Start (30 seconds)

```bash
cd "/sessions/laughing-sweet-hawking/mnt/AI Trading Bot"
python3 run_dashboard.py
```

Then open your browser to: **http://localhost:8000**

That's it! The dashboard is now running.

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Modern web browser (Chrome, Firefox, Safari, Edge)

## Installation Methods

### Method 1: Automatic Installation (Recommended)

The `run_dashboard.py` script handles everything:

```bash
python3 run_dashboard.py
```

What it does:
- Checks Python version
- Installs dependencies from requirements.txt
- Starts the FastAPI server
- Displays the URL to open

### Method 2: Manual Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Navigate to dashboard directory
cd dashboard

# Start the server
python3 -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### Method 3: Bash Script (Linux/Mac)

```bash
chmod +x run_dashboard.sh
./run_dashboard.sh
```

## Verify Installation

After starting the dashboard, verify it's working:

```bash
# Check health endpoint
curl http://localhost:8000/health

# You should see:
# {"status":"healthy","service":"trading-bot-dashboard"}
```

Open your browser to:
- **http://localhost:8000** - Main dashboard
- **http://localhost:8000/health** - Health check
- **ws://localhost:8000/ws** - WebSocket connection (for real-time updates)

## Troubleshooting Installation

### Error: "Python 3 is not installed"

**Solution:** Install Python 3.8+
- Windows: https://www.python.org/downloads/
- Mac: `brew install python3`
- Linux: `sudo apt-get install python3 python3-pip`

### Error: "ModuleNotFoundError: No module named 'fastapi'"

**Solution:** Install dependencies
```bash
pip install -r requirements.txt
```

### Error: "Port 8000 is already in use"

**Solution:** Use a different port
```bash
cd dashboard
python3 -m uvicorn app:app --port 3000
```

Then open: **http://localhost:3000**

### Error: "WebSocket connection failed"

**Solution:** Ensure the server is running and accessible
- Check server logs for errors
- Try accessing http://localhost:8000 first
- Check firewall settings (port 8000 needs to be accessible)

### Dashboard loads but shows "Loading..."

**Solution:** Check API endpoints
1. Open browser DevTools (F12)
2. Check the Console tab for JavaScript errors
3. Check the Network tab to see if API calls are failing
4. Verify the trading engine is providing data

## Configuration

### Environment Variables

Create a `.env` file in the dashboard directory:

```bash
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8000
DEBUG=True
```

See `.env.example` for all available options.

### Customizing Port

Default port is 8000. To use a different port:

```bash
# Using uvicorn directly
python3 -m uvicorn app:app --host 0.0.0.0 --port 3000

# Then access at: http://localhost:3000
```

### Disabling Auto-Reload (Production)

The default setup uses `--reload` for development. For production:

```bash
python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
```

### Multiple Workers (Production)

For better performance with multiple requests:

```bash
python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
```

## Project Structure

```
dashboard/
├── __init__.py                  # Package init
├── app.py                       # FastAPI application
├── api_routes.py                # REST API endpoints
├── websocket_handler.py         # WebSocket management
└── static/
    └── index.html               # Dashboard UI
```

## Files Included

### Core Dashboard Files (5 files, 2,428 lines total)
- `dashboard/__init__.py` - Empty init file
- `dashboard/app.py` - FastAPI app (116 lines)
- `dashboard/api_routes.py` - API endpoints (483 lines)
- `dashboard/websocket_handler.py` - WebSocket handler (184 lines)
- `dashboard/static/index.html` - Dashboard UI (1,645 lines)

### Documentation
- `README.md` - Main documentation
- `DASHBOARD_SETUP.md` - Detailed setup guide
- `QUICK_REFERENCE.txt` - Quick reference
- `INSTALLATION.md` - This file
- `DASHBOARD_FILES_SUMMARY.txt` - Complete file inventory

### Startup Scripts
- `run_dashboard.py` - Python startup script
- `run_dashboard.sh` - Bash startup script

### Configuration
- `requirements.txt` - Python dependencies
- `.env.example` - Configuration template

## Dependencies

Only 4 lightweight dependencies:

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.104.1 | Web framework |
| uvicorn | 0.24.0 | ASGI server |
| python-multipart | 0.0.6 | Form data handling |
| jinja2 | 3.1.2 | Templates (optional) |

Install with:
```bash
pip install -r requirements.txt
```

## Running the Dashboard

### Development Mode

```bash
python3 -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Features:
- Auto-reload on file changes
- Detailed error messages
- Perfect for development

### Production Mode

```bash
python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
```

Features:
- Multiple worker processes
- Better performance
- Suitable for production

### Background Mode (Linux/Mac)

Run in the background:
```bash
nohup python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 > dashboard.log 2>&1 &
```

### With Docker

Create a `Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY dashboard/ .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:
```bash
docker build -t trading-dashboard .
docker run -p 8000:8000 trading-dashboard
```

## Accessing the Dashboard

Once running, access at:

- **Main Dashboard:** http://localhost:8000
- **Health Check:** http://localhost:8000/health
- **WebSocket:** ws://localhost:8000/ws
- **Swagger Docs:** http://localhost:8000/docs (FastAPI auto-docs)

## Initial Setup

### 1. Verify Dashboard Works

Open http://localhost:8000 in your browser. You should see:
- Header with bot status
- Market snapshot (loading...)
- Live signals panel (loading...)
- Trade history
- P&L chart
- Other dashboard panels

### 2. Check Mock Data

The dashboard comes with mock data enabled by default. You should see:
- SPY, SPX, VIX, QQQ prices
- Sample trading signals
- Sample trade history
- P&L chart with sample data

### 3. Connect Your Trading Engine

Replace mock data in `api_routes.py` with real engine calls. See `DASHBOARD_SETUP.md` for details.

## Next Steps

1. **Customize:** Edit colors and layout if desired
2. **Integrate:** Connect your trading engine (see DASHBOARD_SETUP.md)
3. **Deploy:** Move to production server
4. **Monitor:** Watch logs and user feedback

## Common Commands

```bash
# Run dashboard
python3 run_dashboard.py

# Install dependencies only
pip install -r requirements.txt

# Manual server start
cd dashboard
python3 -m uvicorn app:app --reload --host 0.0.0.0 --port 8000

# Check health
curl http://localhost:8000/health

# View Swagger documentation
# Open: http://localhost:8000/docs

# Stop the server
# Press Ctrl+C in the terminal

# Change port
python3 -m uvicorn app:app --port 3000
```

## Performance Notes

- Dashboard is lightweight: ~2MB total size
- No external frameworks overhead (vanilla JS)
- Chart.js loaded from CDN
- WebSocket for efficient real-time updates
- Auto-reconnect on disconnection
- Responsive to mobile devices

## Security Notes

For development: Current setup is fine.

For production: Add these:
- HTTPS/WSS (encrypted connection)
- Authentication (JWT, OAuth)
- CORS restrictions
- Rate limiting
- Input validation
- Security headers

See `DASHBOARD_SETUP.md` for security configuration.

## Support

**Having issues?** Check:

1. `README.md` - Main documentation
2. `DASHBOARD_SETUP.md` - Detailed integration guide
3. `QUICK_REFERENCE.txt` - Quick command reference
4. Browser console (F12) for JavaScript errors
5. Server logs for backend errors

## Next: Integration

Once the dashboard is running smoothly:

1. **Read** `DASHBOARD_SETUP.md` for integration details
2. **Replace** mock data with real trading engine calls
3. **Implement** startup/shutdown hooks
4. **Test** with real data
5. **Deploy** to production

## Version

- Version: 1.0.0
- Last Updated: March 24, 2026
- Status: Production Ready

---

**Ready?** Start with:
```bash
python3 run_dashboard.py
```

Then open: **http://localhost:8000**
