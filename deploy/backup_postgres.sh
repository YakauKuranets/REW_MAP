#!/usr/bin/env bash
set -euo pipefail

# Backup Postgres database (run inside db container)
#
# Требует: pg_dump (есть в образе postgres)
#
# По умолчанию пишет в /backups (см. volume в docker-compose).
# Можно переопределить BACKUP_DIR.

TS="$(date +%Y%m%d_%H%M%S)"
: "${BACKUP_DIR:=/backups}"
OUT="${BACKUP_DIR}/pgdump_${TS}.dump"

: "${POSTGRES_DB:=app}"
: "${POSTGRES_USER:=app}"
: "${PGPASSWORD:=}"

export PGPASSWORD

mkdir -p "${BACKUP_DIR}"
pg_dump -Fc -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -f "${OUT}"
echo "OK: ${OUT}"
