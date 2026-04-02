#!/usr/bin/env bash
set -euo pipefail

# Quick production checks after deployment.
# Usage:
#   BASE_URL=https://your-domain.com ./scripts/healthcheck_prod.sh

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

echo "Checking ${BASE_URL}/ ..."
curl -fsS "${BASE_URL}/" >/dev/null

echo "Checking ${BASE_URL}/admin/login ..."
curl -fsS "${BASE_URL}/admin/login" >/dev/null

echo "Checking ${BASE_URL}/index?center_id=1 ..."
curl -fsS "${BASE_URL}/index?center_id=1" >/dev/null

echo "Health checks passed."
