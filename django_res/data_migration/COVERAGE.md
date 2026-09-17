# Legacy Coverage Matrix

S1 of `ACCEPTANCE.md`: every table in the live legacy DB classified as
**loaded**, **joined** (read as part of another loader), **dropped**
(deliberate, justified), **deferred** (a named follow-up ticket owns it), or
**BLOCKER** (unclassified / unresolved).

Baseline: **`ResProd`** (13-Aug-2026 production data), **73 tables**, row
counts from `sys.partitions` on 2026-09-16. The 24-Apr-2025 dump
(`live-db-24-apr.sql`, 61 tables) is gone; where a figure below could only be
re-derived from that dump it is labelled as history, not as current state.
Regenerate this list against `sys.tables` at every dry run — a table that
appears in a newer dump and not here is automatically a blocker.

Tables the design docs mention that do **not** exist in `ResProd` (confirmed
against `sys.tables`, do not chase): `Tags`/`VillaTags`,
`TblVillaQuotationMaster`, `VillaSettings`, `VillaMapping`,
`VillaOwnerDetails`, `VcemailTemplate` (the real names are `VCEmailTemplate` /
`VCEmailTemplates`), any refund table, `VillaBookingDateHistory`. Four names
the 24-Apr-2025 baseline listed as absent **do exist on ResProd** and are
classified below: `VillaSites`, `VillaSyncDetails`, `VillaCheckoutDetails`,
`PaymentStatusLog`. One table the baseline carried, `VillaPaymentStatus`, is
**gone from ResProd** — see the note at the foot of this file.

## Loaded (primary source of a registered loader)

The registry holds **31 loaders** (`registry.py`); `availability_block` and
`property_defaults` are the two whose sources are written up in
"Classified 2026-07-05" below rather than repeated here.

`Rows` is the whole table; `live` is the subset the loader's own filter keeps
(GAP-108 Unit 3 — see "Soft-delete filters" below).

| Table | Rows | Loader | Target |
|---|---|---|---|
| `VillaCountry` | 24 | country | `properties.Country` (onto ISO seed) |
| `VillaRegion` | 71 | region | `properties.Region` (legacy-deleted / orphaned rows load `is_active=False`, GAP-107) |
| `VillaCurrency` | 7 | currency | `pricing.Currency` |
| `VillaNearByLocationType` | 8 | nearby_place_type | `properties.NearbyPlaceType` (`IsActive` maps to `is_active`, not filtered) |
| `VillaFeaturesCategory` | 8 | feature_category | `properties.FeatureCategory` |
| `VillaFeatures` | 318 (236 live) | feature | `properties.Feature` |
| `UserMaster` | 32 (18 live) | user | `accounts.User` (passwords unusable) |
| `VillaContact` | 332 | contact | `accounts.Person` + agency `Organisation` |
| `VillaContactEmail` | 319 | contact_email | `accounts.PersonEmail` |
| `VillaContactTele` | 259 | contact_phone | `accounts.PersonPhone` |
| `VillaMaster` | 545 (386 live) | property | `properties.Property` + 4 satellites |
| `VillaCollection` | 62 (29 live) | collection | `properties.Collection` |
| `VillaCollectionsMappings` | 2206 (1091 live) | collection_membership | `properties.CollectionMembership` |
| `VillaRooms` | 2714 (2684 live) | room | `properties.Room` + `RoomBeds` |
| `VillaPropertyImages` | 19071 | property_image | `properties.PropertyImage` (`IsActive` maps to `is_active`, not filtered) |
| `VillaNearBy` | 178 (177 live) | nearby_place | `properties.PropertyNearbyPlace` |
| `VillaFeaturesMappings` | 15704 (15442 live) | property_feature | `Property.features` through |
| `VillaSeason` | 1451 (1062 live) | rate_plan | `pricing.RatePlan` — one per (villa, currency) regime, GAP-110 (+`PropertyService` per inclusion season) |
| `VillaSeasonRate` | 42112 | rate_rule + extra | `IsExTra <> 1` (39 151 live) → `pricing.RateBand` + `RatePeriod` on the villa's regime plan (full replace); `IsExTra = 1` (96 live) → `pricing.Extra` (GAP-107, CUTOVER §4i; discount columns dropped) |
| `VillaContactMapping` | 466 | property_contact_assignment | `properties.PropertyContactAssignment` (474 (mapping, role) pairs) |
| `VillaClientDetails` | 1215 | client | `accounts.Person` (`client-` slice) |
| `VillaClientPrefMaster` | 11 | guest_preference_type | `reservations.GuestPreferenceType` |
| `ClientPreferenceDetails` | 836 | guest_preference | `reservations.GuestPreference` |
| `VillaEnquire` | 2792 (2705 live) | enquiry | `reservations.Enquiry` |
| `VillaFinance` | 1597 | property_finance | `properties.PropertyFinance` |
| `VillaQuotationMaster` | 1727 (1550 live) | quotation | `reservations.Quotation` |
| `VillaQuotationDetails` | 8035 | quotation_line | `reservations.QuotationLine` |

