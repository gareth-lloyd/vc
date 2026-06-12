# Todo Index

Quick scan of every open ticket. See `README.md` for conventions and
the recommended fix order. See `CRITIQUE-2026-05-27.md` for the
synthesis of the agent-driven critical review that drove the status
changes below.

Status icons:
- ⬜ open (default)
- ✅ closed / resolved with finding
- ❌ dropped (premise false / framing-only / verified clean)
- ✏️ needs revision before implementing

## 🔴 Bugs

| Id | Title | Status |
|---|---|---|
| [BUG-001](bug-001-cancelled-status-requires-cancelled-at.md) | `CANCELLED` status must imply `cancelled_at IS NOT NULL` | ✅ resolved |
| [BUG-002](bug-002-raterule-zero-length-range.md) | `RateRule` allows zero-length date ranges | ✅ resolved |
| [BUG-003](bug-003-raterule-poa-vs-price-contradiction.md) | `RateRule` lets `is_poa=True` coexist with a numeric price | ✅ resolved |
| [BUG-004](bug-004-owner-approval-race.md) | Owner-approval race | ✅ resolved (promote "Watch" item) |
| [BUG-005](bug-005-stale-bookinghold-blocks-bookings.md) | Stale `BookingHold` rows block valid bookings | ✅ resolved (opportunistic expire in place/update_block/move; EXCLUDE violation → `HoldUnavailable`) |
| [BUG-006](bug-006-payment-active-purpose-uniqueness.md) | `Payment.unique_active_payment_per_purpose` covers only DEPOSIT/BALANCE | ✅ resolved (three per-purpose constraints; SD hold superseded by capture) |
| [BUG-007](bug-007-reference-generation-races.md) | Reference generation races + `bulk_create` bypass | ✅ resolved (sequence + `db_default` on E/P/R/SD; race + retry + bulk_create bypass gone) |
| [BUG-008](bug-008-securitydeposit-damageclaim-fk.md) | `SecurityDeposit.damage_claim_id` is a fake FK | ⬜ (decision-blocked) |
| [BUG-009](bug-009-price-basis-ignored-by-engine.md) | Engine ignores `RatePlan.price_basis` — GROSS plans mis-priced | ⬜ (spec done; code deferred to finance rewrite) |
| [BUG-010](bug-010-refund-self-approve-constraint-conflict.md) | Refund self-approve permission conflicts with the SoD constraint → IntegrityError 500 | ✅ resolved (option 1: bypass dropped from `approve()`, kept on `execute()`) |
| [BUG-011](bug-011-security-deposit-bare-valueerror-500s.md) | SD service raises bare `ValueError` → 500s; zero log events on the SD money path | ✅ resolved (typed `InvalidSecurityDepositKind` + `log_operation` on the SD money path) |
| [BUG-012](bug-012-auditlog-retains-pii-after-anonymize.md) | `AuditLog` retains cleartext PII after `anonymize()`/`merge()` — GDPR erasure hole | ⬜ |

## 🟠 Footguns

| Id | Title | Status |
|---|---|---|
| [FG-001](fg-001-booking-quotation-currency-drift.md) | Booking ↔ quotation-line currency drift | ✅ resolved via GAP-014 (per-line invariant enforced at write time + pinned test; modify_dates fails loud) |
| [FG-002](fg-002-effective-null-vs-empty-string.md) | `effective()` conflates `""` and `NULL` | ⬜ (consider downgrade to smell) |
| [FG-003](fg-003-effective-crashes-on-null-group.md) | `effective()` crashes if `property.group` is null | ❌ DROPPED — `Property.group` is non-nullable |
| [FG-004](fg-004-payment-purpose-field-coherence.md) | Payment fields not gated by `purpose` | ✅ resolved — 3 check constraints (refund no `due_at`, `concierge_item` CONCIERGE-only, refund `amount >= 0`) |
| [FG-005](fg-005-idempotency-user-required.md) | `IdempotencyRecord.user` required; system actors blocked | ✏️ revise: resolve dead-vs-live status first |
| [FG-006](fg-006-modify-without-select-for-update.md) | `modify_dates` / `modify_guests` re-run pricing without row locks | ✅ resolved (row lock + reload) |
| [FG-007](fg-007-syncrecord-genericfk-dangling.md) | `SyncRecord` GenericFK leaves dangling rows | ✅ resolved (post_delete cleanup via registry) |
| [FG-008](fg-008-property-timezone.md) | Property has no timezone | ✅ resolved — `PropertyLocation.timezone` + `services/timing.py` seam + REST/FE surface |
| [FG-009](fg-009-csrf-prime-coupled-to-shell-server.md) | CSRF priming coupled to HTML-shell server — recurring dev double-login | ⬜ (low priority — not vital) |
| [FG-010](fg-010-idempotency-races-no-db-backstop.md) | Idempotency is check-then-create with no DB backstop (meta key, `Booking.quotation_line`, over-refund aggregate) | ⬜ |
| [FG-011](fg-011-adjustment-recompute-skips-bulk-paths.md) | `Booking.adjustment` recompute rides signals; bulk writes desync it | ⬜ |
| [FG-012](fg-012-track-payments-view-bypasses-ledger.md) | Track-payments POST creates ledger rows straight from `request.data` (mintable SUCCEEDED, 500 on bad amount) | ✅ |
| [FG-013](fg-013-owners-app-outside-layers-contract.md) | `owners` app sits outside the import-linter layers contract | ⬜ |
| [FG-014](fg-014-audit-tracking-gaps.md) | Audit-tracking gaps: SecurityDeposit, Enquiry, Quotation untracked | ⬜ |
| [FG-015](fg-015-booking-cancel-leaves-pending-payments.md) | `Booking.cancel` leaves PENDING Payment rows live | ⬜ (depends on feat/backend-review-fixes) |
| [FG-016](fg-016-audit-signals-skip-bulk-writes.md) | Audit signals skip bulk writes; merge FK rewrites unaudited (spec claims otherwise) | ⬜ |
| [FG-017](fg-017-audit-coverage-second-tier.md) | Audit-coverage second tier: BookingHold, Property, property-child hard deletes | ⬜ (after FG-014) |

