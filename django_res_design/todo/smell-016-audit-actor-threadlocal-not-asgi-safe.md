# SMELL-016 — Audit actor capture rides `threading.local`; structlog half already uses contextvars

- **Severity:** 🟡 Smell (works today under WSGI, breaks under ASGI)
- **Source:** the 2026-06-11 audit-logging review
- **Files:** `core/threadlocal.py`, `core/middleware.py:57–98`
  (`AuditMiddleware`), `core/signals.py` (`populate_user_fields`)

## Problem

`AuditMiddleware` stores the request user and correlation id in a
`threading.local()`. The correlation half of the same middleware already
binds into **structlog contextvars** — so the two halves of "request
context" use different propagation mechanisms.

Consequences:

- Under ASGI / async views, coroutines share threads: `threading.local`
  leaks one request's user into another's audit rows, or loses it. We're
  WSGI today, so this is latent — but it fails *silently* (wrong `actor`
  on audit rows), which is the worst failure mode for an audit trail.
- `current_user_as(...)` (the Celery/management-command escape hatch) has
  the same thread affinity.

## Proposed fix

Replace the `threading.local` in `core/threadlocal.py` with
`contextvars.ContextVar`s; keep the module's public API
(`get/set_current_user`, `get/set_correlation_id`, `current_user_as`,
`correlation`) identical so no call site changes. Mechanically small —
the module is ~60 lines. Rename the module (`core/request_context.py`?)
or leave the name as a lie-shaped breadcrumb; renaming preferred.

contextvars propagate into `sync_to_async`/`async_to_sync` correctly and
match what structlog already does, collapsing the two mechanisms into one.

## Acceptance

- `core/threadlocal.py` has no `threading.local` usage.
- Existing audit-actor tests pass unchanged.
- One test exercising actor capture across an async boundary
  (`asgiref.sync` round-trip) if cheap; otherwise the swap + existing
  suite is sufficient.

## Dependencies

None. Do opportunistically; mandatory before any ASGI/async adoption.

## Resolution

Done. Replaced the `threading.local()` store with two
`contextvars.ContextVar`s (stdlib — no new dep, matches what structlog already
uses for `request_id`). The module was renamed `core/threadlocal.py` →
`core/request_context.py`; the public API (`get/set_current_user`,
`clear_current_user`, `get/set_correlation_id`, `current_user_as`,
`correlation`) is byte-for-byte unchanged, so all four call sites
(`core/signals.py`, `core/audit.py`, `core/middleware.py`, `comms/services.py`)
moved with a one-line import swap and no behavioural change.

Two incidental hardenings fell out of the ContextVar shape: the context
managers now `reset(token)` to the *exact* prior context (nesting-safe, where
the old `set(prev)` snapshot worked but was looser), and `clear_current_user`
sets `None` rather than `del`-ing the attribute.

WSGI behaviour is preserved exactly (each request runs on its own thread =
its own context). New `core/tests/test_request_context.py` pins the public API
and adds the SMELL-016 regression guard:
`test_actor_propagates_across_async_boundary` round-trips actor + correlation
id through `async_to_sync(sync_to_async(...))` (asgiref threadpool) — the case
where a `threading.local` would have lost or leaked the actor. Existing
audit-actor / request-logging tests pass unchanged. Full suite green
(1690 passed), ruff + mypy clean.
