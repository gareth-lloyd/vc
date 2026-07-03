# User Administration

Admin-driven user CRUD. All operations multiplex through one stored procedure (`sp_userMaster`) keyed by an `@Action` parameter.

## Create or update user

**ID:** `IDENTITY.USER.UPSERT`
**Trigger:** Admin clicks "Save" on `Users.razor` form (action = `INSERT` for new, `UPDATE` for edit).
**Actor:** Admin (`Authorize(Roles="Admin")`).
**Legacy locus:** `NewResSystem/Pages/Admin/Users.razor:319` (`SubmitAsync`), `UserService.cs:37` (`ModifyUsers`).

### Inputs
Identity:
- `Id` (0 for INSERT, > 0 for UPDATE)
- `Email`, `FirstName`, `LastName`
- `MobileNo`

Auth/2FA:
- `IsTwoFactoryAuth` (bool)
- `TFAMethod` (0 = Disabled, 10 = Email; SMS branch commented out)
- `IsVerified` (mobile-verified flag, not used by current 2FA branch)

Permissions / status:
- `IsActive`, `IsSystemAdmin`

Per-user SMTP (used when this user sends quotations):
- `SmtpAddress`, `SmtpPort`, `SmtpUserName`, `SmtpPassword` — plaintext at rest `[SECURITY]`
- `IsTlsRequired`, `IsAuthRequired`

Password (optional on UPDATE; required on INSERT):
- `Password`, `ConfirmPassword`

Audit:
- `User` (admin's username)
- `Action` (`INSERT` | `UPDATE`)

### Process
1. **SMTP all-or-nothing validation** (UI): if any SMTP field is filled, all must be (`Users.razor:324-349`).
2. If `Password` provided: generate fresh `PasswordSalt` and `PasswordHash` (Argon2i — same params as login).
3. `UserService.ModifyUsers(args, isExistEmail)`:
   - For INSERT, first runs `sp_userMaster` with `@Action=SELECTEXITS` and the supplied email.
     - If returns a non-deleted row → `"Email {email} is already exists!"` error.
     - If returns a soft-deleted row → flip `@Action` to `RESTORE` (`UserService.cs:62`) and proceed.
   - Otherwise call `sp_userMaster` with the original action and `GetUserParams()`-built parameter list (`UserService.cs:126-153`): `@Id`, `@Email`, `@FirstName`, `@LastName`, `@Password` (hash), `@PasswordSalt`, `@IsTFAAuth`, `@TFAMethod`, `@MobileNo`, `@IsVerified`, `@IsActive`, `@IsSystemAdmin`, `@User`, `@IsTls`, `@IsAuth`, `@SmtpAddress`, `@SmtpUser`, `@SmtpPassword`, `@SmtpPort`, `@Action`.

### Outputs / side effects
- **DB write:** `UserMaster` INSERT or UPDATE; on RESTORE `DeletedBy`/`DeletedAt` cleared.
- Toast notification in the admin UI.
- **No email** to the newly-created user.

### Data transformations for storage
- Password → Argon2i hash + Base64 16-byte salt.
- SMTP password is stored as-is (plaintext) `[SECURITY]`.

### Failure modes
- Duplicate active email → block.
- SMTP partial fill → toast, no DB call.
- SP failure → "Please Fill require field" or SP-supplied message.

### Open questions
- The `RESTORE` action multiplexed onto `INSERT` is fragile — restoring a soft-deleted user does **not** reset password (the old hash survives); decide whether that's the desired Django behaviour or whether restore should require a fresh password.

---

## Soft-delete user

**ID:** `IDENTITY.USER.SOFT_DELETE`
**Trigger:** Admin clicks the row trash icon on `Users.razor`; confirmation modal returns yes.
**Actor:** Admin.
**Legacy locus:** `Users.razor:311` (`OnConfirmChange`), service path identical to upsert.

### Inputs
- `Id` (target user id)
- Implicit admin identity

### Process
1. `UIService.IsConfirmAsync()` modal.
2. `SubmitAsync(DbAction.DELETE)` → `sp_userMaster` with `@Action=DELETE`.
3. SP sets `DeletedAt = GETDATE()`, `DeletedBy = current admin`; row stays.

### Outputs / side effects
- **DB write:** `UserMaster.DeletedAt`/`DeletedBy` set.
- User can no longer log in (login query filters `DeletedBy IS NULL`).
- User remains recoverable via the `SELECTEXITS → RESTORE` path of the upsert workflow.

### Open questions
- No anonymisation step on delete. GDPR-erasure-on-request is a separate workflow that doesn't yet exist.
