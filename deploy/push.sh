#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# Run FROM the local dev machine: ship the whole source tree (incl. .env and
# ML artifacts) to the server over SSH, then rebuild + restart there.
# One command, no arguments needed:
#
#     bash deploy/push.sh
#
# Override target if ever needed:
#     bash deploy/push.sh user@host /path/on/server
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

SERVER="${1:-root@42.96.56.55}"
APP_DIR="${2:-/root/ttk/AI-WC-Football}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Shipping $SRC"
echo "    ->  $SERVER:$APP_DIR"
ssh "$SERVER" "mkdir -p '$APP_DIR'"

# rsync the source up. .env IS included (gitignored, never on GitHub, but the
# server needs it). Caches / venv / node_modules / training data excluded.
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

echo "==> Building + restarting on the server ..."
# Run deploy.sh WITHOUT --update: it deploys the just-rsynced files (no git pull).
ssh "$SERVER" "cd '$APP_DIR' && bash deploy/deploy.sh"

echo ""
echo "════════════════════════════════════════════════"
echo "  ✅ Shipped + deployed to $SERVER:$APP_DIR"
echo "     UI: http://ttk2035.duckdns.org/"
echo "════════════════════════════════════════════════"
