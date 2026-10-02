#!/bin/bash
# One-time (or whenever you rotate the key): pushes .env and the Kalshi
# private key to the VPS and locks them down to the kalshi service user
# only. Deliberately separate from sync_and_deploy.sh so a routine code
# push can never accidentally overwrite or re-transmit credentials.
#
#   deploy/push_credentials.sh <droplet-ip>
set -euo pipefail
IP="${1:?Usage: push_credentials.sh <droplet-ip>}"
REMOTE="root@$IP"

scp .env kalshi_private_key.pem "$REMOTE:/opt/kalshi/"
ssh "$REMOTE" '
  chown kalshi:kalshi /opt/kalshi/.env /opt/kalshi/kalshi_private_key.pem
  chmod 600 /opt/kalshi/.env /opt/kalshi/kalshi_private_key.pem
'
echo "Credentials pushed to $IP:/opt/kalshi and locked to 600, owned by kalshi."