## 🟡 Smells

| Id | Title | Status |
|---|---|---|
| [SMELL-001](smell-001-archived-vs-status.md) | `archived_at` is a second status | ⬜ |
| [SMELL-002](smell-002-quotation-expire-draft.md) | `Quotation.expire()` only handles `SENT → EXPIRED` | ✅ resolved (DRAFT/SENT → EXPIRED) |
| [SMELL-003](smell-003-currency-decimal-places-unenforced.md) | `Currency.decimal_places` informational only | ⬜ |
| [SMELL-004](smell-004-emaillog-content-hash-scope.md) | `EmailLog` content hash dedupe scope ambiguous | ✅ resolved (documented + pinning test) |
| [SMELL-005](smell-005-residual-property-country-charfield.md) | Verify no residual `Property.country` free-text | ❌ DROPPED — verified clean |
| [SMELL-006](smell-006-terms-accepted-at-required-no-default.md) | `terms_accepted_at` required, no default | ✅ resolved (convert API requires `terms_accepted: true`; stamped server-side) |
| [SMELL-007](smell-007-occupancy-fallback-doc-claim.md) | Spec misstates legacy occupancy fallback (not "highest bracket") | ✅ resolved (doc-only) |
| [SMELL-008](smell-008-service-layer-contract-single-island.md) | Service-layer contract (perms / `log_operation` / idempotency) fully implemented in one file | ⬜ |
| [SMELL-009](smell-009-duplicate-implemented-three-ways.md) | "Duplicate" implemented three ways; no clone endpoint is idempotent | ⬜ |
| [SMELL-010](smell-010-error-signalling-forks.md) | Three coexisting error-signalling patterns in the service layer | ⬜ |
| [SMELL-011](smell-011-bare-querysets-missing-query-pins.md) | Bare `.objects.all()` querysets; `accounts`/`pricing` lack query pins | ⬜ |
| [SMELL-012](smell-012-module-structure-drift.md) | Module-structure drift: filters / services / routers / views-in-urls | ⬜ |
| [SMELL-013](smell-013-one-model-per-file-doc-drift.md) | "One model per file" rule is fiction; de-facto rule is one aggregate per file | ⬜ (doc-only) |
| [SMELL-014](smell-014-quotation-synthesised-row-guard-structural.md) | Synthesised `booking-` quotation rows: make the exclusion structural | ⬜ |
| [SMELL-015](smell-015-comms-smtp-no-transient-retry.md) | Email send marks FAILED on any SMTP error; no transient retry | ⬜ |
| [SMELL-016](smell-016-audit-actor-threadlocal-not-asgi-safe.md) | Audit actor capture rides `threading.local`; breaks silently under ASGI | ⬜ |
| [SMELL-017](smell-017-cart-naming-vs-shortlist-copy.md) | Quote-builder code still says "cart"; user copy now says "Shortlist" | ⬜ |

## Open product questions

