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
