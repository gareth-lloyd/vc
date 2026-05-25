# 10 — Communications (Email)

Separate `comms` app. Owns transactional email templating, rendering, persistence, and per-user "send as agent" SMTP profiles. Other apps emit Django signals; `comms` listens and dispatches.

## Why this exists

Two workflow constraints force this into v1:

1. `workflows/11-integrations/transmission.md` and `workflows/02-administration/user-administration.md` specify per-user SMTP "send as agent" for quotation emails — quotations leave the agent's own mailbox so the guest reply lands in the agent's inbox.
2. Multiple apps need to fire transactional emails (booking confirmations, payment receipts, hold-expiry notices, owner-approval requests). A single, audited dispatch layer with templates of record beats every app rolling its own `send_mail`.

This deliberately reverses the earlier "per-user SMTP dropped" position recorded in `09-departures.md` (the `UserMaster.SmtpAddress/...` row). See `10-decisions.md`.

## File layout

```
comms/
├── enums.py
├── models.py             # SmtpProfile, EmailTemplate, EmailLog
├── services.py           # EmailService
├── signals.py            # listeners for booking_transitioned, payment_succeeded, ...
├── tasks.py              # Celery: send_email (with retry)
├── templates/comms/      # subject + body Jinja-style templates as files (template-of-record lives in DB; files are seeds)
└── admin.py
```

## Models

### `SmtpProfile(AuditedModel)`
SMTP credentials for either the system mailer or an individual staff user (for "send as agent" quotation emails).

- `name` — CharField (e.g. "System", "alice@vc.com")
- `scope` — TextChoices (`SYSTEM`, `PERSONAL`) — exactly one `SYSTEM` profile is the default sender; `PERSONAL` profiles attach to a `User`
- `owner` — FK accounts.User SET_NULL, null=True, blank=True, related_name="smtp_profiles" — required when `scope=PERSONAL`, null when `scope=SYSTEM`
- `host` — CharField
- `port` — PositiveSmallInteger
- `username` — CharField
- `encrypted_password` — CharField — app-layer encryption (same Fernet pattern as `User.tfa_secret` in `01-accounts.md`)
- `use_tls` — BooleanField(default=True)
- `from_email` — EmailField — the address that appears in the `From:` header
- `reply_to` — EmailField(blank=True)
- `is_active` — BooleanField(default=True)

Constraints:
- `CheckConstraint((scope='PERSONAL' AND owner IS NOT NULL) OR (scope='SYSTEM' AND owner IS NULL), name="smtp_profile_owner_matches_scope")`
- `UniqueConstraint(fields=["scope"], condition=Q(scope="SYSTEM", is_active=True), name="one_active_system_smtp_profile")`
- `UniqueConstraint(fields=["owner"], condition=Q(scope="PERSONAL", is_active=True), name="one_active_personal_profile_per_user")`

`User` gains a convenience reverse accessor `smtp_profile` (the single active `PERSONAL` profile) — not a column on `User`; just `User.smtp_profiles.filter(is_active=True).first()` wrapped in a property.

Sensitive fields: `encrypted_password` is never returned by the admin or API; the test-send action sends a known-text email through the profile rather than echoing the stored secret.

### `EmailTemplate(AuditedModel)`
Versioned templates of record. Files in `comms/templates/comms/` are loaded into the DB on first run; subsequent admin edits supersede them.

- `key` — CharField — short stable id (e.g. `booking.confirmation`, `quotation.sent`, `hold.expired`, `owner.approval_request`, `payment.receipt`, `payment.reminder.deposit`, `payment.reminder.balance`)
- `version` — PositiveIntegerField(default=1)
- `subject_template` — TextField — Django template string
- `body_template` — TextField — Django template string (markdown rendered to HTML at send time, with a generated plaintext alternate)
- `is_active` — BooleanField(default=True)
- `notes` — TextField(blank=True)

