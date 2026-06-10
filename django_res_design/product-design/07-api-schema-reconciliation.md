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

### #2 — Pricing namespace: API exposed 4-level `/seasons` → `/date-ranges` → `/rate-cards` → `/occupancy-bands`; backend had only 2-level `RatePlan` → `RateRule`. — **Resolved**

- **API surface (§2.4 original):** `/properties/{id}/seasons` → `/seasons/{id}/date-ranges` → `/seasons/{id}/rate-cards` → `/rate-cards/{id}/occupancy-bands`. Four nested resources.
- **Backend original (`04-pricing.md`):** `RatePlan` → `RateRule`. Date ranges and party (occupancy) ranges were inline columns on `RateRule`.
- **Investigation (live DB `live-db-24-apr.sql`):**
  - `VillaSeason`: 710 rows
  - `VillaSeasonDates`: 736 rows → **1.04 ranges per season** (96% of seasons have exactly one date range)
  - `VillaSeasonRate`: 8,665 rows (the workhorse — carries date range, party size, price)
  - `VillaOccupencyPrice`: 263 rows → **only 3% of rate rows use occupancy banding**

  Product UX (`03-workflows.md` flow 13) confirms operator mental model is "Season form with N rate-card rows; occupancy bands are a table inside the card".

- **Decision (Option C — middle ground):**
  1. Adopt a **three-level** model: **`RatePlan` (= Season) → `RateCard` → `RateRule`**.
  2. `RateCard` is added as the operator-mental unit (name, min/max nights, changeover, sort order). It has no prices of its own.
  3. `RateRule` is the price row (date range, party range, nightly/weekly). One per (date sub-range × party-size band) inside a card. Sibling rules sharing a date range with disjoint `(min_party, max_party)` express occupancy bands; sibling rules sharing party range with disjoint dates express multi-range cards.
  4. `SeasonDateRange` is **not** a separate table/resource — vestigial in production.
  5. `OccupancyBand` is **not** a separate table/resource — vestigial in production.
  6. The `EXCLUDE` GIST constraint on `RateRule` is scoped to `card_id` instead of `plan_id`. Cross-card overlap is allowed and resolved by card order (`RateCard.sort_order`) in `PricingEngine.quote()` — the per-rule `priority` field was deleted (2026-06-10, `10-decisions.md`).
  7. `Discount` FK moves from `RatePlan` to `RateCard` (with property-level fallback when `card` is null for property-wide promo codes). Adds `rule_kind` TextChoices (`LENGTH_OF_STAY`, `EARLY_BIRD`, `LAST_MINUTE`, `REPEAT_GUEST`, `PROMO_CODE`) and `threshold_days`.
  8. **API renames:**
     - Keep `/properties/{id}/seasons`, `/seasons/{id}` — operator-facing term.
     - Keep `/seasons/{id}/rate-cards`, `/rate-cards/{id}` — backed by new `RateCard` model.
     - **Delete** `/seasons/{id}/date-ranges/*` and `/rate-cards/{id}/occupancy-bands/*`.
     - **Add** `/rate-cards/{id}/rules` and `/rules/{id}` for granular price-row CRUD; default detail responses inline rules.
- **Follow-ups:**
  - `04-pricing.md` updated: added `RateCard`, repointed `RateRule.card` FK, repointed `Discount.card` FK, updated PricingEngine steps. ✓
  - `09-departures.md` updated: legacy mapping table reflects new shape. ✓
  - `product-design/01-domain-model.md` updated: dropped `SeasonDateRange` and `OccupancyBand` entities; reshaped relationship diagram. ✓
  - `product-design/04-rest-api-surface.md` §2.4 updated. ✓
  - Surcharge scoping (RatePlan vs RateCard) deferred to issue #31.

### #3 — "Extras" (cleaning/pet/heating fees): API resource had no backing model. — **Resolved**

- **API original:** `/properties/{id}/extras`, `/extras/{id}` CRUD (kinds implied: cleaning, pet, heating, linen, extra-bed).
- **Backend original:** No `Extra` model. The closest was `pricing.Surcharge` (kinds `TAX`, `COMMISSION`, `CLEANING`, `SERVICE_FEE`, `RESORT_FEE`), scoped to `RatePlan`. Not exposed via API.
- **Investigation (live DB `live-db-24-apr.sql`):**
  - 122 `VillaSeasonRate` rows with `IsExTra=1`. Inspecting names: "+2 pax", "+4 pax", "+with Main House", "Guest house extra", "Chef included", "Cook" — these are **optional rate-card uplifts** (extra capacity, guest-house add-ons, service tiers), not cleaning/pet fees.
  - `VillaConciergeServices`: only 2 rows ("Quintessential", "Signature") — service-tier labels, not a catalogue.
  - `VillaBookingConcierge`: per-booking line items with `Price` + free-text `Notes`. The only place cleaning fees etc. could live, and they did so unstructured.
  - **No structured cleaning/pet/heating fee model exists in legacy.** The product spec's "extras" is therefore a new requirement.
  - Identified a separate defect: tax & commission are modelled in two places — `PropertyFinance.TaxPolicy` / `PropertyFinance.Commission` (per `03-finance-config.md`) AND `Surcharge(kind=TAX|COMMISSION)` (per `04-pricing.md` original). PricingEngine docstring used Surcharge; PropertyFinance was unused at quote time.
- **Decision:**
  1. **Add `pricing.Extra`** — property-scoped catalogue of named charges. Fields: name, description, kind (`CLEANING`/`PET_FEE`/`HEATING`/`LINEN`/`EXTRA_BED`/`SERVICE_FEE`/`RESORT_FEE`/`OTHER`), calc (`FIXED_PER_STAY`/`FIXED_PER_NIGHT`/`FIXED_PER_PERSON`/`FIXED_PER_PERSON_PER_NIGHT`/`PERCENT_OF_SUBTOTAL`), amount, currency, `is_mandatory`, `applies_from`/`applies_to` for seasonality, `min_party`/`max_party` for party-size gating, sort_order, is_active.
  2. **Retire `pricing.Surcharge`** entirely. Tax/commission read via `PropertyFinance.effective_tax_policy()` / `effective_commission()` (already in `03-finance-config.md`); cleaning/service/resort fold into `Extra`.
  3. **No per-card scoping on `Extra`** — product UX renders extras inside the rate-card form, but that's an editing affordance, not the storage shape. Seasonality is expressed via the date window; party-size variation via the party window. Defer per-card overrides until a real requirement appears.
  4. **PricingEngine flow** updated: rate subtotal → mandatory extras → opt-in extras → discounts → commission → tax. Tax base is rate subtotal + extras − discounts.
  5. **API:** keep `/properties/{id}/extras` and `/extras/{id}` plus `/extras/{id}:duplicate`. `/pricing:quote` body accepts `opt_in_extras: [<extra_id>, ...]`; mandatory extras apply automatically.
- **Follow-ups:**
  - `04-pricing.md` updated: removed `Surcharge` section; added `Extra` model; updated PricingEngine `Quote` dataclass and steps. ✓
  - `09-departures.md` updated: removed Surcharge from mapping; split `IsExTra=1` legacy rows into "capacity uplifts → extra RateRule rows" and "named charges → Extra rows"; reconciled `VillaConciergeService` duplicate listing. ✓
  - `product-design/01-domain-model.md` updated: `Extra` section reflects the resolved design. ✓
  - `product-design/04-rest-api-surface.md` §2.4 updated. ✓
  - Closes the "Surcharge scoping" follow-up that was queued from issue #2.

### #4 — Notes: API is a collection; backend is single TextFields. — **Resolved**

- **API:** `GET/POST /bookings/{id}/notes`, `PATCH/DELETE /bookings/{id}/notes/{note_id}`. Same for enquiries.
- **Backend (original):** `Booking.notes`, `Booking.internal_notes`, `Booking.concierge_notes`, `Booking.villa_notes`; `Enquiry.notes`, `Enquiry.internal_notes`, `Enquiry.preferences_note` — all single `TextField` columns. Inconsistently, `product-design/01-domain-model.md` §4 already declared a `BookingNote(booking, author, body, is_internal)` entity, in tension with the flat columns above.
- **Investigation:**
  - **Legacy schema** (`ResSystem/Database/DbScript.sql` and live dump `live-db-24-apr.sql`): `VillaBooking` carries exactly two note columns (`Notes`, `ConciergeNotes`); `VillaEnquire` carries one (`Notes`) plus the unrelated guest-form `PreferencesNote`. No legacy `*Note` child table; no append-only structure; no per-edit authorship.
  - **Legacy UI** (`NewResSystem/Pages/Bookings/Booking.razor`): three side-by-side rich-text editors — "Customer Notes (Internal)", "Booking summary information", "Internal booking information" — each bound to a single column on the model with overwrite semantics. There is no add-note workflow, no list, no timeline. Concurrent edits clobber.
  - **Live data:** 5 booking rows (test data) with short single-paragraph notes; 453 enquiry rows where `Notes` is the guest's original web-form message, not an operator stream.
  - **API direction of travel:** the spec already commits to a collection (`POST /notes`, `note_id` path segment, `PATCH/DELETE`). The activity timeline (`/bookings/{id}/activity`) expects authored, timestamped entries.
  - **Improvements over original** (`product-design/05-improvements-over-original.md`): the rebuild explicitly upgrades audit coverage; per-note authorship and timestamps are the minimum hygiene the legacy lacked.
- **Decision:**
  1. Adopt per-domain note collections — `reservations.BookingNote` and `reservations.EnquiryNote` — as the canonical store. **Drop all flat note `TextField` columns** from `Booking`, `Enquiry`, and `Quotation`.
  2. `BookingNote` carries: `booking` FK, `author` FK User SET_NULL, `kind` TextChoices (`GENERAL` / `INTERNAL` / `CONCIERGE` / `VILLA`), `body` TextField, `is_pinned`, `visibility` TextChoices (`STAFF_ONLY` / `OWNER` / `GUEST`), `created_at`, `updated_at`. Hard-delete on remove; mutation audit lives in `AuditLog`.
  3. `EnquiryNote` carries: `enquiry` FK, `author` FK User SET_NULL, `kind` TextChoices (`GENERAL` / `INTERNAL` / `PREFERENCES`), `body`, `is_pinned`, `created_at`, `updated_at`. Same audit treatment.
  4. **`Enquiry.inbound_message`** (new, immutable single `TextField`) preserves the guest's original web-form message as provenance — it is *not* a note. The 453 legacy `VillaEnquire.Notes` rows migrate here, not into `EnquiryNote`.
  5. `Quotation` loses its flat note columns entirely; quotation-level commentary lives on the source `Enquiry` (via `EnquiryNote`) and the destination `Booking` (via `BookingNote`). `QuotationLine.notes` (per-villa option) survives — it is intrinsically per-line, not a stream.
  6. **API:** keep `/bookings/{id}/notes`, `/bookings/{id}/notes/{note_id}`, `/enquiries/{id}/notes`, `/enquiries/{id}/notes/{note_id}` exactly as already specified. `?kind=` filter on GET supports the legacy three-textarea UI as three pre-filtered tabs over one collection.
  7. **Migration:** each non-empty legacy text column becomes one seed `BookingNote` / `EnquiryNote` row, `kind` derived from the source column, `author` set to a system user, `created_at` = `VillaBooking.UpdatedAt` (or `CreatedAt` fallback). `VillaEnquire.Notes` migrates to `Enquiry.inbound_message` (one column move, no fan-out).
  8. **Reconciliation:** the pre-existing partial `BookingNote` entity in `product-design/01-domain-model.md` §4 is the right idea but was under-specified — extend it with `kind`, `visibility`, `is_pinned`, drop `is_internal` (subsumed by `kind` + `visibility`), and remove the conflicting flat columns from the `Booking` field list.
- **Follow-ups:**
  - `05-reservations.md` updated: dropped flat note columns from `Enquiry`, `Quotation`, `Booking`; added `BookingNote` and `EnquiryNote` model sections; added `Enquiry.inbound_message`. ✓
  - `product-design/01-domain-model.md` updated: reshaped `BookingNote`, added `EnquiryNote`, removed flat columns from `Booking` and `Enquiry`, added `Enquiry`↔`EnquiryNote` to relationship summary. ✓
  - `09-departures.md` updated: legacy mapping rows for `VillaBooking.Notes`/`ConciergeNotes` and `VillaEnquire.Notes`/`PreferencesNote` now point to the new entities with migration instructions. ✓
  - `product-design/04-rest-api-surface.md` §2.6 and §2.8 already correct — no edit needed.

### #5 — Refunds: API has approval workflow; backend has none. — **Resolved**

