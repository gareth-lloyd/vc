# Legacy Coverage Matrix

S1 of `ACCEPTANCE.md`: every table in the live `NewResSystem` dump classified
as **loaded**, **joined** (read as part of another loader), **dropped**
(deliberate, justified), or **BLOCKER** (unclassified / unresolved).

Baseline: 24-Apr-2025 prod dump (`live-db-24-apr.sql`), 60 tables, row counts
from `sys.partitions` on 2026-07-05. Regenerate this list against
`sys.tables` at every dry run — a table that appears in a newer dump and not
here is automatically a blocker.

Tables the design docs mention that do **not** exist in this dump (confirmed
against `sys.tables`, do not chase): `Tags`/`VillaTags`, `VillaSites`,
`VillaSyncDetail(s)`, `VillaCheckoutDetail`, `TblVillaQuotationMaster`,
`VillaSettings`, `VillaMapping`, `VillaOwnerDetails`, `PaymentStatusLog`,
`VcemailTemplate`, any refund table, `VillaBookingDateHistory`.

## Loaded (primary source of a registered loader)

| Table | Rows | Loader | Target |
|---|---|---|---|
| `VillaCountry` | 23 | country | `properties.Country` (onto ISO seed) |
| `VillaRegion` | 64 | region | `properties.Region` |
| `VillaCurrency` | 7 | currency | `pricing.Currency` |
| `VillaPropertyCategory` | 4 | property_category | `properties.PropertyCategory` |
| `VillaNearByLocationType` | 8 | nearby_place_type | `properties.NearbyPlaceType` |
| `VillaFeaturesCategory` | 8 | feature_category | `properties.FeatureCategory` |
| `VillaFeatures` | 307 | feature | `properties.Feature` |
| `UserMaster` | 24 | user | `accounts.User` (passwords unusable) |
| `VillaContact` | 233 | contact | `accounts.Person` + agency `Organisation` |
| `VillaContactEmail` | 222 | contact_email | `accounts.PersonEmail` |
| `VillaContactTele` | 165 | contact_phone | `accounts.PersonPhone` |
| `VillaGroup` | 45 | property_group | `properties.PropertyGroup` (+Settings, +Finance) |
| `VillaMaster` | 441 | property | `properties.Property` + 4 satellites |
| `VillaCollection` | 44 | collection | `properties.Collection` |
| `VillaCollectionsMappings` | 922 | collection_membership | `properties.CollectionMembership` |
| `VillaRooms` | 2098 | room | `properties.Room` + `RoomBeds` |
| `VillaPropertyImages` | 13089 | property_image | `properties.PropertyImage` |
| `VillaNearBy` | 176 | nearby_place | `properties.PropertyNearbyPlace` |
| `VillaFeaturesMappings` | 11955 | property_feature | `Property.features` through |
| `VillaSeason` | 710 | rate_plan | `pricing.RatePlan` (+`PropertyService`) |
| `VillaSeasonRate` | 8665 | rate_rule | `pricing.RateBand` + `RatePeriod` (full replace) |
| `VillaContactMapping` | 335 | property_contact_assignment | `properties.PropertyContactAssignment` |
| `VillaClientDetails` | 31 | client | `accounts.Person` (`client-` slice) |
| `VillaClientPrefMaster` | 13 | guest_preference_type | `reservations.GuestPreferenceType` |
| `ClientPreferenceDetails` | 167 | guest_preference | `reservations.GuestPreference` |
| `VillaEnquire` | 451 | enquiry | `reservations.Enquiry` |
| `VillaFinance` | 1526 | property_finance (+group_finance derives) | `properties.PropertyFinance` / `GroupFinance` |
| `VillaQuotationMaster` | 19 | quotation | `reservations.Quotation` |
| `VillaQuotationDetails` | 23 | quotation_line | `reservations.QuotationLine` |
| `VillaBooking` | 3 | booking | `reservations.Booking` (+synth artifacts) |
| `VillaPaymentDetails` | 3 | payment | `payments.Payment` |
| `VillaBookingDetails` | 2 | booking_charge_item | `reservations.BookingChargeItem` |

`syncrecord_zoho` additionally re-reads `VillaMaster`, `VillaContact`,
`VillaEnquire`, `VillaQuotationMaster`, `VillaBooking` for `ZohoId`.

