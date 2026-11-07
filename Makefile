.PHONY: test lint format migrate up

PYTHON := .venv\Scripts\python.exe

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .

migrate:
	$(PYTHON) -m alembic upgrade head

up:
	docker compose up --build


VM_USER  ?= deploy
SSH_OPTS ?=
VM_DIR    = /opt/uptime-monitor
SSH_CMD   = ssh $(SSH_OPTS) $(VM_USER)@$(VM_HOST)

.PHONY: sync bootstrap release deploy
sync:
	rsync -az --delete -e "ssh $(SSH_OPTS)" app monitor migrations grafana deploy alembic.ini pyproject.toml README.md $(VM_USER)@$(VM_HOST):$(VM_DIR)/

bootstrap: sync
	$(SSH_CMD) 'bash $(VM_DIR)/deploy/bootstrap.sh $(VM_HOST)'

release:
	$(SSH_CMD) 'bash $(VM_DIR)/deploy/release.sh'

deploy: sync release

