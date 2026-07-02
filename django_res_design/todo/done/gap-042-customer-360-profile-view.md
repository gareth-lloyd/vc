> **✅ RESOLVED (2026-06-23)** — Shipped on local `main` (unpushed) via
> feat/gap-042 (B1 `0d0f9ea`, F1 `df116e5`, F2 `08d574d`, F3 `bd33c32`). The
> sales-team 360 profile is assembled over the unified `accounts.Person` —
> *compose*, not a new aggregate endpoint. `GET /contacts/{id}` now serializes
> town/post_code/country (+ `country_name`) and a property-agnostic
> `booking_count` + `is_repeat_customer` (>= 1 booking; the annotation is gated
> to list/retrieve in `get_queryset` per the multi-valued-join rule). The FE
> `CustomerProfilePanel` (identity + Repeat badge + tags + collapsible address +
> linked-contacts + enquiry & booking-history accordions, the latter wiring in
> the previously-dead `ContactEnquiryHistory`) is reused by the contact detail
> page and embedded in the enquiry- and quotation-detail rails. **Deferred:**
> "calls"/activity-log history (no model — see Q-017), rich-text notes (plain
> `notes` for now), country editing (display-only), quote-builder inline embed
> (no rail). Tests: 968 backend + 1260 frontend green.

---

# GAP-042 — Customer 360 profile for the sales team

- **Severity:** Gap (backend endpoint + frontend) — assembles the full client view
- **Source:** 2026-06-17 owner Loom ("a very full customer profile for the sales
  team to view upon quote" — address, customer notes, tags, enquiry history of
  inquiries/quotes/calls, linked contacts, previous bookings) + the mockup at
  https://vc-new-res-system.netlify.app/ → **New Quote → Overview** panel and its
  accordions. Mirrors the legacy `ClientDetails` cards in
  [GAP-010 §4](../gap-010-quote-enquiry-analyzed-wrong-codebase.md).
- **Status:** Open — consumes GAP-040 (tags) and GAP-041 (linked contacts).
- **Files:**
  - `django_res/reservations/` — a per-guest profile read endpoint (or extend
    the existing `GET /guests/{id}/enquiries` from
    [GAP-005](../gap-005-quotation-flow-parity.md) M3)
  - `frontend/src/features/quotations/` (the New-Quote Overview panel) +
    `features/enquiries/`

> ℹ️ **Entity + directory context (2026-06-18):** the profile assembles over a
> unified `accounts.Person` (**GAP-045**); the standalone Clients *list* this
> profile is opened from is **GAP-047** (kept separate — list vs detail).

## Problem

The sales team needs the whole client picture in one place when quoting. The
pieces are scattered or absent: enquiry history exists as a collapsible panel
(GAP-005 M3) but the consolidated profile — identity, address, notes, tags,
linked contacts, previous bookings — is not assembled, and previous
bookings/quotes are only reachable via reverse-FK queries.

## Proposed fix

Build the mockup's **Overview** profile:

- **Identity:** Title, First/Last name, preferred channel (Phone/Email), Email,
  Country code + Phone.
- **Address:** Line 1/2, City/Town, Country, Postcode — **collapsible/hideable**
  (owner: "this guy actually could be hidden … useful to have it there").
- **Internal Notes:** rich text (legacy `ResEditor` parity).
- **Tags:** from [GAP-040](gap-040-customer-tags-taxonomy.md).
- **Accordions:** **Enquiry history** (past enquiries + quotes), **Linked
  contacts** ([GAP-041](gap-041-standing-linked-contacts.md)), **Previous
  Booking** (the legacy `GetPreviousBooking` grid — needs a query/endpoint, not
  just reverse-FK).

Expose it through one profile endpoint so the New-Quote screen and the enquiry
detail both render from a single source.

**Dependency to flag — "calls" history.** The Loom and mockup list history as
"inquiries, quotes, **calls**", but there is **no call/activity-log model** in
the backend. Either scope calls out of v1 or raise a separate modeling
dependency (a lightweight activity/interaction log) — do not imply it exists.
Cross-ref [Q-017](../q-017-comms-direction-signals-vs-spine-position.md) (comms
spine) as the natural home if pursued.

## Acceptance

- Opening a client from the quote/enquiry screen shows identity, hideable
  address, notes, tags, linked contacts, enquiry history, and previous bookings,
  from one endpoint.
- Previous bookings/quotes are listed (not just reverse-FK reachable).
- Quality gate green.

## Dependencies

- Consumes [GAP-040](gap-040-customer-tags-taxonomy.md) and
  [GAP-041](gap-041-standing-linked-contacts.md); extends
  [GAP-005](../gap-005-quotation-flow-parity.md) M3 history. "Calls" needs a new
  activity-log decision before that part can land.
