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

Scoreboard (2026-06-18): **62 done** (58 resolved + 4 dropped), **61 open**
(incl. ✏️ revise and 🟨 partial). Resolved files moved to `done/`. (GAP-030–037
are the availability/commission/region/services cluster; GAP-038–044 are the
enquiry/quote/customer-profile cluster from the 2026-06-17 owner Loom.)

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
| [SMELL-018](done/smell-018-owner-probe-403-as-control-flow.md) | Boot-time owner probe uses a 403 as control flow — console-error noise every staff session | ✅ resolved (2026-06-20) — `OwnerMeView` → `IsAuthenticated`, returns `200 {is_owner:false}` for non-owners; SPA branches on `me.is_owner` (schema `z.literal(true)`→`z.boolean()`), 403→retryable error. Owner data endpoints keep `IsOwner`; staff boot logs zero console 403s. Commits `d71cba5`+`89d6e9f` |

## Surface gaps

| Id | Title | Status |
|---|---|---|
| [GAP-005](gap-005-quotation-flow-parity.md) | Enquiry→Quotation flow parity vs legacy + spine UX overhaul | ⬜ tracker |
| [GAP-010](gap-010-quote-enquiry-analyzed-wrong-codebase.md) | Quote/enquiry specs analysed against the wrong (post-deletion) codebase | ⬜ tracker / corrected reference |
| [GAP-011](gap-011-ical-feed-ingest.md) | iCal feed ingest from owners | 🟨 partial — ingest engine + feed model shipped; residual = staff-awareness UI + sales indicator (GAP-034) |
| [GAP-012](gap-012-s3-image-hosting.md) | S3 image hosting for staging & prod (+ legacy binary import) | 🟨 code complete; remaining: ops prereqs + run the cutover runbook |
| [GAP-013](gap-013-quote-builder-ux-feedback-loops.md) | Quote builder UX: tighten feedback loops (invalid-line flag, remove-undo, unpriceable note, a11y) | ⬜ FE polish, sibling of GAP-005 |
| [GAP-017](gap-017-legacy-villabookingdetails-loader.md) | Data-migration loader for legacy `VillaBookingDetails` | ⬜ |
| [GAP-018](gap-018-comms-charge-itemisation.md) | Itemise charge lines in guest-facing comms | ⬜ |
| [GAP-020](gap-020-direct-booking-creation.md) | Direct booking creation (legacy "book now") — synthetic-quotation design | ⬜ design ready; implementation deferred |
| [GAP-021](gap-021-audit-history-ui.md) | Per-entity "History" tab in the SPA (audit-log surface) | ⬜ blocked by Q-014 exposure decision |
| [GAP-022](done/gap-022-per-property-feature-ordering.md) | Per-property feature display ordering dropped vs legacy (`MappingOrder`) | ✅ resolved (2026-06-18) — `PropertyFeature` through model w/ `sort_order` (non-destructive migration + FG-017 audit), ordered-`feature_ids` diff-write serializer, `MIN(MappingOrder)` loader, flat drag-drop FeaturesTab |
| [GAP-023](gap-023-owner-approval-preview-lifecycle.md) | `live_offline` replacement: `owner_approved_at` + draft preview link + badges | ⬜ deferred per 2026-06-11 owner decision (no approval gating in v1) |
| [GAP-024](done/gap-024-incremental-loading-required-fields.md) | FE required-field posture fights incremental loading — relax room/capacity write schemas | ✅ `beds` relaxed to optional (matches `required=False` serializer); broader room-attribute posture stays open under Q-019 |
| [GAP-025](done/gap-025-changeover-aware-rate-band-dates.md) | Changeover-aware rate-band end-date suggestion (Sat→Fri auto-fill) | ✅ resolved (2026-06-18) — `suggestRateBandEnd` helper + `RateRuleFormDialog` auto-fill |
| [GAP-026](done/gap-026-currency-display-money-fields.md) | Show property currency beside money fields | ✅ FE adornment + soft mismatch warning; PropertySettings exposes read-only group-resolved `currency_code`; multi-currency intentional (2026-06-18) |
| [GAP-027](done/gap-027-inline-contact-creation-primary-convention.md) | Inline contact creation from the property + per-role primary convention | ✅ resolved (2026-06-18) — picker auto-select via `initialContact` + per-role-primary convention documented |
| [GAP-028](gap-028-admin-integrations-surface.md) | Admin `/system/integrations`: `OAuthCredential` CRUD + `SyncRun`/`SyncIssue` lists | ⬜ |
| [GAP-029](gap-029-contact-required-name-fields-divergence.md) | Contact `first_name`/`last_name` FE/BE required-field divergence | ⏸️ deferred — blocked on GAP-045/046 (Person/Organisation); kept open. **Live bug:** company-only contact 400s until they land |
| [GAP-030](done/gap-030-weekly-pricing-in-availability-timeline.md) | Weekly pricing in the sales availability timeline (price-by-week, changeover visible) | ✅ resolved (2026-06-18) — `StayOptionsService.weekly_prices()` + `GET /availability/weekly-prices` price each changeover week (context reused, no per-week reload), Q-013/POA/projected flags, never 500; FE price strip aligned under the bands with changeover weekday, guide/POA markers, separate non-blocking query; en+el; pytest+vitest. Fixed-changeover only; variable/sub-week deferred (GAP-025/Q-022) |
| [GAP-031](done/gap-031-availability-timeline-month-context-header.md) | Month context above the availability timeline date range | ✅ resolved (2026-06-18) — `monthSpanLabel` helper renders spanning month(s)+year above the date range (single/cross-month/cross-year), date-fns locale text + i18n dash join (en+el), vitest all three cases; FE-only |
| [GAP-032](done/gap-032-click-drag-availability-block-creation.md) | Click-and-drag availability block creation | ✅ resolved (2026-06-18) — press-drag-release on the villa month grid opens the create dialog pre-filled; `resolveDragRange` helper truncates before occupied days (half-open), pointer-delegation keeps dropdowns/links working, role-gated; vitest range-mapping + grid-drag; FE-only |
| [GAP-033](gap-033-availability-last-confirmed-timestamp.md) | Availability "last confirmed" timestamp + manual confirm button | ⬜ legacy parity; resets on owner-availability events only, not VC churn |
| [GAP-034](done/gap-034-availability-calendar-source-indicator.md) | Sales-view calendar-source indicator: iCal badge + owner calendar link | ✅ resolved (2026-06-21) — `has_active_ical_feed` (N+1-safe `Exists`) + `calendar_url` on property list/detail via a shared serializer mixin (secret feed `url` never serialized); `calendar_url` on `PropertySettings` (migr. `0020`, editable in the Settings tab, server-validated URL); shared `CalendarSourceIndicator` renders badge-wins-over-link in the timeline + AvailabilityTab; en+el; pytest+vitest. Feed-health tooltip + `GroupSettings`/back-office mgmt deferred |
| [GAP-035](gap-035-net-gross-commission-derivation.md) | Net↔gross rate entry with automatic commission derivation | ⬜ entry-time tool; x-ref BUG-009 single-source-of-truth |
| [GAP-036](done/gap-036-region-filter-property-listing.md) | Region filter on the property listing grid (status filter already exists) | ✅ resolved (2026-06-19) — Region `<Select>` added to the list filter row (country → region → status); slug-valued options (mirrors AvailabilityTimelinePage), URL `region` param read into the list query, en+el i18n; vitest. Reused existing `filter_region`/`toQuery`/`useRegions` — FE-only, no backend change. Country-scoping deferred |
| [GAP-037](gap-037-services-as-separate-entity-and-tab.md) | Services as a separate entity + tab, split from season inclusions | ⬜ reconcile 3 inclusion concepts; model + UX decision |
| [GAP-038](done/gap-038-enquiry-quote-stacking-conversion-metric.md) | Enquiry pipeline: stage taxonomy + quotes-to-convert metric | ✅ resolved (2026-06-19) — stage taxonomy + structured `lost_reason` (Phase 0, migr. 0032–0035) exposed read-only; `quotes_to_convert` query-pinned `SerializerMethodField` + "Converted in N quote(s)" detail badge; per-quote chips already from GAP-005. Rebuild-era only (migrated history reads null) |
| [GAP-039](done/gap-039-enquiry-dashboard-enrichment.md) | Enquiry list/dashboard enrichment to the Ben/owner mockup | ✅ resolved (2026-06-19) — delivered: enriched read columns, inline lead-status edit, lead-status/salesperson/page-size filters, stage tabs (excl. Dead/Converted), en/el i18n. Remaining inline salesperson/stage/lost-reason edits + date-range/delete/select carved out to GAP-050 |
| [GAP-040](gap-040-customer-tags-taxonomy.md) | Customer tags taxonomy (VIP/Trade/Disability/…) | ⬜ owner Loom 2026-06-17; new area, model-shape decision first |
| [GAP-041](gap-041-standing-linked-contacts.md) | Standing linked contacts (spouse/child/PA) | ⬜ owner Loom 2026-06-17; new area |
| [GAP-042](gap-042-customer-360-profile-view.md) | Customer 360 profile for the sales team | ⬜ owner Loom 2026-06-17; consumes GAP-040/041; "calls" needs activity-log decision |
| [GAP-043](gap-043-quote-builder-multi-week-range.md) | Quote builder: multi-week date-range selection | ⬜ owner Loom 2026-06-17; reverses the flexibility_days rework (replace-vs-coexist open) |
| [GAP-044](gap-044-occupancy-band-fanout-builder.md) | Quote builder: occupancy-band fan-out (all bands, default-checked) | ⬜ owner Loom 2026-06-17; reverses 04-pricing "no auto fan-out" |
| [GAP-045](gap-045-unify-person-identity.md) | **Unify human identity into one `Person`** (folds in `Guest`; agent off the supply-side bag) | ⬜ **foundational — blocks GAP-046/047/048**; overturns people-model-cleanup #1 (owner review 2026-06-17) |
| [GAP-046](gap-046-organisation-and-agent-capacity.md) | `Organisation` entity + agent capacity (B2B Companies) | ⬜ after GAP-045; repoints `.agent` FKs; dissolves GAP-029 |
| [GAP-047](gap-047-clients-directory-and-profile.md) | Clients (renter) directory: browsable list + direct/agent filter | ⬜ after GAP-045/046; list only (detail = GAP-042, tags = GAP-040, links = GAP-041) |
| [GAP-048](gap-048-villa-contacts-directory-and-roles.md) | Villa Contacts directory + role taxonomy (Owner/Agent/Villa Admin/Villa Manager/Mgmt Co) | ⬜ after GAP-045; allows `Organisation` assignees |
| [GAP-049](done/gap-049-create-property-ui.md) | No "create property" UI — create flow is API-only | ✅ resolved (2026-06-18) — `CreatePropertyDialog` (6-field form, slug auto-derive, category/group hooks + `useRegions`), role-gated "New villa" button (disabled-with-tooltip), `slugify` helper, en+el i18n, unit+component tests; no backend change |
| [GAP-050](gap-050-enquiry-grid-inline-edits-and-controls.md) | Enquiry grid: inline salesperson/stage/lost-reason edits + remaining mockup controls | ⬜ follow-up to GAP-039; inline assign/stage/reason cells, date-range filter UI (params already plumbed), delete (ADMIN) + select columns, page-size 10. Stage-dropdown blocked on `05-reservations.md` decision |

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
| [Q-019](q-019-structured-room-attributes.md) | Structured room attributes (bath/shower, aircon, views, accessibility, floor) | ⬜ owner vocabulary decision needed; GAP-024's safe `beds` relaxation already shipped |
| [Q-020](q-020-description-sections-parity.md) | Description sections: spec enum vs sections actually written | ⬜ |
| [Q-021](q-021-defaults-and-feature-taxonomy.md) | Seed group defaults + curate feature taxonomy | ⬜ groups stay (owner removal deemed premature); coordinate seed list with GAP-022 |
| [Q-022](q-022-seasons-defined-by-rates.md) | Seasons defined by rental rates not services | ⬜ owner answer recorded (season = named tier over rate bands); cross-villa reporting still open |
| [Q-023](q-023-partial-week-nightly-composition.md) | Partial-week / nightly price composition for odd-length stays | ⬜ rounding + fallback already done; partial-week rule open |

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
| [GAP-015](done/gap-015-modify-resync-payment-schedule.md) | `modify_dates`/`modify_guests` resync the payment schedule |
| [GAP-019](done/gap-019-security-deposit-calculate-from.md) | SD sizing: live-SD resize on charge/modify (dead `calculate_from` dropped) |
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
| [SMELL-014](done/smell-014-quotation-synthesised-row-guard-structural.md) | Synthesised `booking-` quotation-row exclusion made structural |
| [SMELL-015](done/smell-015-comms-smtp-no-transient-retry.md) | Email marks FAILED on any SMTP error |
| [SMELL-016](done/smell-016-audit-actor-threadlocal-not-asgi-safe.md) | Audit actor on `threading.local` (ASGI-unsafe) |
| [SMELL-017](done/smell-017-cart-naming-vs-shortlist-copy.md) | Quote-builder code said "cart" |

Also resolved outside this list: **Q-012** (payment gateway → Flywire).

## ❌ Dropped

| Id | Title | Reason |
|---|---|---|
| [FG-003](done/fg-003-effective-crashes-on-null-group.md) | `effective()` crashes on null `property.group` | `Property.group` is non-nullable |
| [GAP-003](done/gap-003-endpoint-coverage-gap.md) | Endpoint coverage gap | framing only |
| [GAP-016](done/gap-016-rental-price-override.md) | Rental-price override (legacy parity remainder) | superseded by signed `BookingChargeItem` charge line |
| [SMELL-005](done/smell-005-residual-property-country-charfield.md) | Residual `Property.country` free-text | verified clean |
