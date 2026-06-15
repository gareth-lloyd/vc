> **✅ RESOLVED (2026-06-15)** — Problem: Email send marked FAILED on any SMTP error, with no retry. Fix: Classified transient versus terminal errors and added a Celery retry. Commit: f608e42.
>
> _Original ticket preserved below for context._

# SMELL-015 — Email send marks FAILED on any SMTP error; no transient retry

- **Severity:** 🟡 Smell
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `comms/tasks.py:81–87` (the `except` block), `:94–102`
  (`send_email_log`)

## Problem

The send path treats every SMTP failure as terminal:

```python
    except Exception as exc:
        log.status = EmailLogStatus.FAILED
        log.failure_reason = str(exc)
        log.save(update_fields=["status", "failure_reason", "updated_at"])
        return
```

A transient 4xx greylisting response, a dropped connection, or a brief
SMTP-host outage permanently fails the `EmailLog`; the task docstring
confirms "the task itself does not retry" and the only recovery is a manual
operator resend. For deposit-reminder and booking-confirmation mail, that
silently drops customer-facing email on routine infra blips.

## Proposed fix

Split transient from permanent: transient classes
(`smtplib.SMTPServerDisconnected`, `SMTPConnectError`, `OSError`/timeouts,
and 4xx `SMTPResponseException` codes) re-raise so
`@shared_task(autoretry_for=…, retry_backoff=True, retry_jitter=True,
max_retries=N)` retries with backoff; permanent ones (5xx, bad recipients,
auth) keep the FAILED + `failure_reason` path. The existing row-level
idempotency (a `SENT` log is not re-sent) already makes retries safe.

## Acceptance

- Test: a raised transient SMTP error leaves the log un-FAILED and retries
  (eager mode: assert the retry/raise behaviour); a 5xx marks FAILED with
  the reason.
- Exhausted retries land FAILED, not stuck PENDING.

## Dependencies

None. Related: Q-017 (comms architecture — doesn't block this fix).

## Resolution (2026-06-15)

✅ Done. `comms/tasks.py`:

- Added `_is_transient_smtp_error(exc)` to classify the exception raised by
  `message.send()`. **Transient** (retryable): `SMTPServerDisconnected`,
  `SMTPConnectError`, any `OSError` (covers `ConnectionResetError`,
  `TimeoutError`/`socket.timeout`, DNS/socket errors), and a
  `SMTPResponseException` with a **4xx** `smtp_code` (greylisting, "try again
  later"). **Permanent** (FAILED): `SMTPAuthenticationError`,
  `SMTPRecipientsRefused`, `SMTPSenderRefused`, and any **5xx**
  `SMTPResponseException`. (`SMTPResponseException` straddles both, so it's
  classified by code, not type — the conventional choice the ticket
  prescribes.)
- `_send` now re-raises a new `TransientEmailError` on a transient failure,
  leaving the row **QUEUED**; permanent failures keep the existing FAILED +
  `failure_reason` path.
- `send_email_log` is decorated with `autoretry_for=(TransientEmailError,),
  retry_backoff=True, retry_backoff_max=600, retry_jitter=True,
  max_retries=6` — mirrors `payments.tasks.process_webhook_delivery`. After
  the retries exhaust, Celery surfaces the error (django-structlog
  `task_failed` is the alert) and the existing `requeue_stuck_emails` beat
  sweep re-dispatches anything left QUEUED past the grace window, so an
  exhausted message lands QUEUED→retried, never stuck-PENDING-forever. The
  row-level SENT idempotency guard already in `_send` keeps retries safe.

Tests: `comms/tests/test_email_transient_retry.py` — parametrised transient
errors re-raise `TransientEmailError` and leave the log QUEUED; parametrised
permanent errors mark FAILED with a reason; the task carries the autoretry
config. Full backend gate green (`pytest` 1716 passed, `ruff check`/`format`,
`mypy` clean).
