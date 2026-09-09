# GAP-090 — Description sections rebuilt to the legacy block set (sub/para pairs) + own tab

> **🟨 PARTLY BUILT (2026-08-12)** — an ad-hoc change off Nick's "we need some
> new fields" email landed on `main` (`1872df1c`, `892d09c2`, `9524e8ac`)
> before this ticket was read. It does **not** do the block-set rebuild, but it
> moves three things:
>
> - **Step 6's UI half is done.** `DescriptionSection.INTERNAL_NOTES` exists
>   (`properties/enums.py`, migration `properties/0005`), with API, a
>   staff-only UI group ("Not shown to guests"), exclusion from property
>   duplication, and `PropertyDescription` registered for audit so a Clear
>   leaves a tombstone. What remains of step 6 is **data**: the loader still
>   writes `Notes → FURTHER_INFO` (`loaders/properties.py:243`) and existing
>   `further_info` rows still need remapping.
> - **Step 5's "drop the hardcoded `bodies` keys" is done.** `bodiesFor()`
>   builds from the schema tuple; the tab strip renders `WEBSITE_SECTIONS`.
>   The file-ref line numbers below are pre-change.
> - **The enum swap is now much safer.** The SPA used to pin its own four-value
>   `z.enum` and parse strictly, so *any* section value it didn't know threw a
>   ZodError that React Query doesn't retry — collapsing the whole panel. That
>   is exactly what replacing the enum would have done to every property. It
>   now accepts any `section` string and filters to what it knows
>   (`isKnownSection`), so a backend-first landing degrades to "block not shown"
>   instead of an outage. Rendering the new blocks is still frontend work.
>
> Also note the same change fixed a body-less PUT wiping a section, and an
> `update_or_create` that discarded `updated_by`; the loader re-run this ticket
> calls for goes through `PropertyDescription` writes, so keep both in mind.

- **Severity:** 🟢 Gap (customer-facing parity — website copy). Backend +
  frontend + data-migration.
- **Source:** 2026-07-20 Nick screen-recording (`Recording-20260720_134424`,
  6m16s, reviewed 2026-08-11) — walkthrough of a Brian E property-onboarding
  session. Transcript `[01:09–02:05]` + recap `[04:00–04:09]`; legacy screen
  captured at `[01:48]`. **Answers Q-020** (same question, filed from the
  2026-06-11 transcript, unresolved for want of the legacy screen).
- **Files touched (best-guess):**
  - `django_res/properties/enums.py:104` — `DescriptionSection` (the enum to
    replace).
  - `django_res/properties/models/descriptions.py` — `PropertyDescription`
    (structure is right: one row per section, `UniqueConstraint(property,
    section)`; only the enum changes).
  - `django_res/properties/views/description.py:42` — validates
    `section.replace("-", "_")` against `DescriptionSection.values`.
  - `django_res/data_migration/loaders/properties.py:228–264`
    (`_write_descriptions`) — the concatenation to undo.
  - `django_res/data_migration/loaders/property_children.py:87–109`
    (`PropertyImageLoader`) — already reads
    `Interior1/2` + `Exterior1/2` as image captions; see the ⚠️ in step 3.
  - `frontend/src/features/properties/components/DescriptionsSection.tsx` —
    tab strip over `WEBSITE_SECTIONS` + the internal-notes group. (The
    hardcoded `bodies` keys this originally named are gone — see the banner.)
  - `frontend/src/features/properties/schemas.ts` — `WEBSITE_SECTIONS` /
    `DESCRIPTION_SECTIONS` / `isKnownSection`.
  - `frontend/src/features/properties/PropertyDetailLayout.tsx` — tab list, if
    Description is promoted to a top-level tab.
  - `frontend/src/i18n/locales/en/properties.json` —
    `descriptions.sections.*`.

## Problem

The public website renders villa copy as **discrete content blocks**, and
legacy models each block as a **short "sub" + a longer "para"**. Legacy
`property-detail/<id>/descriptions` (captured at `[01:48]`) has nine fields in
two columns:

| Left | Right |
|---|---|
| Web des 1 *(top larger text)* | Web des 2 *(opening para)* |
| Interior sub | Interior Para |
| Exterior Sub | Exterior Para |
| Location sub | Location Para |
| Video Url | — |

