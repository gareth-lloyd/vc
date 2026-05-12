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
| `VillaGroup` | `properties.PropertyGroup` + `GroupSettings` + group-level finance siblings | Renamed/Extended | Group now owns defaults |
| `VillaCountry` | `properties.Country` | Renamed | — |
| `VillaRegion` | `properties.Region` | Renamed | — |
| `VillaRoom` (+ bed counts) | `properties.Room` + `RoomBeds` (OneToOne) | Split | Beds split out; placement enum |
| `VillaRoomsPlacement` | `Room.placement` TextChoices | Replaced | Fixed set; no table needed |
| `VillaPropertyImage` (with `IsHero`/`IsInterior1/2`/`IsExterior1/2`/`IsGallary`) | `properties.PropertyImage` + `kind` TextChoices + `UniqueConstraint(hero)` | Replaced | One enum field, validated; `IsGallary` typo fixed |
| `VillaFeature`, `VillaFeaturesCategory` | `properties.Feature` + `FeatureCategory` | Renamed | — |
| `VillaFeaturesMapping` | M2M `Property.features` (plain through) | Replaced | No per-link metadata in legacy; auto-through is enough |
| `VillaCollection` | `properties.Collection` | Renamed | — |
| `VillaCollectionsMapping` | `properties.CollectionMembership` (explicit through) | Renamed/Extended | Retains sort order + featured_until |
| `VillaNearBy`, `VillaNearByLocationType` | `properties.PropertyNearbyPlace` + `NearbyPlaceType` | Renamed | — |
| `VillaContact` | `accounts.Contact` | Moved | Lives in accounts; address/preferred-method cleaned up |
| `VillaContactEmail`, `VillaContactTele` | `accounts.ContactEmail`, `accounts.ContactPhone` | Renamed | `Tele` → `Phone` |
| `VillaContactRoleMapping` | `properties.PropertyContactAssignment` (with role, dates, primary) | Renamed/Extended | Adds start_date/end_date |
| `VillaRole` | `accounts.ContactRole` TextChoices | Replaced | Fixed enum |
| `VillaContactGroupMap`, `VillaContactMap`, `VillaContactMapping` | — | Dropped | Duplicates in legacy schema |
| `VillaSite` | `Enquiry.site_source`, `Booking.site_source` (TextChoices) | Replaced | Was effectively an enum |
| `VillaStatus` | `Property.status` TextChoices | Replaced | Fixed enum |

## Finance domain

| Legacy | New | Disposition | Rationale |
|---|---|---|---|
| `VillaFinance` | `properties.PropertyFinance` anchor + 5 OneToOne children | Split | God object → focused models |
| `VillaFinance.CommissionType/Amount/Note` | `Commission` model | Split | — |
| `VillaFinance.TaxNumber/IsExempt/Percentage/IsDefaultTax` | `TaxPolicy` model (null = inherit) | Split | `IsDefault*` flag pattern dropped |
| `VillaFinance.BankAcc*` | `BankAccount` model | Split | Often encrypted |
| `VillaFinance.PaymentSchedule*` | `PaymentSchedule` model | Split | — |
| `VillaFinance.SecurityDeposit*` | `SecurityDepositPolicy` model | Split | — |
| `DepositType` | TextChoices on PaymentSchedule/SecurityDepositPolicy | Replaced | Fixed enum |

## Pricing domain

| Legacy | New | Disposition | Rationale |
|---|---|---|---|
| `VillaSeason` | `pricing.RatePlan` | Replaced | Plan as the grouping container; cleaner semantics |
| `VillaSeasonRate` | `pricing.RateRule` | Replaced | Single rule with date range + party range + priority |
| `VillaSeasonDate` | Folded into `RateRule.date_from/date_to` | Merged | One row replaces the join |
| `VillaOccupencyPrice` | Folded into `RateRule.min_party/max_party` | Merged | Same row + range query |
| `VillaWebsitePricing`, `VillaMapping` | `pricing.VillaPricingSummary` (signal-rebuilt cache, named explicitly) | Replaced | Honest about being a cache; single owner |
| `VillaCurrency` | `pricing.Currency` | Renamed | — |
| `ChangeOverDays` | `pricing.ChangeOverRule` (per-property, date-bounded) + enforcement in service | Replaced | Was unused as a constraint in legacy |
| `CalculationType` | TextChoices on RateRule / Surcharge | Replaced | Fixed enum |
| `sp_getQuotationData` (500+ LOC stored proc) | `pricing.services.PricingEngine.quote()` returning `Quote` dataclass | Replaced | Testable, composable, snapshotable |
| Tax/commission/discount fields on rate | `Surcharge` model + `Discount` model | Replaced | Composable, queryable |

## Reservations / availability

