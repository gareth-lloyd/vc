# SMELL-012 — Module-structure drift: filters, services, routers, URL-file views

- **Severity:** 🟡 Smell
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `payments/filters.py`, `reservations/filters.py`,
  `properties/filters/`, `pricing/filters/`, `accounts/views/contact.py:23`,
  `accounts/views/user.py:24`, `comms/services.py`, `payments/urls.py:33–39`,
  the per-app `urls.py` router declarations

## Problem

Four structural concerns each have multiple coexisting shapes:

- **Filters in three shapes**: flat module (`payments/filters.py`,
  `reservations/filters.py`), package (`properties/filters/`,
  `pricing/filters/`), and `FilterSet` classes defined inline in view
  modules (`accounts/views/contact.py:23`, `accounts/views/user.py:24`).
- **Services**: `comms/services.py` is a flat module while every other app
  uses a `services/` package (32 modules).
- **Routers**: `DefaultRouter` (core, comms, properties, accounts, pricing)
  vs `SimpleRouter` (payments, reservations), with differing
  `trailing_slash` handling implied.
- **Views in URL files**: ~~the `refunds_for_booking` dispatcher is a full
  `@api_view` defined inside `payments/urls.py`~~ **DONE (2026-06-23)** — moved
  into `payments/views/refund.py` (beside its `list_/request_` helpers); `urls.py`
  now just imports it. The remaining three concerns below are still open.

None of this is broken; all of it makes "where does X go?" a per-app
archaeology exercise for contributors and agents.

## Proposed fix

Pick one shape per concern (suggested: `filters/` package once an app has
more than one FilterSet, otherwise flat module; `services/` package always;
`SimpleRouter(trailing_slash=False)` unless the browsable-API root is
wanted; views never in `urls.py`), document the choice in
`django_res/CLAUDE.md`, and migrate opportunistically when touching each
app — no big-bang rename commit.

## Acceptance

- CLAUDE.md names the chosen shape for each concern.
- ~~`refunds_for_booking` moves into `payments/views/`~~ ✅ done 2026-06-23.

## Dependencies

None. Related: SMELL-013 (same "document the de-facto convention" family).
