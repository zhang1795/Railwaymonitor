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
if [[ ! -f "$DEPLOY_DIR/.env.p0" ]]; then
  echo "缺少 P0 服务身份配置。请按 deploy/P0-ROLLOUT.md 准备 .env.p0 并完成数据库迁移。" >&2
  exit 1
fi
python3 - "$DEPLOY_DIR/.env" "$DEPLOY_DIR/.env.p0" <<'PY'
import os, sys
for path in sys.argv[1:]:
    if os.stat(path).st_mode & 0o077:
        raise SystemExit('配置文件必须只允许当前用户读取，请先 chmod 600: '+path)
PY

set -a
# shellcheck disable=SC1091
source "$DEPLOY_DIR/.env"
source "$DEPLOY_DIR/.env.p0"
set +a

mkdir -p "$LOG_DIR" "$PID_DIR" "$RUNTIME_DIR/mysql/run" "$RUNTIME_DIR/mysql/log"

start_process() {
  local name="$1"
  local workdir="$2"
  shift 2
  local pidfile="$PID_DIR/$name.pid"
  local logfile="$LOG_DIR/$name.log"

  python3 - "$workdir" "$pidfile" "$logfile" "$@" <<'PY'
import os, subprocess, sys
import json
from pathlib import Path
workdir, pidfile, logfile = sys.argv[1:4]
name=Path(pidfile).stem
root=Path(pidfile).parents[3]
sys.path.insert(0,str(root/'deploy'))
from stop_managed import process,expected
current=process(int(Path(pidfile).read_text())) if Path(pidfile).exists() else None
if current:
    if not expected(name,root,current[1],current[2]):raise SystemExit('PID identity mismatch; refusing duplicate startup')
    if current[2]!=Path(workdir).resolve():raise SystemExit('Running source release differs; use the guarded rollout')
    if name=='backend' and current[1][current[1].index('-jar')+1]!=sys.argv[4:][sys.argv[4:].index('-jar')+1]:raise SystemExit('Running jar differs; use the guarded rollout')
if name in ('backend','flask','detector','demo_stream'):
    manifest=Path(pidfile).parents[1]/'managed-services.json'
    specs=json.loads(manifest.read_text()) if manifest.exists() else {}
    port=os.environ.get('SERVER_PORT','8080') if name=='backend' else os.environ.get('FLASK_PORT','5000')
    specs[name]={'args':sys.argv[4:],'cwd':workdir,'env':dict(os.environ),'startupGrace':180,'health':'http://127.0.0.1:'+port+('/api/health/live' if name=='backend' else '/api/health')}
    temp=manifest.with_suffix('.tmp');temp.write_text(json.dumps(specs));temp.chmod(0o600);temp.replace(manifest)
if current:raise SystemExit(0)
with open(logfile, 'ab', buffering=0) as output:
    process = subprocess.Popen(sys.argv[4:], cwd=workdir,
        stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
        start_new_session=True)
with open(pidfile, 'w') as output:
    output.write(str(process.pid)+'\n')
PY
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
WITH_DEMO=false
for option in "$@"; do
  case "$option" in
    --with-detector) WITH_DETECTOR=true ;;
    --with-demo) WITH_DEMO=true ;;
    *) echo "未知参数：$option（支持 --with-detector、--with-demo）" >&2; exit 1 ;;
  esac
done

python3 "$DEPLOY_DIR/prepare_p0_broker.py" --output "$RUNTIME_DIR/emqx-p0"
COMPOSE_FILES=(-f "$DEPLOY_DIR/compose.yaml")
if [[ -n "${MQTT_CA_FILE:-}" ]]; then
  COMPOSE_FILES+=(-f "$DEPLOY_DIR/compose.p0-tls.yaml")
elif [[ "${MQTT_ALLOW_LOCAL_PLAINTEXT:-false}" != true ]]; then
  echo "必须配置 TLS；仅显式允许的环回开发模式可使用明文 MQTT。" >&2
  exit 1
fi
docker compose "${COMPOSE_FILES[@]}" up -d
for _ in {1..30}; do
  if curl -fsS --max-time 1 "${EMQX_ADMIN_URL:-http://127.0.0.1:18083}/status" >/dev/null 2>&1; then break; fi
  sleep 1
done
python3 "$DEPLOY_DIR/prepare_p0_broker.py" --output "$RUNTIME_DIR/emqx-p0" --provision
start_mysql

JAVA_BIN="$RUNTIME_DIR/jdk17/usr/lib/jvm/java-17-openjdk-amd64/bin/java"
FLASK_PYTHON="$RUNTIME_DIR/flask-venv/bin/python"
DETECTOR_PYTHON="$RUNTIME_DIR/detector-env/bin/python"
NODE_BIN="$(command -v node)"
BACKEND_JAR="$(python3 "$DEPLOY_DIR/stage_backend.py")"
DETECTOR_RELEASE="$(python3 "$DEPLOY_DIR/stage_detector.py")"
GATEWAY_RELEASE="$(python3 "$DEPLOY_DIR/stage_gateway.py")"

start_process backend "$PROJECT_DIR" \
  env -u DEBUG -u MQTT_USERNAME -u MQTT_PASSWORD -u RAILWAY_EMQX_COOKIE -u EMQX_DASHBOARD_PASSWORD \
  "$JAVA_BIN" -jar "$BACKEND_JAR"

