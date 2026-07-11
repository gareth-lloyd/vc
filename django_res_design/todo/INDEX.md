# Todo Index

Live status of every ticket. **Open work is at the top; resolved and
dropped tickets are listed at the bottom and their files live in
[`done/`](done/)** (each carries a top-of-file `✅ RESOLVED` / `❌ DROPPED`
banner with the problem, fix, and commit). See `README.md` for conventions.
The two review passes that drove past status changes are both fully worked
through: `CRITIQUE-2026-05-27.md` was cut once absorbed, and
`CRITIQUE-2026-06-19.md` is retained under [`reviews/`](reviews/) for
provenance. Their outcomes survive in the `done/` ticket banners.

Status icons:
- ⬜ open (default)
- 🟨 partial — code complete, follow-up work remains
- ✏️ needs revision before implementing (premise partly answered / re-scope)
- ⏸ superseded-pending — folded into another ticket, drop when it lands

Scoreboard (2026-07-08 recount + GAP-076/077/079 close-outs to 2026-07-10; BUG-017 deleted outright 2026-07-10): **127 done** (120 resolved + 7 dropped), **41 open**
(incl. ✏️ revise, 🟨 partial, and ⏸ superseded-pending; +7 from the 2026-07-08 Nick call, GAP-074–080). Recently-resolved tickets stay
listed inline in their topic section marked ✅ (not moved to the bottom table); the
scoreboard counts the genuinely-open (⬜/🟨/✏️/⏸/🔵) rows. Clusters: GAP-064–068 room-model
(superseded Q-019/Q-021); GAP-030–037 availability/commission/region/services; GAP-038–044
enquiry/quote/customer-profile (2026-06-17 owner Loom); GAP-048 + GAP-052/053 contacts-
directory (2026-06-29 owner Loom follow-up).

_2026-07-03 additions: GAP-069 (workbench carry-forward, resolved) and SPEC-001
(rate-model date-authority exploration) from the far-future-rates investigation;
GAP-070 (remove property groups) already landed on this branch. GAP-071 (no manual
security-deposit creation) from the `/bookings/383/payments` empty-state
investigation. INV-006 harvests the still-open questions surfaced when the legacy
workflow specs were frozen into `../legacy/` (2026-07-03 `django_res_design/` reorg)._

_2026-07-06: **GAP-070** (remove property groups) landed on local `main` (unpushed),
carrying **GAP-068** (dropped, its default values seed the new `PropertyDefaults`
singleton) and **FG-002** (dropped, `effective()` deleted) with it._

_2026-07-08 additions from the Nick/Gareth res-rebuild call (each checked against
the codebase before filing): **GAP-074/075** (nightly / ad-hoc-flexible quoting
for no-changeover villas), **GAP-076/077/079** (booking-finance cluster —
non-commissionable extras, per-component gross/net split, commission-after-VAT;
GAP-076 is the critical path), **GAP-078** (quote grouping by country/region +
weekly-vs-nightly section break), **GAP-080** (currency obviousness in the
builder UI). Call also confirmed already-built: per-line quote notes, structured
room features (GAP-064/067), direct-booking-via-unsent-quote (GAP-020 dropped),
Greek UI. Leads-stage-before-enquiry and Zoho/WordPress integration were
discussed but not filed here (leads = extend `EnquiryStatus`, tracked via GAP-005/
GAP-050; Zoho blocked on external spec, GAP-028)._

---

# Open / actionable

## 🔴 Bugs

| Id | Title | Status |
|---|---|---|
| [BUG-008](done/bug-008-securitydeposit-damageclaim-fk.md) | `SecurityDeposit.damage_claim_id` is a fake FK | ✅ resolved (2026-06-23) — `DamageClaim` shipped in `reservations/` (v1, "fuller" model: reference seq, booking/currency FKs, status, `itemized_lines`/`photos`/`accepted_by_guest_at` scaffolds, audited) + `SecurityDeposit.damage_claim` → real `FK(SET_NULL)`; `claim()` resolves PK/instance/None into a booking-matched claim, `DomainValidationError` (400) on bad/foreign ref; damages workflow (report/photos/thresholds/email/approval SM) deferred to wf 8/17 |
| [BUG-009](done/bug-009-price-basis-ignored-by-engine.md) | Engine ignores `RatePlan.price_basis` — GROSS plans mis-priced | ✅ resolved (2026-07-02) — engine branch landed **independently of the finance rewrite** (the maths only need pct/fixed/exempt, already flowing through the `_call_finance_resolver` shim, which stays): `PricingEngine._derive_commission_and_tax` branches on `price_basis` (GROSS carve-out / NET gross-up, raw-commission-feeds-tax-base quantization order, ≥100%/zero-base sanitisation guards), breakdown snapshots `price_basis` + `net_to_owner`, FE probe workaround unwound (probe trusts engine `total`, owner economics shown). Spec slice was 2026-06-22 |
| [BUG-013](done/bug-013-migration-drops-villaoccupencyprice.md) | Migration silently drops `VillaOccupencyPrice` — range-based occupancy rates lost on cutover | ✅ resolved (2026-07-01) — `RateRuleLoader.legacy_query` LEFT JOINs `VillaOccupencyPrice`; `_prepare_occupancy_rows` expands each `IsOccupationPrice` parent into one band per rule (`legacy_id="occ-{OccId}"`) + base-weekly gap fallbacks. Fed GAP-044 |
| [BUG-014](done/bug-014-raterule-flattened-period-occupancy-hierarchy.md) | `RateRule` flattened legacy's period→occupancy hierarchy — permits ragged/misaligned bands | ✅ superseded (2026-07-01) by **GAP-056** — Option B shipped and then some: `RateCard` dropped, `Property → RatePlan → RatePeriod → RateRule`, two `btree_gist` EXCLUDEs make ragged bands structurally impossible |
| [BUG-018](bug-018-frontend-cache-staleness-missing-invalidations.md) | Frontend cache staleness — booking mutations skip the availability calendar; contact sub-tabs never invalidate | ⬜ from 2026-07-02 frontend complexity audit; per-mutation hand-listed invalidations have drifted → operator sees stale dates/history |
| [BUG-015](bug-015-scattered-state-machines-false-409.md) | State machines hand-rolled 4 ways; SD's bare `ValueError` → false 409s; `BookingHold`/`DamageClaim` lifecycles unguarded | ⬜ from 2026-07-02 complexity audit; shape depends on Q-024 |
| [BUG-016](done/bug-016-rate-grid-disjointness-reimplemented.md) | Rate-grid disjointness/precedence reimplemented by 4 producers — projected quote can price ≠ its materialised twin | ✅ resolved (2026-07-05) — ONE canonical flattener (`pricing/services/flattening.py` + shared `intervals.py`) consumed by projection (now eager, parity by construction via `map_anchor_sources`), carryover, the legacy loader (split-not-clip; deltas disclosed in CUTOVER.md) and the 0013 backfill; cross-producer equivalence suite pins 9 grids pointwise + byte-identical. Party-widening money bug fixed |

