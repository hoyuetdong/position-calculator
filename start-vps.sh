#!/bin/bash
# VPS 啟動腳本 - 使用 Screen 管理
# 使用方法: ./start-vps.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  Position Calculator - VPS 啟動腳本"
echo "=========================================="
echo ""

# 顏色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 停止舊的 app screen
echo -e "${YELLOW}停止舊的 app screen...${NC}"
screen -S app -X quit 2>/dev/null || true
sleep 1

# 殺掉舊進程（確保乾淨）
pkill -f "python3 backend/main.py" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
sleep 1

echo -e "${GREEN}✓ 舊進程已清理${NC}"
echo ""

# 確保 .next/standalone 存在（production build）
if [ ! -d ".next/standalone" ]; then
    echo -e "${YELLOW}需要先 build，請運行: npm run build${NC}"
    exit 1
fi

# Load environment variables from .env
if [ -f ".env" ]; then
    echo -e "${GREEN}載入 .env 環境變數...${NC}"
    set -a
    source .env
    set +a
fi

# 創建 app screen，包含 backend 和 frontend 兩個 window
echo -e "${GREEN}創建 app screen...${NC}"

# 導出需要嘅環境變數俾後續使用
export APP_PASSWORD
export PYTHON_API_URL
export FUTU_HOST
export FUTU_PORT
export FUTU_LOGIN_ACCOUNT
export FUTU_TRADE_PWD
export API_SECRET

# Window 1: Backend
screen -dmS app bash -c "cd $SCRIPT_DIR && python3 backend/main.py; exec bash"

# 等一下 backend 啟動
sleep 2

# Window 2: Frontend (需要 APP_PASSWORD 俾 middleware)
screen -S app -X screen -t frontend bash -c "cd $SCRIPT_DIR/.next/standalone && APP_PASSWORD='$APP_PASSWORD' PORT=3000 HOSTNAME=0.0.0.0 node server.js; exec bash"

# 等一下
sleep 3

echo ""
echo "=========================================="
echo -e "${GREEN}  Screen 已創建！${NC}"
echo "=========================================="
echo ""
echo "Screen 狀態:"
screen -ls
echo ""
echo "查看 Position Calculator:"
echo "  screen -r app"
echo "  - Ctrl+A n: 切換到下一個 window (frontend)"
echo "  - Ctrl+A p: 切換到上一個 window (backend)"
echo "  - Ctrl+A D: 退出 screen"
echo ""
echo "驗證服務:"
echo "  curl -s -o /dev/null -w 'Frontend: %{http_code}\\n' http://localhost:3000/"
echo "  ss -tlnp | grep -E ':8000|:3000'"