## Joined (read inside another loader's query)

| Table | Rows | Read by |
|---|---|---|
| `VillaFeaturesCategoryMappings` | 392 | feature (first category subquery) |
| `VillaSeasonDates` | 736 | rate_plan (min/max effective dates); 96% single-range, vestigial |
| `VillaOccupencyPrice` | 263 | rate_rule (occupancy-band expansion, BUG-013) |
| `VillaContactRoleMapping` | 335 | property_contact_assignment (role source) |
| `VillaPayment` | 1 | payment (header join for BookingId) |

## Dropped — deliberate, with justification

| Table | Rows | Justification |
|---|---|---|
| `VillaRoles` | 5 | Static 5-row lookup → `ContactRole` TextChoices; mapped 1:1 in `_ROLE_MAP` (GAP-048). |
| `VillaStatus` | 4 | Static lookup → `Property.status` TextChoices. |
| `EnquireStatus` | 4 | Static lookup → `Enquiry` stage enum (int map in loader). |
| `AvailabilityStatus` | 9 | Status-code lookup for `VillaAvailability` day grid → new model has no day grid (see BLOCKER below for the data itself). |
| `CalculationType` | 2 | Static lookup → commission calc enum. |
| `DepositType` | 2 | Static lookup → deposit type enum. |
| `ChangeOverDays` | 8 | Weekday lookup → `ChangeOverRule` weekday enum. |
| `VillaPaymentStatus` | 24 | Payment-status lookup → `Payment.status` TextChoices. **Verify**: 24 rows is large for a status lookup — eyeball contents once (could be misnamed log). |
| `VillaConciergeServices` | 2 | Two tier labels → TextChoices. |
| `VillaBookingConcierge` | 0 | Empty in prod — nothing to migrate. |
| `VillaRentalAlternatives` | 160 | Multi-property bundling not in MVP (documented future scope). Information-bearing: recoverable from archived dump. |
| `VillaCodeSentHistory` | 1 | Ephemeral 2FA-code log; 1 row; worthless post-cutover. |
| `VillaEmailLinkLog` | 10 | Ephemeral magic-link log; expired tokens. |
| `VillaFeaturesIcons` | 17 | Icon asset lookup for legacy UI; new FE has its own icon system. |
| `VillaConfigWebsite` | 10 | WordPress publishing-target registry — part of the documented WP-backfill descope (`WORDPRESS_BACKFILL.md`); revisit if WP continuity is bought back. |

## Dropped — asserted by docs, verification still owed

| Table | Rows | Status |
|---|---|---|
| `VillaContactMap` | 230 | **Verified 2026-07-05 — the "duplicate" claim was FALSE but DROP stands**: it is a contact-level `(ContactId, RoleId)` role directory, not a mapping duplicate. 220/230 rows are reproduced by loaded property assignments; the 10 uncovered rows are role tags on contacts with no property mapping (the new model only carries roles per assignment, GAP-048). Loss: a bare role label on 10 loaded contacts. |
| `VillaContactGroupMap` | 46 | **Verified 2026-07-05; DECISION 2026-07-06: DROP (owner call, GAP-073)**: group-scoped contact assignments (columns `GroupId, ContactId` only — no role, no flags). `VillaContactMapping.GroupId` is never set, so 0/46 edges are directly covered; 27/46 are redundant via property expansion; **19 edges (38 contact×property links) exist only here**. A load-time expansion into `PropertyContactAssignment` was prototyped on `feat/legacy-loader` but the owner dropped it post-GAP-070 (the product no longer has groups). The 19 net-new edges remain recoverable from the archived dump if a business need surfaces. |

## Classified 2026-07-05 (investigation agents; details in DRYRUN_LOG.md)

1. **`VillaAvailability` — 57,389 rows → LOAD (future slice only).**
   Past grid days are display residue; FUTURE non-available runs (statuses
   30/40/50/60) are real state existing nowhere else. New
   `availability_block` loader coalesces them into block rows
   (`avail-{prop}-{start}`), full-replace per run, reconcile check on
   future-day arithmetic. On this stale dump: 1 run (property 133 booked
   2026-07-25→08-22); count is dump-relative by design. Grid itself +
   `AvailabilityStatus` lookup: dropped (mechanism replaced).
