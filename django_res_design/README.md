# Villa Collective — Django Data Model Redesign

A specification for re-implementing the Villa Collective reservation platform as a pure-Django + Postgres application. The current system (`../ResSystem/`) is a .NET 6 / EF Core / SQL Server stack carrying substantial structural debt. This redesign aims for **moderate departures**: fix the structural issues, preserve the product shape and workflows.

This is a **fresh design** — legacy data migration is out of scope. Documents are detailed enough to implement directly but contain no executable code.

## Product

A management platform for **luxury whole-property villa rentals**. Core capabilities:

- Curated portfolio of villas across countries/regions, with rich descriptive content, image galleries, features, owner contacts
- **Enquiry → Quotation → Booking → Check-in → Check-out** lifecycle, sourced via website forms and direct agent input
- Sophisticated pricing: per-villa seasons, occupancy bands, taxes, agent commissions, discounts, POA, multi-currency
- Owner-confirmed bookings (manual approval workflow)
- 3-tier payment schedule: Initial Deposit, Rental Balance, Security Deposit (processed via Flywire)
- Concierge add-ons per booking
- Integration with Zoho CRM

## Design Philosophy

- **Pure Django** — stdlib + Django + Postgres. No `django-fsm`, `django-money`, or third-party state-machine libraries.
- **Database-enforced integrity** — real FKs (`PROTECT`/`CASCADE` chosen deliberately), `EXCLUDE` constraints for non-overlap, `UniqueConstraint`/`CheckConstraint` everywhere they apply.
- **Decompose god objects** — `VillaMaster` and `VillaFinance` split into focused models with OneToOne relationships per concern.
- **Single source of truth** — drop drifting denormalized archive tables in favour of state + audit event rows. Where caches are required for performance, name them explicitly and own them via signals.
- **Null-means-inherit** — replace `IsDefaultSetting*` boolean flags with nullable fields and an `effective_*()` resolver merging from a group default.
- **Explicit state machines** — `TextChoices` + per-transition methods + atomic blocks + audit events + signals. No magic.
- **Service boundaries** — pricing and availability live in `services.py`, not on model methods. Stateless, testable.

## App Map

```
accounts/       Users, Contacts (owners/managers), Roles
properties/     Property, Location, Capacity, Settings, Rooms, Images, Features, Collections, Groups, Geography
                + Finance config (Commission, Tax, BankAccount, PaymentSchedule, SecurityDepositPolicy)
pricing/        RatePlan, RateRule, Surcharge, Discount, ChangeOverRule, Currency, FxRate, PricingEngine service
reservations/   Guest, Enquiry, Quotation, QuotationLine, Booking, BookingHold, BookingEvent, TermsVersion, Concierge
payments/       Payment, PaymentEvent, WebhookDelivery, Flywire webhook flow
integrations/   SyncRecord (generic FK to external systems — Zoho, etc.)
```

`reservations` depends on `pricing` (and uses its `AvailabilityService`). `payments` depends on `reservations` (signals only — reservations doesn't import payments). `integrations` is referenced via generic FK from any model that syncs. `properties` and `accounts` are foundational.

## Documents

| File | Topic |
|---|---|
| [00-conventions.md](./00-conventions.md) | Abstract bases, soft-delete, audit middleware, naming, currency, enums |
| [01-accounts.md](./01-accounts.md) | User, Contact, ContactEmail, ContactPhone, Role |
| [02-properties.md](./02-properties.md) | Property decomposition, Location, Capacity, Settings, Rooms, Images, Features, Collections, Geography |
| [03-finance-config.md](./03-finance-config.md) | PropertyFinance and its 5 child models; group-level defaults |
| [04-pricing.md](./04-pricing.md) | Rate model, surcharges, discounts, change-over rules, PricingEngine |
| [05-reservations.md](./05-reservations.md) | Guest, Enquiry, Quotation, Booking, lifecycle |
| [06-availability.md](./06-availability.md) | BookingHold, range-overlap availability, state machine, change-over enforcement |
| [07-payments.md](./07-payments.md) | Payment, PaymentEvent, WebhookDelivery, Flywire flow |
| [08-integrations.md](./08-integrations.md) | SyncRecord, Zoho reconciliation |
| [09-departures.md](./09-departures.md) | Table-by-table mapping of original → new (kept/merged/renamed/dropped) |

## Reading Order

For first-time readers: README → 00 → 09 (departures table gives the at-a-glance shape) → 02 → 05 → 06 → 04 → 07 → others.

For someone about to implement an app: start at the per-app doc; cross-reference 00 for shared bases and 09 for context on what was changed and why.
