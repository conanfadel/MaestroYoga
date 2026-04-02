#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db \
#   BACKUP_DIR=./backups BACKUP_RETENTION_DAYS=14 \
#   ./scripts/backup_postgres.sh

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required."
  exit 1
fi

BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
OUT_FILE="${BACKUP_DIR}/maestroyoga_${TIMESTAMP}.dump"

mkdir -p "${BACKUP_DIR}"

pg_dump --format=custom --no-owner --no-privileges --dbname="${DATABASE_URL}" --file="${OUT_FILE}"
find "${BACKUP_DIR}" -type f -name "maestroyoga_*.dump" -mtime +"${BACKUP_RETENTION_DAYS}" -delete

echo "Backup created: ${OUT_FILE}"
