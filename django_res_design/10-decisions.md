# 10 — Decisions Log

Cross-reference of design decisions surfaced by the workflow audit (`workflows/**`) against the design docs. Keyed by **what we decided**, not by **what legacy did** — `09-departures.md` is the per-legacy-table mapping; this file is "why doesn't the design do X?" / "where did this come from?".

Each row carries a status:

- **live** — the decision is realised in the current design docs.
- **deferred** — recognised, intentionally postponed past v1.
- **dropped** — considered, rejected for the reasons noted.

Status is point-in-time; flip rows as the design evolves.

## Live decisions

| Decision | Workflow IDs / loci | Docs touched | Rationale |
|---|---|---|---|
| **Per-user SMTP reinstated as `comms.SmtpProfile`** (scope=PERSONAL, encrypted creds) for agent "send as" on quotation emails. Reverses an earlier "dropped as security liability" call. | `workflows/11-integrations/transmission.md`, `workflows/02-administration/user-administration.md` | `10-comms.md`, `01-accounts.md`, `09-departures.md` | Guest replies must land in the agent's inbox; a single shared system SMTP can't deliver that. Encryption-at-rest + admin-only access mitigates the security concern. |
| **`comms` app created in v1** with `EmailTemplate` (versioned, DB-stored, file-seeded), `EmailLog` (persist-first, append-only), and `EmailService.send(...)` (routes via personal or system SMTP). Listens for `booking_transitioned`, `payment_succeeded`, `hold_expired`, etc. | `workflows/11-integrations/email-delivery.md`, `transmission.md`, `flywire-gateway.md` | `10-comms.md`, `06-availability.md`, `07-payments.md`, `00-conventions.md`, `09-departures.md` | Multiple apps need transactional email. A single audited dispatcher beats every app rolling its own `send_mail`. `EmailLog` correlation provides reminder-idempotency without per-row flags. |
| **`RateRule.is_locked` + `RateRule.is_approved`** gates. Bulk recompute / re-import services skip `is_locked`; `PricingEngine.quote()` filters `is_approved=False`. | `workflows/04-pricing/rates.md` (legacy `IsManualUpdate` and `IsApprove`) | `04-pricing.md` | Preserves the legacy operator behaviour of hand-set rates surviving bulk operations, and gates un-reviewed imports out of the engine. |
| **`PricingEngine` tie-break documented**: highest `priority` wins; equal priority resolved by narrowest date range, then by `id` desc. | `workflows/04-pricing/pricing-engine.md` | `04-pricing.md` | Determinism over flexibility; admins know how overlaps resolve without trial-and-error. |
| **`Payment.purpose=CONCIERGE`** + `Payment.concierge_item` FK + `ConciergeService.request_payment(items)`. Excluded from `Booking.outstanding_balance()` schedule maths. | `workflows/09-booking/booking-concierge.md` | `07-payments.md` | Ad-hoc concierge invoices don't fit the 3-tier deposit/balance/security schedule but need first-class payment-history visibility. |
| **`PropertyFinance.cancellation_fee_amount` / `cancellation_fee_percent` / `cancellation_window_days`** + `GroupFinance` mirror. `RefundService.from_cancellation(booking, reason)` computes the refund. | `workflows/09-booking/booking-cancellation.md`, `booking-modification.md` | `03-finance-config.md`, `07-payments.md`, `09-departures.md` | Legacy had no refund workflow at all; cancellation was a data-delete. The new cancellation path needs a configurable fee + a `Refund` row sized as `paid_total − fee`. |
| **`PropertySettings.requires_enquiry_first`** (nullable bool, inherits from group). Public site hides direct-book affordance when True. | `workflows/06-availability/availability-check.md` (legacy status code 20 "Available – Enquire") | `02-properties.md`, `09-departures.md` | Restores a real UX affordance without inflating the 3-value `Property.status` enum (`DRAFT` / `ACTIVE` / `ARCHIVED`). |
| **Hold auto-expiry enabled from day one.** Celery beat task `expire_holds` (every 1 min) sets `released_at`, emits `hold_expired` signal; `comms` sends an email to the creating agent. | `workflows/06-availability/holds.md` (legacy `[DISABLED]` scheduler), `[NEW] AVAILABILITY.HOLD.EXPIRE_NOTIFY` | `06-availability.md`, `00-conventions.md`, `10-comms.md` | Legacy required manual cleanup; the Django port closes that gap on day one. |
| **All Celery beat tasks enabled in v1**: `expire_holds`, `escalate_pending_owner_approvals`, `send_payment_reminders`, `process_sd_refunds`, `auto_check_out`, `cleanup_orphan_images`, `zoho_reconciliation`. Idempotency declared per task. | `workflows/12-automation/scheduler-jobs.md` | `00-conventions.md` | Legacy `SchedullerJob` was checked in but `[DISABLED]`; payment reminders, SD refunds, and hold-expiry never ran. Django port runs them with retry + DLQ. |
| **`SecurityDeposit` and `Refund` as first-class workflow models** (not just Payment rows). State machines on the workflow row; gateway-transaction audit on spawned `Payment(purpose=…)` rows. Separation-of-duties on `Refund` (requester ≠ approver). | `workflows/10-payment/payment-preauth.md`, `payment-collection.md`; reconciliation issues #24, #25 | `07-payments.md`, `09-departures.md` | Legacy had no refund table at all and a flat `IsSDPaid` flag with no pre-auth lifecycle. The new shape models both properly. |
| **Generic `SyncRecord`** + `SyncRun` + `SyncIssue` for cross-provider sync. Idempotent on `(provider, external_id)`. Celery autoretry with exponential backoff; max 6 attempts; `SyncIssue` on exhaustion. | `workflows/11-integrations/zoho-sync.md`, `enquiry-intake.md` (legacy `[CORRECTNESS]` silent loss on Zoho outage) | `08-integrations.md` | Replaces scattered `ZohoId` / `SyncId` columns with one observability point. Fixes legacy fire-and-forget pattern that lost data silently. |
| **No `SoftDeleteModel`.** Lifecycle is always an explicit visible signal: `status` enum, `is_active`, dated timestamps, or hard delete + `AuditLog`. | `00-conventions.md` "Lifecycle, not soft delete" | every doc | Soft-delete tombstones rot; explicit lifecycle scales. |
| **Range-query availability** backed by Postgres `EXCLUDE USING gist` constraints; no daily-row grid. | `workflows/06-availability/availability-check.md`, `booking-status-transitions.md` (legacy `[CORRECTNESS]` two-write hazard) | `06-availability.md` | DB-enforced no-overlap is stronger than the legacy SP pair `sp_villaAvailability` + `SP_SAVE_BOOKING_INFO` — and atomic. |
| **One flat `PropertyFinance`** + `GroupFinance` mirror with prefixed fields (`commission_*`, `tax_*`, `bank_*`, `deposit_*`, `interim_*`, `security_deposit_*`, `cancellation_*`). MVP staff roles gate the whole form; per-concern permissions are a post-v1 refactor. | reconciliation issue #36 | `03-finance-config.md` | An earlier draft used 5 OneToOne children for granular permissions that MVP roles don't need. Collapsed to keep admin/serializer/resolver surface flat. |
| **Per-module Zoho serializers + response capture** handled by the generic `SyncClient` hierarchy; module specifics live in subclasses, not in a separate per-module table. | `workflows/11-integrations/zoho-sync.md` | `08-integrations.md` | Implementation detail handled by the existing client abstraction — no additional spec needed. |
| **Webhook secrets in env / Vault**, HMAC verified on raw body bytes. Persist-first `WebhookDelivery` with idempotent `(provider, event_id)`. | `workflows/10-payment/payment-collection.md`, `flywire-gateway.md`; security-debt items #1, #3, #4 | `07-payments.md`, `08-integrations.md` | Closes the legacy debts: hardcoded API key in source, unsigned webhooks, no idempotency check. |
| **Cancel-and-rebook for post-deposit modifications.** Pre-deposit modifications mutate the booking in place; post-deposit changes force `booking.cancel(reason='guest_modification')` + new Booking creation. State machine stays at 11 states. | `workflows/09-booking/booking-modification.md` | `05-reservations.md`, `06-availability.md` | Avoids inventing a `MODIFICATION_PENDING` state; refund/repricing trail is uniform via cancel+rebook. |
| **Flywire is the v1 payment gateway.** No multi-provider abstraction layer; the `Payment.provider` enum (`FLYWIRE`, `MANUAL_BANK_TRANSFER`) stays extensible so a second provider can be added later without a migration, but no Stripe / other-gateway code paths are built. | `workflows/11-integrations/flywire-gateway.md`, `workflows/10-payment/payment-collection.md`, `workflows/10-payment/payment-preauth.md` | `07-payments.md`, `08-integrations.md`, `product-design/00-overview.md`, `product-design/01-domain-model.md`, `product-design/04-rest-api-surface.md`, `product-design/06-verification.md` | Continuity with the legacy gateway integration (webhook contract, tokenisation flow, refund window semantics). Switching processors at rebuild time is a separate project; not in scope for v1. |
| **Per-booking Communications tab on Booking Detail.** | `product-design/02-frontend-design.md §3.8` | `product-design/02-frontend-design.md`, `product-design/05-improvements-over-original.md`, `10-comms.md` | Operators currently have no way to see what was sent against a booking — legacy stores outbound mail in per-day plaintext files only (`mock_up_analysis/04a-ressystem-email-inventory.md §2.4`, §8). A first-class tab on Booking Detail backed by `EmailLog` is the single biggest operator-UX gain over legacy. |
| **Editable `EmailTemplate` admin with versioning + preview-with-data + test-send.** Promotes templates from SQL-only objects to first-class operator-editable entities. Reverses the v1.1-deferral previously recorded in `product-design/04-rest-api-surface.md §2.19` and in the `Deferred` table below (`Editable-from-admin email template UI beyond basic Django admin`). | `workflows/11-integrations/email-delivery.md`, `workflows/08-quotation/transmission.md`, `10-comms.md` | `10-comms.md`, `product-design/04-rest-api-surface.md`, `product-design/05-improvements-over-original.md` | Legacy `VCEmailTemplates` is managed by raw SQL with no preview, no versioning, no test-send (`mock_up_analysis/04a-ressystem-email-inventory.md §3.1, §8`). An operator-editable admin is required to retire the SQL-only template-edit workflow. |
| **Drop hardcoded BCC + replace cleartext SMTP password storage.** Outbound mail must not BCC any internal/dev address by default; SMTP credentials on `comms.SmtpProfile` are encrypted-at-rest only (no cleartext column). | `workflows/11-integrations/email-delivery.md`, `workflows/02-administration/user-administration.md` | `10-comms.md`, `09-departures.md` | Legacy BCCs every non-quote email to `connectusinfowaydemo12@gmail.com` (`EmailService.cs:71`, `mock_up_analysis/04a-ressystem-email-inventory.md §2.3`); SMTP passwords are stored cleartext in both `VillaConfigEmail` and `UserMaster` (§2.1, §2.2). Both must not survive the rewrite. |

