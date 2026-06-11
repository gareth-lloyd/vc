# Structured logging

`structlog` end to end — config in this package, wired from `settings/base.py`.
JSON to stdout in staging/production (→ Render log drain → Datadog), pretty
console line in dev/test. The must-know summary lives in
`django_res/CLAUDE.md`; this is the full guide.

## Getting a logger

`logger = structlog.get_logger(__name__)` — never `logging.getLogger`. Plain
stdlib `logging` still routes through the same pipeline, but the convention is
structlog, and it's **enforced**: ruff's `TID251` ban
(`[tool.ruff.lint.flake8-tidy-imports.banned-api]` in `pyproject.toml`) fails
the build on `logging.getLogger` in app code (`core/logging/config.py`, which
wires the stdlib `LOGGING` dict, is exempt).

## Event shape

Events are dotted `domain.action`, lowercase, with structured kwargs — not
interpolated sentences: `logger.info("booking.created", booking_id=…,
reference=…)`. Money as `str(Decimal)`. Two shapes, by intent:

- **Facts already true / deliberate skips** → a single past-tense event:
  `booking.created`, `comms.email_skipped`, `payment.schedule_skipped`,
  `payment.reminder_skipped` / `payment.reminder_failed`, `ical.feed_failed`,
  `encrypted_field.decrypt_failed`.
- **Fallible operations (verbs that can fail)** → the operation triple via
  `log_operation` (below), not a hand-rolled single event.

## `log_operation`

Wrap fallible operations with `core.logging.operations.log_operation` — a
context manager that times the block and emits `<event>.succeeded` (`info`,
with `duration_ms`) or `<event>.failed` (`error` + traceback, with
`duration_ms`, then **re-raises** — it never swallows). Pass the operation's
entity ids as kwargs (they bind into contextvars so *nested* lines inherit
them); mutate the yielded `ctx` dict to attach ids found mid-operation:

```python
with log_operation("refund.request", logger=logger, booking_id=booking.pk) as ctx:
    refund = Refund.objects.create(...)
    ctx["refund_id"] = refund.pk          # rides on refund.request.succeeded
    return refund
```

`logger=logger` is required, so the event keeps its module logger name. Put
input/permission validation *above* the block — a rejected call is not an
operation failure and shouldn't log as `.failed` with a traceback. Reference:
`RefundService.request` / `execute` (`refund.request.*` / `refund.execute.*`).
Don't force a *fact* (`booking.created`) into the triple.

## Celery tasks

Tasks get their lifecycle for free: django-structlog already emits
`task_succeeded` / `task_failed` / `task_retrying` with `task_id`, and
`core/logging/celery.py` enriches every one with `task_name`. **Don't** wrap a
task in `log_operation` — add only a domain *summary* line for the outcome
(`hold.expired_batch released=…`, `booking.auto_checked_out_batch count=…`).

## Context is automatic

`django_structlog.middlewares.RequestMiddleware` binds `request_id` +
`user_id`, and `core.middleware.AuditMiddleware` adopts that `request_id` as
the audit `correlation_id` — so a log line joins to the `AuditLog` rows from
the same request by id. Service code adds only its own domain kwargs. Request
start/finish are logged automatically; health-check and static/media paths are
dropped (`core.logging.processors.drop_noisy_requests`).

## Reserved keys — do not use as event kwargs

`message`, `level`, `status` (the JSON stage maps `event`→`message` and
`level`→`status` for Datadog), plus the auto-bound `request_id` / `user_id` /
`correlation_id` and the static `service` / `env` / `release`. Name domain
fields around them (e.g. `booking_status`, not `status`).

## Canonical field names

Spell entity keys the same everywhere so log searches are uniform:
`booking_id`, `property_id`, `refund_id`, `payment_id`, `quotation_line_id`,
`feed_id`, `guest_id`; `amount` = `str(Decimal)`; `currency` = ISO code;
`reason` = a short skip/failure code; `duration_ms` is reserved for the
operation triple. Use `<entity>_id` (the pk), not the ORM object.

## PII never lands in logs

`core.logging.redaction.redact_sensitive` scrubs denylisted keys (passwords,
tokens, secrets, card data, `body`) and PAN/`Bearer` value patterns —
recursively, including nested dicts — replacing them with the shared
`core.audit.REDACTED` sentinel. It's a backstop, not a licence to log secrets.

## Testing

Don't write tests that merely re-assert a log line fired — that restates the
implementation and rots. Test logging only where it *earns* it: the
redaction/noise-drop processors directly (`core/tests/test_log_redaction.py`,
`test_log_processors.py`), the behaviour of `log_operation` (re-raises, unbinds
contextvars — `core/tests/test_operations.py`, *not* its output), or a
high-value observability guarantee on a money path
(`test_refund_service_emits_structured_events`). When you do assert on events,
use `structlog.testing.capture_logs()` on the event name + key fields (not the
rendered string); it bypasses the configured processors, and test settings set
`cache_logger_on_first_use=False` so it intercepts module-level loggers.
