#!/usr/bin/env bash
# Runs on the cPanel server after GitHub Actions has synced the code.
# Installs dependencies, applies migrations and restarts the Passenger app.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/tradecall-api}"
VENV="${VENV:-$HOME/virtualenv/tradecall-api/3.12}"

cd "$APP_DIR"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

pip install --quiet --disable-pip-version-check -r requirements.txt
alembic upgrade head

mkdir -p tmp
touch tmp/restart.txt
echo "Deployed $(cat REVISION 2>/dev/null || echo unknown) at $(date -u +%FT%TZ)"
