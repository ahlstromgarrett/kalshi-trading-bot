#!/bin/bash
# One-time setup for a fresh Ubuntu 24.04 droplet. Run as root:
#   ssh root@<droplet-ip> 'bash -s' < deploy/provision.sh
set -euo pipefail

apt-get update
apt-get install -y python3-venv python3-pip rsync sqlite3 netcat-openbsd ufw

# Dedicated, unprivileged user to run the bot -- never run it as root.
id -u kalshi &>/dev/null || useradd --system --create-home --home-dir /opt/kalshi --shell /usr/sbin/nologin kalshi
mkdir -p /opt/kalshi
chown -R kalshi:kalshi /opt/kalshi

# Lock the firewall down to SSH only -- the dashboard binds 127.0.0.1 and is
# reached via an SSH tunnel, the bot makes outbound calls only, so nothing
# else needs to be open.
ufw allow OpenSSH
ufw --force enable

echo "Provisioning done. Next: run deploy/sync_and_deploy.sh from your laptop."
