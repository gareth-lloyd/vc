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
