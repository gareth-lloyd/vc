# GAP-021 — Per-entity "History" tab in the SPA (audit-log surface)

> ✅ **RESOLVED** (2026-06-22, commit `6f89f95`)
>
> **Problem:** the admin-only audit-log read API (`GET /audit-log`, filterable
> by entity) had no SPA consumer — the trail was write-only from the operator's
> view. The one piece of FE audit scaffolding that did exist (a Contacts
> `AuditTab`) was built test-first against a *fabricated* `field_diffs` shape
> (`{from, to}` objects, a `__created__` marker) that the backend never writes,
> and pointed at `accounts.contact` — a content type that ceased to exist when
> GAP-045 unified human identity into `accounts.Person`, so it returned zero
> rows. It also dumped raw `JSON.stringify(field_diffs)` rather than diff rows.
>
> **Fix (frontend-only — backend read surface already adequate & admin-only):**
> - `features/audit/diff.ts` — a pure interpreter for the *real* `core/audit.py`
>   contract: `[old, new]` pairs, the `__deleted__` tombstone, merge metadata
>   (`__merged_into__` / `__rewrites__`), and the `[REDACTED]` sentinel. (The
>   backend writes no create marker, so a create is rendered honestly as a
>   change with a `— → value` row rather than a guessed "Created" label.)
> - `features/audit/AuditHistory.tsx` — a reusable, single-target view:
>   formatted `field: old → new` rows, a deletion banner, a merge summary
>   (target + reassignment count), a `From`/`To` date-range filter (upper bound
>   widened to end-of-day so the chosen day is inclusive), pagination, and an
>   admin-403 permission notice. Field names are humanised (`commission_amount`
>   → "Commission amount") rather than per-model translated — this is an
>   admin-only technical surface.
> - Admin-gated **History** tabs (the nav link hides for non-admins; the route
>   stays mounted so a direct URL still resolves to the 403 notice):
>   - **Booking** → `reservations.booking`.
>   - **Property** → two stacked single-target panels, **Property**
>     (`properties.property`) and **Finance** (`properties.propertyfinance`);
>     finance shares the property id because `PropertyFinance.property` is a
>     `OneToOneField(primary_key=True)`, so its audit `object_id` == the
>     property id. This answers the ticket's #1 case ("who changed this
>     commission %?") without a multi-content-type merge.
>   - **Contacts** → fixed to `accounts.person` and switched to the formatted
>     renderer.
> - i18n en + el for all new strings; `tabs.history` on bookings/properties.
> - Tests: `diff` unit tests; `AuditHistory` (commission old→new with actor,
>   date-filter params, merge banner); Booking/Property tab wiring + admin-gating;
>   rewritten Contacts tab tests pinning the `accounts.person` entity_type.
>
> **Deliberately not done:** the `action`-filter GIN index flagged below is
> unneeded — the UI never uses that filter. `GroupFinance`-level (inherited)
> finance history is a group-screen concern, out of scope here. Multi-target
> merge was considered and rejected in favour of the simpler stacked
> single-target panels (per the 2026-06-22 scoping decision).

- **Severity:** Gap (designed-but-unbuilt surface)
- **Source:** the 2026-06-11 audit-logging review; Q-014 follow-up list
- **Files:** `core/views.py:68–103` (`AuditLogViewSet`),
  `core/serializers/audit_log.py`, frontend booking/property/finance
  detail screens

## Problem

The backend read surface already exists and is filterable by entity:
`GET /api/v1/audit-log?entity_type=reservations.booking&entity_id=<pk>`
(plus `actor`, `created_after/before`, `action`). Nothing in the SPA
consumes it — audit data is write-only from the operator's point of view,
which halves its value (the trail exists but answering "who changed this
deposit percentage?" requires a shell).

## Proposed fix

- A "History" tab (or drawer) on detail screens, starting where the
  questions actually arise: **PropertyFinance / GroupFinance** (commission,
  bank, deposit terms), then Booking, then Property. Render
  `created_at · actor_email · field: old → new` rows from `field_diffs`;
  `__deleted__` rows render as a deletion banner.
- Domain event timelines (`BookingEvent`, `EnquiryEvent`) already serve the
  activity-feed use case — this tab is the *field-diff* complement, not a
  replacement. Don't merge the two streams in v1; link between tabs if both
  exist on a screen.
- Exposure is gated on **Q-014's** second question (operator vs
  admin-only). Current backend permission is `IsStaffRoleAdmin`; if Q-014
  lands on operator-visible, the viewset needs a scoped-down permission +
  possibly per-entity-type allowlist.
- Backend nit to pick up alongside: the `action` filter uses
  `field_diffs__has_key` with no GIN index (flagged in the code comment at
  `core/views.py:96`). Add `GinIndex(fields=["field_diffs"])` only if/when
  this filter is actually used by the UI.

## Acceptance

- History tab on PropertyFinance shows a just-made commission edit with
  actor and old → new values.
- Pagination + date filtering work against a seeded history.
- Permission behaviour matches the Q-014 decision.

## Dependencies

- **Blocked by Q-014** (exposure decision). Retention half of Q-014 does
  not block.
- BUG-012 should land first so the UI never displays PII that a scrub
  should have removed.