`syncrecord_zoho` additionally re-reads **four** tables for `ZohoId`:
`VillaMaster` (112 non-blank), `VillaContact` (**0** — no contact continuity
exists), `VillaEnquire` (2228), `VillaQuotationMaster` (1601). It sweeps no
booking table: the booking loaders are unregistered, so a `VillaBooking`
`ZohoId` (190 non-blank) has no local target, and `VillaArchiveBookings.ZohoId`
(86 non-blank) is a keep/drop call owned by GAP-098.

### Soft-delete filters (GAP-108 Unit 3)

ResProd's DELETE stored procedures set `IsActive = 0` and its views keep only
`isnull(IsActive,0) = 1`, so **NULL means INACTIVE**. `legacy_active_sql(alias)`
(`loaders/_util.py`) is that filter, and four loaders apply it: `room`
(`VillaRooms`), `property_feature` (`VillaFeaturesMappings`),
`collection_membership` (`VillaCollectionsMappings`) and `nearby_place`
(`VillaNearBy`). `VillaEnquire` gained a `DeletedAt` column, which the
`enquiry` loader filters on like every other `DeletedAt` table. `IsActive`
columns that are **data, not a filter** — `VillaPropertyImages`,
`VillaNearByLocationType`, `VillaClientPrefMaster`, `UserMaster` — map to the
target's own `is_active`.

## Joined (read inside another loader's query)

| Table | Rows | Read by |
|---|---|---|
| `VillaFeaturesCategoryMappings` | 404 | feature (first category via `OUTER APPLY`) |
| `VillaSeasonDates` | 1505 (1130 live) | rate_plan (live window per season → `PropertyService` dates only — GAP-110 dropped the plan envelope); never a pricing input |
| `VillaOccupencyPrice` | 773 | rate_rule (occupancy-band expansion, BUG-013) |
| `VillaContactRoleMapping` | 454 | property_contact_assignment (role source) |

## Dropped — GAP-089 (bookings come from the Past Bookers sheet)

GAP-089/GAP-108 **unregistered** `BookingLoader`, `PaymentLoader` and
`BookingChargeItemLoader`. Bookings are imported from the Past Bookers
spreadsheet (`import_past_bookers`), not from the res DB. The modules and
their tests in `loaders/bookings.py` are kept **only as a record of the legacy
schema**; nothing in `registry.py` runs them, and `reconcile_legacy` asserts
that no row carrying a `legacy_id` ever lands in those tables.

| Table | Rows | Note |
|---|---|---|
| `VillaBooking` | 251 | `BookingLoader` — unregistered. |
| `VillaPayment` | 190 | `PaymentLoader` header join — unregistered. |
| `VillaPaymentDetails` | 244 | `PaymentLoader` — unregistered. |
| `VillaBookingDetails` | 142 | `BookingChargeItemLoader` — unregistered. |

## New on ResProd (not on the 24-Apr-2025 baseline)

Thirteen tables are new; `VillaPaymentStatus` disappeared, so the count went
61 → 73.