## Drops vs the prior decisions pass

The prior plan (`deeply-analyze-the-data-stateful-gizmo.md`) proposed these; the revised pass intentionally **does not** apply them.

| Proposed | Why dropped |
|---|---|
| `Enquiry.flexibility` 5-value enum | Existing `Enquiry.is_flexible` boolean is sufficient for v1; the four legacy ranges (`±3d`, `±7d`, `month`, `any`) weren't load-bearing in the workflow. |
| `Booking.party_size_confirmed_at` column | `PaymentScheduler` can check `Booking.status > CONFIRMED` — no new column needed. |
| `Booking.group_reference` UUID | Group bookings (multi-villa under one Booking) are explicitly out of scope for v1. |
| `Payment.received_amount` / `Payment.received_currency` | Multi-currency settlement capture isn't in v1 workflows; defer. |
| `Payment.reminder_sent_at` | Reminder idempotency rides on an `EmailLog` correlation query — no new column. |
| Named `PartyOutOfRange` exception added separately | Engine already raises typed exceptions; this is one more in the family (documented in `04-pricing.md`), not a new design call. |
| `django-axes` rate-limiting in this pass | Real concern, but a cross-cutting security ticket, not part of this design pass. |
| `Property.requires_full_day_changeover` flag | Half-day changeover is out of scope for v1; full-day is the implicit default — no flag needed. |
| Per-module Zoho **Serializer classes** named explicitly in the design | Implementation detail. The generic `SyncClient` hierarchy is enough at the spec level. |
| `SyncRecord.meta` JSONField | `SyncIssue.local_state` / `remote_state` already capture what's needed for drift inspection. |