## 🟠 Footguns

| Id | Title | Status |
|---|---|---|
| [FG-005](done/fg-005-idempotency-user-required.md) | `IdempotencyRecord.user` required; system actors blocked | ✅ resolved (2026-07-02, local main unpushed) — dead table dropped (`core.0006`; zero runtime writers ever); design docs annotated, issue #39 reversed; live idempotency stays the `core/idempotency.py` meta-key path |

## 🟡 Smells

| Id | Title | Status |
|---|---|---|
| [FG-002](done/fg-002-effective-null-vs-empty-string.md) | `effective()` conflates `""` and `NULL` | ❌ dropped (2026-07-06) — mooted by **GAP-070** (deletes `effective()` entirely; `NULL` now = genuinely unset, resolves to a floor/`_POLICY_FALLBACKS`). Never a real-world risk |
| [SMELL-001](smell-001-archived-vs-status.md) | `archived_at` is a second status | ⬜ |
| [SMELL-008](smell-008-service-layer-contract-single-island.md) | Service-layer contract (perms / `log_operation` / idempotency) lives in one file | ⬜ |
| [SMELL-009](smell-009-duplicate-implemented-three-ways.md) | "Duplicate" implemented three ways; no clone endpoint is idempotent | ⬜ |
| [SMELL-011](smell-011-bare-querysets-missing-query-pins.md) | Bare `.objects.all()` querysets; `accounts`/`pricing` lack query pins | ⬜ |
| [SMELL-012](smell-012-module-structure-drift.md) | Module-structure drift: filters / services / routers / views-in-urls | 🟨 views-in-urls fixed (`refunds_for_booking` moved); filter/service/router shapes still open |
| [SMELL-020](smell-020-booking-money-authority.md) | Booking has no single money authority; guest total re-derived byte-for-byte in two apps; dead `adjustment` column | ⬜ from 2026-07-02 complexity audit; builds on FG-011 |
| [SMELL-021](smell-021-price-basis-two-sources.md) | `PriceBasis` defined twice + two competing authorities; loader defaults imported plans to GROSS (NET villa mis-priced on cutover) | ⬜ from 2026-07-02 complexity audit; sibling to BUG-009/GAP-035 |
| [SMELL-022](smell-022-exclude-constraints-raw-sql-only.md) | Rate-grid overlap EXCLUDE constraints live only in raw migration SQL — invisible to `makemigrations` | ⬜ from 2026-07-02 complexity audit; port to `ExclusionConstraint` |
| [SMELL-023](smell-023-two-money-rounding-conventions.md) | Two money-rounding conventions; hardcoded 2dp paths mis-round for 0/3-decimal currencies | ⬜ from 2026-07-02 complexity audit; dormant until a non-2dp currency ships |
| [SMELL-024](smell-024-god-objects-model-business-logic.md) | God objects: business logic on `Booking` model + in quotation views; oversized engine/stay-options methods | ⬜ from 2026-07-02 complexity audit; incremental extractions, overlaps SMELL-009/012 |
| [SMELL-019](done/smell-019-rate-model-naming-and-ui-residuals-post-gap-056.md) | Rate-model naming & UI residuals after GAP-056 | ✅ done (2026-07-02, local main unpushed) — `RateRule`→`RateBand` (model/API/routes/snapshot), `/seasons`→`/rate-plans`, GAP-025 changeover suggestion reinstated at period grain; `is_active` backfill non-issue confirmed |

## Refactors

| Id | Title | Status |
|---|---|---|
| [REFACTOR-001](refactor-001-frontend-boilerplate-consolidation.md) | Consolidate frontend boilerplate — `useCrudDialog`, FormDialog reset-effect wrapper, `toastError`/`apiErrorMessage`, one optimistic-update helper; decompose QuoteBuilder/QuoteResultLine | ⬜ from 2026-07-02 frontend complexity audit; first `refactor-*` ticket, mechanical, no behaviour change; coordinates with BUG-018 on shared mutation helpers |

## Speculative

| Id | Title | Status |
|---|---|---|
| [SPEC-001](spec-001-rateplan-date-authority-regime-bucket.md) | Make `RatePeriod` the sole date authority; `RatePlan` becomes a dateless regime bucket (drop `effective_from/to`) | 🔵 exploration from 2026-07-03 far-future-rates investigation; year-on-`RatePlan` alt considered + rejected (cross-year multi-regime stays); cheap interim = bind envelope to period union; related Q-022/Q-018/SMELL-021/22, GAP-069 |

## Investigations

| Id | Title | Status |
|---|---|---|
| [INV-006](inv-006-legacy-open-questions.md) | Live open questions harvested from the legacy workflow specs when they were frozen into `../legacy/` | ⬜ holding pen (2026-07-03 reorg) — ~19 still-open questions tracked nowhere else; promote each to its own ticket when its app is next touched |

## Surface gaps