- **API (§2.13):** `/refunds` first-class resource with `:approve`, `:reject`, `:execute`, `:cancel`.
- **Backend original:** Refund was `Payment.purpose=REFUND` with `Payment.status` (PENDING/PROCESSING/SUCCEEDED/FAILED/...). No APPROVED, REJECTED, no separation of approval from execution.
- **Investigation:**
  - **Legacy DB** (`live-db-24-apr.sql`, UTF-16 LE): zero refund tables. No `VillaRefund`, no `RefundStatus`, no `RefundedBy`, no `RefundApproved`, no `RefundAmount`. The only "refund" tokens in the schema are config knobs (`SecurityDepositDaysRefundedAfterDeparture`) and cancellation-policy refund-percent tiers — none of which represent an actual refund record.
  - **Legacy UI** (`ResSystem/*.razor`): no Blazor page references a refund concept. There is no in-app refund workflow, no approval step, no refund list, no refund audit.
  - **Conclusion**: refunds in the legacy system were issued manually through the gateway dashboard, with no in-app trail. There is no legacy constraint on the new design.
  - **Product-side domain model** (`product-design/01-domain-model.md` §7): already declares a `Refund` entity with `requested_by`, `approved_by`, `executed_at`, and a status enum including `pending`, `approved`, `executing`, `succeeded`, `failed`, `cancelled`. The backend doc was lagging.
- **Decision:**
  1. Adopt a **dedicated `payments.Refund` model** as the workflow object — separate from `Payment`. Approving a refund and executing it are distinct authority gates; collapsing them into `Payment.status` would conflate workflow state (`APPROVED`, `REJECTED`) with money-movement state (`PROCESSING`, `SUCCEEDED`) on a single row and lose the ability to enforce requester ≠ approver.
  2. **State machine**: `PENDING → APPROVED → EXECUTING → SUCCEEDED`, with terminal branches `REJECTED` (from `PENDING`), `CANCELLED` (from `PENDING` or `APPROVED`), and `FAILED` (from `EXECUTING`). Seven states total. `EXECUTING` is the outbox state — the Celery task is in flight.
  3. **Workflow object vs gateway transaction split**: `Refund` is the workflow object. On `:execute`, the service creates one `Payment(purpose=REFUND, status=PROCESSING)` row linked via `meta['refund_id']` to record the actual gateway call. Webhook callbacks land on the Payment row; the `payment_refunded` signal advances the linked Refund.
  4. **Separation of duties** enforced in the service layer: `approved_by != requested_by` (override permission `payments.refund.self_approve` for low-value refunds). `executed_by` may equal `approved_by` by default; orgs that want a third actor enforce that in policy.
  5. **Partial refunds** are expressed as multiple `Refund` rows against the same booking/payment — not as a status. The service layer asserts that the cumulative non-failed refund total against an inbound `Payment` does not exceed its amount.
  6. **`PaymentEvent` audit** is extended to be polymorphic over `Payment` / `Refund` with a check constraint that exactly one FK is set. Refund transitions write `PaymentEvent` rows alongside Payment transitions.
  7. **Unique constraint relaxation**: the `unique_active_payment_per_purpose` constraint on `Payment` now excludes `purpose IN (REFUND, ADJUSTMENT)`, because one Refund workflow may legitimately produce more than one `Payment(purpose=REFUND)` row over retries.
  8. **API**: existing §2.13 endpoints (`/refunds`, `POST /bookings/{id}/refunds`, `:approve`, `:reject`, `:execute`, `:cancel`) are kept verbatim — they already match the chosen state machine.
- **Follow-ups:**
  - `07-payments.md` updated: added `Refund` model section with state machine table; extended `PaymentEvent` to polymorphic Payment/Refund FK; relaxed the active-payment unique constraint; rewrote `RefundService` API; added a "New vs legacy" note. ✓
  - `09-departures.md` updated: Payments mapping table records that `Refund` is wholly new (no legacy mapping). ✓
  - `product-design/01-domain-model.md` updated: `Refund` entity field list and status enum aligned to backend model; added explicit state-machine summary and separation-of-duties note; dropped `partially_refunded` status (modelled as multiple `Refund` rows instead). ✓
  - `product-design/04-rest-api-surface.md` §2.13 already correct — no edit needed.

### #6 — Settlement records ("checkouts"): API endpoint maps to nothing. — **Resolved**

- **API original:** `GET /checkouts/{id}`, `GET /checkouts` listed inside §2.14 Payments (flat, cross-booking) with the gloss "Settlement record detail".
- **Backend:** No "settlement" model. `09-departures.md` previously said `VillaCheckoutDetail` was "split across Booking/Guest/Payment" — that was imprecise.
- **Investigation:**
  - **Legacy schema** (`ResSystem/Database/Data/VillaCheckoutDetail.cs`): the columns are `Id`, `BookingRefNo`, `BookingId`, `Amount`, `CheckoutDate`, `Description`, `IsDeposit`, `PaymentStatus`, `PaymentId`, `PayerAmt`, `PayerCurrency`, `IsOfflinePayment`, `PaymentMethod`, `IsActive`, plus timestamps. Despite the name, **none of these fields relate to guest check-in/out** (no key-handover time, no arrival/departure event) and **none relate to gateway payout reconciliation** (no payout id, no reconciliation date, no net-of-fees ledger). They are scheduled-payment ledger fields.
  - **Legacy domain code** (`NewResSystem.Core/Services/Bookings/BookingInfoModels.cs`): a sibling `EmailCheckoutDetailsArgs` DTO carries the exact same shape plus `DueDate` and `ArrivalDate`, and the adjacent `CheckoutPaymentType` enum has only three values — `INITIAL_PAYMENT_DUE`, `RENTAL_BALANCE_PAYMENT`, `SECURITY_DEPOSIT`. The legacy SP `sp_getCheckoutDetailsById` (in `live-db-24-apr.sql`) computes IPD/RB/SD amounts and due-dates by joining `VillaBooking` ⋈ `VillaFinance` — i.e. it derives the payment schedule from finance config, not from any settlement concept.
  - **Conclusion:** `VillaCheckoutDetail` was the legacy **3-tier payment-schedule ledger** — one row per (booking × payment-due track) for the three tracks `DEPOSIT` / `BALANCE` / `SECURITY_DEPOSIT`. It is a 1:1 mirror of the new `payments.Payment(purpose=…)` model. The Django port's `Payment.purpose` enum (`DEPOSIT` / `BALANCE` / `SECURITY_DEPOSIT` / `REFUND` / `ADJUSTMENT`) is a strict superset; the `UniqueConstraint` "one active Payment per (booking, purpose)" exactly preserves the legacy one-row-per-track invariant. Nothing further to model.
  - **Live data:** the live dump (`live-db-24-apr.sql`) actually contains **no `VillaCheckoutDetail` table at all** — only the stored procedure `sp_getCheckoutDetailsById` survives, and that proc reads from `VillaBooking` / `VillaFinance` / `VillaBookingDetails`, not from `VillaCheckoutDetail`. The table is either a deprecated holdover from an earlier schema or was never deployed to prod; either way, there is zero production data to migrate.
- **Decision:**
  1. **Drop `GET /checkouts/{id}` and `GET /checkouts` from the API spec.** They are a legacy naming relic that duplicates `/payments` filtered by `purpose`.
  2. Where consumers want "the deposit / rental balance / security deposit row for a booking", use the nested track endpoints already defined in §2.12 (`/bookings/{id}/deposit`, `/balance`, `/security`) or the flat list `GET /payments?booking=…&purpose=…`.
  3. The `purpose` filter is added to `GET /payments` listing parameters.
  4. The `Payment.purpose` enum already covers all three legacy "checkout payment types" (`INITIAL_PAYMENT_DUE` → `DEPOSIT`, `RENTAL_BALANCE_PAYMENT` → `BALANCE`, `SECURITY_DEPOSIT` → `SECURITY_DEPOSIT`). No model changes required.
  5. No new "settlement" or "payout-reconciliation" model is added. Owner-side payouts, gateway-side fee reconciliation, and accounting ledger entries are all out of MVP scope; revisit if/when an owner-payout workflow lands.
