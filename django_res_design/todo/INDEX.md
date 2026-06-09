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
| [BUG-005](bug-005-stale-bookinghold-blocks-bookings.md) | Stale `BookingHold` rows block valid bookings | ✏️ revise: prefer sweeper + opportunistic expire |
| [BUG-006](bug-006-payment-active-purpose-uniqueness.md) | `Payment.unique_active_payment_per_purpose` covers only DEPOSIT/BALANCE | ✅ resolved (three per-purpose constraints; SD hold superseded by capture) |
| [BUG-007](bug-007-reference-generation-races.md) | Reference generation races + `bulk_create` bypass | ✅ resolved (sequence + `db_default` on E/P/R/SD; race + retry + bulk_create bypass gone) |
| [BUG-008](bug-008-securitydeposit-damageclaim-fk.md) | `SecurityDeposit.damage_claim_id` is a fake FK | ⬜ (decision-blocked) |
| [BUG-009](bug-009-price-basis-ignored-by-engine.md) | Engine ignores `RatePlan.price_basis` — GROSS plans mis-priced | ⬜ (spec done; code deferred to finance rewrite) |

## 🟠 Footguns

| Id | Title | Status |
|---|---|---|
| [FG-001](fg-001-booking-quotation-currency-drift.md) | Booking ↔ Quotation currency drift | ✏️ revise: drop "silent corruption" framing |
| [FG-002](fg-002-effective-null-vs-empty-string.md) | `effective()` conflates `""` and `NULL` | ⬜ (consider downgrade to smell) |
| [FG-003](fg-003-effective-crashes-on-null-group.md) | `effective()` crashes if `property.group` is null | ❌ DROPPED — `Property.group` is non-nullable |
| [FG-004](fg-004-payment-purpose-field-coherence.md) | Payment fields not gated by `purpose` | ✅ resolved — 3 check constraints (refund no `due_at`, `concierge_item` CONCIERGE-only, refund `amount >= 0`) |
| [FG-005](fg-005-idempotency-user-required.md) | `IdempotencyRecord.user` required; system actors blocked | ✏️ revise: resolve dead-vs-live status first |
| [FG-006](fg-006-modify-without-select-for-update.md) | `modify_dates` / `modify_guests` re-run pricing without row locks | ✅ resolved (row lock + reload) |
| [FG-007](fg-007-syncrecord-genericfk-dangling.md) | `SyncRecord` GenericFK leaves dangling rows | ✅ resolved (post_delete cleanup via registry) |
| [FG-008](fg-008-property-timezone.md) | Property has no timezone | ✅ resolved — `PropertyLocation.timezone` + `services/timing.py` seam + REST/FE surface |
| [FG-009](fg-009-csrf-prime-coupled-to-shell-server.md) | CSRF priming coupled to HTML-shell server — recurring dev double-login | ⬜ (low priority — not vital) |

## 🟡 Smells

| Id | Title | Status |
|---|---|---|
| [SMELL-001](smell-001-archived-vs-status.md) | `archived_at` is a second status | ⬜ |
| [SMELL-002](smell-002-quotation-expire-draft.md) | `Quotation.expire()` only handles `SENT → EXPIRED` | ✅ resolved (DRAFT/SENT → EXPIRED) |
| [SMELL-003](smell-003-currency-decimal-places-unenforced.md) | `Currency.decimal_places` informational only | ⬜ |
| [SMELL-004](smell-004-emaillog-content-hash-scope.md) | `EmailLog` content hash dedupe scope ambiguous | ✅ resolved (documented + pinning test) |
| [SMELL-005](smell-005-residual-property-country-charfield.md) | Verify no residual `Property.country` free-text | ❌ DROPPED — verified clean |
| [SMELL-006](smell-006-terms-accepted-at-required-no-default.md) | `terms_accepted_at` required, no default | ⬜ (**upgrade to 🟠 footgun**) |
| [SMELL-007](smell-007-occupancy-fallback-doc-claim.md) | Spec misstates legacy occupancy fallback (not "highest bracket") | ✅ resolved (doc-only) |

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
| [Q-013](q-013-rate-card-incomplete-pricing.md) | Rate-card "incomplete pricing" behaviour | ⬜ |
| [Q-014](q-014-audit-log-retention.md) | Audit log retention window | ✏️ split into audit-retention vs PII-retention |
| [Q-015](q-015-owner-financial-visibility.md) | Owner financial visibility defaults | ✅ resolved — `OwnerOrgProperty.view_full_money`/`view_guest_details` default hidden, per-property; redaction wired |
| [Q-016](q-016-payment-ledger-vs-dedicated-models.md) | `Payment` ledger vs dedicated `SecurityDeposit` — pick a lane | ✏️ Lane A taken implicitly in code (Payment-as-ledger; 3 per-purpose constraints) — record in `10-decisions.md`; no longer blocks |

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
| [GAP-012](gap-012-cloudflare-images-hosting.md) | Object-storage image hosting (Cloudflare Images) for staging & prod — incl. legacy binary import (nested→flat `legacy_id` reconstruction) | ⬜ open — specced, building on `feat/s3-image-hosting` |
| [GAP-013](gap-013-quote-builder-ux-feedback-loops.md) | Quote builder UX: tighten feedback loops (invalid-line flag, remove-undo, currency-change confirm, unpriceable-result note, a11y) | ⬜ open — FE polish, sibling of GAP-005 |

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
- **Q-013** — Rate-card incomplete-pricing behaviour (blocks quote builder)
- **Q-006** — Owner statement cadence + delivery (no code exists yet)
- **BUG-008** — `DamageClaim` in v1? (scope call; blocks SD damage slice)

Recently unblocked / resolved (was on this list): **Q-002** owner SLA
(partially built), **Q-015** owner financial visibility (resolved),
**Q-016** ledger lane (taken in code — just needs recording).
