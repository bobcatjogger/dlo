.PHONY: install test lint format typecheck db-init

VENV := .venv/bin
PY := $(VENV)/python
PIP := $(VENV)/pip

install:
	@command -v python3.13 >/dev/null && PY=python3.13 || PY=python3; \
	$$PY -m venv .venv
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"

test:
	$(PY) -m pytest

lint:
	$(VENV)/ruff check src tests
	$(VENV)/ruff format --check src tests

format:
	$(VENV)/ruff format src tests

typecheck:
	$(VENV)/mypy

db-init:
	$(PY) -m codez init-db
