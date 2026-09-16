# GAP-106 — Res → website push (villa content reaches the site by hand), with its slug, publication-gate and image-SEO prerequisites

> **Scope widened 2026-09-16 (todo consolidation):** this is now the single
> ticket for the Res side of the Mojo website rebuild. It absorbs **GAP-104**
> (slug immutability + history → unit 6), **GAP-105** (`publish_to_website`
> gate → unit 7) and **GAP-084** (image SEO naming + alt text → unit 8); each
> one's full text is kept as a "Merged from" section at the end. All four
> were held on the same go-ahead from Nick and had no consumer outside this
> push. The open questions for Mojo stay separate, in **Q-026** (now also
> covering Q-027), so they can close on Mojo's answer.

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

### 6. Slug immutability + history (was GAP-104)

Drop `slug` from the property write shape, add a `:reslug` action and an
append-only `PropertySlugHistory`, and emit `previous_slugs` in unit 1's
payload. Lands **before** unit 1 goes live — it is what makes "edits in Res
never move a URL" true. Detail, the uniqueness trap for retired slugs and the
open `Region.slug` question: §"Merged from GAP-104".

### 7. Publication gate (was GAP-105)

Explicit `Property.publish_to_website` (default `False`) as the only gate,
with un-publish as an event on the wire. Lands before unit 4 (backfill), which
consumes it. Check SMELL-001 first. Detail: §"Merged from GAP-105".

### 8. Image SEO naming + alt text (was GAP-084)

`{country}-{region}-{villa}-{n}` for the stored filename and the alt text,
carried on unit 2's gallery. Enrichment — lands after unit 2. ⚠️ If the alt
text is wanted on the **current** WordPress site before the rebuild ships
(Ben called it the higher-value half), this unit can be split back out: its
gating question — how do images reach WP today? — is in §"Merged from
GAP-084". Out of scope as before: resizing, variants, CDN.

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
- Unit 6 (was **GAP-104**, slug immutability + history) — supplies
  `previous_slugs`.
- Unit 7 (was **GAP-105**, `publish_to_website`) — supplies the gate for
  unit 4.
- Unit 8 (was **GAP-084**, image SEO naming + alt tags) — enriches unit 2
  afterwards; depends on **GAP-012** (S3 key shape).
- **Q-026** (field ownership matrix) — must be settled before unit 1's field
  list is final.
- **GAP-096 / GAP-082** — the coordination pattern this follows (URL from the
  external party, env var, backfill ordering).
- The WordPress enquiry path (`wp-enquiry-cutover.md`,
  `wp-enquiry-handoff/`) is **independent** and ships first: the new site is
  not expected live until mid-to-late January, well after Res.

---

## Merged from GAP-104 — Property slug is freely mutable and un-historied (live public URLs move silently)

> _Folded in 2026-09-16 (todo consolidation). The standalone ticket is closed as
> [GAP-104](done/gap-104-property-slug-immutability-and-history.md); the text below is that ticket as it stood, headings
> demoted one level. A reference to GAP-104 elsewhere now means this section._

- **Severity:** 🟠 Gap (a villa rename can silently move a live public URL,
  and nothing records the old value, so no 301 can be minted — the page
  404s and its link equity is lost).
- **Source:** Mojo website-rebuild thread 2026-09-09 (Ben Wood → Gareth),
  agreeing the Res → Payload villa push. The contract rests on "Res proposes
  the slug, the site owns the URL, and edits in Res never move a URL"; today
  nothing on our side upholds the second half of that.
- **⚠️ 2026-09-11 loader audit:** the legacy loader writes `Property.slug`
  as the full WordPress URL (`https://www.villacollective.com/<region>/<villa>`,
  294/294 live villas) — BUG-030 §1 fixes the loader to a real slug. Build
  the history table after that lands, or it inherits 294 URL-shaped "slugs".
  **✅ Landed 2026-09-15 (BUG-030 U1):** the loader now writes
  `slugify(last URL path segment)` (fallback `slugify(name)`) + `-{Id}`, never
  doubling an id the segment already ends in — e.g. `agios-isavros-438`.
