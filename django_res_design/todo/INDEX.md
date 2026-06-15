# Todo Index

Live status of every ticket. **Open work is at the top; resolved and
dropped tickets are listed at the bottom and their files live in
[`done/`](done/)** (each carries a top-of-file `✅ RESOLVED` / `❌ DROPPED`
banner with the problem, fix, and commit). See `README.md` for conventions
and `CRITIQUE-2026-05-27.md` for the review that drove the status changes.

Status icons:
- ⬜ open (default)
- 🟨 partial — code complete, follow-up work remains
- ✏️ needs revision before implementing (premise partly answered / re-scope)

Scoreboard (2026-06-15): **54 done** (51 resolved + 3 dropped), **45 open**
(incl. ✏️ revise and 🟨 partial). Resolved files moved to `done/`. (Six
GAP tickets — 010, 015–019 — were absent from the old index and are now
listed.)

---

# Open / actionable

## 🔴 Bugs

| Id | Title | Status |
|---|---|---|
| [BUG-008](bug-008-securitydeposit-damageclaim-fk.md) | `SecurityDeposit.damage_claim_id` is a fake FK | ⬜ decision-blocked (DamageClaim in v1?) |
| [BUG-009](bug-009-price-basis-ignored-by-engine.md) | Engine ignores `RatePlan.price_basis` — GROSS plans mis-priced | ⬜ spec done; code deferred to finance rewrite |

## 🟠 Footguns

| Id | Title | Status |
|---|---|---|
| [FG-002](fg-002-effective-null-vs-empty-string.md) | `effective()` conflates `""` and `NULL` | ⬜ consider downgrade to smell |
| [FG-005](fg-005-idempotency-user-required.md) | `IdempotencyRecord.user` required; system actors blocked | ✏️ resolve dead-vs-live status first |
| [FG-009](fg-009-csrf-prime-coupled-to-shell-server.md) | CSRF priming coupled to HTML-shell server — recurring dev double-login | ⬜ low priority |

## 🟡 Smells

| Id | Title | Status |
|---|---|---|
| [SMELL-001](smell-001-archived-vs-status.md) | `archived_at` is a second status | ⬜ |
| [SMELL-008](smell-008-service-layer-contract-single-island.md) | Service-layer contract (perms / `log_operation` / idempotency) lives in one file | ⬜ |
| [SMELL-009](smell-009-duplicate-implemented-three-ways.md) | "Duplicate" implemented three ways; no clone endpoint is idempotent | ⬜ |
| [SMELL-010](smell-010-error-signalling-forks.md) | Three coexisting error-signalling patterns in the service layer | ⬜ |
| [SMELL-011](smell-011-bare-querysets-missing-query-pins.md) | Bare `.objects.all()` querysets; `accounts`/`pricing` lack query pins | ⬜ |
| [SMELL-012](smell-012-module-structure-drift.md) | Module-structure drift: filters / services / routers / views-in-urls | ⬜ |
| [SMELL-013](smell-013-one-model-per-file-doc-drift.md) | "One model per file" rule is fiction; de-facto rule is one aggregate per file | ⬜ doc-only |
| [SMELL-014](smell-014-quotation-synthesised-row-guard-structural.md) | Synthesised `booking-` quotation rows: make the exclusion structural | ⬜ |

## Surface gaps

