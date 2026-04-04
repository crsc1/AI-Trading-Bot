#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════
# SPY Order Flow Trading Platform — Startup Script
# ════════════════════════════════════════════════════════════════════════════
#
# Starts all 3 processes:
#   1. Theta Terminal (Java — must already be running, or start manually)
#   2. Flow Engine   (Rust — builds if needed, then runs)
#   3. Dashboard     (Python/FastAPI — installs deps if needed, then runs)
#
# Usage:
#   ./start.sh              # Start engine + dashboard (assumes Theta Terminal running)
#   ./start.sh --build      # Force rebuild engine before starting
#   ./start.sh --dash-only  # Only start the dashboard (engine already running)
#
# Requires:
#   - Rust toolchain (cargo) for flow engine
#   - Python 3.10+ with pip for dashboard
#   - .env file with Alpaca API keys
# ════════════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[0;33m'
BLU='\033[0;34m'
RST='\033[0m'

log()  { echo -e "${BLU}[platform]${RST} $1"; }
ok()   { echo -e "${GRN}[  ok  ]${RST} $1"; }
warn() { echo -e "${YLW}[ warn ]${RST} $1"; }
err()  { echo -e "${RED}[error ]${RST} $1"; }

# ── Check prerequisites ──────────────────────────────────────────────────

if [ ! -f .env ]; then
    err ".env file not found. Copy .env.example and set your Alpaca API keys."
    exit 1
fi

# Source .env for validation
set -a; source .env 2>/dev/null; set +a

if [ -z "$ALPACA_API_KEY" ] || [ -z "$ALPACA_SECRET_KEY" ]; then
    err "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env"
    exit 1
fi

ok "Alpaca keys found (${ALPACA_DATA_FEED:-sip} feed)"

# ── Check Theta Terminal ─────────────────────────────────────────────────

THETA_URL="${THETA_BASE_URL:-http://localhost:25503}"
if curl -s --connect-timeout 2 "$THETA_URL/v2/list/dates?root=SPY&format=json" > /dev/null 2>&1; then
    ok "Theta Terminal is running at $THETA_URL"
else
    warn "Theta Terminal not detected at $THETA_URL — options data will be unavailable"
    warn "Start it with: java -jar ThetaTerminal.jar"
fi

# ── Parse arguments ──────────────────────────────────────────────────────

FORCE_BUILD=false
DASH_ONLY=false
for arg in "$@"; do
    case $arg in
        --build)     FORCE_BUILD=true ;;
        --dash-only) DASH_ONLY=true ;;
    esac
done

# ── Build + Start Flow Engine ────────────────────────────────────────────

ENGINE_BIN="$SCRIPT_DIR/flow-engine/target/release/flow-engine"

if [ "$DASH_ONLY" = false ]; then
    log "Building flow engine..."
    cd flow-engine

    if [ "$FORCE_BUILD" = true ] || [ ! -f "$ENGINE_BIN" ] || [ "$(find src -newer "$ENGINE_BIN" -name '*.rs' 2>/dev/null | head -1)" ]; then
        log "Source changed — rebuilding (this may take a minute)..."
        cargo build --release 2>&1 | tail -5
        ok "Flow engine built successfully"
    else
        ok "Flow engine binary is up to date"
    fi

    cd "$SCRIPT_DIR"

    # Kill any existing engine
    pkill -f "flow-engine" 2>/dev/null || true
    sleep 1

    log "Starting flow engine on port ${FLOW_ENGINE_PORT:-8081}..."
    "$ENGINE_BIN" > /tmp/flow-engine.log 2>&1 &
    ENGINE_PID=$!
    sleep 2

    if kill -0 $ENGINE_PID 2>/dev/null; then
        ok "Flow engine running (PID $ENGINE_PID)"
        # Check if it connected to Alpaca
        sleep 1
        STATS=$(curl -s "http://localhost:${FLOW_ENGINE_PORT:-8081}/stats" 2>/dev/null || echo '{}')
        SOURCE=$(echo "$STATS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data_source','unknown'))" 2>/dev/null || echo "unknown")
        ok "Data source: $SOURCE"
    else
        err "Flow engine failed to start. Check /tmp/flow-engine.log"
        cat /tmp/flow-engine.log | tail -20
        exit 1
    fi
fi

# ── Install Python deps + Start Dashboard ────────────────────────────────

log "Checking Python dependencies..."

# Install if needed (pip with --break-system-packages for system Python)
pip_install() {
    pip install "$@" --break-system-packages -q 2>/dev/null || pip install "$@" -q 2>/dev/null
}

python3 -c "import fastapi, uvicorn, aiohttp" 2>/dev/null || {
    log "Installing Python dependencies..."
    pip_install fastapi uvicorn aiohttp pydantic-settings
}
ok "Python dependencies ready"

# Kill any existing dashboard
pkill -f "uvicorn dashboard.app" 2>/dev/null || true
sleep 1

DASH_PORT=8000
log "Starting dashboard on port $DASH_PORT..."
cd "$SCRIPT_DIR"
python3 -m uvicorn dashboard.app:app --host 0.0.0.0 --port $DASH_PORT > /tmp/dashboard.log 2>&1 &
DASH_PID=$!
sleep 2

if kill -0 $DASH_PID 2>/dev/null; then
    ok "Dashboard running (PID $DASH_PID)"
else
    err "Dashboard failed to start. Check /tmp/dashboard.log"
    cat /tmp/dashboard.log | tail -20
    exit 1
fi

# ── Summary ──────────────────────────────────────────────────────────────

echo ""
echo -e "${GRN}════════════════════════════════════════════════════════════${RST}"
echo -e "${GRN}  Platform is running!${RST}"
echo -e "${GRN}════════════════════════════════════════════════════════════${RST}"
echo ""
echo -e "  Dashboard:     ${BLU}http://localhost:$DASH_PORT${RST}"
echo -e "  Flow Engine:   ${BLU}http://localhost:${FLOW_ENGINE_PORT:-8081}/stats${RST}"
echo -e "  Theta Terminal: ${BLU}$THETA_URL${RST}"
echo ""
echo -e "  Logs:  ${YLW}/tmp/flow-engine.log${RST}  |  ${YLW}/tmp/dashboard.log${RST}"
echo ""
echo -e "  Stop:  ${RED}./stop.sh${RST}  or  ${RED}pkill -f flow-engine; pkill -f uvicorn${RST}"
echo ""

# Wait for either process to exit
wait -n $DASH_PID ${ENGINE_PID:-0} 2>/dev/null
