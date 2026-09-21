#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# 停止 Dashboard 服务（macOS）
PORT="${PORT:-8799}"
LOG_DIR="期货/logs"
PID_FILE="${LOG_DIR}/dashboard_${PORT}.pid"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  if [[ -n "$PID" ]] && kill -0 "$PID" >/dev/null 2>&1; then
    echo "[停止] 结束进程 PID ${PID}"
    kill "$PID"
    rm -f "$PID_FILE"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

PID="$(lsof -tiTCP:"${PORT}" -sTCP:LISTEN || true)"
if [[ -n "$PID" ]]; then
  echo "[停止] 结束监听端口 ${PORT} 的进程 PID ${PID}"
  kill $PID
else
  echo "[提示] 端口 ${PORT} 没有正在监听的服务。"
fi
