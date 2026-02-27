#!/usr/bin/env bash
set -euo pipefail

# Restore Postgres dump (run inside db container)
# Usage:
#   /scripts/restore_postgres.sh /backups/pgdump_YYYYmmdd_HHMMSS.dump

DUMP="${1:-}"
if [ -z "${DUMP}" ]; then
  echo "Usage: $0 /path/to/pgdump.dump" >&2
  exit 2
fi

: "${POSTGRES_DB:=app}"
: "${POSTGRES_USER:=app}"
: "${PGPASSWORD:=}"

export PGPASSWORD

pg_restore -c --if-exists -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" "${DUMP}"
echo "OK: restored ${DUMP} into ${POSTGRES_DB}"
