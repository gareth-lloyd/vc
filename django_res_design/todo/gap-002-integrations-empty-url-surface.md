# GAP-002 — `integrations/urls.py` is empty

- **Severity:** Gap
- **Status:** ✅ Slice 1 resolved 2026-06-15 (pre-existing); slices 2–3 re-ticketed (see Resolution)
- **Source:** repo audit
- **Files:** `django_res/integrations/urls.py`

## Resolution (2026-06-15)

**Slice 1 (Flywire webhook) was already built and tested** — the ticket's
premise was stale. It lives in the **`payments` app**, not `integrations/`,
and that placement is *mandated* by the import-linter spine
(`comms > payments > … > integrations`): `integrations` sits below `payments`
and may not import `Payment`/`transition_to`, so a payment-status webhook
cannot live there. Existing implementation:

- `payments/views/webhook.py` — `POST /api/v1/webhooks/payments/<provider>/`
  (CSRF-exempt, persist-first), mounted via `payments/urls.py`.
- `payments/webhooks/base.py` — `WebhookDispatcher`: HMAC-SHA256 over raw
  body bytes (`hmac.compare_digest`, fails closed), DB-backstopped dedupe on
  `(provider, event_id)` via `WebhookDelivery`, webhook-specific transition
  policy, amount/currency mismatch refusal, transitions via the model/service
  seam.
- `payments/webhooks/flywire.py` — Flywire body parser.
- `payments/tasks.py` — Celery `process_webhook_delivery` + stale sweeper.
- Secret is settings-driven: `PAYMENT_WEBHOOK_SECRETS["FLYWIRE"]` ←
  `FLYWIRE_WEBHOOK_SECRET` (required in `production.py`).
- All acceptance criteria covered by `payments/tests/test_webhook.py`
  (17 tests passing).

Timeline confirms the ticket post-dates the code (webhook `a8ee8a5`
2026-05-13; ticket `3e20552` 2026-05-29; hardened through `74e0479`).

**Spec note:** `product-design/04-rest-api-surface.md` says
`POST /webhooks/flywire`; reality is
`POST /api/v1/webhooks/payments/flywire/`. Cosmetic (Flywire is configured
with whatever URL we provide); left as-is, flagged here per the
spec/code-disagreement convention.

**Remaining work re-ticketed** (not part of slice 1):
- Slice 2 (Zoho webhook) stays blocked on [Q-003](q-003-channel-sync-scope.md).
- Slice 3 (admin `/system/integrations`: `OAuthCredential` CRUD +
  sync-run/sync-issue list endpoints) → see **GAP-028**.

Note: [FG-005](fg-005-idempotency-user-required.md) named the Flywire handler
as its first caller, but the webhook dedupes via `WebhookDelivery` uniqueness,
not `IdempotencyRecord` — FG-005 is moot for this surface and wants its own
re-justification.

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
