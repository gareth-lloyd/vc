# GAP-119 — One writer per CRM module: objects are created on their own endpoint, embedded only to link

- **Severity:** 🟠 Gap (architectural principle, retro-fitted). Nothing in
  **res** is broken by its absence — the damage is all CRM-side, and some of
  it is live: CHECK-004 item 6 attaches bookings to the wrong villa and item 7
  mints an unmatchable "Unknown" contact per erased-person booking. The
  standing cost is duplicate and diverging records, and a class of bug that
  keeps being re-filed one flow at a time.
- **Source:** user decision, 2026-09-20, while planning GAP-096. It
  generalises the objection GAP-096 already made to its own problem — "two
  writers to the Accounts module, permanently" — into a rule that covers
  every module.
- **Status:** principle **adopted**; the first half is **built** (GAP-096
  landed `organisation` as its own kind, dark). The thinning half is not
  started and is deliberately sequenced behind Limitless-side work — see
  §"Why thinning must follow, never lead".

## The principle

**An object is created and updated only through its own endpoint.**

Where that object appears inside another object's payload, it carries only
enough to resolve a link — `RES_ID`, plus `id`/`name` for legibility — and a
lookup miss leaves the field unlinked rather than triggering a create.

### Scope: objects that have an endpoint

The rule applies to the kinds in `ZOHO_FLOW_KINDS`
(`django_res/integrations/services/zoho_flow.py:41`):

| Kind | Model | Owner payload |
| --- | --- | --- |
| `organisation` | `accounts.Organisation` | `build_organisation_payload` |
| `contact` | `accounts.Person` | `build_person_payload` |
| `villa` | `properties.Property` | `properties/services/zoho_payload.py` |
| `enquiry` | `reservations.Enquiry` | `reservations/services/zoho_payload.py` |
| `quote` | `reservations.Quotation` | " |
| `booking` | `reservations.Booking` | " |

**Everything else is deliberately exempt.** `region`, `country`, the extras
catalogue, features and room attributes have **no endpoint of their own**, so
their embedded snapshot *is* the delivery route — it is the only way that data
reaches Zoho at all, and it must stay fat. This is not an oversight in the
principle; it is the reason chasing the `region` URL matters (GAP-096
§"Merged from GAP-103"). If a `region` kind is ever built, `region` moves from
the exempt column to the scoped one and its embeds thin with the rest.

## Why

Two writers to one CRM module is not a transitional state that resolves
itself — it is a permanent source of divergence:

- **Duplicates.** Two creators, two match keys, two records. The Accounts
  module has exactly this today: `limitless_upsert_villa` creates an Account
  from `contacts[role=management_company].organisation`, and nothing else
  does, so agencies (which have no villa) never become Accounts at all.
- **Staleness with no owner.** An embedded copy only refreshes when its
  *parent* is pushed. GAP-096 Unit 2 documents the live instance: renaming an
  organisation refreshes its member contacts (there is a fan-out) but not the
  villas it manages (there is none), and adding the missing fan-out would cost
  one villa push per managed property.
- **PII spread.** An embedded copy carries whatever the consuming Flow needs,
  so personal data lands in modules that have no business holding it —
  CHECK-003 item 9 is this exact complaint about emails and phones on
  Products.
- **Invisible rejection.** Per GAP-097 a push is `IN_SYNC` on any HTTP 2xx,
  so a CRM-side rejection of a duplicate or malformed inline create is
  invisible to us. The fewer writers, the fewer such blind spots.

## What this subsumes

Open items that are all the same bug wearing different hats:

- **CHECK-001 item 6** — the contact flow sets `Contact_Type: "Agency"` as
  text with no `else`, and its agency-address fallback is never withdrawn, so
  unlinking an agency in res leaves both in the CRM forever. A real Account
  link would have nothing to withdraw. (Item 2's agency-name fallback is the
  same embed doing the same duty.)
