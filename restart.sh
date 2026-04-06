#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════
# Restart all platform components
# ════════════════════════════════════════════════════════════════════════════
#
# Usage:
#   ./restart.sh              # Restart flow engine + dashboard
#   ./restart.sh --dash-only  # Restart dashboard only (engine stays running)
#
# ════════════════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[0;33m'
BLU='\033[0;34m'
RST='\033[0m'

DASH_ONLY=false
for arg in "$@"; do
    case $arg in
        --dash-only) DASH_ONLY=true ;;
    esac
done

echo -e "${YLW}Restarting platform...${RST}"
echo ""

# ── Stop ─────────────────────────────────────────────────────────────────

if [ "$DASH_ONLY" = false ]; then
    echo -n "  Stopping flow engine... "
    pkill -f "flow-engine" 2>/dev/null && echo -e "${RED}stopped${RST}" || echo "not running"
fi

echo -n "  Stopping dashboard... "
pkill -f "uvicorn dashboard.app" 2>/dev/null && echo -e "${RED}stopped${RST}" || echo "not running"
pkill -f "python.*dashboard" 2>/dev/null || true

sleep 2

# ── Clean bytecode cache ─────────────────────────────────────────────────

find dashboard -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find dashboard -name "*.pyc" -delete 2>/dev/null || true
echo -e "  ${GRN}Bytecode cache cleared${RST}"

# ── Source .env ──────────────────────────────────────────────────────────

set -a; source .env 2>/dev/null; set +a

# ── Start flow engine ────────────────────────────────────────────────────

if [ "$DASH_ONLY" = false ]; then
    ENGINE_BIN="$SCRIPT_DIR/flow-engine/target/release/flow-engine"
    if [ -x "$ENGINE_BIN" ]; then
        echo -n "  Starting flow engine... "
        "$ENGINE_BIN" > /tmp/flow-engine.log 2>&1 &
        ENGINE_PID=$!
        sleep 2
        if kill -0 $ENGINE_PID 2>/dev/null; then
            echo -e "${GRN}running${RST} (PID $ENGINE_PID)"
        else
            echo -e "${RED}FAILED${RST} — check /tmp/flow-engine.log"
        fi
    else
        echo -e "  ${YLW}Flow engine binary not found — run ./start.sh to build${RST}"
    fi
fi

# ── Start dashboard ──────────────────────────────────────────────────────

DASH_PORT=8000
echo -n "  Starting dashboard... "
python3 -m uvicorn dashboard.app:app --host 0.0.0.0 --port $DASH_PORT > /tmp/dashboard.log 2>&1 &
DASH_PID=$!
sleep 2

if kill -0 $DASH_PID 2>/dev/null; then
    echo -e "${GRN}running${RST} (PID $DASH_PID)"
else
    echo -e "${RED}FAILED${RST} — check /tmp/dashboard.log"
    tail -10 /tmp/dashboard.log
    exit 1
fi

# ── Summary ──────────────────────────────────────────────────────────────

echo ""
echo -e "${GRN}════════════════════════════════════════════════════════════${RST}"
echo -e "${GRN}  Platform restarted!${RST}"
echo -e "${GRN}════════════════════════════════════════════════════════════${RST}"
echo ""
echo -e "  Dashboard:    ${BLU}http://localhost:$DASH_PORT${RST}"
echo -e "  Flow Engine:  ${BLU}http://localhost:${FLOW_ENGINE_PORT:-8081}/stats${RST}"
echo -e "  Logs:         ${YLW}/tmp/flow-engine.log${RST}  |  ${YLW}/tmp/dashboard.log${RST}"
echo ""
echo -e "  Stop:  ${RED}./stop.sh${RST}"
echo ""

wait -n $DASH_PID ${ENGINE_PID:-0} 2>/dev/null
