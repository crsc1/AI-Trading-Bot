#!/bin/bash

# SPX/SPY Options Trading Bot Dashboard - Quick Start Script
# This script installs dependencies and runs the dashboard

set -e

echo "=================================================="
echo "SPX/SPY Options Trading Bot Dashboard"
echo "=================================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

echo "Python version: $(python3 --version)"
echo ""

# Get the dashboard directory
DASHBOARD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/dashboard" && pwd)"
echo "Dashboard directory: $DASHBOARD_DIR"
echo ""

# Install required packages
echo "Installing required packages..."
pip install fastapi uvicorn python-multipart -q
echo "✓ Dependencies installed"
echo ""

# Start the dashboard
echo "Starting dashboard server..."
echo "=================================================="
echo "Dashboard is running at: http://localhost:8000"
echo "Open this URL in your browser to view the dashboard"
echo "=================================================="
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

cd "$DASHBOARD_DIR"
python3 -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
