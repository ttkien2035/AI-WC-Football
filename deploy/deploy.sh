#!/usr/bin/env bash
# Run ON the server (idempotent). Installs Docker if missing, then builds and
# starts the stack with production ports (UI :80, backend internal-only).
#   cd /opt/wc2026 && bash deploy/deploy.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

echo "==> App dir: $APP_DIR"

if [ ! -f .env ]; then
  echo "ERROR: .env not found in $APP_DIR — create it first:"
  echo "  FOOTBALL_API_KEY=your_key"
  echo "  ODDS_API_KEY=your_key   # optional"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker ..."
  curl -fsSL https://get.docker.com | sh
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose plugin missing (old Docker?). Update Docker."
  exit 1
fi

echo "==> Building + starting (prod ports) ..."
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build

echo "==> Waiting for backend health ..."
for i in $(seq 1 30); do
  if docker compose exec -T backend curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "==> Backend healthy."
    break
  fi
  sleep 2
done

docker compose ps
echo ""
echo "==> Done. UI:  http://$(hostname -I | awk '{print $1}')/"
echo "    Logs:      docker compose logs -f backend"
echo "    Stop:      docker compose down"
