#!/usr/bin/env bash
set -euo pipefail
FQDN="${1:?usage: bootstrap.sh <fqdn>}"
cd /opt/uptime-monitor

# Grafana provisioning written for compose refers to host "db"; point it at localhost
grep -q ' db$' /etc/hosts || echo '127.0.0.1 db' | sudo tee -a /etc/hosts >/dev/null

sudo install -m 644 deploy/uptime-api.service deploy/uptime-checker.service deploy/uptime-checker.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable uptime-api uptime-checker.timer

sudo mkdir -p /etc/grafana/provisioning /etc/grafana/dashboards
sudo cp -r grafana/provisioning/. /etc/grafana/provisioning/
sudo cp -r grafana/dashboards/. /etc/grafana/dashboards/
sudo systemctl enable grafana-server
sudo systemctl restart grafana-server

printf '%s {\n    reverse_proxy 127.0.0.1:8000\n}\n' "$FQDN" | sudo tee /etc/caddy/Caddyfile >/dev/null
sudo systemctl enable caddy
sudo systemctl restart caddy