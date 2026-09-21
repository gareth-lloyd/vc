# GAP-090 — Description sections rebuilt to the legacy block set (sub/para pairs) + own tab, including the property-level rooms blurb

> **✅ RESOLVED (2026-09-21)** — local `main`, unpushed; 7 units on
> `feat/gap-090`. Absorbed GAP-092 ships with it.
>
> - **Unit 1** (`6544804d`) — `DescriptionSection` rebuilt to 13 values, one
>   per legacy column: `web_des_1/2`, `interior_sub/para`, `exterior_sub/para`,
>   `location_sub/para` join `overview`, `house_rules`, `internal_notes`,
>   `other_information`, `rooms`; `web_description`, `location`, `further_info`
>   are gone. Migration `properties/0010` remaps loaded rows (fused bodies land
>   in the *sub* slot; `further_info` merges into `internal_notes`, appending on
>   collision). `house_rules` untouched — the GAP-094 contract chain.
> - **Unit 2** (`13510a9f`) — the loader writes one section per column, no
>   `"\n\n"` fusing; reads `Interior1/2`, `Exterior1/2`; never overwrites a
>   staff-written `internal_notes`; a re-run drops a still-fused sub row only
>   when it can prove the body is its own.
> - **Unit 3** (`11fe46aa`) — `reconcile_legacy` expects **3 200** rows over 13
>   single-column groups (was 1 049); **CUTOVER §6i** is the re-run that splits
>   an already-loaded DB.
> - **Unit 4** (`1c3495c2`) — `Property.video_url` on the detail + write
>   serializers, audited. (Step 2's "needs no work" was wrong: the field was on
>   no serializer.)
> - **Unit 5** (`7063ade9`) — SPA block model (`DESCRIPTION_BLOCKS` +
>   `SINGLE_SECTIONS`), two-column sub/para editors, per-section button names.
> - **Unit 6** (`4cb2cc60`) — Descriptions is its own property tab with the
>   route's single unsaved-changes guard and an editable video URL.
> - **Unit 7** (`155aa59c`) — per-room `website_description` retired from the
>   API and the room dialog; the column stays as `backfill_room_attrs` input.
>
> **Decisions that departed from the steps below:** `overview` was **kept**,
> not folded into `web_des_1` (6 of the 8 villas that have it also have
> `WebDesc1` — different legacy column, different screen); `location` remapped
> to `location_sub`, not `_para` (the fused body starts with part 1);
> Interior/Exterior are prose blocks *and* stay as image slot captions — one
> legacy text, two surfaces, `PropertyImageLoader` untouched.
>
> **Still to do at cutover, not in code:** run CUTOVER §6i on any DB loaded
> before this landed — until then reconcile reads ~1 049 against 3 200.
> **Not verified in a browser** — the Playwright MCP server was down for the
> session; the ticket's own warning (house-rules editor still present and
> saving) is covered by tests only.

> **Scope widened 2026-09-16 (todo consolidation):** absorbs **GAP-092**
> (website room copy sits per-room; legacy has one property-level blurb
> under all the bedrooms) — see §"Merged from GAP-092" at the end. Same Nick
> recording, same move of website copy onto the legacy property-level
> blocks, and the blurb rides this ticket's enum migration. GAP-092's
> data-loss trap carries over unchanged: **do not drop
> `Room.website_description` blind** — `backfill_room_attrs` (GAP-064) mines
> it, and legacy has a per-room column that contradicts the brief.

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
  was closed into `done/` 2026-09-16 rather than waiting for this to land.
- **GAP-091** (villa info → tags) removes `villa_info` from this enum;
  the two want sequencing together to avoid a double enum migration.
  *Landed 2026-09-09 (GAP-091 shipped first):* the enum is now `overview /
  house_rules / further_info / location / web_description / internal_notes /
  other_information / rooms` (`section` widened to 32 chars, migration
  `properties/0007`). `other_information` and `rooms` are **not**
  Descriptions-tab sections (Features tab / GAP-092), so this ticket's block
  set replaces the first six only; the `further_info` → internal-notes data
  remap is still open here.
