# Todo Index

Live status of every ticket. **Open work is at the top; resolved and
dropped tickets are listed at the bottom and their files live in
[`done/`](done/)** (each carries a top-of-file `✅ RESOLVED` / `❌ DROPPED`
banner with the problem, fix, and commit). See `README.md` for conventions;
`CRITIQUE-2026-06-19.md` (current) for the review that drove the latest status
changes. (The superseded `CRITIQUE-2026-05-27.md` was cut once fully worked
through; its outcomes survive in the `done/` ticket banners.)

Status icons:
- ⬜ open (default)
- 🟨 partial — code complete, follow-up work remains
- ✏️ needs revision before implementing (premise partly answered / re-scope)

Scoreboard (2026-07-01): **92 done** (88 resolved + 4 dropped), **36 open**
(incl. ✏️ revise and 🟨 partial). Resolved files moved to `done/`. (GAP-030–037
are the availability/commission/region/services cluster; GAP-038–044 are the
enquiry/quote/customer-profile cluster from the 2026-06-17 owner Loom; GAP-048 +
GAP-052/053 are the contacts-directory cluster from the 2026-06-29 owner Loom
follow-up.)

---

# Open / actionable

## 🔴 Bugs

| Id | Title | Status |
|---|---|---|
| [BUG-008](done/bug-008-securitydeposit-damageclaim-fk.md) | `SecurityDeposit.damage_claim_id` is a fake FK | ✅ resolved (2026-06-23) — `DamageClaim` shipped in `reservations/` (v1, "fuller" model: reference seq, booking/currency FKs, status, `itemized_lines`/`photos`/`accepted_by_guest_at` scaffolds, audited) + `SecurityDeposit.damage_claim` → real `FK(SET_NULL)`; `claim()` resolves PK/instance/None into a booking-matched claim, `DomainValidationError` (400) on bad/foreign ref; damages workflow (report/photos/thresholds/email/approval SM) deferred to wf 8/17 |
| [BUG-009](bug-009-price-basis-ignored-by-engine.md) | Engine ignores `RatePlan.price_basis` — GROSS plans mis-priced | 🟨 spec written (04-pricing 8-9 GROSS carve-out / NET gross-up + 10-decisions deferred row + engine TODO/assembly pointers); **engine code deferred to finance rewrite**; single-source-of-truth with `prices_entered_as` **resolved** by GAP-035 (`RatePlan.price_basis` canonical) |

## 🟠 Footguns

| Id | Title | Status |
|---|---|---|
| [FG-005](fg-005-idempotency-user-required.md) | `IdempotencyRecord.user` required; system actors blocked | ✏️ re-scoped — `IdempotencyRecord` is a dead table; decide delete-vs-revive first |

## 🟡 Smells

| Id | Title | Status |
|---|---|---|
| [FG-002](fg-002-effective-null-vs-empty-string.md) | `effective()` conflates `""` and `NULL` | ⬜ demoted from footgun (low real-world risk today) |
| [SMELL-001](smell-001-archived-vs-status.md) | `archived_at` is a second status | ⬜ |
| [SMELL-008](smell-008-service-layer-contract-single-island.md) | Service-layer contract (perms / `log_operation` / idempotency) lives in one file | ⬜ |
| [SMELL-009](smell-009-duplicate-implemented-three-ways.md) | "Duplicate" implemented three ways; no clone endpoint is idempotent | ⬜ |
| [SMELL-011](smell-011-bare-querysets-missing-query-pins.md) | Bare `.objects.all()` querysets; `accounts`/`pricing` lack query pins | ⬜ |
| [SMELL-012](smell-012-module-structure-drift.md) | Module-structure drift: filters / services / routers / views-in-urls | 🟨 views-in-urls fixed (`refunds_for_booking` moved); filter/service/router shapes still open |

## Surface gaps

