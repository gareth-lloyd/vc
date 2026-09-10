# GAP-106 — No Res → website push (villa content reaches the site by hand)

- **Severity:** 🟠 Gap (villa content is authored in Res — descriptions,
  other-information, rooms, features — and hand-copied to the website, so the
  two drift the moment either is edited; GAP-090/091/092 keep widening the
  gap they have to close by hand).
- **Source:** Mojo website-rebuild thread 2026-09-09 (Ben Wood → Gareth). Ben
  proposed either continuing manual sync or sharing one database; the agreed
  answer was neither — a push contract, with Res as the source of truth for
  villa content and the site owning presentation and URLs. **Absorbs** the
  separately-proposed "don't reuse the Zoho payload" footgun (now unit 1) and
  "gallery on the wire" (now unit 2).
- **Files touched (when built):**
  - New: `django_res/properties/services/website_payload.py` —
    `build_website_payload`.
  - `django_res/properties/services/zoho_payload.py:227` —
    `build_property_payload`, the **reference shape, not the thing to reuse**
    (see unit 1). Unchanged by this ticket.
  - `django_res/integrations/services/zoho_flow.py:97` —
    `register_zoho_flow(model, *, kind, build_payload, auto_push,
    ignore_update_fields)`; `ZOHO_FLOW_KINDS`.
  - `django_res/integrations/management/commands/zoho_backfill.py:51` —
    `KIND_ORDER = ("contact", "villa", "enquiry", "quote", "booking")`.
  - `django_res/properties/models/images.py:10` — `PropertyImage`
    (`kind`, `name`, `description`, `sort_order`, `is_active`).
  - `django_res/villacollective/settings/` — new webhook + env var, on the
    `ZOHO_FLOW_WEBHOOKS` pattern (env-only, `""` = disabled).

## Problem

Villa marketing content is increasingly authored in Res — description
sections, other-information tags and copy (GAP-091), room-level website
descriptions (GAP-092), features, capacity, rooms and beds. Today it reaches
villacollective.com only when Mojo copies it across by hand. Every one of
those tickets adds surface that has to be re-synced manually, so the drift
grows with the work.

The push machinery to fix this already exists — `register_zoho_flow` takes
`build_payload` as a parameter, so a second destination with a different
payload is a supported shape, not a rewrite.

## Proposed fix

Five units.

### 1. `build_website_payload()` — a new builder, allow-listed from empty

**Do not reuse `build_property_payload`.** It is correct for Zoho and wrong
for a public site: it carries `contacts[]` with owner names, primary emails
and phone numbers, plus `licence_number` and `channel`. A CRM is an
appropriate home for those; a Next.js build artifact on a public origin is
not, and a leak there is not recoverable by editing a page afterwards.

Build a **separate** function that starts empty and gains fields deliberately.
An allow-list, never a deny-list or a `include_contacts=False` flag on the
shared builder — the failure mode of a flag is that a future field is added to
the shared shape and silently ships to both.

Starting set (the site's villa page needs): `RES_ID`, `legacy_id`, `name`,
`display_name`, `slug`, `previous_slugs` (GAP-104), `region` (+ country),
`location`, `capacity`, `rooms`, `features`, `other_information`, description
sections, `publish_to_website` (GAP-105), `updated_at`.

Explicitly excluded: `contacts`, `licence_number`, `channel`, `extras`,
anything price- or commission-shaped.

### 2. Images — the full ordered gallery, **website only**

The Zoho payload's `hero_image_url` is **correct for Zoho** and stays exactly
as it is; a CRM record needs a thumbnail, not forty photos. This unit does not
touch `build_property_payload`.

The website payload carries the full gallery from `prop.images`, filtered to
`is_active`, in `Meta.ordering` (`sort_order`, `id`): URL, `kind`,
`sort_order`, and `name` / `description` as they stand today.

⚠️ **Decision inside this unit:** which `ImageKind`s the site receives.
`FLOOR_PLAN` is plausibly internal; `HERO` / `INTERIOR` / `EXTERIOR` /
`GALLERY` are clearly public. Settle it rather than shipping all five by
default.

Alt text and SEO filenames are **GAP-084**, which enriches this unit later —
the gallery ships without waiting for it.

### 3. Registration + dispatch

`register_zoho_flow(Property, kind="website", build_payload=build_website_payload,
…)` with its own webhook URL and env var.

⚠️ **Naming decision this forces:** the registry, its setting
(`ZOHO_FLOW_WEBHOOKS`) and `zoho_backfill` are Zoho-named end to end. A
`"website"` kind inside `ZOHO_FLOW_WEBHOOKS` is a misnomer that will mislead
the next reader. Either rename the machinery to something destination-neutral
(a mechanical but wide rename) or accept the misnomer with a comment. Decide
deliberately; do not let it happen by default.

Provenance rides along as it does for Zoho: `_meta` sibling + `X-Res-Env`
(GAP-102), so a dev push can never be mistaken for — or land as — a
production one.

### 4. Backfill

A `website` stage so the entire site can be rebuilt from Res on demand. This
is what makes "Res is the source of truth" a real claim rather than an
aspiration, and it is the disaster-recovery answer for the site.

### 5. Replay-safety and ordering

The receiver must tolerate the same push twice (the existing dedupe/ledger
pattern), and the payload carries `updated_at` so the site can ignore a push
older than what it already holds. Out-of-order delivery must not clobber newer
content.

## Acceptance

- `build_website_payload` output contains no `contacts` key, no
  `licence_number`, no `channel` — asserted by a test that fails on **any**
  owner-contact-shaped key, so a future field addition cannot slip through.
  (test)
- `build_property_payload` is byte-identical before and after this ticket.
  (test)
- The website payload carries every active image in `sort_order` with its
  `kind`; the Zoho payload still carries `hero_image_url` only. (test)
- A `Property` save enqueues one Zoho push and one website push, each with its
  own payload. (test)
- `X-Res-Env` and `_meta.source` are present on every website POST. (test)
- The backfill replays every published villa; unpublished villas are skipped
  (GAP-105). (test)
- Re-delivering an identical push is a no-op; a push with an older
  `updated_at` than the site holds is ignored. (test)

## Dependencies

- **Blocked on Nick approving the website rebuild.** As of 2026-09-09 Ben was
  waiting on the go-ahead; nothing here should be built before that. The
  shape is worth agreeing now so both sides can model against it.
- **GAP-104** (slug immutability + history) — supplies `previous_slugs`.
- **GAP-105** (`publish_to_website`) — supplies the gate for unit 4.
- **GAP-084** (image SEO naming + alt tags) — enriches unit 2 afterwards.
- **Q-026** (field ownership matrix) — must be settled before unit 1's field
  list is final.
- **GAP-096 / GAP-082** — the coordination pattern this follows (URL from the
  external party, env var, backfill ordering).
- The WordPress enquiry path (`wp-enquiry-cutover.md`,
  `wp-enquiry-handoff/`) is **independent** and ships first: the new site is
  not expected live until mid-to-late January, well after Res.
