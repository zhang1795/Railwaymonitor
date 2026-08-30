#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"
RUNTIME_DIR="$PROJECT_DIR/workspace/runtime"
PID_DIR="$RUNTIME_DIR/pids"

stop_process() {
  local name="$1"
  local pidfile="$PID_DIR/$name.pid"
  if [[ ! -f "$pidfile" ]]; then
    echo "$name 没有 PID 文件，跳过"
    return
  fi
  local pid
  pid="$(<"$pidfile")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    for _ in {1..40}; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.25
    done
  fi
  unlink "$pidfile" 2>/dev/null || true
  echo "$name 已停止"
}

stop_process detector
stop_process frontend
stop_process flask
stop_process backend

MYSQL_SOCKET="$RUNTIME_DIR/mysql/run/mysql.sock"
MYSQL_BASE_VALUE="/data/anaconda3"
if [[ -f "$DEPLOY_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$DEPLOY_DIR/.env"
  set +a
  MYSQL_BASE_VALUE="${MYSQL_BASE:-/data/anaconda3}"
fi
if "$MYSQL_BASE_VALUE/bin/mysqladmin" --protocol=socket --socket="$MYSQL_SOCKET" -uroot ping >/dev/null 2>&1; then
  "$MYSQL_BASE_VALUE/bin/mysqladmin" --protocol=socket --socket="$MYSQL_SOCKET" -uroot shutdown
  echo "mysql 已停止"
fi

docker compose -f "$DEPLOY_DIR/compose.yaml" stop
echo "所有托管服务已停止；Docker 数据卷和 MySQL 数据均保留。"
