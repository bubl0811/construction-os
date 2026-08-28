#!/usr/bin/env bash

set -Eeuo pipefail

readonly APP_DIR="${CONSTRUCTION_OS_DEPLOY_DIR:-/opt/construction-os}"
readonly COMPOSE_FILE="compose.staging.yaml"
readonly PUBLIC_HEALTH_URL="https://185-143-145-25.sslip.io/api/v1/health"

ensure_server_dependencies() {
  if command -v docker >/dev/null 2>&1 \
    && docker compose version >/dev/null 2>&1 \
    && command -v openssl >/dev/null 2>&1; then
    systemctl enable --now docker
    return
  fi

  if [[ "$(id -u)" -ne 0 ]] || ! command -v apt-get >/dev/null 2>&1; then
    echo "Automatic dependency installation requires root on Debian or Ubuntu." >&2
    exit 1
  fi

  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install --yes ca-certificates curl openssl

  if ! command -v docker >/dev/null 2>&1 \
    || ! docker compose version >/dev/null 2>&1; then
    # shellcheck disable=SC1091
    . /etc/os-release
    case "${ID:-}" in
      debian | ubuntu) ;;
      *)
        echo "Automatic Docker installation supports Debian and Ubuntu only." >&2
        exit 1
        ;;
    esac

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://download.docker.com/linux/${ID}/gpg" \
      -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
      >/etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install --yes \
      docker-ce \
      docker-ce-cli \
      containerd.io \
      docker-buildx-plugin \
      docker-compose-plugin
  fi

  systemctl enable --now docker
}

ensure_server_dependencies
cd "${APP_DIR}"

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
CONSTRUCTION_OS_DOCUMENT_STORAGE_PATH=/var/lib/construction-os/documents
CONSTRUCTION_OS_MAX_DOCUMENT_SIZE_MB=200
CONSTRUCTION_OS_DOCUMENT_UPLOAD_TOKEN_EXPIRE_MINUTES=10
CONSTRUCTION_OS_PUBLIC_API_URL=https://185-143-145-25.sslip.io/api/v1
CONSTRUCTION_OS_CORS_ALLOWED_ORIGINS=https://construction-os-dashboard.hlpumg.chatgpt.site
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

if grep -q '^CONSTRUCTION_OS_MAX_DOCUMENT_SIZE_MB=' .env; then
  sed -i 's/^CONSTRUCTION_OS_MAX_DOCUMENT_SIZE_MB=.*/CONSTRUCTION_OS_MAX_DOCUMENT_SIZE_MB=200/' .env
else
  echo 'CONSTRUCTION_OS_MAX_DOCUMENT_SIZE_MB=200' >>.env
fi
if ! grep -q '^CONSTRUCTION_OS_DOCUMENT_STORAGE_PATH=' .env; then
  echo 'CONSTRUCTION_OS_DOCUMENT_STORAGE_PATH=/var/lib/construction-os/documents' >>.env
fi
if ! grep -q '^CONSTRUCTION_OS_DOCUMENT_UPLOAD_TOKEN_EXPIRE_MINUTES=' .env; then
  echo 'CONSTRUCTION_OS_DOCUMENT_UPLOAD_TOKEN_EXPIRE_MINUTES=10' >>.env
fi
if ! grep -q '^CONSTRUCTION_OS_PUBLIC_API_URL=' .env; then
  echo 'CONSTRUCTION_OS_PUBLIC_API_URL=https://185-143-145-25.sslip.io/api/v1' >>.env
fi
if grep -q '^CONSTRUCTION_OS_CORS_ALLOWED_ORIGINS=' .env; then
  sed -i 's|^CONSTRUCTION_OS_CORS_ALLOWED_ORIGINS=.*|CONSTRUCTION_OS_CORS_ALLOWED_ORIGINS=https://construction-os-dashboard.hlpumg.chatgpt.site|' .env
else
  echo 'CONSTRUCTION_OS_CORS_ALLOWED_ORIGINS=https://construction-os-dashboard.hlpumg.chatgpt.site' >>.env
fi

chmod 600 .env

docker compose -f "${COMPOSE_FILE}" build --pull api
docker compose -f "${COMPOSE_FILE}" up -d db redis
docker compose -f "${COMPOSE_FILE}" run --rm api alembic upgrade head
docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans

api_is_healthy=false
for _ in $(seq 1 18); do
  if docker compose -f "${COMPOSE_FILE}" exec -T api \
    python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"; then
    api_is_healthy=true
    break
  fi
  sleep 5
done

if [[ "${api_is_healthy}" != true ]]; then
  docker compose -f "${COMPOSE_FILE}" ps
  docker compose -f "${COMPOSE_FILE}" logs --tail=100 api
  echo "Construction OS API did not become healthy in time." >&2
  exit 1
fi

for _ in $(seq 1 24); do
  if curl --fail --silent --show-error --max-time 10 "${PUBLIC_HEALTH_URL}" >/dev/null; then
    docker compose -f "${COMPOSE_FILE}" ps
    docker compose -f "${COMPOSE_FILE}" exec -T api sh -c '
      set -- $(df -kP /var/lib/construction-os/documents | tail -n 1)
      printf "Document storage: total=%sKB used=%sKB available=%sKB usage=%s\n" "$2" "$3" "$4" "$5"
      du -sh /var/lib/construction-os/documents 2>/dev/null | awk "{print \"Stored documents: \" \$1}"
    '
    echo "Maximum PDF upload size: 200 MB."
    echo "Construction OS deployment is healthy at ${PUBLIC_HEALTH_URL}."
    exit 0
  fi
  sleep 5
done

docker compose -f "${COMPOSE_FILE}" ps
docker compose -f "${COMPOSE_FILE}" logs --tail=100 caddy
echo "Construction OS HTTPS endpoint did not become healthy in time." >&2
exit 1
