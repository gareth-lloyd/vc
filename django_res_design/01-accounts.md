# 01 — Accounts

System users (staff login) and contacts (owners, property managers, agents — many never log in).

## Models

### `User(AbstractUser)`
Standard Django auth user, extended:

- Inherits username, email, first_name, last_name, password, is_staff, is_superuser, is_active, date_joined.
- `email` — override to `EmailField(unique=True)`; we authenticate by email in practice.
- `phone` — `CharField(max_length=32, blank=True)`.
- `tfa_method` — `TextChoices` (`NONE`, `TOTP`). `SMS` is **deferred** — the enum value is reserved (future-proofing) but not exposed in the API and not implemented in MVP. See reconciliation issue #43.
- `tfa_secret` — `CharField(blank=True)` — base32-encoded TOTP shared secret (encrypted at rest; app-layer Fernet wrap with `settings.FERNET_KEYS`, same pattern as `comms.SmtpProfile` and `integrations.OAuthCredential`). Empty when `tfa_method=NONE`.
- `tfa_enrolled_at` — `DateTimeField(null=True, blank=True)` — set on successful `:enroll`; cleared when `:disable` runs.
- `tfa_recovery_codes` — `JSONField(default=list)` — list of hashed (bcrypt or pbkdf2 via Django's `make_password`) single-use recovery codes generated at enrollment. Plaintext is shown to the user **once** at the end of the `:enroll` flow; the API stores only hashes.
- `last_login_ip` — `GenericIPAddressField(null=True, blank=True)`.
- `role` — fixed `StaffRole` TextChoices (see "Staff roles" below).

`USERNAME_FIELD = "email"`. Use a custom `UserManager` to require email at creation.

Notes:
- SMTP per-user config (`SmtpAddress`/`SmtpPassword` on the legacy `UserMaster`) — **preserved**, but moved into the `comms` app as a separate `SmtpProfile` model rather than four columns on `User`. The workflow at `workflows/11-integrations/transmission.md` requires quotation emails to send *as* the agent so guest replies land in the agent's inbox; a single shared SMTP/SES profile cannot deliver that. Stored credentials are encrypted at rest with the same Fernet pattern used for `tfa_secret`, scoped per user, and only used by the `comms.EmailService` dispatcher — they are never exposed to the API. See `10-comms.md`.
- `IsSystemAdmin` is just Django's `is_superuser`.
- `IsLock` collapses into `is_active=False`.

### `Contact(AuditedModel)`

> ⚠️ **Being unified into `Person` (2026-06-18).** Per the
> `people-model-cleanup.md` banner + `10-decisions.md`, `Contact` and
> `reservations.Guest` merge into a single `accounts.Person` identity (capacity
> as role/relationship; `Organisation` replaces free-text `company`; `User`
> stays `OneToOne`). Tracked by `todo/gap-045`–`gap-048`. The fields below describe
> the pre-unification `Contact` and fold into `Person`.

The villa owner, property manager, or external agent. Distinct from `User` because most contacts never log in. If they do, we link via the optional `user` OneToOne.

- `title` — `CharField(max_length=16, blank=True)` (Mr / Mrs / Dr — free text)
- `first_name`, `last_name` — `CharField`
- `company` — `CharField(blank=True)`
- `website_url` — `URLField(blank=True)`
- `preferred_method` — `TextChoices` (`EMAIL`, `PHONE`, `SMS`) — fixes legacy `PrefferedMethod` typo
- `address_line_1`, `address_line_2` — `CharField(blank=True)`
- `notes` — `TextField(blank=True)`
- `status` — TextChoices (`ACTIVE`, `INACTIVE`, `ANONYMIZED`), default `ACTIVE`
- `anonymized_at` — DateTimeField(null=True, blank=True) — set by `anonymize()`; mirrors the timestamp on the status transition
- `user` — `OneToOneField(User, null=True, blank=True, on_delete=SET_NULL, related_name="contact")` — created lazily if the contact gains login access
- `legacy_id` — nullable, indexed (per 00-conventions)

Reverse relationships:
- `emails` (ContactEmail set)
- `phones` (ContactPhone set)
- `property_assignments` (PropertyContactAssignment set — defined in properties app)

Indexes: `(status, last_name, first_name)`, `legacy_id`.

#### Lifecycle

Per `00-conventions.md` "Lifecycle, not soft delete":

- **Wrong contact created in error, no relationships yet** — hard delete is permitted. `PropertyContactAssignment.contact` is `PROTECT`, so any contact with downstream rows can't be hard-deleted accidentally.
- **Contact retired** — set `status=INACTIVE`. Still visible in search results behind a status filter; never opaquely hidden.
- **Duplicate contacts** — call the explicit service method `Contact.merge(target)`: rewrites FKs on `PropertyContactAssignment`, `Quotation`, `Booking`, `Enquiry` to point at `target`; writes an `AuditLog` row per rewrite; **hard-deletes** `self`. Destructive and final — there is no `merged_into` self-FK and no surviving tombstone. The `AuditLog` is the only trail.
- **GDPR forget-me** — call `Contact.anonymize()`: overwrites `first_name`, `last_name`, `company`, `notes`, `address_line_1`, `address_line_2` with `"[REDACTED]"` or empty; cascades to `ContactEmail.email` (replaced with `"redacted-{id}@anonymized.local"`) and `ContactPhone.number` (replaced with empty string); sets `status=ANONYMIZED`, `anonymized_at=now()`. Row remains for FK integrity on historical assignments and quotations. Still searchable by ID.

Sensitive field edits on `Contact` (PII, address, name) are tracked into `AuditLog` via the `core.audit.track(...)` registration in `accounts.apps.ready()`.

> **Design intent — operator tags + standing linked contacts (owner Loom 2026-06-17).**
> The sales team wants first-class **tags** on the customer (VIP / Repeat / Trade /
> PA / Nick's friend / Nick's network / Disability / Approach-with-care /
> Past-issues / Specific-preferences / Time-waster) and **standing person-to-person
> links** (spouse / child / PA) that persist across bookings — distinct from the
> per-booking `BookingGuest` roles in `05-reservations.md`. Neither exists in the
> model yet; the entity that carries them is the unified **`accounts.Person`**
> (GAP-045 — supersedes the earlier Guest-vs-Contact split), with the model shape
> and the Repeat-is-derived / PA-overlaps-the-link-role reconciliation settled in
> [`todo/gap-040-customer-tags-taxonomy.md`](todo/gap-040-customer-tags-taxonomy.md)
> and [`todo/gap-041-standing-linked-contacts.md`](todo/gap-041-standing-linked-contacts.md).
> Sensitive tags (Disability / Approach-with-care) may carry retention/consent
> implications — cross-ref `todo/q-010-guest-data-retention.md`.

### `ContactEmail(TimestampedModel)`
- `contact` — `ForeignKey(Contact, on_delete=CASCADE, related_name="emails")`
- `email` — `CIEmailField` (case-insensitive via `citext`)
- `label` — `TextChoices` (`PRIMARY`, `WORK`, `PERSONAL`, `OTHER`)
- `is_primary` — `BooleanField(default=False)`

Constraints:
- `UniqueConstraint(fields=["contact", "email"], name="unique_contact_email")`
- `UniqueConstraint(fields=["contact"], condition=Q(is_primary=True), name="one_primary_email_per_contact")`

### `ContactPhone(TimestampedModel)`
- `contact` — FK CASCADE
- `number` — `CharField(max_length=32)` (E.164 recommended but not enforced; admin validation)
- `label` — `TextChoices` (`MOBILE`, `WORK`, `HOME`, `FAX`, `OTHER`)
- `is_primary` — bool

Same unique-primary constraint pattern as `ContactEmail`.

## Roles

There are **two distinct role concepts** in the system — keep them separate.

### Staff roles (`User.role`)

What back-office capability does a logged-in staff user have? Fixed `TextChoices`, not a table:

```python
class StaffRole(models.TextChoices):
    ADMIN = "admin", "Admin"                  # full access; equivalent to legacy IsSystemAdmin=1
    RESERVATIONS = "reservations", "Reservations"  # bookings, enquiries, guests, comms
    ACCOUNTS = "accounts", "Accounts"         # payments, refunds, finance config
    VIEWER = "viewer", "Viewer"               # read-only across the back office
```

Each enum value maps to a Django `auth.Group` of the same name (created via a data migration); the Group owns the actual `auth.Permission` rows. Switching a user's `role` re-attaches them to the matching Group. This gives us:

- A fixed, code-reviewed set of role definitions (no operator typos, no half-configured custom roles in production).
- Django's permission framework as the runtime check surface (`user.has_perm("reservations.add_booking")`).
- A clean upgrade path if the business ever needs custom roles: drop the enum, replace with `Role` FK to a new model that wraps the existing Groups. The API surface (`GET /roles`) stays compatible.

**Legacy mapping**: the legacy `UserMaster` table had no role concept beyond `IsSystemAdmin` (bool). `IsSystemAdmin=1` → `StaffRole.ADMIN`; `IsSystemAdmin=0` → `StaffRole.RESERVATIONS` by default at migration (the operator can subsequently lower individual users to `ACCOUNTS` / `VIEWER` via the admin UI). The legacy `VillaRole` table is **not** the source — that's a *contact* role, see below.

API surface: `GET /roles` is a read-only enum listing for FE dropdowns; there is no POST/PATCH/DELETE and no `/permissions` catalogue endpoint. Per-caller capability introspection rides on `GET /auth/permissions`.

### Contact roles (`ContactRole` on `PropertyContactAssignment`)

How is a `Contact` related to a `Property`? Different concept entirely — referenced from `properties.PropertyContactAssignment`:

```python
class ContactRole(models.TextChoices):
    OWNER = "owner", "Owner"
    MANAGER = "manager", "Manager"
    AGENT = "agent", "Agent"
    HOUSEKEEPER = "housekeeper", "Housekeeper"
    OWNERS_REPRESENTATIVE = "owners_rep", "Owner's representative"
```

This is the direct replacement for the legacy `VillaRoles` table (5 static rows: Owner / Agent / Villa Admin / Villa Manager / Management Company), which was FK'd from `VillaContactMap` — i.e. always a contact-to-property mapping role, never a staff-permissions role.

## Why Contact is not a User by default

- 90% of contacts are passive (we email them booking summaries, they don't log in).
- Forcing every Contact to be a User creates a username/password row per owner, bloats auth queries, and confuses permissions logic.
- The OneToOne link is opportunistic: if an owner is given a dashboard login, we create the User and set `Contact.user = user`.

## Permissions

Standard Django permissions per model. Add three custom `Permission` rows on `Property`:

- `can_view_finance` — restrict finance config visibility to admins and the property's owner
- `can_approve_booking` — for owners/managers to confirm bookings
- `can_manage_availability` — block dates from the admin calendar

Implement via DRF object-level permissions when the API layer is added.

## Two-factor authentication

API surface: `POST /auth/2fa:challenge`, `:verify`, `:enroll`, `:disable` (§2.1). See reconciliation issue #43.

**TOTP only in MVP.** SMS-based 2FA is deferred — no provider integration (Twilio etc.) is wired in v1; the `SMS` enum value is reserved on `User.tfa_method` so a future migration doesn't have to rewrite the column, but `:enroll` only accepts `method=TOTP` and `:challenge` only dispatches for `method=TOTP`. Revisit SMS once an MVP-level reason appears.

### Library

- [`pyotp`](https://pyauth.github.io/pyotp/) — industry-standard, well-tested TOTP/HOTP implementation. Single dependency, no Django coupling, RFC 6238-compliant.
- TOTP parameters: 30-second step, 6-digit codes, SHA-1 (the Google Authenticator default; tighter algorithms break older authenticator apps).
- Drift tolerance: ±1 step on `:verify` (the standard 90-second window).

### `accounts.services.TwoFactorService`

```python
class TwoFactorService:
    @staticmethod
    def enroll(user) -> EnrollmentPayload:
        """Generate a fresh TOTP secret and recovery codes.

        Stores the encrypted secret on User.tfa_secret (PENDING — not yet
        confirmed) and the hashed recovery codes on User.tfa_recovery_codes.
        Returns the plaintext secret + provisioning URI (otpauth://) +
        plaintext recovery codes for one-time display to the user.

        Does NOT set tfa_method=TOTP yet — that happens on the first
        successful :verify against the new secret.
        """

    @staticmethod
    def confirm_enrollment(user, code: str) -> bool:
        """Verify the user's first TOTP code; on success, flip tfa_method
        to TOTP and set tfa_enrolled_at. Failure leaves the pending
        secret intact so the user can retry."""

    @staticmethod
    def challenge(user) -> ChallengeToken:
        """Mint a short-lived challenge token (signed, expires in 5 min)
        that the client posts back with the TOTP code at :verify. Used
        in the post-password, pre-fully-authenticated state."""

    @staticmethod
    def verify(challenge_token: str, code: str) -> User:
        """Validate the TOTP code (or a single-use recovery code) against
        the user resolved from the challenge token. Returns the fully
        authenticated user. Failed attempts increment a rate-limited
        counter; 5 fails within 5 minutes locks 2FA for 15 minutes."""

    @staticmethod
    def disable(user, *, actor) -> None:
        """Clear tfa_method back to NONE, blank tfa_secret, null
        tfa_enrolled_at, empty tfa_recovery_codes. Writes an AuditLog
        row. Requires the user's password to be re-entered at the
        API layer (handled in the view, not the service)."""
```

The view dispatchers for `:challenge` / `:verify` / `:enroll` / `:disable` are thin DRF action endpoints that delegate to this service. The endpoint contract is documented in `04-rest-api-surface.md` §2.1 and stays unchanged by this issue.

## Sessions

API surface: `GET /auth/sessions`, `DELETE /auth/sessions/{id}`, plus the admin-only `GET /users/{id}/sessions` and `DELETE /users/{id}/sessions/{session_id}` (§2.18). See reconciliation issue #41.

**No new session model.** Use Django's default DB-backed session store (`django.contrib.sessions`, `SESSION_ENGINE = "django.contrib.sessions.backends.db"`); the `django_session` table is already queryable. JWT-only API auth would skip sessions entirely, but the admin UI and the magic-link / owner-portal flows both need a server-side session anchor for revocation (revoking a JWT post-issue is not natively possible). Mixed mode is fine — `auth.Session` covers the revocable surface; short-lived JWTs cover API calls.

### `accounts.services.SessionService`

Stateless helpers over `django.contrib.sessions.models.Session`:

```python
class SessionService:
    @staticmethod
    def list_for_user(user) -> list[SessionInfo]:
        """Return non-expired sessions for the user.

        Sessions don't carry a user FK natively; we filter by decoding
        the session_data and matching `_auth_user_id`. For scale, we
        also write a denormalised `accounts.UserSession(user, session_key,
        created_at, last_seen_at, user_agent, ip)` row on login (post_login
        signal) so listings are an indexed query rather than a full-table
        decode. The Session table remains the source of truth for the
        session itself; UserSession is a cached index.
        """
        ...

    @staticmethod
    def revoke(session_key: str, *, actor) -> None:
        """Delete the django_session row and the UserSession index row;
        write an AuditLog entry."""
        ...

    @staticmethod
    def revoke_all_for_user(user, *, except_current: str | None = None, actor) -> int:
        """Bulk revoke; used by 'sign out everywhere'."""
        ...
```

### `accounts.UserSession(TimestampedModel)`

Denormalised index over the Django session table — created on login (post-login signal), updated on each request (middleware), deleted alongside the Session on revoke.

- `user` — FK User CASCADE, related_name="sessions"
- `session_key` — `CharField(max_length=40, unique=True)` — mirrors `django_session.session_key`
- `created_at` — `DateTimeField(auto_now_add=True)`
- `last_seen_at` — `DateTimeField(auto_now=True)`
- `user_agent` — `CharField(max_length=512, blank=True)`
- `ip` — `GenericIPAddressField(null=True, blank=True)`
- `revoked_at` — `DateTimeField(null=True, blank=True)` — set when revoked through the service; the underlying `Session` row is hard-deleted, but `UserSession` lingers briefly for audit then is cleaned up by `cleanup_revoked_sessions` (daily Celery beat).

Indexes: `(user, last_seen_at)`.

This keeps `GET /auth/sessions` and `GET /users/{id}/sessions` cheap (one indexed query), while revocation hits both tables in a single `transaction.atomic` so the underlying Django session is genuinely invalidated.

## Out of scope here

- Guest entity — lives in `reservations/` (a Guest may have an optional User OneToOne — same opportunistic pattern as Contact). Multi-person bookings link to multiple `Guest` rows via `reservations.BookingGuest` (`LEAD` / `CO_TRAVELLER` / `PAYER` / `CC_ONLY`); see `05-reservations.md`. **`Contact` and `Guest` are not the same model** — `Contact` is the operator-side CRM entity (owners, managers, agents); `Guest` is the booking-side person model (travellers, payers, CC'd family).
- Property assignment (which Contacts manage which Properties) — lives in `properties/` via `PropertyContactAssignment`.
- Payment / financial recipient mapping — flows through `properties.PropertyFinance.contact`.
