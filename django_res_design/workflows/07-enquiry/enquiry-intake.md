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

### Idempotency
- **Not idempotent.** No dedupe key — a duplicate POST creates a duplicate `VillaEnquire` row with a fresh `EnquiryNo`. The public website's client-side debounce is the only guard. The Django port should accept a client-supplied `Idempotency-Key` header per RFC draft and short-circuit duplicates at the controller; or fall back to a fuzzy duplicate-key on `(Email, FromDate, ToDate, sha1(payload))` checked within a short window.

### Failure modes
- Network failure on SP → caller exception, no enquiry, no emails.
- Email service down → emails fail silently; enquiry persists, Zoho push happens.
- Zoho API down → enquiry persists, no Zoho record; **no retry** captured. See sub-workflow `ENQUIRY.INTAKE.ZOHO_PUSH` below.
- Required-fields validation: trust the caller (public website performs client-side validation). The SP accepts almost anything.

### Open questions
- Three of the field/column names have typos preserved (`EnquireSaurce`, `PlateFormId`, `EnquireArgs` itself). Rename in the redesign.
- Zoho push **must** be retried on failure — push it through a Celery task with retry/back-off (specified in `ENQUIRY.INTAKE.ZOHO_PUSH`).

### Django redesign — structured date flexibility *(updated 2026-06, quote-builder rework)*

The legacy `EnquireDateTypeString` enum (`SpecificDays` / `ThreeDays` / `SevenDays` / `WholeDays`) encoded the inquiry-taker's date-flexibility preset at the column level. Per the 2026-05-26 scoping session with the site owner, this column carried no operator-meaningful information after capture — it was a UI selector that did not flow through to pricing or availability decisions.

The first redesign dropped the encoding entirely and let the operator widen `date_from`/`date_to` by hand (the intake form's "± n days" stepper shifted the dates **destructively** on submit). That lost the client's true dates, so the 2026-06 quote-builder rework replaced it with structured, non-destructive capture:

- **`Enquiry.date_from` / `date_to` are the client's true requested dates** — the form never shifts them.
- **`Enquiry.flexibility_days` (0–3)** records the "± n days" the operator judges the client flexible by (most guests bend around changeover days — typically Saturday, sometimes Sunday or Monday). The intake form's stepper writes this field; a preview line shows the resulting search window.
- **The quote-builder search widens itself**: `POST /quotations:search-options` derives the window `requested ± flexibility_days` and, for fixed-changeover villas, offers the changeover-to-changeover stay blocks that fit it (default = closest to the requested arrival; alternatives reprice on pick).
- **When the client is genuinely flexible**: set `Enquiry.is_flexible = True`. That boolean reflects the client's *stated* flexibility and is display-only — only `flexibility_days` widens the search.

See `05-reservations.md` "Date flexibility on intake" for the model-side note and the pre-migration data caveat.

---

## Zoho push (sub-workflow of enquiry intake)

**ID:** `ENQUIRY.INTAKE.ZOHO_PUSH`
**Trigger:** Spawned as fire-and-forget background work at the end of `ENQUIRY.INTAKE.WEBSITE` / `ENQUIRY.INTAKE.STAFF`.
**Actor:** System.
**Legacy locus:** `ResService.cs:2395-2400` — wrapped in `Task.Run(async () => { ... })` with **no `await`**, no continuation, no exception handler. The `Task` is dropped on the floor; any exception is swallowed by the .NET task scheduler and never surfaces.

### Inputs
- The `EnquireId` from the just-inserted enquiry row, plus the constructed `Zoho_VillaEnquireData` payload (see `INTEGRATIONS.ZOHO.PUSH_ENQUIRY` in `11-integrations/zoho-crm.md`).

### Process
1. `_apiService.PushZohoEnqueireAsyncNew(obj)` POSTs to the Zoho CRM API under module `VILLA_ENQUIRY`.

### Outputs / side effects
- On success: `VillaEnquire.ZohoId` is updated (via the integration path).
- On failure: **nothing happens**. No retry, no DLQ, no row in any error table, no log entry beyond whatever `_apiService` itself catches internally.

### Idempotency
- The push uses the `EnquireId` as the natural key on the Zoho side; a duplicate replay would either upsert or produce a duplicate Zoho record depending on the module's dedupe config. **The legacy code does not verify Zoho's dedupe behaviour.** Django port should treat this as non-idempotent until proven otherwise.

### Failure modes
- **Silent loss on Zoho outage** `[CORRECTNESS]` — the most common production failure mode. Enquiries land in the legacy DB but never reach Zoho; sales staff working from the Zoho dashboard miss them entirely.
- OAuth token expiry → the `_apiService` retries 3 times internally (`ResApiService.cs:1227-1276`, retry behaviour loose; see Zoho spec) then gives up.

### Django redesign requirement
- Replace `Task.Run(...)` with a Celery task: `tasks.push_enquiry_to_zoho.delay(enquiry_id)` after the `Enquiry` row commits.
- Task is keyed by `(SyncRecord.kind="ZOHO_ENQUIRY", target_id=enquiry.id)`; status transitions through `pending → in_progress → succeeded | failed`.
- Failure path: exponential back-off (Celery `autoretry_for`, `max_retries=5`, `retry_backoff=True`, `retry_jitter=True`); after exhaustion, raise to a DLQ table (`integrations.FailedSync`) for operator triage.
- Idempotency: the Celery task is keyed on `SyncRecord.id`; the worker takes a `select_for_update` on the row before pushing, so concurrent worker replays are linearised.

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
