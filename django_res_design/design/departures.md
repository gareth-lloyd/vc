# 09 — Departures from the Original

A table-by-table mapping of the legacy .NET model to the Django redesign. Use this to orient yourself relative to the .NET codebase or schema.

Disposition column legend:
- **Split** — single legacy model decomposed into multiple Django models.
- **Renamed** — same shape, different name (or typo fixed).
- **Merged** — multiple legacy models collapsed.
- **Replaced** — different model design entirely.
- **Dropped** — not represented in the new design.
- **Moved** — same data lives in a different app/area.
- **As-is** — preserved with only cosmetic cleanup.

## Property domain

| Legacy | New | Disposition | Rationale |
|---|---|---|---|
| `VillaMaster` | `properties.Property` + `PropertyLocation` + `PropertyCapacity` + `PropertySettings` | Split | God object (80 cols); forms/queries hit narrower tables |
| `VillaMaster.IsDefaultSetting*` booleans | Nullable fields in `PropertySettings` + `GroupSettings` defaults + `effective()` resolver | Replaced | Clean inheritance; no boolean salad |
| `VillaMaster.Latitude/Longitude` (nvarchar) | `PropertyLocation.latitude/longitude` (Decimal(9,6)) | Replaced | Numeric, indexable |
| `VillaMaster.ZohoId`, `SyncId`, `OldVillaId` | `integrations.SyncRecord` + `legacy_id` on Property | Moved | Domain models stay focused |
| `VillaPropertyCategory` | `properties.PropertyCategory` | Renamed | — |
| `VillaGroup` | `properties.PropertyGroup` + `GroupSettings` + `GroupFinance` (single flat model per #36) | Renamed/Extended | Group now owns defaults; one finance row per group (no per-concern siblings) |
| `VillaCountry` | `properties.Country` | Renamed | Canonical ISO-3166 rows are seeded via `django-countries` (migration `properties.0009`); legacy `VillaCountry` rows merge onto them by iso2 (with name-lookup fallback for rows missing ISO codes). Unrecognised rows collapse onto the `unknown_country()` sentinel so downstream FKs still resolve. |
| `VillaRegion` | `properties.Region` | Renamed | — |
| `VillaRoom` (+ bed counts) | `properties.Room` + `RoomBeds` (OneToOne) | Split | Beds split out; placement enum |
| `VillaRoomsPlacement` | `Room.placement` TextChoices | Replaced | Fixed set; no table needed |
| `VillaPropertyImage` (with `IsHero`/`IsInterior1/2`/`IsExterior1/2`/`IsGallary`) | `properties.PropertyImage` + `kind` TextChoices + `UniqueConstraint(hero)` | Replaced | One enum field, validated; `IsGallary` typo fixed |
| `VillaFeature`, `VillaFeaturesCategory` | `properties.Feature` + `FeatureCategory` | Renamed | — |
| `VillaFeaturesMapping` | M2M `Property.features` (plain through) | Replaced | No per-link metadata in legacy; auto-through is enough |
| Legacy "Tags" admin page (`Tags.razor` at `/tags`) | `properties.Feature` filtered by `service_type` | Dropped | There is no `Tags` / `VillaTags` table in the legacy schema — confirmed against `live-db-24-apr.sql`, `VillaDb.sql`, and `DbScript.sql` (zero `CREATE TABLE` matches). The `/tags` Blazor page is a `VillaFeatures` CRUD form segmented by a `ServiceType` enum (`ContactService=10`, `PropertyFeature=20`) and persists via `ResService.ModifyFeatures`. The new design covers the same discriminator (with finer granularity) via `Feature.service_type` TextChoices (`AMENITY` / `INCLUDED_SERVICE` / `PAID_ADDON`). No `Tag` model, no `PropertyTag` junction, no `/tags` API resource. See reconciliation issue #8. |
| `VillaCollection` | `properties.Collection` | Renamed | — |
| `VillaCollectionsMapping` | `properties.CollectionMembership` (explicit through) | Renamed/Extended | Retains sort order + featured_until |
| `VillaNearBy`, `VillaNearByLocationType` | `properties.PropertyNearbyPlace` + `NearbyPlaceType` | Renamed | — |
| `VillaContact` | `accounts.Person` | Moved/Folded | Folded into the unified `Person` (`kind=CONTACT`); address/preferred-method cleaned up (GAP-045) |
| `VillaContactEmail`, `VillaContactTele` | `accounts.PersonEmail`, `accounts.PersonPhone` | Renamed | `Tele` → `Phone`; `Contact*` → `Person*` (GAP-045) |
| `VillaContactRoleMapping` | `properties.PropertyContactAssignment` (with role, dates, primary) | Renamed/Extended | Adds start_date/end_date |
| `VillaRoles` | `accounts.ContactRole` TextChoices | Replaced | 5 static rows in legacy (`Owner`, `Agent`, `Villa Admin`, `Villa Manager`, `Management Company`), FK'd from `VillaContactMap` — this is the *contact-to-property* role, not a staff role. New enum is `OWNER` / `MANAGER` / `AGENT` / `HOUSEKEEPER` / `OWNERS_REPRESENTATIVE`. See reconciliation issue #9. |
| `UserMaster.IsSystemAdmin` (bool) | `accounts.User.role` (fixed `StaffRole` TextChoices: `ADMIN` / `RESERVATIONS` / `ACCOUNTS` / `VIEWER`) + Django `auth.Group` per enum value | Replaced | Legacy had no staff-role concept beyond `IsSystemAdmin`. Migration: `IsSystemAdmin=1` → `ADMIN`; `IsSystemAdmin=0` → `RESERVATIONS` (operator can subsequently lower to `ACCOUNTS` / `VIEWER`). No editable role table — see reconciliation issue #9. |
| `VillaContactGroupMap`, `VillaContactMap`, `VillaContactMapping` | — | Dropped | Duplicates in legacy schema |
| `VillaSite` | `Enquiry.site_source`, `Booking.site_source` (TextChoices) | Replaced | Was effectively an enum |
| `VillaStatus` (live DB seed: 4 rows — `live_online`, `live_offline`, `pending`, `archive`) | `Property.status` TextChoices (`DRAFT` / `ACTIVE` / `ARCHIVED`) | Replaced | Fixed 3-value enum. Mapping: `live_online` → `ACTIVE`, `pending` → `DRAFT`, `archive` → `ARCHIVED`, `live_offline` → `ARCHIVED` (with operator notice — the "temporarily not bookable" effect is now expressed via `PropertySettings.availability_default = UNAVAILABLE`, a separate axis from publication status). API verbs are `:activate` / `:archive` / `:restore` (not the earlier `:publish` / `:unpublish`). See reconciliation issue #23. |
| `VillaMaster.WebsiteDescription`, `HouseRules`, `FeatureDescription`, `RoomDescription`, plus the unmapped Blazor "Further information" textarea | `properties.PropertyDescription` rows keyed by `section` (`OVERVIEW` / `HOUSE_RULES` / `VILLA_INFO` / `FURTHER_INFO`) | Replaced | Flat columns become normalised child rows; one row per (property, section), sparse. Migration: `WebsiteDescription` → `OVERVIEW`; `HouseRules` → `HOUSE_RULES`; `FeatureDescription` + `RoomDescription` concatenated with paragraph break → `VILLA_INFO`; "Further information" content (Blazor-only, never had a column) → `FURTHER_INFO` only if surviving content is found. Backend `Property` model no longer carries these as flat columns. API `/properties/{id}/descriptions/{section}` is a 1:1 mirror of the table. See reconciliation issue #28. |

| Legacy availability status code 20 ("Available – Enquire") | `PropertySettings.requires_enquiry_first` (nullable bool, inherits from group) | Replaced | Restores the legacy UX affordance ("quotable but not direct-bookable") without inflating `Property.status` past its 3-value (`DRAFT` / `ACTIVE` / `ARCHIVED`) shape. Public site reads this to gate the "Book now" button. |

## Finance domain

| Legacy | New | Disposition | Rationale |
|---|---|---|---|
| `VillaFinance` | `properties.PropertyFinance` (flat) + `properties.GroupFinance` (flat group floor) | Replaced | Single flat model per scope; concerns prefixed (`commission_*`, `tax_*`, `bank_*`, `deposit_*`/`interim_*`/`days_*`, `security_deposit_*`). Earlier draft had 5 OneToOne children plus 5 group mirrors; collapsed per reconciliation issue #36 — the "per-concern permissions" rationale doesn't apply at MVP staff-role granularity |
| `VillaFinance.CommissionType/Amount/Note` | `PropertyFinance.commission_calculation_type` / `commission_amount` / `commission_note` (group counterpart on `GroupFinance`) | Merged | Inline on the flat model |
| `VillaFinance.TaxNumber/IsExempt/Percentage/IsDefaultTax` | `PropertyFinance.tax_number` / `tax_is_exempt` / `tax_percentage` (null = inherit from `GroupFinance`) | Merged | `IsDefault*` flag pattern dropped |
| `VillaFinance.BankAcc*` | `PropertyFinance.bank_*` fields (group default on `GroupFinance.bank_*`) | Merged | Sensitive fields tagged for `AuditLog` redaction; encrypted at rest |
| `VillaFinance.PaymentSchedule*` | `PropertyFinance.deposit_*` / `interim_*` / `days_*` fields | Merged | — |
| `VillaFinance.SecurityDeposit*` | `PropertyFinance.security_deposit_*` fields | Merged | — |
| _(none — legacy had cancellation-policy fields scattered across UI text and no structured columns)_ | `PropertyFinance.cancellation_fee_amount` / `cancellation_fee_percent` / `cancellation_window_days` / `cancellation_notes` + `GroupFinance` mirror | Added | Makes the cancellation refund flow (`booking-cancellation.md`) computable. Consumed by `payments.RefundService.from_cancellation()` — see `07-payments.md`. |
| `DepositType` | TextChoices on `PropertyFinance.deposit_calculation_type` / `security_deposit_calculation_type` | Replaced | Fixed enum |

## Pricing domain

| Legacy | New | Disposition | Rationale |
|---|---|---|---|
| `VillaSeason` | `pricing.RatePlan` | Replaced | Plan as the grouping container (name, notes, inclusion, currency, envelope dates) |
| — (legacy had no equivalent) | `pricing.RateCard` | Added | Operator-mental-unit: name, min/max nights, discount profile. Sits between Plan and Rule. (Changeover is property-level, not card-level — GAP-007.) |
| `VillaSeasonRate` | `pricing.RateRule` | Replaced | Price row with date range + party range; one card has many rules (one per band / disjoint sub-range). Legacy overlaps are resolved at load time (`data_migration/CUTOVER.md`); precedence between cards is `RateCard.sort_order` |
| `VillaSeasonDate` | Folded into `RateRule.date_from/date_to` | Merged | Production data showed ~1.0 ranges per season; separate table was vestigial |
| `VillaOccupencyPrice` | Folded into sibling `RateRule` rows on the same card | Merged | Only 3% of legacy rates used banding; sibling rules with disjoint party ranges express the same shape |
| `VillaWebsitePricing`, `VillaMapping` | `pricing.VillaPricingSummary` (signal-rebuilt cache, named explicitly) | Replaced | Honest about being a cache; single owner |
| `VillaCurrency` | `pricing.Currency` | Renamed | — |
| `ChangeOverDays` | `pricing.ChangeOverRule` (per-property, date-bounded) + enforcement in service | Replaced | Was unused as a constraint in legacy |
| Legacy changeover auto-shift (`ResService.cs:2028-2041`, silently advanced arrival to next valid weekday) | `ChangeoverService.align_forward` called from `PricingEngine.quote()` (step 1a) | Reinstated | The rebuild first hard-rejected off-weekday arrivals (`ChangeoverViolation`); GAP-007 restores the nudge as the **single** mechanism — property-level changeover only, always shift + surface (`Quote.changeover_shifted_from`), never reject. The hard-reject gate and override flag were removed; the shifted dates are persisted onto the line, hold, and booking. |
| `CalculationType` | TextChoices on `RateRule` and `Extra.calc` | Replaced | Fixed enum |
| `sp_getQuotationData` (500+ LOC stored proc) | `pricing.services.PricingEngine.quote()` returning `Quote` dataclass | Replaced | Testable, composable, snapshotable |
| Legacy no-rate-for-night default (`SettingNightlyPrice × 7`, `ResService.cs:2150-2160`) | `pricing.RatePlan.fallback_nightly` (opt-in, per-plan/currency) + engine synthetic fallback line | Reinstated (opt-in) | The rebuild first dropped this (raised `NoRateAvailable`); GAP-008 restores it as an explicit field rather than a silent property-price echo. `NULL` = keep the hard error. |
| Tax fields on rate | `properties.PropertyFinance.TaxPolicy` (config) + resolver call in PricingEngine | Moved | Tax is property/group configuration, not a per-rate row |
| Commission fields on rate | `properties.PropertyFinance.Commission` (config) + resolver call in PricingEngine | Moved | Same — config, not per-rate |
| Discount fields on rate (`IsDiscount` / `DiscountRate` / `DiscountType` / `DiscountApply` / `DiscountNight`) | `pricing.Discount` (scoped to RateCard, with `rule_kind` for early-bird / last-minute / length-of-stay / repeat-guest / promo-code) | Added / Replaced | Legacy **stored but never applied** these — `RatesModel.Calculate()` read `DiscountType` into an enum and stopped — so the rebuild's `Discount` engine is net-new, not a reproduction. Discounts are now first-class, queryable, and actually applied. `repeat_guest` is recognised but unimplemented in v1 (excluded at the engine queryset — GAP-009); `uses_count`/`max_uses` enforcement is deferred to the booking-redemption slice; the legacy `DiscountApply` gross/net target is intentionally dropped. |
| `VillaSeasonRate.IsExTra=1` rows (capacity uplifts, service tiers — 122 rows) | Two destinations: (a) capacity uplifts become additional `RateRule` rows with appropriate party ranges; (b) named property charges (cleaning / pet / heating / linen / extra-bed) become `pricing.Extra` rows | Split | Legacy conflated two concepts; new model separates capacity-pricing from add-on charges |
| Cleaning / pet / heating / linen fees (never structured in legacy — lived as free-text notes on `VillaBookingConcierge`) | `pricing.Extra` | Added | First-class typed entity for what legacy spread across rate-row notes and concierge free text |

## Reservations / availability

| Legacy | New | Disposition | Rationale |
|---|---|---|---|
| `VillaEnquire` | `reservations.Enquiry` + `accounts.Person` (split) | Split | Person split out from the enquiry; status enum cleaned |
| `VillaEnquire.Notes` (guest-submitted) | `Enquiry.inbound_message` (single immutable TextField) | Renamed | Captures the original web-form message as provenance, not a note |
| `VillaEnquire.PreferencesNote` + any operator scratchpad usage of `Notes` | `reservations.EnquiryNote` (kinds `general` / `internal` / `preferences`) | Collapsed | Per-row authorship and timestamps; matches the `/enquiries/{id}/notes` API surface |
| `EnquireStatus` | `Enquiry.status` TextChoices | Replaced | — |
| `VillaClientDetail` | `accounts.Person` (`client-{Id}`, `kind=CUSTOMER`, via `ClientLoader`) | Merged | One unified `Person` identity (folds in the legacy Enquiry contact fields), with optional `User` OneToOne |
| `VillaClientPrefMaster` | `reservations.GuestPreferenceType` | Renamed | Declarative field-rename (13 rows: bed types and similar). |
| `ClientPreferenceDetails` | `reservations.GuestPreference` | Renamed | One row per (person, type, optional quotation). Duplicate triples collapse to the first occurrence on import (~93 of 167 legacy rows). |
| `VillaQuotationMaster` | `reservations.Quotation` | Renamed | — |
| `VillaQuotationDetail` | `reservations.QuotationLine` + `pricing_snapshot` JSON | Renamed/Extended | Adds price snapshot |
| `TblVillaQuotationMaster` | — | Dropped | Legacy duplicate table |
| `VillaBooking` | `reservations.Booking` (FK to QuotationLine, full state machine, pricing snapshot) | Replaced | Real FK + price-lock + state machine |
| `VillaBooking.IsActive`/`Tbc`/`IsOwnerConfirmed`/`IsDepositePaid`/`IsBankPaid` booleans | `Booking.status` TextChoices | Merged | Single source of truth |
| `VillaBooking.DepositAmount`, `VillaBooking.DepositPercentage` | `PropertyFinance.deposit_*` (config) + `Payment(purpose=DEPOSIT)` (workflow + ledger) + `Booking.pricing_snapshot` (immutable price-at-confirmation) | Dropped | Two sources of truth on the booking row were collapsed: the deposit *requirement* is computed from `PropertyFinance` at booking-creation time; the deposit *track* lives on the spawned `Payment(purpose=DEPOSIT)` row; the deposit *figure* is also embedded in the locked `pricing_snapshot`. `Booking` itself no longer carries either column. See reconciliation issue #45. |
| `VillaBooking.Notes`, `VillaBooking.ConciergeNotes`, and the unmapped Blazor "Internal booking information" / "Villa notes" textareas | `reservations.BookingNote` (kinds `general` / `internal` / `concierge` / `villa`) | Collapsed | Per-row authorship, timestamps, and visibility gating; matches the `/bookings/{id}/notes` API surface. Migration: one non-empty source column → one seed `BookingNote` keyed by `kind` |
| `VillaBookingDetails` (Price + Notes + CurrencyId rows; legacy delete-and-reinserted them and regenerated the payment schedule on every booking save) | `reservations.BookingChargeItem` (signed `amount` — negative = credit, `label`, currency pinned to `booking.currency`) | Replaced | First-class CRUD with audit trail + `BookingEvent`s instead of delete-and-reinsert. PENDING payment rows resize on change (`booking_total_changed` → `PaymentScheduler.resync_for_booking`) — an improvement over legacy's full schedule regeneration, since settled money is never rewritten. Legacy-data loader: `BookingChargeItemLoader` (GAP-017, resolved 2026-07-02 — `data_migration/CUTOVER.md` §4g). |
| `VillaArchiveBooking` | `Booking.is_archived` flag (+ `archived_at`) on the canonical row; archive/restore audited via `BookingEvent` | Dropped/Replaced | No separate table. Archive is an operator-facing "tidy out of main list" flag, orthogonal to the state machine (the terminal post-stay state itself is `Booking.status='checked_out'`). See reconciliation issue #7. |
| Date-change audit (legacy had none — `Booking.razor`'s `OnFromDateChange` overwrote `FromDate` in place; the `ModifyBooking` service emitted no per-change audit row; the live DB has no `VillaBookingDateHistory` / `BookingChange*` table) | `BookingEvent` row written by `Booking.modify_dates()` / `Booking.modify_guests()` with `meta={"from": [...], "to": [...], "from_snapshot": {...}, "to_snapshot": {...}}`; `Booking.pricing_snapshot` regenerated via `PricingEngine.quote()` | Added | New design enforces audit + pricing-snapshot regeneration on date/guest changes. Resolved in issue #7. |
| `VillaCheckoutDetail` | `payments.Payment` (one row per `purpose ∈ {DEPOSIT, BALANCE, SECURITY_DEPOSIT}` per booking) | Replaced | Despite the name, `VillaCheckoutDetail` was not a hospitality check-in/out record nor a gateway settlement table — it was the 3-tier **payment-schedule ledger** (one row per scheduled due: Initial Payment Due, Rental Balance Payment, Security Deposit), with `Amount` / `PaymentStatus` / `PaymentId` / `PaymentMethod` / `Description` columns. Confirmed by `VillaCheckoutDetail.cs` and `CheckoutPaymentType` enum in `BookingInfoModels.cs`. The new `Payment` model (purpose × status × due_at) is a strict superset. The legacy `/checkouts` API endpoint is dropped (see reconciliation issue #6); queries land on `/payments?purpose=…` instead. |
| `CheckoutPersonalInfo`, `CheckoutAdditionalInfo` | Fields on Booking + `accounts.Person` | Merged | — |
| `VillaAvailability` (daily grid) | `BookingHold` + range queries on `Booking` + Postgres `EXCLUDE` constraints | Replaced | Range model, DB-enforced no-overlap |
| `AvailabilityStatus` | `BookingStatus` + `BookingHold.reason` | Replaced | Explicit state machine |
| `VillaBookingConcierge` (legacy: BookingId + Price + free-text Notes) | `reservations.BookingConciergeItem` (tier TextChoices + per-item name/description/unit_price/unit/currency/quantity/status) | Replaced | Per-item shape moves onto the line; no upstream catalogue model |
| `VillaConciergeServices` (legacy: 2 rows of tier-label strings) | `ConciergeTier` TextChoices (`QUINTESSENTIAL`, `SIGNATURE`) on `BookingConciergeItem` | Dropped | A 2-row lookup table doesn't earn its keep; legacy concierge items always carried per-row free-text price + notes anyway. No `ConciergeService` model; no `/concierge-services` API. See reconciliation issue #34. |
| `VillaRentalAlternative`, `VillaPropertyMapAlternativeAndRentToTogether` | — | Dropped (future scope) | Multi-property bundling not in MVP; revisit |

## Payments

| Legacy | New | Disposition | Rationale |
|---|---|---|---|
| `VillaPayment` | `payments.Payment` (single status enum + purpose enum) | Replaced | One model, one status |
| `VillaPaymentDetail` | `payments.PaymentLine` | Renamed | — |
| `VillaPaymentStatus` | `Payment.status` TextChoices | Replaced | Fixed enum |
| `InitialPaymentStatus`, `BalancePaymentStatus`, `DepsitPaymentStatus` (three enums) | `Payment.purpose` + `Payment.status` | Merged | Three enums collapse into one model with a purpose field |
| `PaymentStatusLog` | `payments.PaymentEvent` | Renamed/Extended | Append-only with delivery FK; now also audits `Refund` transitions via a polymorphic `payment` / `refund` FK |
| Flywire webhook (hardcoded VC prefix) | `payments.WebhookDelivery` + `/webhooks/payments/<provider_slug>/` URL routing + Celery dispatch | Replaced | Persist-first idempotent, multi-provider safe |
| _(none — no legacy refund table)_ | `payments.Refund` with four-state workflow (`PENDING` → `APPROVED` → `EXECUTING` → `SUCCEEDED`/`FAILED`, plus terminal `REJECTED`/`CANCELLED`) | New | Legacy DB has zero refund tables/columns and no Blazor refund pages — refunds were issued manually through the gateway dashboard with no in-app audit. The new model enforces separation of duties (requester ≠ approver) and produces `Payment(purpose=REFUND)` rows on `:execute` for the gateway transaction. |

## Integrations

| Legacy | New | Disposition | Rationale |
|---|---|---|---|
| `ZohoId` columns on every table | `integrations.SyncRecord` (generic FK) | Moved | Single observability point |
| `SyncId`, `IsSync`, `IsSynced` booleans | `integrations.SyncRecord.status` + fingerprints | Moved | Drift detection, retry tracking |
| `OldVillaId`, `OldId` | `legacy_id` (CharField, nullable, indexed) on each domain model | Renamed | One slot per model |
| `VillaCodeSentHistory`, `VillaEmailLinkLog` | `comms.EmailLog` | Replaced | Append-only dispatch log with template version + correlation keys. See `10-comms.md`. |
| `VcemailTemplate` | `comms.EmailTemplate` (versioned, DB-stored, file-seeded) | Replaced | Active template per `key`; admin edits bump `version`. See `10-comms.md`. |

## Accounts

| Legacy | New | Disposition | Rationale |
|---|---|---|---|
| `UserMaster` | `accounts.User(AbstractUser)` | Replaced | Standard Django auth, email login |
| `UserMaster.SmtpAddress/User/Password/Port` | `comms.SmtpProfile(scope=PERSONAL, owner=user, ...)` | Moved | Reinstated for the per-agent "send as" quotation flow specified in `workflows/11-integrations/transmission.md`. Credentials encrypted at rest (Fernet); only the `comms.EmailService` dispatcher reads them. See `10-comms.md` and the decisions log entry. |
| `UserMaster.IsLock` | `User.is_active=False` | Replaced | Standard Django |
| `UserMaster.IsSystemAdmin` | `User.is_superuser` | Replaced | Standard Django |

## Cross-cutting

| Legacy pattern | New pattern |
|---|---|
| Mixed `CreateAt`/`CreatedAt`/`UpdateAt`/`UpdatedAt`/`UpdtedAt` (typos) | `TimestampedModel.created_at` / `updated_at` |
| Mixed `CreatedBy`/`UpdatedBy` (int or string) | `AuditedModel.created_by` / `updated_by` FK to User |
| Mixed `DeletedAt`/`DeletedBy` on every table | **Eliminated.** Lifecycle is always explicit (`status` TextChoices, `is_active`, `archived_at`/`cancelled_at`, or hard delete). Sensitive-config field-edit history lives in `AuditLog`. See "Soft delete eliminated" below. |
| CSV string foreign keys (`FeatureIds`, `RegionIds`, `CountryId`) | Proper M2M and FK |
| Booleans for inheritance (`IsDefaultSetting*`) | Nullable fields + `effective()` resolver |
| Bit flags for image kinds | Single `kind` TextChoices + UniqueConstraint |
| 500+ LOC stored procedures | `services.py` Python services |
| App-layer FK only | Real DB FKs with chosen `on_delete` |
| Daily-row availability grid | Range queries + Postgres `EXCLUDE` constraints |
| Three payment status enums | One model with `purpose` + `status` |
| Hardcoded webhook prefix parsing | Provider-slug URL routing |
| Per-row ZohoId / SyncId | `integrations.SyncRecord` |

## Legacy typo registry — preserve-vs-rename plan

The legacy system carries a number of misspellings into table/column names, SP names, enum constants, Zoho module identifiers, and even UI strings. Each is either **preserve-for-compat** (legacy data or external systems depend on the exact spelling) or **rename-with-migration** (a clean Django name with a `RenameField` migration on cutover). Pick once per typo and never invert it.

The Django port refers to entities by the **new** name; the legacy spec text in `workflows/**` preserves the **legacy** name (so the workflow specs remain greppable against the .NET source). The redesign tables in this file are the only place where the two columns sit side by side.

| Legacy spelling | Intended spelling | Where it appears | Disposition |
|---|---|---|---|
| `VILLLA_MASTER` (three L's) | `VILLA_MASTER` | Zoho module identifier; `ResApiService.cs:1007,1015`; SQL switch in `live-db-24-apr.sql:116743` | **Preserve.** The Zoho organisation already has records keyed under this module name. Renaming requires a Zoho-side migration we are not scoping. Treat as a frozen integration artifact; the Django integration layer maps `integrations.SyncRecord.zoho_module = "VILLLA_MASTER"` and nothing in the domain layer ever sees the typo. |
| `EnquireSaurce` | `EnquireSource` / `enquiry_source` | `ResService.cs:2391`; throughout enquiry workflows | **Rename.** Internal field, no external dependency. Migration: `RenameField` on cutover. |
| `ViilaStatus` (double-i) | `VillaStatus` / `status` | `VillaMaster` column (`live-db-24-apr.sql:79246`); read sites throughout `PropertyService.cs` | **Rename.** Becomes `Property.status` (TextChoices); the integer `ViilaStatus` is replaced wholesale by an enum (`09-departures.md` Property domain). |
| `BedChildrens` | `BedChildren` / `child_beds` | `PropertyRoomsModal.cs:28`; `RoomBeds` legacy schema | **Rename.** Becomes `RoomBeds.child_beds`. |
| `OccupencyPrice`, `OccupencyFrom`, `OccupencyTo` | `OccupancyPrice` / `occupancy_price`, etc. | `VillaOccupencyPrice` table; `PropertyService.cs:1101-1130` | **Folded** (see Pricing domain row for `VillaOccupencyPrice`) — disappears with the table; no rename needed. |
| `IsApprove` | `IsApproved` / `is_approved` | Booking flow | **Rename.** Becomes a `BookingStatus` value rather than a boolean. |
| `SchedullerJob` | `SchedulerJob` | `SchedullerJob.cs:16-69` (currently `[DISABLED]`) | **Rename.** Replaced by Celery beat tasks; the class itself doesn't survive. |
| `VIllaConcierges` (capital-I, lowercase-l) | `VillaConcierges` | UPDATE statement at `ResApiService.cs:791` (slug write) | **Rename.** Becomes `reservations.BookingConciergeItem`. |
| `IsEnsuit` | `IsEnsuite` / `is_ensuite` | `PropertyService2.cs:282`; `Room` schema | **Rename.** |
| `SecurityDepositDaysDefundedAfterDeparture` | `SecurityDepositDaysRefundedAfterDeparture` / `refund_days_after_departure` | `VillaConfigPropertyDefault`, `VillaConfigGeneral`, `VillaMaster` (`live-db-24-apr.sql:61420`); `PropertyService2.cs:200` reads the typo and assigns to a clean .NET property name | **Rename.** Critical: the DB column is the typo; the C# model name is the clean version. The Django port reads the typo column and renames on migration. Do not invert. See cross-talk note in `workflows/03-catalog/property-finance.md`. |
| `Categeroy` (UI string only) | `Category` | `Tags.razor:254` ("Please select Categeroy") | **Rename.** UI-only typo; no data implications. |
| `PrefferedMethod` (double-f) | `PreferredMethod` / `preferred_contact_method` | `ResService.cs:1864` (`GetContactParams`) | **Rename.** Contact preference field. |
| `GetEqnuireDetails` | `GetEnquireDetails` / `get_enquiry` | `ResService.cs:2660` | **Rename.** Method name; no DB column. Disappears in service layer rewrite. |
| `Tele` (in `VillaContactTele`) | `Phone` | `accounts.PersonPhone` | **Rename** (already captured in main Accounts table). |
| `IsGallary` | `IsGallery` | `VillaPropertyImage` legacy column | **Replaced** (already captured in Property domain — fixed by `kind` TextChoices). |

**Convention:** when a workflow spec mentions a legacy typo, it uses the legacy spelling and tags it with `[TYPO]` inline so a grep for `[TYPO]` finds every preserve-vs-rename decision site. The disposition for each is then this table.

## Legacy security debt — must-fix on Django port

These findings are confirmed-in-code (line-cited) issues the Django redesign **must not carry forward**. Cross-referenced from the per-workflow specs.

| # | Finding | Legacy locus | Workflow spec | Django requirement |
|---|---|---|---|---|
| 1 | Flywire API key hardcoded in source (`ApiToken = "S2EyL25NWnU5Ynl0T2lXSi91Q1pjdz09"`) | `ResService.cs:320`, `ResApiService.cs:1195` | `workflows/10-payment/payment-preauth.md` | Pull from secret manager (env vars in dev, AWS Secrets Manager / Vault in prod). Never check secrets into the repo. Rotate the leaked key. |
| 2 | Flywire **sandbox** URL hardcoded as the active endpoint (`Url = "https://api-platform-sandbox.flywire.com/"`) | `ResService.cs:320` | `workflows/10-payment/payment-preauth.md` | Environment-configured base URL; the live env never points at sandbox. Add a startup assertion that `settings.FLYWIRE_BASE_URL` is non-sandbox when `DJANGO_ENV == "production"`. |
| 3 | Payment webhook accepts **unsigned** payloads — the `Digest()` HMAC helper exists but is never invoked from the handler | `PaymentController.cs:98-143` (handler), `:275-290` (helper) | `workflows/10-payment/payment-collection.md`, `workflows/11-integrations/flywire-gateway.md` | Verify HMAC before any side effect. Reject (HTTP 401) on missing or mismatched signature. Persist `WebhookDelivery.signature_valid` for audit. |
| 4 | Payment webhook has **no idempotency check** — duplicate deliveries cause duplicate state changes; the data model has a `Payment.idempotency_key` slot but it is never read or written | `ResService.cs:4374-4467` | `workflows/10-payment/payment-collection.md` | Look up `WebhookDelivery` by provider event id before processing; short-circuit duplicates. See "Idempotency" heading in `workflows/00-taxonomy.md`. |
| 5 | Every outbound transactional email BCC'd to a third-party Gmail (`connectusinfowaydemo12@gmail.com`) | `EmailService.cs:71` | `workflows/11-integrations/email-delivery.md` | Remove. Replace with structured per-message logging to a privacy-reviewed sink. |
| 6 | Email bodies (including guest PII and payment amounts) written to disk via `Utilities.WriteResLogFile` | `EmailService.cs:122`, `PaymentController.cs:140`, `ResService.cs:4464` | `workflows/11-integrations/email-delivery.md`, `workflows/10-payment/payment-collection.md` | Log message-id and recipient only; never the body. If a debug log is genuinely needed, gate it behind a temporary feature flag and a fixed retention window. |
| 7 | Email/Zoho/WordPress side effects from the webhook are **fire-and-forget** (`Task.Run` with no DLQ); transient failures vanish silently | `ResService.cs:2395-2400` (Zoho enquiry push), webhook handler downstreams | `workflows/07-enquiry/enquiry-intake.md`, `workflows/10-payment/payment-collection.md` | Queue side effects via Celery with retry + DLQ. Every integration declares its dedupe strategy (see template). |
| 8 | Two-write transitions (`SP_SAVE_BOOKING_INFO` then `sp_villaAvailability`; `sp_delete_booking` then `sp_villaAvailability`) run with **no transaction wrapper** — partial failure produces an inconsistent calendar | `ResService.cs:3242-3249`, `ResService.cs:913-931` | `workflows/06-availability/booking-status-transitions.md` | Wrap in `transaction.atomic()`, or eliminate the daily-grid mirror entirely. |
| 9 | Scheduler entirely commented out (payment reminders, hold expiry, balance flagging not running in production) | `SchedullerJob.cs:16-69` | `workflows/12-automation/scheduler-jobs.md` | Re-implement as Celery beat tasks; each task declares its idempotency / concurrency story. |
| 10 | Raw-SQL UPDATE on `VillaMaster.ViilaStatus` via C# string interpolation (params are int-typed so injection risk is nil in practice, but the pattern is unsafe) | `PropertyService.cs:565` | `workflows/03-catalog/property-master.md` | Use ORM or parameterised SQL. Never carry the C# interpolation idiom forward. |

Findings overturned during verification (kept here as a historical caveat so they are not re-raised by future audits):

- **"Tokenised charge stored as plaintext"** — false. No `TokenisedCharge` column exists on `VillaPaymentDetails` (`live-db-24-apr.sql:1912-1926`).
- **"`sp_getAvailability` mutates `VillaAvailability` as a side effect of a read"** — false. The `DELETE` statements operate on a procedure-local `@temp_table` table variable (`live-db-24-apr.sql:111935`). See `workflows/06-availability/availability-check.md` for the corrected note.

## Legacy correctness bugs explicitly fixed

Behaviours of the legacy `ResSystem/` that the rebuild changes deliberately. These are **not** the CVE-style items in "Legacy security debt" above — they are feature-correctness bugs surfaced during the 2026-05-26 scoping session with the site owner. Each must not survive into the new system.

| # | Bug | Legacy locus | New behaviour |
|---|---|---|---|
| 1 | Owner-facing rate display shows **gross rates where the owner should see net**. The legacy owner view ignores the property's `prices_entered_as` mode on the way to render. | `BookingInfo.razor` owner view, owner-statement render path; confirmed scoping-session 2026-05-26 ("net rates didn't come through — that was a problem with the logic"). | New owner views read `PropertySettings.prices_entered_as` and `RatePlan.price_basis` and render net to the owner. Verified at the owner-statement and booking-summary render layers (`product-design/03-workflows.md` owner flow). |
| 2 | Quote engine **silently falls back to the base weekly rate ÷ 7** when a party matches no occupancy band on a multi-bracket card — quietly mis-pricing instead of flagging the gap. | `ResService.cs:ProcessQuotationItemAsync` + `RatesModel.Calculate()` (`ResService.cs:2117-2134`) | `PricingEngine.quote()` resolves the bracket whose `(min_party, max_party)` interval contains the inquiry party size, and raises `PartyOutOfRange` when none matches. The legacy silent fallback is not preserved under any flag. See `04-pricing.md` "Occupancy bracket: matched, not silently fallen-back". |
| 3 | Inquiry search **misses villas with flexible (`ANY`) changeover** when the query filters to a specific weekday. Reproducible against the owner's aunt's villa (flexible check-in). | Search SP path; scoping-session 2026-05-26. | Search and availability queries must include `changeover_day=ANY` properties on every weekday filter. See `02-properties.md` `changeover_day` note and `06-availability.md` search/filter UX. |
| 4 | Inquiry search **returns unavailable properties interleaved with available ones**, slowing operator scan. | Legacy back-office quote builder. | New search hides unavailable by default with a "Show unavailable" toggle. See `06-availability.md` search/filter UX and decisions row "Search hides unavailable properties by default" in `10-decisions.md`. |
| 5 | Multi-contact context (CC'd family members, co-travellers, third-party payers) **discarded on intake** — only the lead guest survives in the data model; a decade of follow-up marketing audience has been lost. | `VillaCheckoutDetail` single-contact shape; scoping-session 2026-05-26. | `reservations.BookingGuest` through-model retains every traveller, payer, and CC'd person as an addressable `accounts.Person` row. See `05-reservations.md` and decisions row "`BookingGuest` through-model" in `10-decisions.md`. |

Each row above is independent of the security-debt table — that table is about CVE-style issues; this table is about feature correctness.

## Soft delete eliminated

The legacy convention slapped `DeletedAt`/`DeletedBy` on every table. The new design removes the entire pattern: there is no `SoftDeleteModel` base class, no `deleted_at` column anywhere, no `all_objects` manager. Lifecycle is always expressed as something the operator (and any SQL query) can see directly.

Per-concern patterns (full rules in `00-conventions.md`):

| Need | Pattern |
|---|---|
| Lifecycle states (draft / active / archived / cancelled / expired / declined / anonymized) | `status` TextChoices on the model, with `archived_at` / `cancelled_at` / `anonymized_at` timestamps for state-entry audit when needed |
| On/off toggle for lookups & catalogues | `is_active` BooleanField; default operator queries filter at the call site |
| Owned child rows | hard delete via CASCADE from the parent |
| Cross-aggregate references | `on_delete=PROTECT` blocks accidental deletion |
| Audit history of state transitions | append-only event tables (`BookingEvent`, `PaymentEvent`, `EnquiryEvent`) — never deleted |
| Audit history of sensitive-config field edits | per-model `AuditLog` row written by a `pre_save` signal |
| Personal-data removal under GDPR | **anonymization-in-place** via `Person.anonymize()`; row stays for FK integrity, `status=ANONYMIZED` |
| Duplicate records | `Person.merge(target)` rewrites FKs then **hard-deletes** the merged-from row; `AuditLog` is the only trail |

The three cases previously held out as "legitimate soft-delete uses" all resolve cleanly:

**1. `Person`** (the unified identity model — folds the former `accounts.Contact` and `reservations.Guest`, GAP-045) — gains a `status` enum (`PersonStatus`: `ACTIVE`, `INACTIVE`, `ANONYMIZED`). "Wrong contact, no relationships yet" → hard delete (PROTECT FK from `PropertyContactAssignment` gates this). "Contact retired" → `status=INACTIVE`. "Merge duplicates" → `merge(target)` rewrites FKs (on `Enquiry` / `Quotation` / `Booking` and the operator-side relations) and hard-deletes the merged-from row with an `AuditLog` entry per rewrite; the legacy `merged_into` self-FK is dropped — merge is final and the `AuditLog` is the only trail. "GDPR forget-me" → `anonymize()` overwrites PII fields with sentinels and sets `status=ANONYMIZED`; row stays for historical FK integrity.

**2. `PropertyFinance` and its OneToOne children** (`Commission`, `TaxPolicy`, `BankAccount`, `PaymentSchedule`, `SecurityDepositPolicy`) — configuration rows, not transactional state. Edits update in place. Hard delete cascades from `PropertyFinance` to its children. Owner-statement reconstruction relies on `Booking.pricing_snapshot` (which captures commission / tax / Extras at booking-creation time via the PricingEngine), not on a history of `PropertyFinance` rows. "Who changed commission from 10% to 12%?" is answered by `AuditLog` rows written by a `pre_save` signal scoped to financial-config models. `BankAccount` edits log redacted-field diffs (no cleartext IBAN in the audit table).

Other previously-soft-deletable models are reassigned as follows:

- **`status` enum already in design (kept):** `Property` (DRAFT/ACTIVE/ARCHIVED), `Booking` (11 states), `Quotation` (DRAFT/SENT/ACCEPTED/EXPIRED/CANCELLED), `Enquiry` (NEW/CONTACTED/QUOTED/LOST/CONVERTED), `Refund` (PENDING/APPROVED/REJECTED/EXECUTING/SUCCEEDED/FAILED/CANCELLED), `Payment` (PENDING/PROCESSING/SUCCEEDED/FAILED/REFUNDED/CANCELLED/EXPIRED), `SecurityDeposit` (per-kind enum).
- **`status` enum added:** `Person` (`PersonStatus`: `ACTIVE`/`INACTIVE`/`ANONYMIZED`).
- **`is_active` boolean only:** `User` (Django standard), `Currency`, `Country`, `Region`, `FeatureCategory`, `Feature`, `Collection`, `NearbyPlaceType`, `PropertyCategory`, `PropertyGroup`, `RatePlan`, `RateCard`, `RateRule`, `Discount`, `Extra`, `ChangeOverRule`, `EmailTemplate`, `SmtpProfile`.
- **Hard delete (CASCADE from owner, PROTECT from references):** `PropertyLocation`, `PropertyCapacity`, `PropertySettings`, `Room`, `RoomBeds`, `PropertyImage`, `PropertyNearbyPlace`, `PersonEmail`, `PersonPhone`, `CollectionMembership`, `PropertyContactAssignment`, `Commission`, `TaxPolicy`, `BankAccount`, `PaymentSchedule`, `SecurityDepositPolicy`, the group-level finance siblings.
- **Append-only event/audit (never deleted):** `BookingEvent`, `PaymentEvent`, `EnquiryEvent`, `WebhookDelivery`, `SyncRun`, `SyncIssue`, `EmailLog`, `FxRate`, `AuditLog`.
- **Terminal-timestamp lifecycle (already in design):** `BookingHold.released_at` (expired/released holds stay visible; only the partial `EXCLUDE` index treats them as inactive). `Booking.archived_at` (orthogonal operator-facing tidy-out flag; the underlying terminal `status` still tells the truth).

## What we did *not* break

Despite the moderate-departure brief, these legacy concepts survive intact:

- The Enquiry → Quotation → Booking → Check-in → Check-out workflow shape.
- Per-villa seasons, occupancy bands, multi-currency rates.
- 3-tier payment schedule (deposit / balance / security deposit).
- Owner-confirmation manual approval flow.
- Multi-property groups with default inheritance.
- Curated marketing collections.
- Concierge add-ons.
- Zoho CRM integration.
- Flywire as the primary payment provider.

The product's behaviour is the same; the data model under it is sound.