| Id | Title | Status |
|---|---|---|
| [GAP-005](gap-005-quotation-flow-parity.md) | Enquiry→Quotation flow parity vs legacy + spine UX overhaul | ⬜ tracker |
| [GAP-010](gap-010-quote-enquiry-analyzed-wrong-codebase.md) | Quote/enquiry specs analysed against the wrong (post-deletion) codebase | ⬜ tracker / corrected reference |
| [GAP-012](gap-012-s3-image-hosting.md) | S3 image hosting for staging & prod (+ legacy binary import) | 🟨 code complete; remaining: ops prereqs + run the cutover runbook |
| [GAP-013](gap-013-quote-builder-ux-feedback-loops.md) | Quote builder UX: tighten feedback loops (invalid-line flag, remove-undo, unpriceable note, a11y) | ⬜ FE polish, sibling of GAP-005 |
| [GAP-017](gap-017-legacy-villabookingdetails-loader.md) | Data-migration loader for legacy `VillaBookingDetails` | ⬜ |
| [GAP-018](gap-018-comms-charge-itemisation.md) | Itemise charge lines in guest-facing comms | ⬜ |
| [GAP-020](gap-020-direct-booking-creation.md) | Direct booking creation (legacy "book now") — synthetic-quotation design | ⬜ design ready; implementation deferred |
| [GAP-021](done/gap-021-audit-history-ui.md) | Per-entity "History" tab in the SPA (audit-log surface) | ✅ resolved (2026-06-22) — reusable single-target `<AuditHistory>` renders the real `field_diffs` contract (`[old,new]`, `__deleted__` banner, merge summary, `[REDACTED]`) as `field: old → new` rows + date-range filter + pagination; admin-gated History tabs on Booking, Property (property + `propertyfinance`, finance pk == property id), and a fixed Contacts tab (`accounts.contact`→`accounts.person` + raw-JSON→formatted, 2 live bugs); en+el; vitest. FE-only — backend read surface already admin-only; `action`-filter GIN index unneeded (UI doesn't use it) |
| [GAP-022](done/gap-022-per-property-feature-ordering.md) | Per-property feature display ordering dropped vs legacy (`MappingOrder`) | ✅ resolved (2026-06-18) — `PropertyFeature` through model w/ `sort_order` (non-destructive migration + FG-017 audit), ordered-`feature_ids` diff-write serializer, `MIN(MappingOrder)` loader, flat drag-drop FeaturesTab |
| [GAP-023](gap-023-owner-approval-preview-lifecycle.md) | `live_offline` replacement: `owner_approved_at` + draft preview link + badges | ⬜ deferred per 2026-06-11 owner decision (no approval gating in v1) |
| [GAP-024](done/gap-024-incremental-loading-required-fields.md) | FE required-field posture fights incremental loading — relax room/capacity write schemas | ✅ `beds` relaxed to optional (matches `required=False` serializer); broader room-attribute posture stays open under Q-019 |
| [GAP-025](done/gap-025-changeover-aware-rate-band-dates.md) | Changeover-aware rate-band end-date suggestion (Sat→Fri auto-fill) | ✅ resolved (2026-06-18) — `suggestRateBandEnd` helper + `RateRuleFormDialog` auto-fill |
| [GAP-026](done/gap-026-currency-display-money-fields.md) | Show property currency beside money fields | ✅ FE adornment + soft mismatch warning; PropertySettings exposes read-only group-resolved `currency_code`; multi-currency intentional (2026-06-18) |
| [GAP-027](done/gap-027-inline-contact-creation-primary-convention.md) | Inline contact creation from the property + per-role primary convention | ✅ resolved (2026-06-18) — picker auto-select via `initialContact` + per-role-primary convention documented |
| [GAP-028](gap-028-admin-integrations-surface.md) | Admin `/system/integrations`: `OAuthCredential` CRUD + `SyncRun`/`SyncIssue` lists | ⬜ |
| [GAP-029](gap-029-contact-required-name-fields-divergence.md) | Contact `first_name`/`last_name` FE/BE required-field divergence | ▶️ **unblocked (2026-06-23)** — GAP-045/046 landed (`Person`+`Organisation` shipped). **Live bug still open:** `person.py:28-29` names lack `blank=True`, so company-only contact still 400s; now actionable (add `blank=True` + migration + name-OR-org validator + tests) |
| [GAP-030](done/gap-030-weekly-pricing-in-availability-timeline.md) | Weekly pricing in the sales availability timeline (price-by-week, changeover visible) | ✅ resolved (2026-06-18) — `StayOptionsService.weekly_prices()` + `GET /availability/weekly-prices` price each changeover week (context reused, no per-week reload), Q-013/POA/projected flags, never 500; FE price strip aligned under the bands with changeover weekday, guide/POA markers, separate non-blocking query; en+el; pytest+vitest. Fixed-changeover only; variable/sub-week deferred (GAP-025/Q-022) |
| [GAP-031](done/gap-031-availability-timeline-month-context-header.md) | Month context above the availability timeline date range | ✅ resolved (2026-06-18) — `monthSpanLabel` helper renders spanning month(s)+year above the date range (single/cross-month/cross-year), date-fns locale text + i18n dash join (en+el), vitest all three cases; FE-only |
| [GAP-032](done/gap-032-click-drag-availability-block-creation.md) | Click-and-drag availability block creation | ✅ resolved (2026-06-18) — press-drag-release on the villa month grid opens the create dialog pre-filled; `resolveDragRange` helper truncates before occupied days (half-open), pointer-delegation keeps dropdowns/links working, role-gated; vitest range-mapping + grid-drag; FE-only |
| [GAP-033](done/gap-033-availability-last-confirmed-timestamp.md) | Availability "last confirmed" timestamp + manual confirm button | ✅ resolved (2026-07-01) — split into three separately-labelled signals (owner-updated / calendar-import / VC-staff-confirmed) rather than one conflated field; Signal 1 stored on `Property` + touched from `OwnerBlockService` create/release (MANUAL only; excludes contest/iCal/quotation/booking churn — tested both ways), Signal 2 derived from `PropertyCalendarFeed.last_polled_at`, Signal 3 via `POST /properties/{id}:confirm-availability` (reservations-write); FE three lines + "Mark as up-to-date" button + read-only timeline badges (en+el); freshness touches don't bump `updated_at` |
| [GAP-034](done/gap-034-availability-calendar-source-indicator.md) | Sales-view calendar-source indicator: iCal badge + owner calendar link | ✅ resolved (2026-06-21) — `has_active_ical_feed` (N+1-safe `Exists`) + `calendar_url` on property list/detail via a shared serializer mixin (secret feed `url` never serialized); `calendar_url` on `PropertySettings` (migr. `0020`, editable in the Settings tab, server-validated URL); shared `CalendarSourceIndicator` renders badge-wins-over-link in the timeline + AvailabilityTab; en+el; pytest+vitest. Feed-health tooltip + `GroupSettings`/back-office mgmt deferred |
| [GAP-035](done/gap-035-net-gross-commission-derivation.md) | Net↔gross rate entry with automatic commission derivation | ✅ resolved (2026-06-22) — rate-band form derives the counterpart on display (owner net for a GROSS plan, guest price for NET) via the engine's mode-aware commission+tax math (`netGross.ts`, `÷(1−pct)` gross-up, fixed flat, exempt-aware, `ROUND_HALF_EVEN`); **derive-on-display only** (no double-count vs BUG-009). Effective commission/tax + `prices_entered_as_effective` surfaced read-only on the settings endpoint; **`RatePlan.price_basis` is the sole pricing authority**, `prices_entered_as` demoted to the new-season default. pytest+vitest, en+el. Residual: owner-statement serializer's `prices_entered_as` read closes with the BUG-009 finance rewrite |
| [GAP-036](done/gap-036-region-filter-property-listing.md) | Region filter on the property listing grid (status filter already exists) | ✅ resolved (2026-06-19) — Region `<Select>` added to the list filter row (country → region → status); slug-valued options (mirrors AvailabilityTimelinePage), URL `region` param read into the list query, en+el i18n; vitest. Reused existing `filter_region`/`toQuery`/`useRegions` — FE-only, no backend change. Country-scoping deferred |
| [GAP-037](done/gap-037-services-as-separate-entity-and-tab.md) | Services as a separate entity + tab, split from season inclusions | ✅ resolved (2026-07-01) — new informational, date-ranged `properties.PropertyService` (option c) replaces free-text `RatePlan.inclusion` on its own **Services** tab; `Extra` untouched (no 4th concept), `RatePlan.inclusion` dropped / `.notes` kept. Engine derives `breakdown["inclusion"]` from active overlapping services (projection maps future stays to anchor year); `seed_inclusions`/`QuotationLine.inclusions` unchanged. 6 units (model→data migr→engine→drop column→API→FE tab) on `feat/gap-037-services`, pytest+vitest, en+el. Deferred: `Feature(INCLUDED_SERVICE)` retirement, structured per-service guest lines, services→comms (GAP-018) |
| [GAP-038](done/gap-038-enquiry-quote-stacking-conversion-metric.md) | Enquiry pipeline: stage taxonomy + quotes-to-convert metric | ✅ resolved (2026-06-19) — stage taxonomy + structured `lost_reason` (Phase 0, migr. 0032–0035) exposed read-only; `quotes_to_convert` query-pinned `SerializerMethodField` + "Converted in N quote(s)" detail badge; per-quote chips already from GAP-005. Rebuild-era only (migrated history reads null) |
| [GAP-039](done/gap-039-enquiry-dashboard-enrichment.md) | Enquiry list/dashboard enrichment to the Ben/owner mockup | ✅ resolved (2026-06-19) — delivered: enriched read columns, inline lead-status edit, lead-status/salesperson/page-size filters, stage tabs (excl. Dead/Converted), en/el i18n. Remaining inline salesperson/stage/lost-reason edits + date-range/delete/select carved out to GAP-050 |
| [GAP-040](done/gap-040-customer-tags-taxonomy.md) | Customer tags taxonomy (VIP/Trade/Disability/…) | ✅ resolved (2026-06-23) — fixed `PersonTag` `ArrayField` on `Person` (10 tags; "Repeat" → derived badge in GAP-042), audited + erasure-scrubbed (special-category), `?tags=` overlap filter; FE checkbox-dialog editor + read-only chips on the contact profile (merge feat/gap-040-041, B1/B2/F1). Enquiry/quote chips + curated taxonomy (Q-021) deferred |
| [GAP-041](done/gap-041-standing-linked-contacts.md) | Standing linked contacts (spouse/child/PA) | ✅ resolved (2026-06-23) — directed `PersonRelationship(from,to,kind)` (DB no-self-link + `(from,to,kind)` unique), one row rendered with an inverse label (CHILD↔PARENT, PA→Principal); merge folds links dropping self-links/dupes/mirrors, anonymize deletes them; `/contacts/{id}/relationships` + "Linked contacts (N)" accordion reusing the GAP-027 picker (B3/B4/F2) |
| [GAP-042](done/gap-042-customer-360-profile-view.md) | Customer 360 profile for the sales team | ✅ resolved (2026-06-23) — assembled over the unified `Person` (compose, no aggregate endpoint): `/contacts/{id}` serializes town/post_code/country(+name) + property-agnostic `booking_count`/`is_repeat_customer` (≥1 booking, gated annotation); FE `CustomerProfilePanel` (identity + Repeat badge + tags + collapsible address + linked-contacts + enquiry & booking history, wiring in the dead `ContactEnquiryHistory`) reused on the contact page and embedded in the enquiry- & quote-detail rails (merge feat/gap-042, B1/F1/F2/F3). Deferred: calls/activity-log (Q-017), rich-text notes, country edit, quote-builder inline embed |
| [GAP-043](gap-043-quote-builder-multi-week-range.md) | Quote builder: multi-week date-range selection | ⬜ owner Loom 2026-06-17; reverses the flexibility_days rework (replace-vs-coexist open) |
| [GAP-044](gap-044-occupancy-band-fanout-builder.md) | Quote builder: occupancy-band fan-out (all bands, default-checked) | ⬜ owner Loom 2026-06-17; reverses 04-pricing "no auto fan-out" |
| [GAP-045](done/gap-045-unify-person-identity.md) | **Unify human identity into one `Person`** (folds in `Guest`; agent off the supply-side bag) | ✅ resolved (2026-06-22) — full expand/contract shipped across 3a–3d / D1–D5 (merge `51feb1a`): `reservations.Guest` + the 5 `guest` FKs deleted; `accounts.Person` is the sole human identity (PersonEmail/PersonPhone children, `kind`, merge/anonymize); legacy import writes `Person` directly (`client-{Id}`) with a one-shot mirror re-key migration; `/contacts` is the unified `?kind=`-filtered directory, `/guests` retired. Unblocks GAP-046/047/048 |
| [GAP-046](done/gap-046-organisation-and-agent-capacity.md) | `Organisation` entity + agent capacity (B2B Companies) | ✅ resolved (2026-06-22) — `accounts.Organisation` (org_type-scoped) + `Person.agency` FK shipped (merge `8184ab2`, 7 units); free-text `Person.company` migrated to Organisation(agency) + dropped (migration `0012`, content-hash dedup + `dedupe_organisations` reporter); FE `/companies` directory + CompanyPicker, contacts form swapped to the agency FK. `.agent` repoint already done in GAP-045. Dissolves GAP-029; mgmt/supplier screens (GAP-048/q-007), agent filter (GAP-047) + FE `:merge` UI deferred |
| [GAP-047](done/gap-047-clients-directory-and-profile.md) | Clients (renter) directory: browsable list + direct/agent filter | ✅ resolved (2026-06-23) — `/clients` list endpoint over customer-capacity `Person` + direct/agent filter, quoted/booked region aggregation (query-pinned) + region chip columns, FE Clients directory page + Sidebar nav/route; pytest+vitest (merge `16680fd`, 4 units). List only — detail = GAP-042, tags = GAP-040, links = GAP-041 |
| [GAP-048](gap-048-villa-contacts-directory-and-roles.md) | Suppliers directory (rename from Contacts) + role taxonomy + type surfacing | ⬜ reworked 2026-06-29 owner Loom — rename "Contacts"→"Suppliers" + capacity-scope to owner/manager/admin/mgmt-co (customers+agents → Clients), role-enum reconciliation (Owner/Agent/Villa Admin/Villa Manager/Mgmt Co), `Organisation` assignees, Suppliers/concierge-Suppliers name collision (Q-007) |
| [GAP-049](done/gap-049-create-property-ui.md) | No "create property" UI — create flow is API-only | ✅ resolved (2026-06-18) — `CreatePropertyDialog` (6-field form, slug auto-derive, category/group hooks + `useRegions`), role-gated "New villa" button (disabled-with-tooltip), `slugify` helper, en+el i18n, unit+component tests; no backend change |
| [GAP-050](gap-050-enquiry-grid-inline-edits-and-controls.md) | Enquiry grid: inline salesperson/stage/lost-reason edits + remaining mockup controls | ⬜ follow-up to GAP-039; inline assign/stage/reason cells, date-range filter UI (params already plumbed), delete (ADMIN) + select columns, page-size 10. Stage-dropdown blocked on `05-reservations.md` decision |
| [GAP-051](gap-051-checkout-charge-itemisation.md) | Itemise charge lines on the guest checkout page | ⬜ deferred until the guest checkout page exists |
| [GAP-052](gap-052-contact-detail-edit-completeness.md) | Contact detail: editable address + editable/finished notes + contact-type badges | ⬜ 2026-06-29 owner Loom — overturns GAP-042 address-display-only; spans Clients profile + Suppliers detail |
| [GAP-053](gap-053-clients-tag-filters-and-inline-tag-editor.md) | Clients directory: VIP/Trade/Repeat chip filters + inline (no-dialog) client-only tag editor | ⬜ 2026-06-29 owner Loom — follow-up to GAP-047/040; Repeat filter = derived annotation |

## Open product questions

| Id | Title | Status |
|---|---|---|
| [Q-007](q-007-concierge-supplier-directory.md) | Concierge supplier directory shape | ⬜ |
| [Q-008](q-008-2fa-enforcement.md) | 2FA enforcement scope | ⬜ |
| [Q-010](q-010-guest-data-retention.md) | Guest data retention / GDPR | ⬜ |
| [Q-017](q-017-comms-direction-signals-vs-spine-position.md) | comms: signals-only sink, or move it down the spine? | ⬜ |
| [Q-018](q-018-rate-reduction-vs-carryover.md) | Rate reductions: base price + reduction so carry-over copies the base | ⬜ Q1 answered (both % and fixed reductions, specific weeks) |
| [Q-019](q-019-structured-room-attributes.md) | Structured room attributes (bath/shower, aircon, views, accessibility, floor) | ⬜ owner vocabulary decision needed; GAP-024's safe `beds` relaxation already shipped |
| [Q-020](q-020-description-sections-parity.md) | Description sections: spec enum vs sections actually written | ⬜ |
| [Q-021](q-021-defaults-and-feature-taxonomy.md) | Seed group defaults + curate feature taxonomy | ⬜ groups stay (owner removal deemed premature); coordinate seed list with GAP-022 |
| [Q-022](q-022-seasons-defined-by-rates.md) | Seasons defined by rental rates not services | ⬜ owner answer recorded (season = named tier over rate bands); cross-villa reporting still open |
| [Q-023](q-023-partial-week-nightly-composition.md) | Partial-week / nightly price composition for odd-length stays | ⬜ rounding + fallback already done; partial-week rule open |

## Decisions blocking implementation

Highest-leverage unanswered questions (each blocks a slice of downstream work):

- **Q-019** — Structured room attributes (owner vocabulary; blocks room-attribute write surface)

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
| [FG-009](done/fg-009-csrf-prime-coupled-to-shell-server.md) | CSRF priming coupled to HTML-shell server → dedicated `auth/csrf` endpoint |
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
| [GAP-011](done/gap-011-ical-feed-ingest.md) | iCal feed ingest from owners (engine + ops conflict alert + in-app `OwnerBlockUpdate` awareness feed + feed-`url` secrecy; awareness *digest email* deferred) |
| [GAP-014](done/gap-014-quote-currency-forced-selection.md) | Quote builder forced currency → per-line currency |
| [GAP-015](done/gap-015-modify-resync-payment-schedule.md) | `modify_dates`/`modify_guests` resync the payment schedule |
| [GAP-019](done/gap-019-security-deposit-calculate-from.md) | SD sizing: live-SD resize on charge/modify (dead `calculate_from` dropped) |
| [INV-001](done/inv-001-propertycontactassignment-owner-uniqueness.md) | `PropertyContactAssignment` owner uniqueness |
| [INV-002](done/inv-002-raterule-priority-tiebreak.md) | `RateRule.priority` tie-break |
| [INV-003](done/inv-003-refund-amount-sign-convention.md) | `Refund.amount` sign convention |
| [INV-004](done/inv-004-syncrun-syncissue-retry.md) | `SyncRun`/`SyncIssue` failure handling |
| [INV-005](done/inv-005-legacy-id-indexing-consistency.md) | `legacy_id` indexing consistency |
| [Q-001](done/q-001-cancellation-policy-thresholds.md) | Cancellation policy → named templates + per-villa override |
| [Q-002](done/q-002-owner-pre-approval-sla.md) | Owner pre-approval SLA → escalate to human, 24h |
| [Q-003](done/q-003-channel-sync-scope.md) | Channel sync scope → out of v1 |
| [Q-004](done/q-004-hold-expiry-default.md) | Hold expiry default (shape) |
| [Q-005](done/q-005-currency-display-base.md) | Reports base currency + FX → EUR base, daily snapshot |
| [Q-006](done/q-006-owner-statement-scheduling.md) | Owner statements → monthly + on-demand, portal-only (PDF+CSV), auto-send deferred to v2 |
| [Q-009](done/q-009-multi-site-inventory-sharing.md) | Multi-site inventory sharing → single site v1 |
| [Q-011](done/q-011-email-template-inheritance.md) | Email template inheritance → system → site |
| [Q-013](done/q-013-rate-card-incomplete-pricing.md) | Rate-card incomplete pricing → flag + manual quote |
| [Q-014](done/q-014-audit-log-retention.md) | Audit-log retention → keep forever + scrub, admin-only |
| [Q-015](done/q-015-owner-financial-visibility.md) | Owner financial visibility defaults |
| [Q-016](done/q-016-payment-ledger-vs-dedicated-models.md) | Payment ledger vs dedicated SD → Lane A |
| [SMELL-002](done/smell-002-quotation-expire-draft.md) | `Quotation.expire()` only handled SENT→EXPIRED |
| [SMELL-003](done/smell-003-currency-decimal-places-unenforced.md) | `Currency.decimal_places` informational only |
| [SMELL-004](done/smell-004-emaillog-content-hash-scope.md) | `EmailLog` content-hash dedupe scope |
| [SMELL-006](done/smell-006-terms-accepted-at-required-no-default.md) | `terms_accepted_at` required, no default |
| [SMELL-007](done/smell-007-occupancy-fallback-doc-claim.md) | Spec misstates legacy occupancy fallback (doc) |
| [SMELL-010](done/smell-010-error-signalling-forks.md) | Three error-signalling patterns converged on typed `DomainError` (+ import-linter ban on `rest_framework` in services) |
| [SMELL-013](done/smell-013-one-model-per-file-doc-drift.md) | "One model per file" rule reworded to "one aggregate per file" (CLAUDE.md, doc-only) |
| [SMELL-014](done/smell-014-quotation-synthesised-row-guard-structural.md) | Synthesised `booking-` quotation-row exclusion made structural |
| [SMELL-015](done/smell-015-comms-smtp-no-transient-retry.md) | Email marks FAILED on any SMTP error |
| [SMELL-016](done/smell-016-audit-actor-threadlocal-not-asgi-safe.md) | Audit actor on `threading.local` (ASGI-unsafe) |
| [SMELL-017](done/smell-017-cart-naming-vs-shortlist-copy.md) | Quote-builder code said "cart" |
| [SMELL-018](done/smell-018-owner-probe-403-as-control-flow.md) | Boot-time owner probe 403-as-control-flow → `OwnerMeView` `IsAuthenticated` + `{is_owner:false}` |

Also resolved outside this list: **Q-012** (payment gateway → Flywire).

## ❌ Dropped

| Id | Title | Reason |
|---|---|---|
| [FG-003](done/fg-003-effective-crashes-on-null-group.md) | `effective()` crashes on null `property.group` | `Property.group` is non-nullable |
| [GAP-003](done/gap-003-endpoint-coverage-gap.md) | Endpoint coverage gap | framing only |
| [GAP-016](done/gap-016-rental-price-override.md) | Rental-price override (legacy parity remainder) | superseded by signed `BookingChargeItem` charge line |
| [SMELL-005](done/smell-005-residual-property-country-charfield.md) | Residual `Property.country` free-text | verified clean |