Both halves of each pair are prose — the "sub" is a lead-in sentence, not a
heading. Nick: *"if you could replicate that on the current one, that would be
great… I suspect it will need its own tab."*

Our `DescriptionSection` enum (`overview / house_rules / villa_info /
further_info / location / web_description`, plus `internal_notes` added
2026-08-12) is a different shape entirely: it
has no interior or exterior at all, and it **collapses the sub/para split**.
The loader makes that concrete — `_write_descriptions` (L247–254) reads
`WebDesc1`/`WebDesc2` and `Location1`/`Location2` and joins each pair with a
blank line (`"\n\n".join(...)`, the "PRESERVE ALL, 2026-07-06" decision), so
the two slots are already fused on import and cannot be split back out
reliably. Interior/exterior columns are not read at all.

Per the standing principle (customer-facing output matches legacy), this is a
parity break in the copy that sells the villas.

## Proposed fix

1. **Replace the enum** with the legacy block set:
   `web_des_1`, `web_des_2`, `interior_sub`, `interior_para`, `exterior_sub`,
   `exterior_para`, `location_sub`, `location_para`.
   `house_rules` stays (see GAP-094); `villa_info` leaves for the Features
   surface (GAP-091); `further_info` becomes property internal notes (below).

   ⚠️ **`house_rules` now has a runtime consumer** — GAP-094 shipped
   2026-09-09, so this is no longer just "keep the value in the enum".
   `reservations/models/booking.py::live_house_rules` filters
   `PropertyDescription` by `section=DescriptionSection.HOUSE_RULES`, and
   `Booking._house_rules_stamp` feeds the result into `_transition` on the
   first entry to `AWAITING_DEPOSIT`, where it lands on
   `Booking.house_rules_snapshot` — which is what every booking contract PDF
   renders from. It is the only *Python* reader of the value (the loader at
   `loaders/properties.py:221` is the only writer). If the rebuild renames the
   value, remaps the rows, or moves a property's rules under a different
   section, that filter silently returns nothing and confirmed bookings get a
   **contract with no house rules** — no error, no failed test unless one is
   written. Any migration that moves these rows must keep them reachable under
   whatever the new value is, and `test_house_rules_snapshot.py` must be
   re-run against it.

   ⚠️ **Grep the lowercase slug too — `HOUSE_RULES` does not find the
   frontend.** The value is spelled `"house_rules"` in
   `frontend/src/features/properties/schemas.ts` (`WEBSITE_SECTIONS`, which
   backs `isKnownSection`) and keyed in
   `frontend/src/i18n/locales/{en,el}/properties.json`. Since GAP-091,
   `propertyDescriptionSchema.section` is a deliberate `z.string()` and
   callers filter with `isKnownSection`, so an unrecognised section no longer
   throws — it is **silently not rendered**. That is the safer failure but the
   quieter one: a backend-first rename passes every Python test, raises
   nothing in the browser, and simply makes the house-rules editor vanish from
   the Descriptions tab. Move both halves together, and check the panel
   visually rather than trusting a green suite.

   Note also that the FE files `house_rules` under a constant named
   `WEBSITE_SECTIONS` ("guest-facing copy"). That predates GAP-094 and now
   reads wrong — house rules are contract-only and never shown online; the
   grouping is a staff-UI affordance, not a claim about publication. The whole
   properties API is staff-gated so nothing leaks, but the naming is worth
   correcting whenever this set is rebuilt.
2. **Video Url needs no work** — `Property.video_url` already exists
   (`models/property.py:39`) and the loader already maps legacy `VodeoUrl`
   (sic) onto it. Render it on the same tab for parity with the legacy screen.
