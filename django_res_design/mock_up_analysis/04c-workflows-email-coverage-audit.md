# Workflows/ — Email Coverage Audit

> Source for the legacy inventory: `04a-ressystem-email-inventory.md`
> Audited against: every email-relevant file in `django_res_design/workflows/`
> Purpose: ensure nothing from the legacy email system has been lost in the
> workflow extraction.
> Audit performed: 2026-05-20.

---

## 1. Headline

- **~28** discrete legacy items (templates, trigger sites, SMTP plumbing, UI
  buttons, footnotes) were checked against `workflows/`.
- **~18** are covered (sometimes only partially / by reference).
- **~10** are missing or under-documented — most critically the legacy
  **"Resend CC Booking Confirmation" per-property-contact button** (button
  #2 in 04a §4), the **`sp_owner_template` fan-out**, the
  **`SP_SAVE_VC_EMAIL_TEMPLATE` snapshot row written from `ModifyBooking`**,
  the **Manual Invoice email**, the **`VillaEmailLinkLog` table**, and the
  fact that `BOOKING_RECEIPT` is double-sent (Flywire webhook **and**
  `SavePaymentStatus`).
- **2** subtle contradictions: `03-catalog/property-features.md` cites the
  *dead* `PropertyService.cs` SentBookingConfirmEmail path, not the active
  `ResService.cs:3621-3660` one used by `PropertyContacts.razor`; and
  `12-automation/scheduler-jobs.md` says `CC_CARD_UPDATE` is sent "Else"
  rather than as the CC-card branch of the rental-balance reminder
  (minor — but should be reviewed).
- **Several footnote behaviours** are missing: the "Start Booking - No Send"
  silent suppression is mentioned in passing only; `VillaBooking.IsEmailSent`
  is documented in two places but not framed as the *only* per-booking comm
  signal; the dead `OWNER_BOOKING_CONFIRM` direct sends and dead
  `SentQuotation` / per-user SMTP wiring need to be flagged louder.

---

## 2. Coverage matrix

| # | Legacy item (04a) | 04a ref | Workflow file:line | Status |
|---|---|---|---|---|
| 1 | `EmailService.SentEmail` global-SMTP path | §2.1 | `11-integrations/email-delivery.md:5-42` | Covered |
| 2 | `VillaConfigEmail` single-row config table | §2.1 | `02-administration/system-configuration.md:55-83`; `11-integrations/email-delivery.md:21` | Covered |
| 3 | Admin → Configuration → "Email" tab UI | §2.1 / §8 | `02-administration/system-configuration.md:55-83` | Covered |
| 4 | `SP_CRUD_VillaConfigEmail` SP | §2.1 | `02-administration/system-configuration.md:60`; `02-administration/README.md:28` | Covered |
| 5 | Per-user SMTP on `UserMaster` (SmtpAddress, SmtpUserName, SmtpPassword, Port, IsTlsRequired, IsAuthRequired) | §2.2 | `01-identity/user-administration.md:26-28, 44, 53`; `11-integrations/email-delivery.md:46-66` | Covered |
| 6 | Admin → Users → "SMTP Details" card UI | §2.2 | `01-identity/user-administration.md:26-28, 38` | Covered |
| 7 | **Per-user SMTP is only consulted by `SentQuoteEmail` and the only callers (`SentQuotation`/`SentQuotationNew`) are dead** | §2.2 / §7 | `11-integrations/email-delivery.md:46-66` describes the path; `08-quotation/transmission.md:9, 28` *assumes* the path is live; **the dead-code fact is not surfaced** | **Partial / contradicts** |
| 8 | Hard-coded BCC `connectusinfowaydemo12@gmail.com` | §2.3 / §7 | `11-integrations/email-delivery.md:15, 25, 32, 40` | Covered (well) |
| 9 | "Permissive cert validation" inside `SentEmailToVC` (TLS 1.3, lax cert check) | §2 (SentEmailToVC) | `11-integrations/email-delivery.md:70-86` | Covered |
| 10 | No email-log table; per-day plaintext logs in `wwwroot/ResLogs/<ddMMyyyy>/...` via `Utilities.WriteResLogFile` | §2.4 / §8 | `11-integrations/email-delivery.md:29, 33, 41` (mentions log dump and PII concern, but **not** the `wwwroot/ResLogs/<ddMMyyyy>/` filename pattern) | Partial |
| 11 | `VillaBooking.IsEmailSent` boolean | §2.4 / §8 | `09-booking/README.md:19`; `12-automation/scheduler-jobs.md:46, 72`; `12-automation/README.md:14` | Covered (the framing that this is the **only** per-booking comm signal is missing) |
| 12 | `VillaEmailLinkLog` table (`sp_villaEmailLinkLog`) — the only audit-style table | §2.4 / §3 | `01-identity/password-management.md:21`; `01-identity/README.md:17, 25` | Covered |
| 13 | All sends are fire-and-forget `await SendMailAsync` (often inside `Task.Run`); no queue, no retry, no DLQ | §2.4 / §8 | `11-integrations/email-delivery.md:36-42` | Covered |
| 14 | `VCEmailTemplates` table + DB-stored templates (the active path) | §3.1 | `11-integrations/email-delivery.md:89-127` references it via `EmailTemplate` enum but **never names the `VCEmailTemplates` table** | Partial |
| 15 | `sp_get_email_template_data` read SP | §3.1 | `09-booking/booking-management.md:57, 65` (in passing); `09-booking/booking-creation.md:67` | Partial — never explicitly enumerated |
| 16 | `sp_owner_template` SP (owner fan-out, multi-contact) | §3.1 / §6 #5 | **NOT DOCUMENTED** — `09-booking/booking-creation.md:69` mentions `SentEmailToOwner` but does not name `sp_owner_template` or the fan-out semantics | **Missing** |
| 17 | `sp_save_vc_email_template` — snapshot of CC-booking-confirm to `VCEmailTemplates` per booking, written during `ModifyBooking` (so button #2 can later resolve it) | §3.1 / §5 #1 | `09-booking/booking-creation.md:69` mentions `SP_SAVE_VC_EMAIL_TEMPLATE` writing `Type=CC_VO_BOOKING_CONFIRMATION` but **does not explain that this is the snapshot that powers the per-property-contact CC button** | Partial |
| 18 | Filesystem templates dir `wwwroot/templates/email/*.html` | §3.2 | `11-integrations/email-delivery.md:94-104, 125` (renderer mechanics covered; the directory and the specific filenames are not listed) | Partial |
| 19 | `EMAIL_AUTH_CODE_TEMPLATE` filesystem template (`User-AuthCode.html`) | §3.2 / §5 #4, #5 | `01-identity/authentication.md:55-58`; `11-integrations/email-delivery.md:121` | Covered |
| 20 | `User-PasswordReset.html` filesystem template is **dead**; active path is `VC_USER_PASSWORD_RESET` DB template | §3.2 / §7 | `01-identity/password-management.md:18` — mentions the DB template, doesn't flag the on-disk template as dead | Partial |
| 21 | `enquire_auto_replay_email` filesystem template, used by `PropertyService.cs:1481-1500` (`SentBookingConfirmEmail` — the *dead* path) | §7 | `03-catalog/property-features.md:41-67` — **points at the dead path** and treats it as the active behaviour | **Contradicts** legacy: active CC-confirm path is `ResService.cs:3621-3660`, which pulls from `VCEmailTemplates` rows of `Type=CC_VO_BOOKING_CONFIRMATION` |
| 22 | `EmailTemplates.Render(path, dict)` `[#TOKEN#]` and `{:TOKEN:}` placeholder syntaxes | §3.3 / §3.4 | `11-integrations/email-delivery.md:94-104, 127` | Covered |
| 23 | Two ages of placeholder syntax in the codebase | §3.4 | `11-integrations/email-delivery.md:127` | Covered |
| 24 | Hard-coded `tash.accounts@villacollective.com` + `info@villacollective.com` in `SentInvoiceMailByBookingId` ("Request Manual Invoice", subject literal `"Request manual invoice from {fullName}"`) — built with a raw StringBuilder of literal HTML | §3.3 / §9 | **NOT DOCUMENTED** — no workflow file mentions Manual Invoice, the hard-coded address, or the trigger from `SaveBookingFinanceConfig` | **Missing** |
| 25 | Hard-coded "Concierge Payment Request" `baseUrl = "https://vc2.mojodev.co.uk"` (`ResService.cs:3722`) pointing at dev regardless of env | §4 button #3 | `09-booking/concierge.md:41-74` documents the button and template but **does not flag the hard-coded dev URL** | Partial |
| 26 | Resend Booking Summary button (button #1) on `BookingInfo.razor:155` | §4 button #1 | `09-booking/booking-management.md:52-74` (well covered, including PDF + T&Cs attachment) | Covered |
| 27 | CC Booking Confirmation icon-check button on `PropertyContacts.razor:59` (button #2) — resolves rows in `VCEmailTemplates` snapshotted at booking time, sends subject literal `"CC Booking Confirmation"`, hardcoded subject | §4 button #2 | `05-directory/contact-property-assignment.md:67-86` documents the click flow but **redirects to `03-catalog/property-features.md` which describes the dead path**; the `VCEmailTemplates`-resolved nature of the send is not captured | **Partial / contradicts** |
| 28 | Request Payment button per concierge service line (button #3) | §4 button #3 | `09-booking/concierge.md:41-74` | Covered |
| 29 | UI side-effect: Save Booking → `INITIAL_PAYMENT_TEMPLATE` + owner fan-out + `CC_VO_BOOKING_CONFIRMATION` snapshot | §5 #1 | `09-booking/booking-creation.md:67-69` (snapshot mentioned but link to button #2 is implicit) | Partial |
| 30 | UI side-effect: **"Start Booking - No Send"** silently suppresses **all** booking-save emails by passing `ownerDetails=null` (button at `Booking.razor:471`) | §5 #2 / §7 | `09-booking/booking-creation.md:8` (button listed); `:42`, `:69`, `:79` all hint; `09-booking/booking-modification.md:32` mentions it. **The silent-suppression-of-the-client-INITIAL_PAYMENT-email behaviour is not called out** — the wording suggests it only stops the owner email | **Partial / under-documented** |
| 31 | UI side-effect: Save Checkout (`isConciergeService==true`) → `UPGRADE_CONCIERGE_SERVICE_REQUEST` | §5 #3 | `10-payment/checkout-flow.md:30, 34` | Covered |
| 32 | UI side-effect: Save User with empty password → `User-AuthCode.html` via `SentAuthCode` (`UserService.cs:208`) | §5 #4 | `01-identity/user-administration.md:49` — explicitly says **"No email"** to the newly-created user, which conflicts with 04a (auth-code fires) | **Contradicts** |
| 33 | UI side-effect: Forgot-password link on login page → `VC_USER_PASSWORD_RESET` DB template + `VillaEmailLinkLog` insert | §5 #6 | `01-identity/password-management.md:5-37` | Covered |
| 34 | UI: Resend 2FA code on login screen (`Login.cshtml:110`) | §5 #5 / §8 | `01-identity/authentication.md:44-58` | Covered |
| 35 | Backend trigger #1: external cron `GET /api/WordPressApi/Payment/BookingEmailReminder?key={hardcoded GUID}` calling `PaymentReminderSchedulerJob` | §6 #1 / §7 | `12-automation/scheduler-jobs.md:8-93` | Covered |
| 36 | `INITIAL_PAYMENT_TEMPLATE` sent by scheduler on checkout-date for "Initial Payment Due Immediately" | §6 #1 / §9 #0 | `12-automation/scheduler-jobs.md:34` | Covered |
| 37 | `BALANCE_PAYMENT` sent by scheduler on checkout-date (rental balance) | §6 #1 / §9 #5 / §9 #7 | `12-automation/scheduler-jobs.md:35-37` | Covered |
| 38 | `CC_CARD_UPDATE` sent by scheduler when balance-rental is due AND `paymentMethod` is CC | §6 #1 | `12-automation/scheduler-jobs.md:36` | Covered |
| 39 | `SECURITY_DEPOSIT_PAYMENT` sent by scheduler on stay-date OR 7 days before checkout | §6 #1 | `12-automation/scheduler-jobs.md:38` | Covered |
| 40 | Hard-coded API key `130d0022-8fe4-4878-8ec2-c44c939bb336` gating the scheduler endpoint | §6 #1 | `02-administration/system-configuration.md:25` | Covered (cross-referenced) |
| 41 | Scheduler-job class `SchedullerJob.cs` BackgroundService entirely commented out — never `AddHostedService`-d | §7 | `12-automation/scheduler-jobs.md:8`; `12-automation/README.md:3` | Covered |
| 42 | Backend trigger #2: Flywire webhook on `status=="guaranteed"` → `BOOKING_RECEIPT` to **both** payer and lead guest, with PDF + T&Cs PDF attached | §6 #2 / §9 #1 | `10-payment/payment-collection.md:74, 81` (mentions the email; does **not** spell out: receipt-to-payer **and** lead-guest, PDF attachment, T&Cs PDF attachment from `wwwroot/templates/email/`) | Partial |
| 43 | Backend trigger #3: Website enquiry POST → `VC_ENQUIRE_EMAIL` (to VC) + `VC_ENQUIRE_AUTO_REPLY` (to guest), **only when `User==WEBSITE`** | §6 #3 | `07-enquiry/enquiry-intake.md:32-37, 106-111`; `07-enquiry/README.md:29` | Covered |
| 44 | **Backend trigger #4: `SavePaymentStatus` also calls `SentEmailToPayerAndLeadGuest` — a second `BOOKING_RECEIPT` send path, overlapping with the Flywire webhook** | §6 #4 | **NOT DOCUMENTED** — `10-payment/payment-collection.md` and `10-payment/checkout-flow.md` do not call out the duplicate-send risk | **Missing** |
| 45 | Backend trigger #5: `SentEmailToOwner(bookingRefNo)` uses `sp_owner_template` to fan out to multiple owner-side contacts; recipients are decided by the SP, not the operator | §6 #5 | `09-booking/booking-creation.md:69` names `SentEmailToOwner` but **does not** explain the fan-out semantics or the SP body | Partial |
| 46 | `OWNER_BOOKING_CONFIRM` template key + `villa-owner-booking-confirm.html` filesystem file — **but the direct `SentEmailAsync(OWNER_BOOKING_CONFIRM, …)` sites are commented out** at three places in `ResService.cs:3387, 3392, 3396` | §7 | `11-integrations/email-delivery.md:114` lists the template; the dead-code status is **not** mentioned | Partial |
| 47 | `PropertyService.cs:1494` `_service.SentEmail(emailConfig)` is a commented-out send | §7 | **NOT DOCUMENTED** | Missing (minor) |
| 48 | No template editor UI in legacy | §8 | `11-integrations/email-delivery.md:125` (open question to build one) | Covered |
| 49 | No email log / sent-history UI in legacy | §8 | `11-integrations/email-delivery.md:41` (open question) | Covered |
| 50 | No bulk / marketing / free-text composer / preview / test-send | §8 | `11-integrations/email-delivery.md` open questions section | Covered (by absence) |
| 51 | No per-booking communications tab | §8 | Not explicitly stated anywhere in `workflows/` | Missing (but trivially absent from legacy) |
| 52 | `BOOKING_RECEIPT` is reused regardless of paid-in-full vs deposit (no separate paid-in-full template) | §9 #2 | **NOT DOCUMENTED** in `workflows/` | Missing |
| 53 | `BALANCE_PAYMENT` template is reused for 7-day-warning **and** day-of (no distinct 3-day / due-today templates) | §9 #5/#6/#7 | `12-automation/scheduler-jobs.md:35` lists both triggers using the same template; the "reuse means same body + no urgency variation" implication is not stated | Partial |
| 54 | `VC_ENQUIRE_AUTO_REPLY` filesystem path at `ResService.cs:2389-2459` is commented out in favour of the DB template | §7 | Covered indirectly by `07-enquiry/enquiry-intake.md:32-33` (active path is DB) | Partial |

---

## 3. Gaps — items in legacy but **not** represented (or under-represented) in `workflows/`

For each, the suggested home file.

1. **Manual Invoice email** (`SentInvoiceMailByBookingId`,
   `ResService.cs:3577-3599`).
   - Trigger: `SaveBookingFinanceConfig` (when a manual invoice is requested
     on the booking-finance modal).
   - Recipients: hard-coded `tash.accounts@villacollective.com` + CC
     `info@villacollective.com`.
   - Body: hand-built StringBuilder of literal HTML in C# (no template).
   - Subject: `"Request manual invoice from {fullName}"`.
   - Where it belongs: `09-booking/booking-creation.md` (or a new
     `09-booking/manual-invoice.md` sub-workflow) and cross-listed in
     `11-integrations/email-delivery.md` as a hard-coded send-site.

2. **`sp_owner_template` fan-out semantics**.
   - 04a §6 #5 makes clear `SentEmailToOwner` calls `sp_owner_template` which
     iterates multiple owner-side contacts (the operator doesn't choose
     them).
   - `workflows/` mentions `SentEmailToOwner` but never explains the
     fan-out or the SP body. Where it belongs:
     `09-booking/booking-creation.md` (in step 8) and a new section in
     `11-integrations/email-delivery.md` documenting the
     "owner template multi-row resolve" mechanism.

3. **`SP_SAVE_VC_EMAIL_TEMPLATE` snapshot write + link to the CC button**.
   - 04a §3.1 explains the snapshot row is what later powers the
     `PropertyContacts.razor:59` icon-check button.
   - `09-booking/booking-creation.md:69` mentions the SP write but does
     not link to the downstream button. Where it belongs:
     `05-directory/contact-property-assignment.md` (`MARK_CC` workflow)
     should explicitly reference the snapshot as its source of truth.

4. **`VCEmailTemplates` is the active 2025 template store, named explicitly**.
   - Currently `11-integrations/email-delivery.md` only refers to
     "DB-stored templates" via the `EmailTemplate` enum. The table name
     `VCEmailTemplates`, columns (`SourceId`, `DestinationId`, `Type`),
     and the read SP `sp_get_email_template_data` should be made
     first-class in the email-delivery doc.

5. **"Start Booking - No Send" silently suppresses the client
   `INITIAL_PAYMENT_TEMPLATE` email, not just the owner email**.
   - 04a §5 #2 is explicit: passing `ownerDetails=null` skips the entire
     email block at `ResService.cs:3363-3410` — including the client
     deposit-request email.
   - `workflows/` currently implies only the owner email is suppressed.
     `booking-creation.md:69, 79` should be updated to make the
     client-email suppression explicit.

6. **`SavePaymentStatus` second `BOOKING_RECEIPT` send-site** (04a §6 #4).
   - The Flywire webhook and the `SavePaymentStatus` WP endpoint both call
     `SentEmailToPayerAndLeadGuest`, so a guest can be receipted twice on
     overlapping paths. `10-payment/payment-collection.md` should document
     this overlap explicitly and call out the "belt-and-braces / refactor
     leftover" risk.

7. **`BOOKING_RECEIPT` PDF attachment + bundled
   `VillaCollectiveBookingTermsConditions.pdf` from
   `wwwroot/templates/email/`**.
   - Documented in 04a §4 #1 and §6 #2/#4. `booking-management.md`
     mentions sending the receipt but does not mention the PDF generation
     (`Utilities.Createpdf`) or the T&Cs attachment.

8. **`wwwroot/ResLogs/<ddMMyyyy>/...` per-day plaintext email log files**
   (04a §2.4 / §8).
   - `email-delivery.md:29` says "Log file with full content" but does not
     name the path pattern. The Django redesign needs to know this is the
     legacy "audit trail" so the migration can choose to import or
     discard.

9. **`PropertyService.cs:1494` commented-out `SentEmail` site** (04a §7)
   — a small dead-code marker.

10. **`OWNER_BOOKING_CONFIRM` direct-send sites commented out at three
    locations** (`ResService.cs:3387, 3392, 3396`) (04a §7).
    - Should be noted in `09-booking/booking-creation.md` as a footnote
      explaining why the active owner email goes through
      `SentEmailToOwner` + `sp_owner_template` rather than the template
      key.

11. **`SentQuotation` / `SentQuotationNew` are dead code in the active
    Blazor UI** (04a §2.2 / §7).
    - `08-quotation/transmission.md` describes them as if live; the
      doc should add a `[DEAD-CODE]` / `[DISABLED]` tag and note that
      the active quote-send goes through the booking-save path's
      `INITIAL_PAYMENT_TEMPLATE` instead.

12. **No separate paid-in-full booking-confirmation template; no
    distinct 3-day-warning template; no separate "balance received" vs
    "deposit received" templates** (04a §9 #2/#4/#6).
    - These absences should be recorded in `12-automation/scheduler-jobs.md`
      and `10-payment/payment-collection.md` as design constraints in
      the legacy so the Django redesign documents the deliberate
      expansion.

13. **`VillaEmailLinkLog` is the *only* general-purpose email-audit row in
    the system** (04a §2.4).
    - It is documented in `01-identity/README.md:17, 25` but only as a
      password-reset thing. `11-integrations/email-delivery.md` should
      reference it as "the closest thing the legacy has to an
      `EmailLog`".

14. **`VillaBooking.IsEmailSent` is the *only* per-booking comm signal**
    (04a §2.4, §8).
    - Mentioned in `09-booking/README.md:19` and
      `12-automation/scheduler-jobs.md` as a field, but never framed as
      "the only signal you have that comms went out for this booking".

15. **Cleartext SMTP password in `VillaConfigEmail.serverpassword` is
    committed in the SQL dump at `Database/Scripts/live-db-24-apr.sql:61382`**
    (04a §2.1).
    - The plaintext-at-rest concern is flagged in
      `02-administration/system-configuration.md:82` and
      `11-integrations/email-delivery.md`, but the "committed in the SQL
      dump" sub-point is missing. Worth noting because the dump itself
      is a credential-leak vector.

---

## 4. Contradictions — `workflows/` disagrees with the legacy

1. **`03-catalog/property-features.md:41-67` (`SEND_CONFIRM_EMAIL`) points
   at `PropertyService.cs:1481-1500` (`SentBookingConfirmEmail`)** —
   but **that method is the *dead* path**. The legacy CC-confirm icon
   button on `PropertyContacts.razor:59` actually calls
   `ResService.cs:3621-3660`, which:
   - resolves `VCEmailTemplates` rows where `SourceId=VillaId AND
     Type=CC_VO_BOOKING_CONFIRMATION`;
   - iterates those rows;
   - sends each with subject literal `"CC Booking Confirmation"` (not
     `"Thank You for Your Enquiry – We'll Get Back to You Soon"` as the
     workflow doc says).
   - The "auto reply" template name `enquire_auto_replay_email` quoted in
     the workflow doc is the *module string* of the dead path; the active
     path's body comes out of the DB snapshot, not a filesystem file.
   - Both `03-catalog/property-features.md:41-67` and
     `05-directory/contact-property-assignment.md:67-86` need to be
     re-pointed at the active code path.

2. **`01-identity/user-administration.md:49` says "No email to the
   newly-created user"** but 04a §5 #4 says saving a new user (with the
   2FA flag set) **does** fire `SentAuthCode` → `User-AuthCode.html`.
   The "no email" line is true only for the "create user without 2FA and
   without empty-password" path; it needs the 2FA caveat to match
   legacy.

3. **`08-quotation/transmission.md:9, 28` describes the quote-send as
   "Staff … sends from their own SMTP profile"** — but per 04a §2.2 /
   §7 this path is not wired to any active Blazor screen and the quote
   sends in the current build go through the booking-save
   `INITIAL_PAYMENT_TEMPLATE`. The workflow doc presents dead-code
   behaviour as if it were the active path.

4. **`12-automation/scheduler-jobs.md:36-37`**: the description of the
   CC-card-update branch reads as if `CC_CARD_UPDATE` is a fallback "Else"
   inside the rental-balance trigger. The 04a §6 #1 / `ResService.cs:206`
   structure is the other way around: `CC_CARD_UPDATE` is the *primary*
   branch when the saved payment method is CC, and `BALANCE_PAYMENT` is
   the bank-transfer / no-card-on-file branch. The workflow doc reads
   correctly enough on a careful read, but the "Else" wording is
   ambiguous.

5. **`09-booking/booking-confirmation.md:31`** uses `Module =
   "Enquiry_Email"` for the owner-confirm-rejection email. That matches
   the legacy `ResService.cs:4583` literal — but the workflow file does
   not warn that the "Module" string is the legacy's only structured
   classifier of email kind (it is the key used to grep ResLogs files
   after the fact). Worth a footnote.

---

## 5. Hidden / footnote behaviours legacy has that `workflows/` should record

These are items 04a explicitly calls out as "easy to miss" that
`workflows/` does not surface clearly.

1. **Hard-coded BCC `connectusinfowaydemo12@gmail.com`**
   (`EmailService.cs:71`) — every non-quote email is silently CC'd to a
   dev-vendor Gmail.
   *Coverage:* well documented in `11-integrations/email-delivery.md:15`
   — **OK**.

2. **Cleartext SMTP passwords** in both `VillaConfigEmail.serverpassword`
   and `UserMaster.SmtpPassword`, plus the system password being
   committed in the SQL dump.
   *Coverage:* flagged in `02-administration/system-configuration.md:82`
   and `01-identity/user-administration.md:53`, but the
   committed-SQL-dump observation is missing.

3. **`OWNER_BOOKING_CONFIRM` is a template key whose *direct* sends are
   all commented out at `ResService.cs:3387, 3392, 3396`**, and the
   active owner-notify path is the `sp_owner_template` fan-out.
   *Coverage:* `11-integrations/email-delivery.md:114` lists the template
   without noting it is dead — **missing**.

4. **"Start Booking - No Send" silently suppresses the client deposit
   email**, not just the owner email (button at `Booking.razor:471`).
   *Coverage:* alluded to in `09-booking/booking-creation.md:42, 79` and
   `09-booking/booking-modification.md:32`, but the silent-client-
   suppression is **under-documented**.

5. **`VillaBooking.IsEmailSent` is a single bool set only by the
   rental-balance reminder** — meaning it cannot be trusted as a
   generic "any email sent for this booking" indicator.
   *Coverage:* documented as a field (`09-booking/README.md:19`,
   `12-automation/README.md:14`) but **its narrowness is not flagged**.

6. **`SP_SAVE_VC_EMAIL_TEMPLATE` snapshot write inside `ModifyBooking`**
   is what later powers the CC-confirm icon-check button. The link is
   not made in `workflows/`.
   *Coverage:* `09-booking/booking-creation.md:69` notes the SP write;
   `05-directory/contact-property-assignment.md:76` documents the
   button — **the two are not connected**.

7. **`sp_owner_template` multi-recipient fan-out** — the operator does
   not see / cannot choose the recipients; the SP body decides.
   *Coverage:* **missing**.

8. **`SentQuotation` / `SentQuotationNew` and the per-user-SMTP
   `SentQuoteEmail` are dead in the active UI**; the per-user SMTP
   fields on `Users.razor` are configurable but never consulted by
   anything wired-in.
   *Coverage:* `08-quotation/transmission.md` treats the path as live —
   **contradicts legacy**.

9. **`SavePaymentStatus` is a second `BOOKING_RECEIPT` send-site,
   overlapping with the Flywire webhook**. Bookings can receive the
   receipt email twice.
   *Coverage:* **missing**.

10. **`BOOKING_RECEIPT` send-sites attach two PDFs**: a freshly-rendered
    HTML→PDF receipt (`Utilities.Createpdf`) and a static
    `VillaCollectiveBookingTermsConditions.pdf` file from
    `wwwroot/templates/email/`.
    *Coverage:* the PDF generation is mentioned **nowhere** in
    `workflows/`.

11. **Hard-coded `baseUrl = "https://vc2.mojodev.co.uk"`** in
    `RequestPaymentConcierge` (`ResService.cs:3722`) — concierge payment
    links always point at dev.
    *Coverage:* **missing**.

12. **Manual Invoice email** with hard-coded `tash.accounts@…` and
    StringBuilder body.
    *Coverage:* **missing**.

13. **Per-day plaintext email logs in `wwwroot/ResLogs/<ddMMyyyy>/…`** are
    the legacy's only audit trail for non-link emails.
    *Coverage:* the *log-to-file* fact is in
    `11-integrations/email-delivery.md:29, 33, 41` but the **path pattern
    is not named**.

14. **`Module` string on `EmailConfig` is the de-facto email-kind
    classifier in legacy logs** (e.g., `"PAYMENT_URL_EMAIL"`,
    `"Sent_Email_Quotation"`, `"Enquiry_Email"`,
    `"enquire_auto_replay_email"`). It is the only way to grep ResLogs
    files for a particular send-type.
    *Coverage:* the field is described in
    `11-integrations/email-delivery.md:17` but the "this is the only
    classifier we have" framing is missing.

15. **`EmailService.SentEmail` uses `From = serverusername` (the SMTP
    *auth* username) and `ReplyTo = fromaddress`**, not what you would
    naively expect (`From = fromaddress`). This affects deliverability
    (DMARC/SPF) — the From and the authenticated mailbox can drift.
    *Coverage:* documented in `11-integrations/email-delivery.md:23` —
    **OK**.

16. **HMAC `Digest()` is defined on the Flywire webhook but never
    invoked** (04a §2 / §6 #2). Already flagged as `[SECURITY]` in
    `10-payment/payment-collection.md:66` — **OK**.

---

## 6. Quick to-do list for `workflows/` to absorb this audit

Suggested concrete changes, in priority order:

1. **Rewrite `03-catalog/property-features.md:41-67`
   (`SEND_CONFIRM_EMAIL`)** to point at the active
   `ResService.cs:3621-3660` path and the `VCEmailTemplates` snapshot.
   Also fix `05-directory/contact-property-assignment.md:67-86` to
   match. (Item 4.1, 2.27.)
2. **Add a Manual Invoice sub-workflow** under `09-booking/` describing
   `SentInvoiceMailByBookingId`. (Item 3.1.)
3. **Add `sp_owner_template` fan-out section** to
   `11-integrations/email-delivery.md` and reference it from
   `09-booking/booking-creation.md:69`. (Items 3.2, 5.7.)
4. **Tag dead code louder** in `08-quotation/transmission.md` (per-user
   SMTP / SentQuotation are dead) and in
   `11-integrations/email-delivery.md` (`OWNER_BOOKING_CONFIRM` direct
   sends, filesystem `enquiry-auto-reply.html`, `User-PasswordReset.html`,
   `PropertyService.cs:1494`). (Items 3.10–3.11, 4.3, 5.3, 5.8.)
5. **Document the duplicate `BOOKING_RECEIPT` send-sites** (Flywire
   webhook + `SavePaymentStatus`) in `10-payment/payment-collection.md`,
   including the PDF attachment and T&Cs PDF. (Items 3.6–3.7.)
6. **Update `09-booking/booking-creation.md`** to make the "Start Booking
   - No Send" silent suppression of the client deposit email explicit.
   (Items 3.5, 5.4.)
7. **Fix `01-identity/user-administration.md:49`** to describe the 2FA
   auth-code email that fires on new user save. (Item 4.2.)
8. **Cross-link `09-booking/booking-creation.md:69`
   (`SP_SAVE_VC_EMAIL_TEMPLATE` snapshot) to
   `05-directory/contact-property-assignment.md:67`** so the
   write-now-read-later contract is visible from both sides. (Items
   3.3, 5.6.)
9. **Add a paragraph** in `11-integrations/email-delivery.md` naming the
   `wwwroot/ResLogs/<ddMMyyyy>/` legacy log pattern, the `Module`
   classifier convention, and `VillaEmailLinkLog` as the only audit
   row table. (Items 3.8, 3.13, 5.13, 5.14.)
10. **Add a footnote** in `09-booking/concierge.md` flagging the
    hard-coded `https://vc2.mojodev.co.uk` baseUrl. (Items 3.10, 5.11.)
11. **Add a one-liner** in `12-automation/scheduler-jobs.md` noting that
    the `BALANCE_PAYMENT` template is reused for both the 7-day warning
    and the day-of nudge (no urgency variation), and that there is no
    3-day-warning or paid-in-full variant in legacy. (Item 3.12.)
12. **In `09-booking/README.md` / `12-automation/README.md`**, reframe
    `VillaBooking.IsEmailSent` as "the only per-booking comm signal, set
    only by the balance reminder". (Items 3.14, 5.5.)
