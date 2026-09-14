# GAP-104 — Property slug is freely mutable and un-historied (live public URLs move silently)

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

## Problem

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

## Proposed fix

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

## Acceptance

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

## Dependencies

- **Blocks** the Res → Payload villa push (Mojo rebuild — Nick had not given
  the go-ahead as of 2026-09-09). The "edits in Res never move a URL"
  guarantee is this ticket.
- **GAP-103** (region/country edits never re-push) — related, one level up.
  The villa URL's *first* segment is the region slug, so a region re-slug
  moves every villa URL under it (up to 64 for Corfu). GAP-103 makes the
  region push exist; this ticket covers only the villa segment.
- **GAP-084** (image SEO naming + alt tags) — same theme: website-facing SEO
  surface is Res-owned data.

## Open question

Does `Region.slug` need the same immutability + history treatment? The blast
radius is larger (one region re-slug moves every villa URL beneath it), so
probably yes — but scope it separately once GAP-103 has made region pushes
exist at all. Related: `Region.slug` is unique **per country** while the
website's destination namespace is flat at the root, so two same-slug regions
in different countries would collide on the site. Worth checking whether any
exist today.
