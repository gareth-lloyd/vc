# GAP-121 — A damaged venv rewrote Django's contrib migrations; add a guard

**Severity:** gap (dev-infra; bit us once, cost a failed staging restore).

**Status:** ⬜ filed 2026-09-22, spun off GAP-120 step 4.

**Source:** GAP-120 close-out. On 2026-07-08 something deleted Django's own
migration files inside `django_res/.venv` (`django/contrib/{auth,admin,
contenttypes,sessions}/migrations/`) and regenerated a single `0001_initial`
per app. Every `migrate` since then recorded those four rows instead of the
stock eighteen, so the local database carried **64** `django_migrations` rows
where stock Django 5 has **78**. The first restore of that database to staging
failed at `contenttypes.0002` (`column "name" of relation
"django_content_type" does not exist`) because staging's clean venv wanted to
apply the fourteen migrations the local venv had never heard of.

Fix applied locally 2026-09-21: `uv sync --reinstall-package django`, schema
diffed against a stock-migrated scratch DB (only column order in
`auth_permission` differed), `migrate --fake` (14 FAKED), re-dump.

## What is still open

1. **Find the cause.** Candidates: a stray `makemigrations` with the venv's
   `site-packages` on a writable path plus a deleted `migrations/` folder; an
   editor "clean" action; a script that globbed `**/migrations/*.py`. Check the
   shell history and any `Makefile` / pre-commit / agent-run command around
   2026-07-08. The regenerated files carried the auto-generated header, so the
   tool was Django's own `makemigrations`.
2. **Check the other checkouts.** Every worktree under `.claude/worktrees/`
   has its own `.venv`; any created from a damaged copy, or that ran the same
   step, is suspect. `uv sync --reinstall-package django` is cheap — run it in
   all of them and compare `showmigrations --plan | wc -l` (78 at `bea09ed6`).
3. **A guard in CI and pre-commit.** Cheapest form: a test that asserts the
   migration plan length for the four contrib apps equals the stock count
   (`MigrationLoader(None).graph.nodes` filtered by app label — 12 auth, 3
   admin, 2 contenttypes, 1 sessions on Django 5.x). It fails the moment a venv
   is damaged, before any dump leaves the laptop. Django's version bump would
   change the count, which is the point: the number is checked, not assumed.
4. **Make the restore verify it too.** GAP-120's recipe already says "the
   migration count must equal `showmigrations --plan | wc -l` from a clean
   venv"; once GAP-123 turns the recipe into a `make` target, fold the check
   in so the target refuses to dump a database whose count disagrees.

## Acceptance

- The cause is written down here (or "not recoverable from history").
- Every checkout's venv passes the contrib-migration count check.
- A test fails on a venv whose contrib migrations are not stock.
