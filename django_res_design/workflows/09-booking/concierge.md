# Concierge

Optional add-on services (chef, airport transfer, catering, etc.) attached to a booking. Two service levels exist: Quintessential (basic) and Signature (premium, included in balance) — gated by `ConciergeService` enum.

## Save concierge service add-ons

**ID:** `BOOKING.CONCIERGE.SAVE`
**Trigger:** "Save Concierge" button on the Concierge panel of `Booking.razor:442`.
**Actor:** Staff.
**Legacy locus:** `Booking.razor:987-1021`; `ResService.cs:3662-3704` (concierge save path); SPs `sp_concierge`, `SP_BOOKING_CONCIERGE`.

### Inputs
- `ConciergeVM`: `Id` (service level id), `Description` (e.g., `"Signature"`, `"Quintessential"`), `Guid`
- `List<ConciergeItem>`: per-item `ConciergeId`, `CurrencyId`, `Price`, `Description` (e.g., "Chef service", "Airport transfer")
- Implicit: `QuotationNo` (booking ref), `UserId`

### Process
1. Validate: at least one concierge item, and concierge payment not already received.
2. **Header**: `sp_concierge` with `@BookingRefNo`, `@UserId`, `@ConciergeId`, `@Description`. Returns `@Id` (concierge master record id).
3. **Clear existing items**: `SP_BOOKING_CONCIERGE @Action=DELETE` for the concierge id.
4. **Bulk insert items** into `VillaBookingConcierge` via `BulkInsertAsync` mapping (`ConciergeId`, `CurrencyId`, `Price`, `Notes` ← `Description`).
5. **Push to WordPress**: `_apiService.PushConciergeBookingToWP({ ConciergeId, BookingId, Description, ConciergeData[] })`. Response carries a slug that's persisted via raw SQL (`UPDATE VIllaConcierges` `[TYPO]` `SET Slug='{url}' WHERE Id={id}`).
6. UI updates the in-memory concierge object with returned slug.

### Outputs / side effects
- **DB write:** `VillaBookingConcierge` rows (rewritten), concierge master row, slug field on `VIllaConcierges` `[TYPO]`.
- **Outbound push:** WordPress concierge endpoint (see `11-integrations/public-website-sync.md` → `INTEGRATIONS.PUBLIC_API.CONCIERGE_SYNC`).
- Toast "Concierge save successfully!".

### Failure modes
- No items → "Please add at least one Concierge price!".
- Already-paid concierge → blocked.
- WordPress push failure → caught; concierge persisted locally but no slug.

### Open questions
- Delete-and-reinsert items breaks any external references. Diff-and-patch is safer.
- `VIllaConcierges` table-name typo to fix in migration.

---

## Request concierge payment from guest

**ID:** `BOOKING.CONCIERGE.REQUEST_PAYMENT`
**Trigger:** "Request Payment" button on a concierge card (`Booking.razor:439`).
**Actor:** Staff.
**Legacy locus:** `ResService.cs:3731-3789`.

### Inputs
- `ResBookingDetails` (full booking context)
- `ConciergeVM` (the chosen service to bill for)

### Process
1. Filter `Concierges[]` to items matching `ConciergeId`.
2. Load template `CONCIERGE_PAYMENT_TEMPLATE` from disk.
3. Build HTML table of items (description + price in guest currency).
4. Build placeholders dictionary: logo URL, user name, booking ref, villa name, dates, party size, check-in info, service inclusions, booking notes, villa info, concierge table, total.
5. `EmailTemplates.Render(filePath, placeholders)` — substitutes `[#PLACEHOLDER#]` tokens.
6. `EmailConfig`:
   - `Module = "PAYMENT_URL_EMAIL"`
   - `Body =` rendered HTML
   - `To =` `ClientDetails.Email`
   - `Subject = "Concierge payment request"`
7. `EmailService.SentEmail()`.

### Outputs / side effects
- **Email out** to guest with itemised concierge request.
- Toast "Email sent successfully to {guest name}".

### Failure modes
- No items selected → "Please add at least one Concierge price!".
- SMTP failure → toast error.

### Open questions
- Concierge billing is fully decoupled from the 3-tier payment schedule — it's a separate one-off charge. The redesign should decide whether to fold this into the schedule as a 4th tier or keep it as ad-hoc invoices.