| Id | Title | Status |
|---|---|---|
| [Q-001](q-001-cancellation-policy-thresholds.md) | Cancellation policy thresholds | ✏️ partially answered — re-scope to "bands in v1?" |
| [Q-002](q-002-owner-pre-approval-sla.md) | Owner pre-approval SLA | ✏️ partially answered — 24h `escalate_pending_owner_approvals` task (count-only); window not configurable, auto-approve TBD |
| [Q-003](q-003-channel-sync-scope.md) | Channel sync scope (Airbnb / Booking.com / VRBO) | ✅ resolved — out of v1 |
| [Q-004](q-004-hold-expiry-default.md) | Hold expiry default | ✅ resolved (shape) — numeric default TBD |
| [Q-005](q-005-currency-display-base.md) | Reports base currency + FX source | ⬜ |
| [Q-006](q-006-owner-statement-scheduling.md) | Owner statement cadence + delivery | ⬜ |
| [Q-007](q-007-concierge-supplier-directory.md) | Concierge supplier directory shape | ⬜ |
| [Q-008](q-008-2fa-enforcement.md) | 2FA enforcement scope | ⬜ |
| [Q-009](q-009-multi-site-inventory-sharing.md) | Multi-site inventory sharing | ✅ resolved — single site v1 |
| [Q-010](q-010-guest-data-retention.md) | Guest data retention / GDPR | ⬜ |
| [Q-011](q-011-email-template-inheritance.md) | Email template inheritance chain | ✅ resolved — system → site, no property layer |
| [Q-013](q-013-rate-card-incomplete-pricing.md) | Rate-card "incomplete pricing" behaviour | ✅ resolved — flag + manual quote per legacy NO RATE; builder affordance built (no-rate cards stage manual lines) |
| [Q-014](q-014-audit-log-retention.md) | Audit log retention window | ✏️ recommendation recorded: keep-forever + BUG-012 scrub; exposure half blocks GAP-021 |
| [Q-015](q-015-owner-financial-visibility.md) | Owner financial visibility defaults | ✅ resolved — `OwnerOrgProperty.view_full_money`/`view_guest_details` default hidden, per-property; redaction wired |
| [Q-016](q-016-payment-ledger-vs-dedicated-models.md) | `Payment` ledger vs dedicated `SecurityDeposit` — pick a lane | ✅ resolved — Lane A (Payment-as-ledger; 3 per-purpose constraints); recorded in `10-decisions.md` 2026-06-12 |
| [Q-017](q-017-comms-direction-signals-vs-spine-position.md) | comms: signals-only sink, or move it down the spine? | ⬜ |
| [Q-018](q-018-rate-reduction-vs-carryover.md) | Rate reductions: base price + reduction so carry-over copies the base | ⬜ |
| [Q-019](q-019-structured-room-attributes.md) | Structured room attributes (bath/shower, aircon, views, accessibility, floor) | ⬜ |
| [Q-020](q-020-description-sections-parity.md) | Description sections: spec enum vs sections actually written (verify vs legacy site) | ⬜ |
| [Q-021](q-021-defaults-and-feature-taxonomy.md) | Seed group defaults (30% deposit, SD required, 16:30/10:30) + curate feature taxonomy | ⬜ |

Q-012 was resolved (Payment gateway → Flywire).

## Surface gaps

