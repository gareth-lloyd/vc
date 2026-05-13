# Villa Collective

Rebuild of the legacy `ResSystem/` (.NET 7 + Blazor + SQL Server) villa-rental
reservation platform as a **Django REST API + React (Vite + TypeScript) SPA**.

This file is the project's north star for agentic work. Per-stack details live
in `django_res/CLAUDE.md` and the frontend's `CLAUDE.md` (created when those
trees are scaffolded). Keep this file principles-only.

## Principles

1. **TDD — red / green / refactor.** Write the failing test first, make it
   pass with the simplest thing that works, then refactor. We are *not*
   chasing 100% line coverage; we are chasing 100% of *important* logic.
   That's a judgement call — when in doubt, write the test. TDD is how we
   advance carefully and reliably, one small increment at a time.

2. **Off-the-shelf over bespoke.** Reach for established libraries (DRF,
   `django-filter`, `dj-rest-auth` / `django-allauth`, `factory-boy`,
   `React Query`, `Zod`, `react-hook-form`, etc.) before writing custom
   abstractions. If you find yourself writing a framework, stop. This is a
   simple project that benefits from simple, well-trodden libraries.

3. **KISS.** Excessive cleverness is actively discouraged. Simple solutions
   for simple problems. Prefer boring. Three duplicated lines beats a
   premature abstraction; a flat function beats a class hierarchy; an
   explicit `if` beats a strategy pattern.

4. **Linting from day one.** No "we'll add it later."
   - **Backend:** `ruff` (format + lint) and `mypy` configured in
     `pyproject.toml` before the first real commit of Django code.
   - **Frontend:** `eslint` + `prettier` + `tsc --noEmit` configured before
     the first real commit of React code.

## Quality gate (non-negotiable)

Before any commit:

- All backend tests pass (`pytest`).
- All frontend tests pass (`vitest`).
- All backend lint + typecheck pass (`ruff check`, `ruff format --check`, `mypy`).
- All frontend lint + typecheck pass (`eslint`, `prettier --check`, `tsc --noEmit`).

Enforced locally by:

- **Python side:** `pre-commit` hooks (`.pre-commit-config.yaml`).
- **JS side:** `husky` + `lint-staged` on the `pre-commit` git hook.

Never bypass with `--no-verify` unless explicitly authorised by a human in
the loop. If a hook fails, fix the underlying problem.

## Repo layout

- `django_res/` — Django REST API. Models, services, DRF surface, and the
  `data_migration/` package that ports the legacy SQL Server dump into
  Postgres. See `django_res/CLAUDE.md` for backend specifics and
  `django_res/data_migration/CUTOVER.md` for the legacy-cutover playbook.
- `frontend/` — Vite + React + TypeScript SPA.
- `django_res_design/` — Detailed design specs for the rebuild: models,
  conventions, REST surface, workflows, departures from legacy. Start at
  `django_res_design/INDEX.md`.
- `ResSystem/` — **Read-only** legacy .NET app. Reference only; do not
  modify. Source of truth for behaviour we're reproducing.
- `investigation/` — ad-hoc investigation notes.

## Tooling

- **Python:** managed by `uv` (`uv sync`, `uv run …`, `uv add …`).
- **Node:** npm (or pnpm) for the frontend.
- **DB:** PostgreSQL, run locally via `docker compose`.
- **MCP servers wired for this project** (see `.claude/settings.json`):
  `context7` (library docs), `postgres` (schema introspection),
  `playwright` (browser-driven FE checks).

## Working principles for agents

- Read `django_res_design/INDEX.md` before designing new backend models or
  endpoints — the spec is detailed and authoritative.
- When the spec and code disagree, surface the disagreement to the user;
  do not silently choose one side.
- Prefer small, incremental, test-backed commits over large landings.
- If a task seems to require breaking the quality gate (e.g. skipping
  tests, disabling a lint rule), stop and ask.
