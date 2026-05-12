# Authentication

Workflows that establish and tear down the user's authenticated session, and that propagate auth state into Blazor circuits.

## Authenticate user with email and password

**ID:** `IDENTITY.AUTH.LOGIN_PASSWORD`
**Trigger:** `POST /account/login` (Razor Pages `Login.cshtml.cs:OnPostForm1`) **or** `POST /api/auth/login` (`AuthController.Login`)
**Actor:** Unauthenticated visitor.
**Legacy locus:** `NewResSystem/Pages/Account/Login.cshtml.cs:62`, `NewResSystem.Core/Services/Users/UserService.cs:37`, `NewResSystem/Controllers/AuthController.cs:33`.

### Inputs
- `Email` (string)
- `Password` (string, plaintext on the wire — HTTPS at the edge is the only protection)
- `returnUrl` (querystring, optional)

### Process
1. `UserService.GetLoginDetails(Email)` runs `sp_getLoginDetails` returning `UsersViewModel` from `UserMaster`.
2. `HashPasswordConverter.ValidatePassword(plaintext, PasswordSalt, PasswordHash)` recomputes Argon2i (`DegreeOfParallelism=4, Iterations=16, MemorySize=8MB`) and constant-time-compares.
3. If `IsTwoFactoryAuth == false`:
   - Build `ClaimsIdentity` with claims `NameIdentifier`, `Name`, `Role` (`Admin` if `IsSystemAdmin` else `User`), `Sid`, `Email`.
   - `HttpContext.SignInAsync(CookieAuthenticationDefaults.AuthenticationScheme, claimsPrincipal)` — emits cookie `NewResCookie` (24h, HttpOnly, SameSite=Strict in prod).
   - `UserService.ModifyUsers(data, false)` with `@Action = LAST_LOGIN` updates `UserMaster.LoginAt`.
   - 302 → `returnUrl` else `/`.
4. If `IsTwoFactoryAuth == true`: invoke `IDENTITY.AUTH.TFA_ISSUE` (see below) — do not sign in yet.

### Outputs / side effects
- **DB write:** `UserMaster.LoginAt` updated.
- **Cookie set:** `NewResCookie`.
- **No event log row** — last-login tracking is a single overwrite.

### Failure modes
- User not found → generic "Invalid username or password".
- Hash mismatch → same generic message.
- **No lockout / rate limiting** `[SECURITY]` — brute-force is unprotected.
- Exception → logged, error in `TempData`.

### Open questions
- Django redesign should add lockout (`django-axes` or equivalent) and replace claims-based role with Django's group/permission model.

---

## Issue and send two-factor code

**ID:** `IDENTITY.AUTH.TFA_ISSUE`
**Trigger:** Login workflow detects `IsTwoFactoryAuth == true`, **or** user POSTs the "Resend Code" form (`OnPostForm3`).
**Actor:** System (during partial-auth flow).
**Legacy locus:** `Login.cshtml.cs:213` (resend handler), `UserService.cs:184` (`SentAuthCode`).

### Inputs
- `Id` (user id), `ContactType=10` (email), `Email`, `baseUrl`.

### Process
1. Generate code: `Random().Next(0, 999999).ToString("D6")` `[SECURITY]` — non-cryptographic RNG, predictable. Should be `RandomNumberGenerator`-derived in redesign.
2. Load email template `EMAIL_AUTH_CODE_TEMPLATE` from disk.
3. Substitute `{:InterfaceGatewayURL:}`, `{:AuthCode:}`, `{:InterfaceURL:}`.
4. `EmailService.SentEmail(emailConfig)` via the user-or-global SMTP profile.
5. `sp_crud_auth_code` with `@Action=INSERT`, `@AuthType='TWO_FACTOR_AUTH'`, `@ContactType=10`, `@AuthCode={code}`, `@ExpireAt = now + 2h`.

### Outputs / side effects
- **DB write:** new `VillaCodeSentHistories` row (code stored **plaintext** `[SECURITY]`).
- **Email out:** via SMTP.
- Old codes are not invalidated — multiple in-flight codes will validate.

