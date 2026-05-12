# Villa Collective ResSystem — Code & Security Review

**Date:** 2026-05-11
**Reviewer:** Gareth Lloyd
**Repository:** `github.com/ConnectUsSoftware/ResSystem` (private)
**Live host reviewed:** `https://vc2.mojodev.co.uk`
**Owner referral:** owner of villacollective.com

---

## Executive summary

ResSystem is the .NET 7 Blazor Server back-office that powers the booking, payment and property-management workflow behind villacollective.com (which itself is a WordPress site). It exposes a set of HTTP endpoints called by the WordPress front-end and an admin UI used by Villa Collective staff.

Two **critical, exploitable** security flaws were confirmed against the live system in under five minutes of read-only probing:

1. **`/api/Auth/login` discloses any staff user's full record — including `PasswordHash`, `PasswordSalt`, role flags, and the schema slot for `SmtpPassword` — to an unauthenticated caller.** Confirmed against a real admin account.
2. **`/api/WordPressApi/Payment/*` endpoints accept anonymous POSTs that mutate booking and payment state.** The middleware that was supposed to authenticate them is commented out in source.

In addition there is a hard-coded API key checked into the public-ish source tree (and into a PowerShell script that also disables TLS certificate validation host-wide), an unverified webhook signing helper, and several smaller issues.

The codebase shows no tests, no CI, no code review, no pull requests, and a single offshore developer pushing directly to `main`. It runs on .NET 7, which has been out of vendor support since May 2024.

The minimum patch set to take the two critical issues off the table is small (tens of lines of code) and should be done immediately. The structural problems (no tests, no CI, EOL framework, single-developer process) are a separate conversation about ongoing engagement.

---

## History

| | |
|---|---|
| **First commit** | 2024-09-10 |
| **Last commit** | 2026-05-08 (3 days before review) |
| **Total commits** | 552 |
| **Contributors** | **1** — `connectussoftware@gmail.com` exclusively |
| **Pull requests opened, ever** | 0 |
| **Branches** | `main` only |
| **CI / CD** | None. No `.github/`, no Dockerfile, no workflow files. |
| **Tests** | None. Zero files matching `*test*.cs` or `*spec*.cs`. |
| **README / docs** | None. |
| **Issue tracker / Linear / Jira** | Not visible in repo. Commit messages mostly read *"Updated at 14-Apr-26"* — no ticket references. |

### Activity in the last 6 months

22 commits across 18 active days. March 2026 had zero commits. Of the LoC churn, a substantial proportion is auto-generated (EF Core scaffolded entities, `style.css` reformats). The hand-written portion across six months is roughly 2.5–3.5k lines.

---

## Findings, categorised

### Security

> Severity scale below is **Critical / High / Medium / Low**. Items marked **CONFIRMED** were verified against the live host on 2026-05-11.

---

#### S1. Login endpoint leaks password hash, salt and full user record — **Critical — CONFIRMED**

**Source:** `NewResSystem/Controllers/AuthController.cs:33-72`

The login handler retrieves a user via `UserService.GetLoginDetails(email)`. The result populates `res.Status = true` and `res.Data = <full UsersViewModel from DB>`. If the password fails to validate, the code overwrites `res.Message` but **does not** clear `res.Data` or reset `res.Status`. The full user record is then returned to the anonymous caller.

**Live demonstration (against `vc2.mojodev.co.uk` on 2026-05-11):**

```bash
curl -sS -X POST https://vc2.mojodev.co.uk/api/Auth/login \
  -H 'Content-Type: application/json' \
  -d '{"Email":"<real_admin_email>"}'
```

Response (sensitive fields redacted in this document — the live response contains the real values):

