# 07 · Enquiry

Inbound interest — a customer (via public website) or a staff member (via back-office form) saying "I want a villa for these dates / region / party size". Enquiries are the head of the funnel:

```
Enquiry → Quotation (one-or-more) → Booking → Payment → Stay
```

## Files

| File | Workflows |
|---|---|
| [`enquiry-intake.md`](./enquiry-intake.md) | Receive enquiry from public website, create enquiry manually (staff) |
| [`enquiry-management.md`](./enquiry-management.md) | List enquiries, edit enquiry, update enquiry status |

## Entities touched

- `VillaEnquire` — `Id`, `EnquiryNo` (display ref), `FirstName`, `LastName`, `Email`, `Title`, `CountryCode`, `ContactNo`, `Town`, `Country`, `PostCode`, `AddressLine1`, `AddressLine2`, `FromDate`, `ToDate`, `EnquireDateTypeString` (e.g., `"SpecificDays"`, `"ThreeDays"`, `"SevenDays"`, `"WholeDays"`), `MinBed`, `MaxBed`, `Adults`, `Children`, `Countries`, `Region` (comma-delimited), `Properties`, `RequestType` (e.g., `"WISHLIST"`), `UserFeedback` (marketing source), `Notes`, `referral`, `IsSignUp`, `PlateFormId` `[TYPO]`, `EnquireSaurce` `[TYPO]` (intended `EnquirySource`), `Status` (1=New, 2=Quoted, 3=Booked, …), `CreatedAt`, `CreatedBy` (=`"WEBSITE"` for public submissions, staff username otherwise), `AgentId`

## Stored procedures

- `sp_villaEnquire` — primary CRUD (INSERT/UPDATE/etc.)
- `sp_getEnquireData` — paginated list
- `sp_updateEnquireStatus` — single-purpose status setter
- `sp_check_email_exits` — used by sign-up branch

## Cross-cutting notes

- **Public vs staff branching** is by `User` field — `"WEBSITE"` triggers auto-emails (VC notification + guest auto-reply); any other value suppresses them.
- **Zoho sync is fire-and-forget**: `PushZohoEnqueireAsyncNew` runs in a background task. If Zoho is down, the enquiry exists locally but no Zoho record is created.
- **`EnquireDateTypeString`** captures date-flexibility: specific dates, +/- 3 days, +/- 7 days, "any time this whole period". The pricing engine doesn't currently use this to widen the search.