start_process flask "$GATEWAY_RELEASE" \
  env -u DB_URL -u DB_USERNAME -u DB_PASSWORD -u MQTT_USERNAME -u MQTT_PASSWORD \
    -u NOTIFY_WEBHOOK_URL -u NOTIFY_WEBHOOK_KEY -u SMS_ACCESS_KEY_ID -u SMS_ACCESS_KEY_SECRET -u SMS_SIGN_NAME -u SMS_TEMPLATE_CODE -u SMS_RECIPIENTS -u SMS_TEMPLATE_PARAMS_JSON \
    -u EVIDENCE_SERVICE_KEY \
    -u MQTT_BACKEND_USERNAME -u MQTT_BACKEND_PASSWORD -u RAILWAY_EMQX_COOKIE -u EMQX_DASHBOARD_PASSWORD \
    FLASK_HOST="${FLASK_HOST:-127.0.0.1}" FLASK_PORT="${FLASK_PORT:-5000}" \
    RAILWAY_PROJECT_ROOT="$PROJECT_DIR" DETECTOR_CODE_ROOT="$DETECTOR_RELEASE" \
  "$FLASK_PYTHON" -m gunicorn --no-control-socket --workers 1 --worker-class gthread --threads 80 --timeout 30 --graceful-timeout 15 --bind "${FLASK_HOST:-127.0.0.1}:${FLASK_PORT:-5000}" app:app

start_process frontend "$PROJECT_DIR/web-vue" \
  env -u DB_URL -u DB_USERNAME -u DB_PASSWORD -u MQTT_USERNAME -u MQTT_PASSWORD \
    -u NOTIFY_WEBHOOK_URL -u NOTIFY_WEBHOOK_KEY -u SMS_ACCESS_KEY_ID -u SMS_ACCESS_KEY_SECRET -u SMS_SIGN_NAME -u SMS_TEMPLATE_CODE -u SMS_RECIPIENTS -u SMS_TEMPLATE_PARAMS_JSON \
    -u EVIDENCE_SERVICE_KEY \
    -u MQTT_BACKEND_USERNAME -u MQTT_BACKEND_PASSWORD -u PREVIEW_SERVICE_KEY \
    -u RAILWAY_EMQX_COOKIE -u EMQX_DASHBOARD_PASSWORD -u MQTT_SERVER_KEY \
  "$NODE_BIN" "$PROJECT_DIR/web-vue/node_modules/vite/bin/vite.js" --host 127.0.0.1

if [[ "$WITH_DEMO" == true ]]; then
  FFMPEG_BIN="$RUNTIME_DIR/detector-env/lib/python3.8/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux64-v4.2.2"
  DEMO_VIDEO="${P0_DEMO_VIDEO:-$RUNTIME_DIR/smoke-cow-short.mp4}"
  if [[ ! -x "$FFMPEG_BIN" || ! -f "$DEMO_VIDEO" ]]; then
    echo "缺少本机样例视频或 FFmpeg，不能启动演示流。" >&2
    exit 1
  fi
  start_process demo_stream "$PROJECT_DIR" env -i PATH="$PATH" \
    "$FFMPEG_BIN" -hide_banner -loglevel warning -nostats -nostdin -re -stream_loop -1 -i "$DEMO_VIDEO" \
    -c copy -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/p0_demo
fi

if [[ "$WITH_DETECTOR" == true ]]; then
  mkdir -p "$RUNTIME_DIR/config/yolov5" "$RUNTIME_DIR/config/matplotlib" "$RUNTIME_DIR/cache" "$RUNTIME_DIR/detector-output"
  DETECTOR_RELEASE="$(python3 "$DEPLOY_DIR/stage_detector.py")"
  DETECTOR_WEIGHT="$(python3 - "$PROJECT_DIR/RailwayDetector" "${RAILWAY_MODEL_PATH:-./models/best1030.pt}" <<'PYCODE'
from pathlib import Path
import sys
path=Path(sys.argv[2]);print((path if path.is_absolute() else Path(sys.argv[1])/path).resolve())
PYCODE
)"
  start_process detector "$DETECTOR_RELEASE" \
    env -u DB_URL -u DB_USERNAME -u DB_PASSWORD -u MQTT_BACKEND_USERNAME -u MQTT_BACKEND_PASSWORD \
    -u NOTIFY_WEBHOOK_URL -u NOTIFY_WEBHOOK_KEY -u SMS_ACCESS_KEY_ID -u SMS_ACCESS_KEY_SECRET -u SMS_SIGN_NAME -u SMS_TEMPLATE_CODE -u SMS_RECIPIENTS -u SMS_TEMPLATE_PARAMS_JSON \
    -u PREVIEW_SERVICE_KEY -u RAILWAY_EMQX_COOKIE -u EMQX_DASHBOARD_PASSWORD -u MQTT_SERVER_KEY \
    YOLOV5_CONFIG_DIR="$RUNTIME_DIR/config/yolov5" \
    XDG_CONFIG_HOME="$RUNTIME_DIR/config" XDG_CACHE_HOME="$RUNTIME_DIR/cache" \
    MPLCONFIGDIR="$RUNTIME_DIR/config/matplotlib" \
    RAILWAY_DEVICE="${RAILWAY_DEVICE:-cpu}" RAILWAY_MODEL_PATH="$DETECTOR_WEIGHT" PYTHONDONTWRITEBYTECODE=1 \
    MQTT_HOST="${MQTT_HOST:-127.0.0.1}" MQTT_PORT="${MQTT_PORT:-1883}" \
    DETECTOR_OUTPUT_DIR="$RUNTIME_DIR/detector-output" \
    "$DETECTOR_PYTHON" ui.py
fi

start_process guardian "$PROJECT_DIR" python3 "$DEPLOY_DIR/guardian.py" --root "$PROJECT_DIR"
echo "启动命令已完成。运行 deploy/status.sh 查看健康状态。"