Constraints:
- `UniqueConstraint(fields=["key", "version"], name="unique_template_version")`
- `UniqueConstraint(fields=["key"], condition=Q(is_active=True), name="one_active_template_per_key")`

Edits bump `version` and atomically deactivate the prior row. Active template is what `EmailService.send()` resolves.

### `EmailLog(TimestampedModel)`
Persist-first log of every dispatch attempt. Append-only (per `00-conventions.md` lifecycle rules).

- `template_key` — CharField (snapshot of which template was used)
- `template_version` — PositiveIntegerField
- `to` — JSONField (list of addresses)
- `cc` — JSONField(default=list)
- `bcc` — JSONField(default=list)
- `from_email` — EmailField
- `sender_user` — FK accounts.User SET_NULL, null=True, blank=True — set when sent through a `PERSONAL` profile
- `smtp_profile` — FK SmtpProfile SET_NULL, null=True
- `rendered_subject` — TextField
- `rendered_body` — TextField (the HTML version; plaintext alternate is regenerated on inspection if needed)
- `status` — TextChoices (`QUEUED`, `SENT`, `FAILED`, `BOUNCED`)
- `provider_reference` — CharField(blank=True) — SMTP queue id or provider message id
- `failure_reason` — TextField(blank=True)
- `attachments` — JSONField(default=list) — list of `{filename, content_type, size, storage_key}`; binary content lives on object storage, not in the DB
- `correlation` — JSONField(default=dict) — `{booking_id?, quotation_id?, payment_id?, enquiry_id?}` so the timeline view on each entity can grep `EmailLog` by linkage
- `queued_at` — DateTimeField(default=now)
- `sent_at` — DateTimeField(null=True, blank=True)

Indexes: `(status, queued_at)`, `(template_key, queued_at)`, GIN on `correlation`.

## Service

### `EmailService`

```python
class EmailService:
    @classmethod
    def send(
        cls,
        *,
        template_key: str,
        context: dict,
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        sender_user: User | None = None,
        attachments: list[Attachment] | None = None,
        correlation: dict | None = None,
    ) -> EmailLog:
        """Resolve the active EmailTemplate by key, render with context,
        choose the SmtpProfile (sender_user.smtp_profile if active else
        system), persist an EmailLog row in QUEUED, dispatch via the
        Celery `send_email_log` task. Returns the EmailLog row."""
```

Routing rule:

1. If `sender_user` has an active `PERSONAL` SmtpProfile → use it; the `From:` and `Reply-To:` come from that profile.
2. Else → use the single active `SYSTEM` profile.

Failure handling: Celery retries with exponential backoff; on exhaustion the `EmailLog.status` becomes `FAILED` and a Sentry event is emitted. There is no "fire and forget" path — every send goes through Celery so the `EmailLog` row exists before the SMTP call.

