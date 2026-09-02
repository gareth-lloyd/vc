# GAP-096 — `Organisation` has no Zoho push of its own

- **Severity:** 🟠 Gap (CRM Accounts are created as a side effect and go
  stale; blocks the agency half of the contact mapping).
- **Source:** 2026-09-01 review of Limitless' `limitless_upsert_villa` and
  `limitless_parse_res_contact` against our payloads.
- **Files touched (when built):**
  - `django_res/integrations/apps.py:131` — where `Person` registers as the
    `contact` kind; `Organisation` would register alongside it.
  - `django_res/integrations/services/zoho_payloads.py` —
    `_agency_payload` is already the shape an organisation payload wants;
    lift it to a `build_organisation_payload`.
  - `django_res/properties/services/zoho_payload.py` —
    `_organisation_summary` (the villa-embedded copy).
  - `django_res/integrations/services/zoho_flow.py:82` — `ZOHO_FLOW_KINDS`
    + the `ZOHO_FLOW_WEBHOOKS` setting (a new webhook URL is needed from
    Limitless).

## Problem

Registered push kinds today are `contact` (Person), `enquiry`, `quotation`,
`booking` and `villa` (Property). `accounts.Organisation` is not among them,
and three consequences follow — all of which surfaced as apparent Flow bugs
before tracing back here:

1. **CRM Accounts exist only as a villa side effect.** `limitless_upsert_villa`
   creates/updates an Account from `contacts[role=management_company]
   .organisation`. That is the *only* path by which an Organisation becomes
   an Account.
2. **Agency organisations never become Accounts at all.** The contact flow
   writes `Contact_Type: "Agency"` as text on the Contact and stops there, so
   the B2B directory GAP-046 built has no CRM counterpart. Our contact
   payload already sends a keyed `agency` sub-object (`RES_ID`, `id`, `name`,
   address, `org_type`, `status`) that has nowhere to land.
3. **Renames never propagate.** `Organisation` is not in `_VILLA_CHILDREN`
   (`properties/signals.py:99`) — correctly, since it is not a child of one
   property — so editing an organisation bumps nothing. `Account_Name` can
   stay wrong indefinitely, and the villa payload docstring already records
   this class of staleness as an accepted trade-off for *embedded catalog
   copies*. It is not an acceptable trade-off for the Account record itself.

Adding a bump receiver would be the wrong fix: an organisation can be the
management company of many villas, so an edit would fan out N villa pushes to
refresh one Account name.

## Proposed fix

Register `Organisation` as its own kind, mirroring the `contact` pattern:

- `register_zoho_flow(Organisation, kind="organisation",
  build_payload=build_organisation_payload)` with `auto_push=True`.
- Payload from the existing `_agency_payload` shape (`RES_ID`, `id`, `name`,
  `org_type`, `email`, `phone`, address block, `country`, `website_url`,
  `notes`, `status`), plus `created_at`/`updated_at`.
- New `ZOHO_FLOW_WEBHOOKS["organisation"]` URL — needs Limitless to stand up
  the endpoint, so this is a coordinated landing, not a solo one.
- Extend `zoho_backfill` ordering: organisation **before** contact and villa,
  so the Account exists before anything looks it up.
- **Villa before booking**, for the same reason (added 2026-09-02, off the
  booking-flow review). `limitless_insert_booking` COQLs `Products` by
  `RES_ID` and, on a miss, creates a *stub* villa from the thin `region`
  object the booking payload carries — no location, no capacity, no rooms,
  no features, and a free-text `Region`/`Country`. That stub is a
  second-class Product the villa upsert then has to reconcile, and its
  duplicate-name branch is where CHECK-004 item 6 (booking attached to the
  wrong villa) becomes reachable. The stub path is a legitimate safety net,
  but it should be rare: emitting villas ahead of bookings makes it so. Full
  ordering: organisation → contact → villa → enquiry → booking.
- Once it exists, the villa flow's inline Account create/update becomes a
  lookup, and the contact flow can set a real Account lookup instead of the
  `Contact_Type` text. Both are Limitless-side follow-ups — record them on
  CHECK-001 / CHECK-003 when this lands.

No erasure concern: `OrgStatus` has no ANONYMIZED member by design (an
organisation is not a data subject — see `accounts/enums.py`), so the
GAP-095 question does not extend here.

## Acceptance

- Saving an `Organisation` enqueues an `organisation` push. (test)
- The payload carries every CRM-relevant column, JSON-safe. (test)
- `zoho_backfill` emits organisation → contact → villa → enquiry → booking,
  in that order. (test)
- Renaming an organisation results in exactly ONE push, not one per villa it
  manages. (test — this is the whole point)
- A villa's management-company Account is found by lookup, not created by the
  villa flow. (verified Zoho-side, CHECK-003)

## Dependencies

- **Blocked on a webhook URL from Limitless** — same coordination shape as
  the villa/booking kinds in GAP-082.
- **CHECK-003** item 2 — picking the *right* management company is
  orthogonal and can land first; this ticket changes where the Account comes
  from, not which one is chosen.
- **CHECK-001** — the agency half of the contact mapping is blocked on this.
- **GAP-046** — the Organisation model this pushes.
