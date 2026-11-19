#!/usr/bin/env bash
set -u

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"
RUNTIME_DIR="$PROJECT_DIR/workspace/runtime"

if [[ -f "$DEPLOY_DIR/.env.p0" ]]; then
  set -a
  source "$DEPLOY_DIR/.env.p0"
  set +a
  COMPOSE_FILES=(-f "$DEPLOY_DIR/compose.yaml")
  [[ -z "${MQTT_CA_FILE:-}" ]] || COMPOSE_FILES+=(-f "$DEPLOY_DIR/compose.p0-tls.yaml")
  docker compose "${COMPOSE_FILES[@]}" ps
else
  docker ps --filter name=railway- --format '{{.Names}} {{.Status}}'
fi

check_http() {
  local name="$1"
  local url="$2"
  local code
  code="$(curl -sS --max-time 3 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
  printf '%-10s %s (%s)\n' "$name" "$url" "${code:-无法连接}"
}

check_http frontend http://127.0.0.1:3000/
check_http flask http://127.0.0.1:5000/api/health
check_http emqx http://127.0.0.1:18083/

MYSQL_BASE_VALUE="/data/anaconda3"
if [[ -f "$DEPLOY_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$DEPLOY_DIR/.env"
  set +a
  MYSQL_BASE_VALUE="${MYSQL_BASE:-/data/anaconda3}"
fi
check_http backend "http://127.0.0.1:${SERVER_PORT:-8080}/api/health/ready"
if [[ -f "$RUNTIME_DIR/guardian-status.json" ]]; then
  python3 - "$RUNTIME_DIR/guardian-status.json" <<'PY'
import json,sys,time
data=json.load(open(sys.argv[1]));print('guardian   '+('reporting' if time.time()-data['at']<15 else 'report expired'));print(json.dumps(data['services'],ensure_ascii=False))
PY
fi
if "$MYSQL_BASE_VALUE/bin/mysqladmin" --protocol=socket --socket="$RUNTIME_DIR/mysql/run/mysql.sock" -uroot ping >/dev/null 2>&1; then
  echo "mysql      healthy (127.0.0.1:3307)"
else
  echo "mysql      unavailable"
fi