- Merged **GAP-092** (room website description → property level) adds one
  more property-level prose block; lay it out in this tab. Its own
  dependencies (GAP-091, GAP-064's `backfill_room_attrs`) are in §"Merged
  from GAP-092".
- Related: GAP-010 (spec areas reverse-engineered from the wrong codebase —
  the reason Q-020 distrusted the spec mapping in the first place).
- Requires the legacy prod snapshot (`ResSystem-prod`) to settle the
  interior/exterior double-read (step 3) and to re-run the loader. The column
  *names* no longer need discovery — they are `Interior1/2`, `Exterior1/2`.

---

## Merged from GAP-092 — Website room copy sits on the room; legacy puts one blurb under all the bedrooms

> _Folded in 2026-09-16 (todo consolidation). The standalone ticket is closed as
> [GAP-092](gap-092-room-website-description-wrong-level.md); the text below is that ticket as it stood, headings
> demoted one level. A reference to GAP-092 elsewhere now means this section._

- **Severity:** 🟢 Gap (customer-facing parity). Backend + frontend +
  data-migration. Small, but carries a data-loss trap.
- **Source:** 2026-07-20 Nick screen-recording (`Recording-20260720_134424`,
  reviewed 2026-08-11). Transcript `[05:21–06:00]`; room dialog captured at
  `[04:55]` / `[05:55]`.
- **Files touched (best-guess):**
  - `django_res/properties/models/rooms.py:35` — `Room.website_description`
    (the field to retire). `vc_notes` (L36) stays.
  - `django_res/properties/serializers/room.py:82`.
  - `django_res/data_migration/loaders/property_children.py:54` — maps legacy
    per-room `WebsiteDescription` onto the room.
  - `django_res/data_migration/loaders/properties.py` `_write_descriptions` —
    property-level legacy `RoomDescription`. *Since GAP-091 (2026-09-09) it
    loads to its own `DescriptionSection.ROOMS` row* (API
    `/properties/{id}/descriptions/rooms`); step 1 below is done, no UI yet.
  - `django_res/data_migration/management/commands/backfill_room_attrs.py:121,128`
    — **reads `website_description` as a keyword source** (see trap below).
  - `frontend/src/features/properties/components/RoomFormDialog.tsx:76, 90,
    465–470` — the Add/Edit room dialog field itself (`Website description`
    sits above `Internal notes`); `tabs/RoomsTab.tsx` only mounts the dialog.
  - `frontend/src/features/properties/schemas.ts:240` (read) and `:361`
    (write form) — note the comment at `:356`/`:368`: `website_description`
    is deliberately `z.string()` rather than nullable, part of the GAP-024
    clearing-trap convention. Removing the field must not disturb `vc_notes`,
    which shares it.
  - `frontend/src/i18n/locales/{en,el}/properties.json:616` —
    `rooms.dialog.fields.website_description` (**both** locales; Greek is
    translated, so don't drop only the English key).

### Problem

Our Add-room dialog has a per-room **Website description** field. The website
doesn't work that way. Nick `[05:38]`: *"underneath the bedrooms we have a
generic text box which refers to all the different rooms. That's just how it's
been designed, so I think we should keep it like that."* And explicitly
`[05:51]`: *"the website description shouldn't be at a room level, it should
be relating to all the rooms."*

He is **endorsing** the legacy design here, not asking for a new feature — the
ask is to stop offering a per-room field that has no home on the public site.

`Room.vc_notes` (internal notes) is fine and stays — `[06:04]`: *"we can keep
internal notes, no problem."*

### Proposed fix

1. **Add a property-level rooms blurb.** The data almost certainly already
   exists: legacy `RoomDescription` is a **property-level** column that the
   loader currently concatenates into `VILLA_INFO`
   (`loaders/properties.py:237–241`). That is very likely this exact box.
   Confirm against the snapshot, then give it its own home — a
   `DescriptionSection` member (`rooms`) is the cheapest, rendering under the
   bedrooms. **Done by GAP-091 (2026-09-09):** `DescriptionSection.ROOMS`
   exists and the loader writes `RoomDescription` into it (a DB loaded before
   then needs the CUTOVER §6e re-run). What remains here is rendering it and
   retiring the per-room field.
2. **Retire `Room.website_description`** from the room dialog and the room
   serializer.
3. ⚠️ **Do not drop the column blind — two traps:**
   - **`backfill_room_attrs` mines it.** The command keyword-scans
     `website_description` + `placement_note` to derive room attribute facets
     (GAP-064). Deleting the field breaks a backfill that is still the only
     source for those facets on imported rooms. Either keep the column as
     import-only (unexposed), or re-run the backfill and retire it after.
   - **Legacy *does* have a per-room `WebsiteDescription` column**
     (`property_children.py:54` maps it), which contradicts "there is no
     room-level description". Most likely the legacy DB carries a column its
     UI doesn't expose — but **verify what's actually in those rows before
     discarding them**, and surface the disagreement rather than silently
     picking a side.

### Acceptance

- A single property-level rooms description exists, editable, rendering under
  the bedrooms. (test)
- The room dialog no longer offers a website description; internal notes
  unaffected. (component test)
- Room attribute backfill still works (or has been re-run and the dependency
  removed) — no facet regression. (test)
- Any legacy per-room `WebsiteDescription` content is accounted for: migrated,
  or documented as an expected loss in `CUTOVER.md`.
- Quality gate green (backend + frontend).

### Dependencies

- **GAP-091** — takes `FeatureDescription`, the other half of the
  `VILLA_INFO` concatenation this ticket splits.
- **GAP-090** — if the blurb becomes a `DescriptionSection` member, it rides
  the same enum migration; sequence together.
- **GAP-064** — room attributes; owns `backfill_room_attrs`, the blocker on
  dropping the column.
