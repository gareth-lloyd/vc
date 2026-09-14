# BUG-030 — Legacy loader: data-shape defects across property, geo, feature, people, enquiry, quotation, availability and the sheet importers

- **Severity:** 🔴 Bug (wrong values, not missing ones — slugs that are
  URLs, an agency called "NA" on 226 people, 457 dropped feature links, 14
  enquiries closed as CONVERTED, quotes for the wrong party size).
- **Source:** 2026-09-11 legacy-loader audit (dump + scratch DB
  `villacollective_loaderaudit`). Grouped by the user's 2026-09-11 call to
  keep loader fixes in a few large tickets; each § is independently
  landable, so ship as ordered units on one branch.
- **Files touched:** listed per section. Tests that pin the wrong shape:
  `tests/test_property_loader.py:22` (clean slug fixture),
  `tests/test_feature_loaders.py:36` (`ServiceType: 10`, asserts nothing),
  `tests/test_contact_loader_agency.py` (no "NA" case),
  `tests/test_reservations_loaders.py:181` (`EnquiryNo="E-000001"`, not the
  real bare-numeric shape; no status-map test), `tests/test_preference_loader.py:73`.
  No tests exist for `RegionLoader`, `CurrencyLoader`, `NearbyPlaceTypeLoader`,
  `UserLoader`, `ContactEmailLoader`, `ContactPhoneLoader`, `CollectionLoader`,
  `CollectionMembershipLoader`, `NearbyPlaceLoader`,
  `PropertyContactAssignmentLoader._process_row`, `GuestPreferenceTypeLoader`,
  `DeclarativeLoader`, `merge_country`, `legacy_db`.

## Problem and fix, by loader

### A. Property (`loaders/properties.py`)

1. **`Property.slug` is a full WordPress URL** (`:121-123`). 294/294 live
   `VillaMaster.Slug` values are
   `https://www.villacollective.com/<region>/<villa>` (17 with a trailing
   `/`); scratch sample `https://www.villacollective.com/paxos/agios-isavros-438`.
   Saves because nothing calls `full_clean`; breaks the id-or-slug lookup
   convention (`properties/views/feature.py:28`) and any URL built from it.
   **Fix:** `slugify` of the last non-empty path segment (fallback
   `slugify(name)`) + `-{Id}`; keep the URL elsewhere only if the WordPress
   backfill wants it. Tell GAP-104 (slug immutability) — its history table
   must not inherit URLs.
2. **Status 3 "pending" → ARCHIVED** (`:42-48`). 20 live villas are
   pre-go-live, not archived. **Decision 2026-09-11: 3 → DRAFT.**
3. **Prices-entered-as** hardcoded GROSS is correct by accident (BUG-028 §2);
   add the comment there.
4. `m.Channel`, `SettingAvailabilityStatusId`, `SettingPricesEnteredTypeId`
   are selected and never read (`:97-101, 202, 213`) — drop from the SELECT.

### B. Geo (`loaders/country.py`, `loaders/lookups.py:23-55`)

5. **`dial_code` is built from the ISO-numeric `Code`** (`country.py:64-65`).
   Legacy `Admin/Country.razor:22-39` labels `Code` "Number" (ISO 3166-1
   numeric). Greece stores 300 and loads `dial_code="+300"` — the only
   country with a dial code after load, and wrong. **Fix:** drop the mapping.
6. **Any 2-letter code is accepted as ISO** (`country.py:30-32`). England
   (id 24, `ShortName1='UK'`) mints `Country(iso2="UK")` beside the seeded
   GB. That is the +1 hidden in `expected_gap=-228` and the whole reason
   CUTOVER §7's `merge_country` step exists; after the merge, any later
   `loadlegacy country` re-mints it and the check becomes a blocker.
   **Fix:** validate against `django_countries`, map England → GB in
   `_resolve_iso2`, retire §7.
