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

## What's deferred

- Per-villa template branding overrides (legacy didn't have it; revisit when a partner brand needs it).
- Multi-language templates (locale field on `EmailTemplate` is the obvious extension; no v1 use case).
- An editable-from-admin template UI past the basic Django admin form.
- Per-recipient send-time personalisation beyond what context dict carries.

These are recorded in `10-decisions.md`.
