# Legacy ResSystem — Email Feature Inventory

> Source: `/Users/garethlloyd/projects/villacollective/ResSystem/`
> Purpose: separate what's in the staff UI from what's backend-only, for comparison
> against the client-emails mockup (`04-client-emails.md`).
> All line numbers are against the files committed at the time of writing.

---

## 1. Summary

Legacy ResSystem is a .NET 7 / Blazor Server admin app with **a single shared
`EmailService` class** (`NewResSystem.Core/Services/EmailServices/EmailService.cs`)
that wraps `System.Net.Mail.SmtpClient`. There is **one global SMTP profile**
stored in `VillaConfigEmail` (single row, admin-editable in the **Configuration →
Email** tab) and **optional per-user SMTP overrides** stored on `UserMaster`
(admin-editable in **Users**). The per-user SMTP is consulted **only** by
`EmailService.SentQuoteEmail`, which is used by `SentQuotation` /
`SentQuotationNew`.

Templates are dual-storage:

- **Filesystem** (`wwwroot/templates/email/*.html`) — used by older paths
  (auth code, password reset, enquiry form) and by `RequestPaymentConcierge`,
  which still does `EmailTemplates.Render(path, placeholders)` against
  `concierge-payment-template.html`.
- **Database** (`VCEmailTemplates` table, accessed via
  `sp_get_email_template_data` and `sp_owner_template`) — used by the newer
  `SentEmailAsync(templateKey, bookingRefNo)` path. Most of the active 2025
  email-sending sites resolve through this DB path.

Counts (call-sites in `NewResSystem.Core/`, excluding commented-out lines):

- **Templates referenced by key (`EmailTemplate.*` struct):** 12 distinct keys
  — `INITIAL_PAYMENT_TEMPLATE`, `BALANCE_PAYMENT`, `SECURITY_DEPOSIT_PAYMENT`,
  `CC_CARD_UPDATE`, `BOOKING_RECEIPT`, `UPGRADE_CONCIERGE_SERVICE_REQUEST`,
  `VILLA_LOOKUP_CONTENT`, `VC_ENQUIRE_EMAIL`, `VC_ENQUIRE_AUTO_REPLY`,
  `CC_BOOKING_CONFIRM`, `OWNER_BOOKING_CONFIRM` (legacy, references commented
  out), `VC_USER_PASSWORD_RESET`.
  Defined in `NewResSystem.Core/Enums.cs:341-355`.
- **Filesystem-only templates** (`Constant` class,
  `NewResSystem.Core/Enums.cs:303-325`): `email-enquiry.html`,
  `enquiry-auto-reply.html`, `initial_payment_template.html`,
  `security-deposit-payment-template.html`, `concierge-payment-template.html`,
  `vc-booking-receipt-email.html`, `villa-owner-booking-confirm.html`,
  `cc-booking-confirm.html`, `update_card_template.html`,
  `User-AuthCode.html`, `User-PasswordReset.html`, `quote-rate-lookup.html`.
  Most of these have been superseded by the DB-stored versions but are still
  on disk; the auth-code and password-reset HTML files remain in active use.
- **UI-driven "click to send" buttons in the staff app:** **3**
  (Resend Booking Summary, CC Booking Confirmation per-contact,
  Request Concierge Payment).
- **UI-triggered side-effect emails (no preview, fires as part of saving):**
  ~6 (Save Booking → INITIAL_PAYMENT + OWNER + CC confirm; Save Concierge
  checkout-info → UPGRADE_CONCIERGE_SERVICE_REQUEST; Save User /
  forgot-password; SaveBookingFinanceConfig → Request Manual Invoice).
- **Backend-only / webhook / scheduled triggers:** **5** (Flywire payment
  webhook → BOOKING_RECEIPT to payer+lead guest; website POST /api enquiry →
  VC_ENQUIRE_EMAIL + VC_ENQUIRE_AUTO_REPLY; cron-hit
  `/api/WordPressApi/Payment/BookingEmailReminder` → 4 payment-reminder
  templates).
- **Disabled / commented-out infra:** the entire `SchedullerJob`
  `BackgroundService` is commented out
  (`NewResSystem.Core/Services/BackgroundServices/SchedullerJob.cs:16-69`).
  `OWNER_BOOKING_CONFIRM` send is commented out at three sites in
  `ResService.cs` (3387, 3392, 3396) in favour of `SentEmailToOwner` which
  hits `sp_owner_template`. The "Start Booking - No Send" button
  (`Booking.razor:471`) is a documented bypass that suppresses **all** of the
  booking-confirmation emails.

**Key gaps in the staff UI:**

- No template editor in the staff UI — the DB templates in `VCEmailTemplates`
  are managed by direct SQL only.
