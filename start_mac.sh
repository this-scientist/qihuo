#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# 商品期货/期权研究系统启动脚本（macOS）
PORT="${PORT:-8799}"
PY=".venv/bin/python"
URL="http://127.0.0.1:${PORT}/index.html"
LOG_DIR="期货/logs"
PID_FILE="${LOG_DIR}/dashboard_${PORT}.pid"

if [[ ! -x "$PY" ]]; then
  echo "[错误] 未找到虚拟环境 ${PY}"
  echo "请先执行: python3 -m venv .venv"
  echo "然后安装依赖: ${PY} -m pip install -r 期货/requirements.txt"
  exit 1
fi

mkdir -p "$LOG_DIR"

if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[提示] 端口 ${PORT} 已在监听，服务可能已启动，直接打开页面。"
  open "$URL"
  exit 0
fi

echo "[启动] Dashboard 服务端口 ${PORT} ..."
nohup "$PY" "期货/dashboard_server.py" --port "$PORT" \
  > "${LOG_DIR}/dashboard_${PORT}.log" 2>&1 &
PID="$!"
echo "$PID" > "$PID_FILE"

READY=0
for _ in {1..15}; do
  if ! kill -0 "$PID" >/dev/null 2>&1; then
    echo "[错误] Dashboard 服务启动后退出。最近日志："
    tail -n 80 "${LOG_DIR}/dashboard_${PORT}.log"
    rm -f "$PID_FILE"
    exit 1
  fi
  if curl --max-time 2 -fsS "http://127.0.0.1:${PORT}/api/data" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done

if [[ "$READY" != "1" ]]; then
  echo "[错误] Dashboard 进程仍在运行，但 API 未响应。最近日志："
  tail -n 80 "${LOG_DIR}/dashboard_${PORT}.log"
  exit 1
fi

open "$URL"

echo
echo "服务已启动: ${URL}"
echo "期权扫描页: http://127.0.0.1:${PORT}/scanner.html"
echo "停止服务: ./stop_mac.sh"
echo "日志文件: ${LOG_DIR}/dashboard_${PORT}.log"
