# GAP-002 — `integrations/urls.py` is empty

- **Severity:** Gap
- **Source:** repo audit
- **Files:** `django_res/integrations/urls.py`

## Problem

`integrations/urls.py` declares an empty `urlpatterns` list. The app has
models (`SyncRecord`, `OAuthCredential`, the `SyncRun`/`SyncIssue` shapes),
services, and signals — but no HTTP surface.

The design spec calls for `/webhooks/{provider}` endpoints (Flywire,
Zoho), an admin-facing `/system/integrations` configuration surface, and
sync-run / sync-issue list endpoints.

## Proposed fix

Three slices:

1. **Flywire webhook** — `POST /webhooks/flywire` with HMAC signature
   verification on raw body bytes. This is the highest-value slice; the
   payment confirmation path depends on it.
2. **Zoho webhook** — `POST /webhooks/zoho` once Q-003 (channel scope)
   is clear.
3. **Admin /system/integrations** — `OAuthCredential` CRUD plus
   sync-run / sync-issue list endpoints for the admin screen.

## Acceptance

- Slice 1 first. Test: signed payload accepted, unsigned/invalid
  rejected with 401, replayed payload deduped (see
  [FG-005](fg-005-idempotency-user-required.md)).

## Dependencies

- Slice 1 → [FG-005](fg-005-idempotency-user-required.md) is the right
  shape for webhook dedupe.
- Slice 2 → [Q-003](q-003-channel-sync-scope.md).
