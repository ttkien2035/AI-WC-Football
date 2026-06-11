#!/usr/bin/env bash
# Run FROM the dev machine: sync code (incl. .env and ML artifacts) to the
# server over SSH, then run the remote deploy script.
#   bash deploy/push.sh user@YOUR_SERVER [/opt/wc2026]
set -euo pipefail

SERVER="${1:?usage: bash deploy/push.sh user@server [app_dir]}"
APP_DIR="${2:-/opt/wc2026}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Syncing $SRC -> $SERVER:$APP_DIR"
ssh "$SERVER" "mkdir -p '$APP_DIR'"
rsync -az --delete \
  --exclude '.git/' \
  --exclude 'node_modules/' \
  --exclude 'frontend/dist/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'backend/app/data/cache.sqlite' \
  --exclude 'backend/ml/data/' \
  "$SRC/" "$SERVER:$APP_DIR/"

echo "==> Running remote deploy ..."
ssh "$SERVER" "cd '$APP_DIR' && bash deploy/deploy.sh"