7. ✅ **Decided otherwise, GAP-107 as built (user decision 2026-09-14:
   "merge as built").** A deleted legacy country *does* keep its `legacy_id`
   on the matching seeded ISO row, and GAP-107 **retires** that row
   (`is_active=False`): GB, IN, NZ and AU leave the pickers at cutover, stay
   readable, and legacy references still resolve to them. Regions under a
   retired country load retired. Staff reactivate a country if they need it
   for new contacts. No work left in this item. *Original audit text:*
   **Deleted countries with a resolvable ISO keep their `legacy_id`**
   (6→GB, 10→NZ, 11→IN; 10 of the 17 deleted rows are still `IsActive=1`),
   so regions 42/44/45/46 under deleted countries resolve onto live seed rows
   rather than the sentinel. GAP-107 §2's "deleted country becomes
   selectable" already holds for all 249 seeded rows (`0002_seed_countries.py:25`
   sets `is_active=True`); the harm is the linkage. Fold into GAP-107 §2's
   fix: a deleted legacy country attaches no `legacy_id` to a live ISO row.
8. **Six live villas under deleted regions that have live successors**:
   236/237/238/376 → 25 "The Peloponnesse" (deleted 2024-11-12; live twin 61
   "Peloponnese"), 138/263 → 27 "Midi-Pyrenese" (live twin 60). **Decision
   2026-09-11: remap by explicit id map (25→61, 27→60)** in `RegionLoader`
   /`PropertyLoader`, logged per villa. Region 10 "Andalucía" vs 49 is the
   same pattern with no live villas.
9. **Region slug used verbatim** (`lookups.py:52-53`): `andalucía-10` in a
   `SlugField`. **Fix:** `slugify()`.
10. ✅ *(Recounted in GAP-107 dry-run 3: 64 / 42 live, pinned by the
    reconcile checks.)* **GAP-107 §2's region numbers are wrong for this dump**: `VillaRegion` has
    64 rows, 12 deleted, 10 live under deleted countries, 42 clean — not
    71/57. Recount before pinning the invariant (noted in GAP-107).

### C. Features and collections (`loaders/lookups.py:121-161`, `loaders/property_children.py:199-239`, `loaders/properties.py:299-346`)

11. **457 live villa → soft-deleted feature links dropped silently, no
    reconcile gate.** `FeatureLoader` filters `DeletedAt IS NULL`, so the
    mapping loader skips them at `:223-225`. Largest: deleted 55 "Sitting
    room" on **242** live villas, 56 "Study" on 58, 82 "Parking spaces" on 28.
    41 of the 53 deleted features have a live twin by normalised name
    (55→299, 56→304, 15→99, 17→98, 1→90 …) and the villa usually does *not*
    already carry the twin (Sitting room: 4/242 do). `reconcile_legacy` has
    **no check on the `PropertyFeature` through table** (11 955 rows, the
    largest loaded table after images). **Fix:** remap deleted → live twin
    by `LOWER(LTRIM(RTRIM(Name)))` in the mapping query (log the unmapped
    12); add a reconcile check against distinct live pairs (10 031 today +
    remapped). Coordinate with GAP-067's post-load curation so the remap
    does not fight it.
12. **`_service_type_map = {1,2,3}` is on the wrong scale** (`lookups.py:136-140,
    157`). Legacy `EServiceType` is `Unknown=0 / ContactService=10 /
    PropertyFeature=20`; all 229 live features are 20 → every
    `Feature.service_type` is "amenity" by fallback. Same shape as BUG-028 §1
    and the role-code bug fixed 2026-07-06. **Fix:** decide whether
    `included_service` / `paid_addon` should derive from the category `Code`
    (50 "Included Features" ×69 mappings, 70 "Services On Request" ×96);
    otherwise delete the map and document "amenity for all".