## Deferred (recognised, out of v1)

These are real legacy or workflow concepts that the v1 design intentionally does not cover. Each becomes a v2 (or later) discussion when the business need re-emerges.

| Item | Reason |
|---|---|
| **Client / guest portal** (post-booking guest self-service: itinerary view, in-app messaging, concierge ticketing, arrival info reveal, co-traveller invites, guest-initiated payment). Mockup: `mock_up_analysis/02-client-portal.md`. | The legacy `ResSystem/` has no analog — the only guest touchpoint is the WordPress checkout form (`workflows/10-payment/checkout-flow.md`). The portal is ~80% greenfield: new auth model, new `Thread`/`Message`/`ServiceRequest` entities, new guest-driven concierge approval flow. Too speculative for v1; revisit once the operator-facing rebuild is live and we have real usage signal. |
| **Owner portal beyond read-only view** (multi-user owner-org accounts with internal RBAC, owner-initiated content edits with a VC approval queue, owner-driven property onboarding, in-portal messaging). Mockup: `mock_up_analysis/05-owner-portal.md`. | The legacy `ResSystem/` has no owner-facing tooling — owners interact via staff/email. The mockup goes meaningfully beyond `product-design/02-frontend-design.md §7.3` and `03-workflows.md` flow 14 (which only commit to read-only bookings/statements + simple block requests). The four expansion axes (multi-user org, change-request approval queue, owner-driven onboarding, messaging) each require new entities and have no legacy basis. Keep the v1 owner surface to the spec'd read-only minimum; defer the rest. |
| Group bookings (multi-villa under one `Booking`, shared payment) | Niche in legacy; one `Booking` = one `Property` for v1. |
| Half-day changeover boundaries | Range-model `[date_from, date_to)` makes half-day modelling expensive; owner blocks the day instead. |
| Per-villa email-template branding overrides | Legacy didn't have it; resist gold-plating. |
| Multi-language email templates | No v1 use case. Locale field on `EmailTemplate` is the obvious extension. |
| ~~Editable-from-admin email template UI beyond basic Django admin~~ | **Reversed** — now live: see the "Editable `EmailTemplate` admin with versioning + preview-with-data + test-send" row in `Live decisions` above. |
| WordPress → Canary bidirectional sync; multi-site fan-out | Single public site for v1; `SyncRecord(provider=WORDPRESS_SITE)` is sufficient. |
| Channel-manager integrations (Booking.com, Vrbo) | Out of v1; would land as new `integrations.SyncClient` subclasses. |
| Multi-currency payment-settlement capture | v2 once a gateway with multi-currency settlement is selected. |
| Pre-auth live wiring (provider call layer) | The state machine and `SecurityDeposit` model exist; gateway integration is v2. |
| Concierge personalisation / per-recipient quote-line metadata | Legacy doesn't have it. |
| `GuestPreference` model (legacy `VillaClientPrefMaster` / `ClientPreferenceDetail`) | Underused in legacy; can re-add later as a structured model. |
| Per-villa rental alternatives / "rent together" bundles (legacy `VillaRentalAlternative`) | Future scope. |
| `BookingPaymentMethod` (saving multiple cards-on-file per booking) | One card-on-file token on the booking is enough for v1. |