```json
{
  "Status": true,
  "Message": "failed to login, please try again or contact support for further assistanc!",
  "Data": {
    "Id": 2,
    "Email": "<redacted>",
    "FirstName": "<redacted>",
    "LastName": "<redacted>",
    "UserName": "<redacted>",
    "PasswordSalt": "<REDACTED — real Argon2 salt returned>",
    "PasswordHash": "<REDACTED — real Argon2 hash returned>",
    "IsTwoFactoryAuth": false,
    "IsAdmin": true,
    "IsActive": true,
    "IsLock": false,
    "SmtpAddress": null, "SmtpUserName": null, "SmtpPassword": null,
    ...
  }
}
```

The probe was performed responsibly: an earlier probe with an invalid email confirmed that `Password` is stored as `null` (system uses hash+salt, not cleartext) **before** any real email was tested. The first real-email probe used the live admin account `nick@villacollective.com` and the returned hash and salt have been captured as evidence and should be considered exposed.

**What an attacker can do with this:**

1. **Offline cracking** — server rate limits, lockouts, 2FA, and monitoring are all bypassed. Cracking happens locally on GPUs. Argon2 (via `Konscious.Security.Cryptography.Argon2`) is strong, but cracking time depends on the chosen parameters; weak or default parameters drop time from years to a weekend. Real-world dictionary attacks routinely recover 20–40% of any corporate password set.
2. **Targeted cracking** — the same response leaks `IsAdmin` and `IsTwoFactoryAuth`. The attacker filters to admins without 2FA and concentrates compute there.
3. **Credential stuffing** — cracked passwords are sprayed against Microsoft 365 / Google Workspace / Zoho / Monday.com / banking. Real reuse rates sit at 40–70%.
4. **User enumeration at scale** — real email returns a populated record, non-existent email returns all-zero defaults. The full staff directory plus role flags is scrapeable in seconds.
5. **`SmtpPassword` field is in the response shape** — currently `null` on the tested account, but if it is populated for any user and is stored plaintext in the DB (the model has no `Encrypted*` type), this allows direct mailbox takeover and SPF/DKIM/DMARC-clean phishing **as** Villa Collective staff. This is the single highest-financial-loss vector for a luxury rental business (fraudulent wire-transfer instructions to clients).
6. **Booking-system takeover** — once any staff password is cracked, attacker logs into vc2.mojodev.co.uk and has full access to guest PII, bookings, rates, owner payouts and the Zoho integration.

**Containment / fix:**

- Patch `AuthController.Login` to return `Data: null` (and `Status: false`) on both the "user not found" and "wrong password" branches. ~3 lines.
- Defence in depth: add `[JsonIgnore]` to `PasswordHash`, `PasswordSalt`, `SmtpPassword`, `SmtpUserName` etc. on `UsersViewModel`, or move to a separate outbound DTO.
- Assume hashes are exposed. **Force-reset every staff password.** Notify staff and instruct them not to reuse the old password elsewhere.
- Rotate any per-user `SmtpPassword`/app-password entries.
- Pull the last 90 days of IIS access logs for `/api/Auth/login` and look for any source IP that hit it with varied bodies — those are scraping candidates.
- Add per-IP and per-account rate limiting and an account lockout policy that doesn't depend on the response leaking `IsLock`.
- Make the wrong-password branch in `AuthController.Login` set `res.Status = false` so the existing client behaviour is correct (current code can return `Status: true` with an error message, which is also a separate bug).

---

#### S2. WordPress-callback API accepts anonymous payment/booking mutations — **Critical — CONFIRMED**

**Source:** `NewResSystem/Program.cs:142` (middleware commented out) + `NewResSystem/Controllers/PaymentController.cs` (no `[Authorize]`, no per-action auth on most endpoints).

`Program.cs:142` contains:

```csharp
//app.UseWhen(context => context.Request.Path.StartsWithSegments("/api/WordPressApi"),
//    appBuilder => appBuilder.UseMiddleware<AuthMiddleware>());
```

The middleware that was supposed to authenticate the WordPress-callback path is commented out — and the `AuthMiddleware` class it references **does not exist anywhere in the repository**. A repo-wide search returns zero definitions; the commented line would not compile if uncommented. The controller class itself has no `[Authorize]` attribute and most actions have no per-action auth check. Affected endpoints, all anonymous, all POST:

