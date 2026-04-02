#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db \
#   ./scripts/restore_postgres.sh ./backups/maestroyoga_YYYYMMDD_HHMMSS.dump

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required."
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <backup_file.dump>"
  exit 1
fi

BACKUP_FILE="$1"
if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "Backup file not found: ${BACKUP_FILE}"
  exit 1
fi

pg_restore --clean --if-exists --no-owner --no-privileges --dbname="${DATABASE_URL}" "${BACKUP_FILE}"
echo "Restore complete from: ${BACKUP_FILE}"
