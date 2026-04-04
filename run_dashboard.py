#!/usr/bin/env python3
"""
SPX/SPY Options Trading Bot Dashboard - Quick Start Script
Installs dependencies and runs the dashboard server
Works on Windows, Mac, and Linux
"""

import subprocess
import sys
import os
from pathlib import Path

def print_header(text):
    """Print a formatted header"""
    print("\n" + "=" * 50)
    print(text)
    print("=" * 50 + "\n")

def install_dependencies():
    """Install required Python packages"""
    print_header("Installing Dependencies")

    packages = [
        "fastapi",
        "uvicorn",
        "python-multipart"
    ]

    for package in packages:
        print(f"Installing {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package])

    print("✓ All dependencies installed\n")

def run_dashboard():
    """Run the FastAPI dashboard server"""
    print_header("Starting Dashboard Server")

    # Get the dashboard directory
    script_dir = Path(__file__).parent
    dashboard_dir = script_dir / "dashboard"

    print(f"Dashboard directory: {dashboard_dir}")
    print(f"Python version: {sys.version}")
    print()

    # Change to dashboard directory
    os.chdir(dashboard_dir)

    # Run uvicorn
    print("Starting server...")
    print("\n" + "=" * 50)
    print("✓ Dashboard is running!")
    print("=" * 50)
    print("\nOpen your browser to: http://localhost:8000")
    print("Press Ctrl+C to stop the server\n")

    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "app:app",
            "--reload",
            "--host", "0.0.0.0",
            "--port", "8000"
        ])
    except KeyboardInterrupt:
        print("\n\n✓ Dashboard stopped")
        sys.exit(0)

def main():
    """Main entry point"""
    print_header("SPX/SPY Options Trading Bot Dashboard")

    # Check Python version
    if sys.version_info < (3, 8):
        print("Error: Python 3.8+ required")
        sys.exit(1)

    try:
        # Install dependencies
        install_dependencies()

        # Run the dashboard
        run_dashboard()

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
