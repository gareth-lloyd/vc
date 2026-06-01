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
| [BUG-001](bug-001-cancelled-status-requires-cancelled-at.md) | `CANCELLED` status must imply `cancelled_at IS NOT NULL` | ⬜ |
| [BUG-002](bug-002-raterule-zero-length-range.md) | `RateRule` allows zero-length date ranges | ⬜ (pre-check legacy data) |
| [BUG-003](bug-003-raterule-poa-vs-price-contradiction.md) | `RateRule` lets `is_poa=True` coexist with a numeric price | ⬜ |
| [BUG-004](bug-004-owner-approval-race.md) | Owner-approval race | ✅ resolved (promote "Watch" item) |
| [BUG-005](bug-005-stale-bookinghold-blocks-bookings.md) | Stale `BookingHold` rows block valid bookings | ✏️ revise: prefer sweeper + opportunistic expire |
| [BUG-006](bug-006-payment-active-purpose-uniqueness.md) | `Payment.unique_active_payment_per_purpose` covers only DEPOSIT/BALANCE | ⬜ (refactor to three per-purpose constraints) |
| [BUG-007](bug-007-reference-generation-races.md) | Reference generation races + `bulk_create` bypass | ✏️ **fix is wrong** — `pre_save` doesn't fire on `bulk_create` |
| [BUG-008](bug-008-securitydeposit-damageclaim-fk.md) | `SecurityDeposit.damage_claim_id` is a fake FK | ⬜ (decision-blocked) |

## 🟠 Footguns

| Id | Title | Status |
|---|---|---|
| [FG-001](fg-001-booking-quotation-currency-drift.md) | Booking ↔ Quotation currency drift | ✏️ revise: drop "silent corruption" framing |
| [FG-002](fg-002-effective-null-vs-empty-string.md) | `effective()` conflates `""` and `NULL` | ⬜ (consider downgrade to smell) |
| [FG-003](fg-003-effective-crashes-on-null-group.md) | `effective()` crashes if `property.group` is null | ❌ DROPPED — `Property.group` is non-nullable |
| [FG-004](fg-004-payment-purpose-field-coherence.md) | Payment fields not gated by `purpose` | ⬜ |
| [FG-005](fg-005-idempotency-user-required.md) | `IdempotencyRecord.user` required; system actors blocked | ✏️ revise: resolve dead-vs-live status first |
| [FG-006](fg-006-modify-without-select-for-update.md) | `modify_dates` / `modify_guests` re-run pricing without row locks | ⬜ (**upgrade to 🔴 bug** — lost-update race) |
| [FG-007](fg-007-syncrecord-genericfk-dangling.md) | `SyncRecord` GenericFK leaves dangling rows | ⬜ (downgrade to smell — no live targets) |
| [FG-008](fg-008-property-timezone.md) | Property has no timezone | ⬜ (**upgrade to 🔴 bug** — breaks every wall-clock reminder) |

## 🟡 Smells

| Id | Title | Status |
|---|---|---|
| [SMELL-001](smell-001-archived-vs-status.md) | `archived_at` is a second status | ⬜ |
| [SMELL-002](smell-002-quotation-expire-draft.md) | `Quotation.expire()` only handles `SENT → EXPIRED` | ⬜ |
| [SMELL-003](smell-003-currency-decimal-places-unenforced.md) | `Currency.decimal_places` informational only | ⬜ |
| [SMELL-004](smell-004-emaillog-content-hash-scope.md) | `EmailLog` content hash dedupe scope ambiguous | ⬜ (contract is documented in code — add pinning test or close) |
| [SMELL-005](smell-005-residual-property-country-charfield.md) | Verify no residual `Property.country` free-text | ❌ DROPPED — verified clean |
| [SMELL-006](smell-006-terms-accepted-at-required-no-default.md) | `terms_accepted_at` required, no default | ⬜ (**upgrade to 🟠 footgun**) |

## Open product questions

| Id | Title | Status |
|---|---|---|
| [Q-001](q-001-cancellation-policy-thresholds.md) | Cancellation policy thresholds | ✏️ partially answered — re-scope to "bands in v1?" |
| [Q-002](q-002-owner-pre-approval-sla.md) | Owner pre-approval SLA | ⬜ **highest leverage** |
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
| [Q-015](q-015-owner-financial-visibility.md) | Owner financial visibility defaults | ⬜ |
| [Q-016](q-016-payment-ledger-vs-dedicated-models.md) | `Payment` ledger vs dedicated `SecurityDeposit` — pick a lane | ⬜ (blocks BUG-006/FG-004/BUG-008 SD slice) |

Q-012 was resolved (Payment gateway → Flywire).

## Surface gaps

| Id | Title | Status |
|---|---|---|
| [GAP-001](gap-001-comms-empty-url-surface.md) | `comms/urls.py` empty | ⬜ |
| [GAP-002](gap-002-integrations-empty-url-surface.md) | `integrations/urls.py` empty | ⬜ **highest-leverage gap** (Flywire webhook) |
| [GAP-003](gap-003-endpoint-coverage-gap.md) | Endpoint coverage gap vs. designed surface | ❌ DROPPED — framing only |
| [GAP-004](gap-004-frontend-coming-soon-tabs.md) | Frontend "Coming Soon" tabs | ⬜ (tracker) |
| [GAP-005](gap-005-quotation-flow-parity.md) | Enquiry→Quotation flow parity vs legacy | ⬜ (tracker) |
| [GAP-006](gap-006-legacy-reference-format-parity.md) | Customer-facing reference format must match legacy (`VC`/`QVC`) | ⬜ (decision made — ready to build) |

## Investigations

| Id | Title | Status |
|---|---|---|
| [INV-001](inv-001-propertycontactassignment-owner-uniqueness.md) | `PropertyContactAssignment` owner uniqueness | ✅ closed — invariant present via `is_primary` |
| [INV-002](inv-002-raterule-priority-tiebreak.md) | `RateRule.priority` tie-break behaviour | ✅ closed — deterministic + tested |
| [INV-003](inv-003-refund-amount-sign-convention.md) | `Refund.amount` sign convention | ✅ closed — partition-by-purpose, no signed sum |
| [INV-004](inv-004-syncrun-syncissue-retry.md) | `SyncRun` / `SyncIssue` failure handling | ⬜ (pre-Zoho checklist) |
| [INV-005](inv-005-legacy-id-indexing-consistency.md) | `legacy_id` indexing consistency | ✅ closed — contract holds |

## Cheapest first commits

Three constraint-tighten tickets, no design questions, no data risk:

1. **BUG-001** — `cancelled_at IS NOT NULL ↔ status=CANCELLED` inverse constraint
2. **BUG-002** — `RateRule` zero-length range (`__lte` → `__lt`)
3. **BUG-003** — `RateRule` POA-vs-price mutex (split into floor + mutex constraints)

After those three, the next-highest-value moves are:

- **FG-006** (promote to bug): `select_for_update` on every booking
  status-transition path
- **FG-008** (promote to bug): add `Property.timezone`
- **BUG-007** (revise first): pick a `bulk_create`-safe approach before
  any code lands

## Decisions still blocking implementation

Highest-leverage unanswered Qs (block lots of downstream work):

- **Q-002** — Owner pre-approval SLA (blocks Celery escalation + flow 15)
- **Q-005** — Reports base currency + FX source (blocks every report)
- **Q-013** — Rate-card incomplete-pricing behaviour (blocks quote builder)
- **Q-015** — Owner financial visibility defaults (blocks portal MVP)
