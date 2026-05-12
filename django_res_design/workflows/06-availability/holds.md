# Holds

A "hold" is a temporary block on a property's nights — created when a quotation is saved, expiring 7 days later if not converted into a booking.

## Create hold on quotation save

**ID:** `AVAILABILITY.HOLD.CREATE`
**Trigger:** Quotation save (status code 40 = On Hold).
**Actor:** System (auto from quotation save workflow).
**Legacy locus:** `CommonService.cs:218-238` (the `ModifyVillaAvailability` entry point); SP `sp_villaAvailability` with `@Status=40`.

### Inputs
- `VillaId`, `FromDate`, `ToDate`
- `QuotationNo` (so the hold can later be promoted to booked or released on cancel)
- `Status=40`, `Notes="OnHold quote pending confirmation"`, `User`, `Action="UPDATE"`

### Process
The SP body (from the seed snapshot in `live-db-24-apr.sql`):
1. **Delete boundary nights** with available status (10, 70) on `FromDate` / `ToDate` to make room.
2. **Delete all interior nights** between from/to.
3. **UPDATE existing rows** in the range to status 40, set `StatusTime=NOW()`, `StartDate=@FromDate`, `EndDate=@ToDate`.
4. **INSERT missing nights** using `master.dbo.spt_values` `[SQL_QUIRK]` to generate the date series:
   ```sql
   SELECT DATEADD(DAY, number, @AvailableDate) AS AvailableDate
   FROM master.dbo.spt_values
   WHERE type='P' AND number <= DATEDIFF(DAY, @AvailableDate, @ToDate)
   ```
5. Record fields per row: `PropertyId`, `AvailableDate`, `StartDate`, `EndDate`, `AvailableStatus=40`, `StatusTime`, `Notes`, `CreatedBy`, `CreatedAt`.

### Outputs / side effects
- **DB write:** N rows in `VillaAvailability` (N = nights in range).
- Calendar UI refreshes to show hold.
- Other system reads `QuotationNo` to find the hold during conversion.

### Failure modes
- `Status <= 0` → SP rejects ("Invalid status").
- Same-day check-in/check-out for back-to-back bookings is fragile: half-day handling depends on `CheckinTime` < noon vs > noon — see the boundary-night handling in `sp_getAvailability`.

### Open questions
- Using `master.dbo.spt_values` is a SQL Server idiom that doesn't exist in Postgres. Redesign uses `generate_series(from_date, to_date - 1, '1 day')`.

---

## Auto-expire stale holds (scheduler)

**ID:** `AVAILABILITY.HOLD.EXPIRE`
**Trigger:** Scheduler tick (`PaymentReminderSchedulerJob` — see `12-automation/scheduler-jobs.md`).
**Actor:** Background worker.
**Legacy locus:** `ResService.cs:238-275` (within the scheduler job).

### Inputs
- Implicit: current UTC datetime.

### Process
1. Query: `SELECT Id, isnull(UpdatedAt, CreatedAt) Data FROM VillaAvailability WHERE AvailableStatus = 40`.
2. For each row, compute `targetDate = createdAt.AddDays(7)`. If `UtcNow >= targetDate` → expire.
3. Raw SQL: `UPDATE VillaAvailability SET AvailableStatus=70, UpdatedAt=NOW(), UpdatedBy=0, Notes='OnHold Status autoremoved from scheduler task on Date {currentDate}' WHERE Id={id}`.

### Outputs / side effects
- **DB write:** `VillaAvailability.AvailableStatus` flips 40 → 70.
- **Notes** field gets the auto-removal message (only audit trail; no event row).
- **No email** to the quoting agent.

### Failure modes
- Scheduler not running → holds **never** expire. The job is currently commented out in `SchedullerJob.cs:50-52` — meaning in production the cleanup behaviour is **not active**. `[DISABLED]`
- Concurrent scheduler invocations could double-update — no `SELECT … FOR UPDATE`.

### Open questions
- The Django redesign should make hold expiry deterministic (`expires_at` column populated at create-time, a single sweep query, idempotent).
- Consider notifying the agent when a hold is auto-released so they can re-quote.