- No email log / sent-history screen — outbound mail is dumped to per-day text
  files in `wwwroot/ResLogs/<ddMMyyyy>/...` via `Utilities.WriteResLogFile`.
  `VillaEmailLinkLog` exists (`Database/Data/VillaEmailLinkLog.cs`) but only
  for password-reset link auditing, not general email history.
- No "preview" or "test send" anywhere.
- No bulk / marketing email screen.
- No free-text composer.
- No way to cancel a queued email — there is no queue. All sends are
  fire-and-forget `await smtpClient.SendMailAsync`, often wrapped in
  `_ = Task.Run(...)` so the UI doesn't even know if delivery failed.

---

## 2. SMTP / sending infrastructure

### 2.1 System SMTP profile (the default)

- **Table:** `VillaConfigEmail` — single-row config table.
  - Entity: `Database/Data/VillaConfigEmail.cs` (12 columns:
    `Fromname`, `Fromaddress`, `Errortogeneric`, `Serveraddress`,
    `Serverport`, `Servertls`, `Serverauthentication`, `Serverusername`,
    `Serverpassword`, `Createdon`, `Updatedon`).
  - Production row (from
    `Database/Scripts/live-db-24-apr.sql:61382`):
    `smtp.office365.com:587` TLS+auth, username `hello@villacollective.com`,
    from-name `Villa Collective`, from-address `info@villacollective.com`,
    error-to `ben@mojomedia.co.uk`. **Password is stored in cleartext in
    the DB and committed in the SQL dump.**
- **CRUD proc:** `SP_CRUD_VillaConfigEmail`
  (`Enums.cs:56`), called from `ConfigurationService.SaveVillaConfigEmail`.
- **Loaded by:** `EmailService.SentEmail`
  (`EmailServices/EmailService.cs:36`),
  `EmailService.SentQuoteEmail`
  (`EmailServices/EmailService.cs:133` — used as the *fallback* when the
  user has no per-user SMTP set),
  and `EmailService.SentEmailToVC`
  (`EmailServices/EmailService.cs:254`).
- **Editable in staff UI:**
  `NewResSystem/Pages/Admin/Configuration.razor:142-217` — the "Email" tab.
  Two cards: "Sending config" (from-name, from-address, errors-to) and
  "Server settings" (address, port, TLS, auth, username, password).
  Submit handler at `:675` calls
  `configurationService.SaveVillaConfigEmail(_email, DbAction.INSERT)`.

### 2.2 Per-user SMTP (the "send as agent" path)

- **Table columns:** `UserMaster.SmtpAddress`, `SmtpUserName`,
  `SmtpPassword`, `Port`, `IsTlsRequired`, `IsAuthRequired`.
- **Used by:** `EmailService.SentQuoteEmail`
  (`EmailServices/EmailService.cs:127-148`). The code reads the user record
  for the `userId` passed in, and *if all of SmtpUserName, SmtpAddress,
  SmtpPassword are populated*, overrides the system SMTP with the user's
  credentials and rewrites `From` to `"FirstName LastName"
  <user.SmtpUserName>`. Otherwise it falls back to system SMTP.
- **Callers:** only the two `SentQuotation` / `SentQuotationNew` methods
  (`ResService.cs:4121`, `4183`) — these are NOT wired to any active staff
  UI page (see §4 / §10). The agent-as-sender capability is therefore
  effectively dead in the current Blazor UI; quote sends in the current
  build go through the DB-template path (`INITIAL_PAYMENT_TEMPLATE` via
  `SentEmailAsync`), which uses the SYSTEM SMTP, not the agent's.
- **Editable in staff UI:**
  `NewResSystem/Pages/Admin/Users.razor:96-137` — "SMTP Details" card on the
  user edit form. Free-form, validated only in the no-some-some-some
  branch (`:325-346`).
- **Storage:** plaintext in `UserMaster.SmtpPassword`.

### 2.3 Hard-coded BCC

