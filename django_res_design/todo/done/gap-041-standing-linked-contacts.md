> **✅ RESOLVED (2026-06-23)** — Shipped on local `main` (unpushed) via
> feat/gap-040-041 (B3 `1daf9f2`, B4 `4714f17`, F2 `11f77da`).
> `accounts.PersonRelationship` is a directed `(from_person, to_person, kind)`
> row with a DB no-self-link `CheckConstraint` + `(from,to,kind)` unique. One
> source-of-truth row is rendered with an **inverse label** on the reverse
> profile (CHILD↔PARENT, PA→Principal; symmetric kinds self-inverse) — no mirror
> row. Kinds: SPOUSE/PARTNER/CHILD/PARENT/PA/SIBLING/OTHER. `Person.merge` folds
> links (drops self-links, duplicates, **and mirrors**, per-instance so the audit
> trail survives); `anonymize()` deletes them. Surfaced at
> `/contacts/{id}/relationships` (both directions, one query) and a "Linked
> contacts (N)" accordion reusing the GAP-027 picker + inline-create. Distinct
> from per-booking `BookingGuest` roles, as required.

# GAP-041 — Standing linked contacts (spouse / child / PA)

- **Severity:** Gap (backend model + frontend) — new area, not in spec
- **Source:** 2026-06-17 owner Loom ("link contact — spouse, child, PA, that
  kind of thing") + the mockup at https://vc-new-res-system.netlify.app/ →
  **New Quote → "Linked contacts (N)"** accordion.
- **Status:** Open — needs a model decision; distinct from per-booking guests.
- **Files:** new relationship model in `reservations/` (Guest) or `accounts/`
  (Contact); serializer; FE accordion on the profile/quote screen.

> ℹ️ **Entity decision resolved (2026-06-18):** the "which entity — `Guest`,
> `Contact`, or both" question below is settled by **GAP-045** — a unified
> `accounts.Person`. Model this as `PersonRelationship` (Person↔Person); the
> open calls are the relationship `kind` set and symmetry/inverse.

## Problem

The owner wants standing person-to-person links on a client profile (spouse,
child, PA) that persist **across** bookings so the sales team has the full
relationship picture when quoting. Today the only multi-person construct is the
per-booking `BookingGuest` through-model with trip roles (`LEAD` /
`CO_TRAVELLER` / `PAYER` / `CC_ONLY`) — those describe a person's function on
*one* booking, not a durable relationship between two clients.

## Proposed fix

Add a directed/labelled relationship between customer records — e.g. a
`GuestRelationship` (or `ContactRelationship`) with `from`, `to`, and a `kind`
(SPOUSE / CHILD / PA / OTHER). Render the mockup's "Linked contacts" accordion on
the profile and quote-overview screens; allow linking an existing record or
creating + linking inline (reuse the picker pattern from
[GAP-027](gap-027-inline-contact-creation-primary-convention.md)).

**Decisions to settle:**
- **Which entity** holds relationships — `Guest`, `Contact`, or both — aligned
  with the entity chosen in [GAP-040](gap-040-customer-tags-taxonomy.md) and
  [GAP-042](gap-042-customer-360-profile-view.md).
- **Symmetry/inverse** — is "spouse" auto-reciprocal; does "PA" need a direction.
- **Relationship to `BookingGuest`** — keep separate (standing vs. per-trip); a
  linked PA may be added as a `CC_ONLY` on a specific booking, but the link
  itself is durable. Do not conflate.

No soft delete — links are added/removed directly; audit the change.

## Acceptance

- A client can be linked to another with a typed relationship; the link shows on
  both profiles and survives across bookings.
- Linking does not create duplicate guest/contact rows (reuse + advisory dedup).
- Quality gate green.

## Dependencies

- [GAP-042](gap-042-customer-360-profile-view.md) (renders the accordion),
  [GAP-040](gap-040-customer-tags-taxonomy.md) (entity choice + PA tag overlap),
  [GAP-027](gap-027-inline-contact-creation-primary-convention.md) /
  [GAP-029](gap-029-contact-required-name-fields-divergence.md) (inline-create
  + name-field rules).
