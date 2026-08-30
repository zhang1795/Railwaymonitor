#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"
RUNTIME_DIR="$PROJECT_DIR/workspace/runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PID_DIR="$RUNTIME_DIR/pids"

if [[ ! -f "$DEPLOY_DIR/.env" ]]; then
  echo "缺少 $DEPLOY_DIR/.env，请先复制 .env.example 并填写配置。" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$DEPLOY_DIR/.env"
set +a

mkdir -p "$LOG_DIR" "$PID_DIR" "$RUNTIME_DIR/mysql/run" "$RUNTIME_DIR/mysql/log"

start_process() {
  local name="$1"
  local workdir="$2"
  shift 2
  local pidfile="$PID_DIR/$name.pid"
  local logfile="$LOG_DIR/$name.log"

  if [[ -f "$pidfile" ]]; then
    local existing_pid
    existing_pid="$(<"$pidfile")"
    if kill -0 "$existing_pid" 2>/dev/null; then
      echo "$name 已运行，PID=$existing_pid"
      return
    fi
  fi

  (
    cd "$workdir"
    nohup "$@" >>"$logfile" 2>&1 &
    echo $! >"$pidfile"
  )
  echo "$name 已启动，日志：$logfile"
}

start_mysql() {
  local mysql_base="${MYSQL_BASE:-/data/anaconda3}"
  local mysql_data="$RUNTIME_DIR/mysql/data"
  local mysql_socket="$RUNTIME_DIR/mysql/run/mysql.sock"
  local mysql_pid="$RUNTIME_DIR/mysql/run/mysql.pid"
  local mysql_log="$RUNTIME_DIR/mysql/log/mysql.log"

  if "$mysql_base/bin/mysqladmin" --protocol=socket --socket="$mysql_socket" -uroot ping >/dev/null 2>&1; then
    echo "mysql 已运行"
    return
  fi
  if [[ ! -d "$mysql_data/mysql" ]]; then
    echo "MySQL 数据目录尚未初始化：$mysql_data" >&2
    exit 1
  fi

  nohup "$mysql_base/bin/mysqld" \
    --no-defaults \
    --basedir="$mysql_base" \
    --lc-messages-dir="$mysql_base/share/mysql" \
    --datadir="$mysql_data" \
    --port=3307 \
    --bind-address=127.0.0.1 \
    --socket="$mysql_socket" \
    --pid-file="$mysql_pid" \
    --log-error="$mysql_log" \
    --skip-log-bin \
    --character-set-server=utf8mb4 \
    --collation-server=utf8mb4_unicode_ci >/dev/null 2>&1 &

  for _ in {1..60}; do
    if "$mysql_base/bin/mysqladmin" --protocol=socket --socket="$mysql_socket" -uroot ping >/dev/null 2>&1; then
      echo "mysql 已启动"
      return
    fi
    sleep 0.5
  done
  echo "MySQL 启动失败，请查看 $mysql_log" >&2
  exit 1
}

WITH_DETECTOR=false
if [[ "${1:-}" == "--with-detector" ]]; then
  WITH_DETECTOR=true
fi

docker compose -f "$DEPLOY_DIR/compose.yaml" up -d
start_mysql

JAVA_BIN="$RUNTIME_DIR/jdk17/usr/lib/jvm/java-17-openjdk-amd64/bin/java"
FLASK_PYTHON="$RUNTIME_DIR/flask-venv/bin/python"
DETECTOR_PYTHON="$RUNTIME_DIR/detector-env/bin/python"

start_process backend "$PROJECT_DIR" \
  env DB_USERNAME="$DB_USERNAME" DB_PASSWORD="$DB_PASSWORD" SERVER_PORT="${SERVER_PORT:-8080}" \
  "$JAVA_BIN" -jar web-springboot/target/railway-monitoring-1.0.0.jar

start_process flask "$PROJECT_DIR/web-flask" \
  env FLASK_HOST="${FLASK_HOST:-0.0.0.0}" FLASK_PORT="${FLASK_PORT:-5000}" \
  "$FLASK_PYTHON" app.py

start_process frontend "$PROJECT_DIR/web-vue" npm run dev -- --host 0.0.0.0

if [[ "$WITH_DETECTOR" == true ]]; then
  mkdir -p "$RUNTIME_DIR/config/yolov5" "$RUNTIME_DIR/config/matplotlib" "$RUNTIME_DIR/cache" "$RUNTIME_DIR/detector-output"
  start_process detector "$PROJECT_DIR/RailwayDetector" \
    env YOLOV5_CONFIG_DIR="$RUNTIME_DIR/config/yolov5" \
    XDG_CONFIG_HOME="$RUNTIME_DIR/config" XDG_CACHE_HOME="$RUNTIME_DIR/cache" \
    MPLCONFIGDIR="$RUNTIME_DIR/config/matplotlib" \
    RAILWAY_DEVICE="${RAILWAY_DEVICE:-cpu}" RAILWAY_MODEL_PATH="${RAILWAY_MODEL_PATH:-./models/best1030.pt}" \
    MQTT_HOST="${MQTT_HOST:-127.0.0.1}" MQTT_PORT="${MQTT_PORT:-1883}" \
    DETECTOR_OUTPUT_DIR="$RUNTIME_DIR/detector-output" \
    "$DETECTOR_PYTHON" ui.py
fi

echo "启动命令已完成。运行 deploy/status.sh 查看健康状态。"