| Id | Title | Status |
|---|---|---|
| [GAP-005](gap-005-quotation-flow-parity.md) | Enquiry→Quotation flow parity vs legacy + spine UX overhaul | ⬜ tracker |
| [GAP-010](gap-010-quote-enquiry-analyzed-wrong-codebase.md) | Quote/enquiry specs analysed against the wrong (post-deletion) codebase | ⬜ tracker / corrected reference |
| [GAP-011](gap-011-ical-feed-ingest.md) | iCal feed ingest from owners | ⬜ deferred (v2 tracker) |
| [GAP-012](gap-012-s3-image-hosting.md) | S3 image hosting for staging & prod (+ legacy binary import) | 🟨 code complete; remaining: ops prereqs + run the cutover runbook |
| [GAP-013](gap-013-quote-builder-ux-feedback-loops.md) | Quote builder UX: tighten feedback loops (invalid-line flag, remove-undo, unpriceable note, a11y) | ⬜ FE polish, sibling of GAP-005 |
| [GAP-015](gap-015-modify-resync-payment-schedule.md) | `modify_dates`/`modify_guests` don't resync the payment schedule | ⬜ |
| [GAP-016](gap-016-rental-price-override.md) | Rental-price override (legacy parity remainder) | ⬜ |
| [GAP-017](gap-017-legacy-villabookingdetails-loader.md) | Data-migration loader for legacy `VillaBookingDetails` | ⬜ |
| [GAP-018](gap-018-comms-charge-itemisation.md) | Itemise charge lines in guest-facing comms | ⬜ |
| [GAP-019](gap-019-security-deposit-calculate-from.md) | SD sizing ignores `calculate_from`; no resync on charges | ⬜ |
| [GAP-020](gap-020-direct-booking-creation.md) | Direct booking creation (legacy "book now") — synthetic-quotation design | ⬜ design ready; implementation deferred |
| [GAP-021](gap-021-audit-history-ui.md) | Per-entity "History" tab in the SPA (audit-log surface) | ⬜ blocked by Q-014 exposure decision |
| [GAP-022](gap-022-per-property-feature-ordering.md) | Per-property feature display ordering dropped vs legacy (`MappingOrder`) | ⬜ rescoped (non-destructive migration + loader rewrite + serializer + tab rewrite + FG-017 audit registration); add-property-flow cluster |
| [GAP-023](gap-023-owner-approval-preview-lifecycle.md) | `live_offline` replacement: `owner_approved_at` + draft preview link + badges | ⬜ deferred per 2026-06-11 owner decision (no approval gating in v1) |
| [GAP-024](gap-024-incremental-loading-required-fields.md) | FE required-field posture fights incremental loading — relax room/capacity write schemas | ⬜ premise corrected (FE text fields already lax; real divergence is the beds field); decide jointly with Q-019 |
| [GAP-025](gap-025-changeover-aware-rate-band-dates.md) | Changeover-aware rate-band end-date suggestion (Sat→Fri auto-fill) | ⬜ add-property-flow cluster (customer-confirmed) |
| [GAP-026](gap-026-currency-display-money-fields.md) | Show property currency beside money fields | ⬜ backend no-mixing enforcement DROPPED (contradicts GAP-014); scope is FE adornment + soft warning; groups stay |
| [GAP-027](gap-027-inline-contact-creation-primary-convention.md) | Inline contact creation from the property + per-role primary convention | ⬜ inline-create already wired; real fix is picker auto-select + convention doc; required-field divergence spun out to GAP-029 |
| [GAP-028](gap-028-admin-integrations-surface.md) | Admin `/system/integrations`: `OAuthCredential` CRUD + `SyncRun`/`SyncIssue` lists | ⬜ |
| [GAP-029](gap-029-contact-required-name-fields-divergence.md) | Contact `first_name`/`last_name` FE/BE required-field divergence | ⬜ |

## Open product questions

| Id | Title | Status |
|---|---|---|
| [Q-001](q-001-cancellation-policy-thresholds.md) | Cancellation policy thresholds | ✏️ partial — re-scope to "bands in v1?" |
| [Q-002](q-002-owner-pre-approval-sla.md) | Owner pre-approval SLA | ✏️ partial — 24h escalate task built; window not configurable, auto-approve TBD |
| [Q-005](q-005-currency-display-base.md) | Reports base currency + FX source | ⬜ blocks every report |
| [Q-006](q-006-owner-statement-scheduling.md) | Owner statement cadence + delivery | ⬜ no code yet |
| [Q-007](q-007-concierge-supplier-directory.md) | Concierge supplier directory shape | ⬜ |
| [Q-008](q-008-2fa-enforcement.md) | 2FA enforcement scope | ⬜ |
| [Q-010](q-010-guest-data-retention.md) | Guest data retention / GDPR | ⬜ |
| [Q-014](q-014-audit-log-retention.md) | Audit log retention window | ✏️ recommendation recorded (keep-forever + BUG-012 scrub); exposure half blocks GAP-021 |
| [Q-017](q-017-comms-direction-signals-vs-spine-position.md) | comms: signals-only sink, or move it down the spine? | ⬜ |
| [Q-018](q-018-rate-reduction-vs-carryover.md) | Rate reductions: base price + reduction so carry-over copies the base | ⬜ Q1 answered (both % and fixed reductions, specific weeks) |
| [Q-019](q-019-structured-room-attributes.md) | Structured room attributes (bath/shower, aircon, views, accessibility, floor) | ⬜ decided jointly with GAP-024 |
| [Q-020](q-020-description-sections-parity.md) | Description sections: spec enum vs sections actually written | ⬜ |
| [Q-021](q-021-defaults-and-feature-taxonomy.md) | Seed group defaults + curate feature taxonomy | ⬜ groups stay (owner removal deemed premature); coordinate seed list with GAP-022 |
| [Q-022](q-022-seasons-defined-by-rates.md) | Seasons defined by rental rates not services | ⬜ |

