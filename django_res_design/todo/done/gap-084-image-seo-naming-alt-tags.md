# GAP-084 — SEO image naming + alt tags (villa/country/region structure, through to WP)

> **✅ SUPERSEDED (2026-09-16) — merged into [GAP-106](../gap-106-res-to-website-push.md)** as
> §"Merged from GAP-084". Image SEO naming + alt text is what enriches the push's gallery (unit 2); how images reach the site is the question the push itself answers. Nothing was decided or built by the
> merge; the open work continues there.
>
> _Original ticket preserved below for context._

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

## Problem — current state (as-built)

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

## Sketch (to be designed properly once the WP question is answered)

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

## Open questions (gate the design)

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

## Acceptance (draft)

- New uploads land with `{country}-{region}-{villa}-{n}`-style keys; alt text
  defaults derived, editable, exposed in the API.
- Legacy GUID images get alt text (backfillable from the pure function — no
  binary touch needed).
- WP-facing answer documented: either the feed carries alt/filename, or a
  one-off re-import runbook exists, or we've explicitly told Ben which half
  we're shipping.

## Dependencies

- **GAP-012** (S3 hosting) — key shape, `AWS_S3_FILE_OVERWRITE=False`
  suffixing, legacy flat `properties/legacy/<guid>` keys.
- [GAP-082 ✅](gap-082-zoho-villa-push.md) (Zoho villa push, done
  2026-07-27) — candidate carrier for image URL + alt if the WP feed rides
  Zoho Flow; today it sends `hero_image_url` only.
- **Not covered:** image resizing/variants/CDN (out of scope, as in GAP-012).
