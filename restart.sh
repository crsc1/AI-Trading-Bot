#!/bin/bash
# Restart all platform components
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'; BLU='\033[0;34m'; RST='\033[0m'

DASH_ONLY=false
for arg in "$@"; do case $arg in --dash-only) DASH_ONLY=true ;; esac; done

echo -e "${YLW}Restarting platform...${RST}"

if [ "$DASH_ONLY" = false ]; then
    echo -n "  Stopping ThetaData server... "
    pkill -f "thetadatadx-server" 2>/dev/null && echo -e "${RED}stopped${RST}" || echo "not running"
    pkill -f "ThetaTerminal" 2>/dev/null || true
    echo -n "  Stopping flow engine... "
    pkill -f "flow-engine" 2>/dev/null && echo -e "${RED}stopped${RST}" || echo "not running"
fi
echo -n "  Stopping dashboard... "
pkill -f "uvicorn dashboard.app" 2>/dev/null && echo -e "${RED}stopped${RST}" || echo "not running"
pkill -f "python.*dashboard" 2>/dev/null || true
sleep 2

find dashboard -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
set -a; source .env 2>/dev/null; set +a

THETA_SERVER_BIN="$SCRIPT_DIR/bin/thetadatadx-server"
if [ "$DASH_ONLY" = false ] && [ -x "$THETA_SERVER_BIN" ] && [ -n "$THETADATA_EMAIL" ] && [ -n "$THETADATA_PASSWORD" ]; then
    echo -n "  Starting ThetaData server... "
    "$THETA_SERVER_BIN" --email "$THETADATA_EMAIL" --password "$THETADATA_PASSWORD" > /tmp/theta-server.log 2>&1 &
    THETA_PID=$!; sleep 2
    kill -0 $THETA_PID 2>/dev/null && echo -e "${GRN}running${RST} (PID $THETA_PID)" || echo -e "${RED}FAILED${RST}"
fi

if [ "$DASH_ONLY" = false ]; then
    ENGINE_BIN="$SCRIPT_DIR/flow-engine/target/release/flow-engine"
    if [ -x "$ENGINE_BIN" ]; then
        echo -n "  Starting flow engine... "
        "$ENGINE_BIN" > /tmp/flow-engine.log 2>&1 &
        ENGINE_PID=$!; sleep 2
        kill -0 $ENGINE_PID 2>/dev/null && echo -e "${GRN}running${RST} (PID $ENGINE_PID)" || echo -e "${RED}FAILED${RST}"
    fi
fi

DASH_PORT=8000
echo -n "  Starting dashboard... "
python3 -m uvicorn dashboard.app:app --host 0.0.0.0 --port $DASH_PORT > /tmp/dashboard.log 2>&1 &
DASH_PID=$!; sleep 2
kill -0 $DASH_PID 2>/dev/null && echo -e "${GRN}running${RST} (PID $DASH_PID)" || { echo -e "${RED}FAILED${RST}"; tail -10 /tmp/dashboard.log; exit 1; }

echo ""
echo -e "${GRN}  Platform restarted!${RST}"
echo -e "  Dashboard:    ${BLU}http://localhost:$DASH_PORT${RST}"
echo -e "  Flow Engine:  ${BLU}http://localhost:${FLOW_ENGINE_PORT:-8081}/stats${RST}"
echo -e "  ThetaData:    ${BLU}http://localhost:25503${RST} (native Rust)"
echo -e "  Stop: ${RED}./stop.sh${RST}"
echo ""
wait -n $DASH_PID ${ENGINE_PID:-0} 2>/dev/null