`EmailService.SentEmail` line 71 unconditionally BCCs every send to
`connectusinfowaydemo12@gmail.com` (the dev vendor's mailbox). Every
non-quote email ever sent by this system was copied to that address.

### 2.4 Email-as-transport, not email-as-data

There is no `EmailLog`/`EmailMessage`/`SentEmail` table. Outbound mail
state is only persisted as:

- per-day plaintext files at `wwwroot/ResLogs/<ddMMyyyy>/`
  (written by `Utilities.WriteResLogFile`);
- `VillaEmailLinkLog` (`Database/Data/VillaEmailLinkLog.cs`), used by
  `UserService.EmailLinkLog` to record password-reset link issuance
  with `TemplateType`, `Code`, `EmailTo`, `SentAt`, `UsedAt`,
  `UsedExpireAt`. Not used for any other template.
- `VillaBooking.IsEmailSent` (a bool on the booking row, set by the
  scheduler only for the rental-balance reminder —
  `ResService.cs:178`).

There is no queue, no retry, no DLQ. Every send is a synchronous
`await smtpClient.SendMailAsync` inside the request thread (or a
fire-and-forget `Task.Run`).

---

## 3. Template storage

### 3.1 Database — `VCEmailTemplates` (the primary store as of 2025)

- **Entity:** `Database/Data/VcemailTemplate.cs`. Columns:
  `Id`, `SourceId`, `DestinationId`, `Template` (the HTML body),
  `Subject`, `Type` (string discriminator e.g.
  `CC_VO_BOOKING_CONFIRMATION`), `Description`,
  `CreatedAt`/`CreatedBy`/`UpdatedAt`/`UpdatedBy`.
- **Read proc:** `sp_get_email_template_data` (`Enums.cs:169`,
  called by `ResService.GetEmailTemplate(template, bookingRefNo)`
  — `ResService.cs:561`).
- **Owner-specific read proc:** `sp_owner_template`
  (`Enums.cs:170`, called by the second overload at `ResService.cs:573`,
  used by `SentEmailToOwner`).
- **Insert proc:** `sp_save_vc_email_template` (`Enums.cs:160`). Called
  only once, at `ResService.cs:3385`, as part of `ModifyBooking` to
  *snapshot* the CC-booking-confirm template against the new booking
  (`SourceId=VillaId`, `DestinationId=BookingId`,
  `Type=CC_VO_BOOKING_CONFIRMATION`). This is how the per-property CC
  confirmation later gets resolved by the "Send CC Booking Confirm"
  button (§4).
- **No UI editor** — there is no Blazor page that reads or writes
  `VCEmailTemplates`. Edits happen in SQL.
- **No versioning** — no `Version` column, no audit table.
- **No localisation** — single template body per key.

### 3.2 Filesystem — `wwwroot/templates/email/`

Live files (from `ls`):

- `email-enquiry.html` (referenced by `Constant.ENQUIRY`, used only in
  commented-out code at `ResService.cs:2390+`)
- `User-AuthCode.html` (referenced by `Constant.EMAIL_AUTH_CODE_TEMPLATE`,
  actively used by `UserService.SentAuthCode` at `:190`)
- `User-PasswordReset.html` (referenced by
  `Constant.EMAIL_PWD_RESET_TEMPLATE` — but the active password-reset
  path now uses the DB template `VC_USER_PASSWORD_RESET`; this file is
  effectively dead — line 319 in `UserService.cs` comments out the
  filesystem read in favour of `GetEmailTemplate(VC_USER_PASSWORD_RESET, 0)`)
- `User-PasswordSet.html` — unreferenced from code in this checkout.

Other filenames referenced by `Constant` (`Enums.cs:303-325`) that
target this directory but which I could not find on disk in the current
working copy (likely runtime-deployed, or removed in the move to DB
templates):
`initial_payment_template.html`, `security-deposit-payment-template.html`,
`concierge-payment-template.html`, `vc-booking-receipt-email.html`,
`villa-owner-booking-confirm.html`, `cc-booking-confirm.html`,
`update_card_template.html`, `enquiry-auto-reply.html`,
`quote-rate-lookup.html`. The
**concierge payment** template is loaded by path at
`ResService.cs:3723` (`RequestPaymentConcierge`) — so the rendered file
must exist in the production deployment even though it's not in the repo
working tree.

### 3.3 Inline strings (hard-coded subjects / bodies)

- **`SentInvoiceMailByBookingId`** (`ResService.cs:3577-3599`) —
  the **Request Manual Invoice** email body is built with a `StringBuilder`
  of literal HTML in C#. To/CC are hard-coded:
  `tash.accounts@villacollective.com` and `info@villacollective.com`.
  Subject is `"Request manual invoice from {fullName}"`.
- **`ModifyBooking` payment-link message** (`ResService.cs:3357-3361`)
  — `"<h4>Villa Collective payment link</h4>"` etc. is built inline,
  but this StringBuilder is **assigned but never sent**; the actual sends
  on this path resolve `INITIAL_PAYMENT_TEMPLATE` from the DB.
- **`SentBookingConfirmEmail`** (`ResService.cs:3621-3660`) — subject
  literal `"CC Booking Confirmation"`; body comes from `VCEmailTemplates`.

### 3.4 Inline placeholder rendering

For DB templates, replacement is done inside `sp_get_email_template_data`
(SQL Server T-SQL string concatenation, not visible from the working
tree since the proc body is not in the dump). For filesystem templates,
`Shared/EmailTemplates.cs` does naive `String.Replace` of
`[#TOKEN#]` placeholders (`EmailTemplates.cs:10-25`).

---

## 4. UI-driven email actions (staff clicks a button)

These are the only places where a staff member *explicitly chooses* to
send an email by clicking a control. Three buttons. No preview, no
"send a test", no confirmation modal.

| # | Screen | Action | Template | File:line | Notes |
|---|---|---|---|---|---|
| 1 | `Pages/Bookings/BookingInfo.razor` | **"Resend Booking Summary"** button per booking row | `BOOKING_RECEIPT` | button `:155`, handler `SentReceipt` `:202-224` → `ResService.SentReceiptEMailAsync(EmailTemplate.BOOKING_RECEIPT, …)` `:5145-5162` | Re-renders the booking-receipt HTML to PDF via `Utilities.Createpdf`, attaches `VillaCollectiveBookingTermsConditions.pdf` from `wwwroot/templates/email/`, then sends to the lead-guest email pulled from `sp_get_email_template_data`. No confirmation, no preview. |
| 2 | `Pages/Properties/Contacts/PropertyContacts.razor` | **CC Booking Confirmation icon-check** (per property-contact row, shown only when contact is not already CC/primary/Owner) | `VCEmailTemplates` row of type `CC_VO_BOOKING_CONFIRMATION` (whatever was snapshotted at booking time) | button `:59`, handler `SentBookingConfirmEmail` `:577-591` → `ResService.SentBookingConfirmEmail` `:3621-3660` | Looks up `VCEmailTemplates` rows where `SourceId = VillaId` (one row per booking made for that villa), iterates them, sends each with subject literal `"CC Booking Confirmation"` to the chosen property contact. Hardcoded subject. No preview. |
| 3 | `Pages/Bookings/Booking.razor` | **"Request Payment" button** (one per concierge service line in the Concierge card) | filesystem `concierge-payment-template.html` (`Constant.CONCIERGE_PAYMENT_TEMPLATE`) | button `:439`, handler `RequestConciergePayment` `:1037-1059` → `ResService.RequestPaymentConcierge` `:3717-3801` | Hardcoded `baseUrl = "https://vc2.mojodev.co.uk"` (`:3722`) — points at the dev environment regardless of where the app is running. Renders the file template with `[#…#]` placeholders, subject literal `"Concierge payment request"`, sends to `ClientDetails.Email`. |

---

## 5. UI-triggered automatic emails (user action → email, no preview)

The user clicks "Save" or "Confirm" and emails fire as a *side effect*.
There is no opt-out, no preview, no UI affordance that an email will go
out beyond label text on the button itself.

| # | Screen / trigger | Template(s) | File:line | Notes |
|---|---|---|---|---|
| 1 | `Pages/Bookings/Booking.razor` — **"Start/Update booking"** button (`:462`, `SaveBookingDetails(true)`) | `INITIAL_PAYMENT_TEMPLATE` (to client), then `sp_owner_template` lookup (to owner/CC contacts) | handler `:886-953` → `ResService.ModifyBooking` `:3194` → email block at `:3363-3410` | The owner email is *only* sent when `isSent=true` is passed, i.e. when the button labelled "Start/Update booking" is used. The block also writes a `CC_VO_BOOKING_CONFIRMATION` row to `VCEmailTemplates` (`:3385`) so later button #2 in §4 has something to resolve. |
| 2 | `Pages/Bookings/Booking.razor` — **"Start Booking - No Send"** button (`:471`, `SaveBookingDetails(false)`) | none | same handler with `isSent=false` | This is the documented (via monday.com link in the code comment, `:880`) escape hatch — pass `ownerDetails=null` and the entire email block at `ResService.cs:3363` is skipped, including the client `INITIAL_PAYMENT_TEMPLATE`. So this button silently suppresses the deposit-request email; the only signal to staff that this matters is the button label. |
| 3 | Save Checkout (concierge service requested during guest checkout) | `UPGRADE_CONCIERGE_SERVICE_REQUEST` | `ResService.cs:4945-4948` (inside `SaveCheckoutInfo`) | Fires when `personalInfo.IsConciergeService == true`. Triggered via the `POST /api/WordPressApi/Payment/SaveCheckoutInfo` controller, called from the WordPress-hosted checkout, *not* from a Blazor screen — but classed here because the *user action* is the guest checking the concierge box on the WP form. |
| 4 | `Pages/Admin/Users.razor` — Save user with empty password (`:325-376`) → `UserService.ModifyUsers` calling the password-set flow | `User-AuthCode.html` (the active branch via `SentAuthCode`) | `UserService.cs:208` (auth-code email) and `:326` (password reset, via separate `ForgotPasswordAsync`) | Saving a new user causes the 2FA / password-set email to fire as a side-effect of save. |
| 5 | `Pages/Account/Login.cshtml` — login form 2FA branch | `User-AuthCode.html` (template loaded from filesystem at `UserService.cs:190`) | login handler at `Login.cshtml.cs:79` and `:224` (`Resend Code` link `Login.cshtml:110`) | The 6-digit code email. Wraps `sp_crud_auth_code` to persist the code with a 2-hour expiry. |
| 6 | `Pages/Account/Login.cshtml` — **"Forgot your password?"** link (`:76`) | `VC_USER_PASSWORD_RESET` (DB template) | redirect to `/forgot-password` (`Login.cshtml.cs:250`) which is NOT a Blazor route in this repo — the page is missing, suggesting it lives in the WP site that POSTs back into `ForgotPasswordAsync` (`UserService.cs:311-340`) | The reset-link write to `VillaEmailLinkLog` is the only template-bound send that produces a real audit row. |

---

## 6. Backend-only / scheduled emails (no UI affordance)

These fire without any staff interaction at all. The trigger is either
an external HTTP call (webhook), an external cron-style HTTP call into a
controller endpoint, or a domain-event side effect inside a service.

| # | Trigger / scheduler | Template | File:line | Notes |
|---|---|---|---|---|
| 1 | **External cron → `GET /api/WordPressApi/Payment/BookingEmailReminder?key=…`** (`PaymentController.cs:235-273`). Auth via hard-coded GUID `130d0022-8fe4-4878-8ec2-c44c939bb336` (`:41`). Calls `ResService.PaymentReminderSchedulerJob` (`:100-293`). | a) `INITIAL_PAYMENT_TEMPLATE` (when checkout-date hits, initial unpaid) — `:157`<br/>b) `BALANCE_PAYMENT` (when checkout-date hits, balance unpaid) — `:166`<br/>c) `SECURITY_DEPOSIT_PAYMENT` (7d before checkout OR on arrival, SD unpaid) — `:173`<br/>d) `CC_CARD_UPDATE` (checkout-date, card-on-file path) — `:206` | `ResService.cs:100-293` | The in-process `SchedullerJob` `BackgroundService` (`Services/BackgroundServices/SchedullerJob.cs`) is **commented out in its entirety** (`:16-69`). The scheduler is therefore driven by an *external* cron hitting the controller endpoint. The same job also auto-removes stale "OnHold" availability after 7 days (`:238-280`) — unrelated to email but bundled in. |
| 2 | **Flywire payment webhook → `POST /api/WordPressApi/Payment/PaymentStatusWebHook`** (`PaymentController.cs:96-143`) → `ResService.PaymentStatusNotification` (`:4374-4467`) → `SentEmailToPayerAndLeadGuest(bookingRefNo)` (`:4422`) when status == `"guaranteed"`. | `BOOKING_RECEIPT` (with PDF attached + Terms PDF) | `ResService.cs:4500-4519` | The PDF is generated on the fly with `Utilities.Createpdf(template)`. Sends to **both** payer (from `sp_get_emails`) and lead-guest email from the DB template lookup. |
| 3 | **Website enquiry form → `POST /api/WordPressApi/Properties/PostEnquire`** (`PropertiesController.cs:61-97`) → `ResService.PostEnquireNew` (`:2367-2480`). Two emails fire as a `Task.Run` side-effect: one to VC mailbox via `SentEmailToVC` (`:2448`), one to the enquirer via `SentEmailAsync(VC_ENQUIRE_AUTO_REPLY, …)` (`:2450`). | `VC_ENQUIRE_EMAIL` (to VC), `VC_ENQUIRE_AUTO_REPLY` (to guest) | `ResService.cs:2387-2467` | Fires only when `args.Action == INSERT` and `args.User == "WEBSITE"` (line 2386). i.e. only fresh, public-site enquiries trigger these — admin-created enquiries do not. |
| 4 | **Save payment status** from the WordPress checkout (`PaymentController.SavePaymentStatus`) → `ResService.SavePaymentStatus` (`:3426-3485`) → `SentEmailToPayerAndLeadGuest(model.Id)` (`:3452`). | `BOOKING_RECEIPT` (with PDF + T&Cs PDF attached) | `ResService.cs:4500-4519` | Overlaps with #2 above. Likely either a belt-and-braces double-send or a leftover from an earlier flow; the comment at `:4421` (`//isSent = await SentEmailAsync(EmailTemplate.BOOKING_RECEIPT, ...)`) shows the path has been refactored at least once. |
| 5 | **Owner-confirmation email after booking save** — `ResService.SentEmailToOwner(bookingRefNo)` (`:4469-4498`) called from `ModifyBooking` (`:3397`) when `ownerDetails != null`. Uses `sp_owner_template` to fan out to multiple owner-side contacts. | Multiple DB rows from `sp_owner_template` — typically a render of `OWNER_BOOKING_CONFIRM` semantics but resolved per-row, per-contact. | `ResService.cs:4469-4498`, `:573-583` | This is *classed* as backend-only because the staff member doesn't see the recipients or get to choose them — the `sp_owner_template` proc decides who gets the email based on the booking's villa contacts. |

