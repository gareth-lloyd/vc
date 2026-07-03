# 01 — Accounts

> **Design-time spec — frozen 2026-07-03.** Rationale for the design as
> conceived; not a live description of the built system. Current truth:
> [`../data-model-overview.md`](../data-model-overview.md) + the code in
> `django_res/` + [`../../todo/INDEX.md`](../../todo/INDEX.md).

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
- `tfa_last_verified_step` — `BigIntegerField(null=True, blank=True, editable=False)` — the last TOTP 30-second step index consumed by `verify_code` (GAP-057). The single-use replay guard: a code whose step is `<=` this value is refused, and a successful verify atomically advances it. `NULL` until the first `verify_code` (login or refund step-up). Not touched by the recovery-code path.
- `last_login_ip` — `GenericIPAddressField(null=True, blank=True)`.
- `role` — fixed `StaffRole` TextChoices (see "Staff roles" below).

`USERNAME_FIELD = "email"`. Use a custom `UserManager` to require email at creation.

Notes:
- SMTP per-user config (`SmtpAddress`/`SmtpPassword` on the legacy `UserMaster`) — **preserved**, but moved into the `comms` app as a separate `SmtpProfile` model rather than four columns on `User`. The workflow at `workflows/11-integrations/transmission.md` requires quotation emails to send *as* the agent so guest replies land in the agent's inbox; a single shared SMTP/SES profile cannot deliver that. Stored credentials are encrypted at rest with the same Fernet pattern used for `tfa_secret`, scoped per user, and only used by the `comms.EmailService` dispatcher — they are never exposed to the API. See `10-comms.md`.
- `IsSystemAdmin` is just Django's `is_superuser`.
- `IsLock` collapses into `is_active=False`.

### `Person(AuditedModel)`

> ✅ **Unified into `Person` — delivered (GAP-045, 2026-06-22).** Per the
> `people-model-cleanup.md` banner + `10-decisions.md`, the model formerly
> `Contact` was renamed `accounts.Person` and `reservations.Guest` was folded
> into it: there is now **one** human-identity model. `Person.kind`
> (CUSTOMER vs CONTACT) distinguishes booking-side customers (travellers,
> payers) from operator-side contacts (owners, managers, agents); `User` stays
> an optional `OneToOne`. The section below documents the unified `Person`.
> Tracked by `todo/gap-045`–`gap-048`.

