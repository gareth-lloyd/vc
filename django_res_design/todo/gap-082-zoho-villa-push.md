# GAP-082 — Zoho Flow villa push (descoped from GAP-081)

- **Severity:** Gap
- **Source:** Descoped from [GAP-081](done/gap-081-zoho-flow-outbound-push.md)
  by user decision (2026-07-23) when the Limitless sandbox endpoints landed —
  contacts/enquiries/quotes shipped there; the villa push is its own,
  lower-urgency slice.
- **Files:** `django_res/integrations/services/zoho_flow.py` (registry to
  plug into), `django_res/properties/` (where the builder must live),
  `legacy/workflows/11-integrations/zoho-crm.md:143-146` (`PushZohoVilla` /
  `ZohoVillaPostData` field reference)

## Problem

Limitless has already provisioned a **Villas** Zoho Flow webhook endpoint
(delivered in their 2026-07-23 email alongside contacts/enquiries/quotes),
but res has no villa push. Zoho-side villa records give the CRM something to
segment/report against and let enquiry/quote records reference a villa
entity rather than a free-text name.

GAP-081 built all the machinery this needs — `register_zoho_flow`,
`enqueue_zoho_push`, `push_sync_record` delivery/retry, the `push_pending`
sweep, loader suppression, and the `zoho_backfill` command. This ticket is
"one more registration + payload builder", plus the wrinkles below.

## Proposed fix

1. **Settings:** add `"villa"` to the kind vocabulary in `zoho_flow.py` and a
   `ZOHO_FLOW_WEBHOOK_VILLA` env var → `ZOHO_FLOW_WEBHOOKS["villa"]`
   (name reserved here; the sandbox URL from the 2026-07-23 email goes into
   Render env vars, never the repo). Hard-pin `""` in `settings/test.py`
   like the other four kinds.
2. **Builder placement:** `properties` sits **above** `integrations` in the
   import spine, so (like enquiries/quotes) the builder lives in
   `properties/services/zoho_payload.py` and registration happens in
   `properties.apps.ready()` — `register_zoho_flow(Property, kind="villa",
   build_payload=..., auto_push=True)`.
3. **Payload:** full-fat per the GAP-081 policy, `RES_ID` + all fields,
   nested region/country sub-objects. Legacy `ZohoVillaPostData` minimum
   checklist (`zoho-crm.md:146`): `id`, `Name`, `VillaId`, `CountryName`,
   `Region`, `Owner`, `Villa_URL`, `Villa_Name_Other`, `Co_ordinates`,
   `Note`, `Country`, `Last_Activity_Time`, `Modified_Time`, `Created_Time`.
   Note **`Owner`, `Co_ordinates`, `Villa_URL` have no clean current-model
   equivalents** (owner is an authz relation, no lat/long on Property, no
   public site URL yet) — map what exists, document the rest as omitted; do
   NOT invent placeholder values.
4. **Change-signal caveats** (why this wasn't a free rider on GAP-081):
   - `Property.features` is **M2M** — `post_save` on Property does not fire
     on M2M mutations; an `m2m_changed` receiver (or explicit enqueue in the
     features-save service) is needed for feature edits to push.
   - Property rows churn on operational timestamps (availability freshness
     signals, GAP-033 three-signal split) — a bare `auto_push=True` would
     re-push the villa on every iCal sweep. Use a `fields=`-style change
     restriction (the generic `register_sync_target` has a `fields=`
     precedent in `integrations/signals.py`; `register_zoho_flow` would need
     the same option) or enqueue from the specific edit services instead.
5. **Backfill:** add `villa` to `zoho_backfill`'s kind order (villas should
   push **before** enquiries/quotes so their references resolve —
   i.e. order becomes villa → contact → enquiry → quote or similar; confirm
   with Limitless whether their Flow mapping cares).

## Acceptance

- Villa create/edit (including feature M2M changes) POSTs full-field JSON to
  the configured villa Flow URL; availability-freshness churn does NOT
  re-push.
- Unset URL = silently disabled; suppression covers legacy loads;
  `zoho_backfill --kinds villa` replays all properties idempotently.
- `ZohoVillaPostData` minimums mapped or documented-omitted; no placeholder
  values invented.

## Dependencies

- [GAP-081 ✅](done/gap-081-zoho-flow-outbound-push.md) — all push machinery
  (registry, delivery task, sweep, suppression, backfill) built there.
- The villa webhook URL from the Limitless 2026-07-23 email (env var only).