- **Follow-ups:**
  - `product-design/04-rest-api-surface.md` §2.14 updated: removed the two `/checkouts*` rows; documented the dropped endpoint and added `purpose` to the `/payments` filter list. ✓
  - `09-departures.md` updated: legacy mapping row for `VillaCheckoutDetail` rewritten to point explicitly at `payments.Payment` with the rationale and the legacy-vs-new field correspondence. ✓
  - `product-design/01-domain-model.md` updated: legacy mapping row corrected (was "Collapsed into PaymentEvent" — should be "Replaced by `payments.Payment` rows"); `VillaPaymentDetail` row also clarified (Payment + PaymentEvent split, per issue #5). ✓

### #7 — Booking state machine missing transitions. — **Resolved**

- **API surface (§2.8):** `:confirm`, `:cancel`, `:owner-approve`, `:owner-decline`, `:modify-dates`, `:modify-guests`, `:archive`, `:restore`, `:check-in`, `:check-out`, `:resend-confirmation` (11 colon-verbs total).
- **Backend (`06-availability.md`) before this issue:** `submit`, `auto_accept`, `owner_approve`, `owner_decline`, `record_deposit`, `arm_balance`, `record_balance`, `check_in`, `complete()` (system on `date_to` → `COMPLETED`), `cancel`, `expire`. **No** `modify_dates`, `modify_guests`, `archive`, `restore`, `resend_confirmation_email`; `:check-out` had no manual operator path.
- **Investigation:**
  - **Legacy date-change audit:** the live DB dump (`live-db-24-apr.sql`) contains **no** `VillaBookingDateHistory`, `VillaBookingChange`, `DateChangedAt`, `OriginalFromDate`, or `PreviousAmount` columns. The Blazor `Booking.razor` page binds `FromDate`/`ToDate` directly to the model via `OnFromDateChange` and posts through `ResService.ModifyBooking` — overwrite semantics, zero per-change audit. The rebuild's audit obligation is **new design**, not a legacy port.
  - **Legacy check-out:** no manual "mark checked out" UI exists. Departures were date-driven (the equivalent of the proposed beat task). The new `:check-out` is therefore a manual override added for early/late departures; the auto-completion beat task uses the same backend method.
  - **Legacy resend-confirmation:** `BookingInfo.razor:155` exposes "Resend Booking Summary" — direct evidence the workflow exists in legacy. Keep the API action; back it with a non-state-mutating method.
  - **Legacy archive:** `VillaArchiveBooking` table exists in legacy and is read by `GetArchiveBooking` in `ResService.cs`. It is an *operator-facing visibility* concept — bookings disappear from the main list and surface under an archive view — **not** a "this record shouldn't have existed" delete. The current rebuild already covers this with `Booking.is_archived` plus the separate `/bookings/archived` read surface, but the field was missing from `05-reservations.md` and the archive-vs-status distinction was undocumented. (Soft delete has since been eliminated entirely — see `09-departures.md` "Soft delete eliminated" — so archive is now simply orthogonal to the `status` enum, with no third axis to reconcile against.)
  - **`archived` vs `completed` enum collision:** `product-design/01-domain-model.md` §4 listed both `completed` and `archived` as status values; `06-availability.md` had only `COMPLETED` (no `archived`); meanwhile `05-reservations.md`'s model treated "delete" as a separate concept. Three slightly different shapes for what should be one decision. (The follow-up soft-delete-elimination work removed the third axis entirely — bookings now express lifecycle solely through `status` + the `is_archived` flag.)
- **Decision:**
  1. **Rename the terminal post-stay state** `BookingStatus.COMPLETED` → `BookingStatus.CHECKED_OUT` and **rename the transition** `complete()` → `check_out()`. The transition is the same code path whether invoked manually by an operator (early/late departure) or by the auto-completion Celery beat task on `date_to`. The product-design `01-domain-model.md` enum is realigned to the backend (single source of truth).
  2. **Add `:modify-dates`** as a non-state-mutating audited method `Booking.modify_dates(date_from, date_to, *, actor, reason)`. Allowed from `AWAITING_DEPOSIT`, `DEPOSIT_PAID`, `AWAITING_BALANCE`, `BALANCE_PAID` (refused from `CHECKED_IN` and terminal states). Acquires a short-lived `BookingHold` on the new range, runs the availability + change-over check, re-runs `PricingEngine.quote(...)`, replaces `pricing_snapshot`, recomputes `rental_price` / `balance_due` / `balance_due_at`, releases the prior hold, and writes a `BookingEvent` with `meta={"from": [...], "to": [...], "from_snapshot": {...}, "to_snapshot": {...}}`. `from_status == to_status` on the event (the state machine doesn't advance).
  3. **Add `:modify-guests`** symmetrically as `Booking.modify_guests(adults, children, infants, *, actor, reason)`. Re-runs the pricing engine (party-size can resolve to a different `RateRule` / occupancy band). Same allowed-from window and audit shape. No status change.
  4. **Add `:archive`/`:restore`** as flag mutations: `Booking.is_archived` (bool, default False) and `Booking.archived_at` (DateTimeField, null=True) added to the model. `archive()` allowed only from terminal states (`CHECKED_OUT`, `CANCELLED`, `EXPIRED`, `DECLINED`); `restore()` allowed when `is_archived=True`. The default `/bookings` list filters `is_archived=False` at the call site; `/bookings/archived` is the inverse query. Drop `archived` from the `Booking.status` enum (it was duplicating the flag). There is no `DELETE /bookings/{id}` — once a booking exists it is preserved for audit; correction goes via `:cancel` then `:archive` (see also `09-departures.md` "Soft delete eliminated").
  5. **Add `:resend-confirmation`** as a non-state-mutating idempotent action `Booking.send_confirmation_email(*, actor)`. Writes a `BookingEvent` with `meta={"resent_confirmation": true}` and (when the future `comms` app lands) a row to the email log. No status change. Matches the legacy "Resend Booking Summary" button.
  6. **Keep `:confirm`** as an alias that dispatches to the appropriate underlying transition (`owner_approve()` when in `PENDING_OWNER_APPROVAL`; advances `AWAITING_DEPOSIT` workflows otherwise). It's primarily a UX convenience; the service layer routes.
  7. The full transition table (including the new methods) lives in `06-availability.md` as the single source of truth; the API spec mirrors it and is forbidden from adding actions without a corresponding backend transition.
- **Follow-ups:**
  - `06-availability.md` updated: renamed `COMPLETED` → `CHECKED_OUT` and `complete()` → `check_out()`; added "Non-transition mutations" subsection covering `modify_dates`, `modify_guests`, `archive`, `restore`, `send_confirmation_email`; documented archive vs soft-delete distinction. ✓
  - `05-reservations.md` updated: added `is_archived` and `archived_at` to `Booking` field list; extended the Services bullet list with the new methods; fixed the "Dropped from legacy" line to reflect that `VillaArchiveBooking` maps to `is_archived`, not `status='COMPLETED'`. ✓
  - `product-design/01-domain-model.md` updated: realigned the `Booking.status` enum to match `06-availability.md` (single source of truth); dropped `archived` as a status value; rewrote the `ArchiveBooking` paragraph to spell out the flag-vs-soft-delete distinction. ✓
  - `product-design/04-rest-api-surface.md` §2.8 updated: rewrote the state-transitions table with per-action semantics; clarified that `DELETE /bookings/{id}` is soft-delete (not archive); pointed readers at `06-availability.md` for the canonical state machine. ✓
  - `09-departures.md` updated: rewrote the `VillaArchiveBooking` row; added a new row documenting that per-change audit on date/guest modifications is a **new design** (legacy had none). ✓
  - **Cross-check:** the `BookingHold` model is already specified in `06-availability.md` §A — `:modify-dates` reuses it. No new model required.

### #8 — `Tag` top-level resource doesn't exist. — **Resolved**

- **API original:** `/tags` CRUD (§2.3) plus `/properties/{id}/tags` GET/PUT (§2.2), `/public/tags`, `/properties/bulk:tag`. Glossed as "service-type metadata tags, distinct from features."
- **Backend:** No `Tag` model. `Feature.service_type` is a TextChoices on `Feature` (`AMENITY` / `INCLUDED_SERVICE` / `PAID_ADDON`). `product-design/01-domain-model.md` §1 carried a stub `Tag` entity ("Service-type metadata tag (similar to Feature but separate domain — used for back-office classification). Original `Tags`.") that was in tension with the backend.
- **Investigation:**
  - **Legacy schema:** No `Tags` / `VillaTags` table exists in any legacy SQL artifact. Confirmed against `live-db-24-apr.sql` (production dump, UTF-16 LE, ~96 MB), `ResSystem/Database/Scripts/VillaDb.sql`, and `ResSystem/Database/DbScript.sql` — zero matches for `CREATE TABLE [Tags]`, `[VillaTags]`, `TagId`, or any FK referencing a tag table. The `Tag` row in `01-domain-model.md` annotated "Original `Tags`" was a mis-citation; there is no `Tags` table to be original to.
  - **Legacy UI:** `ResSystem/NewResSystem/Pages/Others/Tags.razor` exists and is mounted at `@page "/tags"`. Reading the file (~454 lines) shows it is a **CRUD form over `VillaFeatures`** that calls `ResService.GetFeatures` / `ResService.ModifyFeatures` and exposes a `ServiceType` dropdown with two values: `ContactService = 10` and `PropertyFeature = 20`. The grid columns are id / icon / name / description / categories — exactly the `VillaFeatures` shape. The label "Tags" is operator-facing branding for the back-office segmentation; the storage is `VillaFeatures` with a `ServiceType` discriminator.
  - **Other tag-named code:** `PropertyFeaturesContent.razor` uses `_lstTags` / `_lstCategoryTags` as local variable names but the data type is `PropertyFeaturesModal` / `ResSelectItems<int>` — same story, "tag" is UI vocabulary over the features table. `Booking.razor` mentions "Villa Information (tags and description)" as a UI label, not a separate resource.
  - **Domain semantics:** The legacy two-value enum (`ContactService` / `PropertyFeature`) is a strict subset of the new three-value `Feature.service_type` enum (`AMENITY` / `INCLUDED_SERVICE` / `PAID_ADDON`). The new design already covers this discriminator with finer granularity.
  - **No back-office label semantics surface anywhere.** The brief speculated about labels like "needs-photo-refresh" or "premium-tier"; nothing in the legacy schema, the Blazor pages, or the .NET services suggests such operator-applied free-form labels exist. The legacy "Tags" is purely a feature-catalogue admin view, not a labelling system.
- **Decision (Option b — fold and drop):**
  1. **No `Tag` model.** No `PropertyTag` junction. No M2M from Property to Tag.
  2. **Drop the `/tags` API resource entirely:** `GET / POST /tags`, `GET / PATCH / DELETE /tags/{id}`, `GET / PUT /properties/{id}/tags`, `GET /public/tags`. Remove "tags" from the page-number pagination list in §1.
  3. The legacy "Tags" admin page is reproduced by `/features` with the existing `service_type` filter; the FE can render a "Tags" tab over `/features?service_type=INCLUDED_SERVICE` (or whatever segment maps to the legacy `ContactService` row) without any new endpoint.
  4. `/properties/bulk:tag` keeps its name (it's a generic verb in our API for "apply a labelled set to many") but its semantics narrow to feature/collection application, not tag application. Renamed to clarify.
  5. **Domain-model fix:** the `Tag` entity stub in `product-design/01-domain-model.md` §1 is removed; the `Feature` entry gets an explanatory paragraph about `service_type` and a pointer to this issue.
- **Follow-ups:**
  - `product-design/04-rest-api-surface.md` updated: removed `/properties/{id}/tags` block (§2.2), removed `/tags` CRUD block (§2.3), dropped "tags" from the page-number pagination list (§1), dropped `GET /public/tags`, narrowed `/properties/bulk:tag` gloss. ✓
  - `product-design/01-domain-model.md` updated: removed the `Tag` entity; added explanatory paragraph to `Feature (amenity)` describing `service_type` and the legacy "Tags" page; fixed two downstream mentions of "tags handle this" in the `PropertyContactAssignment` section and legacy mapping table that were predicated on a `Tag` model existing. ✓
  - `02-properties.md` updated: added a note under the `Feature` model explaining that the legacy `/tags` Blazor page is a `VillaFeatures` view and absorbed by `/features` with the existing `service_type` filter. ✓
  - `09-departures.md` updated: new row in the Property domain mapping table documenting that the legacy "Tags" admin page maps to `Feature` filtered by `service_type` — no `Tags` table exists in the legacy schema. ✓

### #9 — Roles table doesn't exist. — **Resolved**

- **API original:** `/roles` full CRUD (`GET`/`POST`/`PATCH`/`DELETE`) with permission sets, plus `GET /permissions` catalogue (§2.18).
- **Backend:** Plain Django `auth.Permission`; legacy `VillaRoles` already replaced by `accounts.ContactRole` TextChoices (per `09-departures.md`). No editable staff `Role` table; `product-design/01-domain-model.md` §6 had a stub `Role` entity ("named permission set, fields name/description/permissions") that conflicted with both `01-accounts.md` and `09-departures.md`.
- **Naming pitfall — two distinct "role" concepts:**
  1. **Staff role** — what back-office capability does a logged-in `User` have? This is what `/roles` API §2.18 is talking about (it sits under "Users & Roles" and the `?role=` filter is on `/users`).
  2. **Contact role** — how is a `Contact` related to a `Property` (owner / manager / agent / housekeeper / owner's-rep)? Already modelled as `accounts.ContactRole` TextChoices on `PropertyContactAssignment`. Exposed via `/properties/{id}/contacts` and `/contact-property-mappings`. **Not** what `/roles` API refers to.
- **Investigation:**
  - **Legacy `VillaRoles` table** (`live-db-24-apr.sql`, UTF-16 LE): 5 static rows — `(1, 'Owner', 10)`, `(2, 'Agent', 20)`, `(3, 'Villa Admin', 40)`, `(4, 'Villa Manager', 50)`, `(5, 'Management Company', 80)`. Schema: `Id` / `Name` / `Code` / `IsActive`. FK'd **from `VillaContactMap.RoleId` and `VillaContactRoleMapping.RoleId`** — i.e. it is the **contact-to-property** role lookup. Never referenced from `UserMaster`. Operators added zero custom rows in production: the 5 rows are the seed data and have stayed unchanged since the schema was first deployed.
  - **Legacy staff-role concept**: the `UserMaster` table has no role FK and no role enum. Staff power is a **single `IsSystemAdmin` boolean** (and a passive `IsActive` / `IsLock`). The .NET service layer (`NewResSystem.Core/Services/Users/UsersViewModel.cs` exposes a single `IsAdmin` bool; `UserService.cs:142` writes it to `@IsSystemAdmin`). No `RoleManager`, no `AspNetRoles` table, no permission claims. Two-tier permissions in production: superuser vs everyone-else.
  - **Conclusion**: the legacy app demonstrates zero operator demand for editable staff roles over four-plus years of production use. There is no legacy migration burden — there is no legacy staff-role data to migrate.
- **Decision (Option b — fixed enum, trim API):**
  1. **`User.role`** becomes a hard-coded `StaffRole` TextChoices with four values: `ADMIN` (full access; replaces legacy `IsSystemAdmin=1`), `RESERVATIONS` (bookings/enquiries/guests/comms), `ACCOUNTS` (payments/refunds/finance), `VIEWER` (read-only across the back office). The split below `ADMIN` is a modest improvement over the legacy two-tier model and lets the FE hide irrelevant nav.
  2. **No editable `Role` model.** No `RolePermission` junction. The enum-stub in `product-design/01-domain-model.md` §6 (`Role — named permission set ... permissions (JSON list ... or M2M)`) is removed.
  3. **Each enum value maps to a Django `auth.Group`** of the same name, created via a data migration. The Group owns the actual `auth.Permission` rows. Switching `User.role` re-attaches the user to the matching Group. Runtime checks use Django's standard framework (`user.has_perm("reservations.add_booking")`). The three custom Property-level permissions in `01-accounts.md` (`can_view_finance`, `can_approve_booking`, `can_manage_availability`) are wired into the Groups via the migration.
  4. **API trims:**
     - **Drop** `POST /roles`, `PATCH /roles/{id}`, `DELETE /roles/{id}`, `GET /roles/{id}` (no detail view — the role is the enum value).
     - **Drop** `GET /permissions`. Per-caller capability introspection rides on the existing `GET /auth/permissions` (§2.0). Server-side checks ride on Django's `auth.Permission` registry; no client-facing catalogue endpoint.
     - **Keep** `GET /roles` as a read-only enum listing (`[{"value": "admin", "label": "Admin"}, ...]`) so the FE can populate `?role=` filter on `/users` and the user-edit dropdown. Page-number pagination per §1.
     - `?role=` filter on `/users` validates against the enum.
  5. **Future escape hatch**: if business asks for custom roles, replace `User.role` enum with a `Role` FK to a new model that wraps the existing Groups, and unlock the CRUD verbs on `/roles`. The API surface (`GET /roles`) stays compatible; no breaking change for the FE filter.
- **Follow-ups:**
  - `01-accounts.md` updated: added `User.role` field; rewrote the "Roles" section to distinguish staff roles (new `StaffRole` enum) from contact roles (existing `ContactRole`); documented `auth.Group` mapping and legacy migration (`IsSystemAdmin=1` → `ADMIN`; `IsSystemAdmin=0` → `RESERVATIONS`). ✓
  - `09-departures.md` updated: clarified the `VillaRoles` row to spell out it's the *contact-to-property* role lookup (5 static seed rows); added a new row mapping `UserMaster.IsSystemAdmin` → `User.role` with the migration default. ✓
  - `product-design/01-domain-model.md` §6 updated: replaced `User.role (FK or enum)` with explicit `StaffRole` TextChoices; removed the conflicting `Role — named permission set` paragraph; added an explicit warning distinguishing `User.role` from `PropertyContactAssignment.role`. Replaced legacy `is_admin` field reference with Django's built-in `is_superuser`. ✓
  - `product-design/04-rest-api-surface.md` §2.18 updated: dropped `POST/PATCH/DELETE /roles`, `GET /roles/{id}`, and `GET /permissions`; kept `GET /roles` as read-only enum listing; added explanatory note about the two role concepts and pointer to `01-accounts.md` and this issue. ✓

---

## B. Out-of-scope creep (API includes deferred features)

Section B is scope triage: each row is a feature whose API spec appears in `04-rest-api-surface.md` but whose backend either has no model, has a model declared but no service, or has been explicitly deferred. Decisions are KISS-biased — default toward DROP/DEFER unless the feature is load-bearing for MVP. Where a feature has an entity declared in `01-domain-model.md` and is operationally essential, KEEP+MODEL records the commitment without expanding the entity spec inline (the model entry stands).

### #10 — Email templates + logs + code-auth log. — **Resolved (split)**

- **API surface:** `/email-templates` CRUD + `:preview` + `:test-send`, `/email-logs` + `:resend`, `/email-logs/bulk-resend`, `/code-auth-logs` (§2.19).
- **Backend:** `01-domain-model.md` §8 declares `EmailTemplate`, `EmailLog`, `CodeAuthLog`. `09-departures.md` notes the underlying comms app is "future scope".
- **Decision (split):** Transactional comms (booking confirmation, deposit request, owner-approval request, magic-link dispatch) are MVP-load-bearing — the booking workflow does not function without them. The **template-editing CMS is not.**
  1. **KEEP+MODEL** the read/log surface: `GET /email-templates`, `GET /email-templates/{id}` (read-only, seeded), `GET /email-logs`, `GET /email-logs/{id}`, `GET /code-auth-logs`. Logs are forensic-essential.
  2. **DROP / DEFER (v1.1):** `POST/PATCH/DELETE /email-templates`, `:preview`, `:test-send`, `:resend`, `/email-logs/bulk-resend`. Templates ship as code/seed data in v1.
  3. Send pipeline is implementation, not surface: emails are dispatched by service-layer calls inside booking/quotation/payment workflows. No public "send email" endpoint.
- **Follow-ups:** `04-rest-api-surface.md` §2.19 trimmed; bulk-resend row removed from §2.22; §3 action-inventory line replaced with deferred-note. ✓ Comms app spec is a v1.1 ticket — captures editable templates, ad-hoc resend, and a test-send harness.

### #11 — Channel-manager integrations (Airbnb / Booking.com / VRBO). — **Resolved (DROP)**

- **API surface:** `/properties/{id}/channel-mappings` (§2.2), `/webhooks/airbnb|booking|vrbo`, `/channel-sync/*` (§2.25).
- **Backend:** `ChannelSyncJob` declared in `01-domain-model.md` §9 as a stub; `PropertyChannelMapping` declared in §1 as a placeholder. No service layer, no inbound webhook plumbing.
- **Decision:** **DROP** all OTA endpoints. Channel-manager integration is a discrete v1.x project with its own product scoping, contract negotiation, and sync engine — folding it into MVP would dwarf every other workstream. Domain-model stubs remain as forward-looking entities; no endpoints in v1.
- **Follow-ups:** `04-rest-api-surface.md` §2.2 importers block trimmed (channel-mappings rows removed, Zoho importer kept); §2.25 replaced with deferred-note; §3 action-inventory updated; §1 webhooks note rewritten. ✓ v1.x ticket: scope OTA channel-manager integration end-to-end.

### #12 — iCal feeds (per-property + per-owner). — **Resolved (DEFER)**

- **API surface:** `/feeds/properties/{id}/ical`, `/feeds/contacts/{id}/ical`, `:rotate-token` (§2.24).
- **Backend:** Not modelled. No `FeedToken` entity, no rotation surface, no signed-URL infra.
- **Decision:** **DEFER to v1.1.** Single feature with modest scope, but no MVP ops dependency and OTA-style calendar subscription is most useful when channel-manager integration (issue #11) lands. Revisit alongside that effort.
- **Follow-ups:** `04-rest-api-surface.md` §2.24 replaced with deferred-note. ✓ v1.1 ticket: iCal export feeds with signed-URL token rotation.

### #13 — Stored payment methods / wallet. — **Resolved (DROP)**

- **API surface:** `/payment-methods`, `POST /guests/{id}/payment-methods`, `DELETE …/{pm_id}` (§2.14).
- **Backend:** Already explicitly deferred per backend note ("`BookingPaymentMethod` if multi-method ever lands"); the new `PaymentInstrument` model is a per-charge audit record, not a reusable wallet.
- **Decision:** **DROP.** v1 captures cards per-transaction via the gateway's hosted fields. Multi-method wallet is a discrete future feature. Domain model `PaymentInstrument` note updated to reflect single-use-audit semantics.
- **Follow-ups:** `04-rest-api-surface.md` §2.14 payment-methods rows removed; `01-domain-model.md` `PaymentInstrument` paragraph clarified to reflect per-charge audit semantics in v1. ✓

### #14 — In-app notifications + per-user preferences. — **Resolved (KEEP+MODEL)**

- **API surface:** `/notifications`, `:mark-read`, `:mark-all-read`, `/notification-preferences` (§4).
- **Backend:** `01-domain-model.md` §11 declares both `Notification` and `NotificationPreference`. Backend docs lacked a service-layer notes section but the entities exist.
- **Decision:** **KEEP+MODEL.** In-app notifications are operationally essential for the booking workflow — owners need a non-email signal that they have a pending booking to approve, ops staff need deposit-paid/balance-paid alerts, and the preference table is the unsubscribe surface. The entities are already declared; backend service layer is a fill-in, not a new model.
- **Follow-ups:** API surface stands as specified. Backend gap: a `notifications` app spec is needed — capture event-to-notification mapping (which booking transitions fan out to which recipients) in a follow-up. Not blocking MVP API contract.

### #15 — Feature flags. — **Resolved (KEEP+MODEL, trimmed)**

- **API surface:** `GET /feature-flags`, `GET /feature-flags/all`, `PATCH /feature-flags/{key}` (§4).
- **Backend:** `01-domain-model.md` §11 declares `FeatureFlag` (`key`, `description`, `is_enabled_default`, `enabled_for_users` M2M, `rollout_percent`).
- **Decision:** **KEEP+MODEL** but trim. Internal infra, not customer-facing — minimal surface. Collapse `/feature-flags/all` into a `?all=true` query param on the main list endpoint.
- **Follow-ups:** `04-rest-api-surface.md` §4 feature-flags trimmed to two endpoints. ✓

### #16 — Exports + generic async job surface. — **Resolved (KEEP+MODEL)**

- **API surface:** `/exports` CRUD, `/jobs/{id}`, `/jobs/{id}:cancel` (§2.21).
- **Backend:** `01-domain-model.md` §10 declares `Export`, `ReportRun`, `ScheduledReport`. Reports are MVP (owner statements, commissions, tax, refunds, enquiry-funnel — already in §2.20).
- **Decision:** **KEEP+MODEL.** Reports are operational essentials; exporting them as CSV/PDF/XLSX is the obvious next step and the generic `/jobs/{id}` polling surface is also reused by document generation (issue #18) and bulk imports.
- **Follow-ups:** API surface stands. Backend gap: `Export` and `ReportRun` need a thin service-layer spec (where files land — S3 key convention, expiry) — capture in a follow-up backend doc.

### #17 — Outbound webhook subscriptions. — **Resolved (DROP)**

- **API surface:** `/webhook-subscriptions` resource referenced in §1 webhooks convention.
- **Backend:** Not modelled.
- **Decision:** **DROP.** Outbound webhook fan-out (notifying third parties of our state changes) is future scope. Internal integrations (Zoho push, WordPress fan-out from issue #1) run via Celery jobs configured through `/system/integrations`, not via a customer-facing subscription model.
- **Follow-ups:** `04-rest-api-surface.md` §1 webhook convention rewritten to remove the `/webhook-subscriptions` reference. ✓

### #18 — Booking document generation (contract / voucher PDF). — **Resolved (KEEP+MODEL)**

- **API surface:** `GET /bookings/{id}/documents`, `POST :generate`, `GET /bookings/{id}/documents/{doc_id}` (§2.8).
- **Backend:** `01-domain-model.md` §4 declares `BookingDocument` (`kind ∈ {confirmation, contract, voucher, invoice, receipt}`, `file_key`, `generated_at/by`, `sent_to_guest_at`).
- **Decision:** **KEEP+MODEL.** Operationally essential — confirmation PDFs and contracts are part of the booking flow, not optional. The entity is already declared and small. Generation is async via the generic `/jobs/{id}` surface (issue #16).
- **Follow-ups:** API surface stands. Backend gap: PDF rendering pipeline (template + WeasyPrint or similar) is implementation — flag in backend doc as a v1 deliverable, not a model gap.

### #19 — Quotation PDF. — **Reversed → DROP (2026-06-02)**

- **API surface:** `/quotations/{id}/pdf` — **removed** from §2.7.
- **Original decision (2026-05-12):** KEEP+MODEL, justified by "quotations
  are sent to guests as PDFs; the legacy app does this."
- **Reversal (2026-06-02):** the premise was false. Legacy
  (`ResService.SentQuotation` / `SentQuotationNew` → `SentQuoteEmail`)
  sends quotations as **inline HTML email only — no PDF, no attachment,
  and no download/print affordance.** Legacy's `wkhtmltopdf` pipeline is
  used *only* for booking receipts (see #18), never quotations. The
  rebuild already matches legacy: a rich inline-HTML quote email plus a
  copy-to-Outlook clipboard path. A guest-saveable quotation PDF is
  therefore net-new scope beyond legacy parity — overreach — and is
  dropped. Revisit only if a concrete operator/guest requirement appears
  post-v1, at which point the existing `render_quotation_html` seam can
  back it cheaply.
- **Follow-ups:** drop the `:pdf` endpoint stub
  (`reservations/views/quotation.py`).

### #20 — Audit log (global + per-resource alias). — **Resolved (KEEP+MODEL)**

- **API surface:** `GET /audit-log`, `GET /audit-log/{id}`, `GET /{resource}/{id}/audit-log` (§4).
- **Backend:** `01-domain-model.md` §11 declares `AuditLog` as "the single source of truth for who-changed-what" with `actor`, `entity_kind`, `entity_id`, `before/after`, `correlation_id`. Domain-specific event tables (`BookingEvent`, `PaymentEvent`) coexist as workflow-specific audit streams.
- **Decision:** **KEEP+MODEL.** The entity is declared and is referenced repeatedly by resolved issues (#4 — note mutation audit, #7 — date-change audit). Compliance and ops need a queryable cross-entity audit. `BookingEvent` / `PaymentEvent` stay as workflow-state audit (status transitions, money movement); `AuditLog` is the generic record for everything else (field edits, archive/restore, note CRUD, role changes).
- **Follow-ups:** API surface stands. Backend gap: service-layer convention for emitting `AuditLog` rows (a `record_change(entity, before, after, actor, action)` helper) — capture in a backend follow-up.

### #21 — System integrations admin. — **Resolved (KEEP+MODEL, minimal)**

- **API surface:** `GET /system/integrations`, `GET /system/integrations/{key}`, `POST :test` (§2.28).
- **Backend:** Not modelled; config lives in `SystemDefaults` keys.
- **Decision:** **KEEP+MODEL** minimally. Required by the issue #1 resolution (WordPress fan-out configured via `system/integrations`) and the Zoho OAuth flow. No new top-level `Integration` entity for MVP — config-row identity is the `key`, backed by `SystemDefaults` rows + the existing `ZohoSyncJob` / `SyncRecord` state. Promote to a real entity if config-row identity becomes load-bearing post-v1.
- **Follow-ups:** `04-rest-api-surface.md` §2.28 expanded with intent note. ✓

### #22 — `GuestPreference` model. — **Resolved (closed)**

- **API surface:** Not exposed (no `/guests/{id}/preferences` endpoint in §2.17).
- **Backend:** Explicitly dropped per `09-departures.md`.
- **Decision:** **Closed.** Nothing to do — backend dropped it and the API never exposed it. The brief flagged it for completeness; verification confirms no action required. Re-add as a sub-resource of `/guests/{id}` if a real requirement appears post-v1.
- **Follow-ups:** None.

---

## C. Workflow & semantic mismatches

### #23 — Property status values disagree. — **Resolved**
- **API original:** `POST /properties/{id}:publish` ("draft → live"), `:unpublish` ("live → draft").
- **Backend original:** `Property.status ∈ {DRAFT, ACTIVE, OFFLINE, ARCHIVED}` (4 values; product-design said 3, backend doc had 4 — the cross-cut had drifted).
- **Investigation:** Legacy `VillaStatus` lookup table (live DB dump) seeds exactly 4 rows: `live_online`, `live_offline`, `pending`, `archive`. `live_offline` is the only one with no obvious 3-value mapping — but its operational meaning ("published but not currently bookable") is already covered by `PropertySettings.availability_default = UNAVAILABLE`, which is a separate axis (publication vs bookability).
- **Decision:** Standardise on `ACTIVE` (Django convention; "live" is web-jargon). Collapse `Property.status` to **three** values: `DRAFT` / `ACTIVE` / `ARCHIVED`. Drop `OFFLINE`. API verbs become `:activate` (any → `active`) and `:archive` (any → `archived`); `:restore` un-archives back to `draft`. `:publish` / `:unpublish` removed. Legacy migration: `live_online`→`ACTIVE`, `pending`→`DRAFT`, `archive`→`ARCHIVED`, `live_offline`→`ARCHIVED` (with a note in the migration that the operator can re-`:activate` if the property is being temporarily withheld via settings instead).
- **Follow-ups:**
  - `02-properties.md` updated: `Property.status` enum trimmed to three values with explanatory note; legacy-mapping bullet expanded. ✓
  - `product-design/01-domain-model.md` §1 updated: status note expanded to call out the dropped `OFFLINE` value, the legacy `live_offline` mapping, and the new API verbs. ✓
  - `product-design/04-rest-api-surface.md` §2.2 and §3 action-inventory updated: `:publish` / `:unpublish` replaced with `:activate` / `:archive`. ✓
  - `09-departures.md` `VillaStatus` row rewritten with the 4→3 mapping and rationale. ✓

### #24 — Payment `:waive` and `:mark-paid` have no backend transitions. — **Resolved**
- **API:** `POST /bookings/{id}/deposit:waive`, `/balance:waive`, and `:mark-paid` on deposit / balance / security tracks (§2.10–2.12).
- **Backend original:** `Payment.status` had no `WAIVED` value and no `mark_paid()` transition; `:mark-paid` was a hand-wave that "implied" `provider=MANUAL_BANK_TRANSFER` without spelling out the lifecycle.
- **Decision:**
  1. **Add `WAIVED` to `Payment.status`** as a terminal state (applies to `DEPOSIT` and `BALANCE` purposes only; `SECURITY_DEPOSIT` lives on its own workflow model — see issue #25). `:waive` is an operator action gated by `payments.payment.waive` permission; transition is `PENDING|PROCESSING → WAIVED`. Side effect: fire `payment_waived(payment)` signal which advances the booking exactly as `payment_succeeded` would (the booking workflow doesn't care whether the money actually moved; only that the receivable is resolved).
  2. **`:mark-paid` is a manual-payment shortcut**, not a generic "force to SUCCEEDED" — it writes the manual receipt onto the existing scheduled `Payment` row. Transition is `PENDING → SUCCEEDED` with `provider=MANUAL_BANK_TRANSFER` (or `OTHER` for cash / cheque), `settled_at=paid_at`, `provider_reference` from input. Fires the normal `payment_succeeded` signal so reservations advances `record_deposit` / `record_balance` consistently.
  3. **PaymentEvent** records both transitions with `kind ∈ {WAIVED, MARK_PAID}`.
  4. For the **security-deposit** track, `:mark-paid` does **not** act on a `Payment` row — it advances the parent `SecurityDeposit` workflow (issue #25) along the BT-refundable path. The security track has no `:waive` action (a property either has a SD policy or it doesn't; if not, no SD row is ever created).
- **Follow-ups:**
  - `07-payments.md` updated: added `WAIVED` to `Payment.status`; added the "Operator-applied transitions" subsection with the transition table; added `payment_waived` to the signal contract; new-vs-legacy entry. ✓
  - `product-design/01-domain-model.md` §7 `PaymentEvent` status enum extended with `waived` and explanatory note. ✓
  - `product-design/04-rest-api-surface.md` §2.10–2.12 already correct — no edit needed.

### #25 — Security-deposit pre-auth hold lifecycle. — **Resolved**
- **API:** `POST /bookings/{id}/security/payments/{id}:hold`, `:release`, `:claim`, plus `:mark-paid` on the parent track.
- **Backend original:** `Payment.status` only had `PENDING` / `PROCESSING` / `SUCCEEDED` — no `AUTHORIZED` / `HELD` / `CAPTURED`. Pre-auth flow had no representation. `01-domain-model.md` §7 already declared a `SecurityDepositTrack` model with the right enum shape; the backend `07-payments.md` was the lagging side.
- **Decision:** Mirror the `Refund` pattern (issue #5). Promote security-deposit to a **first-class workflow model `SecurityDeposit`** with its own state machine; the gateway-transaction audit lives on spawned `Payment(purpose=SECURITY_DEPOSIT)` rows linked via `meta['security_deposit_id']`.
  1. Single model with `kind` (`PRE_AUTH_HOLD` / `BT_REFUNDABLE`) discriminating the two operational paths. `kind` is immutable after creation.
  2. **Pre-auth path** states: `AWAITING_DETAILS` → `PRE_AUTHED` → (`RELEASED` | `CAPTURED` | `EXPIRED`); `FAILED` from any non-terminal. `:hold`, `:release`, `:claim` are the operator actions; `EXPIRED` is system-driven via Celery beat when `hold_expires_at` passes.
  3. **BT refundable path** states: `AWAITING_BT` → `HELD` → (`REFUNDED` | `PARTIALLY_REFUNDED`); `FAILED` from `AWAITING_BT` on timeout. `:mark-paid` records the manual BT receipt (creates a `Payment(provider=MANUAL_BANK_TRANSFER, status=SUCCEEDED, purpose=SECURITY_DEPOSIT)`); release at post-departure delegates to the `Refund` workflow (`purpose_track=SECURITY_DEPOSIT`) so separation-of-duties applies uniformly.
  4. `PaymentEvent` extended to a **3-FK polymorphic** audit (one of `payment` / `refund` / `security_deposit` set per row).
  5. The pre-auth `:claim` does **not** route through `Refund` (it captures against an existing authorization, not a money-return movement). BT path partial refunds **do** route through `Refund` (because they involve returning money to the guest).
  6. `01-domain-model.md` §7 renamed `SecurityDepositTrack` → `SecurityDeposit` to match the new workflow shape; dropped the synthetic `not_applicable` status (when no SD is required, no row exists).
  7. `Payment.UniqueConstraint(active per purpose)` is relaxed for `SECURITY_DEPOSIT` (one workflow can spawn multiple `Payment` rows over its life — pre-auth + capture, or manual-BT + refund). One active `SecurityDeposit` per `Booking` is enforced on the workflow model.
- **Follow-ups:**
  - `07-payments.md` updated: new `SecurityDeposit` model section with two state machine tables; `SecurityDepositService` skeleton; `PaymentEvent` extended to 3-FK polymorphic; signal contract extended (`security_deposit_released`, `security_deposit_expired`); unique-constraint scope tightened to `DEPOSIT`/`BALANCE` only; new-vs-legacy entry. ✓
  - `product-design/01-domain-model.md` §7 updated: `SecurityDepositTrack` renamed to `SecurityDeposit`; field list and status enums aligned to backend; transition summary added; relationship summary cardinality changed from `1..1` to `0..1`. ✓
  - `product-design/04-rest-api-surface.md` §2.12 already correct — no edit needed (action verbs were already `:hold` / `:release` / `:claim`).
  - **Cross-cutting:** SecurityDeposit now mirrors Refund — both are workflow models with state machines; `Payment` is the gateway-transaction ledger underneath. Same pattern as issue #5.

### #26 — `assigned_to` filter has no backing field. — **Resolved**
- **API:** `?assigned_to=` filter on `GET /enquiries` and `GET /bookings`; `:assign` action on both.
- **Backend original:** `Booking.agent` and `Enquiry.agent` exist (FK to `Contact`), but no FK to `User` for an internal staff owner. The two concepts had silently merged.
- **Decision:** Add `assigned_to` FK to `User` on both `Enquiry` and `Booking` (nullable, `SET_NULL`, `related_name="assigned_{enquiries,bookings}"`). `agent` and `assigned_to` are kept as **two distinct fields** representing two distinct concepts:
  - `agent` — **external** intermediary (Contact FK): a travel agent or booking representative acting *on behalf of the guest*. Already populated by the legacy data; represents the relationship the platform brokers.
  - `assigned_to` — **internal** staff owner (User FK): which Canary-side staff member owns the work. Backs the API filter and the `:assign` action.
  Renaming the filter to `?agent=` (collapsing the two) would lose the distinction; legacy data already has both concepts (the agent contact is real, and operators have long wanted an internal-owner field — `UserMaster.AssignedToBookingsView` exists but is unused in legacy code, confirming the gap).
- **Follow-ups:**
  - `05-reservations.md` updated: `Enquiry.assigned_to` and `Booking.assigned_to` field bullets added; `agent` field comments clarified. ✓
  - `product-design/01-domain-model.md` §3 (Enquiry) and §4 (Booking) field lists updated with both fields and the internal-vs-external note. Relationship summary extended. ✓
  - `product-design/04-rest-api-surface.md` already correct — `?assigned_to=` filter and `:assign` action need no change.

### #27 — Enquiry has no activity timeline. — **Resolved**
- **API:** `GET /enquiries/{id}/activity`.
- **Backend original:** `BookingEvent` exists; no `EnquiryEvent`. Issue #20 just established that `AuditLog` is for everything; domain-specific event tables exist for hot timelines (Booking, Payment) where structured queries matter.
- **Decision:** Add `EnquiryEvent` mirroring `BookingEvent`. Same shape: `(enquiry, from_status, to_status, kind, actor, source, reason, meta)`. `kind` enum gives the activity stream queryable categories (`STATUS_CHANGE`, `ASSIGNED`, `UNASSIGNED`, `CONTACTED`, `QUOTE_SENT`, `CONVERTED`, `LOST`, `REOPENED`, `NOTE_ADDED`). `NOTE_ADDED` is the only event-kind written outside a transition method (emitted by an `EnquiryNote.post_save` signal). The cross-cutting `AuditLog` continues to record field-level edits; `EnquiryEvent` is the workflow-state + assignment timeline.
- **Follow-ups:**
  - `05-reservations.md` updated: `EnquiryEvent` model section added under Enquiry; file layout updated to include it in `enquiry.py`. ✓
  - `product-design/01-domain-model.md` §3 relationship summary extended with `Enquiry (1) ── (many) EnquiryEvent`. ✓
  - `product-design/04-rest-api-surface.md` already correct — endpoint exists.
  - Consistent with issue #20: domain-specific event tables (`BookingEvent`, `PaymentEvent`, `EnquiryEvent`) for hot timelines; generic `AuditLog` for everything else.

### #28 — Property descriptions API vs backend flat columns. — **Resolved**
- **API:** `/properties/{id}/descriptions/{section}` with `section ∈ {overview, house-rules, villa-info, further-info}`.
- **Backend original:** `Property` carried flat columns `overview`, `house_rules`, `feature_description`, `room_description`, `notes` — five columns, names didn't 1:1 match the API's four sections. `01-domain-model.md` §1 already declared a `PropertyDescription` sub-resource model; the backend `02-properties.md` was the lagging side.
- **Decision:** Adopt the normalised `PropertyDescription(property, section, body)` child table. Drop the flat columns from `Property`. Section enum is fixed (`OVERVIEW`, `HOUSE_RULES`, `VILLA_INFO`, `FURTHER_INFO`); kebab-cased on the API path. `VILLA_INFO` absorbs the two legacy columns (`feature_description` + `room_description` concatenated at migration — the two-column split was a UX artefact, not a semantic distinction). Constraint: `UniqueConstraint(property, section)`. Sections are sparse: a property may have zero, one, or all four rows. API gains a `DELETE /properties/{id}/descriptions/{section}` to remove a row.
- **Follow-ups:**
  - `02-properties.md` updated: `Property` model field list trimmed of the five flat columns; new `Descriptions` section with the `PropertyDescription` model and migration mapping; file layout updated with `descriptions.py`; dropped-section bullet added. ✓
  - `product-design/01-domain-model.md` §1 `PropertyDescription` sub-resource bullet expanded with the no-flat-column note and pointer to this issue. ✓
  - `product-design/04-rest-api-surface.md` §2.2 Descriptions table re-written with explanatory prose and `DELETE` row added. ✓
  - `09-departures.md` new mapping row added for the flat-column-to-`PropertyDescription` migration. ✓

### #29 — Collections membership PUT loses through-fields. — **Resolved**
- **API:** `PUT /properties/{id}/collections` (and the mirror `PUT /collections/{slug}/properties`).
- **Backend:** `CollectionMembership` is an explicit through model with `sort_order`, `featured_until`, `description`. A naive `PUT [<id>, ...]` would silently zero those fields on every replace.
- **Decision:** Keep `PUT` (full-set replace is the convenient verb for "drag-and-drop reorder + edit per-row attrs in one call") but change the body shape to an array of **membership objects**, not ids: `[{collection: <slug-or-id>, sort_order, featured_until, description}, ...]`. Add singular non-destructive paths for fine-grained edits: `POST /properties/{id}/collections` (attach one), `PATCH /properties/{id}/collections/{collection}` (edit through-fields), `DELETE /properties/{id}/collections/{collection}` (detach one). Mirror semantics on `/collections/{slug}/properties`.
- **Follow-ups:**
  - `02-properties.md` updated: `CollectionMembership` constraint section gets a note pointing at the API body shape. ✓
  - `product-design/04-rest-api-surface.md` §2.2 Collections block expanded with prose, body shape, and the new singular `POST` / `PATCH` / `DELETE` rows; §2.3 mirror endpoint clarified. ✓
  - `product-design/01-domain-model.md` already correct (the through model is described accurately in §1 already).

---

## D. Missing admin surfaces (entity exists; API doesn't expose it)

| # | Backend entity | Decision | Status |
|---|---|---|---|
| 30 | `ChangeOverRule` (per-property check-in weekdays) | **EXPOSE** — nested `/properties/{id}/change-over-rules` CRUD | **Resolved** |
| 31 | ~~`Surcharge` per `RatePlan`~~ — model retired in issue #3; `Extra` replaces it and now has CRUD via `/properties/{id}/extras` | — | **Resolved (by #3)** |
| 32 | `Discount` | **EXPOSE** — `/discounts` (flat, with `?property=` / `?card=` filters), `/rate-cards/{id}/discounts`, `/properties/{id}/discounts`, and `POST /discounts:lookup-code` for promo-code validation | **Resolved** |
| 33 | `TermsVersion` | **EXPOSE** read+publish — `GET/POST /terms-versions`, `GET /terms-versions/{version}`, `POST :publish` (atomic flip of `is_current`), `GET /terms-versions/current`. No `PATCH`/`DELETE` (append-only legal copy) | **Resolved** |
| 34 | `ConciergeService` catalogue | **DROP** — legacy held only 2 tier-label rows ("Quintessential", "Signature"). Collapse to `ConciergeTier` TextChoices on `BookingConciergeItem`; per-item name/description/price/unit move onto the line item. No catalogue model, no `/concierge-services` endpoint | **Resolved** |
| 35 | `NearbyPlaceType` | **EMBED** read-only — keep model (small curated taxonomy used as FK from `PropertyNearbyPlace`); expose `GET /nearby-place-types` for dropdown population. No write CRUD in v1; seeded via data migration. Per-property POIs remain at `/properties/{id}/nearby` (already exposed) | **Resolved** |
| 36 | `PropertyFinance` children (5 OneToOne) + `Group*` mirrors | **COLLAPSE** — fold `Commission`, `TaxPolicy`, `BankAccount`, `PaymentSchedule`, `SecurityDepositPolicy` into the parent `PropertyFinance` as a flat field set. Same for `GroupFinance` (group-level mirror). API stays `/properties/{id}/finance` and adds `/property-groups/{id}/finance` (issue #38). The "separate permissions per child" rationale doesn't apply — MVP staff roles (`ADMIN`/`RESERVATIONS`/`ACCOUNTS`/`VIEWER` per issue #9) gate the whole finance form, not individual sub-concerns | **Resolved** |
| 37 | `PropertySettings` vs `GroupSettings` | **EXPOSE** group settings — add `GET/PATCH /property-groups/{id}/settings` mirroring the property surface. `GroupSettings` is the inheritance floor (non-nullable defaults) that `PropertySettings` null-fields fall back to | **Resolved** |
| 38 | `PropertyGroup` config children | **EXPOSE** — add `/property-groups/{id}/finance` (flat, per #36) and `/property-groups/{id}/settings` (per #37). Group is the inheritance floor; without operator access to its config the property-level `null = inherit` semantics are unusable | **Resolved** |

---

## E. Smaller items

| # | Issue | Decision | Status |
|---|---|---|---|
| 39 | Idempotency-Key generic surface | **GENERIC TABLE + MIDDLEWARE** — add `core.IdempotencyRecord(user, path, key, request_hash, response_status, response_body, response_headers, expires_at)` and `core.middleware.IdempotencyMiddleware`. Drop the per-model `idempotency_key` columns from `Payment`, `Refund`, `SecurityDeposit`. Dedupe lives at the API boundary. Endpoint-policy-driven: payment/booking/refund-creation views set `idempotency_required=True` (header required → `400` if missing); other unsafe POSTs are opt-in. Hash mismatch → `409 Conflict`. Nightly cleanup task. | **Resolved** |
| 40 | Upload storage backend | **S3 via `django-storages`** — `DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"`; MinIO container in local dev. Two-step signed-URL pattern (`POST /uploads:sign` → client PUT → `POST /properties/{id}/images` with returned key) backed by a transient `core.UploadTicket` row. Small files (<5 MB) may still use direct `POST /uploads`. `PropertyImage.image` retains its `ImageField(upload_to=…)` shape — only the storage backend swaps. | **Resolved** |
| 41 | Sessions list & revoke | **DEFAULT DJANGO SESSIONS + SERVICE LAYER** — no new session model; use the existing `django_session` table. Add `accounts.UserSession(user, session_key, last_seen_at, ua, ip)` as a denormalised index (written on login signal) so `GET /auth/sessions` is an indexed query. `SessionService.list_for_user / revoke / revoke_all_for_user` thin wrappers; revoke hits both tables in `transaction.atomic`. Daily cleanup task for revoked rows. | **Resolved** |
| 42 | Zoho OAuth credential storage | **GENERIC `OAuthCredential` MODEL** — `integrations.OAuthCredential(provider, access_token, refresh_token, expires_at, scope, account_id, connected_by, connected_at, disconnected_at, is_active)`; tokens encrypted at rest via Fernet (same pattern as `User.tfa_secret` / `comms.SmtpProfile`). `OAuthService.begin / complete / disconnect / get_access_token` orchestrates the `/zoho:connect` / `:disconnect` flow. Hourly `refresh_oauth_tokens` Celery beat task pre-emptively refreshes near-expiry tokens; `ZohoSyncClient` reads the credential on every call. Single active credential per provider enforced by partial unique constraint. | **Resolved** |
| 43 | 2FA library + SMS path | **TOTP via `pyotp`; SMS DEFERRED.** `User.tfa_method` becomes `{NONE, TOTP}` for MVP (`SMS` enum value reserved for future). Add `tfa_enrolled_at` and hashed `tfa_recovery_codes` JSONField. `accounts.services.TwoFactorService.enroll / confirm_enrollment / challenge / verify / disable` backs the API. 30-second step, 6-digit codes, ±1 step drift on verify; rate-limited (5 fails / 5 min → 15-min lockout). | **Resolved** |
| 44 | Three search endpoints (`/availability:search`, `/quotations:search-villas`, `/pricing:quote-bulk`) | **KEEP ALL THREE** — they are meaningfully different: `/availability:search` is availability-only (no prices); `/pricing:quote-bulk` is **stateless** priced results for N tuples (used by FE comparison tables/cards — no quotation written); `/quotations:search-villas` is **stateful** and operator-facing (creates/updates `QuotationLine` candidates attached to a given `Quotation` draft). Boundaries documented inline in §2.4 / §2.5 / §2.7 of `04-rest-api-surface.md`. | **Resolved** |
| 45 | Deposit source of truth | **DROP `Booking.deposit_amount` / `deposit_percentage` COLUMNS.** Deposit *requirement* is config on `PropertyFinance.deposit_*`; deposit *track* is the `Payment(purpose=DEPOSIT)` row created by `PaymentScheduler` at booking-creation time; the locked figure is also embedded in `Booking.pricing_snapshot` (immutable price-at-confirmation). API consumers read deposit state from `GET /bookings/{id}/deposit` or `GET /payments?booking=…&purpose=DEPOSIT`. `Booking` no longer carries the duplicated columns. | **Resolved** |

---

## Decision log

| Date | Issue | Decision | Notes |
|---|---|---|---|
| 2026-05-12 | #1 | Drop `/sites` from API. Keep `site_source` enum. WP fan-out via integrations. | Confirmed against `live-db-24-apr.sql` — multi-tenancy never deployed; `VillaSite` was WP publishing-target registry. |
| 2026-05-12 | #2 | Adopt three-level `RatePlan → RateCard → RateRule`. Drop `SeasonDateRange` and `OccupancyBand` as first-class entities. Move `Discount` FK to `RateCard`. Rename API: keep `/seasons` + `/rate-cards`, delete `/date-ranges` + `/occupancy-bands`, add `/rate-cards/{id}/rules`. | Production data showed `VillaSeasonDates` (1.04/season) and `VillaOccupencyPrice` (3% of rates) were vestigial. Three-level honors operator mental model from workflows §13. |
| 2026-05-12 | #3 | Add `pricing.Extra` (property-scoped catalogue: cleaning/pet/heating/linen/extra-bed/etc., with mandatory-vs-opt-in flag and date+party windows). Retire `pricing.Surcharge`. Tax & commission read from `PropertyFinance` resolvers. Closes follow-up #31. | Legacy never tracked cleaning fees as structured data — `IsExTra=1` rate rows were capacity uplifts, not fees. Surcharge model conflated config (tax/commission) with charges. |
| 2026-05-12 | #4 | Adopt `BookingNote` and `EnquiryNote` collections (per-domain, with `kind` / `author` / `visibility` / timestamps). Drop all flat note `TextField` columns from `Booking`, `Enquiry`, `Quotation`. Preserve the guest's original web-form message as `Enquiry.inbound_message` (provenance, not a note). Keep API as specified. | Legacy shape was overwrite-only textareas with no authorship; API already commits to a collection; per-row audit aligns with the project's "improvements over original" goal. The three-textarea legacy UI survives as three `?kind=`-filtered tabs over one collection. |
| 2026-05-12 | #5 | Add dedicated `payments.Refund` workflow model with 7-state machine (`PENDING` → `APPROVED` → `EXECUTING` → `SUCCEEDED`/`FAILED`, plus terminal `REJECTED`/`CANCELLED`). Refund is the workflow object; `:execute` spawns `Payment(purpose=REFUND)` row for the gateway transaction. Separation of duties: `approved_by != requested_by`. Partial refunds = multiple Refund rows, not a status. `PaymentEvent` extended to polymorphic Payment/Refund audit. Active-payment unique constraint relaxed for `REFUND`/`ADJUSTMENT`. API §2.13 already aligned. | Legacy DB has zero refund tables/columns and no Blazor refund pages — refunds were issued manually outside the app, so no legacy constraint. Product-side domain model already declared a `Refund` entity; backend doc was the lagging side. Collapsing approval into `Payment.status` would conflate workflow state with money-movement state on one row and prevent enforcing requester ≠ approver. |
| 2026-05-12 | #6 | Drop `GET /checkouts/{id}` and `GET /checkouts` from the API spec. Add `purpose` filter to `GET /payments`. No new "settlement" model. | `VillaCheckoutDetail` was not a hospitality check-in/out record nor a gateway-payout reconciliation table — its columns and the sibling `CheckoutPaymentType` enum (`INITIAL_PAYMENT_DUE` / `RENTAL_BALANCE_PAYMENT` / `SECURITY_DEPOSIT`) show it was the 3-tier scheduled-payment ledger, already 1:1 covered by `payments.Payment(purpose=…)`. `/checkouts` was a legacy-name relic duplicating `/payments?purpose=…`. The live DB dump contains no `VillaCheckoutDetail` rows — only an unrelated stored procedure of similar name survives. Owner-side payouts and gateway-fee reconciliation are out of MVP scope. |
| 2026-05-12 | #7 | Keep all 11 Booking colon-verbs. Rename terminal state `COMPLETED` → `CHECKED_OUT` (and method `complete()` → `check_out()`); single backend method serves both the manual `:check-out` action and the auto-completion beat task. Add `Booking.modify_dates()` and `Booking.modify_guests()` as non-state-mutating audited methods that re-run the pricing engine and regenerate `pricing_snapshot`; both refused from `CHECKED_IN` and terminal states. Add `is_archived` + `archived_at` flag on `Booking` (orthogonal to `status`, distinct from soft-delete) backing `:archive` / `:restore`; drop `archived` from the status enum. Add idempotent `send_confirmation_email()` for `:resend-confirmation` (matches legacy "Resend Booking Summary" button). | Legacy has zero date-change audit (no `VillaBookingDateHistory` / `BookingChange*` table, `OnFromDateChange` overwrites in place) so the new audit + snapshot-regeneration behaviour is new design. Legacy lacks a manual check-out UI (date-driven only) — the new `:check-out` is an operator override that converges on the same backend method as the beat task. Legacy `VillaArchiveBooking` and `BookingInfo.razor`'s "Resend Booking Summary" button confirm archive and resend workflows exist. `BookingHold` reused for the re-availability check on date changes — no new model needed. |
| 2026-05-12 | #8 | Drop the `Tag` resource entirely. No `Tag` model, no `PropertyTag` junction. Remove `/tags`, `/properties/{id}/tags`, `/public/tags`. The legacy "Tags" admin page is a `VillaFeatures` CRUD view segmented by a `ServiceType` enum (`ContactService` / `PropertyFeature`) — there is no `Tags` table in the legacy schema. The new `Feature.service_type` TextChoices covers the discriminator with finer granularity, so `/features?service_type=…` reproduces the legacy admin surface. | Confirmed across `live-db-24-apr.sql`, `VillaDb.sql`, `DbScript.sql`: zero `Tags`/`VillaTags` CREATE TABLE matches and no FKs to such a table. `Tags.razor` (mounted at `/tags`) calls `ResService.ModifyFeatures` against `VillaFeatures` rows. The `Tag` stub in `01-domain-model.md` was a mis-citation ("Original `Tags`" pointed to a non-existent table). |
| 2026-05-12 | #9 | Adopt fixed `User.role` `StaffRole` TextChoices (`ADMIN` / `RESERVATIONS` / `ACCOUNTS` / `VIEWER`) backed by a Django `auth.Group` per value. No editable `Role` model. Trim API: drop `POST/PATCH/DELETE /roles`, `GET /roles/{id}`, and `GET /permissions`; keep `GET /roles` as a read-only enum listing for FE dropdowns. Reuse `GET /auth/permissions` for per-caller capability introspection. Legacy `UserMaster.IsSystemAdmin=1` → `ADMIN`; `0` → `RESERVATIONS` at migration. Distinct from `accounts.ContactRole` (the contact-to-property role; that's the real successor to legacy `VillaRoles` and untouched by this issue). | Legacy `UserMaster` has no staff-role concept beyond `IsSystemAdmin` bool; `.NET` code uses a single `IsAdmin` flag. Legacy `VillaRoles` (5 static rows: Owner / Agent / Villa Admin / Villa Manager / Management Co) is FK'd from `VillaContactMap`, not `UserMaster` — it's a *contact* role, already handled by `accounts.ContactRole`. Zero production demand for custom staff roles. Django Groups give us the escape hatch (swap enum for FK to wrap existing Groups if needed). |
| 2026-05-12 | #10 | Split. KEEP+MODEL the read/log surface (`GET /email-templates`, `GET /email-logs`, `GET /code-auth-logs`) — forensic essentials. DROP/DEFER template editing, `:preview`, `:test-send`, `:resend`, `/email-logs/bulk-resend` to v1.1. Templates ship as seed data; sends are service-layer calls. | Transactional comms are MVP-load-bearing; the editing CMS is not. Entities already declared in `01-domain-model.md` §8. Follow-up: comms app spec for v1.1. |
| 2026-05-12 | #11 | DROP. Channel-manager integration (Airbnb / Booking.com / VRBO inbound + outbound) is a discrete v1.x project. Remove `/properties/{id}/channel-mappings*`, OTA inbound webhooks, and the entire `/channel-sync/*` family. Keep `PropertyChannelMapping` / `ChannelSyncJob` as forward-looking entity stubs. | Backend has no service layer; folding into MVP dwarfs every other workstream. |
| 2026-05-12 | #12 | DEFER to v1.1. Remove `/feeds/properties/{id}/ical`, `/feeds/contacts/{id}/ical`, `:rotate-token`. No `FeedToken` entity, no MVP ops dependency. Revisit alongside channel-manager work. | Modest scope feature but not load-bearing day-1; better grouped with OTA calendar work. |
| 2026-05-12 | #13 | DROP. Remove `/payment-methods` and `/guests/{id}/payment-methods` endpoints. v1 captures cards per-transaction via gateway hosted fields. `PaymentInstrument` becomes a per-charge audit record; multi-method wallet revisits post-v1. | Already explicitly deferred by backend; no MVP ops need for a stored wallet. |
| 2026-05-12 | #14 | KEEP+MODEL. In-app notifications are operationally essential (owner approval signals, ops staff payment alerts). Entities `Notification` and `NotificationPreference` already declared in `01-domain-model.md` §11. API surface stands. | Backend service-layer spec (event-to-notification mapping) is a v1 follow-up, not a model gap. |
| 2026-05-12 | #15 | KEEP+MODEL, trimmed. `FeatureFlag` entity already declared. Collapse `/feature-flags/all` into `?all=true` on the main endpoint; keep `GET /feature-flags` and admin `PATCH /feature-flags/{key}`. | Internal infra, not customer-facing — minimal surface. |
| 2026-05-12 | #16 | KEEP+MODEL. Reports are MVP (owner statements, commissions, tax, refunds, enquiry-funnel). `Export`, `ReportRun`, `ScheduledReport` already declared in `01-domain-model.md` §10. Generic `/jobs/{id}` polling reused by exports and document generation (#18). | Backend follow-up: thin service-layer spec for S3 key convention and file expiry. |
| 2026-05-12 | #17 | DROP. Outbound webhook subscriptions are future scope. Internal integrations (Zoho push, WordPress fan-out) run as Celery jobs configured through `/system/integrations`, not customer-facing subscriptions. | Rewrote §1 webhook convention to remove `/webhook-subscriptions` reference. |
| 2026-05-12 | #18 | KEEP+MODEL. Confirmation/contract/voucher PDFs are MVP operational essentials. `BookingDocument` entity already declared in `01-domain-model.md` §4. API surface stands; async generation rides the `/jobs/{id}` surface from #16. | PDF rendering pipeline (WeasyPrint or similar) is implementation, not a model gap. |
| 2026-05-12 | #19 | KEEP+MODEL. Quotation PDF is operationally essential — quotations are sent to guests. Single endpoint, synchronous render from `Quotation` + `QuotationLine`. No new model. | **Superseded — see 2026-06-02 row.** |
| 2026-06-02 | #19 | **REVERSED → DROP.** Premise was false: legacy sends quotations as inline HTML email only (no PDF/attachment); `wkhtmltopdf` is used only for booking receipts (#18). Rebuild already matches legacy (HTML email + copy-to-Outlook). Quotation PDF is beyond-legacy overreach. Removed `/quotations/{id}/pdf` from §2.7. | Revisit post-v1 if a real requirement appears; `render_quotation_html` seam would back it. |
| 2026-05-12 | #20 | KEEP+MODEL. `AuditLog` entity already declared in `01-domain-model.md` §11 and is referenced by issues #4 and #7. `BookingEvent` / `PaymentEvent` stay as workflow-state audit; `AuditLog` is the generic cross-entity record. API surface stands. | Backend follow-up: service-layer helper `record_change(entity, before, after, actor, action)`. |
| 2026-05-12 | #21 | KEEP+MODEL minimal. Required by issue #1 resolution (WordPress fan-out config) and Zoho OAuth. Config-row identity is the `key`, backed by `SystemDefaults` + existing `ZohoSyncJob` / `SyncRecord` state — no new top-level `Integration` entity in v1. Promote post-v1 if needed. | §2.28 expanded with intent note. |
| 2026-05-12 | #22 | Closed (no action). `GuestPreference` was dropped backend-side and never exposed in the API. Verified `/guests/{id}/preferences` does not appear in §2.17. Re-add as a sub-resource if a real requirement appears post-v1. | Listed for completeness only. |
| 2026-05-12 | #23 | Standardise on `ACTIVE`. Drop `OFFLINE`. `Property.status ∈ {DRAFT, ACTIVE, ARCHIVED}` (3 values). API verbs become `:activate` / `:archive` / `:restore`; `:publish` / `:unpublish` removed. Legacy `live_offline` collapses to `ARCHIVED` — "temporarily not bookable" is `PropertySettings.availability_default = UNAVAILABLE` (separate axis). | Live DB `VillaStatus` seed: 4 rows (`live_online`, `live_offline`, `pending`, `archive`). Backend doc had drifted to 4 values; product-design said 3 — aligned to 3 with a `PropertySettings`-based path for the unbookable-but-published state. |
| 2026-05-12 | #24 | Add `WAIVED` as a terminal `Payment.status` for `DEPOSIT` / `BALANCE`. `:waive` (`PENDING\|PROCESSING → WAIVED`) fires `payment_waived` signal which advances the booking like `payment_succeeded`. `:mark-paid` (`PENDING → SUCCEEDED`) is the manual-receipt shortcut — sets `provider=MANUAL_BANK_TRANSFER` (or `OTHER`), `settled_at=paid_at`. Security-deposit `:mark-paid` advances the parent `SecurityDeposit` workflow (issue #25), not a `Payment` row; security track has no `:waive`. | Both API actions now have first-class backend transitions with `PaymentEvent` audit. Workflow stays consistent: the booking advances whether the receivable was paid, waived, or manually credited. |
| 2026-05-12 | #25 | Add `payments.SecurityDeposit` workflow model mirroring `Refund`. `kind ∈ {PRE_AUTH_HOLD, BT_REFUNDABLE}` discriminates the two operational paths. Pre-auth path: `AWAITING_DETAILS → PRE_AUTHED → {RELEASED, CAPTURED, EXPIRED}` with `:hold` / `:release` / `:claim`. BT path: `AWAITING_BT → HELD → {REFUNDED, PARTIALLY_REFUNDED}` with `:mark-paid` / `:release` (delegates to `Refund`) / `:claim` (delegates to `Refund` for the refund portion). `PaymentEvent` extended to 3-FK polymorphic (`payment` / `refund` / `security_deposit`). `Payment.UniqueConstraint(active per purpose)` narrowed to `DEPOSIT` / `BALANCE` only — SD spawns multiple `Payment` rows over its life. | Mirrors issue #5 (Refund) pattern: workflow row owns the state machine; `Payment` rows are the gateway-transaction ledger underneath. BT refunds route through `Refund` so separation-of-duties applies uniformly. `01-domain-model.md` had already declared a `SecurityDepositTrack` with the right enum; backend was the lagging side — same shape, renamed to `SecurityDeposit` for parallelism with `Refund`. |
| 2026-05-12 | #26 | Add `assigned_to` FK to `User` on both `Enquiry` and `Booking` (nullable, SET_NULL). Keep `agent` FK to `Contact` as the **external** intermediary; `assigned_to` is the **internal** staff owner. Two distinct concepts that had silently merged. Backs the `?assigned_to=` filter and `:assign` action. | Renaming the filter to `?agent=` would lose the distinction between "travel agent acting for the guest" (external) and "Canary staff member who owns this work" (internal). Legacy data has both concepts. |
| 2026-05-12 | #27 | Add `reservations.EnquiryEvent` mirroring `BookingEvent`. Same shape: `(enquiry, from_status, to_status, kind, actor, source, reason, meta)`. `kind` TextChoices (`STATUS_CHANGE`, `ASSIGNED`, `UNASSIGNED`, `CONTACTED`, `QUOTE_SENT`, `CONVERTED`, `LOST`, `REOPENED`, `NOTE_ADDED`). `NOTE_ADDED` emitted by `EnquiryNote.post_save` signal; all other kinds written by `Enquiry` transition methods inside `transaction.atomic`. | Consistent with issue #20: domain-specific event tables for hot timelines (`BookingEvent`, `PaymentEvent`, `EnquiryEvent`); generic `AuditLog` for everything else. `/enquiries/{id}/activity` reads from `EnquiryEvent`. |
| 2026-05-12 | #28 | Adopt the normalised `properties.PropertyDescription(property, section, body)` child table with `UniqueConstraint(property, section)`. Section TextChoices fixed at `OVERVIEW` / `HOUSE_RULES` / `VILLA_INFO` / `FURTHER_INFO`. Drop flat columns `Property.overview` / `house_rules` / `feature_description` / `room_description` / `notes`. Migration: `WebsiteDescription` → `OVERVIEW`; `HouseRules` → `HOUSE_RULES`; `FeatureDescription` + `RoomDescription` concatenated → `VILLA_INFO`; legacy "Further information" Blazor textarea → `FURTHER_INFO` if content survives. API gains `DELETE /properties/{id}/descriptions/{section}`. | `01-domain-model.md` already declared `PropertyDescription` as a sub-resource; backend `02-properties.md` was the lagging side. The legacy two-column split (`FeatureDescription` + `RoomDescription`) was a UX artefact, not a semantic distinction — collapsed to one `VILLA_INFO` row. |
| 2026-05-13 | #30 | EXPOSE. Add nested `GET/POST /properties/{id}/change-over-rules`, `GET/PATCH/DELETE /change-over-rules/{id}`. Per-property bounded weekday set used by `AvailabilityService.is_available()` and `BookingHold.clean()`; operators need CRUD to publish/retire allowed check-in weekdays. Zero rows = any day allowed. | Distinct from `PropertySettings.changeover_day` (single fallback day) and `RateCard.changeover_weekday` (per-card override) — `ChangeOverRule` is the date-bounded multi-weekday set. |
| 2026-05-13 | #32 | EXPOSE. Add `GET/POST /discounts` with filters (`?property=`, `?card=`, `?rule_kind=`, `?code=`, `?is_active=`), `GET/PATCH/DELETE /discounts/{id}`, nested `GET/POST /rate-cards/{id}/discounts` and `GET/POST /properties/{id}/discounts` (for property-wide promo codes where `card` is null), and unauthenticated `POST /discounts:lookup-code` (used by the quote / quotation acceptance UI to validate a promo code without leaking the catalogue). | Promo-code lookup is essential to the booking workflow per #2's `Discount` reshape. Property-wide promo codes need a path that scopes the FK correctly (`card=null`, `property=…`). |
| 2026-05-13 | #33 | EXPOSE read+publish. Add `GET/POST /terms-versions`, `GET /terms-versions/{version}`, `POST /terms-versions/{version}:publish` (atomic — flips `is_current=True` on this row and `False` on the previous current row inside `transaction.atomic`), `GET /terms-versions/current` (resolver used by quotation/booking creation). No `PATCH`/`DELETE` — legal copy is append-only; correcting a published version means publishing a new one. `Quotation.terms_version` and `Booking.terms_version` snapshot the current version at creation, so old versions stay queryable. | Operators need to author and roll out new T&Cs without engineering. Append-only because legal precedent on what was accepted at booking time must not be silently rewritten. |
| 2026-05-13 | #34 | DROP. Legacy `VillaConciergeServices` held exactly 2 rows ("Quintessential", "Signature") — operator-facing tier labels, not a configurable catalogue. Retire the `reservations.ConciergeService` model entirely. Replace with `ConciergeTier` TextChoices (`QUINTESSENTIAL`, `SIGNATURE`) on `BookingConciergeItem`. Per-item `name`, `description`, `unit_price`, `unit`, `currency` move directly onto `BookingConciergeItem` (it was already snapshotting price; the new fields are first-class). No `/concierge-services` API endpoint. | A 2-row lookup table doesn't earn its keep — TextChoices give the same dropdown UX without an extra CRUD surface, and the legacy free-text-on-the-line-item shape was always how concierge items varied in practice. |
| 2026-05-13 | #35 | EMBED read-only. Keep `properties.NearbyPlaceType` model (small curated taxonomy: airport, beach, restaurant, station, etc.; FK from `PropertyNearbyPlace`). Expose `GET /nearby-place-types` (read-only list, used by the FE to populate the type dropdown when adding a POI to a property). No `POST`/`PATCH`/`DELETE` in v1; seeded via data migration. Per-property POIs remain at the existing `/properties/{id}/nearby` endpoint. | A new "place type" is rare and operator-driven type expansion isn't in MVP. If real demand surfaces, promote to full CRUD. |
| 2026-05-13 | #36 | COLLAPSE. Fold `Commission` / `TaxPolicy` / `BankAccount` / `PaymentSchedule` / `SecurityDepositPolicy` into a flat `PropertyFinance` model with all their fields as nullable columns directly on the parent (null = inherit from group). Same for `GroupFinance` (replaces the 5 `Group*` siblings — non-nullable with defaults, the inheritance floor). The "separate permissions per child" rationale doesn't apply — MVP staff roles (`ADMIN` / `RESERVATIONS` / `ACCOUNTS` / `VIEWER` per #9) gate the whole finance form, not individual sub-concerns; and the in-house Canary permission framework that motivated child-level grants doesn't exist here. The `effective_*()` resolvers stay (they now look at fields on the flat parent instead of nested children). Bank-account fields are still tagged for redaction in `AuditLog` per `03-finance-config.md`. The API stays flat `/properties/{id}/finance` and `/property-groups/{id}/finance` (issue #38). | KISS: 6 models become 2 (one property, one group). One admin form, one serializer, one set of `null` resolvers — no five-way join, no fanned-out OneToOne migrations. If granular permissions ever land post-v1, splitting back out is a refactor, not a re-architecture. |
| 2026-05-13 | #37 | EXPOSE group settings. Add `GET/PATCH /property-groups/{id}/settings` mirroring `/properties/{id}/settings`. `GroupSettings` is the inheritance floor (non-nullable defaults) that property-level null fields fall back to. Without an operator-facing surface for the floor, the property-level `null = inherit` semantics are inert. | Same shape, same fields as `/properties/{id}/settings` — only the FK target changes. |
| 2026-05-13 | #38 | EXPOSE group config children. Add `GET/PATCH /property-groups/{id}/finance` (using the flattened `GroupFinance` from #36) and `GET/PATCH /property-groups/{id}/settings` (from #37). No `POST`/`DELETE` — the rows are created automatically with the `PropertyGroup` (`post_save` signal) and live for the group's lifetime. `/property-groups` CRUD itself is already exposed (§2.3). | Mirrors the property finance/settings surface one level up. Group is the inheritance floor; exposing it makes the operator-visible model coherent. |
| 2026-05-12 | #29 | Keep `PUT /properties/{id}/collections` as the full-set replace verb, but change the body shape from `[<collection_id>, ...]` to `[{collection: <slug-or-id>, sort_order, featured_until, description}, ...]` — through-fields are carried explicitly so the replace doesn't silently zero them. Add singular non-destructive paths: `POST /properties/{id}/collections`, `PATCH /properties/{id}/collections/{collection}`, `DELETE /properties/{id}/collections/{collection}`. Mirror semantics on `/collections/{slug}/properties`. | `CollectionMembership` is an explicit through model with curation metadata; a bare-id PUT would silently lose `sort_order`, `featured_until`, and the per-membership `description` on every replace. Object-shape PUT preserves them; singular paths support fine-grained edits without round-tripping the whole set. |
| 2026-05-13 | #39 | Generic `core.IdempotencyRecord` + `core.middleware.IdempotencyMiddleware` covering all unsafe POSTs. Drop the `idempotency_key` columns from `Payment`, `Refund`, `SecurityDeposit`. Endpoint-policy-driven (`idempotency_required = True` on payment/booking/refund creation; opt-in elsewhere). Hash-mismatch → `409 Conflict`. Nightly cleanup beat task. | Dedupe belongs at the API boundary, not per-model. One mechanism covers everything. The off-the-shelf `django-idempotency-key` package only covers a subset of the desired semantics, so a thin in-house middleware over `IdempotencyRecord` is the pragmatic shape; revisit if a maintained library catches up. |
| 2026-05-13 | #40 | S3 via `django-storages` (`S3Boto3Storage`); MinIO container in local dev. Two-step signed-URL upload (`POST /uploads:sign` → client `PUT` → `POST /properties/{id}/images`) backed by `core.UploadTicket(user, path, key, content_type, max_bytes, expires_at, consumed_at)`. `PropertyImage.image` keeps `ImageField(upload_to=…)`; only the storage backend changes. Small files (<5 MB) still allowed via direct `POST /uploads` streaming. | Off-the-shelf. Sidesteps streaming uploads through Django, decouples upload latency from API responsiveness, and avoids the single-server bottleneck of local-disk storage. |
| 2026-05-13 | #41 | Default Django DB-backed sessions + thin `accounts.services.SessionService`. Add `accounts.UserSession(user, session_key, last_seen_at, ua, ip)` as a denormalised index written on the login signal so `GET /auth/sessions` is an indexed query rather than a full session-table decode. `SessionService.revoke()` hits both `django_session` and `UserSession` in `transaction.atomic`. Daily cleanup beat task for revoked rows. | No new session model needed — Django's built-in store is already queryable. The denorm index is the smallest viable addition for listing performance; revocation correctness lives in the service layer, not the model. |
| 2026-05-13 | #42 | Add `integrations.OAuthCredential(provider, access_token, refresh_token, expires_at, scope, account_id, connected_by, connected_at, disconnected_at, is_active, meta)` with Fernet encryption of tokens at rest. Add `OAuthService.begin / complete / disconnect / get_access_token` orchestrating `/zoho:connect` / `:disconnect`. `ZohoSyncClient` reads the active credential on every call; inline-refresh near expiry; `refresh_oauth_tokens` Celery beat task pre-emptively refreshes hourly. Single active credential per provider via partial unique constraint. Provider-agnostic so future OAuth integrations add an enum value, not a table. | Off-the-shelf — same Fernet-encryption pattern used elsewhere; no new framework. Generic from the start because the second OAuth integration (Mailchimp/HubSpot/etc.) is cheaper to anticipate than to refactor for. |
| 2026-05-13 | #43 | TOTP via `pyotp`. SMS deferred (enum value reserved on `User.tfa_method`, not exposed in the API in MVP). Add `User.tfa_enrolled_at` and hashed `tfa_recovery_codes` JSONField. `accounts.services.TwoFactorService.enroll / confirm_enrollment / challenge / verify / disable` backs the API. 30-sec step, 6-digit codes, SHA-1, ±1 step drift on verify; 5 fails / 5 min → 15-min lockout. | `pyotp` is the industry-standard library — RFC 6238 compliant, zero Django coupling, well-tested. Deferring SMS keeps MVP focused: no Twilio integration, no second factor of fragility. The enum value is reserved so the future addition is a feature, not a column migration. |
| 2026-05-13 | #44 | Keep all three endpoints. Document boundaries inline: `/availability:search` = availability-only (no prices); `/pricing:quote-bulk` = **stateless** priced N-tuple computation (no quotation written, used by FE comparison cards); `/quotations:search-villas` = **stateful** operator-facing villa shortlist that creates/updates `QuotationLine` candidates on a given Quotation draft. | They are three distinct use cases. Consolidating to one endpoint would either force the unauthenticated public quote calculator to write `Quotation` state (privacy + churn issue), or force the operator villa-search to manage state externally (UX regression). Names already disambiguate; only the docs were under-clear. |
| 2026-05-13 | #45 | Drop `Booking.deposit_amount` and `Booking.deposit_percentage` columns. Deposit *requirement* is computed at booking-creation time from `PropertyFinance.deposit_*` (config); deposit *track* lives on the `Payment(purpose=DEPOSIT)` row created by `PaymentScheduler.create_for_booking()`; the figure-at-confirmation is also embedded in the immutable `Booking.pricing_snapshot`. API consumers read deposit state from `GET /bookings/{id}/deposit` (§2.10) or `GET /payments?booking=…&purpose=DEPOSIT`. | The legacy `VillaBooking.DepositAmount` / `DepositPercentage` columns were a denormalisation that drifted out of sync with the actual payment row in practice. Single source of truth: config on `PropertyFinance`, workflow on `Payment(purpose=DEPOSIT)`, frozen value on `pricing_snapshot`. No column on `Booking` itself. |