| Id | Title | Status |
|---|---|---|
| [GAP-001](gap-001-comms-empty-url-surface.md) | `comms/urls.py` empty | ✅ resolved (slice 1: EmailLog list+detail) |
| [GAP-002](gap-002-integrations-empty-url-surface.md) | `integrations/urls.py` empty | ⬜ **highest-leverage gap** (Flywire webhook) |
| [GAP-003](gap-003-endpoint-coverage-gap.md) | Endpoint coverage gap vs. designed surface | ❌ DROPPED — framing only |
| [GAP-004](gap-004-frontend-coming-soon-tabs.md) | Frontend "Coming Soon" tabs | ✅ resolved — stale; all configured tabs built, placeholder mechanism dormant |
| [GAP-005](gap-005-quotation-flow-parity.md) | Enquiry→Quotation flow parity vs legacy + spine UX overhaul | ⬜ (tracker) |
| [GAP-006](gap-006-legacy-reference-format-parity.md) | Customer-facing reference format must match legacy (`VC`/`QVC`) | ✅ resolved — `core/refs.py`, sequence-backed quotation numbers, `test_references.py` |
| [GAP-007](gap-007-changeover-autoshift-parity.md) | Changeover auto-shift dropped vs legacy — reinstate | ✅ resolved |
| [GAP-008](gap-008-no-rate-night-fallback-parity.md) | No-rate-for-night fallback dropped vs legacy — reinstate via `RatePlan.fallback_nightly` | ✅ resolved |
| [GAP-009](gap-009-discount-loose-ends.md) | Discount loose ends: REPEAT_GUEST dead, `uses_count` inert, `DiscountApply` dropped | ✅ resolved (now-slice; `uses_count`/`max_uses` deferred) |
| [GAP-011](gap-011-ical-feed-ingest.md) | iCal feed ingest from owners — consolidated spec + verified assumptions | ⬜ deferred (v2 tracker) |
| [GAP-012](gap-012-s3-image-hosting.md) | S3 image hosting for staging & prod (simple v1: no resizing, uploads via Django) — incl. legacy binary import (nested→flat `legacy_id` reconstruction) | 🟨 code complete — PR-A landed; PR-B built (`import_legacy_images` + cutover runbook); remaining: ops prereqs + executing the runbook (staging/prod import runs) |
| [GAP-013](gap-013-quote-builder-ux-feedback-loops.md) | Quote builder UX: tighten feedback loops (invalid-line flag, remove-undo, unpriceable-result note, a11y; item 3 moot per GAP-014) | ⬜ open — FE polish, sibling of GAP-005 |
| [GAP-014](gap-014-quote-currency-forced-selection.md) | Quote builder forces currency selection — legacy prices each villa in its rate card's currency (per-line) | ✅ resolved (per-line currency end-to-end; header field dropped; GAP-013 item 3 moot) |
| [GAP-020](gap-020-direct-booking-creation.md) | Direct booking creation (legacy rate-lookup "book now") — synthetic-quotation design; resolves GAP-006's numbering sub-question; folds SMELL-014's `kind` fix | ⬜ design ready; implementation deferred |
| [GAP-021](gap-021-audit-history-ui.md) | Per-entity "History" tab in the SPA (audit-log surface; backend filters already exist) | ⬜ blocked by Q-014 exposure decision |
| [GAP-022](gap-022-per-property-feature-ordering.md) | Per-property feature display ordering dropped vs legacy (`MappingOrder`) — reinstate via through model | ⬜ spec-vs-reality disagreement |
| [GAP-023](gap-023-owner-approval-preview-lifecycle.md) | `live_offline` replacement: `owner_approved_at` + draft preview link + sales-facing unapproved/unconfirmed badges | ⬜ |
| [GAP-024](gap-024-incremental-loading-required-fields.md) | FE required-field posture fights incremental loading — relax room/capacity write schemas | ⬜ |
| [GAP-025](gap-025-changeover-aware-rate-band-dates.md) | Changeover-aware rate-band end-date suggestion (Sat→Fri auto-fill) | ⬜ |
| [GAP-026](gap-026-currency-display-money-fields.md) | Show property currency beside money fields (decision: single currency per property, no mixing) | ⬜ |
| [GAP-027](gap-027-inline-contact-creation-primary-convention.md) | Inline contact creation from the property + record per-role primary convention | ⬜ |

## Investigations

| Id | Title | Status |
|---|---|---|
| [INV-001](inv-001-propertycontactassignment-owner-uniqueness.md) | `PropertyContactAssignment` owner uniqueness | ✅ closed — invariant present via `is_primary` |
| [INV-002](inv-002-raterule-priority-tiebreak.md) | `RateRule.priority` tie-break behaviour | ✅ closed — deterministic + tested |
| [INV-003](inv-003-refund-amount-sign-convention.md) | `Refund.amount` sign convention | ✅ closed — partition-by-purpose, no signed sum |
| [INV-004](inv-004-syncrun-syncissue-retry.md) | `SyncRun` / `SyncIssue` failure handling | ✅ closed — execution unbuilt (v1.1); schema adequate, retry-cap noted |
| [INV-005](inv-005-legacy-id-indexing-consistency.md) | `legacy_id` indexing consistency | ✅ closed — contract holds |

## Cheapest first commits

Three constraint-tighten tickets, no design questions, no data risk:

1. **BUG-001** — `cancelled_at IS NOT NULL ↔ status=CANCELLED` inverse constraint
2. **BUG-002** — `RateRule` zero-length range (`__lte` → `__lt`)
3. **BUG-003** — `RateRule` POA-vs-price mutex (split into floor + mutex constraints)

After those three, the next-highest-value moves are:

- **FG-006** (promote to bug): `select_for_update` on every booking
  status-transition path
- ~~**BUG-007** (revise first): pick a `bulk_create`-safe approach~~ —
  resolved via sequence + `db_default` (feat/reference-sequence)

## Decisions still blocking implementation

Highest-leverage unanswered Qs (block lots of downstream work):

- **Q-005** — Reports base currency + FX source (blocks every report)
- **Q-006** — Owner statement cadence + delivery (no code exists yet)
- **BUG-008** — `DamageClaim` in v1? (scope call; blocks SD damage slice)

Recently unblocked / resolved (was on this list): **Q-002** owner SLA
(partially built), **Q-013** incomplete pricing (flag + manual quote,
built), **Q-015** owner financial visibility (resolved), **Q-016**
ledger lane (Lane A recorded in `10-decisions.md`).