### Failure modes
- Template missing → throws.
- SMTP failure → `Status=false` returned, error in TempData; row not inserted.

---

## Verify two-factor code

**ID:** `IDENTITY.AUTH.TFA_VERIFY`
**Trigger:** `POST /account/login` (handler `OnPostForm2`).
**Actor:** Partially-authenticated user.
**Legacy locus:** `Login.cshtml.cs:147`, `UserService.cs:VerifyAuthCode`.

### Inputs
- `Id` (user id, hidden form field)
- `AuthCode` (6-digit string)

### Process
1. Query `VillaCodeSentHistories` where `UserId=@Id AND AuthType='TWO_FACTOR_AUTH' AND ContactType=10 AND AuthCode=@authCode`.
2. Check `ExpireUtc < UTC now`.
3. On success: `UserService.GetLoginDetails(Id)` → build identical `ClaimsIdentity` to password-login → `SignInAsync` → record `LAST_LOGIN` → 302 to `returnUrl` (else `/`).

### Outputs / side effects
- Cookie set as in password login.
- The used code is **not** marked consumed `[SECURITY]` — same code can be re-used until it expires.

### Failure modes
- Code not found / expired → "Auth code is expired, Please resend and try again!"

---

## Log out

**ID:** `IDENTITY.AUTH.LOGOUT`
**Trigger:** `GET /account/logout` (`LogoutModel.OnGet`) or `POST /api/auth/logout` (`AuthController.Logout`).
**Actor:** Authenticated user.
**Legacy locus:** `NewResSystem/Pages/Account/Logout.cshtml.cs:9`, `AuthController.cs:75`.

### Inputs
None.

### Process
1. `HttpContext.SignOutAsync()` — clears `NewResCookie`.
2. Razor variant 302 → `/account/login`. API variant returns empty `Response`.

### Outputs / side effects
- Cookie removed.
- No server-side session record to invalidate (cookie auth is stateless).
- Active Blazor circuits lose auth state at next `GetAuthenticationStateAsync` poll.

---

## Propagate authentication state to Blazor circuits

**ID:** `IDENTITY.AUTH.CIRCUIT_STATE`
**Trigger:** Blazor circuit initialization and any `NotifyAuthenticationStateChanged` call.
**Actor:** System.
**Legacy locus:** `NewResSystem.Core/Auth/ResAuthentication.cs:14`.

### Inputs
- Implicit: `IHttpContextAccessor.HttpContext.User` (the principal from the cookie).

### Process
1. `ResAuthentication.GetAuthenticationStateAsync()` wraps current `HttpContext.User` in `AuthenticationState`.
2. Components consume via `[Authorize]` / `[Authorize(Roles="Admin")]` and `AuthenticationStateProvider`.

### Outputs / side effects
- Protected components hidden / redirected when principal is anonymous.
- No DB writes.

### Open questions
- The Blazor seam vanishes in a Django + React redesign; auth state lives in the SPA client (token or session cookie) and the Django backend does pure cookie-or-JWT auth. This workflow has no Django analogue.

---

## Track Blazor circuit open/close

**ID:** `IDENTITY.AUTH.CIRCUIT_LIFECYCLE`
**Trigger:** Blazor SignalR circuit lifecycle events.
**Actor:** System (`ResCircuitHandler`).
**Legacy locus:** `NewResSystem/ResHandler/ResCircuitHandler.cs:20-41`, `MissingStubs.cs:21` (`ConnectionTracker` `[STUB]`).

### Process
1. `OnCircuitOpenedAsync` sets `ConnectionTracker.IsConnected = true`.
2. `OnCircuitClosedAsync` and `OnConnectionDownAsync` set `false`.

### Outputs / side effects
- In-memory flag only. Used (or intended to be used) by components for an "offline" indicator.

### Open questions
- The stub is empty; the original `ConnectionTracker` was never committed. No Django analogue needed.
