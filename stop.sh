#!/bin/bash
# Stop all platform processes
echo "Stopping ThetaData server..."
pkill -f "thetadatadx-server" 2>/dev/null && echo "  Stopped" || echo "  Not running"
echo "Stopping flow engine..."
pkill -f "flow-engine" 2>/dev/null && echo "  Stopped" || echo "  Not running"
echo "Stopping dashboard..."
pkill -f "uvicorn dashboard.app" 2>/dev/null && echo "  Stopped" || echo "  Not running"
echo "Done."
