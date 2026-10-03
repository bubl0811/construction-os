#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
snapshot="${1:?Pass the snapshot directory}"
snapshot="$(realpath "${snapshot}")"
(cd "${snapshot}" && sha256sum -c database.sha256)
docker compose -f compose.staging.yaml run --rm --no-deps -T \
  -v "${snapshot}:/backup:ro" -v "$PWD/scripts:/maintenance:ro" --user 0:0 --cap-add DAC_READ_SEARCH api \
  python /maintenance/storage_backup.py restore /backup/documents /tmp/restored-documents
restore_name="construction-restore-$(date +%s)-${RANDOM}"
trap 'docker rm -f "${restore_name}" >/dev/null 2>&1 || true' EXIT
# Disposable DB; no production hostname, volumes or credentials are used.
docker run --name "${restore_name}" -d --network none -e POSTGRES_HOST_AUTH_METHOD=trust postgres:16-alpine >/dev/null
for attempt in {1..30}; do
  if docker exec "${restore_name}" pg_isready -U postgres >/dev/null 2>&1; then break; fi
  sleep 1
done
docker exec -i "${restore_name}" pg_restore --exit-on-error --no-owner -U postgres -d postgres < "${snapshot}/database.dump"
docker exec "${restore_name}" psql -v ON_ERROR_STOP=1 -U postgres -d postgres -c 'SELECT count(*) AS restored_projects FROM projects; SELECT count(*) AS restored_documents FROM documents;'
echo 'Database restored successfully in a disposable container; PDF files restored and digests verified.'
