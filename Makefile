.PHONY: setup test lint typecheck dev-backend dev-frontend logs logs-backend logs-frontend hooks help

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

LOG_DIR := logs

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-16s %s\n", $$1, $$2}'

setup: ## Install all dependencies (backend, frontend, pre-commit hooks)
	cd django_res && uv sync
	cd frontend && npm ci
	uv tool install --force pre-commit
	pre-commit install --hook-type pre-commit --hook-type pre-push

hooks: ## Run all pre-commit hooks on all files
	pre-commit run --all-files
	pre-commit run --all-files --hook-stage pre-push

test: ## Run backend + frontend tests
	cd django_res && uv run pytest
	cd frontend && npm test -- --run

lint: ## Run backend + frontend lint + format + typecheck
	cd django_res && uv run ruff check
	cd django_res && uv run ruff format --check .
	cd django_res && uv run mypy .
	cd frontend && npm run lint
	cd frontend && npm run format:check
	cd frontend && npm run typecheck

dev-backend: ## Start the Django dev server (output mirrored to logs/django.log)
	@mkdir -p $(LOG_DIR)
	cd django_res && uv run python manage.py runserver 2>&1 | tee -a ../$(LOG_DIR)/django.log

dev-frontend: ## Start the Vite dev server (output mirrored to logs/vite.log)
	@mkdir -p $(LOG_DIR)
	cd frontend && npm run dev 2>&1 | tee -a ../$(LOG_DIR)/vite.log

logs: ## Tail both dev-server logs
	@mkdir -p $(LOG_DIR) && touch $(LOG_DIR)/django.log $(LOG_DIR)/vite.log
	tail -F $(LOG_DIR)/django.log $(LOG_DIR)/vite.log

logs-backend: ## Tail backend log
	@mkdir -p $(LOG_DIR) && touch $(LOG_DIR)/django.log
	tail -F $(LOG_DIR)/django.log

logs-frontend: ## Tail frontend log
	@mkdir -p $(LOG_DIR) && touch $(LOG_DIR)/vite.log
	tail -F $(LOG_DIR)/vite.log
