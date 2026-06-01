# GAP-001 — `comms/urls.py` is empty

- **Severity:** Gap
- **Source:** repo audit
- **Files:** `django_res/comms/urls.py`

## Problem

`comms/urls.py` declares an empty `urlpatterns` list. There are models
(`EmailLog`, `SmtpProfile`, `EmailTemplate`), serializers, and a view
(`comms/views/email_log.py`), but nothing is mounted under `/api/v1/`.

The design spec in `04-rest-api-surface.md` lists endpoints for email
templates, email logs, SMTP profiles, allowlists, manual mark/send.

## Proposed fix

Slice 1 (smallest viable): expose `EmailLog` read endpoints —
list + detail — for the operator UI's Comms tab. Wire the existing
`EmailLogViewSet` into the URL conf with a router.

Subsequent slices:

- `EmailTemplate` CRUD (admin only).
- `SmtpProfile` CRUD (admin only).
- Recipient allowlist management.
- Manual `:resend` action on `EmailLog`.

## Acceptance

- `GET /api/v1/email-logs` returns a paginated list.
- `GET /api/v1/email-logs/{id}` returns the detail row.
- Permission test: only authorised roles can read.
- `assert_max_queries` regression on the list endpoint per CLAUDE.md.

## Resolution

✅ Slice 1 shipped. Added `EmailLogViewSet` (read-only list + detail) in
`comms/views/email_log.py`, wired into `comms/urls.py` via a `DefaultRouter`
under `email-logs` (so `GET /api/v1/email-logs` and `/email-logs/{id}`).
Reuses the existing `EmailLogSerializer` for the list (no body) and adds
`EmailLogDetailSerializer` (adds `body` + `body_html`) for retrieve — matching
the list/detail split convention. Queryset `select_related`s `sender_user` +
`smtp_profile` and orders newest-first; permission is `IsAuthenticated +
IsReservationsWriter` (read for any authenticated staff). Tests in
`comms/tests/test_api_email_logs.py`: paginated list, newest-first ordering,
detail-includes-body, anonymous-forbidden, and an `assert_max_queries(10)`
N+1 regression. Subsequent slices (EmailTemplate/SmtpProfile CRUD, allowlist,
top-level resend) remain open.

## Dependencies

None for slice 1. Subsequent slices may depend on the
[Q-011 email template inheritance](q-011-email-template-inheritance.md)
answer.
