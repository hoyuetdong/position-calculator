#!/bin/bash
# VPS 停止腳本
# 使用方法: ./stop-vps.sh

echo "停止 Position Calculator 服務..."

# 殺掉 app screen
screen -S app -X quit 2>/dev/null && echo "✓ app screen 已停止" || echo "- app screen 未運行"

# 殺掉舊進程（確保乾淨）
pkill -f "python3 backend/main.py" 2>/dev/null && echo "✓ Backend 已停止" || echo "- Backend 未運行"
pkill -f "next-server" 2>/dev/null && echo "✓ Frontend 已停止" || echo "- Frontend 未運行"

echo ""
echo "所有 Position Calculator 服務已停止。"
echo "OpenD (opend screen) 保持運行。"