---

## 7. Disabled / dead-letter triggers

- **`SchedullerJob` BackgroundService** — entire class commented out
  (`NewResSystem.Core/Services/BackgroundServices/SchedullerJob.cs:16-69`).
  Never registered with `AddHostedService` in `Program.cs`. The intended
  in-process cron was abandoned in favour of the external HTTP-cron
  endpoint described in §6 #1.
- **`OWNER_BOOKING_CONFIRM` direct send** —
  `ResService.cs:3387`, `:3392`, `:3393`, `:3396` are all commented out,
  superseded by `SentEmailToOwner` (which uses `sp_owner_template`
  rather than a single template key).
- **Filesystem enquiry templates** — `email-enquiry.html` and
  `enquiry-auto-reply.html` paths at `ResService.cs:2389-2459` are all
  commented out; the active flow uses DB templates `VC_ENQUIRE_EMAIL`
  and `VC_ENQUIRE_AUTO_REPLY`.
- **`PropertyService` commented send at `:1494`** — `_service.SentEmail(emailConfig)` left as a TODO marker; no longer reachable.
- **`User-PasswordReset.html`** — present on disk but `UserService.cs:319`
  comments out the filesystem read; the active path is
  `GetEmailTemplate(EmailTemplate.VC_USER_PASSWORD_RESET, 0)`.
