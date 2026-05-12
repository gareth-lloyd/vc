# 07 — API ↔ Schema Reconciliation Issues

Tracks issues raised by reconciling `04-rest-api-surface.md` (product-design) against the backend design in `django_res_design/00`–`09`. Each issue has a status, a current decision (if any), and links to evidence.

Status legend:
- **Open** — needs a decision.
- **In progress** — decision in flight; notes captured below.
- **Resolved** — decision recorded; design docs updated (or queued to update).
- **Deferred** — out of MVP scope; revisit later.

---

## A. Hard contradictions

### #1 — Multi-tenant `Site` model: API treats sites as tenants; backend has only an enum. — **Resolved**

- **API surface:** `/sites` CRUD, `/sites/{slug}/settings`, `?site=` filter on most lists, `X-Site` impersonation, token site claim, `/public/` per-site mirror.
- **Backend:** `VillaSite` was dropped; replaced by `Enquiry.site_source` / `Booking.site_source` TextChoices. No `Site` model, no `site` FK on `Property` / `Contact` / `Guest` / `User` / `RatePlan`.
- **Investigation:** Production data dump `live-db-24-apr.sql` contains **zero references** to `VillaSites`, `SiteId`, `VillaSyncDetails`. `VillaEnquire` schema in production has no `SiteId` column. The 16-Apr-25 migration that introduced `VillaSites` was never deployed (or was rolled back). The .NET app code in `ResApiService.cs` and `CommonService.cs` uses `vw_villa_sites` as an **outbound publishing target registry** — one back-office fans out to multiple WordPress storefronts via REST API. There is no domain-level `SiteId` FK anywhere; the same `Property` / `Booking` is published to all WP sites.
- **Decision:**
  1. The legacy system was never multi-tenant. Drop `/sites` CRUD, `/sites/{slug}/settings`, `?site=` filter, `X-Site` header, token site claim, and per-site `/public/` variants from the API spec.
  2. Keep `Enquiry.site_source` and `Booking.site_source` TextChoices — that's the real concept (inbound channel).
  3. If publishing to multiple WordPress sites is in scope for v1, model it through `integrations.SyncRecord` with provider `WORDPRESS_SITE` (already enumerated in `08-integrations.md`); configure via `system/integrations`.
  4. Owner-portal scoping is not tenancy — it's per-`Contact` permissioning via `PropertyContactAssignment` (already covered).
- **Follow-up:** update `04-rest-api-surface.md` to remove site endpoints/filters; note WP fan-out lives under integrations.

---

### #2 — Pricing namespace: API exposes `/seasons` → `/rate-cards` → `/occupancy-bands`; backend has only `RatePlan` → `RateRule`. — **Open**

- **API surface (§2.4):** `/properties/{id}/seasons` → `/seasons/{id}/date-ranges` → `/seasons/{id}/rate-cards` → `/rate-cards/{id}/occupancy-bands`. Four nested resources.
- **Backend (`04-pricing.md`):** `RatePlan` → `RateRule` only. Date ranges and party (occupancy) ranges are inline columns on `RateRule`. `VillaSeasonDate` and `VillaOccupencyPrice` were explicitly merged into `RateRule` per `09-departures.md`.
- **Decision needed:** rename API to `/rate-plans` / `/rate-rules` and drop the date-range and occupancy-band sub-paths, OR re-introduce separate `RateCard` / `OccupancyBand` / `SeasonDateRange` models.

### #3 — "Extras" (cleaning/pet fee): API resource has no backing model. — **Open**

- **API:** `/properties/{id}/extras`, `/extras/{id}` CRUD.
- **Backend:** No `Extra` model. Closest is `pricing.Surcharge` (`kind=CLEANING|SERVICE_FEE|RESORT_FEE`) scoped to a `RatePlan`, not a `Property`. Not exposed via API.
- **Decision needed:** treat extras as a flat alias for property-scoped surcharges (then `Surcharge` needs to be FK-able to `Property`) or introduce a new model.

### #4 — Notes: API is a collection; backend is single TextFields. — **Open**

- **API:** `GET/POST /bookings/{id}/notes`, `PATCH/DELETE /bookings/{id}/notes/{note_id}`. Same for enquiries.
- **Backend:** `Booking.notes`, `Booking.internal_notes`, `Booking.concierge_notes`, `Enquiry.notes`, `Enquiry.internal_notes` — all single `TextField` columns.
- **Decision needed:** add a `Note` model (or per-domain `BookingNote` / `EnquiryNote`) with author, kind, timestamps.

### #5 — Refunds: API has approval workflow; backend has none. — **Open**

