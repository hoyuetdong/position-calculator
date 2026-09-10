#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPEND_DIR="/opt/futuopend"
OPEND_BIN="$OPEND_DIR/FutuOpenD"
OPEND_CFG="$OPEND_DIR/FutuOpenD.xml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cd "$SCRIPT_DIR"

echo "=========================================="
echo " Position Calculator - CLEAN START"
echo "=========================================="

stop_named_screen() {
    local name="$1"

    for s in $(screen -ls 2>/dev/null | awk -v pat="\\.${name}" '$0 ~ pat {print $1}'); do
        echo "Stopping screen: $s"
        screen -S "$s" -X quit 2>/dev/null || true
    done
}


echo
echo -e "${YELLOW}[1/7] 停止 Backend / Frontend...${NC}"

if systemctl cat vcp-backend.service >/dev/null 2>&1; then
    systemctl stop vcp-frontend vcp-backend
fi

stop_named_screen app
stop_named_screen frontend

pkill -TERM -f '[p]ython3 .*backend/main.py' 2>/dev/null || true
pkill -TERM -f '[n]ode .*server.js' 2>/dev/null || true

sleep 2


echo
echo -e "${YELLOW}[2/7] CLEAN STOP Futu OpenD...${NC}"

# 關所有歷史 opend screen
for s in $(screen -ls 2>/dev/null | awk '/\.opend/{print $1}'); do
    echo "Stopping OpenD screen: $s"
    screen -S "$s" -X quit 2>/dev/null || true
done

# graceful first
pkill -TERM -x FutuOpenD 2>/dev/null || true

for i in {1..8}; do
    if ! pgrep -x FutuOpenD >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# fallback only if still alive
if pgrep -x FutuOpenD >/dev/null 2>&1; then
    echo "FutuOpenD still alive, force killing..."
    pkill -KILL -x FutuOpenD 2>/dev/null || true
    sleep 2
fi

# 確認舊 port 真係釋放
if ss -ltn | grep -qE '127\.0\.0\.1:(11111|2222)'; then
    echo -e "${RED}ERROR: 11111/2222 still occupied after stopping OpenD.${NC}"
    ss -ltnp | grep -E ':11111|:2222' || true
    exit 1
fi


echo
echo -e "${GREEN}[3/7] 啟動乾淨 Futu OpenD...${NC}"

if [ ! -x "$OPEND_BIN" ]; then
    echo -e "${RED}ERROR: $OPEND_BIN not found/executable.${NC}"
    exit 1
fi

if [ ! -f "$OPEND_CFG" ]; then
    echo -e "${RED}ERROR: $OPEND_CFG not found.${NC}"
    exit 1
fi

screen -dmS opend bash -lc \
"cd '$OPEND_DIR' && exec ./FutuOpenD -cfg_file='$OPEND_CFG'"

echo "Waiting for OpenD :11111..."

OPEND_OK=0

for i in {1..20}; do
    if timeout 1 bash -c 'cat < /dev/null > /dev/tcp/127.0.0.1/11111' \
        2>/dev/null
    then
        OPEND_OK=1
        break
    fi

    sleep 1
done

if [ "$OPEND_OK" != "1" ]; then
    echo -e "${RED}ERROR: OpenD :11111 did not become ready.${NC}"

    SESSION=$(screen -ls 2>/dev/null | awk '/\.opend/{print $1; exit}')

    if [ -n "${SESSION:-}" ]; then
        screen -S "$SESSION" -X hardcopy -h /tmp/opend-start-failed.log || true
        tail -n 100 /tmp/opend-start-failed.log 2>/dev/null || true
    fi

    exit 1
fi

echo -e "${GREEN}✓ OpenD ready${NC}"

ss -ltnp | grep -E ':11111|:2222' || true


echo
echo -e "${YELLOW}[4/7] 檢查 Backend runtime...${NC}"

if [ ! -x "$SCRIPT_DIR/venv/bin/python3" ]; then
    echo -e "${RED}ERROR: venv/bin/python3 missing.${NC}"
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo -e "${RED}ERROR: .env missing.${NC}"
    exit 1
fi

# Load + export 全部 .env variables
set -a
source "$SCRIPT_DIR/.env"
set +a

echo "Backend Python:"
"$SCRIPT_DIR/venv/bin/python3" - <<'PY'
import sys
import futu

print("  executable :", sys.executable)
print("  prefix     :", sys.prefix)
print("  futu       :", futu.__file__)
PY


echo
echo -e "${GREEN}[5/7] 啟動 Backend...${NC}"

if systemctl cat vcp-backend.service >/dev/null 2>&1; then
    systemctl start vcp-backend
else
    screen -dmS app bash -lc "cd '$SCRIPT_DIR' && exec '$SCRIPT_DIR/venv/bin/python3' backend/main.py"
fi

echo "Waiting for backend :8000..."

BACKEND_OK=0

for i in {1..25}; do
    if curl --max-time 2 -fsS http://127.0.0.1:8000/api/env >/dev/null 2>&1; then
        BACKEND_OK=1
        break
    fi

    sleep 1
done

if [ "$BACKEND_OK" != "1" ]; then
    echo -e "${RED}ERROR: Backend did not become ready.${NC}"

    SESSION=$(screen -ls 2>/dev/null | awk '/\.app/{print $1; exit}')

    if [ -n "${SESSION:-}" ]; then
        screen -S "$SESSION" -X hardcopy -h /tmp/backend-start-failed.log || true
        tail -n 150 /tmp/backend-start-failed.log 2>/dev/null || true
    fi

    exit 1
fi

echo -e "${GREEN}✓ Backend ready${NC}"

curl -s http://127.0.0.1:8000/api/env
echo


echo
echo -e "${YELLOW}[6/7] 啟動 Frontend...${NC}"

if [ ! -f "$SCRIPT_DIR/.next/standalone/server.js" ]; then
    echo -e "${YELLOW}WARNING: .next/standalone/server.js missing.${NC}"
    echo "Backend/OpenD 已正常啟動。"
    echo "如要 frontend，先執行 npm run build。"
else

    mkdir -p "$SCRIPT_DIR/.next/standalone/.next"

    if [ -d "$SCRIPT_DIR/.next/static" ]; then
        rm -rf "$SCRIPT_DIR/.next/standalone/.next/static" 2>/dev/null || true
        ln -s "$SCRIPT_DIR/.next/static" \
              "$SCRIPT_DIR/.next/standalone/.next/static"
    fi

    if systemctl cat vcp-frontend.service >/dev/null 2>&1; then
        systemctl start vcp-frontend
    else
        screen -dmS frontend bash "$SCRIPT_DIR/run-frontend.sh"
    fi

    FRONTEND_OK=0
    for i in {1..20}; do
        if [[ "$(curl --max-time 2 -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/)" =~ ^(200|401)$ ]]; then
            FRONTEND_OK=1
            echo -e "${GREEN}✓ Frontend ready${NC}"
            break
        fi
        sleep 1
    done
    if [ "$FRONTEND_OK" != "1" ]; then
        echo "ERROR: Frontend did not become ready"
        exit 1
    fi
fi


echo
echo -e "${GREEN}[7/7] STATUS${NC}"
echo

screen -ls || true

echo
echo "Ports:"
ss -ltnp | grep -E ':11111|:2222|:8000|:3000' || true

echo
echo "Processes:"
pgrep -af 'FutuOpenD|backend/main.py|server.js' || true

echo
echo "=========================================="
echo -e "${GREEN} CLEAN START COMPLETE${NC}"
echo "=========================================="
