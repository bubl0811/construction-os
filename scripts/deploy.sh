#!/usr/bin/env bash

set -Eeuo pipefail

readonly APP_DIR="${CONSTRUCTION_OS_DEPLOY_DIR:-/opt/construction-os}"
readonly COMPOSE_FILE="compose.staging.yaml"

cd "${APP_DIR}"

for required_command in docker openssl; do
  if ! command -v "${required_command}" >/dev/null 2>&1; then
    echo "Required command is not installed: ${required_command}" >&2
    exit 1
  fi
done

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  umask 077
  database_password="$(openssl rand -hex 24)"
  jwt_secret="$(openssl rand -hex 32)"
  cat >.env <<EOF
CONSTRUCTION_OS_ENVIRONMENT=staging
CONSTRUCTION_OS_SECRET_KEY=${jwt_secret}
CONSTRUCTION_OS_DATABASE_URL=postgresql+asyncpg://construction:${database_password}@db:5432/construction
CONSTRUCTION_OS_REDIS_URL=redis://redis:6379/0
CONSTRUCTION_OS_LOG_LEVEL=INFO
CONSTRUCTION_OS_POSTGRES_DB=construction
CONSTRUCTION_OS_POSTGRES_USER=construction
CONSTRUCTION_OS_POSTGRES_PASSWORD=${database_password}
CONSTRUCTION_OS_BIND_ADDRESS=0.0.0.0
CONSTRUCTION_OS_PORT=8000
EOF
elif ! grep -qx "CONSTRUCTION_OS_ENVIRONMENT=staging" .env; then
  echo "Existing .env is not a staging environment; deployment stopped." >&2
  exit 1
fi

chmod 600 .env

docker compose -f "${COMPOSE_FILE}" build --pull api
docker compose -f "${COMPOSE_FILE}" up -d db redis
docker compose -f "${COMPOSE_FILE}" run --rm api alembic upgrade head
docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans

for _ in $(seq 1 18); do
  if docker compose -f "${COMPOSE_FILE}" exec -T api \
    python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"; then
    docker compose -f "${COMPOSE_FILE}" ps
    echo "Construction OS deployment is healthy."
    exit 0
  fi
  sleep 5
done

docker compose -f "${COMPOSE_FILE}" ps
docker compose -f "${COMPOSE_FILE}" logs --tail=100 api
echo "Construction OS did not become healthy in time." >&2
exit 1
