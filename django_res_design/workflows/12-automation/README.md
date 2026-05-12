# 12 · Automation

Scheduled background work. The legacy system has **one** scheduler class (`SchedullerJob.cs` `[TYPO]`) hosting **one** combined job. The job is currently **commented out** at the registration site `[DISABLED]` — meaning the automated reminder/cleanup behaviour is **not running** in production.

## Files

| File | Workflows |
|---|---|
| [`scheduler-jobs.md`](./scheduler-jobs.md) | The single combined payment-reminder + hold-expiry + balance-flagging job (`PaymentReminderSchedulerJob`) |

## Entities touched

The job both reads many tables (`VillaBooking` / `VillaPayment` / `VillaAvailability` etc.) and writes:
- `VillaBooking.IsEmailSent` (after sending the balance-payment reminder)
- `VillaAvailability.AvailableStatus` (40 → 70 when a hold expires after 7 days)

## Stored procedures

- `SP_GET_EMAIL_PAYMENT_DETAILS` — read pending payments with computed status flags
- Direct SQL UPDATEs on `VillaBooking` and `VillaAvailability` for the side-effects

## Open design questions for the Django redesign

- Split the combined job into **discrete tasks**: payment-reminder, hold-expiry, balance-flag.
- Drive them via **Celery beat** with explicit schedule (`crontab(hour=2, minute=0)` for daily, etc.).
- Each task should be **idempotent** and emit a **structured event** per record processed.
- The current "scheduler runs daily but only acts on records whose dates match `today`" logic is fragile if the scheduler misses a day — a record can fall through the cracks. Redesign so each record carries an `action_due_at` and the sweep is `WHERE action_due_at <= NOW() AND processed_at IS NULL`.
- The current `[DISABLED]` state is dangerous: bookings have no reminder emails going out, and holds aren't being auto-released. If anyone is operating off the legacy system today, this is a real operational gap.