3. **Loader** — stop concatenating: `WebDesc1 → web_des_1`,
   `WebDesc2 → web_des_2`, `Location1 → location_sub`,
   `Location2 → location_para`, and add the interior/exterior pairs.

   ⚠️ **The interior/exterior columns are found — and they are already being
   read for something else.** They live on the same
   `VillaPropertyImagesDescription` row this loader already joins
   (`loaders/properties.py:89–107`): `Interior1`, `Interior2`, `Exterior1`,
   `Exterior2` — the same 1/2 = sub/para shape as `WebDesc1`/`WebDesc2`. But
   `PropertyImageLoader` **already consumes all four as image captions**
   (`property_children.py:96–97, 106–109`), pairing each with its
   `IsInterior1/2` / `IsExterior1/2` flag, and `PropertyLoader`'s own comment
   records that as settled: *"Its Interior\*/Exterior\* columns are already
   migrated as image slot captions there; not read here."*

   So two readings of the same four columns are now in play — captions under
   the interior/exterior photos, or the prose blocks the legacy Descriptions
   screen shows at `[01:48]`. They may well be both (one text rendered beside
   its image), but **do not assume**: check the live villa page against a
   snapshot row before writing the mapping, and if it is genuinely one text
   serving two surfaces, say so explicitly rather than importing it twice
   under two names. **This is a spec-vs-code disagreement — surface it, don't
   pick a side.**
4. **Data migration** for already-imported rows: `overview → web_des_1`,
   `location → location_para`, `web_description → web_des_1`. The fused pairs
   cannot be split programmatically — the honest fix is a **re-run of the
   property loader** against the snapshot once the mapping is right, rather
   than a lossy string split.
5. **Frontend** — promote Description out of the Details tab into its own
   top-level tab, laid out as sub/para pairs in two columns mirroring legacy.
   ~~Drop the hardcoded `bodies` keys in favour of the schema constant so the
   set is defined in one place.~~ *Done 2026-08-12 — see the banner.*
6. **`further_info` → internal notes** — *UI half already built, see the banner;
   what's left is the loader mapping + a data migration of existing rows.*
   Nick `[03:48–04:00]`, recap
   `[04:22–04:31]`: *"what we need here is an internal notes box… that's just
   for our knowledge"*, and *"we can get rid of further info, just make it
   internal notes"*. Staff-only, never rendered publicly. Legacy `Notes` (the
   current `FURTHER_INFO` source, L242–243) is the right data to carry over.
   Kept in this ticket because it's the same UI surface and the same enum
   change — splitting it would force two coordinated landings.

## Acceptance

- `DescriptionSection` is the legacy block set; `views/description.py`
  validation and the frontend tab set derive from it (no second hardcoded
  list). (test)
- Loader writes each legacy column to its own section, no concatenation; a
  transform test pins each pair separately (style:
  `data_migration/tests/test_country_loader.py`). The existing
  `test_web_description_concatenates_both_parts` /
  `test_location_concatenates_both_parts` tests invert to assert the split.
- `reconcile_legacy` shows no new unexplained gaps; any expected loss recorded
  in `CUTOVER.md`.
- Description is a top-level property tab; each block is independently
  editable and clearable.
- Internal notes exist at property level and appear nowhere customer-facing.
  ✅ *already met — the remaining half is the `further_info` data remap.*
- Quality gate green (backend + frontend).

## Dependencies

- **Supersedes Q-020** — same question, now answered by the recording; Q-020
  is marked ⏸ superseded-pending and drops when this lands.
- **GAP-091** (villa info → tags) removes `villa_info` from this enum;
  the two want sequencing together to avoid a double enum migration.
  *Landed 2026-09-09 (GAP-091 shipped first):* the enum is now `overview /
  house_rules / further_info / location / web_description / internal_notes /
  other_information / rooms` (`section` widened to 32 chars, migration
  `properties/0007`). `other_information` and `rooms` are **not**
  Descriptions-tab sections (Features tab / GAP-092), so this ticket's block
  set replaces the first six only; the `further_info` → internal-notes data
  remap is still open here.
- **GAP-092** (room website description → property level) adds one more
  property-level prose block; fold into this tab's layout if both are live.
- Related: GAP-010 (spec areas reverse-engineered from the wrong codebase —
  the reason Q-020 distrusted the spec mapping in the first place).
- Requires the legacy prod snapshot (`ResSystem-prod`) to settle the
  interior/exterior double-read (step 3) and to re-run the loader. The column
  *names* no longer need discovery — they are `Interior1/2`, `Exterior1/2`.
