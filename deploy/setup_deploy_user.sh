#!/usr/bin/env bash
# One-time VPS setup for GitHub Actions deploys. Run as root on the server:
#   bash setup_deploy_user.sh "<public key of the GitHub Actions deploy key>"
# Creates a non-root "deploy" user that owns the app folders, may only restart
# the API service via sudo, and runs the API itself.
set -euo pipefail

PUBKEY="${1:?usage: $0 \"ssh-ed25519 AAAA... github-actions@tradecall-vps\"}"
WEB_DIR=/var/www/tradecall

id deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/bash deploy

install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
grep -qxF "$PUBKEY" /home/deploy/.ssh/authorized_keys 2>/dev/null \
  || echo "$PUBKEY" >> /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys

mkdir -p "$WEB_DIR"
chown -R deploy:deploy /opt/tradecall "$WEB_DIR"

cat > /etc/sudoers.d/deploy <<'SUDO'
deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart tradecall-api, /usr/bin/systemctl is-active tradecall-api
SUDO
chmod 440 /etc/sudoers.d/deploy
visudo -cf /etc/sudoers.d/deploy

# Run the API as the deploy user (matches deploy/tradecall-api.service)
UNIT=/etc/systemd/system/tradecall-api.service
grep -q '^User=deploy' "$UNIT" || sed -i '/^\[Service\]/a User=deploy\nGroup=deploy' "$UNIT"
systemctl daemon-reload
systemctl restart tradecall-api
sleep 3
systemctl is-active tradecall-api
curl -fsS http://127.0.0.1:8000/health && echo
echo "deploy user ready"