## Decisions blocking implementation

Highest-leverage unanswered questions (each blocks a slice of downstream work):

- **Q-005** — Reports base currency + FX source (blocks every report)
- **Q-006** — Owner statement cadence + delivery (no code exists yet)
- **BUG-008** — `DamageClaim` in v1? (scope call; blocks the SD damage slice)
- **Q-014 exposure** — blocks **GAP-021** (audit History tab)

---

# Resolved & dropped

Files live in [`done/`](done/); each has a top-of-file banner with the
problem, fix, and commit. Listed here for traceability.

## ✅ Resolved

| Id | Title |
|---|---|
| [BUG-001](done/bug-001-cancelled-status-requires-cancelled-at.md) | `CANCELLED` ↔ `cancelled_at IS NOT NULL` constraint |
| [BUG-002](done/bug-002-raterule-zero-length-range.md) | `RateRule` zero-length date ranges |
| [BUG-003](done/bug-003-raterule-poa-vs-price-contradiction.md) | `RateRule` `is_poa` vs numeric price mutex |
| [BUG-004](done/bug-004-owner-approval-race.md) | Owner-approval race |
| [BUG-005](done/bug-005-stale-bookinghold-blocks-bookings.md) | Stale `BookingHold` rows block valid bookings |
| [BUG-006](done/bug-006-payment-active-purpose-uniqueness.md) | `unique_active_payment_per_purpose` only covered DEPOSIT/BALANCE |
| [BUG-007](done/bug-007-reference-generation-races.md) | Reference generation races + `bulk_create` bypass |
| [BUG-010](done/bug-010-refund-self-approve-constraint-conflict.md) | Refund self-approve vs SoD constraint → 500 |
| [BUG-011](done/bug-011-security-deposit-bare-valueerror-500s.md) | SD service bare `ValueError` → 500s; no logging |
| [BUG-012](done/bug-012-auditlog-retains-pii-after-anonymize.md) | `AuditLog` retains cleartext PII after anonymize/merge |
| [FG-001](done/fg-001-booking-quotation-currency-drift.md) | Booking ↔ quotation-line currency drift |
| [FG-004](done/fg-004-payment-purpose-field-coherence.md) | Payment fields not gated by `purpose` |
| [FG-006](done/fg-006-modify-without-select-for-update.md) | `modify_dates`/`modify_guests` re-price without row locks |
| [FG-007](done/fg-007-syncrecord-genericfk-dangling.md) | `SyncRecord` GenericFK dangling rows |
| [FG-008](done/fg-008-property-timezone.md) | Property has no timezone |
| [FG-010](done/fg-010-idempotency-races-no-db-backstop.md) | Idempotency check-then-create, no DB backstop |
| [FG-011](done/fg-011-adjustment-recompute-skips-bulk-paths.md) | `Booking.adjustment` recompute skips bulk paths |
| [FG-012](done/fg-012-track-payments-view-bypasses-ledger.md) | Track-payments POST mints ledger rows from `request.data` |
| [FG-013](done/fg-013-owners-app-outside-layers-contract.md) | `owners` app outside the import-linter contract |
| [FG-014](done/fg-014-audit-tracking-gaps.md) | Audit-tracking gaps: SecurityDeposit, Enquiry, Quotation |
| [FG-015](done/fg-015-booking-cancel-leaves-pending-payments.md) | `Booking.cancel` leaves PENDING Payment rows live |
| [FG-016](done/fg-016-audit-signals-skip-bulk-writes.md) | Audit signals skip bulk writes; merge FK rewrites unaudited |
| [FG-017](done/fg-017-audit-coverage-second-tier.md) | Audit-coverage second tier: BookingHold, Property + children |
| [GAP-001](done/gap-001-comms-empty-url-surface.md) | `comms/urls.py` empty (EmailLog list+detail) |
| [GAP-002](done/gap-002-integrations-empty-url-surface.md) | `integrations/urls.py` empty — slice 1 (rest re-ticketed) |
| [GAP-004](done/gap-004-frontend-coming-soon-tabs.md) | Frontend "Coming Soon" tabs (stale) |
| [GAP-006](done/gap-006-legacy-reference-format-parity.md) | Legacy reference format parity (`VC`/`QVC`) |
| [GAP-007](done/gap-007-changeover-autoshift-parity.md) | Changeover auto-shift parity |
| [GAP-008](done/gap-008-no-rate-night-fallback-parity.md) | No-rate-night fallback parity (`fallback_nightly`) |
| [GAP-009](done/gap-009-discount-loose-ends.md) | Discount loose ends |
| [GAP-014](done/gap-014-quote-currency-forced-selection.md) | Quote builder forced currency → per-line currency |
| [INV-001](done/inv-001-propertycontactassignment-owner-uniqueness.md) | `PropertyContactAssignment` owner uniqueness |
| [INV-002](done/inv-002-raterule-priority-tiebreak.md) | `RateRule.priority` tie-break |
| [INV-003](done/inv-003-refund-amount-sign-convention.md) | `Refund.amount` sign convention |
| [INV-004](done/inv-004-syncrun-syncissue-retry.md) | `SyncRun`/`SyncIssue` failure handling |
| [INV-005](done/inv-005-legacy-id-indexing-consistency.md) | `legacy_id` indexing consistency |
| [Q-003](done/q-003-channel-sync-scope.md) | Channel sync scope → out of v1 |
| [Q-004](done/q-004-hold-expiry-default.md) | Hold expiry default (shape) |
| [Q-009](done/q-009-multi-site-inventory-sharing.md) | Multi-site inventory sharing → single site v1 |
| [Q-011](done/q-011-email-template-inheritance.md) | Email template inheritance → system → site |
| [Q-013](done/q-013-rate-card-incomplete-pricing.md) | Rate-card incomplete pricing → flag + manual quote |
| [Q-015](done/q-015-owner-financial-visibility.md) | Owner financial visibility defaults |
| [Q-016](done/q-016-payment-ledger-vs-dedicated-models.md) | Payment ledger vs dedicated SD → Lane A |
| [SMELL-002](done/smell-002-quotation-expire-draft.md) | `Quotation.expire()` only handled SENT→EXPIRED |
| [SMELL-003](done/smell-003-currency-decimal-places-unenforced.md) | `Currency.decimal_places` informational only |
| [SMELL-004](done/smell-004-emaillog-content-hash-scope.md) | `EmailLog` content-hash dedupe scope |
| [SMELL-006](done/smell-006-terms-accepted-at-required-no-default.md) | `terms_accepted_at` required, no default |
| [SMELL-007](done/smell-007-occupancy-fallback-doc-claim.md) | Spec misstates legacy occupancy fallback (doc) |
| [SMELL-015](done/smell-015-comms-smtp-no-transient-retry.md) | Email marks FAILED on any SMTP error |
| [SMELL-016](done/smell-016-audit-actor-threadlocal-not-asgi-safe.md) | Audit actor on `threading.local` (ASGI-unsafe) |
| [SMELL-017](done/smell-017-cart-naming-vs-shortlist-copy.md) | Quote-builder code said "cart" |

Also resolved outside this list: **Q-012** (payment gateway → Flywire).

## ❌ Dropped

| Id | Title | Reason |
|---|---|---|
| [FG-003](done/fg-003-effective-crashes-on-null-group.md) | `effective()` crashes on null `property.group` | `Property.group` is non-nullable |
| [GAP-003](done/gap-003-endpoint-coverage-gap.md) | Endpoint coverage gap | framing only |
| [SMELL-005](done/smell-005-residual-property-country-charfield.md) | Residual `Property.country` free-text | verified clean |
