# GAP-105 — No publication gate for the public website (`status` and `channel` both mean something else)

- **Severity:** 🟠 Gap (nothing in the model answers "should this villa have a
  public web page?", so the website push would have to infer it from a field
  that means something else — and get it wrong for white-label, agent-only and
  publicity-shy owners).
- **Source:** Mojo website-rebuild thread 2026-09-09 (Ben Wood → Gareth); the
  agreed Res → Payload contract needs a defensible answer to "which villas does
  the site get?". 275 villas are on the live site today (Yoast sitemap,
  2026-09-09).
- **Files touched (when built):**
  - `django_res/properties/models/property.py:22-35` — `status` and `channel`.
  - `django_res/properties/enums.py:6-16` — `PropertyStatus` (DRAFT / ACTIVE /
    ARCHIVED), `PropertyChannel` (DIRECT / AGENT / WHITE_LABEL / INTERNAL).
  - `django_res/properties/services/lifecycle.py:31` —
    `PropertyLifecycleService.activate` / `.archive` / `.restore`.
  - `django_res/properties/views/property.py:167-182` — the matching action
    endpoints.
  - `django_res/properties/serializers/property.py:199` —
    `PropertyWriteSerializer` (where the new flag becomes writable).

## Problem

Neither existing field means "publish to the marketing site":

- **`status`** is a bookability lifecycle. `ACTIVE` means the villa can be
  quoted and booked. Plenty of ACTIVE villas should not appear on
  villacollective.com — an owner who does not want a public listing, a villa
  held for repeat guests only, one mid-onboarding whose copy is not ready.
- **`channel`** is the commercial route. `WHITE_LABEL` and `AGENT` villas are
  live and bookable but are precisely the ones that should *not* be on the
  public site — and `INTERNAL` is a third thing again.

Inferring publication from either produces the wrong answer in both
directions, and the mistake is not symmetrical: listing a villa that should be
private is a client-relationship problem, not just a bug.

There is also no way to express **un-publishing**. If the push simply stops
sending a villa, the site cannot tell "no longer published" from "no changes
this cycle" or "the push is broken". Absence must never be the signal.

And `ARCHIVED` is not deletion (per the repo's no-soft-delete principle, an
archived villa is a real row with real history). Its page has accumulated
inbound links and search equity that a 404 throws away.

## Proposed fix

1. **`Property.publish_to_website = models.BooleanField(default=False)`** —
   one explicit gate, independent of `status` and `channel`, writable through
   `PropertyWriteSerializer` and surfaced in the FE Settings tab. Default
   `False` so a newly-created villa is never published by accident; publishing
   is a deliberate act.

2. **The website push is gated on this flag alone.** Not on `status`, not on
   `channel`. Staff can reason about one checkbox.

3. **Un-publishing is an explicit event on the wire**, not silence: the push
   carries the villa with the flag flipped, so the site can retire the page
   deliberately.

4. **Archiving implies un-publishing**, and the site 301s the retired page to
   its destination hub (`/{region-slug}/`) rather than 404ing.
   `PropertyLifecycleService.archive` is the natural hook.

⚠️ **Open decision:** whether `publish_to_website` is a pure staff toggle, or
whether `archive` forcing it false should be irreversible on `restore`. The
conservative default — `restore` leaves the flag false and re-publishing is a
second, deliberate action — is what this ticket proposes.

## Acceptance

- A newly-created property has `publish_to_website=False`. (test)
- The website push includes a villa iff `publish_to_website` is true —
  independent of `status` and `channel`, verified across the matrix. (test)
- Flipping the flag false enqueues a push carrying the false value; it does
  not merely stop pushing. (test)
- `PropertyLifecycleService.archive` sets the flag false and enqueues one
  push; `restore` does not set it back true. (test)
- Zoho pushes are unaffected by the flag — the CRM gets every villa
  regardless. (test)

## Dependencies

- **Feeds GAP-106** (the website push) — that ticket consumes this gate.
- Independent of GAP-104; both are prerequisites for the same contract.
- **SMELL-001** (archived vs status) — adjacent; check it before adding a
  fourth lifecycle-adjacent concept to `Property`.
