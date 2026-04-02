#!/usr/bin/env bash
set -euo pipefail

# Bootstrap Ubuntu server for MaestroYoga production deployment.
# Run as root on a fresh Ubuntu server:
#   sudo bash scripts/bootstrap_hetzner_ubuntu.sh

apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl gnupg lsb-release ufw nginx certbot python3-certbot-nginx \
  postgresql-client

# Install Docker engine + compose plugin.
install -m 0755 -d /etc/apt/keyrings
if [[ ! -f /etc/apt/keyrings/docker.asc ]]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
fi

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y --no-install-recommends docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable docker
systemctl start docker
systemctl enable nginx
systemctl start nginx

# Firewall baseline.
ufw allow OpenSSH
ufw allow "Nginx Full"
ufw --force enable

echo "Bootstrap complete."
echo "Next: create deployment user, clone repo, set .env.production, then docker compose up."
