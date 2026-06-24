#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# One-shot server deploy. After cloning the repo, just run:
#
#     git clone https://github.com/ttkien2035/AI-WC-Football.git /opt/wc2026
#     cd /opt/wc2026 && bash deploy/deploy.sh
#
# Re-deploy after new commits:   bash deploy/deploy.sh --update
#
# Prerequisite: copy your local .env to the server FIRST (it is gitignored,
# never on GitHub):   scp .env user@YOUR_SERVER:/opt/wc2026/.env
#
# What it does (idempotent):
#   1. --update: git pull latest code
#   2. checks .env exists (you copy it manually — never committed)
#   3. installs Docker if missing
#   4. builds + starts the stack with production ports (UI :80, API internal)
#   5. waits for backend health and prints status
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"
echo "==> App dir: $APP_DIR"

# 1) optional self-update ------------------------------------------------
if [ "${1:-}" = "--update" ]; then
  if [ -d .git ]; then
    echo "==> Pulling latest code ..."
    git pull --ff-only
  else
    echo "WARN: not a git clone — skipping pull."
  fi
fi

# 2) .env (copied manually — gitignored, never on GitHub) -----------------
if [ ! -f .env ]; then
  echo "ERROR: $APP_DIR/.env not found."
  echo "Copy it from your local machine first (run on your LOCAL machine):"
  echo "    scp .env user@YOUR_SERVER:$APP_DIR/.env"
  echo "Then re-run:  bash deploy/deploy.sh"
  exit 1
fi
chmod 600 .env

# 3) Docker --------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker ..."
  curl -fsSL https://get.docker.com | sh
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: 'docker compose' plugin missing (Docker too old?). Update Docker."
  exit 1
fi

# 4) build + start (prod ports: only :80 published) ----------------------
echo "==> Building + starting ..."
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build

# 5) health --------------------------------------------------------------
echo "==> Waiting for backend health ..."
ok=""
for _ in $(seq 1 45); do
  if docker compose exec -T backend curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done
if [ -z "$ok" ]; then
  echo "ERROR: backend not healthy after 90s. Logs:"
  docker compose logs --tail 40 backend
  exit 1
fi

# 5b) seed NEW committed model artifacts into the persistent volume ----------
# models_data persists in-tournament RETRAINED models across deploys, so it
# SHADOWS artifacts that ship only in the freshly-built image. Copy any MISSING
# committed artifact into the volume (add-missing: never clobber a retrained
# one), then restart so the app re-reads. This is how new fitted artifacts
# (e.g. shot_form.json) reach prod without a volume wipe.
echo "==> Syncing new model artifacts into volume (add-missing) ..."
added=""
for f in backend/app/data/models/*; do
  [ -f "$f" ] || continue
  name="$(basename "$f")"
  if ! docker compose exec -T backend test -e "/app/app/data/models/$name" 2>/dev/null; then
    if docker compose cp "$f" "backend:/app/app/data/models/$name" 2>/dev/null; then
      echo "   + added $name"; added=1
    fi
  fi
done
# 5c) FORCE-sync locally-fit priors that are refreshed from git (NOT produced by
# the in-prod nightly retrain, so safe to overwrite — add-missing alone would
# leave a stale copy shadowing the updated commit, e.g. a re-centered corner_form).
FORCE_SYNC="corner_form.json shot_form.json"
for name in $FORCE_SYNC; do
  f="backend/app/data/models/$name"
  [ -f "$f" ] || continue
  if docker compose cp "$f" "backend:/app/app/data/models/$name" 2>/dev/null; then
    echo "   ↻ force-synced $name"; added=1
  fi
done
if [ -n "$added" ]; then
  echo "==> Artifacts changed — restarting backend ..."
  docker compose restart backend >/dev/null 2>&1 || true
  for _ in $(seq 1 30); do
    docker compose exec -T backend curl -sf http://localhost:8000/api/health >/dev/null 2>&1 && break
    sleep 2
  done
fi

docker compose ps
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo ""
echo "════════════════════════════════════════════════"
echo "  ✅ Deployed!  UI:  http://${IP:-<server-ip>}/"
echo "════════════════════════════════════════════════"
echo "  Logs:      docker compose logs -f backend"
echo "  Update:    bash deploy/deploy.sh --update"
echo "  Stop:      docker compose down"
echo "  Security:  see deploy/DEPLOY.md (SSH key, firewall)"
