#!/bin/bash
# 啟動 Position Calculator - 前端 + 後端 (同一個 Terminal)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 啟動 Position Calculator..."
echo ""

# 啟動後端 (背景)
echo "啟動後端服務..."
source venv/bin/activate
python backend/main.py &
BACKEND_PID=$!

# 返回專案根目錄
cd "$SCRIPT_DIR"

# 啟動前端 (背景)
echo "啟動前端服務..."
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ 服務已啟動："
echo "   - 前端: http://localhost:3000"
echo "   - 後端: http://localhost:8000"
echo ""
echo "按 Ctrl+C 停止所有服務"
echo ""

# 等候 Ctrl+C
trap "echo '停止服務...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
