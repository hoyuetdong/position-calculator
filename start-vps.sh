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

# 停止舊的 screens
echo -e "${YELLOW}停止舊的 screens...${NC}"
screen -S app -X quit 2>/dev/null || true
screen -S frontend -X quit 2>/dev/null || true
sleep 1

# 殺掉舊進程（確保乾淨）
pkill -f "python3 backend/main.py" 2>/dev/null || true
pkill -f "node" 2>/dev/null || true
sleep 1

echo -e "${GREEN}✓ 舊進程已清理${NC}"
echo ""

# 確保 .next/standalone 存在（production build）
if [ ! -d ".next/standalone" ]; then
    echo -e "${YELLOW}需要先 build，請運行: npm run build${NC}"
    exit 1
fi

# 確保 static files symlink 存在（standalone 模式的 bug）
if [ ! -L ".next/standalone/.next/static" ]; then
    echo -e "${GREEN}創建 static files symlink...${NC}"
    rm -rf .next/standalone/.next/static 2>/dev/null
    ln -sf ../../static .next/standalone/.next/static
fi

# Load environment variables from .env
if [ -f ".env" ]; then
    echo -e "${GREEN}載入 .env 環境變數...${NC}"
    set -a
    source .env
    set +a
    
    # 創建 wrapper script 俾 frontend（因為 screen session 唔會 inherit 環境變數）
    cat > /tmp/start-frontend.sh << EOFWRAPPER
#!/bin/bash
export HOSTNAME='0.0.0.0'
export PORT='3000'
export APP_PASSWORD='${APP_PASSWORD}'
export PYTHON_API_URL='${PYTHON_API_URL}'
export API_SECRET='${API_SECRET}'
cd ${SCRIPT_DIR}/.next/standalone
exec node server.js
EOFWRAPPER
    chmod +x /tmp/start-frontend.sh
    echo -e "${GREEN}✓ Frontend wrapper script 已創建 (bind 127.0.0.1)${NC}"
fi

# 確保 .next/standalone/.env 存在（下次重啟時 load）
if [ -f ".env" ]; then
    echo -e "${GREEN}更新 standalone .env...${NC}"
    grep -E '^(APP_PASSWORD|PYTHON_API_URL|API_SECRET)=' .env > .next/standalone/.env
    echo "HOSTNAME=0.0.0.0" >> .next/standalone/.env
fi

echo ""
echo -e "${GREEN}啟動 Backend...${NC}"

# Backend screen
screen -dmS app bash -c "cd $SCRIPT_DIR && python3 backend/main.py; exec bash"

# 等一下 backend 啟動
sleep 3

echo -e "${GREEN}啟動 Frontend...${NC}"

# Frontend screen (separate)
screen -dmS frontend bash -c '/tmp/start-frontend.sh; exec bash'

# 等一下
sleep 3

echo ""
echo "=========================================="
echo -e "${GREEN}  所有服務已啟動！${NC}"
echo "=========================================="
echo ""
echo "Screen 狀態:"
screen -ls
echo ""
echo "查看 Position Calculator: http://107.173.153.41:3000"
echo ""
echo "查看後端日誌:"
echo "  screen -r app"
echo ""
echo "查看前端日誌:"
echo "  screen -r frontend"
echo ""
echo "驗證服務:"
echo "  curl -s -o /dev/null -w 'Frontend: %{http_code}\\n' http://localhost:3000/"
echo "  curl -s http://localhost:8000/api/health"
echo ""
echo "退出 screen: Ctrl+A D"
