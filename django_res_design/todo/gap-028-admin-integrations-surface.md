# GAP-028 — Admin `/system/integrations` configuration surface

- **Severity:** Gap
- **Source:** split out of [GAP-002](done/gap-002-integrations-empty-url-surface.md) slice 3 (2026-06-15)
- **Files:** `django_res/integrations/urls.py` (still empty), `integrations/views.py`

## Problem

The `integrations` app has models (`SyncRecord`, `OAuthCredential`, the
`SyncRun`/`SyncIssue` shapes), services, and signals, but no HTTP surface —
`integrations/urls.py` declares an empty `urlpatterns`.

GAP-002 slice 1 (Flywire payment webhook) turned out to already exist in the
`payments` app (layering-mandated location). This ticket carries the
**remaining** integrations surface:

1. `OAuthCredential` CRUD for the admin `/system/integrations` screen.
2. `SyncRun` / `SyncIssue` list (+ detail) endpoints for the same screen.

## Proposed fix

Admin-only DRF viewsets in `integrations/`, mounted in
`integrations/urls.py`, gated by the staff-write permission floor. Read
[INV-004](done/inv-004-syncrun-syncissue-retry.md) first — it closed the
`SyncRun`/`SyncIssue` schema as adequate (execution is v1.1), so these are
read surfaces over existing rows, not new execution machinery.

## Acceptance

- `OAuthCredential` CRUD with secrets write-only / never serialized back.
- `SyncRun` / `SyncIssue` lists filterable by provider + status.
- Staff-write gate enforced; non-staff 403.

## Dependencies

- Independent of Q-003 (that blocks the Zoho *webhook*, slice 2, which stays
  on GAP-002).
- **2026-07-15 re-scope note ([GAP-081](gap-081-zoho-flow-outbound-push.md)):**
  the agreed Zoho integration is Flow webhooks with **no OAuth on the res
  side**, so the `OAuthCredential` CRUD half of this surface has no Zoho
  consumer — it only earns its keep if/when a second OAuth-based provider
  lands (Mailchimp/HubSpot per the model's own rationale). The
  `SyncRun`/`SyncIssue` read surfaces still apply and will display GAP-081's
  push rows. Consider descoping to the read surfaces when picked up.
