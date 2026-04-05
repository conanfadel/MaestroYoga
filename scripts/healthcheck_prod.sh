#!/usr/bin/env bash
set -euo pipefail

# Quick production checks after deployment.
# Usage:
#   BASE_URL=https://your-domain.com ./scripts/healthcheck_prod.sh

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
# يطابق PUBLIC_INDEX_DEFAULT_PATH في backend/app/web_shared.py
PUBLIC_INDEX_PATH="${PUBLIC_INDEX_PATH:-/index?center_id=1}"

echo "Checking ${BASE_URL}/ ..."
curl -fsS "${BASE_URL}/" >/dev/null

echo "Checking ${BASE_URL}/admin/login ..."
curl -fsS "${BASE_URL}/admin/login" >/dev/null

echo "Checking ${BASE_URL}/health/ready ..."
curl -fsS "${BASE_URL}/health/ready" >/dev/null

echo "Checking ${BASE_URL}${PUBLIC_INDEX_PATH} ..."
curl -fsS "${BASE_URL}${PUBLIC_INDEX_PATH}" >/dev/null

echo "Health checks passed."