| Table | Rows | Classification |
|---|---|---|
| `VillaArchiveBookings` | 295 (272 live) | **LOADED by `import_archive_stays`** (GAP-113, runs after the sheet imports; CUTOVER [§4](CUTOVER.md#4-run-every-loader)). Staff re-keying of past sheet bookings: re-saves fold into one stay, which either fills the matching `sheet-stay-…` `PastStay`'s empty dates, amount, currency and notes, or creates an `archive-stay-<Id>` `PastStay` (finding or creating the person with the archive address and mobile). **Dropped:** `Adults`/`Children` (mostly form defaults), `ZohoId` (GAP-098), the contact fields of *enriched* stays, and staff test row 297. `reconcile_legacy` blocks while any stay is still to enrich or create. 7 live rows (6 stays) end on or after 2026-09-16; their nights are already `BookingHold`s. |
| `VillaCheckoutDetails` | 598 | Booking-side payment/checkout ledger (`BookingRefNo`, `Amount`, `PaymentId`, `PaymentStatus`, `IsDeposit`). Falls under the GAP-089 booking descope — not loaded. |
| `CheckoutPersonalInfo` | 160 | Lead-guest checkout form per booking. GAP-089 descope — not loaded. |
| `CheckoutAdditionalInfo` | 25 | Additional-guest rows hanging off `CheckoutPersonalInfo`. GAP-089 descope — not loaded. |
| `VillaConcierges` | 119 | Per-booking concierge requests (`BookingRefNo`, `Description`, `PaymentId`). GAP-089 descope — not loaded. |
| `PaymentStatusLog` | 1400 | Single `Logs` nvarchar column — an ephemeral gateway log. DROP. |
| `temp_vc_logs` | 19864 | Ad-hoc column-change scratch audit (`TableName/ColumnName/OldValue/NewValue`), written by legacy maintenance scripts. DROP. |
| `TempQuoteSearchResult` | 1 | Session-scoped JSON scratch for the quote search screen. DROP. |
| `VCEmailTemplate` | 11 | Legacy e-mail template bodies; the new system owns its own templates (`comms`). DROP. |
| `VCEmailTemplates` | 224 | Per-(source, destination) template variants; same reasoning. DROP. |
| `VillaSites` | 2 | WordPress publishing-target registry (site URL + API key) — part of the `WORDPRESS_BACKFILL.md` descope. |
| `VillaSyncDetails` | 5773 | WordPress push ledger (`SiteId`, `ModuleId`, `ModulePrimaryId`). Same descope; `reconcile_legacy --integrations` reports its volume informationally. |
| `VillaWebSettings` | 1 | One-row `AllowSyncOnUpdate` flag for the WP sync. Same descope. |

### New columns worth a line

- **`VillaSeason.CarriedRates`** — "rates carried over, not confirmed" flag;
  **198 live seasons** carry it (214 rows including deleted). **Loaded since
  GAP-114** as `RateBand.is_indicative` on every band whose source row sits on
  a flagged season (`ISNULL(CarriedRates, 0) = 1`; occupancy children, `occ-fb-*`
  fallbacks and `#seg` fragments inherit it). ResProd 16-Sep-2026: 1 616
  carried source rows → 1 421 indicative bands, reconciled by the
  `RateBand indicative (CarriedRates)` check (expected gap 195, itemised in
  `CUTOVER.md` §5). Quotes still price from them; staff see an
  "indicative rates" warning until they confirm the plan
  (`POST /rate-plans/{id}:confirm-rates`).
- **`VillaMaster.AvailabilityType` / `.AvailabilityValue`** — across the 387
  non-deleted villas `AvailabilityType` is NULL ×222, 1 ×102, 2 ×63; the
  meaning of the two codes is not decoded here. No Django target; dropped,
  listed in GAP-109.
- **`VillaAvailability.QuotationNo`** — populated on only 10 grid days; the
  `availability_block` loader does not read it.
- **`VillaContactMapping.IsCC`** — set on **2** of 466 mappings; dropped
  (GAP-109). `GroupId` is still 0/NULL on every row.
- **`VillaFinance.SecurityDepositPaymentMethod`** — integer codes, and **we do
  not know what they mean**: 0 ×59, 10 ×1537, 20 ×1, with no lookup table in
  the schema and no decode in `ResSystem/`. **Known open item** — do not guess
  a mapping; dropped until someone decodes it (**GAP-115**).
- **`VillaQuotationMaster.IsUnbrandedVilla`** — set on **87** quotations; no
  Django target, dropped (GAP-109).
- **`VillaQuotationMaster.ZohoId`** — **exists on ResProd** with **1601**
  non-blank values, and `VillaBooking.ZohoId` exists with 190. This reverses
  the 24-Apr-2025 finding recorded at the foot of this file.

## Dropped — deliberate, with justification

| Table | Rows | Justification |
|---|---|---|
| `VillaRoles` | 5 | Static 5-row lookup → `ContactRole` TextChoices; mapped 1:1 in `_ROLE_MAP` on the legacy **Code** (10/20/40/50/80), not the Id (GAP-048). |
| `VillaPropertyCategory` | 4 | **DECISION 2026-09-01: DROP (owner call, GAP-093)** — country + region is enough; `Property.category` and the `PropertyCategory` lookup were removed, so there is no target. |
| `VillaGroup` | 49 | **DECISION 2026-07-05: DROP (owner call, GAP-070)** — property groups left the product; the group-level settings/finance floors became the `PropertyDefaults` singleton. Loader + `PropertyGroup` removed. |
| `VillaStatus` | 4 | Static lookup → `Property.status` TextChoices. |
| `EnquireStatus` | 4 | Static lookup → `Enquiry` stage enum (int map in loader). |
| `AvailabilityStatus` | 9 | Status-code lookup for `VillaAvailability` day grid → new model has no day grid (the data itself is loaded as blocks — see "Classified" §1). |
| `CalculationType` | 2 | Static lookup → commission calc enum. |
| `DepositType` | 2 | Static lookup → deposit type enum. |
| `ChangeOverDays` | 8 | Weekday lookup → `ChangeOverRule` weekday enum. |
| `VillaConciergeServices` | 2 | The two tier labels (`Quintessential`, `Signature`) do have a home — `reservations.ConciergeTier` TextChoices on `BookingConciergeItem.tier`. **But the per-villa assignment is dropped**: `VillaMaster.ConciergeService` is set on 383 of 386 live villas (code 1 ×210, code 2 ×173) and **no `Property.concierge_tier` field exists**. Owned by **GAP-109** item 10 (decide with Nick: add the field or record the drop). Earlier wording here claimed the mapping was complete — it is not. |
| `VillaBookingConcierge` | 70 | Booking-side concierge selections; GAP-089 descope (it was empty on the 24-Apr-2025 dump, hence the older "nothing to migrate" note). |
| `VillaRentalAlternatives` | 166 | Multi-property bundling not in MVP (documented future scope). Information-bearing: recoverable from the archived dump. |
| `VillaCodeSentHistory` | 1 | Ephemeral 2FA-code log; 1 row; worthless post-cutover. |
| `VillaEmailLinkLog` | 19 | Ephemeral magic-link log; expired tokens. |
| `VillaFeaturesIcons` | 17 | Icon asset lookup for legacy UI; new FE has its own icon system. |
| `VillaConfigWebsite` | 10 | WordPress publishing-target registry — part of the documented WP-backfill descope (`WORDPRESS_BACKFILL.md`); revisit if WP continuity is bought back. |

## Dropped — asserted by docs, verification still owed

Both analyses below were run against the 24-Apr-2025 dump; the ResProd row
counts differ (`VillaContactMap` 230 → 313, `VillaContactGroupMap` 46 → 40),
so the per-row coverage arithmetic is **owed a re-run** before cutover. The
DROP decisions themselves stand.

| Table | Rows | Status |
|---|---|---|
| `VillaContactMap` | 313 | **Verified 2026-07-05 on the 24-Apr-2025 dump — the "duplicate" claim was FALSE but DROP stands**: it is a contact-level `(ContactId, RoleId)` role directory, not a mapping duplicate. On that dump 220/230 rows were reproduced by loaded property assignments and the 10 uncovered rows were role tags on contacts with no property mapping (the new model only carries roles per assignment, GAP-048). Coverage not yet re-measured on ResProd. |
| `VillaContactGroupMap` | 40 | **Verified 2026-07-05; DECISION 2026-07-06: DROP (owner call, GAP-073)**: group-scoped contact assignments (columns `GroupId, ContactId` only — no role, no flags). `VillaContactMapping.GroupId` is still never set on ResProd (0 rows), so no edge is directly covered. On the 24-Apr-2025 dump 27/46 were redundant via property expansion and 19 edges (38 contact×property links) existed only here. A load-time expansion into `PropertyContactAssignment` was prototyped on `feat/legacy-loader` but the owner dropped it post-GAP-070 (the product no longer has groups). Net-new edges remain recoverable from the archived dump if a business need surfaces; not yet re-measured on ResProd. |

## Classified 2026-07-05 (investigation agents; details in DRYRUN_LOG.md)

1. **`VillaAvailability` — 108,196 rows → LOAD (future slice only).**
   Past grid days are display residue; FUTURE non-available runs (statuses
   30/40/50/60, plus 0/NULL "Unknown" and 6 "BookedExt" since BUG-030 §31;
   runs split around bookings and staff holds) are real state existing
   nowhere else. The `availability_block` loader coalesces them into block
   rows (`avail-{prop}-{start}`), full-replace per run, reconcile check on
   future-day arithmetic. On ResProd as of 2026-09-16: 16,617 future grid
   days over 261 properties, of which **10,346 rows (10,189 distinct
   property-days, over 219 properties) carry a blocking status
   (`AvailableStatus IN (0, 6, 30, 40, 50, 60)`) and coalesce to ~470 runs**
   (vs 1 run on the stale 24-Apr-2025 dump). The
   window is anchored on the day the loader runs, so this count is
   load-date-relative by design. Grid itself + `AvailabilityStatus` lookup:
   dropped (mechanism replaced).
2. **`VillaPropertyImagesDescription` — 407 rows → LOAD (full).**
   Not captions: one row per villa of website section copy.
   `Interior1/2`/`Exterior1/2` pair 1:1 with slot-flagged images → joined
   into `PropertyImage.description`. **DECISION 2026-07-06: PRESERVE ALL** —
   `WebDesc1/2` (390 villas on ResProd) and `Location1/2` (372 villas) fold
   into new `PropertyDescription` sections (`WEB_DESCRIPTION`, `LOCATION`);
   `VodeoUrl` (55 links) → `Property.video_url`. Content verified distinct
   from the `OverView` blurb already migrated (WebDesc = activities/extras,
   Location = location copy).
   **2026-08-07:** both sections are now actually reachable in the SPA. The
   frontend had pinned four sections in a `z.enum`, so every property carrying
   a `web_description` or `location` row failed the response parse and
   collapsed the whole Descriptions panel — i.e. this migrated copy was loaded
   but invisible, and it took the other sections down with it. The schema now
   accepts any `section` string and the UI filters to what it knows.
3. **`VillaRoomsPlacement` — 57 rows → LOAD (GAP-065).** Curator-entered
   building labels referenced by 2,409 live rooms (the same figure the
   `Room placement` reconcile row is derived from); `RoomLoader` was hardcoding
   MAIN_HOUSE for all of them (live data-loss bug, already ticketed).
   Loader now maps placement per GAP-065 scope. (The ticket's "floor" axis
   is NOT in this table — building only.)
4. **`VillaWebsitePricing` — 542 rows → DROP min/max cache; POA DEFERRED.**
   Min/max is a stale display cache (113/441 matched live rates on the
   24-Apr-2025 dump — **not re-measured on ResProd**); superseded by
   `VillaPricingSummary` rebuilt from loaded rates. The POA flag is
   curator-set (**20** live villas on ResProd, `IsPOA=1`; not derivable from
   rate-level `is_poa`) and has no property-level home. **DECISION
   2026-07-06: DEFERRED** pending a schema call on a property-level POA flag.
   Migration risk if it ships un-resolved: those 20 villas show a computed
   price instead of legacy "price on application / enquire" — a
   customer-facing behavioural regression. Tracked as an open cutover item,
   NOT silently dropped.
5. **`VillaConfigEmail` — 20 rows → DROP; provision manually.** 1 real
   profile + 19 UAT rows. Secrets don't ride the migration: create the one
   SYSTEM `comms.SmtpProfile` by hand at cutover (CUTOVER step to add).
6. **`VillaConfigGeneral` — 10 rows → DROP** (legacy app self-config; 1 prod
   URL + 9 localhost rows). **`VillaConfigPropertyDefault` — 1 row → loaded, then
   DROP after cutover**: `PropertyDefaultsLoader` (`property_defaults`) ports it
   to the `PropertyDefaults` singleton, and BUG-028 (2026-09-14) resolves every
   `IsDefault*` / zero-value field from it at load time (finance, settings;
   see CUTOVER §4). Keep it in the dump until the final load has run.
7. **`VillaPaymentStatus` — DROPPED, and the table no longer exists.** On the
   24-Apr-2025 dump it held 24 rows and was a misnamed payment-gateway
   webhook/event log from the Feb–Apr 2025 provider trial, not a status
   lookup. It is absent from ResProd's `sys.tables`; `PaymentStatusLog` (1400
   rows, single `Logs` column) is its successor and is dropped for the same
   reason.

## Notes

- **GAP-091 (2026-09-09)** — `VillaMaster.FeatureDescription` and
  `VillaMaster.RoomDescription` now load to their own `PropertyDescription`
  sections (`other_information`, `rooms`); they were fused into `villa_info`
  before (CUTOVER §6e). Legacy's "Other Information" tags are `VillaFeatures`
  rows under category Code 60 / Id 8 — loaded by `feature` like any other
  feature, no dedicated table (`Tags`/`VillaTags` still do not exist). Two
  caveats stand: `VillaFeaturesMappings.CategoryId` (per-assignment category)
  and `.Description` (per-villa tag override) are still dropped by
  `property_feature` (GAP-067 follow-up), and a feature mapped to several
  categories lands under its first mapping only.
- **Multi-category features are not a one-off.** Measured on ResProd
  2026-09-16: all **236** live `VillaFeatures` rows carry at least one
  category mapping and **55 of them map to more than one** category, so
  `FeatureLoader`'s first-mapping rule discards a real second category on
  ~23% of features. The worst case is `298 Sea View` — 8 mapping rows, 7 of
  which resolve to a real `VillaFeaturesCategory` (one `CategoryId` matches no
  category `Code`) — then `164 Gym` with 3. Earlier wording here named only
  `298 Sea View`, which understated the loss by 54 features. (The GAP-108
  ticket quotes 50/229; that is the same finding measured earlier — today's
  numbers are 55/236.)
- Booking-side volume on ResProd is **no longer tiny** — 251 bookings, 1727
  quotations, 190 payment headers / 244 payment details, 142 booking charge
  items — but the booking, payment and charge-item loaders are unregistered
  (GAP-089), so none of that volume is loaded from the res DB. Quotations and
  quotation lines (1550 live / 8035) ARE loaded and are now a real money-parity
  surface, alongside property/rates/images/availability.
- **Superseded 2026-09-16** — the 2026-07-05 dry-run finding that
  `SyncRecordZohoLoader` crashes because `VillaQuotationMaster` and
  `VillaBooking` have **no `ZohoId` column** was true of the 24-Apr-2025 dump
  only. On ResProd both columns exist (1601 and 190 non-blank). The loader
  probes for the column at run time (`zoho_id_column_exists`) and sweeps four
  tables; it no longer aborts the whole `loadlegacy --all` run.
- CUTOVER §4f role-source warning **resolved 2026-07-05, re-verified on
  ResProd 2026-09-16**: `VillaContactMapping` has **no `RoleId` column** (the
  doc claim was wrong for this schema vintage); the role comes only from the
  LEFT-JOINed `VillaContactRoleMapping`, and **23/466** mappings have no role
  child → `owner` fallback (accepted; it was 3/335 on the 24-Apr-2025 dump).
  `GroupId`, all `IsAccess*`/`IsNotify*` flags and `Notes` are zero/unused in
  prod — dropping them loses nothing.
- Row counts here come from `sys.partitions`, which is approximate under
  concurrent write; the `live` figures are exact `COUNT(*)`. Trust `COUNT(*)`
  at reconcile time.