- **`SentQuotation` / `SentQuotationNew`** — the only two methods that
  consult per-user SMTP via `SentQuoteEmail`. They are not called from
  any active Blazor screen in this repo (search of `Pages/` returns no
  callers). The capability to "send a quote as the agent" is therefore
  dead code in the current build, although the per-user SMTP fields in
  `Users.razor` remain visible and editable.
- **`SaveBookingDetails(isSent=false)`** — the "Start Booking - No Send"
  button (`Booking.razor:471`) silently disables all the booking-save
  emails by passing `ownerDetails=null`. Documented in a monday.com link
  in a code comment (`:880`).
- **Hard-coded BCC `connectusinfowaydemo12@gmail.com`**
  (`EmailService.cs:71`) — leaks every non-quote email to a dev-vendor
  Gmail account. Likely should have been removed before go-live.

---

## 8. UI screens specifically about email

| Question | Answer | Reference |
|---|---|---|
| Is there a **template list / edit screen**? | **No.** | — |
| Is there an **email log / sent-history screen**? | **No.** Outbound mail is dumped to per-day plaintext under `wwwroot/ResLogs/<ddMMyyyy>/...` via `Utilities.WriteResLogFile`. `VillaEmailLinkLog` is the only audit-style table and is scoped to password-reset link tokens. | `EmailService.cs:122`, `Database/Data/VillaEmailLinkLog.cs` |
| Is there a **system SMTP profile screen**? | **Yes** — Admin → Configuration → "Email" tab. Two cards (Sending config / Server settings). | `Pages/Admin/Configuration.razor:142-217` |
| Is there a **per-user SMTP profile screen**? | **Yes** — Admin → Users → user edit form → "SMTP Details" card. | `Pages/Admin/Users.razor:96-137` |
| Is there a **bulk / marketing email screen**? | **No.** | — |
| Is there a **free-text email composer**? | **No.** All sends go through a named template or a hard-coded body. | — |
| Is there a **preview / test-send screen**? | **No.** | — |
| Is there a **per-booking communications tab** (history of what was sent for this booking)? | **No.** The only persisted booking-level signal is `VillaBooking.IsEmailSent` (a single bool set by the rental-balance reminder only). | `ResService.cs:178` |
| Is there a **template-pick UI** before sending? | **No.** Every UI send is hard-bound to one template at the call site. | — |
| Can staff **cancel a queued email**? | **No queue exists.** Sends are synchronous SMTP calls or fire-and-forget `Task.Run`. | `EmailService.cs:99-111` |
| Can staff **resend a previously sent email**? | **Partly** — "Resend Booking Summary" on `BookingInfo.razor:155` is the only resend button. It re-renders from current DB state, not from the original payload. | — |

