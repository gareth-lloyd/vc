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
