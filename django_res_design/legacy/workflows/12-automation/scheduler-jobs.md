# Scheduler Jobs

The single combined background job. It does three things in one pass: payment-reminder emails, balance-flag updates, and stale-hold release.

## Run payment reminders + hold-expiry sweep

**ID:** `AUTOMATION.SCHEDULER.PAYMENT_REMINDERS`
**Trigger:** Was intended to fire on a daily cron via `IHostedService.ExecuteAsync` in `SchedullerJob.cs:16-69` `[TYPO]` — **currently commented out** `[DISABLED]`. The job is also exposed as a callable endpoint `GET BookingEmailReminder` gated by the system API key, which means an external scheduler could trigger it.
**Actor:** Background worker (when enabled) or external cron (via API).
**Legacy locus:** `ResService.cs:100-293` (`PaymentReminderSchedulerJob`); SPs `SP_GET_EMAIL_PAYMENT_DETAILS` plus inline SQL.

### Inputs
- Current UTC datetime
- Implicit: all booking + payment + availability rows

### Process

#### Stage 1: Fetch outstanding payments
```sql
exec SP_GET_EMAIL_PAYMENT_DETAILS
```
Returns `EmailCheckoutDetailsArgs[]` per pending payment with: `bookingId`, `id` (payment detail id), `bookingNo`, `amount`, `checkoutDate`, `arrivalDate`, `paymentStatus`, `paymentMethod`, `token`, `description` (`CheckoutPaymentType` = "Initial Deposit" / "Rental Balance" / "Security Deposit"), plus the booking metadata for templating.

Filter: `where ArrivalDate.Date >= UtcNow.Date` — exclude bookings already in the past.

#### Stage 2: Per-payment evaluation

For each unpaid (`paymentStatus` null/empty) payment, compute three boolean triggers:
- `isCheckoutDate` = `UtcNow.Date == checkoutDate.Date` — payment is due today
- `isStayDate` = `UtcNow.Date == arrivalDate.Date` — guest arrives today
- `isEmailSentBeforeCD` = `UtcNow.Date == checkoutDate.AddDays(-7).Date` — 7 days warning

Decide which template:
- `description == "Initial Payment Due Immediately"` AND `isCheckoutDate` → `INITIAL_PAYMENT_TEMPLATE`
- `description == "Rental Balance Payment"` AND `isCheckoutDate`:
  - If `paymentMethod` is CC: send `CC_CARD_UPDATE` instead (asking guest to refresh stored card)
  - Else: `BALANCE_PAYMENT`
- `description == "Security Deposit"` AND (`isStayDate` OR `isEmailSentBeforeCD`) → `SECURITY_DEPOSIT_PAYMENT`

For each match: `SentEmailAsync(template, bookingNo)` (which uses the template-rendering workflow in `11-integrations/email-delivery.md`).

#### Stage 3: Mark balance-email sent

After sending a balance reminder:
```sql
UPDATE VillaBooking SET IsEmailSent = 'true' WHERE Id = {bookingId}
```

#### Stage 4: Release stale holds

Independent of payments:
```sql
SELECT Id, isnull(UpdatedAt, CreatedAt) Data FROM VillaAvailability WHERE AvailableStatus = 40
```
For each:
- `targetDate = createdAt.AddDays(7)`
- If `UtcNow.Date >= targetDate.Date`:
  ```sql
  UPDATE VillaAvailability SET AvailableStatus=70,
                                UpdatedAt=NOW(),
                                UpdatedBy=0,
                                Notes='OnHold Status autoremoved from scheduler task on Date {currentDate}'
  WHERE Id={id}
  ```

#### Stage 5: Log
- Everything logged to file `scheduler_background_service`.

### Outputs / side effects
- **Emails out:** multiple (one per match per booking).
- **DB writes:**
  - `VillaBooking.IsEmailSent` for balance reminders.
  - `VillaAvailability.AvailableStatus` 40 → 70 for expired holds.

### Failure modes
- **Currently disabled** `[DISABLED]` — none of this runs in production.
- Even if enabled: scheduler missed a day = reminders are silently skipped for that day's matches; payments still get processed but no email goes out.
- Template missing → email skipped, no retry.
- SMTP failure → email skipped, no retry.
- Concurrent invocations could double-update holds.
- The tokenized-charge code path is commented out (`ResService.cs:204-207`) `[DISABLED]` — even if enabled, the scheduler **only sends emails**, never automatically captures payment.

### Open questions
- This is one of the most important workflows to get right in the Django redesign:
  - Split into three Celery beat tasks:
    1. `payments.tasks.send_payment_reminders`
    2. `availability.tasks.expire_stale_holds`
    3. `payments.tasks.flag_balance_emails_sent`
  - Each is idempotent.
  - Each emits a `WorkflowRunEvent` on completion (or per-record).
  - Hold expiry should also notify the agent who created the hold.
  - Decide whether the tokenized-recurring-charge is part of the redesign scope (see `10-payment/payment-preauth.md`).
- The "7 days before checkout" trigger is hand-rolled by comparing dates today; a more robust pattern computes the trigger time at booking-time and stores `reminder_due_at` on a separate table.
