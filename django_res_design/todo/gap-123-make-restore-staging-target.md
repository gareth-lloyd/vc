# GAP-123 — `make dump-legacy` / `make restore-staging`: script the restore recipe

**Severity:** gap (ops; the recipe is proven once and lives only in prose).

**Status:** ⬜ filed 2026-09-22, spun off GAP-120 step 4.

**Source:** GAP-120. The legacy database reached staging by a hand-run
sequence that worked on the second attempt (the first shipped a dump with an
incomplete migration record — the damaged-venv trap in GAP-120 step 4).
Everything in it is deterministic
and repeatable; only the two secrets (the Render database URL and the
dashboard's IP allow-list) need a human. Production cutover (CUTOVER §8) will
run the same steps against `villacollective-images-prod` and the production
database, so the script pays for itself on its first re-use.

## The recipe as run (from GAP-120)

1. `reconcile_legacy --integrations` exits 0 against the local database.
2. `createdb -T villacollective vc_scrub`; set every `accounts_user.password`
   to an unusable value; `pg_dump -Fc --no-owner --no-acl` to
   `~/villacollective-legacy/db-dumps/<date>-<sha>-scrubbed.dump` (mode 600);
   `dropdb vc_scrub`. All via `docker exec villacollective-db …`.
3. Verify the dump's `django_migrations` count equals
   `showmigrations --plan | wc -l` from a clean venv.
4. Human: suspend the web service; add a `/32` to the DB's allow-list; export
   the external URL as `STAGING_DB_URL`.
5. `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` then
   `pg_restore --no-owner --no-acl --exit-on-error`, via `docker exec -i`.
6. Verify counts (images / properties / migrations) match local.
7. Human: remove the `/32`; resume the service; deploy (expect "No migrations
   to apply"); `ensure_staff_superusers` (GAP-122).

## Proposal

Two targets in the root `Makefile`, wrapping a script under `scripts/`:

- **`make dump-legacy`** — steps 1–3. Refuses if reconcile fails or the
  migration count disagrees (the only guard against the damaged-venv trap;
  a CI check was considered and dropped 2026-09-22 unless it recurs).
  Prints the dump path and its counts.
- **`make restore-staging DUMP=<path>`** — steps 5–6, reading
  `STAGING_DB_URL` from the environment (never from a file, never echoed).
  Refuses unless the URL host looks like a Render external hostname, prints
  "suspend the service and add your /32 first — continue? [y/N]", and ends by
  printing the counts and reminding the operator to remove the rule.
- A `TARGET=production` variant is the same script with a different URL var;
  add it when CUTOVER §8 is imminent, not before.

Keep it shell, not a management command: it drives `docker exec` and needs no
Django. Document both targets in `CUTOVER.md` §8 and replace the prose in
GAP-120 with a pointer.

## Acceptance

- One command produces a scrubbed, migration-complete dump; one command
  restores it; neither prints a secret.
- The dump target refuses a damaged venv (migration count ≠ clean plan).
- `CUTOVER.md` §8 references the targets.
