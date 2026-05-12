.PHONY: setup test lint typecheck dev-backend dev-frontend hooks help

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

dev-backend: ## Start the Django dev server
	cd django_res && uv run python manage.py runserver

dev-frontend: ## Start the Vite dev server
	cd frontend && npm run dev