The single human-identity model — booking-side customers (travellers, payers, CC'd family) **and** operator-side contacts (villa owners, property managers, external agents). Distinct from `User` because most people never log in. If they do, we link via the optional `user` OneToOne. The `kind` field tells the two populations apart (a directory filter hint, not access control).

- `title` — `CharField(max_length=16, blank=True)` (Mr / Mrs / Dr — free text)
- `first_name`, `last_name` — `CharField`
- `company` — `CharField(blank=True)`
- `website_url` — `URLField(blank=True)`
- `preferred_method` — `TextChoices` (`EMAIL`, `PHONE`, `SMS`), default `EMAIL` — fixes legacy `PrefferedMethod` typo
- `address_line_1`, `address_line_2` — `CharField(blank=True)`
- `town`, `post_code` — `CharField(blank=True)`
- `country` — `FK properties.Country PROTECT`, null=True, blank=True
- `marketing_consent` — `BooleanField(default=False)`
- `notes` — `TextField(blank=True)`
- `status` — TextChoices (`ACTIVE`, `INACTIVE`, `ANONYMIZED`), default `ACTIVE` (`PersonStatus`)
- `kind` — TextChoices (`CUSTOMER`, `CONTACT`), default `CONTACT` (`PersonKind`) — CUSTOMER for booking-side people (set by the customer-create path and the legacy `ClientLoader`), CONTACT for owner/manager/agent records. A `/contacts` filter hint, not access control.
- `anonymized_at` — DateTimeField(null=True, blank=True) — set by `anonymize()`; mirrors the timestamp on the status transition
- `user` — `OneToOneField(User, null=True, blank=True, on_delete=SET_NULL, related_name="contact")` — created lazily if the person gains login access
- `legacy_id` — nullable, indexed (per 00-conventions)

Reverse relationships:
- `emails` (PersonEmail set)
- `phones` (PersonPhone set)
- `property_assignments` (PropertyContactAssignment set — defined in properties app)
- `bookings_as_customer`, `enquiries_as_customer`, `quotations_as_customer` (the booking-side `person` FKs on `reservations.Booking` / `Enquiry` / `Quotation`)
- `booking_guests` (`reservations.BookingGuest` set — multi-person bookings)
- `travel_preferences` (`reservations.GuestPreference` set)

Indexes: `(status, last_name, first_name)`, `legacy_id`.

#### Lifecycle

Per `00-conventions.md` "Lifecycle, not soft delete":

- **Wrong person created in error, no relationships yet** — hard delete is permitted. `PropertyContactAssignment.contact` is `PROTECT`, so any person with downstream rows can't be hard-deleted accidentally.
- **Person retired** — set `status=INACTIVE`. Still visible in search results behind a status filter; never opaquely hidden.
- **Duplicate people** — call the explicit service method `Person.merge(target)`: model-agnostically rewrites every FK pointing at `self` (`PropertyContactAssignment`, the booking-side `person` FKs on `Quotation` / `Booking` / `Enquiry`, the agent FKs, `PropertyFinance.contact`, plus `BookingGuest` / `GuestPreference`) to point at `target`, reconciling the `PersonEmail` / `PersonPhone` channel children and the FK-scoped unique constraints (`BookingGuest`, `GuestPreference`) so a blind bulk update can't collide; writes an `AuditLog` summary row; **hard-deletes** `self`. Destructive and final — there is no `merged_into` self-FK and no surviving tombstone. The `AuditLog` is the only trail.
- **GDPR forget-me** — call `Person.anonymize()`: overwrites `first_name`, `last_name`, `company`, `notes`, `address_line_1`, `address_line_2`, `town`, `post_code` with `"[REDACTED]"` or empty; cascades to `PersonEmail.email` (replaced with `"redacted-{id}@anonymized.local"`) and `PersonPhone.number` (replaced with empty string); sets `status=ANONYMIZED`, `anonymized_at=now()`. Row remains for FK integrity on historical assignments, quotations, and bookings. Still searchable by ID. `primary_email()` / `primary_phone()` fail closed (return `None`) for an ANONYMIZED person so the sentinel never leaks to a person-first read or comms send.

Sensitive field edits on `Person` (PII, address, name) are tracked into `AuditLog` via the `core.audit.track(...)` registration in `accounts.apps.ready()`; the erasure flows scrub those cleartext columns from the `AuditLog` trail.

> **Design intent — operator tags + standing linked contacts (owner Loom 2026-06-17).**
> The sales team wants first-class **tags** on the customer (VIP / Repeat / Trade /
> PA / Nick's friend / Nick's network / Disability / Approach-with-care /
> Past-issues / Specific-preferences / Time-waster) and **standing person-to-person
> links** (spouse / child / PA) that persist across bookings — distinct from the
> per-booking `BookingGuest` roles in `05-reservations.md`. Neither exists in the
> model yet; the entity that carries them is the unified **`accounts.Person`**
> (GAP-045, delivered — there is no longer a Guest-vs-Contact split), with the model shape
> and the Repeat-is-derived / PA-overlaps-the-link-role reconciliation settled in
> [`todo/gap-040-customer-tags-taxonomy.md`](todo/done/gap-040-customer-tags-taxonomy.md)
> and [`todo/gap-041-standing-linked-contacts.md`](todo/done/gap-041-standing-linked-contacts.md).
> Sensitive tags (Disability / Approach-with-care) may carry retention/consent
> implications — cross-ref `todo/q-010-guest-data-retention.md`.

### `PersonEmail(TimestampedModel)`
- `contact` — `ForeignKey(Person, on_delete=CASCADE, related_name="emails")` (FK column name retained as `contact` from the legacy table)
- `email` — `CIEmailField` (case-insensitive via `citext`)
- `label` — `TextChoices` (`PRIMARY`, `WORK`, `PERSONAL`, `OTHER`)
- `is_primary` — `BooleanField(default=False)`

Constraints:
- `UniqueConstraint(fields=["contact", "email"], name="unique_contact_email")`
- `UniqueConstraint(fields=["contact"], condition=Q(is_primary=True), name="one_primary_email_per_contact")`

### `PersonPhone(TimestampedModel)`
- `contact` — FK CASCADE (FK column name retained as `contact`)
- `number` — `CharField(max_length=32)` (E.164 recommended but not enforced; admin validation)
- `label` — `TextChoices` (`MOBILE`, `WORK`, `HOME`, `FAX`, `OTHER`)
- `is_primary` — bool

Same unique-primary constraint pattern as `PersonEmail`.

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

How is a `Person` (a CONTACT-kind one — an owner / manager / agent) related to a `Property`? Different concept entirely — referenced from `properties.PropertyContactAssignment`.

> ⚠️ **Taxonomy reconciliation pending — GAP-048.** The owner / legacy / mockup §2.14 set is **Owner / Agent / Villa Admin / Villa Manager / Management Company**. The built enum (below) instead reads `OWNER / MANAGER / AGENT / HOUSEKEEPER / OWNERS_REPRESENTATIVE` — it drops `villa_admin` + `management_company` and adds `housekeeper` + `owners_rep`. GAP-048 re-introduces the two missing roles, records the keep/drop call on housekeeper/owners_rep in `10-decisions.md`, and lets `management_company` point at an `Organisation` (GAP-046), not only a `Person`.

```python
class ContactRole(models.TextChoices):
    OWNER = "owner", "Owner"
    AGENT = "agent", "Agent"
    VILLA_ADMIN = "villa_admin", "Villa Admin"          # GAP-048: re-introduced
    MANAGER = "manager", "Villa Manager"
    MANAGEMENT_COMPANY = "management_company", "Management Company"  # GAP-048: re-introduced
    # Kept-or-dropped pending the GAP-048 / 10-decisions call:
    HOUSEKEEPER = "housekeeper", "Housekeeper"
    OWNERS_REPRESENTATIVE = "owners_rep", "Owner's representative"
```

This is the direct replacement for the legacy `VillaRoles` table (5 static rows: Owner / Agent / Villa Admin / Villa Manager / Management Company), which was FK'd from `VillaContactMap` — i.e. always a contact-to-property mapping role, never a staff-permissions role.

## Why Person is not a User by default

- 90% of people are passive (we email them booking summaries, they don't log in).
- Forcing every Person to be a User creates a username/password row per owner, bloats auth queries, and confuses permissions logic.
- The OneToOne link is opportunistic: if an owner is given a dashboard login, we create the User and set `Person.user = user`.

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
    def verify_code(user, code: str) -> bool:
        """Single-use TOTP check against a raw (user, code) pair (GAP-057).

        Computes the current 30s step, tries (cur-1, cur, cur+1) skipping
        any step <= user.tfa_last_verified_step, and on a pyotp match
        atomically claims that step via a guarded UPDATE
        (WHERE tfa_last_verified_step < step OR IS NULL). A lost race
        (rowcount 0 — a concurrent request already consumed the step)
        rejects. This is the replay guard login previously lacked and the
        refund step-up requires. Recovery codes are NOT accepted here —
        they are a lockout escape hatch, not a money-movement credential.
        """

    @staticmethod
    def challenge(user) -> ChallengeToken:
        """Mint a short-lived challenge token (signed, expires in 5 min)
        that the client posts back with the TOTP code at :verify. Used
        in the post-password, pre-fully-authenticated state."""

    @staticmethod
    def verify(challenge_token: str, code: str) -> User:
        """Validate the TOTP code (or a single-use recovery code) against
        the user resolved from the challenge token. Returns the fully
        authenticated user. The TOTP branch delegates to `verify_code`
        (GAP-057) so login and refund step-up share one replay-guarded
        path; the recovery-code fallback stays login-only. Failed attempts
        increment a rate-limited counter; 5 fails within 5 minutes locks
        2FA for 15 minutes."""

    @staticmethod
    def disable(user, *, actor) -> None:
        """Clear tfa_method back to NONE, blank tfa_secret, null
        tfa_enrolled_at, empty tfa_recovery_codes. Writes an AuditLog
        row. Requires the user's password to be re-entered at the
        API layer (handled in the view, not the service)."""
```

The view dispatchers for `:challenge` / `:verify` / `:enroll` / `:disable` are thin DRF action endpoints that delegate to this service. The endpoint contract is documented in `04-rest-api-surface.md` §2.1 and stays unchanged by this issue.

### Enrolment enforcement (GAP-057)

The mechanism above is enrolment-*optional*. GAP-057 adds a policy layer that can
force every `is_staff=True` user to enrol before they can use the API. See the
`10-decisions.md` Q-008 → GAP-057 row for the decision.

- **`TFA_ENFORCED` settings flag** — `False` in `base` (dev / test / `seed_dev`
  stay ceremony-free), `True` in `production` (staging inherits via
  `from .production import *`). Targeted tests opt in with
  `override_settings(TFA_ENFORCED=True)`. The middleware reads it **per-request**
  (never cached in `__init__`) so the override is honoured.

- **`accounts.middleware.TfaEnforcementMiddleware`** — installed **after**
  `AuthenticationMiddleware` in **both** `base.MIDDLEWARE` and the redefined
  `test.MIDDLEWARE`. It blocks a request with `403`
  `{"code": "tfa_enrollment_required", "detail": …, "field_errors": {}}` (the
  canonical envelope) when **all** hold: `settings.TFA_ENFORCED`,
  `request.user.is_authenticated`, `user.is_staff`, `user.tfa_method == NONE`,
  `request.path.startswith("/api/")`, and the path is not in the allowlist.

  The **`/api/` scope is load-bearing**: without it the middleware would 403 the
  SPA HTML shell and static assets, so the user could never *render*
  `/enroll-2fa`. Django admin (`/admin/`) is therefore **not** enforced —
  acceptable per the "to use the API" scope and necessary for boot.

- **Allowlist** (exact, full `/api/v1/…` paths — the root mounts accounts at
  `/api/v1/`): `auth/csrf`, `auth/login`, `auth/logout`, `auth/me` (FE boot
  probe), `auth/permissions`, `auth/2fa:enroll` — the minimum for a
  logged-in-but-unenrolled user to complete enrolment and nothing else.
  (`auth/2fa:verify` is `AllowAny`, pre-session; unaffected. Note the literal
  `:` verb form and no trailing slash.)

- **`:disable` guard** — `TfaDisableView` returns the same `403`
  `tfa_enrollment_required` payload when enforcement would immediately re-trip
  (enforced + staff), because self-serve disable would be an enforcement bypass.
  The admin `users/{pk}:reset-2fa` escape hatch stays the only way out (lost
  phone → reset → the user funnels back into forced enrolment on the next
  request).

- **`StaffExcludedBasicAuthentication`** (review finding, Unit 2) — DRF's
  `DEFAULT_AUTHENTICATION_CLASSES` include `BasicAuthentication`, which runs at
  the *view* layer, **after** the session-only middleware. Left as stock
  `BasicAuthentication`, an unenrolled staff user could send an HTTP Basic
  header and be authenticated past the middleware (which only saw an
  anonymous session), fully bypassing both enrolment enforcement **and** the
  2FA login challenge. `accounts.authentication.StaffExcludedBasicAuthentication`
  raises `AuthenticationFailed` for any `is_staff` principal, so staff must go
  through the session + 2FA login path; non-staff principals (the owner iCal
  feed) keep Basic auth. Wired via
  `REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]` in `base.py`.

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

## One Person, two kinds (GAP-045)

There is **one** `accounts.Person` human-identity model — there is no separate `Guest` model (it was folded in). `Person.kind` distinguishes the two populations:

- `kind=CUSTOMER` — booking-side people: travellers, payers, CC'd family. Was the deleted `reservations.Guest`.
- `kind=CONTACT` — operator-side CRM people: owners, managers, agents.

`kind` is a directory filter hint (it powers `/contacts?kind=customer`), **not** access control — customer-history reads and agent relations work regardless of `kind`. Both kinds carry `marketing_consent`, the opportunistic `user` OneToOne, and the `PersonEmail` / `PersonPhone` channel children.

Multi-person bookings link a `Booking` to several `Person` rows via `reservations.BookingGuest` (`LEAD` / `CO_TRAVELLER` / `PAYER` / `CC_ONLY`); the LEAD is mirrored onto `Booking.person` for read convenience. See `05-reservations.md`.

### Directory views over the one `Person` (owner Loom 2026-06-29)

The single `Person` identity surfaces in the SPA as **three capacity-scoped directory views**, not three tables:

- **Clients** — `kind=CUSTOMER` **and agent-capacity** people (an agent is a client with a different category, filtered direct-vs-agent — the owner overruled the separate-Agents-page mockup §2.13; see `10-decisions.md`). Carries the client-only **tags** (GAP-040) and tag chip filters (GAP-053). Directory = GAP-047; profile = GAP-042.
- **Suppliers** — operator-side `kind=CONTACT` people with a property role (owner / villa manager / villa admin / management company). Renamed from "Contacts" (GAP-048). Tags do **not** appear here.
- **Companies** — B2B agency `Organisation`s (GAP-046).

A **dual-capacity human** (owner who also rents; agent who books personally) is **one** `Person` appearing in more than one view, with **type badges** (GAP-052) showing every capacity they hold — surface the overlap, don't hide it. Contact **address and notes are operator-editable** on the detail (GAP-052, overturning the GAP-042 display-only call).

## Out of scope here

- Multi-person booking linkage (`BookingGuest`), travel preferences (`GuestPreference`), and the enquiry / quotation / booking `person` FKs — live in `reservations/`; see `05-reservations.md`.
- Property assignment (which people manage which Properties) — lives in `properties/` via `PropertyContactAssignment`.
- Payment / financial recipient mapping — flows through `properties.PropertyFinance.contact`.
