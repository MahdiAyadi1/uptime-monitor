#!/usr/bin/env bash
set -euo pipefail
FQDN="${1:?usage: bootstrap.sh <fqdn>}"
cd /opt/uptime-monitor

# Grafana provisioning written for compose refers to host "db"; point it at localhost
grep -q ' db$' /etc/hosts || echo '127.0.0.1 db' | sudo tee -a /etc/hosts >/dev/null

for unit in uptime-api.service uptime-checker.service uptime-checker.timer; do
  sed "s/^User=deploy/User=$(id -un)/" "deploy/$unit" | sudo tee "/etc/systemd/system/$unit" >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable uptime-api uptime-checker.timer

sudo systemctl enable grafana-server

printf '%s {\n    reverse_proxy 127.0.0.1:8000\n}\n' "$FQDN" | sudo tee /etc/caddy/Caddyfile >/dev/null
sudo systemctl enable caddy
sudo systemctl restart caddy