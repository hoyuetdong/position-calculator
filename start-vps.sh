#!/bin/bash
# VPS 啟動腳本 - 適用於 VPS 部署
# 使用方法: ./start-vps.sh
# 日誌位置: /tmp/position-calculator-{backend,frontend}.log

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

# 殺掉舊進程
echo -e "${YELLOW}殺掉舊進程...${NC}"
pkill -f "python backend/main.py" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
sleep 2

# 確保 Python 虛擬環境存在
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}創建 Python 虛擬環境...${NC}"
    python3 -m venv venv
fi

# 激活虛擬環境並安裝依賴
echo -e "${YELLOW}安裝 Python 依賴...${NC}"
source venv/bin/activate
pip install -q -r requirements.txt 2>/dev/null || pip install -r requirements.txt

# 返回專案根目錄
cd "$SCRIPT_DIR"

# 啟動後端
echo -e "${GREEN}啟動後端服務...${NC}"
source venv/bin/activate
nohup python backend/main.py > /tmp/position-calculator-backend.log 2>&1 &
BACKEND_PID=$!
echo "後端 PID: $BACKEND_PID"
echo "後端日誌: /tmp/position-calculator-backend.log"

# 等一下後端啟動
sleep 3

# 檢查後端是否啟動成功
if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 後端啟動成功${NC}"
else
    echo -e "${RED}✗ 後端啟動失敗，查看日誌: tail /tmp/position-calculator-backend.log${NC}"
fi

# 返回專案根目錄
cd "$SCRIPT_DIR"

# 啟動前端
echo -e "${GREEN}啟動前端服務...${NC}"
nohup npm run dev > /tmp/position-calculator-frontend.log 2>&1 &
FRONTEND_PID=$!
echo "前端 PID: $FRONTEND_PID"
echo "前端日誌: /tmp/position-calculator-frontend.log"

# 等一下前端啟動
sleep 5

# 檢查前端是否啟動成功
if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 前端啟動成功${NC}"
else
    echo -e "${RED}✗ 前端啟動失敗，查看日誌: tail /tmp/position-calculator-frontend.log${NC}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}  服務已啟動！${NC}"
echo "=========================================="
echo ""
echo "前端: http://localhost:3000"
echo "後端: http://localhost:8000"
echo ""
echo "常用命令:"
echo "  tail -f /tmp/position-calculator-backend.log  # 查看後端日誌"
echo "  tail -f /tmp/position-calculator-frontend.log # 查看前端日誌"
echo "  curl http://localhost:8000/api/health         # 測試後端"
echo "  ./stop-vps.sh                                     # 停止服務"
echo ""
echo "要停止服務，請運行: ./stop-vps.sh"
