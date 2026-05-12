# Enquiry Intake

The two paths by which an enquiry enters the system. They share most of the code; they diverge on what they trigger downstream.

## Receive enquiry from public website

**ID:** `ENQUIRY.INTAKE.WEBSITE`
**Trigger:** `POST` from public villacollective.com forms (villa detail page, landing page, wishlist).
**Actor:** Guest visitor.
**Legacy locus:** `ResService.cs:2367-2480` (`PostEnquireNew`); SP `sp_villaEnquire`.

### Inputs
`EnquireArgs` / `PostEnquireArgs`:
- Identity: `FirstName`, `LastName`, `Email` (required), `Title`, `CountryCode`, `ContactNo`
- Address (optional): `Town`, `Country`, `PostCode`, `AddressLine1`, `AddressLine2`
- Travel: `FromDate`, `ToDate`, `EnquireDateTypeString` ∈ {`SpecificDays`, `ThreeDays`, `SevenDays`, `WholeDays`}
- Property criteria: `MinBed`, `MaxBed`, `Adults`, `Children`, `Countries`, `RegionIds` (array → comma-joined into `Region` field), `Properties`
- Marketing: `RequestType` (e.g., `WISHLIST`), `UserFeedback` (marketing source: `"Previous Customer"`, `"Google/Online Search"`, `"Social Media"`, `"Friend/Family"`, …)
- `Notes`, `referral`, `IsSignUp`
- `PlateFormId` `[TYPO]` (source platform identifier)
- Implicit: `User="WEBSITE"`, `Action=INSERT`

### Process
1. Normalise: `args.Region = string.Join(",", args.RegionIds)`.
2. Execute `sp_villaEnquire` with the action and parameter set.
3. SP returns `EnquireId`, `EnquiryNo`, and other auto-assigned fields via output parameters.
4. Compute `EnquireSaurce`:
   - `WISHLIST` request type → `"From Website Wishlist"`
   - Else: `"Website Form on Villa details page"` or `"Website Form on Landing Page"` depending on `PlateFormId`.
5. Spawn background task (non-blocking, `ResService.cs:2395`):
   - `PushZohoEnqueireAsyncNew(obj)` — see `INTEGRATIONS.ZOHO.PUSH_ENQUIRY`.
   - Send VC internal notification email (template `VC_ENQUIRE_EMAIL`).
   - Send guest auto-reply email (template `VC_ENQUIRE_AUTO_REPLY`).

### Outputs / side effects
- **DB write:** `VillaEnquire` INSERT with `Status=1`, `CreatedBy="WEBSITE"`.
- **Emails out:** 2 (internal + guest).
- **Zoho sync queued** to custom `VILLA_ENQUIRY` module.

### Data transformations for storage
- `RegionIds` array → comma-string in `Region` column.
- `Length_of_Stay` = `(ToDate - FromDate).TotalDays + " nights"` is computed at Zoho-push time, not stored.
- Status starts at 1.

### Failure modes
- Network failure on SP → caller exception, no enquiry, no emails.
- Email service down → emails fail silently; enquiry persists, Zoho push happens.
- Zoho API down → enquiry persists, no Zoho record; **no retry** captured.
- Required-fields validation: trust the caller (public website performs client-side validation). The SP accepts almost anything.

### Open questions
- Three of the field/column names have typos preserved (`EnquireSaurce`, `PlateFormId`, `EnquireArgs` itself). Rename in the redesign.
- Zoho push **must** be retried on failure — push it through a Celery task with retry/back-off.

---

## Create enquiry manually (staff)

**ID:** `ENQUIRY.INTAKE.STAFF`
**Trigger:** "New Enquiry" button in the back-office, fill form, submit.
**Actor:** Staff / agent.
**Legacy locus:** Same `PostEnquireNew` path with `User = {staff username}` rather than `"WEBSITE"`.

### Inputs
Same as the public path, plus:
- `AgentId` (the staff member who entered the enquiry; routes routing/commission)
- `EnquireSaurce` (manually entered: `"Phone"`, `"Email"`, `"Walk-in"`, etc.)

### Process
Same as public, except:
- The condition `shouldEmailSent = args.Action == INSERT && args.User == "WEBSITE"` is **false**, so **no guest auto-reply email and no VC internal notification are sent**.
- Zoho push still queued.

### Outputs / side effects
- **DB write:** `VillaEnquire` INSERT, `CreatedBy = staff username`.
- **No emails** (staff controls communication explicitly).
- **Zoho sync:** yes.

### Open questions
- The "no emails on staff path" is an implicit policy. Make it explicit in the redesign (e.g., a "Send confirmation email" checkbox on the form).
