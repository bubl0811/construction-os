#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
cd "${CONSTRUCTION_OS_DEPLOY_DIR:-/opt/construction-os}"
backup_root="${CONSTRUCTION_OS_BACKUP_DIR:?Set a backup directory outside deployment/storage}"
mkdir -p "${backup_root}"
backup_path="$(mktemp -d "${backup_root}/snapshot-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
compose=(docker compose -f compose.staging.yaml)
# Stop API writes so the database dump and PDF snapshot describe the same instant.
"${compose[@]}" stop api >&2
trap '"${compose[@]}" start api >/dev/null' EXIT
"${compose[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "${backup_path}/database.dump"
"${compose[@]}" run --rm --no-deps -T -v "${backup_path}:/backup" -v "$PWD/scripts:/maintenance:ro" --user 0:0 --cap-add DAC_READ_SEARCH api \
  python /maintenance/storage_backup.py backup /var/lib/construction-os/documents /backup/documents >&2
(cd "${backup_path}" && sha256sum database.dump > database.sha256)
printf '%s\n' "${backup_path}"