- `/api/WordPressApi/Payment/PaymentStatus` — marks a booking paid.
- `/api/WordPressApi/Payment/PaymentStatusWebHook` — accepts a webhook payload and writes payment state.
- `/api/WordPressApi/Payment/TokenisePaymentStatus` — accepts tokenised payment data.
- `/api/WordPressApi/Payment/SaveCheckoutInfo` — saves guest checkout PII against a booking.
- `/api/WordPressApi/Payment/ConfirmBooking` — confirms or cancels a booking.

The single endpoint that *is* guarded — `BookingEmailReminder` — uses a hard-coded GUID key checked into source (see S3).

**Live demonstration (against `vc2.mojodev.co.uk` on 2026-05-11, non-mutating, using `BookingId: 0` so the controller's own input validation short-circuits before any DB write):**

```bash
curl -sS -i -X POST https://vc2.mojodev.co.uk/api/WordPressApi/Payment/ConfirmBooking \
  -H 'Content-Type: application/json' \
  -d '{"BookingId":0,"IsConfirm":false,"Reason":"SECURITY-DEMO-DO-NOT-PROCESS"}'
```

Response:

```
HTTP/2 200
content-type: application/json; charset=utf-8
...
{"Status":false,"Message":"Could not confirm booking please try again!.","Data":"Booking id must me greater then zero!"}
```

The 200 response with `"Booking id must me greater then zero!"` is direct output from `PaymentController.cs:213` — proving the request reached the controller anonymously. There is no `WWW-Authenticate` header, no 401, no 403. Replacing `BookingId: 0` with any real booking ID would have invoked `_service.ConfirmBooking(args)` and mutated production state.

**What an attacker can do:**

- Mark any booking as paid (`PaymentStatus`) — defrauding Villa Collective of room nights and triggering downstream confirmation emails / Zoho sync as if a real payment had occurred.
- Confirm or cancel any booking (`ConfirmBooking`) — operational chaos plus refund triggering.
- Overwrite checkout PII against a booking (`SaveCheckoutInfo`) — data integrity and GDPR implications.
- Forge webhook events (`PaymentStatusWebHook`). The controller does have an `HMACSHA256` helper named `Digest()` (line 275) — but it is **never called**. The webhook deserialises whatever body it receives.

Booking IDs are sequential integers (`VillaBooking` table) so they're trivial to enumerate or brute-force.

**Containment / fix:**

- Implement an `AuthMiddleware` class from scratch (the type referenced at `Program.cs:142` is not defined in the repo, so uncommenting alone won't compile) and have it validate a shared secret pulled from configuration (not from source). Then uncomment line 142.
- For `PaymentStatusWebHook`, require an `X-Signature` (or vendor-specific) header and verify it using the existing `Digest()` helper against the **raw** request body. Reject before deserialisation.
- Add IP allow-listing on top of authentication — these endpoints are only meant to be called by the WordPress host.
- For each mutating endpoint, also add an idempotency-key check to prevent replay.

---

#### S3. Hard-coded API key in source — **High**

**Source:** `NewResSystem/Controllers/PaymentController.cs:41` and `bypass_script.ps1` (committed).

```csharp
_apiKey = "130d0022-8fe4-4878-8ec2-c44c939bb336";
```

The same key is checked into `bypass_script.ps1` at the repo root. It guards the `BookingEmailReminder` endpoint, which when called executes `PaymentReminderSchedulerJob()` — sending real emails to real guests. Rotating the key requires a code change and redeploy. Anyone with read access to the repo (including any past contractor) has the key.

**Fix:** move to `appsettings.{env}.json` / environment variables / Plesk-managed secret. Rotate the current value. Remove `bypass_script.ps1` from the repo and from source history if practical.

---

#### S4. PowerShell helper disables TLS certificate validation globally — **High**

**Source:** `bypass_script.ps1` at repo root.

```powershell
[System.Net.ServicePointManager]::CertificatePolicy = New-Object TrustAllCertsPolicy
```

This installs a policy on the current PowerShell process that returns `true` for every certificate validation, then makes a `https://localhost:44361/...` call. The policy is process-scoped (not machine-wide), so it dies with the script — but for the lifetime of that process, every `.NET` HTTPS call in the same session, to any host, silently accepts invalid certificates. If this script is ever extended or re-used in a longer-lived session that also talks to external services, those calls become man-in-the-middleable. There is no legitimate reason to disable certificate validation, even briefly.

It also references a hard-coded server path `F:\Live Work\bypass_script.ps1`, which together with the IIS/Plesk fingerprint implies this is the actual production server's filesystem layout.

**Fix:** delete this script. Replace the reminder scheduler with a proper Windows Task Scheduler job (or, better, an in-process `IHostedService`/Hangfire job) calling an authenticated endpoint over HTTPS with a server certificate that validates correctly. There is no legitimate reason to disable TLS validation on a production host.

---

#### S5. Webhook HMAC verification is implemented but never called — **High**

**Source:** `NewResSystem/Controllers/PaymentController.cs:275-292` (`Digest` method) referenced from nowhere.

The author wrote a HMAC-SHA256 helper for webhook verification, then never wired it into `PaymentStatusWebHook`. The endpoint reads the raw body, deserialises with Newtonsoft, and trusts it. Combined with S2 (no authentication on the route) this means any internet caller can post fraudulent payment webhooks.

**Fix:** before deserialisation, read the raw body, fetch the shared secret from configuration, compute `Digest(secret, body)`, and compare in constant time against an `X-Signature` header. Reject mismatches with 401.

---

#### S6. Login response status bug — **Medium**

**Source:** `AuthController.cs:43-65`.

When the password validation fails, the code overwrites `res.Message` but leaves `res.Status = true`. The client therefore receives a response that says both *"success"* and *"incorrect username or password"*. Whichever field the front-end trusts determines the outcome. This is a correctness bug and should be fixed alongside S1.

**Fix:** set `res.Status = false` and `res.Data = null` on the wrong-password branch.

---

#### S7. Routable Razor page without `[Authorize]` — **Medium**

**Source:** `NewResSystem/Pages/Contacts/Contacts.razor`.

This page declares `@page "/contacts"` (it is routable) but has no `@attribute [Authorize]`. Of the 19 routable Razor pages in the app, 18 declare `[Authorize]`; `Contacts.razor` is the sole exception. The downstream services may still require auth, but the page is reachable and may leak template structure or trigger side effects.

**Fix:** add `@attribute [Authorize]` to `Contacts.razor`. Better: enforce auth via fallback policy in `Program.cs` (`builder.Services.AddAuthorization(opts => opts.FallbackPolicy = …)`).

---

#### S8. Detailed errors enabled on Blazor circuit — **Low**

**Source:** `Program.cs:36`.

```csharp
.AddCircuitOptions(option => { option.DetailedErrors = true; })
```

Stack traces are returned to clients. Useful for development, dangerous in production.

**Fix:** wire this to `builder.Environment.IsDevelopment()`.

---

#### S9. Server fingerprint headers leaked — **Low**

`x-powered-by: ASP.NET`, `x-powered-by-plesk: PleskWin`, `server: Microsoft-IIS/10.0` on every response. Useful to attackers for selecting exploit chains. Not directly exploitable.

**Fix:** suppress in IIS / `web.config` and via `builder.WebHost.UseKestrel(...)` options.

---

#### S10. HSTS max-age short — **Low**

`strict-transport-security: max-age=2592000` (30 days). Industry baseline is 1 year (`31536000`) with `includeSubDomains; preload`.

**Fix:** raise to 1 year, add `includeSubDomains`.

---

#### S11. Cookie configured well — *positive note*

`Program.cs:67-78` sets `SameSite=Strict`, `SecurePolicy=Always`, sliding expiry, `IsEssential=true`. Cookie name is `NewResCookie`. This is one of the few areas that follows best practice.

---

### Dev practice

---

#### D1. Single contributor pushing straight to `main` — **High**

552 commits, all from `connectussoftware@gmail.com`. No PRs ever opened. No branches besides `main`. No second pair of eyes on any change in 20 months. The security issues above are direct consequences — middleware that was commented out for testing has been on `main` for an unknown period, and nobody else has looked at the auth controller.

**Fix:** establish a two-person review process. Even an asynchronous "vendor opens a PR, agency approves" cycle would catch issues like commented-out middleware and leaked hashes.

---

#### D2. No tests of any kind — **High**

Zero files matching `*test*.cs` or `*spec*.cs`. No test project in the solution. The system handles money and personally-identifiable booking data.

**Fix:** start with controller-level tests for the WordPress-callback endpoints (these are the highest-risk surface) and for `AuthController.Login`. xUnit + `WebApplicationFactory<>` is the standard ASP.NET Core pattern.

---

#### D3. No CI / CD — **High**

No `.github/workflows/`, no build pipeline, no static analysis, no security scanner. Every release is presumably a manual RDP-and-copy operation onto the IIS host. Combined with no tests and no review, regressions can ship without anyone noticing.

**Fix:** GitHub Actions workflow doing `dotnet restore && dotnet build && dotnet test`. Add `dotnet format` to enforce style. Add a security scanner (`dotnet list package --vulnerable`, `dotnet list package --outdated`) on every PR. Deploy via Web Deploy or Plesk's own automation.

---

#### D4. Empty `catch` blocks in payment flow — **High**

`PaymentController.cs:89-92` and `:168-171` both catch `Exception` and do nothing. Failures during payment processing are invisible: the client gets a 200 with whatever `res` happens to contain, and there is no log entry, no alert.

**Fix:** at minimum, `_logs.Save(ex)`. Better, return a non-200 status code on internal error.

---

#### D5. Forced-success after service call — **Medium**

`PaymentController.cs:85`:

```csharp
res = await _service.AddPaymentDetails(data);
res.Status = true;
```

The code discards whatever success/failure the service returned and unconditionally reports success.

**Fix:** trust the service's return value; only override on a specific known-good condition.

---

#### D6. Commit message hygiene — **Medium**

Representative recent commits:

- `Updated at 08-May-26 change property category Discount to Reduced`
- `Updated at 16-Jan-26`
- `changes`
- `Updated at 06-Feb-26 remove unnecessary properties`

No ticket references. No description of *why*. No "before/after" framing. Combined with the lack of PRs, this makes it impossible to audit "what changed in production this month and why."

**Fix:** require Conventional Commits or any consistent prefix scheme. Require a ticket reference in the message body.

---

#### D7. Dead `Backup/` folders carried in the repo — **Medium**

Both `Database/NewResSystem.Database.csproj` and `NewResSystem/NewResSystem.csproj` use `<Compile Remove="Backup\**" />` patterns to exclude folders from build. Those folders are still in the repo and in git history. They contain old copies of source. This is what `git revert` and tags are for.

**Fix:** delete the `Backup/` folders. Tag historical versions in git instead.

---

#### D8. Typos baked into namespaces — **Low**

`NewResSystem.Core.ApiIntigration` (should be "Integration"). Survives across the repo with hundreds of `using` statements pointing at it. Cannot be cleanly renamed without coordinated migration. Minor, but it tells you nobody has done a clean-up pass.

---

#### D9. Inline `<style>` blocks in Razor pages — **Low**

`Bookings/Booking.razor:14-18` and others define CSS classes inline within the page. Suggests no shared styling discipline; each page reinvents what it needs.

---

#### D10. PowerShell deployment artefacts in source — **Medium**

`bypass_script.ps1` at the repo root references `F:\Live Work\bypass_script.ps1` (a path on the live server). Operational tooling is intermingled with application source. There is no `infra/` or `scripts/` folder, no IaC, no documented deployment.

**Fix:** move operational scripts to a separate repo or a dedicated `infra/` directory with documented setup and an explicit policy on what may run on the production host.

---

### Environment

---

#### E1. .NET 7 is end-of-life — **High**

Microsoft ended support for .NET 7 in May 2024. The current production runtime has received no security patches for almost two years (as of May 2026). Same for EF Core 7.

**Fix:** plan a .NET 8 LTS upgrade. .NET 8 is supported until November 2026; .NET 10 LTS is the upgrade after that. Most .NET 7 → 8 upgrades are package-version bumps plus a handful of API tweaks; Blazor Server upgrades are usually straightforward.

---

#### E2. Build references a DLL from a sibling project's debug bin folder — **High**

`NewResSystem.Core.csproj`:

```xml
<Reference Include="WkHtmlToPdf">
  <HintPath>..\..\DekiwadiyaHMS\DekiwadiyaHospitalSystem\bin\Debug\net7.0\WkHtmlToPdf.dll</HintPath>
</Reference>
<Reference Include="Wkhtmltopdf.NetCore">
  <HintPath>..\..\DekiwadiyaHMS\DekiwadiyaHospitalSystem\bin\Debug\net7.0\Wkhtmltopdf.NetCore.dll</HintPath>
</Reference>
```

The build requires the developer's machine to contain **another unrelated project** (DekiwadiyaHMS — a hospital management system, presumably another ConnectUsSoftware client) in a sibling directory, with that project having been compiled in Debug mode first.

This is not reproducible. No CI system, no new developer, no auditor can build this from source as-is. It also means that hospital-management-system DLLs are deployed alongside the villa-rental application, which is a software-bill-of-materials nightmare.

**Fix:** find the NuGet package equivalents (`HakanL.WkHtmlToPdf-DotNet` or similar) or vendor the DLLs into the repo under a `lib/` folder with a relative path. Remove the cross-project dependency.

---

#### E3. No infrastructure-as-code — **Medium**

Deployment appears to be manual RDP-and-copy to `F:\Live Work\` on the IIS server. No Dockerfile, no Bicep/Terraform, no documented setup. If the server dies, recovery time is "however long it takes the vendor to remember every configuration knob."

**Fix:** document the setup in a `DEPLOYMENT.md` at minimum. Better: containerise (Linux containers run ASP.NET Core fine; Blazor Server in particular is container-friendly) and deploy to App Service / Container Apps / a managed host.

---

#### E4. Plesk on Windows IIS — **Medium**

Plesk on Windows is a perfectly valid hosting choice for an SMB but is unusual for a .NET 7 Blazor Server app handling payments. The combination introduces additional moving parts (Plesk's own panel, its file-permissions model, its auto-rotation behaviour) that few engineers will be familiar with. Combined with the manual deploy flow, it's a single-server single-vendor lock-in.

**Fix:** evaluate Azure App Service or Container Apps for the application tier, with managed Azure SQL or a comparable hosted Postgres/SQL Server for the database. Reduces the surface area significantly.

---

#### E5. Data Protection keys persisted to local filesystem — **Medium**

`Program.cs:26`:

```csharp
builder.Services.AddDataProtection()
    .PersistKeysToFileSystem(new DirectoryInfo(builder.Configuration.GetValue<string>("FilePaths:DPKeys:Physical")));
```

Keys are stored unencrypted on disk. If the server is single-instance, this works. If anyone ever needs to scale out, sessions will break. If the server is restored from a backup without those keys, every signed cookie/state becomes invalid.

**Fix:** encrypt the keys at rest (`ProtectKeysWithDpapi` or `ProtectKeysWithCertificate`), document where they live, and include them in the backup procedure.

---

#### E6. SQL Server connection retries are enabled — *positive note*

`Program.cs:56` uses `opt.EnableRetryOnFailure()`. Good. Transient connection failures will retry automatically.

---

#### E7. Konscious Argon2 chosen over PBKDF2/bcrypt — *positive note*

`HashPasswordConverter` uses `Konscious.Security.Cryptography.Argon2` (the modern recommendation). Worth auditing the parameter choice (memory size, iterations, parallelism) but the algorithm choice is sound.

---

## Effort estimate (recap)

| Method | Generous result |
|---|---|
| Hours per commit (22 commits over 6 months) | ~16 hours/month |
| Active days × full workday (18 active days) | ~24 hours/month |
| Authored LoC ÷ brownfield rate (~3,000 lines) | ~10 hours/month |
| Plus unobserved overhead (deploy, support, Zoho config) | +8–10 hours/month |

**Generous range: 10–20 hours/month.** Realistic from git alone: 6–12 hours/month. March 2026 had zero commits; four of the six months had ≤3 commits. This is part-time maintenance.

---

## Recommended triage order

| # | Action | Effort | When |
|---|---|---|---|
| 1 | Patch `AuthController.Login` to never echo `Data`; add `[JsonIgnore]` to sensitive `UsersViewModel` fields | < 1 hour | **Today** |
| 2 | Force-reset all staff passwords; rotate per-user SMTP credentials; pull `/api/Auth/login` access logs | A few hours | **Today** |
| 3 | Implement the missing `AuthMiddleware` class and wire it up at `Program.cs:142`; verify HMAC on the webhook; rotate the hard-coded GUID key | 1 day | This week |
| 4 | Remove `bypass_script.ps1`; replace its reminder call with a proper scheduled job hitting an authenticated endpoint | < 1 day | This week |
| 5 | Fix the empty `catch` blocks and the `res.Status = true` override in `PaymentController` | < 1 day | This week |
| 6 | Add `[Authorize]` to `Contacts.razor`; disable `DetailedErrors` in production; suppress server fingerprint headers; lengthen HSTS | < 1 day | This week |
| 7 | Stand up basic CI (build + lint) + a handful of controller tests targeting the changed endpoints | 2–3 days | This month |
| 8 | Remove the `..\..\DekiwadiyaHMS\...` build reference; pin a NuGet WkHtmlToPdf package | < 1 day | This month |
| 9 | Plan .NET 8 LTS upgrade | 1–2 weeks | Next quarter |
| 10 | Document deployment and key management; consider App Service / containers | Ongoing | Next quarter |

Items 1–2 are non-negotiable and time-sensitive: the hash for at least one admin account is presumed exposed as of this review.

---

## Evidence captured during the review

1. Login endpoint data leak — `curl` request and full response body (Nick Cookson, admin, real hash + salt). Treat the response as sensitive and store under restricted access.
2. WordPress-API unauthenticated mutation endpoint — `curl` request and response showing controller-level validation reached anonymously.
3. Repository clone at `/Users/garethlloyd/projects/villacollective/ResSystem` (commit `e5a8980`, 2026-05-08).
4. Public surface reconnaissance — HTTPS response headers from `vc2.mojodev.co.uk` confirming Blazor Server, IIS 10, Plesk Windows, and ASP.NET fingerprints.

No data was exfiltrated beyond what is documented above. No mutating endpoint was called with valid parameters. No login was attempted with credentials.

---

## Suggested next steps with the owner

1. Share findings 1–4 (the *Today / This week* items) verbally before sending this document — the login hash exposure should be patched and credentials rotated within hours, not after a written review cycle.
2. Establish whether the vendor (ConnectUsSoftware) is contracted directly or through Mojo Media UK; both need to be aware.
3. Ask whether the owner has any back-ups or access logs older than the IIS default retention, so the scope of any prior exposure can be bounded.
4. Decide whether the engagement is to continue with the current vendor under stricter process (PRs, CI, reviewer on the agency side) or to migrate. The codebase is recoverable — the framework is sound and the bulk of the bugs are concentrated in a few files — but the *process* needs to change regardless of who owns the code going forward.