No BCC to internal addresses by default (this reverses one of the legacy security debts — `09-departures.md` security row #5).

## Signal listeners

Registered in `comms/signals.py`, attached in `comms/apps.py:CommsConfig.ready()`:

| Signal | Source | Template key | Recipient |
|---|---|---|---|
| `booking_transitioned(from_status, to_status, booking, actor, source)` | `reservations` | `booking.confirmation` (on `AWAITING_DEPOSIT` from `PENDING_OWNER_APPROVAL` and on `AWAITING_DEPOSIT` from `DRAFT`), `booking.declined`, `booking.cancelled`, `booking.checked_out` | guest + optionally the agent (`sender_user`) |
| `owner_approval_requested(booking)` | `reservations` | `owner.approval_request` | owner contact email; carries a signed-token link to `:approve` / `:decline` |
| `quotation_sent(quotation, sender_user)` | `reservations` | `quotation.sent` | guest, sent **as** `sender_user` when their profile is active |
| `payment_succeeded(payment)` | `payments` | `payment.receipt` | guest |
| `payment_failed(payment)` | `payments` | `payment.failed` | ops (system) + guest (separate template `payment.failed_guest`) |
| `hold_expired(hold)` | `reservations` (emitted by `expire_stale_holds` Celery task — see `06-availability.md`) | `hold.expired` | the agent who created the hold |
| `security_deposit_released(sd)` | `payments` | `security_deposit.released` | guest |

The signal contract is one-way: `comms` imports models from `reservations` / `payments` / `accounts`; the source apps never import `comms`. They emit signals and Django wiring does the rest.

## Idempotency

`EmailLog` is keyed by an idempotency hash on `(template_key, template_version, sorted(to), correlation)`. Re-emission of the same signal does not create a duplicate row — the listener queries first. This is how payment reminders are kept idempotent in `12-automation` without a `Payment.reminder_sent_at` column.

## Template catalogue

The signal listener table above documents the dispatch wiring; this is the **list of `EmailTemplate.key` rows that ship with v1**. Each row identifies a distinct guest-facing or internal email; keys that previously reused one row in legacy (e.g. balance reminders at 7d / due-today) are split here. Source for the gap analysis: `mock_up_analysis/04-client-emails.md §4` and `04a-ressystem-email-inventory.md §9`.

| Key | Purpose (one-line) | Workflow trigger |
|---|---|---|
| `enquiry.auto_reply` | Guest acknowledgement after public enquiry submission. | `workflows/07-enquiry/enquiry-intake.md` (website POST) |
| `enquiry.internal_notification` | Internal VC-inbox notice for a new enquiry. | `workflows/07-enquiry/enquiry-intake.md` (website POST) |
| `quotation.send` | Quote to client; sends via the agent's `PERSONAL` `SmtpProfile` when one is active. | `workflows/08-quotation/transmission.md` |
| `booking.confirmation` | Confirmation to guest on `AWAITING_DEPOSIT` (covered by signal listener table above). | `workflows/09-booking/booking-confirmation.md` |
| `booking.paid_in_full_confirmation` | Distinct confirmation variant when deposit + balance are paid in a single transaction. | `workflows/10-payment/payment-collection.md` (single payment covers full schedule) |
| `booking.owner_declined` | Guest-facing notice when the owner declines a pending-approval booking. | `workflows/09-booking/booking-confirmation.md` (owner-decline path) |
| `booking.modification_notice` | Confirmation to guest that dates or party size have changed. | `workflows/09-booking/booking-modification.md` |
| `booking.cancellation_confirmation` | Guest-facing cancellation with itemised refund. | `workflows/09-booking/booking-cancellation.md` |
| `booking.refund_confirmation` | Refund-executed confirmation receipt. | `workflows/09-booking/booking-cancellation.md` |
| `booking.damages_claim` | Security-deposit damages claim notification to guest. | pending `DamageClaim` model (see `10-decisions.md` Open follow-ups) |
| `booking.balance_received` | Receipt to guest confirming the rental balance payment landed. | `workflows/10-payment/payment-collection.md` (`status=guaranteed` on `BALANCE` payment) |
| `booking.balance_reminder_7d` | Balance reminder at T-7d. | `workflows/12-automation/scheduler-jobs.md` |
| `booking.balance_reminder_3d` | Balance reminder at T-3d (new; legacy reused one key for 7d/0d). | `workflows/12-automation/scheduler-jobs.md` |
| `booking.balance_due_today` | Balance reminder on the due date, distinct urgency tone. | `workflows/12-automation/scheduler-jobs.md` |
| `booking.pre_arrival_info` | Pre-arrival information pack at T-7d before check-in. | `workflows/12-automation/scheduler-jobs.md` |
| `booking.check_in_reminder` | Check-in nudge at T-48h. | `workflows/12-automation/scheduler-jobs.md` |
| `booking.post_stay_thanks` | Thank-you note T+24h after check-out. | `workflows/12-automation/scheduler-jobs.md` |
| `payment.security_deposit_request` | Security-deposit invoice (distinct from `booking.confirmation`). | `workflows/10-payment/payment-preauth.md`, `workflows/10-payment/payment-collection.md` |
| `payment.card_update_request` | Stored-card refresh request (legacy `CC_CARD_UPDATE`). | `workflows/12-automation/scheduler-jobs.md` |
| `report.scheduled_delivery` | Operator-scheduled report delivery to a recipient list. | `workflows/12-automation/scheduler-jobs.md` |
| `ops.overdue_escalation` | Internal ops alert when a booking balance is overdue. | `workflows/12-automation/scheduler-jobs.md` |

Keys already covered explicitly by the **Signal listeners** table above (`booking.confirmation`, `booking.declined`, `booking.cancelled`, `booking.checked_out`, `owner.approval_request`, `quotation.sent`, `payment.receipt`, `payment.failed`, `payment.failed_guest`, `hold.expired`, `security_deposit.released`) remain the source of truth for their wiring; the catalogue above adds the rows the legacy → v1 gap analysis surfaced.

## Template admin UX requirements

The `EmailTemplate` admin is operator-editable (per `10-decisions.md` "Editable `EmailTemplate` admin" row). Requirements:

- **Versioning.** Edits bump `EmailTemplate.version` and atomically deactivate the prior active row (already enforced by the `one_active_template_per_key` constraint). Version history is browseable; rollback is "publish prior version as new active version", not in-place mutation.
- **Preview-with-data.** Operator picks a real booking / enquiry / quotation (or a synthetic fixture) and the admin renders the template against that context, side-by-side subject + HTML + plaintext alternate.
- **Test-send.** Operator chooses a recipient address (defaults to their own); the admin sends through the active `SmtpProfile` and writes an `EmailLog` row tagged with `correlation.test_send=True` so test sends are visible-but-distinguishable in the log.
- **Locale-ready field placeholder.** The catalogue keys above are locale-agnostic; the `EmailTemplate` model leaves room for a future `locale` field (multi-language templates remain deferred per `10-decisions.md` Deferred table — no v1 use case).
- **Audit trail.** Every edit produces an `AuditLog` row keyed on `(EmailTemplate, version, actor, at, before, after)` matching the project-wide audit convention (`00-conventions.md`).

The API surface for this lives under `/email-templates/*` in `product-design/04-rest-api-surface.md §2.19`.

## Operator UX — per-booking Communications tab

Operators need first-class visibility into what has been sent against each booking. The legacy app dumps outbound mail to per-day plaintext under `wwwroot/ResLogs/<ddMMyyyy>/` only (`mock_up_analysis/04a-ressystem-email-inventory.md §2.4, §8`), so there is no per-booking history surface at all today.

The redesign adds a **Communications tab** on the Booking Detail screen (`product-design/02-frontend-design.md §3.8`) backed by `EmailLog`:

- Lists every email sent against the booking, queried via `EmailLog.correlation.booking_id`.
- Per-row: timestamp, recipient, template key + version, rendered subject, status, opens/clicks (when provider events are wired).
- Per-row actions: **View payload** (modal showing rendered HTML + plaintext alternate) and **Resend** (creates a new `EmailLog` row, does not mutate the original).
- Top-of-tab action: **Compose** (template picker → preview → send), persisted as a normal `EmailLog` entry with `template_key` resolved from the picked template.

API endpoints under `product-design/04-rest-api-surface.md §2.19`.

## What's deferred

- Per-villa template branding overrides (legacy didn't have it; revisit when a partner brand needs it).
- Multi-language templates (locale field on `EmailTemplate` is the obvious extension; no v1 use case).
- Per-recipient send-time personalisation beyond what context dict carries.
- Inbound-email gateway for guest-side reply threading (per-booking reply-to alias). The "New Message from VC" / "Service Request Update" templates in `mock_up_analysis/04-client-emails.md §3.9, §3.10` depend on this — both are gated behind the deferred client portal (`10-decisions.md` Deferred table).

These are recorded in `10-decisions.md`.