- **Files touched (when built):**
  - `django_res/properties/models/property.py:18` — `slug =
    models.SlugField(max_length=255, unique=True)`.
  - `django_res/properties/serializers/property.py:199-227` —
    `PropertyWriteSerializer.Meta.fields` includes `"slug"` and the class
    declares **no** `read_only_fields` (unlike the list/detail serializers at
    :117 and :178).
  - `django_res/properties/services/zoho_payload.py:227` —
    `build_property_payload` already emits `slug`.
  - `django_res/properties/views/property.py` — new `:reslug` action, on the
    existing `:activate` / `:archive` / `:restore` pattern.
  - New: `PropertySlugHistory` model + migration.

### Problem

Villa URLs on villacollective.com are `/{region-slug}/{villa-slug}` — 275 of
them, verified against the live Yoast sitemap on 2026-09-09. Under the agreed
push contract those two segments are **our** data, published to a site that
owns the URL but cannot invent history it was never told about.

Three things are missing:

1. **`slug` is freely writable.** `PATCH /api/properties/{id}` accepts a new
   slug like any other field. A staffer fixing a typo in a villa name can
   change the slug in the same request, with nothing in the UI or the API
   signalling that a live public URL is about to move.

2. **Nothing records the outgoing value.** `AuditedModel` emits a field diff,
   but there is no queryable "what slugs has this villa had" surface to build
   a redirect map from, and no carrier for it on the wire.

3. **The change propagates.** `build_property_payload` already ships `slug`,
   so a silent edit reaches the website on the next push, the new URL appears,
   and the old one 404s with no redirect.

This is **asymmetric with `status`**, which the same serializer already
protects — its docstring reads: *"`status` is not directly writable here —
lifecycle changes go through the `:activate` / `:archive` / `:restore` action
endpoints."* A slug change is a state change with consequences beyond the row,
for exactly the same reason, and deserves the same treatment.

Note `factories.py:184` derives `slug = slugify(name)`. That is correct for
seed data; the production rule is that the coupling exists **only at
creation**.

### Proposed fix

1. **Drop `"slug"` from `PropertyWriteSerializer.Meta.fields`.** Settable on
   create, immutable through the ordinary write path thereafter.

2. **Add `POST /api/properties/{id}:reslug`** on the established action-endpoint
   idiom: takes the new slug, validates it, appends the outgoing value to
   history, and bumps the property so exactly one push goes out. The endpoint
   is the place to put the "this will change the website URL" warning in the
   FE.

3. **New `PropertySlugHistory(property, slug, changed_at, changed_by)`**,
   append-only. Consistent with the no-soft-delete principle: this is a record
   of what happened, not a graveyard of deleted rows.

   ⚠️ **Design point to settle, not assumed here.** A retired slug must never
   be re-issued to a *different* villa, or a stale 301 will point at the wrong
   page. A plain `unique=True` on the history table does not give that — the
   check has to span live slugs *and* history. Two options:

   - **(a)** Uniqueness enforced in the `:reslug` service against both tables,
     plus a test. Boring, no schema gymnastics — the KISS default, and what
     this ticket proposes.
   - **(b)** Collapse to a single `PropertySlug` table with an `is_current`
     flag and one unique constraint doing all the work. Cleaner invariant,
     but it moves `Property.slug` off the model and touches every reader.

   Take (a) unless the reader count makes (b) obviously cheaper when the work
   is actually opened.

4. **Carry `previous_slugs` (ordered, oldest first) on the wire**, so the site
   mints its redirects from our history rather than keeping a parallel copy.
   ⚠️ Which builder this lands in depends on the allow-listed **website**
   payload (proposed in the 2026-09-09 rules note, not yet filed as its own
   ticket — the Zoho builder carries owner contact PII and must not be reused
   for a public site): the website consumer needs `previous_slugs`, Zoho does
   not. If it is added to `build_property_payload` in the interim, check whether it
   needs the gated-bump treatment GAP-091 used for a new villa block rather
   than assuming Limitless tolerates an unknown key.

### Acceptance

- `PATCH /api/properties/{id}` carrying a `slug` key leaves the slug unchanged
  and does not error. (test)
