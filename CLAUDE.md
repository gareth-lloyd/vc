# Villa Collective

Rebuild of the legacy `ResSystem/` (.NET 7 + Blazor + SQL Server) villa-rental
reservation platform as a **Django REST API + React (Vite + TypeScript) SPA**.
Per-stack details live in `django_res/CLAUDE.md` and `frontend/CLAUDE.md`;
this file stays principles-only.

## Principles

1. **TDD — red / green / refactor.** Failing test first, simplest pass, then
   refactor. Not chasing line coverage — chasing 100% of _important_ logic;
   when in doubt, write the test.

2. **Off-the-shelf over bespoke.** Established libraries (DRF, `django-filter`,
   `factory-boy`, `React Query`, `Zod`, `react-hook-form`, …) before custom
   abstractions. If you find yourself writing a framework, stop.

3. **KISS.** Prefer boring. Three duplicated lines beats a premature
   abstraction; an explicit `if` beats a strategy pattern.

4. **Linting from day one.** Backend: `ruff` (format + lint) + `mypy`;
   frontend: `eslint` + `prettier` + `tsc --noEmit`. No "we'll add it later."

5. **No soft delete.** No `SoftDeleteModel` / `deleted_at`. Lifecycle via a
   `status` enum, an `is_active` bool, an `archived_at` timestamp, or a hard
   delete with an `AuditLog` trail (canonical pattern:
   `accounts.Contact.merge`).

## Quality gate (non-negotiable)

Before any commit: backend tests (`pytest`) + lint/typecheck (`ruff check`,
`ruff format --check`, `mypy`); frontend tests (`vitest`) + lint/typecheck
(`eslint`, `prettier --check`, `tsc --noEmit`). Enforced by `pre-commit`
hooks (Python) and `husky` + `lint-staged` (JS). Never bypass with
`--no-verify` unless explicitly authorised by a human; if a hook fails, fix
the underlying problem.

## Repo layout

- `django_res/` — Django REST API, including the `data_migration/` package
  that ports the legacy SQL Server dump into Postgres. See
  `django_res/CLAUDE.md` and `django_res/data_migration/CUTOVER.md`.
- `frontend/` — Vite + React + TypeScript SPA.
- `django_res_design/` — detailed design specs (models, REST surface,
  workflows). Start at `django_res_design/INDEX.md`.
- `ResSystem/` — **read-only** legacy .NET app; source of truth for behaviour
  we're reproducing. Do not modify.
- `investigation/` — ad-hoc investigation notes.

## Tooling

- **Python:** `uv` (`uv sync`, `uv run …`, `uv add …`). **Node:** npm.
  **DB:** PostgreSQL via `docker compose`.
- **MCP servers** (`.claude/settings.json`): `context7` (library docs),
  `postgres` (schema introspection), `playwright` (browser FE checks).
- **Git worktrees** live in a sibling directory, never nested in the repo:
  `git worktree add -b feat/<slug> ../villacollective-worktrees/<slug> HEAD`
  (keeps the second checkout out of lint/test walks and `git status`).
  **Always edit through the worktree path** — main-repo paths land changes on
  the wrong branch.

## Working principles for agents

- Read `django_res_design/INDEX.md` before designing new backend models or
  endpoints — the spec is detailed and authoritative.
- Before touching `django_res/data_migration/`, read its `CUTOVER.md`; the
  package is the executable legacy → Postgres spec and must stay idempotent.
- When the spec and code disagree, surface the disagreement to the user; do
  not silently choose one side.
- Prefer small, incremental, test-backed commits over large landings.
- If a task seems to require breaking the quality gate (skipping tests,
  disabling a lint rule), stop and ask.
- **Keep your context window lean.** Token-efficient test invocations are
  documented per stack (`django_res/CLAUDE.md` §Tests, `frontend/CLAUDE.md`
  §Testing). For large outputs of any kind, capture only what you need:
  `git --no-pager diff --stat` before a full diff and scope diffs to a path
  (`git diff -- <path>`); prefer the Read tool with a line range over `cat`ing
  a large file (a single design doc can be several thousand tokens).
