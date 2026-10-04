#!/usr/bin/env bash
# Server-side deploy steps, run by GitHub Actions as the "deploy" user after the
# checkout in /opt/tradecall/brokerage-app-backend has been moved to the new commit.
set -euo pipefail

cd "$(dirname "$0")/.."

./venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt
./venv/bin/alembic upgrade head

sudo /usr/bin/systemctl restart tradecall-api

for _ in $(seq 1 15); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null; then
    echo "Deployed $(git rev-parse --short HEAD), API healthy"
    exit 0
  fi
  sleep 2
done
echo "API did not become healthy after restart" >&2
sudo /usr/bin/systemctl is-active tradecall-api || true
exit 1
