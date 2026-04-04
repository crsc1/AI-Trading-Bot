#!/bin/bash
# Restart the dashboard server with auto-reload enabled
cd "$(dirname "$0")"

echo "Stopping existing dashboard server..."
pkill -f "uvicorn dashboard.app" 2>/dev/null || true
pkill -f "python.*dashboard" 2>/dev/null || true
sleep 1

# Clean Python bytecode cache to ensure fresh code
find dashboard -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find dashboard -name "*.pyc" -delete 2>/dev/null || true

echo "Starting dashboard server with auto-reload..."
python -m uvicorn dashboard.app:app --reload --host 0.0.0.0 --port 8000 &
SERVER_PID=$!

echo "Dashboard server started (PID: $SERVER_PID)"
echo "URL: http://localhost:8000/flow"
echo ""
echo "Auto-reload is ON — code changes will be picked up automatically."
echo "Press Ctrl+C to stop."

wait $SERVER_PID