2. **`VillaPropertyImagesDescription` — 315 rows → LOAD (full).**
   Not captions: one row per villa of website section copy.
   `Interior1/2`/`Exterior1/2` pair 1:1 with slot-flagged images → joined
   into `PropertyImage.description`. **DECISION 2026-07-06: PRESERVE ALL** —
   `WebDesc1/2` (298 villas) and `Location1/2` (276 villas) fold into new
   `PropertyDescription` sections (`WEB_DESCRIPTION`, `LOCATION`); `VodeoUrl`
   (31 links) → new `Property.video_url`. Content verified distinct from the
   `OverView` blurb already migrated (WebDesc = activities/extras, Location =
   location copy). Loader change under way.
3. **`VillaRoomsPlacement` — 46 rows → LOAD (GAP-065).** Curator-entered
   building labels referenced by 1,819 rooms; `RoomLoader` was hardcoding
   MAIN_HOUSE for all of them (live data-loss bug, already ticketed).
   Loader now maps placement per GAP-065 scope. (The ticket's "floor" axis
   is NOT in this table — building only.)
4. **`VillaWebsitePricing` — 441 rows → DROP min/max cache; POA DEFERRED.**
   Min/max is a stale display cache (only 113/441 match live rates);
   superseded by `VillaPricingSummary` rebuilt from loaded rates. The POA
   flag is curator-set (**18** live villas, `IsPOA=1`; not derivable from
   rate-level `is_poa`) and has no property-level home. **DECISION
   2026-07-06: DEFERRED** pending a schema call on a property-level POA flag.
   Migration risk if it ships un-resolved: those 18 villas show a computed
   price instead of legacy "price on application / enquire" — a
   customer-facing behavioural regression. Tracked as an open cutover item,
   NOT silently dropped.
5. **`VillaConfigEmail` — 20 rows → DROP; provision manually.** 1 real
   profile + 19 UAT rows. Secrets don't ride the migration: create the one
   SYSTEM `comms.SmtpProfile` by hand at cutover (CUTOVER step to add).
6. **`VillaConfigGeneral` — 10 rows → DROP** (legacy app self-config; 1 prod
   URL + 9 localhost rows). **`VillaConfigPropertyDefault` — 1 row → KEEP
   until the deferred IsDefault resolution lands**: GAP-073 deferred the
   `IsDefault*` default-resolution work to a separate finance investigation
   (it targeted the now-deleted `GroupFinance`; must be re-aimed at GAP-070's
   `PropertyDefaults`). Until then min_nights ×197 / commission ×68 /
   currency ×91 still load from the stored VillaMaster columns — do NOT drop
   this config row (see DRYRUN_LOG loader bugs 5–6 and the deferral note).
7. **`VillaPaymentStatus` — 24 rows → DROP.** Misnamed table: a
   payment-gateway webhook/event log from the Feb–Apr 2025 provider trial,
   not a status lookup. Ephemeral events, recoverable from the archived
   dump.

## Notes

- Booking-side volume is tiny (3 bookings / 19 quotations / 1 payment / 2
  charge items): the pre-BUG-016 dry-run counters and any money-parity checks
  exercise almost nothing. **Property/rates/images/availability are where the
  real migration risk lives.**
- `VillaEnquire` shows 451 rows here vs 453 in the older reconciliation doc —
  sys.partitions counts are approximate under concurrent write but this DB is
  frozen; trust `COUNT(*)` at reconcile time.
- **Dry-run finding 2026-07-05**: `SyncRecordZohoLoader` crashes on the live
  dump — `VillaQuotationMaster` and `VillaBooking` have **no `ZohoId` column**
  (only `VillaContact`, `VillaEnquire`, `VillaMaster` do). The loader,
  CUTOVER §4b, and `08-integrations.md` all assume five ZohoId-bearing
  tables. Also: the crash aborted the whole `loadlegacy --all` run — no
  per-loader crash isolation.
- CUTOVER §4f role-source warning **resolved 2026-07-05**: live
  `VillaContactMapping` has **no `RoleId` column** (the doc claim was wrong
  for this schema vintage); 3/335 mappings have no role child → `owner`
  fallback (accepted). `GroupId`, all `IsAccess*`/`IsNotify*` flags and
  `Notes` are zero/unused in prod — dropping them loses nothing.
