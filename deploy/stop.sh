#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"
RUNTIME_DIR="$PROJECT_DIR/workspace/runtime"
PID_DIR="$RUNTIME_DIR/pids"

stop_process() {
  python3 "$DEPLOY_DIR/stop_managed.py" "$1"
}

stop_process guardian
stop_process detector
stop_process user_stream
stop_process demo_stream
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

if [[ -f "$DEPLOY_DIR/.env.p0" ]]; then
  set -a
  source "$DEPLOY_DIR/.env.p0"
  set +a
  COMPOSE_FILES=(-f "$DEPLOY_DIR/compose.yaml")
  [[ -z "${MQTT_CA_FILE:-}" ]] || COMPOSE_FILES+=(-f "$DEPLOY_DIR/compose.p0-tls.yaml")
  docker compose "${COMPOSE_FILES[@]}" stop
else
  docker stop railway-emqx railway-mediamtx
fi
echo "所有托管服务已停止；Docker 数据卷和 MySQL 数据均保留。"
