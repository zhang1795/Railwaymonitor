#!/usr/bin/env bash
set -u

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"
RUNTIME_DIR="$PROJECT_DIR/workspace/runtime"

docker compose -f "$DEPLOY_DIR/compose.yaml" ps

check_http() {
  local name="$1"
  local url="$2"
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
  printf '%-10s %s (%s)\n' "$name" "$url" "${code:-无法连接}"
}

check_http frontend http://127.0.0.1:3000/
check_http backend http://127.0.0.1:8080/api/statistics/overview
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
if "$MYSQL_BASE_VALUE/bin/mysqladmin" --protocol=socket --socket="$RUNTIME_DIR/mysql/run/mysql.sock" -uroot ping >/dev/null 2>&1; then
  echo "mysql      healthy (127.0.0.1:3307)"
else
  echo "mysql      unavailable"
fi