13. **`CollectionMembership` gap 308 is right for the wrong reason**
    (`reconcile_legacy.py:195` says "duplicates"; only 3 are). 308 = 3 dups +
    22 on deleted villas + **283 live memberships of five collections deleted
    together on 2024-05-28** ("Chef Included" 66, "Exceptional Design" 55,
    "Walk to restaurants" 34, "Water Front" 59, "WALK TO THE BEACH" 67).
    **Decision 2026-09-11: drop, record the composition** in the check
    comment and CUTOVER §5.
14. `IsActive=1` in the collection SELECT (`:303`) is a SQL Server alias
    literal — harmless, confusing; remove.

### D. People (`loaders/people.py`, `loaders/reservations.py:126-213`)

15. **Company "NA" becomes an agency `Organisation` linked to 226 contacts.**
    226/233 `VillaContact.Company` values are literally `NA`;
    `organisation_for_company_name` (`accounts/services/organisations.py:55-56`)
    maps only blank → None, so `people.py:88` creates `Organisation(name="NA",
    org_type=AGENCY)` as `Person.agency` on 226 owners/managers. The
    reconcile "Organisation (agency)" check counts `DISTINCT Company`
    including "NA", so it passes. **Fix:** treat `NA` / `N/A` / `-` as blank
    in the loader and in the reconcile SQL (`reconcile_legacy.py:160-180`);
    add the fixture.
