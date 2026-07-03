> **✅ RESOLVED (2026-06-23)** — Shipped on local `main` (unpushed) via
> feat/gap-040-041 (B1 `baa69de`, B2 `36b2749`, F1 `c8fc246`).
> `accounts.Person.tags` is a fixed `PersonTag` `ArrayField` (10 tags; **"Repeat"
> excluded** → derived badge deferred to GAP-042). `save()` canonicalises to a
> sorted, de-duplicated set; the change is audit-tracked and **scrubbed from the
> trail on erasure** (Disability / Approach-with-care are special-category).
> Queryable via `?tags=vip,trade` (overlap, unknown tokens dropped). Surfaced on
> the contact profile: a checkbox-dialog editor + read-only chips (rail + Details
> tab). **Deferred:** read-only chips on the enquiry/quote client block (needs an
> enquiry/quotation serializer change beyond this ticket) and the curated/
> ops-editable taxonomy (Q-021).

# GAP-040 — Customer tags taxonomy

- **Severity:** Gap (backend model + frontend) — new area, not in spec
- **Source:** 2026-06-17 owner Loom ("we've got some tags … trade, [Nick's]
  friend, approach with care, disability … VIP") + the mockup at
  https://vc-new-res-system.netlify.app/ → **New Quote → client block** (a
  checkbox set on the client Internal Notes panel).
- **Status:** Open — needs a model-shape decision first.
- **Files:** new model in `accounts/` (Contact) or `reservations/` (Guest);
  serializer; FE chips on the enquiry/profile screens.

> ℹ️ **Entity decision resolved (2026-06-18):** the "which entity — `Guest`,
> `Contact`, or both" question below is settled by **GAP-045** — a unified
> `accounts.Person`. Tags hang off `Person`; the remaining open call here is
> shape (fixed choice set vs `Tag` lookup + through-table) and the
> derived-vs-manual question for "Repeat".

## Problem

Neither `Guest` nor `Contact` carries operator-applied tags today. The legacy
`ClientDetails` "Preferences & Notes" card appended selected preference names to
free-text `ClientNotes` (`ClientDetails.razor:696`) — lossy and unqueryable. The
owner wants first-class tags so the sales team sees the client's profile flags at
a glance and can filter on them.

## Proposed fix

Add a tag set to the customer record. **Seed taxonomy from the mockup:** VIP,
Repeat, Trade, PA, Nick's friend, Nick's network, Disability, Approach with care,
Past issues, Specific preferences, Time waster. Surface as checkboxes/chips on
the enquiry and customer-profile screens
([GAP-042](gap-042-customer-360-profile-view.md)).

**Decisions to settle before building:**
- **Model shape** — a fixed choice set on the model vs. a `Tag` lookup +
  through-table (the latter lets ops curate the list; coordinate with the
  feature-taxonomy approach in [Q-021](./q-021-defaults-and-feature-taxonomy.md)).
- **Which entity** carries them — `Guest` (booking-side traveller), `Contact`
  (CRM), or both. The Loom context is the sales/quote screen, which is
  guest-centric.
- **Overlap (avoid duplicate sources of truth):** "Repeat" is derivable from
  previous bookings (see [GAP-042](gap-042-customer-360-profile-view.md)) — make
  it a derived badge, not a manual flag. "PA" overlaps the linked-contact role
  in [GAP-041](gap-041-standing-linked-contacts.md) — decide tag vs.
  relationship. "Disability" / "Approach with care" may warrant
  retention/consent handling (cross-ref [Q-010](../q-010-guest-data-retention.md)).

No soft delete — tags are added/removed directly; audit-register the change set.

## Acceptance

- A customer can be tagged from the enquiry/profile screen; tags persist and are
  filterable.
- Tag changes are audited.
- Quality gate green.

## Dependencies

- [GAP-042](gap-042-customer-360-profile-view.md) (profile view consumes tags),
  [GAP-041](gap-041-standing-linked-contacts.md) (PA overlap),
  [Q-021](./q-021-defaults-and-feature-taxonomy.md) (taxonomy curation pattern),
  [Q-010](../q-010-guest-data-retention.md) (sensitive-tag retention).
