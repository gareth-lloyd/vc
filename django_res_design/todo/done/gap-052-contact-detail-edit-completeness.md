> **✅ RESOLVED (2026-07-01)** — Shipped on local `main` (unpushed) as Landing 1
> of the contacts-directory cluster. **Editable + audited country** (`6fd4771` —
> `Person.country` writable via ModelSerializer auto-gen + added to the audit
> `track()` set; FE `CountryPicker` in the contact form with Clear, `020713b`).
> **Contact-type badges** (`8cac257` — `contact_types` SerializerMethodField from
> kind / booking_count / agency / a correlated `ArrayAgg` of active
> property-assignment roles, no COUNT inflation; FE token badges `58e51a2`).
> Address/town/post-code/notes were already writable+tracked. Deferred: rich-text
> notes; full-fidelity deal-channel agent in `contact_types` (accounts-only
> derivation — a pure deal-channel agent with no agency/agent-role isn't badged,
> still appears in Clients).

# GAP-052 — Contact detail: editable address, editable notes, contact-type badges

- **Severity:** Gap (frontend-led + small serializer surface) — follow-up to
  GAP-042; cross-directory (Clients **and** Suppliers detail).
- **Source:** 2026-06-29 owner Loom follow-up notes:
  - "make the address fields for contacts **editable**";
  - "contact notes should be **finished and editable**";
  - "viewing an individual contact needs a clear indication of contact
    **type(s)** (agent, customer, owner, etc)".
  Builds on the 2026-06-17 owner Loom that drove GAP-042. Mockup
  `mock_up_analysis/01-new-res-system.md` §2.12 ("Client Type (badges)") + §2.14.
- **Status:** Open.
- **Files:**
  - `frontend/src/features/contacts/` — `CustomerProfilePanel` (GAP-042) +
    the Suppliers detail form (GAP-048).
  - `django_res/accounts/serializers/person.py` — make address/notes writable;
    a derived `contact_types` read field.
  - `django_res/accounts/views/` (or serializer annotation) for the type
    derivation, query-pinned.

## Problem

GAP-042 deliberately shipped the customer-360 profile with **address
display-only** ("country editing deferred — display-only") and **plain `notes`**
("rich-text deferred"); the address block is collapsible but not editable. The
owner now wants both **editable** on the contact detail — for Clients *and*
Suppliers — and a clear, at-a-glance indication of **what type(s)** a contact is
(a person can be an owner *and* a customer *and* an agent over time).

This **overturns** the GAP-042 "display-only / country-deferred" calls (record in
`10-decisions.md`).

## Proposed fix

1. **Editable address.** Make `address_line_1/2`, `town`, `post_code`, and
   `country` (FK → `properties.Country`, the `country_code`/`get_country()`
   convention) writable on the contact PATCH path. `Person` already carries all
   five fields (GAP-045) and the read side is shipped (GAP-042); this is the
   write surface + form fields on both the `CustomerProfilePanel` and the
   Suppliers detail. Edits are PII/audited — they already route through the
   `Person` audit `track(...)` registration; confirm the address columns are in
   the tracked set and scrubbed on erasure.
2. **Editable / finished notes.** Surface `Person.notes` as an editable field
   (plain text is acceptable for v1 — rich-text/`ResEditor` parity stays
   deferred unless the owner insists); ensure it saves and is audited. "Finished"
   = a real edit affordance, not a read-only block.
3. **Contact-type badges.** Render the contact's **type(s)** on the detail
   (and optionally as the mockup's list "Client Type" badges): derive from
   - `kind=CUSTOMER` and/or has bookings/enquiries → **Customer**,
   - has `agency` / used as an `.agent` → **Agent** (per GAP-046),
   - has a `PropertyContactAssignment` role → **Owner / Manager / Villa Admin /
     Villa Manager / Management Company** (per GAP-048).
   Expose as a query-pinned derived read field (`contact_types`) so a
   dual-capacity human shows all their hats — surface the overlap, don't hide it
   (cross-ref the GAP-047 dual-capacity caveat). Tags are **not** types — tags
   are the client-only flag set (GAP-040/GAP-053).

## Acceptance

- Address (incl. country) and notes are editable end-to-end on both the Clients
  profile and the Suppliers detail; edits are audited and erasure-scrubbed.
- The contact detail shows the contact's type(s) as badges, derived (not a
  manual field), reflecting every capacity the person holds.
- Decision recorded in `10-decisions.md` (overturns GAP-042 display-only).
- Quality gate green (vitest + pytest for the serializer/derivation change).

## Dependencies

- Follows **GAP-042** (shipped the read-only profile + `CustomerProfilePanel`),
  **GAP-048** (Suppliers detail + property roles feeding the type derivation),
  **GAP-046** (agent capacity), **GAP-040** (tags — distinct from types).
- Country lookups follow the `country_code` + `get_country()` convention.
