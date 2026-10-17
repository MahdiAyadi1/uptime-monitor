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
