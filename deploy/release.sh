#!/usr/bin/env bash
set -euo pipefail
cd /opt/uptime-monitor

[ -d .venv ] || python3.11 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e .

set -a; . /etc/uptime-monitor.env; set +a
.venv/bin/alembic upgrade head

sudo systemctl restart uptime-api
sudo systemctl restart uptime-checker.timer