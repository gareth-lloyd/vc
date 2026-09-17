# SMELL-025 — Flushed reference data is re-seeded per test, never restored

- **Severity:** 🟡 Smell (test-suite performance and fragility; no product impact)
- **Source:** the 2026-09-17 investigation of five `Country.DoesNotExist`
  failures on `main`, fixed in `955cec5a` (the autouse restore fixture now also
  covers tests that request `db` / `transactional_db` directly). This ticket is
  the performance follow-up raised afterwards. Related history: GAP-073 (done)
  note 3 — `test_dashboard_activity` flakes under `transaction=True` +
  `--reuse-db` + xdist.
- **Files:** `django_res/conftest.py` — `_ensure_seeded_reference_data` (:19),
  `_db_fixture_for` (:69), `_restore_seeded_reference_data` (:90);
  `django_res/test_conftest.py`; the `transaction=True` tests:
  `seeding/tests/test_dashboard_activity.py`,
  `seeding/tests/test_seed_dev_{calendar_density,stay_rules,pricing_shape,variety}.py`,
  `comms/tests/test_celery_dispatch.py`

## Problem

pytest-django's `transactional_db` teardown truncates every table, including
the rows seeded by data migrations: `Country` (`properties.0002`), the on-disk
`EmailTemplate` seeds, and `RoomAttribute`. With `--reuse-db` (on by default in
`addopts`), those rows are never restored. On 2026-09-17, **264 of 832**
`test_villacollective_*` databases on the local Postgres had zero countries,
including main's `gw1`–`gw13`.

`_restore_seeded_reference_data` only refills **before** each test, inside that
test's rolled-back transaction. So on an emptied worker DB:

- **Every** later DB test on that worker pays the full refill: a `bulk_create`
  of 249 countries, `sync_templates()` reading templates from disk, and
  `sync_room_attributes()`. Normally this is one `EXISTS` query per table.
- It comes back every run. The seeding tests empty the DB again when they
  finish, so `--create-db` only helps until the next run.
- Correctness depends entirely on the per-test backstop. Any migration-seeded
  table that `_ensure_seeded_reference_data` doesn't list stays silently empty
  on a reused DB. That is the bug class behind the 2026-09-17 failures, which
  surfaced only on workers that had run a seeding test.

The docstring is also stale: it cites `properties.0009` (now `0002`, after the
migration flatten) and says the only `transaction=True` tests live in
`seeding/tests/` (`comms/tests/test_celery_dispatch.py` is one too).

## Proposed fix

Make `_restore_seeded_reference_data` a yield fixture and refill again **after**
a transactional test:

```python
request.getfixturevalue(db_fixture)
_ensure_seeded_reference_data()
yield
if db_fixture == "transactional_db":
    _ensure_seeded_reference_data()  # post-flush; autocommits
```

`transactional_db` is requested from inside this fixture, so its finalizer (the
flush) runs first (LIFO). Our post-yield refill then runs outside any atomic
block, autocommits, and leaves the worker DB seeded for the next test and the
next `--reuse-db` run. Keep the pre-test refill as a cheap backstop. Fix the
stale docstring.

**Rejected:** `serialized_rollback=True` on the seeding tests. It is slower (the
whole DB is serialized and reloaded around each test) and opt-in per test, so
the next new transactional test would bring the problem back.

## Acceptance

- A regression test in `django_res/test_conftest.py` proves that reference rows
  survive a `transactional_db` test's teardown. Options: a test pair pinned to
  one worker (`xdist_group`, `--dist loadgroup` if needed) or a `pytester`
  in-process run. Pick whichever stays deterministic under `-n auto`.
- After a full `uv run pytest --create-db`, every `test_villacollective_gw*`
  DB still has 249 `properties_country` rows (check with `psql`).
- Full-suite wall-clock is no worse. Record before/after in the close-out banner.
- Quality gate green: `pytest`, `ruff check`, `ruff format --check`, `mypy`.

## Dependencies

None. Follows `955cec5a`.
