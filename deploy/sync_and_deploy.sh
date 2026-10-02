#!/bin/bash
# Deploys/updates the bot code on the VPS. Safe to re-run any time you want
# to push a code change -- it never touches credentials or the ledger.
#
#   deploy/sync_and_deploy.sh <droplet-ip>
set -euo pipefail
IP="${1:?Usage: sync_and_deploy.sh <droplet-ip>}"
REMOTE="root@$IP"

rsync -avz --delete \
  --exclude='.venv' --exclude='.git' --exclude='__pycache__' \
  --exclude='logs' --exclude='*.pem' --exclude='.env' \
  --exclude='ledger.db*' --exclude='*.pyc' \
  ./ "$REMOTE:/opt/kalshi/"

ssh "$REMOTE" bash -s <<'EOF'
set -euo pipefail
cd /opt/kalshi
python3 -m venv --upgrade-deps .venv 2>/dev/null || python3 -m venv .venv
./.venv/bin/pip install --upgrade pip -q
./.venv/bin/pip install -r requirements.txt -q
mkdir -p logs
cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now kalshi-bot.service kalshi-dashboard.service kalshi-watchdog.timer
chown -R kalshi:kalshi /opt/kalshi
EOF

echo "Code deployed to $IP:/opt/kalshi."
echo "If this is the first deploy, credentials still need to be pushed -- run deploy/push_credentials.sh $IP"
