#!/bin/bash
# VPS 停止腳本
# 使用方法: ./stop-vps.sh

echo "停止 Position Calculator 服務..."

# 殺掉進程
pkill -f "python backend/main.py" 2>/dev/null && echo "✓ 後端已停止" || echo "- 後端未運行"
pkill -f "next dev" 2>/dev/null && echo "✓ 前端已停止" || echo "- 前端未運行"
pkill -f "next-server" 2>/dev/null && echo "✓ Next.js 已停止" || echo "- Next.js 未運行"

echo ""
echo "所有服務已停止。"
echo "日誌保留在 /tmp/position-calculator-*.log"