16. **`_method_map = {1,2,3}` on the wrong scale** (`people.py:68-72`).
    Legacy `Preferred_Contact_Method` is `0 / Email=10 / Phone=20 /
    WhatsApp=30 / Text=40`; data is 0 ×231, 10 ×2 → all EMAIL by fallback.
    **Fix:** re-key (decide WhatsApp's target).
17. **Phones normalised three ways.** `ClientLoader` calls `to_e164()` with
    no region, so ~26/31 numbers fail to parse and store raw
    (`reservations.py:161`). `ContactPhoneLoader` builds its own string
    (`people.py:140-141`): `"+0044 7770302297"`, `"+44 07771950930"`, bare
    `"07919591288"`. `EnquiryLoader` anchors by `CountryCode`. **Fix:** all
    three through `to_e164` anchored on the row's country (default GB).
18. **Duplicate and cross-slice Persons.** Clients 1 and 4 share e-mail and
    name (both referenced by bookings/preferences). Clients 5 and 19 share an
    e-mail with VillaContact 1 and 232 (19↔232 same name, has a property
    mapping), so one human is two ACTIVE Persons and the sheet matcher's
    e-mail lookup (`sheets/matching.py:338-341`, `.order_by("status")` only)
    picks whichever sorts first. **Fix:** deterministic CUSTOMER-first
    tiebreak in `match_person_by_email`; add "merge clients 1↔4, 5↔contact 1,
    19↔contact 232 via `/contacts/{id}:merge`" to the CUTOVER post-load
    checklist.
19. Client `ContactType` (Email 14 / Phone 1) → `Person.preferred_method`
    exists and is never set; `CreatedAt` (31/31) has no Person back-stamp.
    Small; do them here.

### E. Enquiry (`loaders/reservations.py:216-327`, `loaders/_util.py:52-64`)

20. **Status map inverts legacy: 14 enquiries land CONVERTED.**
    `EnquireStatus` is 1 New / 2 Completed / 3 Pending / 4 Opened; legacy
    writes 4 when a quotation is *added* (`DbScript.sql:50295`) and 2 when
    the quote e-mail is *sent* (`ResService.cs:2755`). The loader maps 4 →
    CONVERTED (terminal; `views/enquiry.py:172` short-circuits it) and 2 →
    PROGRESSING. All 14 status-4 rows are exactly the 14 with a quotation;
    none has a booking. Real distinct values: NULL 181, 1 ×255, 2 ×1, 4 ×14.
    **Fix:** 4 → PROGRESSING, 2 → QUOTE_SENT, plus a test.
21. **Stale leads.** 436 status-1/NULL enquiries load NEW with the model
    default WARM (Nov 2024 → freeze on the final dump); the sheet importer
    parks its rows DEAD / UNKNOWN / COLD (`import_enquiry_sheet.py:61-64`).
    **Decision 2026-09-11: age cutoff, same as the sheet** — an enquiry
    created before a date constant (proposed: 90 days before cutover) with
    no quotation loads DEAD / `lost_reason=UNKNOWN` / COLD; the rest keep
    their mapped status. One constant, next to the sheet importer's.
22. **No enquiry links to a Person** (no `person` key in the transform).
    Customer-360 lists `person.enquiries_as_customer`
    (`reservations/views/contact_reads.py:80`); 28 enquiry rows share an
    e-mail with the 31 `client-` Persons, 4 with owner/agent Persons, 63 with
    enquiry-sheet people, 37 with past-booker people. **Fix:** resolve
    `person` by primary-e-mail match over ACTIVE people (CUSTOMER-first
    tiebreak, §18), and via the quotation chain for the 14 quoted rows.
23. **`Adult=0` (54 rows) is rewritten to 2** by `or 2` (`:314`) —
    fabricated occupancy. **Fix:** load 0 as 0 (or NULL if the model allows)
    and let the UI prompt.
24. **`ensure_enquiry` stand-ins are mislabelled and undated** (`_util.py:52-64`).
    5/19 quotations point at hard-deleted enquiries (EnquireId 306/380/381/
    382/522) → synthesised with `site_source=AGENT_PORTAL` (they were
    website/staff quotes, `AgentId=0`), status NEW, no dates, no back-stamp.
    **Fix:** stamp from the quotation's `CreatedAt`, use `OTHER`, note the
    provenance in `inbound_message`.
25. **Reference shape doc/test drift.** 451/451 `EnquiryNo` are bare
    numerics 1501…2176 (and `EnquiryNo == QuotationNo`, 14/14), so the
    `E-{Id:06d}` fallback never fires; the fixture's `"E-000001"` is not the
    real shape. Fix the fixture; CUTOVER §4c line in GAP-108.
26. `site_source` hardcoded MAIN_WEBSITE for all incl. the 8 staff-entered
    (`CreatedBy` WEBSITE 262 / ENQUIRE 181 / staff 8). Map staff names →
    `OTHER`/staff source. (The other dropped enquiry columns are GAP-109.)

### F. Quotation (`loaders/finance.py:339-343, 375-389, 432-433`)

27. **Lines hard-code 2 adults / 0 children** while `VillaQuotationMaster.
    Adult/Children` are populated 19/19 (10/0, 5/2, 4/2 …). **Fix:** join
    the master, copy per line.
28. **No `created_at` back-stamp; `expires_at = now + 7d`.** All 19 appear
    created on cutover day and the beat expire sweeper flips every DRAFT to
    EXPIRED a week later. `CreatedAt` is 19/19 populated. **Fix:** back-stamp
    via `.update()` like `EnquiryLoader._process_row`; derive `expires_at`
    from legacy `CreatedAt` (+ the legacy validity window, or mark already-
    expired ones EXPIRED at load).
29. `EnquiryNote` is SELECTed and never used (9 rows); fold with
    `PreferencesNote` into the linked enquiry's `inbound_message` (GAP-109
    lists the rest).
30. **Preferences: the 93 gap is quotation-context loss, not duplicates.**
    126/167 `ClientPreferenceDetails` rows carry a `QuotationMasterId` that
    does not exist (values 21…541; `VillaQuotationMaster` max Id is 20,
    several are `VillaEnquire` ids) → `quotation=None` → the (person, type,
    NULL) collapse yields exactly the 74 loaded. Flattening is defensible;
    count it as its own outcome in the report and fix the check comment
    (`reconcile_legacy.py:377-384`; test `:73` pins only the duplicate case).

### G. Availability (`loaders/availability.py`)