- **API (§2.13):** `/refunds` first-class resource with `:approve`, `:reject`, `:execute`, `:cancel` (four-state workflow).
- **Backend:** Refund is `Payment.purpose=REFUND` with `Payment.status` (PENDING/PROCESSING/SUCCEEDED/FAILED/...). No APPROVED, REJECTED, no separation of approval from execution.
- **Decision needed:** add `Refund` table with own state machine, or extend `Payment.status` with approval intermediate states.

### #6 — Settlement records ("checkouts"): API endpoint maps to nothing. — **Open**

- **API:** `/checkouts/{id}`, `/checkouts` — described as "Settlement record detail".
- **Backend:** `VillaCheckoutDetail` was dropped/split per `09-departures.md`; fields distributed across Booking/Guest/Payment. No new "settlement" model.
- **Decision needed:** clarify intent (gateway-side payout reconciliation? Guest check-in records?) and either add a model or remove the endpoint.

### #7 — Booking state machine missing transitions. — **Open**

- **Missing transitions for API actions:** `:modify-dates`, `:modify-guests`, `:check-out` (backend uses automatic `complete()` on `date_to`), `:archive` / `:restore` (overlaps with `SoftDeleteModel.delete()` — what's the difference?), `:resend-confirmation`.
- **Decision needed:** add transitions to `BookingStatus` / `Booking` methods, or remove the actions from the API. Date-change is non-trivial — needs hold acquisition, availability re-check, pricing-snapshot regeneration.

### #8 — `Tag` top-level resource doesn't exist. — **Open**

- **API:** `/tags` CRUD, `/properties/{id}/tags`, distinct from features.
- **Backend:** No `Tag` model. `Feature.service_type` is a TextChoices on `Feature` (AMENITY / INCLUDED_SERVICE / PAID_ADDON).
- **Decision needed:** add a `Tag` model + M2M, or repurpose `Feature.service_type` and document the rename.

### #9 — Roles table doesn't exist. — **Open**

- **API:** `/roles` full CRUD with permission sets, plus `/permissions` catalogue.
- **Backend:** Plain Django permissions; legacy `VillaRole` replaced by `accounts.ContactRole` TextChoices. No editable `Role` table.
- **Decision needed:** if admin UI needs editable roles, add `Role` model and groups; otherwise expose Django's `auth.Group` and trim API.

---

## B. Out-of-scope creep (API includes deferred features)

| # | API surface | Backend status | Status |
|---|---|---|---|
| 10 | `/email-templates`, `/email-logs`, `:preview`, `:test-send`, `:resend`, `/code-auth-logs` (§2.19) | `VcemailTemplate`, `VillaCodeSentHistory`, `VillaEmailLinkLog` — Dropped (future comms app) | **Open** |
| 11 | `/channel-mappings`, `/webhooks/airbnb`, `/webhooks/booking`, `/webhooks/vrbo`, `:sync`, `/channel-sync/*` (§2.25) | Channel manager integrations — future scope | **Open** |
| 12 | `/feeds/properties/{id}/ical`, rotate-token (§2.24) | Not modelled | **Open** |
| 13 | `/payment-methods`, `/guests/{id}/payment-methods` (§2.14) | "BookingPaymentMethod if multi-method ever lands" — explicitly deferred | **Open** |
| 14 | `/notifications`, `/notification-preferences` (§4) | Not modelled | **Open** |
| 15 | `/feature-flags` (§4) | Not modelled | **Open** |
| 16 | `/exports`, `/jobs/{id}` (§2.21) | Not modelled | **Open** |
| 17 | `/webhook-subscriptions` (outbound) (§1) | Not modelled | **Open** |
| 18 | `/bookings/{id}/documents:generate` (contract/voucher PDF) (§2.8) | Not modelled | **Open** |
| 19 | `/quotations/{id}/pdf` (§2.7) | Not modelled | **Open** |
| 20 | `/audit-log` global + `/{resource}/{id}/audit-log` alias (§4) | Only domain-specific `BookingEvent`, `PaymentEvent`; no generic audit log | **Open** |
| 21 | `/system/integrations`, `:test` (§2.28) | Not modelled | **Open** |
| 22 | `GuestPreference` (implied) | Dropped — can re-add later | **Open** |

**Group decision needed:** trim API spec to what the data model supports for MVP, or commit to scope-expanding the backend.

---

## C. Workflow & semantic mismatches

### #23 — Property status values disagree. — **Open**
- API: `:publish` = "draft → live", `:unpublish` = "live → draft". Backend: `DRAFT | ACTIVE | OFFLINE | ARCHIVED`. No `LIVE`. Pick one name.

### #24 — Payment "tracks" terminology: `:waive` and `:mark-paid` have no backend transitions. — **Open**
- API: `/bookings/{id}/deposit`, `/balance`, `/security` parallel resources, with `:waive` and `:mark-paid` actions. Backend: `Payment.purpose = DEPOSIT | BALANCE | SECURITY_DEPOSIT | REFUND | ADJUSTMENT`. No `WAIVED` status; `:mark-paid` implies a manual provider path not fleshed out beyond `provider=MANUAL_BANK_TRANSFER`.

### #25 — Security deposit pre-auth hold lifecycle. — **Open**
- API: `:hold`, `:release`, `:claim` on a security-deposit payment. Backend: `Payment.status` doesn't distinguish AUTHORIZED / HELD / CAPTURED — only PENDING / PROCESSING / SUCCEEDED. Pre-auth flow needs explicit states.

### #26 — `assigned_to` filter has no backing field. — **Open**
- API: `?assigned_to=` filter on `/bookings`, `/enquiries`, plus `:assign` action. Backend: `Booking.agent` and `Enquiry.agent` exist (FK to `Contact`), but no `assigned_to` FK to `User`. Rename the filter or add an internal assignee FK.

### #27 — Enquiry has no activity timeline. — **Open**
- API: `GET /enquiries/{id}/activity`. Backend: `BookingEvent` exists; no `EnquiryEvent`. Status changes on Enquiry aren't audited.

### #28 — Property descriptions: API sub-resource vs backend flat columns. — **Open**
- API: `/properties/{id}/descriptions/{section}` where `section ∈ {overview, house-rules, villa-info, further-info}`. Backend: `Property.overview`, `Property.house_rules`, `Property.feature_description`, `Property.room_description`, `Property.notes` — flat columns, section names don't 1:1 match. Decide: serializer mapping or normalise to `PropertyDescription(section, body)` child table.

### #29 — Collections membership PUT replace loses through-fields. — **Open**
- API: `PUT /properties/{id}/collections` replaces the set. Backend: `CollectionMembership` is an explicit through model with `sort_order`, `featured_until`, `description`. Naive PUT will lose those fields; need a body shape that preserves them or a partial-update verb.

---

## D. Missing admin surfaces (entity exists; API doesn't expose it)

| # | Backend entity | API gap | Status |
|---|---|---|---|
| 30 | `ChangeOverRule` (per-property check-in weekdays) | No CRUD | **Open** |
| 31 | `Surcharge` per `RatePlan` | No CRUD | **Open** |
| 32 | `Discount` | No CRUD or code-lookup | **Open** |
| 33 | `TermsVersion` | No CRUD | **Open** |
| 34 | `ConciergeService` catalogue | Only booking-nested items exposed | **Open** |
| 35 | `NearbyPlaceType` | Curated table, no endpoint | **Open** |
| 36 | `PropertyFinance` children (`Commission`, `TaxPolicy`, `BankAccount`, `PaymentSchedule`, `SecurityDepositPolicy`) and `Group*` mirrors | API has flat `/properties/{id}/finance`; backend is 5+5 OneToOne children with separate permissions | **Open** |
| 37 | `PropertySettings` vs `GroupSettings` | Same pattern; API only has `/properties/{id}/settings` | **Open** |
| 38 | `PropertyGroup.GroupSettings`, `GroupCommission`, etc. | `/property-groups` exposed but group-level config children not | **Open** |

---

## E. Smaller items

| # | Issue | Status |
|---|---|---|
| 39 | API mandates `Idempotency-Key` on all POST actions; backend only has it on `Payment.idempotency_key`. Need generic `IdempotencyRecord` table or middleware. | **Open** |
| 40 | API specifies two-step S3 signed-URL uploads; backend uses Django's default `ImageField(upload_to=...)`. Pick S3 (django-storages) or local. | **Open** |
| 41 | `/auth/sessions` list & revoke implies queryable session model; Django default sessions are usable but need service layer. | **Open** |
| 42 | `/zoho:connect` / `:disconnect` OAuth flow; backend has `ZohoSyncClient` but no OAuth token storage model. | **Open** |
| 43 | API has `:challenge` / `:verify` / `:enroll`; backend has `User.tfa_method` / `tfa_secret`. SMS path needs provider; TOTP needs library choice. | **Open** |
| 44 | `POST /availability:search`, `POST /quotations:search-villas`, `POST /pricing:quote-bulk` overlap. Consolidate. | **Open** |
| 45 | `Booking.deposit_amount` / `deposit_percentage` columns plus `Payment(purpose=DEPOSIT)` row — two sources of truth. Decide which the API reads from. | **Open** |

---

## Decision log

| Date | Issue | Decision | Notes |
|---|---|---|---|
| 2026-05-12 | #1 | Drop `/sites` from API. Keep `site_source` enum. WP fan-out via integrations. | Confirmed against `live-db-24-apr.sql` — multi-tenancy never deployed; `VillaSite` was WP publishing-target registry. |
