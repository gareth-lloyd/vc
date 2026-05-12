# 01 · Identity

Authentication, authorization state, password lifecycle, and admin user management. Covers the seam between Razor-Pages cookie auth (login/logout pages) and Blazor Server circuit authentication state.

## Files

| File | Workflows |
|---|---|
| [`authentication.md`](./authentication.md) | Login (password), 2FA verify, 2FA resend, logout, API login, API logout, circuit auth state propagation, circuit connection tracking |
| [`password-management.md`](./password-management.md) | Request password-reset link, complete password reset, admin-driven user password change |
| [`user-administration.md`](./user-administration.md) | Create user, edit user, soft-delete user (with restore-via-INSERT) |

## Entities touched

- `UserMaster` — `Id`, `Email`, `FirstName`, `LastName`, `Password` (Argon2i hash), `PasswordSalt`, `IsSystemAdmin`, `IsTfaauth`, `TFAMethod`, `MobileNo`, `IsVerified`, `IsActive`, `LoginAt`, SMTP-per-user fields (`SmtpAddress`/`SmtpUserName`/`SmtpPassword`/`SmtpPort`/`IsTlsRequired`/`IsAuthRequired`), `CreatedAt`/`CreateBy`/`UpdatedAt`/`UpdatedBy`/`DeletedAt`/`DeletedBy`
- `VillaCodeSentHistories` — `UserId`, `AuthType` (`TWO_FACTOR_AUTH`), `AuthCode`, `ContactType` (10 = email), `Contact`, `CreatedAt`/`CreatedUtc`, `ExpireAt`/`ExpireUtc`
- Email link log (via `sp_villaEmailLinkLog`) — `UserId`, `TemplateType`, `Code` (GUID), `EmailTo`, `UsedExpireAt`

## Stored procedures

- `sp_getLoginDetails` — fetch user by email for login
- `sp_userMaster` — multiplexed CRUD on `UserMaster` (actions: `INSERT`, `UPDATE`, `DELETE`, `RESTORE`, `SELECTEXITS`, `LASTLOGIN`, `UPDATE_PASSWORD`)
- `sp_getUsers` — paginated user list
- `sp_crud_auth_code` — write 2FA codes
- `sp_villaEmailLinkLog` — write/look up password-reset link records

## Cross-cutting decisions worth challenging in the Django redesign

- Password hashing is Argon2i with `DegreeOfParallelism=4, Iterations=16, MemorySize=8MB`. Django's `argon2id` (via `django[argon2]`) is a sensible replacement; salt/hash storage shapes will change.
- 2FA codes are stored **in plaintext** in `VillaCodeSentHistories.AuthCode` — `[SECURITY]`. Hash them (HMAC-SHA256 with a server-side pepper) in the redesign.
- Password reset codes (4-hour TTL GUIDs) are stored in plaintext — same `[SECURITY]` issue.
- Each user has their own SMTP credentials stored in `UserMaster` in plaintext — `[SECURITY]`. Consider whether per-user SMTP is still a requirement (it underpins quotation emails sent "from" the agent) and if so use encrypted-at-rest credentials or a vault.
- Mixed cookie-auth (Razor Pages) + Blazor circuit-auth (via `AuthenticationStateProvider`) is a transitional artifact. Pure Django auth removes the seam.
- Soft-delete with restore via INSERT-after-existing-email is a hack (`SELECTEXITS` → `RESTORE` action). Django redesign should use explicit `is_active`/`deleted_at` with admin UI for reactivation.
