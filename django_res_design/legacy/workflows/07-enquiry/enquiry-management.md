# Enquiry Management

Read, edit, and status-transition workflows on existing enquiries.

## List / search enquiries

**ID:** `ENQUIRY.MGMT.LIST`
**Trigger:** Staff opens the Enquiries page; applies filters (date range, agent, status).
**Actor:** Staff.
**Legacy locus:** `ResService.cs:2660` (`GetEqnuireDetails` `[TYPO]`); SP `sp_getEnquireData`.
**Screen:** the legacy `/quote` list grid this backs (columns, status-circle colours, admin-only delete, row navigation) is specified in [`../legacy-quote-enquiry-reference.md`](../../quote-enquiry-reference.md) §4 — it was missing from the tree this spec was extracted from.

### Inputs
`PageEventArgs`:
- `FromDate`, `ToDate`
- `AgentId`
- `Status` (1=New, 2=Quoted, 3=Booked, …)
- Pagination: `Skip`, `Next`
- Search: `Search`
- Sort: `Column`, `SortOrder`

### Process
1. Execute `sp_getEnquireData` with the filter parameters.
2. Map to `List<EnquireDetailsVM>`.

### Outputs / side effects
- Read-only. Grid bound.

---

## Edit enquiry

**ID:** `ENQUIRY.MGMT.UPDATE`
**Trigger:** Staff clicks Edit on an enquiry row, modifies, saves.
**Actor:** Staff.
**Legacy locus:** Same `PostEnquireNew` path with `Action=UPDATE`.

### Inputs
Full `EnquireArgs` payload as in intake (now including an `Id`).

### Process
1. `sp_villaEnquire` with `@Action=UPDATE`.
2. Background `PushZohoEnqueireAsyncNew` push to update Zoho.
3. If dates change, `Length_of_Stay` is recomputed for the Zoho payload.

### Outputs / side effects
- **DB write:** `VillaEnquire` UPDATE; `UpdatedAt`, `UpdatedBy`.
- **Zoho sync:** updated record.

### Failure modes
- Same as intake.

---

## Update enquiry status

**ID:** `ENQUIRY.MGMT.SET_STATUS`
**Trigger:** Internal — called by quotation send (`QUOTATION.TRANSMISSION.SEND_EMAIL` sets status to 2) and by booking creation paths.
**Actor:** System.
**Legacy locus:** `ResService.cs:4124` (called inline after quote email send): `EXEC sp_updateEnquireStatus {EnquireId}, {2}`.

### Inputs
- `EnquireId`
- New status code (1=New, 2=Quoted, 3=Booked, plus likely 4=Lost / 5=Closed)

### Process
1. Execute `sp_updateEnquireStatus`.
2. Update `VillaEnquire.Status` and `UpdatedAt`.

### Outputs / side effects
- **DB write:** status field flip.
- **No audit row** of the transition.

### Open questions
- The full set of valid statuses is not enumerated in committed code. Recover and document.
- Each status transition deserves an event row in the redesign for traceability.
