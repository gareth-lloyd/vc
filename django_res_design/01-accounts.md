# 01 — Accounts

System users (staff login) and contacts (owners, property managers, agents — many never log in).

## Models

### `User(AbstractUser)`
Standard Django auth user, extended:

- Inherits username, email, first_name, last_name, password, is_staff, is_superuser, is_active, date_joined.
- `email` — override to `EmailField(unique=True)`; we authenticate by email in practice.
- `phone` — `CharField(max_length=32, blank=True)`.
- `tfa_method` — `TextChoices` (`NONE`, `TOTP`, `SMS`).
- `tfa_secret` — `CharField(blank=True)` (encrypted at rest; use `django-fernet-fields` or app-layer encryption).
- `last_login_ip` — `GenericIPAddressField(null=True, blank=True)`.
- `role` — fixed `StaffRole` TextChoices (see "Staff roles" below).

`USERNAME_FIELD = "email"`. Use a custom `UserManager` to require email at creation.

Notes:
- SMTP per-user config (`SmtpAddress`/`SmtpPassword` on the legacy `UserMaster`) — drop. System-wide email goes through one SMTP/SES configuration; per-user sending was unused and a security liability.
- `IsSystemAdmin` is just Django's `is_superuser`.
- `IsLock` collapses into `is_active=False`.

### `Contact(AuditedModel)`
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

## Out of scope here

- Guest entity — lives in `reservations/` (a Guest may have an optional User OneToOne — same opportunistic pattern as Contact).
- Property assignment (which Contacts manage which Properties) — lives in `properties/` via `PropertyContactAssignment`.
- Payment / financial recipient mapping — flows through `properties.PropertyFinance.contact`.