- **CHECK-002 item 2** — the enquiry flow writes to Contacts.
- **CHECK-003 §Dependencies (GAP-096)** — the villa flow's inline Account
  create/update should become a lookup by `RES_ID`, and *"a created Account is
  the bug, not the fallback"* — CHECK-003's own words, and the clearest
  statement of this principle anywhere in the tickets. Note this is **not**
  item 2: item 2 only fixes *which* management company is picked (it ignores
  `end_date` and `is_primary`), which is orthogonal and can land first.
- **CHECK-003 item 9** — person email/phone embedded on Products.
- **CHECK-004 item 6** — the `DUPLICATE_DATA` branch adopts a colliding
  Product and attaches the booking to the *wrong* villa. It is reachable only
  because the booking flow creates Products at all: on a `RES_ID` miss it
  mints a stub villa from the thin `region` object the booking payload
  carries. Under the principle the miss leaves the booking unlinked and the
  duplicate branch becomes unreachable.
- **CHECK-004 item 7** — a third writer into Contacts, which on an erased
  person (no `RES_ID`) creates an unmatchable "Unknown" contact.

Under the principle each has the same fix shape: the flow stops writing the
foreign module and resolves a link by `RES_ID`; res stops sending the fields
that only existed to feed that write.

## Why thinning must follow, never lead

Every embedded copy listed below is currently **load-bearing on the Limitless
side** — their Flow reads those fields to do the inline create. Removing them
first would not enforce the principle, it would break the flow and leave the
CRM with emptier records than before.

So each row is sequenced: **(a)** res pushes the object on its own endpoint
(so the Account/Contact/Product exists), **(b)** Limitless switch that flow to
a `RES_ID` lookup and confirm, **(c)** res thins the embed. Step (c) is a
one-function change each time; the whole cost is in (b), which is theirs.

| Embed | Where | Thin to | Gated on |
| --- | --- | --- | --- |
| `agency` on the contact payload | `integrations/services/zoho_payloads.py` `_agency_payload` | `RES_ID`, `id`, `name` | CHECK-001 items 2 and 6 |
| `contacts[].organisation` on the villa payload | `properties/services/zoho_payload.py` `_organisation_summary` | `RES_ID`, `id`, `name` | CHECK-003 §Dependencies (GAP-096) |
| `contacts[].person` email/phone on the villa payload | `properties/services/zoho_payload.py` `_person_summary` | drop `primary_email`/`primary_phone` | CHECK-003 item 9 |
| villa + person references inside enquiry / quote / booking | `reservations/services/zoho_payload.py` | `RES_ID`, `id`, `name` | CHECK-004 items 6 and 7 |

Both `_agency_payload` and `_organisation_summary` carry an inline comment
saying they are embeds whose thinning must follow the switch (added by
GAP-096). Those comments point at
[GAP-096](gap-096-organisation-zoho-push-kind.md), which delegates here — the
extra hop is deliberate: GAP-096 shipped before this ticket existed, and a
comment that dangled at three commits would have been worse than one that
forwards.

Note `_person_summary` already carries a thin three-key `agency` reference —
the in-codebase precedent for a link-only embed, and the shape the rest should
converge on.

## Acceptance

Per module, as each one switches:

- The foreign module's records are created only by pushes of that module's own
  kind. (verified Zoho-side)
- A lookup miss inside another flow leaves the field unlinked and does **not**
  create a record. (verified Zoho-side — this is the behaviour change, and the
  one worth checking explicitly, since "create on miss" is the current safety
  net)
- The embed carries `RES_ID` + `id`/`name` and nothing that exists only to
  feed a create. (test, per payload module)

## Dependencies

- **GAP-096** — built the first instance (`organisation` as its own kind) and
  is where the principle's consequence was first recorded.
- **CHECK-001 (items 2, 6), CHECK-002 (item 2), CHECK-003 (§Dependencies,
  item 9), CHECK-004 (items 6, 7)** — the Limitless-side half of every row in
  the table above. Each is closed by *verifying*, not building.
- **GAP-097** — until a push reports real CRM-side status, "did the lookup
  find it?" can only be answered by reading Zoho, which is why every switch
  above is a push-and-read verification.
- **Q-026** — if hub pages are ever Res-fed, `region` gains an endpoint and
  moves into scope.