| Legacy | New | Disposition | Rationale |
|---|---|---|---|
| `VillaEnquire` | `reservations.Enquiry` + `Guest` (split) | Split | Guest split out; status enum cleaned |
| `EnquireStatus` | `Enquiry.status` TextChoices | Replaced | — |
| `VillaClientDetail` | `reservations.Guest` (unified with Enquiry guest fields) | Merged | One Guest entity, with optional User OneToOne |
| `VillaClientPrefMaster`, `ClientPreferenceDetail` | `Guest.notes` initially; future scope `GuestPreference` model | Dropped | Underused in legacy; can re-add later |
| `VillaQuotationMaster` | `reservations.Quotation` | Renamed | — |
| `VillaQuotationDetail` | `reservations.QuotationLine` + `pricing_snapshot` JSON | Renamed/Extended | Adds price snapshot |
| `TblVillaQuotationMaster` | — | Dropped | Legacy duplicate table |
| `VillaBooking` | `reservations.Booking` (FK to QuotationLine, full state machine, pricing snapshot) | Replaced | Real FK + price-lock + state machine |
| `VillaBooking.IsActive`/`Tbc`/`IsOwnerConfirmed`/`IsDepositePaid`/`IsBankPaid` booleans | `Booking.status` TextChoices | Merged | Single source of truth |
| `VillaArchiveBooking` | `Booking.status=COMPLETED` + `BookingEvent` history | Dropped/Replaced | No drift, full audit |
| `VillaCheckoutDetail` | Fields distributed across Booking, Guest, Payment | Split | — |
| `CheckoutPersonalInfo`, `CheckoutAdditionalInfo` | Fields on Booking + Guest | Merged | — |
| `VillaAvailability` (daily grid) | `BookingHold` + range queries on `Booking` + Postgres `EXCLUDE` constraints | Replaced | Range model, DB-enforced no-overlap |
| `AvailabilityStatus` | `BookingStatus` + `BookingHold.reason` | Replaced | Explicit state machine |
| `VillaConcierge` | `reservations.BookingConciergeItem` | Renamed | — |
| `VillaConciergeService` | `reservations.ConciergeService` | Renamed | — |
| `VillaRentalAlternative`, `VillaPropertyMapAlternativeAndRentToTogether` | — | Dropped (future scope) | Multi-property bundling not in MVP; revisit |

## Payments

| Legacy | New | Disposition | Rationale |
|---|---|---|---|
| `VillaPayment` | `payments.Payment` (single status enum + purpose enum) | Replaced | One model, one status |
| `VillaPaymentDetail` | `payments.PaymentLine` | Renamed | — |
| `VillaPaymentStatus` | `Payment.status` TextChoices | Replaced | Fixed enum |
| `InitialPaymentStatus`, `BalancePaymentStatus`, `DepsitPaymentStatus` (three enums) | `Payment.purpose` + `Payment.status` | Merged | Three enums collapse into one model with a purpose field |
| `PaymentStatusLog` | `payments.PaymentEvent` | Renamed/Extended | Append-only with delivery FK |
| Flywire webhook (hardcoded VC prefix) | `payments.WebhookDelivery` + `/webhooks/payments/<provider_slug>/` URL routing + Celery dispatch | Replaced | Persist-first idempotent, multi-provider safe |

## Integrations

| Legacy | New | Disposition | Rationale |
|---|---|---|---|
| `ZohoId` columns on every table | `integrations.SyncRecord` (generic FK) | Moved | Single observability point |
| `SyncId`, `IsSync`, `IsSynced` booleans | `integrations.SyncRecord.status` + fingerprints | Moved | Drift detection, retry tracking |
| `OldVillaId`, `OldId` | `legacy_id` (CharField, nullable, indexed) on each domain model | Renamed | One slot per model |
| `VillaCodeSentHistory`, `VillaEmailLinkLog` | — | Dropped (future `comms` app) | Out of scope for this redesign |
| `VcemailTemplate` | — | Dropped (future `comms` app) | Out of scope |

## Accounts

| Legacy | New | Disposition | Rationale |
|---|---|---|---|
| `UserMaster` | `accounts.User(AbstractUser)` | Replaced | Standard Django auth, email login |
| `UserMaster.SmtpAddress/User/Password/Port` | — | Dropped | Per-user SMTP was unused & a security liability |
| `UserMaster.IsLock` | `User.is_active=False` | Replaced | Standard Django |
| `UserMaster.IsSystemAdmin` | `User.is_superuser` | Replaced | Standard Django |

## Cross-cutting

| Legacy pattern | New pattern |
|---|---|
| Mixed `CreateAt`/`CreatedAt`/`UpdateAt`/`UpdatedAt`/`UpdtedAt` (typos) | `TimestampedModel.created_at` / `updated_at` |
| Mixed `CreatedBy`/`UpdatedBy` (int or string) | `AuditedModel.created_by` / `updated_by` FK to User |
| Mixed `DeletedAt`/`DeletedBy` | `SoftDeleteModel.deleted_at` / `deleted_by` |
| CSV string foreign keys (`FeatureIds`, `RegionIds`, `CountryId`) | Proper M2M and FK |
| Booleans for inheritance (`IsDefaultSetting*`) | Nullable fields + `effective()` resolver |
| Bit flags for image kinds | Single `kind` TextChoices + UniqueConstraint |
| 500+ LOC stored procedures | `services.py` Python services |
| App-layer FK only | Real DB FKs with chosen `on_delete` |
| Daily-row availability grid | Range queries + Postgres `EXCLUDE` constraints |
| Three payment status enums | One model with `purpose` + `status` |
| Hardcoded webhook prefix parsing | Provider-slug URL routing |
| Per-row ZohoId / SyncId | `integrations.SyncRecord` |

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