## Open follow-ups

These need an answer before implementation; tracked here so they don't get lost in workflows / docs.

- **Owner-approval SLA**: `workflows/09-booking/booking-creation.md` describes owner approval but doesn't specify a default reminder cadence or auto-decline window. The `escalate_pending_owner_approvals` Celery task needs a threshold (currently `[CONFIGURABLE]`).
- **Cancellation-fee pre-window behaviour**: current design uses a single `cancellation_window_days`. A common pattern is sliding bands (e.g. 100% > 60 days, 50% 30-60d, 0% < 30d). Out of v1; add a `cancellation_bands` JSONField on `PropertyFinance` if it lands.
- **`DamageClaim` model**: referenced from `SecurityDeposit.damage_claim` in `07-payments.md` but not yet specified in `05-reservations.md`. Open ticket.

## How to use this file

When you are deciding whether a behaviour belongs in the design:

1. Grep this file for the area first (e.g. "concierge", "refund", "SMTP").
2. If the row exists and is **live** — implement against it.
3. If the row exists and is **deferred** — push back and surface this file as the basis for not doing it.
4. If the row exists and is **dropped** — surface this file as the basis for not re-raising it.
5. If no row exists — propose a new decision via a PR that adds one here. Status starts as **live** only when the docs are updated to match.