---

## 9. Cross-reference to the mockup catalogue

Mapping the 14 templates from `04-client-emails.md:29-42` against legacy
ResSystem coverage. "Legacy template key" refers to entries in
`EmailTemplate` (`Enums.cs:341-355`) where one exists.

| # | Mockup template | Legacy template key / mechanism | Coverage |
|---|---|---|---|
| 0 | **Proceed to Booking** | `INITIAL_PAYMENT_TEMPLATE` (sent from `ModifyBooking` `:3371` when `isSent=true`) | **UI-triggered side-effect** (Booking.razor save). No legacy mockup-equivalent "Proceed to Booking" — legacy conflates this with the deposit-payment-link email. |
| 1 | **Booking Confirmation** (deposit paid, balance outstanding) | `BOOKING_RECEIPT` (sent from Flywire webhook `:4422` and from `SavePaymentStatus :3452`) | **Backend-only / webhook.** |
| 2 | **Booking Confirmation (Paid in Full)** | **Not in legacy.** `BOOKING_RECEIPT` is reused regardless of whether balance is paid; no separate paid-in-full template. | **Not in legacy** — new in mockup. |
| 3 | **Owner Approval Request** | Legacy has `OWNER_BOOKING_CONFIRM` template-key (`Enums.cs:344`) and a `villa-owner-booking-confirm.html` file, but all the **direct** `SentEmailAsync(OWNER_BOOKING_CONFIRM, …)` calls are commented out (`ResService.cs:3387, 3392, 3396`). The active path uses `SentEmailToOwner` which iterates per-contact templates from `sp_owner_template`. The owner-side "approve/decline" flow has no template that I can locate. | **Partially covered (legacy)** — legacy sends *a* notification to owners (`SentEmailToOwner`), but there are no Approve/Decline action URLs in the legacy template structure. |
| 4 | **Balance Payment Received** | **Not in legacy.** The webhook simply re-sends `BOOKING_RECEIPT` (`:4422`) when payment status flips to `guaranteed`. There is no separate "balance received" template. | **Not in legacy** — new (good idea per the mockup's red/green semantic split). |
| 5 | **Balance Reminder (7 Days)** | `BALANCE_PAYMENT` triggered by scheduler when `isEmailSentBeforeCD` (UTC date == checkoutDate - 7d) — `ResService.cs:137, 166`. | **Backend-only / scheduled.** Same template key is reused for the due-today case. |
| 6 | **Balance Reminder (3 Days)** | **Not in legacy.** Scheduler only has the 7-day and the day-of nudges (`:137-167`). | **Not in legacy** — new. |
| 7 | **Balance Due Today** | `BALANCE_PAYMENT` (same template key) triggered when `isCheckoutDate` (`:152-167`). | **Backend-only / scheduled** — but legacy reuses the 7-day template, so the urgency/danger styling in the mockup is new. |
| 8 | **Concierge Payment Request** | Filesystem template `concierge-payment-template.html` rendered by `RequestPaymentConcierge` (`:3717-3801`) | **UI-driven** — "Request Payment" button on `Booking.razor:439`. |
| 9 | **New Message from VC** | **Not in legacy.** No guest-messaging primitive exists; there is no `BookingMessage` / inbox entity. | **Not in legacy** — new. |
| 10 | **Service Request Update** | **Not in legacy.** No service-request state machine. | **Not in legacy** — new. |
| 11 | **Pre-Arrival Information** | **Not in legacy.** Implied by the `SECURITY_DEPOSIT_PAYMENT` cadence (~14d before) and by the Balance Receipt body text, but no template exists. | **Not in legacy** — new. |
| 12 | **Check-In Reminder (48h)** | **Not in legacy.** Scheduler has no T-2-day branch. | **Not in legacy** — new. |
| 13 | **Post-Stay Thank You** | **Not in legacy.** No post-checkout trigger anywhere. | **Not in legacy** — new. |

**Tally:** of the 14 mockup templates, **5** map directly to a legacy
template/trigger (mockup #0, #1, #5, #7, #8), **2** map to a
legacy-but-deprecated path (#3 owner-confirm), and **7** are net-new
(#2, #4, #6, #9, #10, #11, #12, #13 — that's 8 actually, depending on
how you score #3).

The legacy also has emails the mockup *does not* enumerate:

- **`VC_ENQUIRE_EMAIL`** (enquiry-to-VC internal notify) and
  **`VC_ENQUIRE_AUTO_REPLY`** (enquiry acknowledgement to guest) — see
  `04-client-emails.md:257` for the same omission flagged there.
- **`SECURITY_DEPOSIT_PAYMENT`** as a distinct template (the mockup
  folds SD into the body of #1 "Booking Confirmation").
- **`CC_CARD_UPDATE`** (card-on-file re-tokenisation request) — niche;
  mockup doesn't have it.
- **`UPGRADE_CONCIERGE_SERVICE_REQUEST`** (sent when a guest ticks the
  "I want concierge" box during checkout, distinct from #8 which is the
  *invoice* for a concierge service already agreed) — mockup doesn't
  have it.
- **`VC_USER_PASSWORD_RESET`** + **`EMAIL_AUTH_CODE_TEMPLATE`** —
  operator-account auth, not guest-facing; correctly omitted from the
  client-emails mockup but they exist as templates in the legacy.
- **Manual invoice request** (hard-coded HTML, sent to
  `tash.accounts@villacollective.com` from `SentInvoiceMailByBookingId`) —
  an internal-ops email with no template entry.

---

## 10. Findings & implications

### What the legacy staff UI actually let operators **do** around email

In practice, the only deliberate "I want to send an email" actions
available to a Villa Collective operator are:

1. **Resend a booking-summary receipt** (one button, per booking row, on
   the bookings list).
2. **Resend / send the CC-Booking-Confirmation** to a specific property
   contact (one button, per property-contact row, on Properties →
   Contacts).
3. **Request payment from a guest for a concierge service line** (one
   button, per concierge line, on Booking edit).

Everything else is a side-effect of saving a record or comes from a
non-Blazor surface (the WordPress-hosted guest checkout, the Flywire
webhook, or the external cron).

### What was hidden / opaque

- **Operators cannot see** what emails fired against a booking. There
  is no "communications" tab. `VillaBooking.IsEmailSent` is the only
  per-booking signal and it covers only the rental-balance reminder.
- **Operators cannot edit** any template through the UI. The DB
  `VCEmailTemplates` rows are SQL-only. The on-disk HTML is git-only.
- **Operators cannot preview** what will be sent. No render-with-data
  step exists.
- **Operators cannot test-send.** No "send to me first" button.
- **Operators cannot cancel** a queued email — there is no queue.
- **Operators cannot resend** anything except the booking summary
  (button #1 above). Even the "Resend Code" button on the login screen
  (`Login.cshtml:110`) is for the 2FA code, not for any client email.
- **Operators cannot retry** a failed send. Failures only surface as
  toast text on the live save action and as plaintext under
  `wwwroot/ResLogs/...`. There is no failed-email dashboard.
- **Operators cannot tell** that "Start Booking - No Send" suppresses
  client + owner emails beyond the button label itself. The two save
  buttons (`Start/Update booking` vs `Start Booking - No Send`) sit
  millimetres apart on the same page (`Booking.razor:462, :471`).
- **Operators cannot choose** who receives the CC confirmation other
  than by clicking the icon-check on a specific contact row.
- **The hard-coded `connectusinfowaydemo12@gmail.com` BCC**
  (`EmailService.cs:71`) leaks every non-quote email to an external dev
  Gmail address that no operator knows about. This includes guest
  bookings, payment links, password resets, etc.

### Where the new comms model would meaningfully improve operator UX

Cross-referencing the mockup and the legacy gaps, the redesign should:

1. **Introduce a real `EmailMessage` / `EmailLog` entity** (the
   `product-design/01-domain-model.md` already has `EmailLog` as a
   first-class entity, per `04-client-emails.md:19`). Replace the
   per-day plaintext ResLogs files with a queryable table.
2. **Render a per-booking "Communications" tab** showing every email
   sent against that booking, who it went to, status, opens (if
   tracked), and a resend button.
3. **Promote `VCEmailTemplates` to a Django model with a CRUD admin**
   (template list, edit, version history, preview-with-data). The
   legacy operator base manages templates via raw SQL today.
4. **Make the "send the deposit request email" step explicit** instead
   of bundling it inside `ModifyBooking`. The current "Start Booking -
   No Send" / "Start/Update booking" pair is a fragile mistake-prone
   binary choice.
5. **Build the messaging primitive** the mockup templates #9 (New
   Message from VC) and #10 (Service Request Update) imply — both
   require a `BookingMessage` / `ServiceRequest` model that does not
   exist in the legacy.
6. **Differentiate balance-reminder cadence** into three distinct
   template keys (`balance_reminder_7d`, `balance_reminder_3d`,
   `balance_due_today`) — the legacy reuses one key for two cadences.
7. **Remove the hard-coded `connectusinfowaydemo12@gmail.com` BCC.**
8. **Stop storing SMTP passwords in plaintext** (both
   `VillaConfigEmail.serverpassword` and `UserMaster.SmtpPassword`
   today).
9. **Decide whether per-agent "send-as" is a real feature**. The
   plumbing is in `UserMaster` and `EmailService.SentQuoteEmail` but
   the only callers (`SentQuotation`, `SentQuotationNew`) are no
   longer reachable from the active UI. Either re-wire it into the
   Quote workflow (per `workflows/08-quotation/transmission.md`) or
   remove it.
10. **Move the external HTTP-cron pattern**
    (`POST /api/WordPressApi/Payment/BookingEmailReminder?key=…` with
    a static GUID for auth) onto a proper scheduler (Celery /
    APScheduler / `django-q2`) and surface a job-status view in the
    admin.
