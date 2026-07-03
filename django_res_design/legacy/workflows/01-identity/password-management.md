# Password Management

Self-service password reset (forgot password → emailed link → set new password) plus admin-driven password change.

## Request password-reset link

**ID:** `IDENTITY.PASSWORD.RESET_REQUEST`
**Trigger:** `POST /account/ForgotPassword` (Razor Page handler — page itself not in the committed code, but service method is).
**Actor:** Unauthenticated user supplying their email.
**Legacy locus:** `UserService.cs:311` (`ForgotPasswordAsync`), `UserService.cs:357` (`EmailLinkLog` helper).

### Inputs
- `Email` (string)
- `baseUrl` (string, computed from the request)

### Process
1. Generate code: `code = "VC_" + Guid.NewGuid()`.
2. Load template `EmailTemplate.VC_USER_PASSWORD_RESET`.
3. Substitute `#InterfaceGatewayURL#` → `{baseUrl}/account/ResetPassword?code={code}`.
4. `EmailService.SentEmail(emailConfig)` to the user's `Email`.
5. On send-success, `EmailLinkLog` runs `sp_villaEmailLinkLog` with `@TemplateType=Email_Template_Type.User_PasswordReset`, `@Code={code}`, `@EmailTo={email}`, `@UsedExpireAt = now + 4h`, `@Action=INSERT`.

### Outputs / side effects
- **DB write:** one row in the email-link-log table (name not in committed schema, accessed only via SP).
- **Email out:** reset link email.

### Data transformations for storage
- Code stored **plaintext** `[SECURITY]` — fine for an attacker reading the DB to immediately use any unexpired token.

### Failure modes
- User not found → "could not sent link to your email" (returned to caller; UI shows generic).
- Template missing → throws.
- SMTP failure → `Status=false`; log row **not** inserted.

### Open questions
- The combination of "no enumeration protection" + "code in plaintext + 4h TTL" is the typical reset-flow set of issues. Django redesign should: (a) always return success to the user, (b) hash the token (HMAC + pepper) at rest, (c) tie the TTL into the row and DELETE on use, (d) optionally rotate the user's session secret on completion.

---

## Complete password reset

**ID:** `IDENTITY.PASSWORD.RESET_COMPLETE`
**Trigger:** `POST /account/ResetPassword?code={GUID}` with new password.
**Actor:** Unauthenticated user holding a valid emailed code.
**Legacy locus:** Page handler is one of the *missing* pieces — only the helper path is in code (`UserService.cs:357` `EmailLinkLog` with `@Action=SELECT`). The endpoint behaviour below is inferred from the helper contract.

### Inputs
- `code` (string, the emailed `VC_{GUID}`)
- `Password`, `ConfirmPassword` (string, must match)

### Process (inferred)
1. `EmailLinkLog` with `@Action=SELECT` and `@Code=code` returns `UserId`, `EmailTo`, `UsedExpireAt`.
2. Validate `UsedExpireAt > now` and code matches.
3. Validate `Password == ConfirmPassword`.
4. Generate `PasswordSalt = HashPasswordConverter.CreateSalt()` and `PasswordHash = CreateHashPassword(Password, salt)`.
5. `UserService.ModifyUsers` with `@Action=UPDATE_PASSWORD` writes new salt + hash on `UserMaster`.
6. Code row is **not** marked used `[SECURITY]` — natural TTL is the only defence against replay.

### Outputs / side effects
- **DB write:** `UserMaster.Password`, `UserMaster.PasswordSalt` updated.
- Active sessions are **not** invalidated `[SECURITY]` — the resetting user's old cookies remain valid until they naturally expire.

### Failure modes
- Code expired / not found → caller error.
- Passwords mismatch → form validation.

### Open questions
- Django redesign should: invalidate the token row on use, rotate the user's `password_changed_at` timestamp, and force re-login of any active session (Django's `update_session_auth_hash` etc.).

---

## Admin: change a user's password

**ID:** `IDENTITY.PASSWORD.ADMIN_CHANGE`
**Trigger:** Admin clicks "Change" button on the Password tab of the user grid (`Users.razor`).
**Actor:** Admin (`Authorize(Roles="Admin")`).
**Legacy locus:** `NewResSystem/Pages/Admin/Users.razor:395` (`PasswordChangeAsync`), `UserService.cs:ModifyUsers`.

### Inputs
- `Id` (target user id)
- `Password`, `ConfirmPassword`
- Implicit: admin user identity from session

### Process
1. Client-side: both non-empty and equal.
2. Generate salt + Argon2i hash as in self-service reset.
3. `UserService.ModifyUsers(args, false)` → `sp_userMaster` with `@Action=UPDATE_PASSWORD`.

### Outputs / side effects
- **DB write:** `UserMaster.Password`, `PasswordSalt`.
- **No notification** to the user that their password has changed `[SECURITY]`.

### Open questions
- Django redesign should email the user when an admin changes their password, and force them to choose a new one on next login.