- `POST /api/properties` still accepts an explicit slug on create. (test)
- Renaming via `name` / `display_name` never changes `slug`. (test)
- `:reslug` changes the slug, writes exactly one history row, and enqueues
  exactly one villa push. (test)
- A slug held by another villa **or present in any villa's history** is
  rejected. (test)
- The payload carries `previous_slugs` oldest-first; a villa never re-slugged
  sends `[]`. (test)

### Dependencies

- **Blocks** the Res → Payload villa push (Mojo rebuild — Nick had not given
  the go-ahead as of 2026-09-09). The "edits in Res never move a URL"
  guarantee is this ticket.
- **GAP-103** (region/country edits never re-push) — related, one level up.
  The villa URL's *first* segment is the region slug, so a region re-slug
  moves every villa URL under it (up to 64 for Corfu). GAP-103 makes the
  region push exist; this ticket covers only the villa segment.
- **GAP-084** (image SEO naming + alt tags) — same theme: website-facing SEO
  surface is Res-owned data.

### Open question

Does `Region.slug` need the same immutability + history treatment? The blast
radius is larger (one region re-slug moves every villa URL beneath it), so
probably yes — but scope it separately once GAP-103 has made region pushes
exist at all. Related: `Region.slug` is unique **per country** while the
website's destination namespace is flat at the root, so two same-slug regions
in different countries would collide on the site. Worth checking whether any
exist today.

---

## Merged from GAP-105 — No publication gate for the public website (`status` and `channel` both mean something else)

> _Folded in 2026-09-16 (todo consolidation). The standalone ticket is closed as
> [GAP-105](done/gap-105-no-website-publication-gate.md); the text below is that ticket as it stood, headings
> demoted one level. A reference to GAP-105 elsewhere now means this section._

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

### Problem

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

### Proposed fix

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

### Acceptance

- A newly-created property has `publish_to_website=False`. (test)
- The website push includes a villa iff `publish_to_website` is true —
  independent of `status` and `channel`, verified across the matrix. (test)
- Flipping the flag false enqueues a push carrying the false value; it does
  not merely stop pushing. (test)
- `PropertyLifecycleService.archive` sets the flag false and enqueues one
  push; `restore` does not set it back true. (test)
- Zoho pushes are unaffected by the flag — the CRM gets every villa
  regardless. (test)

### Dependencies

- **Feeds GAP-106** (the website push) — that ticket consumes this gate.
- Independent of GAP-104; both are prerequisites for the same contract.
- **SMELL-001** (archived vs status) — adjacent; check it before adding a
  fourth lifecycle-adjacent concept to `Property`.

---

## Merged from GAP-084 — SEO image naming + alt tags (villa/country/region structure, through to WP)

> _Folded in 2026-09-16 (todo consolidation). The standalone ticket is closed as
> [GAP-084](done/gap-084-image-seo-naming-alt-tags.md); the text below is that ticket as it stood, headings
> demoted one level. A reference to GAP-084 elsewhere now means this section._

