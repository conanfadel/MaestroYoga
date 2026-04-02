#!/usr/bin/env bash
set -euo pipefail

# Production deploy helper (run on server).
# Example:
#   APP_DIR=/opt/maestroyoga BRANCH=main ./scripts/deploy_prod.sh

APP_DIR="${APP_DIR:-/opt/maestroyoga}"
BRANCH="${BRANCH:-main}"

if [[ ! -d "${APP_DIR}/.git" ]]; then
  echo "Repository not found at ${APP_DIR}"
  exit 1
fi

cd "${APP_DIR}"

if [[ ! -f ".env.production" ]]; then
  echo ".env.production is missing in ${APP_DIR}"
  exit 1
fi

git fetch origin
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}"

docker compose -f docker-compose.prod.yml --env-file .env.production build app
docker compose -f docker-compose.prod.yml --env-file .env.production up -d

echo "Deployment complete."
docker compose -f docker-compose.prod.yml --env-file .env.production ps
