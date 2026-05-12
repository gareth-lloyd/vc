# Email Delivery

SMTP-based email sending. Three callers: the global config (from `VillaConfigEmail`), per-user SMTP (from `UserMaster` per-user fields — used for quotation sends so the email appears from the agent), and a "send to VC ourselves" variant for internal notifications.

## Send via global SMTP

**ID:** `INTEGRATIONS.EMAIL.SEND`
**Trigger:** Any email-emitting workflow (booking confirmations, payment reminders, etc.).
**Actor:** System.
**Legacy locus:** `EmailService.cs:30-125`.

### Inputs
`EmailConfig`:
- `To`: `List<string>` of recipients
- `CC`, `BCC`: optional lists (BCC is **auto-augmented** with hardcoded `connectusinfowaydemo12@gmail.com` `[SECURITY][PRIVACY]` — every outbound email is silently CC'd to this test account)
- `Subject`, `Body` (HTML)
- `Module` (string — used for logging)
- `Attachments`: `Dictionary<string,string>` (filename → file path)

### Process
1. Load global SMTP profile from `VillaConfigEmail` (via `ConfigService.SaveVillaConfigEmail()` — odd naming for a read).
2. Build `MailMessage`:
   - `From = serverusername` with display name `fromname`
   - `ReplyTo = fromaddress`
   - Add the hardcoded BCC.
3. For each attachment: open via `File.OpenRead()` and attach.
4. Configure `SmtpClient` with `serveraddress`, `serverport`, `EnableSsl=servertls`, `Credentials = NetworkCredential(serverusername, serverpassword)` (only if `serverauthentication`).
5. `smtpClient.SendMailAsync(mailMessage)`.
6. Log everything (addresses, body, status) via `Utilities.WriteResLogFile()`.

### Outputs / side effects
- **Email sent** to recipients + hardcoded BCC.
- **Log file** with full content (including bodies that may contain PII).

### Failure modes
- SMTP timeout — no retry.
- Bad SMTP password — logged plaintext.

### Open questions
- Remove the hardcoded BCC. This is a privacy leak.
- Stop writing email bodies to disk logs (PII). Use structured event logging without body content.
- Replace with Django's `django.core.mail` + a transactional provider (SendGrid, Postmark, AWS SES).

---

## Send via per-user SMTP (for quote emails)

**ID:** `INTEGRATIONS.EMAIL.SEND_AS_USER`
**Trigger:** `QUOTATION.TRANSMISSION.SEND_EMAIL`.
**Actor:** System (acting as the agent).
**Legacy locus:** `EmailService.cs:127-246` (`SentQuoteEmail`).

### Inputs
- `EmailConfig` (as above)
- `userId` — the staff member whose SMTP profile to use

### Process
Same as global send, but the SMTP profile is loaded from `UserMaster` for the given `userId`:
- `SmtpAddress`, `SmtpUserName`, `SmtpPassword` (plaintext at rest `[SECURITY]`)
- `Port`, `IsTlsRequired`, `IsAuthRequired`
- `FirstName`, `LastName` (used as display name)

The MailMessage's `From` therefore shows the agent's name/address.

### Open questions
- Per-user SMTP is unusual but valuable for trust ("the agent emailed me from her own address"). The redesign should preserve the capability but store the per-user credentials encrypted (or use OAuth / Gmail send-as).

---

## Send internal VC notification

**ID:** `INTEGRATIONS.EMAIL.SEND_TO_VC`
**Trigger:** Enquiry intake, booking attention required, etc.
**Actor:** System.
**Legacy locus:** `EmailService.cs:248-339` (`SentEmailToVC`).

### Inputs
- `EmailConfig` (subject, body, attachments)
- `fromAddress`, `fullName` — sender info (used only for logging — the actual From is the global SMTP profile)

### Process
Same as global send. The recipient is **the configured `fromaddress`** (i.e., VC sends to itself). TLS 1.3 is enabled with permissive cert validation `[SECURITY]`.

### Open questions
- "Permissive cert validation" is a vulnerability. Use system cert store in the redesign.

---

## Email template rendering

**ID:** `INTEGRATIONS.EMAIL.RENDER_TEMPLATE`
**Trigger:** Sub-workflow inside any send.
**Actor:** System.
**Legacy locus:** `EmailTemplates.cs:13-42` (`Render(path, data)`).

### Inputs
- `path` — disk path to HTML template
- `data` — `Dictionary<string,string>` of placeholders

### Process
1. Read HTML file.
2. Replace placeholders (`{:Token:}` or `[#TOKEN#]` patterns) from the dictionary.
3. Return filled HTML body.

### Email templates (constants in `EmailTemplate`)

| Template | Use |
|---|---|
| `INITIAL_PAYMENT_TEMPLATE` | Deposit/initial payment due |
| `BALANCE_PAYMENT` | Rental balance reminder |
| `SECURITY_DEPOSIT_PAYMENT` | Security deposit request |
| `CC_CARD_UPDATE` | Request guest to update saved CC |
| `BOOKING_RECEIPT` | Booking confirmation receipt |
| `OWNER_BOOKING_CONFIRM` | Owner notification of new booking |
| `CC_BOOKING_CONFIRM` / `CC_VO_BOOKING_CONFIRMATION` | Booking-confirm CC variants |
| `UPGRADE_CONCIERGE_SERVICE_REQUEST` | Concierge upsell trigger (sent to ops) |
| `VILLA_LOOKUP_CONTENT` | Property info embed |
| `VC_ENQUIRE_EMAIL` | Internal: new enquiry from website |
| `VC_ENQUIRE_AUTO_REPLY` | Guest auto-reply after website enquiry |
| `VC_USER_PASSWORD_RESET` | Password reset link |
| `EMAIL_AUTH_CODE_TEMPLATE` | 2FA code |
| `CONCIERGE_PAYMENT_TEMPLATE` | Concierge payment request |

### Open questions
- File-on-disk templates with token substitution should be replaced by Django templates with proper context objects.
- The two different placeholder syntaxes (`{:X:}` and `[#X#]`) indicate two ages of code. Standardise.