31. **Status 0 "Unknown" is excluded, but staff entered it as whole-calendar
    blocks** (`:174`): 4 063 rows on 12 live villas (e.g. 26, 85, 87: every
    day 2025-01-01 → 2027-12-31, one staff user). Legacy's rate lookup treats
    only the literal "Available" as bookable (`RateLookup.razor:426`,
    `ResService.cs:1180`), so these were blocked there and bookable here.
    **Decision 2026-09-11: treat 0 as blocked** — add it to the filter and
    `STATUS_NAMES`; recalibrate the reconcile check. Also add Code 6
    "BookedExt" (Id 7, 0 rows) to `STATUS_NAMES` for completeness.
32. **Never exercised at volume.** On this dump, as of today, the loader
    loads nothing (future rows: 1 908 ×0, 3 321 ×10, 7 ×70; zero 30/40/50/60),
    so the reconcile passes 0 = 0 trivially. Relative to the dump date there
    were 14 785 non-available days over ~180 villas; the final dump will
    carry thousands of future rows plus 21 on soft-deleted villas (→ skips).
    A proper dry run on the final dump is mandatory; `StartDate/EndDate`
    (55 189 populated) are legacy's own run boundaries and can cross-check
    the coalescer. (Duplicate-day ordering is BUG-029 §3.)

### H. Sheet importers (`sheets/matching.py`, `import_*.py`)

33. **Villa matching leaves ~40 % of stays unlinked, largely through
    ambiguity.** `PropertyMatcher` indexes `Property.objects.all()` with no
    status filter (`:162-194`). Booking History: 497 matched / **156
    ambiguous** / 185 unmatched / 9 blank of 847; enquiry sheet 902 / 357 /
    751 / 67 of 2 077. Top ambiguous names are legacy duplicates of one villa
    ("villa yeraki" ×34, "villa olea" ×13). **Fix:** index non-archived
    properties first, fall back to all.
34. **Report over-counts and mis-keys.** `import_enquiry_sheet.py:160-161,
    280` increments `created["person"]` before `_import_enquiry` can raise in
    the same savepoint (row rolls back, count stays); `:144` keys the
    invalid-e-mail error by the person's name, not `Sheet1!{index}`. Same
    shape at `import_past_bookers.py:162-165`.
35. `match_person_by_name` (`:295-305`) prefers CUSTOMER only when > 1
    candidate, so a single ACTIVE owner namesake is linked as the guest
    (3 history names collide with an owner/agent name). Prefer CUSTOMER
    always.
36. Future stays in the Past Bookers sheet (2026 ×141, 2027 ×17) → **Q-028**
    (owner question); no change here until answered.

## Acceptance

- Each § has transform tests on real-shaped dict fixtures (the fixture
  corrections listed under Files); the untested loaders listed there get at
  least one transform test each.
- Live dry-run: slugs are slugs; 0 `Organisation(name="NA")`; feature links
  on live villas ≥ 10 031 + remapped and a `PropertyFeature` reconcile row;
  0 enquiries CONVERTED, 14 PROGRESSING, stale rule applied; enquiries link
  to the 28 + 4 matchable Persons; quotation lines carry the master's
  occupancy; quotations back-stamped; regions 25/27 remapped; status-3
  villas DRAFT; availability status-0 runs coalesced.
- Decisions recorded in `design/decisions.md`: pending → DRAFT, region
  remap, collections drop, availability status 0, stale-lead rule, enquiry
  status map.
- `reconcile_legacy` green with recalibrated constants (GAP-108 owns the
  constants table) and quality gate green.

## Dependencies

- **BUG-028** first (currency), **BUG-029** for the ordering fixes it owns.
- **GAP-107 §2** (deleted regions/countries as inactive) — §7/§8/§10 here
  refine it; land together.
- **GAP-104** (slug immutability) must know about §1. **GAP-067** (feature
  taxonomy curation) must know about §11. **GAP-090** still owes its own
  loader half (WebDesc/Location split, `further_info` remap) — untouched here.
- **GAP-108** pins the reconcile constants this ticket moves.
- **Q-028** carries §36.