**Severity:** gap (SEO improvement — "another tick in the box", not a
game-changer; Ben's words).

**Status:** ⬜ captured, not designed. One open investigation gates the design:
how do villa images actually reach WP today (see Open questions).

**Source:** Ben Wood (mojo media, `ben@mojomedia.co.uk`) email thread
2026-06-25 with Gareth + Nick. Ben noticed res2 renames images after upload
(to meaningless names) and asked whether res3 can instead impose a naming
structure — **both the stored file name and the alt tag that pushes through
to WP** — piecing together villa name, country and region, e.g.
`greece-corfu-villa-melissonia-2` / `-3` / `-4`…

**Motivation (Ben, follow-up same day):** SEO / organic reach. The **alt tag
is the higher-value half** — it "should filter into the images already loaded
onto WP" without touching binaries. Renamed *files* only help WP if WP
re-imports them; Ben's stated worst case is "remove and import all the
properties images again, which may or may not be worth the effort."

### Problem — current state (as-built)

- `properties.PropertyImage` (`properties/models/images.py`) has `name`
  (blank CharField), `description`, `kind`, `sort_order` — **no `alt_text`
  field** and nothing derives a structured label.
- `image = ImageField(upload_to="properties/%Y/%m/")` — fresh uploads keep
  whatever filename the browser sent (plus dedupe suffixing;
  `AWS_S3_FILE_OVERWRITE=False` on staging/prod per GAP-012).
- All ~12.3k legacy images are **GUID-named** (`properties/legacy/<guid>.jpg`
  — legacy `VillaPropertyImages.Name` values are GUIDs, see GAP-012). Zero
  SEO value; this is exactly the res2 behaviour Ben is complaining about.
- The building blocks for the label all exist:
  `Property.name` + `Property.region` → `Region.slug` / `Region.name` →
  `Country.name`/`iso2` (`properties/models/geo.py`; Region already carries a
  per-country-unique `slug`).
- **No res3 → WP image path exists.** WP integration today is inbound only
  (WP enquiry intake endpoint); outbound push is Zoho Flow
  (GAP-081 done; GAP-082 villa push done 2026-07-27) — Zoho, not WP. So
  "pushes through to WP" has no wire to ride yet.

### Sketch (to be designed properly once the WP question is answered)

1. **Derived SEO slug** per image:
   `{country}-{region}-{property-name}-{n}` — slugified, `n` from
   `sort_order` (or stable per-image ordinal). Pure function in `properties`,
   unit-tested; reuse `Region.slug`, slugify the rest.
2. **`alt_text` on `PropertyImage`** — stored column, defaulted from the
   derived slug (human-readable variant, e.g. "Villa Melissonia, Corfu,
   Greece — photo 2"), staff-overridable via the existing image endpoints/FE
   dialog. Alt text ≠ filename: alt should be readable prose, not the
   hyphen-slug.
3. **Filename**: apply the slug at upload time via `upload_to` callable
   (rename on the way in — the inverse of res2's rename-to-garbage). Existing
   S3 objects are *not* renamed in v1 (S3 rename = copy+delete migration over
   ~13k objects; only worth it if WP actually re-imports — Ben's
   "may or may not be worth the effort").
4. **WP hand-off**: whatever feed eventually pushes villas/images to WP
   (GAP-082's Zoho villa payload, a WP REST push, or a manual re-import)
   carries `image_url` + `alt_text` + the SEO filename.

### Open questions (gate the design)

1. **How do villa images get onto WP today?** (Manual upload by mojo? Feed
   from res2?) Determines whether alt text can "filter into images already
   loaded" automatically or whether that's a WP-side job for Ben. Ask
   Ben/Nick — also clarifies whether the file-rename half is worth doing at
   all, or alt-text-only ships the SEO value.
2. **Slug stability**: villa renamed / region re-parented / images reordered —
   do filenames (and alt) re-derive (URL churn on WP) or freeze at upload?
   Lean: freeze filename, re-derive alt default.
3. Does the GAP-082 villa payload grow an `images` array (URL + alt) so
   Zoho/WP gets this for free? *(2026-07-29 update: GAP-082 landed 2026-07-27
   carrying a single `hero_image_url`
   — `properties/services/zoho_payload.py:261` — no images array, no alt.
   The question narrows to: extend that payload, or is the WP hand-off a
   different wire entirely? Still gated on open question 1.)*

### Acceptance (draft)

- New uploads land with `{country}-{region}-{villa}-{n}`-style keys; alt text
  defaults derived, editable, exposed in the API.
- Legacy GUID images get alt text (backfillable from the pure function — no
  binary touch needed).
- WP-facing answer documented: either the feed carries alt/filename, or a
  one-off re-import runbook exists, or we've explicitly told Ben which half
  we're shipping.

### Dependencies

- **GAP-012** (S3 hosting) — key shape, `AWS_S3_FILE_OVERWRITE=False`
  suffixing, legacy flat `properties/legacy/<guid>` keys.
- [GAP-082 ✅](done/gap-082-zoho-villa-push.md) (Zoho villa push, done
  2026-07-27) — candidate carrier for image URL + alt if the WP feed rides
  Zoho Flow; today it sends `hero_image_url` only.
- **Not covered:** image resizing/variants/CDN (out of scope, as in GAP-012).