| Id | Title | Status |
|---|---|---|
| [GAP-005](gap-005-quotation-flow-parity.md) | Enquiry→Quotation flow parity vs legacy + spine UX overhaul | ⬜ tracker |
| [GAP-010](done/gap-010-quote-enquiry-analyzed-wrong-codebase.md) | Quote/enquiry specs analysed against the wrong (post-deletion) codebase | ✅ resolved (2026-07-02) — reference promoted to `workflows/legacy-quote-enquiry-reference.md`; errata banners landed; ticket retired |
| [GAP-012](gap-012-s3-image-hosting.md) | S3 image hosting for staging & prod (+ legacy binary import) | 🟨 code complete; remaining: ops prereqs + run the cutover runbook |
| [GAP-013](gap-013-quote-builder-ux-feedback-loops.md) | Quote builder UX: tighten feedback loops (invalid-line flag, remove-undo, unpriceable note, a11y) | ⬜ FE polish, sibling of GAP-005 |
| [GAP-017](done/gap-017-legacy-villabookingdetails-loader.md) | Data-migration loader for legacy `VillaBookingDetails` | ✅ resolved (2026-07-02) — `BookingChargeItemLoader` ports Chargeable Extras with convert-or-flag FX (pinned `as_of=booking.date_from`, no-rate → `errors`), payment-resync suppression around the load (package's first), removal sweep, `reconcile_legacy` check (gap 0 placeholder, recalibrate at dry-run); same-currency rows verbatim reproduce legacy totals by construction (CUTOVER.md §4g) |
| [GAP-018](done/gap-018-comms-charge-itemisation.md) | Itemise charge lines in guest-facing comms | ✅ resolved (2026-06-21) — shared `booking_charge_breakdown(booking)` builder (`reservations/services/charges.py`) decomposes the billed total, surfaced in guest-facing email |
| [GAP-021](done/gap-021-audit-history-ui.md) | Per-entity "History" tab in the SPA (audit-log surface) | ✅ resolved (2026-06-22) — reusable single-target `<AuditHistory>` renders the real `field_diffs` contract (`[old,new]`, `__deleted__` banner, merge summary, `[REDACTED]`) as `field: old → new` rows + date-range filter + pagination; admin-gated History tabs on Booking, Property (property + `propertyfinance`, finance pk == property id), and a fixed Contacts tab (`accounts.contact`→`accounts.person` + raw-JSON→formatted, 2 live bugs); en+el; vitest. FE-only — backend read surface already admin-only; `action`-filter GIN index unneeded (UI doesn't use it) |
| [GAP-022](done/gap-022-per-property-feature-ordering.md) | Per-property feature display ordering dropped vs legacy (`MappingOrder`) | ✅ resolved (2026-06-18) — `PropertyFeature` through model w/ `sort_order` (non-destructive migration + FG-017 audit), ordered-`feature_ids` diff-write serializer, `MIN(MappingOrder)` loader, flat drag-drop FeaturesTab |
| [GAP-023](gap-023-owner-approval-preview-lifecycle.md) | `live_offline` replacement: `owner_approved_at` + draft preview link + badges | ⬜ deferred per 2026-06-11 owner decision (no approval gating in v1) |
| [GAP-024](done/gap-024-incremental-loading-required-fields.md) | FE required-field posture fights incremental loading — relax room/capacity write schemas | ✅ `beds` relaxed to optional (matches `required=False` serializer); broader room-attribute posture stays open under Q-019 |
| [GAP-025](done/gap-025-changeover-aware-rate-band-dates.md) | Changeover-aware rate-band end-date suggestion (Sat→Fri auto-fill) | ✅ resolved (2026-06-18) — `suggestRateBandEnd` helper + `RateRuleFormDialog` auto-fill |
| [GAP-026](done/gap-026-currency-display-money-fields.md) | Show property currency beside money fields | ✅ FE adornment + soft mismatch warning; PropertySettings exposes read-only group-resolved `currency_code`; multi-currency intentional (2026-06-18) |
| [GAP-027](done/gap-027-inline-contact-creation-primary-convention.md) | Inline contact creation from the property + per-role primary convention | ✅ resolved (2026-06-18) — picker auto-select via `initialContact` + per-role-primary convention documented |
| [GAP-028](gap-028-admin-integrations-surface.md) | Admin `/system/integrations`: `OAuthCredential` CRUD + `SyncRun`/`SyncIssue` lists | ⬜ |
| [GAP-029](done/gap-029-contact-required-name-fields-divergence.md) | Contact `first_name`/`last_name` FE/BE required-field divergence | ✅ resolved (2026-07-01) — `Person.first_name`/`last_name` → `blank=True` (migration `0015`, state-only) + a name-OR-agency floor at the top of `ContactSerializer.validate()` reading the effective (attrs-over-instance) value so a PATCH clearing names but keeping the agency still passes; app-level gate (mirrors channel-contactability), not a DB CHECK; error keyed on `first_name`. FE was already loosened (schema + en/el i18n + tests). Decision recorded in `10-decisions.md`. `2a7fee7`/`15edeb3` |
| [GAP-030](done/gap-030-weekly-pricing-in-availability-timeline.md) | Weekly pricing in the sales availability timeline (price-by-week, changeover visible) | ✅ resolved (2026-06-18) — `StayOptionsService.weekly_prices()` + `GET /availability/weekly-prices` price each changeover week (context reused, no per-week reload), Q-013/POA/projected flags, never 500; FE price strip aligned under the bands with changeover weekday, guide/POA markers, separate non-blocking query; en+el; pytest+vitest. Fixed-changeover only; variable/sub-week deferred (GAP-025/Q-022) |
| [GAP-031](done/gap-031-availability-timeline-month-context-header.md) | Month context above the availability timeline date range | ✅ resolved (2026-06-18) — `monthSpanLabel` helper renders spanning month(s)+year above the date range (single/cross-month/cross-year), date-fns locale text + i18n dash join (en+el), vitest all three cases; FE-only |
| [GAP-032](done/gap-032-click-drag-availability-block-creation.md) | Click-and-drag availability block creation | ✅ resolved (2026-06-18) — press-drag-release on the villa month grid opens the create dialog pre-filled; `resolveDragRange` helper truncates before occupied days (half-open), pointer-delegation keeps dropdowns/links working, role-gated; vitest range-mapping + grid-drag; FE-only |
| [GAP-033](done/gap-033-availability-last-confirmed-timestamp.md) | Availability "last confirmed" timestamp + manual confirm button | ✅ resolved (2026-07-01) — split into three separately-labelled signals (owner-updated / calendar-import / VC-staff-confirmed) rather than one conflated field; Signal 1 stored on `Property` + touched from `OwnerBlockService` create/release (MANUAL only; excludes contest/iCal/quotation/booking churn — tested both ways), Signal 2 derived from `PropertyCalendarFeed.last_polled_at`, Signal 3 via `POST /properties/{id}:confirm-availability` (reservations-write); FE three lines + "Mark as up-to-date" button + read-only timeline badges (en+el); freshness touches don't bump `updated_at` |
| [GAP-034](done/gap-034-availability-calendar-source-indicator.md) | Sales-view calendar-source indicator: iCal badge + owner calendar link | ✅ resolved (2026-06-21) — `has_active_ical_feed` (N+1-safe `Exists`) + `calendar_url` on property list/detail via a shared serializer mixin (secret feed `url` never serialized); `calendar_url` on `PropertySettings` (migr. `0020`, editable in the Settings tab, server-validated URL); shared `CalendarSourceIndicator` renders badge-wins-over-link in the timeline + AvailabilityTab; en+el; pytest+vitest. Feed-health tooltip + `GroupSettings`/back-office mgmt deferred |
| [GAP-035](done/gap-035-net-gross-commission-derivation.md) | Net↔gross rate entry with automatic commission derivation | ✅ resolved (2026-06-22) — rate-band form derives the counterpart on display (owner net for a GROSS plan, guest price for NET) via the engine's mode-aware commission+tax math (`netGross.ts`, `÷(1−pct)` gross-up, fixed flat, exempt-aware, `ROUND_HALF_EVEN`); **derive-on-display only** (no double-count vs BUG-009). Effective commission/tax + `prices_entered_as_effective` surfaced read-only on the settings endpoint; **`RatePlan.price_basis` is the sole pricing authority**, `prices_entered_as` demoted to the new-season default. pytest+vitest, en+el. Residual closed by BUG-009 (2026-07-02): the owner-statement money path reads snapshot `net_to_owner`; its `prices_entered_as` read is a display label only |
| [GAP-036](done/gap-036-region-filter-property-listing.md) | Region filter on the property listing grid (status filter already exists) | ✅ resolved (2026-06-19) — Region `<Select>` added to the list filter row (country → region → status); slug-valued options (mirrors AvailabilityTimelinePage), URL `region` param read into the list query, en+el i18n; vitest. Reused existing `filter_region`/`toQuery`/`useRegions` — FE-only, no backend change. Country-scoping deferred |
| [GAP-037](done/gap-037-services-as-separate-entity-and-tab.md) | Services as a separate entity + tab, split from season inclusions | ✅ resolved (2026-07-01) — new informational, date-ranged `properties.PropertyService` (option c) replaces free-text `RatePlan.inclusion` on its own **Services** tab; `Extra` untouched (no 4th concept), `RatePlan.inclusion` dropped / `.notes` kept. Engine derives `breakdown["inclusion"]` from active overlapping services (projection maps future stays to anchor year); `seed_inclusions`/`QuotationLine.inclusions` unchanged. 6 units (model→data migr→engine→drop column→API→FE tab) on `feat/gap-037-services`, pytest+vitest, en+el. Deferred: `Feature(INCLUDED_SERVICE)` retirement, structured per-service guest lines, services→comms (GAP-018) |
| [GAP-038](done/gap-038-enquiry-quote-stacking-conversion-metric.md) | Enquiry pipeline: stage taxonomy + quotes-to-convert metric | ✅ resolved (2026-06-19) — stage taxonomy + structured `lost_reason` (Phase 0, migr. 0032–0035) exposed read-only; `quotes_to_convert` query-pinned `SerializerMethodField` + "Converted in N quote(s)" detail badge; per-quote chips already from GAP-005. Rebuild-era only (migrated history reads null) |
| [GAP-039](done/gap-039-enquiry-dashboard-enrichment.md) | Enquiry list/dashboard enrichment to the Ben/owner mockup | ✅ resolved (2026-06-19) — delivered: enriched read columns, inline lead-status edit, lead-status/salesperson/page-size filters, stage tabs (excl. Dead/Converted), en/el i18n. Remaining inline salesperson/stage/lost-reason edits + date-range/delete/select carved out to GAP-050 |
| [GAP-040](done/gap-040-customer-tags-taxonomy.md) | Customer tags taxonomy (VIP/Trade/Disability/…) | ✅ resolved (2026-06-23) — fixed `PersonTag` `ArrayField` on `Person` (10 tags; "Repeat" → derived badge in GAP-042), audited + erasure-scrubbed (special-category), `?tags=` overlap filter; FE checkbox-dialog editor + read-only chips on the contact profile (merge feat/gap-040-041, B1/B2/F1). Enquiry/quote chips + curated taxonomy (Q-021) deferred |
| [GAP-041](done/gap-041-standing-linked-contacts.md) | Standing linked contacts (spouse/child/PA) | ✅ resolved (2026-06-23) — directed `PersonRelationship(from,to,kind)` (DB no-self-link + `(from,to,kind)` unique), one row rendered with an inverse label (CHILD↔PARENT, PA→Principal); merge folds links dropping self-links/dupes/mirrors, anonymize deletes them; `/contacts/{id}/relationships` + "Linked contacts (N)" accordion reusing the GAP-027 picker (B3/B4/F2) |
| [GAP-042](done/gap-042-customer-360-profile-view.md) | Customer 360 profile for the sales team | ✅ resolved (2026-06-23) — assembled over the unified `Person` (compose, no aggregate endpoint): `/contacts/{id}` serializes town/post_code/country(+name) + property-agnostic `booking_count`/`is_repeat_customer` (≥1 booking, gated annotation); FE `CustomerProfilePanel` (identity + Repeat badge + tags + collapsible address + linked-contacts + enquiry & booking history, wiring in the dead `ContactEnquiryHistory`) reused on the contact page and embedded in the enquiry- & quote-detail rails (merge feat/gap-042, B1/F1/F2/F3). Deferred: calls/activity-log (Q-017), rich-text notes, country edit, quote-builder inline embed |
| [GAP-043](done/gap-043-quote-builder-multi-week-range.md) | Quote builder: multi-week date-range selection | ✅ resolved (2026-07-02) — search form **replaced** with the mockup's arrival-window range shape (Arrive from/to + weeks + Search Specific Date), mapped client-side onto the unchanged `search-options` contract (flex = ceil(W/2), 42-day cap); `StayOptionPicker` now multi-select (held stays non-selectable) — each ticked week stages its own line (`line_id`), save fans out weeks × checked bands; enquiry seeds the window symmetrically (± flexibility_days). Deferred: `flexibility_days` widening + "Flexible" enum → GAP-050 item 7. Accepted: flexible-changeover villas single-week (H1); shared band-check across weeks (M2) |
| [GAP-044](done/gap-044-occupancy-band-fanout-builder.md) | Quote builder: occupancy-band fan-out (all bands, default-checked) | ✅ resolved (2026-07-01) — engine `covering_bands` party-independent enumerator (`abf6bcd`); `StayOptionsService` attaches priced `occupancy_bands` per result, POA-flagged, party-independent (`d220f03`); FE checkable default-checked band list + picker-suppressed (`1ca6b3b`) → staged bands + shortlist + save flat-maps one non-manual line per checked non-POA band (`e28c6ea`). Engine single-band contract unchanged; bands are alternatives. Bands×alternate-blocks / per-band override / projection bands deferred |
| [GAP-045](done/gap-045-unify-person-identity.md) | **Unify human identity into one `Person`** (folds in `Guest`; agent off the supply-side bag) | ✅ resolved (2026-06-22) — full expand/contract shipped across 3a–3d / D1–D5 (merge `51feb1a`): `reservations.Guest` + the 5 `guest` FKs deleted; `accounts.Person` is the sole human identity (PersonEmail/PersonPhone children, `kind`, merge/anonymize); legacy import writes `Person` directly (`client-{Id}`) with a one-shot mirror re-key migration; `/contacts` is the unified `?kind=`-filtered directory, `/guests` retired. Unblocks GAP-046/047/048 |
| [GAP-046](done/gap-046-organisation-and-agent-capacity.md) | `Organisation` entity + agent capacity (B2B Companies) | ✅ resolved (2026-06-22) — `accounts.Organisation` (org_type-scoped) + `Person.agency` FK shipped (merge `8184ab2`, 7 units); free-text `Person.company` migrated to Organisation(agency) + dropped (migration `0012`, content-hash dedup + `dedupe_organisations` reporter); FE `/companies` directory + CompanyPicker, contacts form swapped to the agency FK. `.agent` repoint already done in GAP-045. Dissolves GAP-029; mgmt/supplier screens (GAP-048/q-007), agent filter (GAP-047) + FE `:merge` UI deferred |
| [GAP-047](done/gap-047-clients-directory-and-profile.md) | Clients (renter) directory: browsable list + direct/agent filter | ✅ resolved (2026-06-23) — `/clients` list endpoint over customer-capacity `Person` + direct/agent filter, quoted/booked region aggregation (query-pinned) + region chip columns, FE Clients directory page + Sidebar nav/route; pytest+vitest (merge `16680fd`, 4 units). List only — detail = GAP-042, tags = GAP-040, links = GAP-041 |
| [GAP-048](done/gap-048-villa-contacts-directory-and-roles.md) | Suppliers directory (rename from Contacts) + role taxonomy + type surfacing | ✅ resolved (2026-07-01) — `ContactRole` reconciled to verified legacy VillaRoles (+Villa Admin/Mgmt Co, loader remap, `70ad76b`); `Organisation` assignee on `PropertyContactAssignment` (XOR/org-unique/org→mgmt-co constraints + merge dedupe, `d2fcc45`); `?directory=suppliers` scoping + `/contacts`→"Suppliers" relabel + role column + FE role-enum catch-up (`2680240`). Org-assignment **create** UI + suppliers merge-UI + Q-007 vocabulary deferred |
| [GAP-049](done/gap-049-create-property-ui.md) | No "create property" UI — create flow is API-only | ✅ resolved (2026-06-18) — `CreatePropertyDialog` (6-field form, slug auto-derive, category/group hooks + `useRegions`), role-gated "New villa" button (disabled-with-tooltip), `slugify` helper, en+el i18n, unit+component tests; no backend change |
| [GAP-050](gap-050-enquiry-grid-inline-edits-and-controls.md) | Enquiry grid: inline salesperson/stage/lost-reason edits + remaining mockup controls | ⬜ follow-up to GAP-039; inline assign/stage/reason cells, date-range filter UI (params already plumbed), delete (ADMIN) + select columns, page-size 10. Stage-dropdown blocked on `05-reservations.md` decision |
| [GAP-051](gap-051-checkout-charge-itemisation.md) | Itemise charge lines on the guest checkout page | ⬜ deferred until the guest checkout page exists |
| [GAP-052](done/gap-052-contact-detail-edit-completeness.md) | Contact detail: editable address + editable/finished notes + contact-type badges | ✅ resolved (2026-07-01) — editable+audited `Person.country` + FE CountryPicker (`6fd4771`/`020713b`); `contact_types` badges from kind/booking/agency/active-roles (`8cac257`/`58e51a2`); address/notes already writable. Rich-text notes + full-fidelity deal-channel agent deferred |
| [GAP-053](done/gap-053-clients-tag-filters-and-inline-tag-editor.md) | Clients directory: VIP/Trade/Repeat chip filters + inline (no-dialog) client-only tag editor | ✅ resolved (2026-07-01) — widened `/clients` to agent-capacity + `?repeat=`/`?tags=` (`c0efa66`); VIP/Trade/Repeat one-click chips (`4faa233`); inline Popover tag editor (optimistic, audited, replaced TagsFormDialog, `5c1888e`) |
| [GAP-054](gap-054-damage-claims-workflow-remainder.md) | Damage-claims workflow remainder: capture thresholds + Senior Op role, guest damages email + acceptance, capture-guard tightening, photo polish | ⬜ continues BUG-008; wf8 state-machine + photo upload already shipped (merge `c20dc9e`), these are the deferred permission/guest-facing pieces (`03-workflows.md:429/440/447`) |
| [GAP-055](done/gap-055-occupancy-band-week-picker.md) | Quote builder: two-dimensional picker (week choice × occupancy bands) [GAP-044b] | ✅ resolved (2026-07-01) — lifts GAP-044's picker-suppression: a banded villa now shows the **week picker *and* the selected week's bands**; pick a week → its bands fan out → each saves at the chosen week's dates. Almost FE-only, zero new pricing cost (the `flex_days:0` reprice already returns the week's bands; only `stayRepriceSchema` needed the field). `resolvedBands` decoupled from reprice `available` (out-of-bracket stays saveable), checked-by-party-range-identity, `d68c1c1`/`37f6936`/`479b7e3`. Per-week chip "from" price / shortlist week-change / per-band override deferred |
| [GAP-057](done/gap-057-2fa-enforcement-and-refund-stepup.md) | 2FA: staff enrolment enforcement + refund-execution step-up | ✅ resolved (2026-07-02, local main unpushed) — six TDD units: single-use `verify_code` + `tfa_last_verified_step` replay guard; `TfaEnforcementMiddleware` (behind `TFA_ENFORCED`, `/api/`-scoped, allowlisted) + `:disable` guard + `StaffExcludedBasicAuthentication` (review: closes a Basic-auth staff bypass); refund `:execute` step-up (`tfa_code`, `tfa_stepup_required` 403 / `invalid_tfa_code` 400, gated on `TFA_ENFORCED`, `actor=None` exempt); forced-enrolment UX (`Enroll2faPage` QR + recovery ack, boot redirect + 403 interceptor) + step-up dialog. Step-up gated on `TFA_ENFORCED` not always-on (reversible deviation) |
| [GAP-058](gap-058-comms-pull-only-top-of-spine.md) | comms pull-only: retire all 7 blessed comms back-edges (reminder sweep → comms.tasks, password-reset signal, self-mounted email routes) | ⬜ converted from Q-017 (decision recorded 2026-07-02); 3-unit plan + docs in ticket |
| [GAP-056](done/gap-056-rate-model-restructure-property-period-band.md) | Rate-model restructure: `Property → RatePlan → RatePeriod → RateBand`, drop `RateCard` | ✅ resolved (2026-07-01) — two-level rate tree shipped on local `main` (unpushed, `feat/gap-056`, 9 units); `RateCard` dropped, `RatePeriod` owns an inclusive date window + nullable min/max nights, two `btree_gist` EXCLUDEs; period-native everywhere. Subsumes BUG-014 |
| [GAP-059](done/gap-059-rate-period-name-compulsory.md) | `RatePeriod.name` compulsory (model+CHECK, loader/backfill placeholder names, required in dialog, one FE fallback) | ✅ resolved (2026-07-02, local main unpushed) — 4 units: `derive_period_name` + loader names every synthesized period, field required + CHECK + `0017` backfill, required in dialog, one shared FE fallback |
| [GAP-060](done/gap-060-kill-old-pricing-tab.md) | Retire the legacy property "Pricing" tab; rename the Workbench tab to "Rates" | ✅ resolved (2026-07-02) — FE-only on local `main` (unpushed; `7f8fe63`, `f7bd8b9`, `fc27581`). Unit 1: rate-plan create/edit/duplicate/delete + period edit/delete + GAP-026 warning ported into the Workbench (add/duplicate no longer skeleton-blanks the page). Unit 2: renamed "Rates", dropped the Preview badge. Unit 3: deleted PricingTab + RatePlanDetailPanel, `/pricing`→Rates redirect, dropped the writer-only nav gate, pruned dead i18n. Full FE gate green (1642 tests) |
| [GAP-061](gap-061-security-deposit-release-automation.md) | Security-deposit release/refund automation unbuilt (`process_sd_refunds` empty, unscheduled); holds sit open indefinitely | ⬜ from 2026-07-02 complexity audit; real money held on cards; needs idempotency key on the release refund |
| [GAP-062](gap-062-frontend-schema-contract-drift-no-codegen.md) | No frontend↔backend contract check — 20 hand-maintained Zod schemas drift silently from DRF (`currency`/`country` typed number in some features, string in others) | ⬜ from 2026-07-02 frontend complexity audit; add a fixtures contract test or OpenAPI type-gen |
| [GAP-063](done/gap-063-frontend-feature-coupling-and-cycles.md) | Frontend feature boundaries leak — cross-feature imports (rate-workbench→properties ×26) + schema-level cycles (enquiries⇄quotations, properties⇄availability); no import boundary rule | ✅ resolved (2026-07-05) — `eslint-plugin-boundaries` shrink-only ratchet (`boundaries.allowlist.js`, 32→27 pairs) + staleness vitest; rate-workbench folded into `properties/`; all four 2-cycles broken via `src/lib/domain/` + logout-cleanup registry; remaining edge pay-down → GAP-072 |
| [GAP-064](done/gap-064-structured-room-attributes.md) | Structured room attributes — enum-column facets (ensuite type, access) + an admin-editable `RoomAttribute` catalog for open-ended amenities | ✅ resolved (2026-07-05) — shipped with ticket-default A1 vocabulary (all admin-editable data; owner confirmation pending, see `design/decisions.md`); backfill re-run + placement source → GAP-065; derivation → GAP-067 |
| [GAP-065](done/gap-065-room-location-building-floor.md) | Room location: split placement into **building** + **floor** — and fix the lossy migration (`RoomLoader` hardcodes `MAIN_HOUSE`, discards every `PlacementId`) | ✅ resolved (2026-07-05) — two blank-able axes + `placement_note` no-loss preserve + parsing loader + reconcile row + grouped rooms list; shipped on ticket-default A2 ladder (owner confirmation pending, see `design/decisions.md`); ambiguous rungs stay `""`+raw note |
| [GAP-066](done/gap-066-room-bed-size.md) | Bed **size** fidelity (King/Super-king/Emperor) + bed-type vocabulary | ✅ resolved (2026-07-06, local main unpushed) — `BedSize` enum + optional `RoomBeds.double_size` facet (blank = unspecified, no `STANDARD` member) + migration `0031`; positives-only backfill folded into `backfill_room_attrs` (ordered super-king→king, gated on a double bed, per-size counts); FE conditional size select + en/el i18n. Bed **counts** unchanged (parity). Feature-taxonomy cleanup → GAP-067 |
| [GAP-067](gap-067-room-feature-taxonomy-cleanup.md) | Feature taxonomy cleanup + derive property features from room attributes (data-driven bridge) | ⬜ supersedes the taxonomy half of Q-021; de-dupe the ~300-row `VillaFeatures` list (5× aircon, junk rows) with link-remap |
| [GAP-068](done/gap-068-seed-group-finance-settings-defaults.md) | Seed group finance/settings defaults + new-villa starter set | ❌ dropped (2026-07-06) — superseded by **GAP-070** (dropped groups); its default **values** seed the global `PropertyDefaults` singleton, its features-starter half → GAP-067 |
| [GAP-069](done/gap-069-workbench-carry-forward-affordance.md) | Rate-workbench carry-forward affordance — promote a projected year into editable rows | ✅ resolved (2026-07-03, local main unpushed) — FE-only; "Carry rates forward" button in the empty-year state (writer-gated, currency-code + non-past-year gated) → `CarryForwardDialog` (uplift %) → live `…:carry-forward` endpoint; on success new plan selected + year fills in place. No backend change. `f524142`/`e303050`/`62f5f14` |
| [GAP-070](done/gap-070-remove-groups-global-property-defaults.md) | Remove property groups + runtime inheritance; global `PropertyDefaults` singleton + editor UI, snapshot at creation | ✅ resolved (2026-07-06, local main unpushed) — 9 units on `feat/gap-070`: `PropertyDefaults` singleton (`get_solo`, `/property-defaults`) snapshotted into concrete `PropertySettings`/`PropertyFinance` at creation, freeze migration `0027`, `PropertyGroup`/`Group*Settings`/`effective()` deleted (NULL now = genuinely unset → floor/`_POLICY_FALLBACKS`), cutover parity loader + owner-contact finance fallback, FE groups removed + `/admin/property-defaults` editor. **Subsumes GAP-068**, mooted FG-002, reversed FG-003 |
| [GAP-071](gap-071-manual-security-deposit-creation.md) | No way to create a security deposit — auto-creation at booking confirmation is the only path; empty state is a dead end | ⬜ from 2026-07-03 `/bookings/383/payments` investigation (follows `c9e5fac` 204 fix); needs new `SecurityDepositService.create_manual` + POST endpoint + FE empty-state action; 4 open product decisions |
| [GAP-072](gap-072-frontend-boundary-ratchet-paydown.md) | Pay down the remaining boundary-ratchet edges — last 2 mutual cycles (properties⇄contacts, UI-level enquiries⇄quotations), sanctioned-vs-debt allowlist tiering, geo/taxonomy home decision | ⬜ GAP-063 residue (2026-07-05); incremental, one edge-group per commit; coordinates `lib/domain` lifts with GAP-062 |
| [GAP-073](done/gap-073-legacy-loader-bulletproofing-reconcile.md) | Legacy-loader bullet-proofing — land the remainder + reconcile the branch against post-GAP-070/065 main | ✅ done (2026-07-07) — reconciled onto `main` as 6 TDD units (web-copy, Zoho/Temenos, availability loader, loadlegacy crash-isolation, reconcile calibration + guest-pref order, standards docs). GroupMap expansion dropped + finance IsDefault* deferred (owner calls). Live dry-run on the 24-Apr dump: `loadlegacy --all` exit 0, every GAP-073 reconcile check green. Surfaced 3 pre-existing follow-ups (not GAP-073): reconcile blockers `Room placement (GAP-065)` gap 49 + `PropertyFinance (GAP-070)` off-by-one, and the `test_dashboard_activity` full-parallel-suite isolation flake |
| [GAP-074](gap-074-nightly-price-quoting-no-changeover.md) | Nightly-price quoting for no-fixed-changeover villas (full available range + per-night, banded) | ⬜ from 2026-07-08 Nick call; engine has per-night data, no output path; **⚠️ owner/Debbie call gates build** (two-tier weekly-vs-nightly presentation) |
| [GAP-075](gap-075-per-line-flexible-min-nights-override.md) | Per-quote-line ad-hoc flexible stay (min-nights + nightly), independent of property changeover | ⬜ from 2026-07-08 Nick call (late-season "flexible from now, with a minimum"); depends on GAP-074 |
| [GAP-076](done/gap-076-non-commissionable-extras.md) | `commissionable` flag on `Extra` (+ `BookingChargeItem`) — non-commissionable extras reduce commission base but stay in guest total | ✅ resolved (2026-07-10) — flag on both models (default True), engine commission base = rate_subtotal + commissionable extras − discounts with **full pass-through** for non-commissionable extras (excluded from commission AND tax, never discounted; GAP-079 coordination closed, no per-villa toggle), snapshot records `commission_base` + `extras_non_commissionable_total` for GAP-077, per-line charge owner-effect via shared `charges_owner_adjustments`, FE checkboxes + non-commissionable tags in workbench/probe/FinanceTab |
| [GAP-077](done/gap-077-deposit-balance-gross-net-split.md) | Gross/net/commission split per payment component (deposit & balance), not just whole-booking | ✅ resolved (2026-07-10) — derive-on-read `payment_component_splits` (pro-rata by scheduled gross, residual to BALANCE, tax surfaced per component, GAP-076 charge overlay riding along), staff detail `payment_splits` + `get_net_to_owner` consolidation, owner detail-only behind `view_full_money`, FE FinanceTab split table + owner-portal cards (en+el); INTERIM deferred (allocator already N-component); track semantics set-equality-pinned in payments/tests |
| [GAP-078](gap-078-quote-property-ordering-country-region.md) | Quote property ordering — group picker + email by country/region + weekly-vs-nightly section break | ⬜ from 2026-07-08 Nick call; picker is alphabetical, email is insertion-order; email section needs GAP-074/075 |
| [GAP-079](done/gap-079-commission-after-local-vat.md) | Commission-after-local-VAT — verify GROSS branch matches real villa numbers + per-villa policy | ✅ resolved (2026-07-09) — verify-only: the GROSS branch already takes VAT off the gross then commission off the remainder (legacy `RatesModel.Calculate()` parity), **no per-villa toggle** (ordering is a function of `price_basis`; decision row in `design/decisions.md`); constructed 13%/20%/10,000 worked example pinned engine-side + through the 30/70 deposit/balance split (re-reconcile when Nick supplies real villa numbers); extras-taxability handed to GAP-076 via a coordination note |
| [GAP-080](gap-080-currency-obvious-in-quote-builder.md) | Make currency unmistakable in the quote **builder** UI (email already shows codes) | ⬜ from 2026-07-08 Nick call; FE-only; builder `formatMoney` is symbol-only for £/€/$ |

## Open product questions

| Id | Title | Status |
|---|---|---|
| [Q-010](q-010-guest-data-retention.md) | Guest data retention / GDPR | ⬜ |
| [Q-018](q-018-rate-reduction-vs-carryover.md) | Rate reductions: base price + reduction so carry-over copies the base | ⬜ all questions answered + design decided 2026-07-02 (field shape, hazards, 8-unit build sketch in ticket); build not started |
| [Q-019](done/q-019-structured-room-attributes.md) | Structured room attributes (bath/shower, aircon, views, accessibility, floor) | ✅ superseded (2026-07-02) by **GAP-064/065/066** — legacy-grounded build tickets; the A1/A2 owner-vocabulary decision is carried in their "Owner steer" sections |
| [Q-020](q-020-description-sections-parity.md) | Description sections: spec enum vs sections actually written | ⬜ |
| [Q-021](done/q-021-defaults-and-feature-taxonomy.md) | Seed group defaults + curate feature taxonomy | ✅ superseded (2026-07-02) — split into **GAP-067** (feature taxonomy + room→property derivation) and **GAP-068** (group-defaults seeding, buildable now); groups stay |
| [Q-022](q-022-seasons-defined-by-rates.md) | Seasons defined by rental rates not services | ⬜ owner answer recorded (season = named tier over rate bands); tier-list confirmation drafted (C1, [owner-questions-2026-07-02.md](owner-questions-2026-07-02.md)) |
| [Q-023](q-023-partial-week-nightly-composition.md) | Partial-week / nightly price composition for odd-length stays | ⬜ rounding + fallback already done; confirmation questions drafted (D1–D3, [owner-questions-2026-07-02.md](owner-questions-2026-07-02.md)); docs+tests half can proceed ahead of answers |
| [Q-024](q-024-signals-as-control-flow.md) | Cross-app money/lifecycle side-effects: stay on domain signals, or move to explicit orchestration? | ⬜ from 2026-07-02 complexity audit; architecture direction — blocks SMELL-020/BUG-015/GAP-061 |

## Decisions blocking implementation

Highest-leverage unanswered questions (each blocks a slice of downstream work):

- **Q-024** — Signals vs explicit orchestration for cross-app money side-effects (architecture; blocks SMELL-020, BUG-015, GAP-061)

(GAP-064 A1 + GAP-065 A2 owner-vocabulary confirmations are pending but no
longer block code — both shipped on ticket defaults with everything
vocabulary-shaped either admin-editable data or re-parseable from the
preserved `placement_note`; see `design/decisions.md` Open follow-ups.)

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
| [Q-007](done/q-007-concierge-supplier-directory.md) | Concierge supplier shape → contact-only (`Person`/`Organisation`), no `Supplier` entity |
| [Q-008](done/q-008-2fa-enforcement.md) | 2FA enforcement → all staff forced to enrol + always-fresh refund step-up; build plan → GAP-057 |
| [Q-009](done/q-009-multi-site-inventory-sharing.md) | Multi-site inventory sharing → single site v1 |
| [Q-011](done/q-011-email-template-inheritance.md) | Email template inheritance → system → site |
| [Q-013](done/q-013-rate-card-incomplete-pricing.md) | Rate-card incomplete pricing → flag + manual quote |
| [Q-014](done/q-014-audit-log-retention.md) | Audit-log retention → keep forever + scrub, admin-only |
| [Q-015](done/q-015-owner-financial-visibility.md) | Owner financial visibility defaults |
| [Q-016](done/q-016-payment-ledger-vs-dedicated-models.md) | Payment ledger vs dedicated SD → Lane A |
| [Q-017](done/q-017-comms-direction-signals-vs-spine-position.md) | comms direction → stays top-of-spine, strictly pull-only (signals + own beat sweeps); build plan → GAP-058 |
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
| [GAP-020](done/gap-020-direct-booking-creation.md) | Direct booking creation (legacy "book now") | Sidelined 2026-07-01 — legacy has no standalone direct booking (always quote-first); owner never requested it and the booking flow is un-validated (`10-decisions.md:132`). Revive only post owner walkthrough |
| [GAP-003](done/gap-003-endpoint-coverage-gap.md) | Endpoint coverage gap | framing only |
| [GAP-016](done/gap-016-rental-price-override.md) | Rental-price override (legacy parity remainder) | superseded by signed `BookingChargeItem` charge line |
| [SMELL-005](done/smell-005-residual-property-country-charfield.md) | Residual `Property.country` free-text | verified clean |
