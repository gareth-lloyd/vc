# FG-009 — CSRF priming is coupled to who serves the HTML shell (recurring double-login)

- **Severity:** 🟠 Footgun (dev-only impact; **not vital** — year-long cookie means it bites rarely)
- **Source:** 2026-06-06 investigation of the recurring "log in twice" bug
- **Files:** `core/views.py:142` (`spa_index` `@ensure_csrf_cookie`),
  `frontend/vite.config.ts:24-37`, `frontend/src/app/boot.tsx:16`,
  `accounts/views/auth.py:89` (`MeView` is `IsAuthenticated`)

## Problem

The only thing that primes the `csrftoken` cookie is `spa_index`'s
`@ensure_csrf_cookie`, which runs **only when Django serves the HTML shell**.
In local dev the Vite server on `:5173` serves the shell (only `/api` + `/media`
proxy to Django), so nothing primes the cookie on the dev origin. The login page
also makes no backend GET (`BootGate` public branch), and `GET /auth/me` is
`IsAuthenticated` so it can't prime either. Fresh/incognito/cleared browser →
first login POST has no `X-CSRFToken` → 403 → that response sets the cookie →
second submit works. Fixed twice before (`201d0e6`, `d3df533`), both times only
for the production single-origin path — never dev. Hence the recurrence.

## Proposed fix

Decouple priming from who serves the shell:

1. Backend: `GET /api/v1/auth/csrf` — thin `AllowAny` `APIView` with
   `@method_decorator(ensure_csrf_cookie, name="get")`, mirroring the `health`/
   `system_version` pattern in `core/views.py`. Register in `accounts/urls.py`.
2. Frontend (chosen: simplest): `usePrimeCsrf()` `useQuery` called at the top of
   `BootGate` for **all** paths (incl. `/login`), `enabled` only when no
   `csrftoken` cookie present. Accepts a benign race (submit before GET resolves)
   that doesn't bite the type-then-submit human flow.

Leaves `spa_index`'s priming in place — prod still relies on it — so two
priming mechanisms now coexist; keep the `spa_index` regression tests.

## Acceptance

- `GET /api/v1/auth/csrf` is 200 while logged out and sets `csrftoken`
  (regression test written red-first — `ensure_csrf_cookie` on a DRF view can
  silently no-op).
- FE: with cookie cleared, mounting `BootGate` issues `GET /auth/csrf`; with
  cookie present it does not.
- E2E: clear `localhost:5173` cookies, load `/login`, submit valid creds once →
  authenticated, no 403.

## Dependencies

None. Low priority — acceptable alternative is "document the dev gotcha and
serve single-origin locally when it matters".
