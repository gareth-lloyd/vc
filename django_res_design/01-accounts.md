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

`USERNAME_FIELD = "email"`. Use a custom `UserManager` to require email at creation.

Notes:
- SMTP per-user config (`SmtpAddress`/`SmtpPassword` on the legacy `UserMaster`) — drop. System-wide email goes through one SMTP/SES configuration; per-user sending was unused and a security liability.
- `IsSystemAdmin` is just Django's `is_superuser`.
- `IsLock` collapses into `is_active=False`.

### `Contact(SoftDeleteModel)`
The villa owner, property manager, or external agent. Distinct from `User` because most contacts never log in. If they do, we link via the optional `user` OneToOne.

- `title` — `CharField(max_length=16, blank=True)` (Mr / Mrs / Dr — free text)
- `first_name`, `last_name` — `CharField`
- `company` — `CharField(blank=True)`
- `website_url` — `URLField(blank=True)`
- `preferred_method` — `TextChoices` (`EMAIL`, `PHONE`, `SMS`) — fixes legacy `PrefferedMethod` typo
- `address_line_1`, `address_line_2` — `CharField(blank=True)`
- `notes` — `TextField(blank=True)`
- `user` — `OneToOneField(User, null=True, blank=True, on_delete=SET_NULL, related_name="contact")` — created lazily if the contact gains login access
- `legacy_id` — nullable, indexed (per 00-conventions)

Reverse relationships:
- `emails` (ContactEmail set)
- `phones` (ContactPhone set)
- `property_assignments` (PropertyContactAssignment set — defined in properties app)

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

`Role` is a fixed `TextChoices` (not a table), referenced from `properties.PropertyContactAssignment`:

```python
class ContactRole(models.TextChoices):
    OWNER = "owner", "Owner"
    MANAGER = "manager", "Manager"
    AGENT = "agent", "Agent"
    HOUSEKEEPER = "housekeeper", "Housekeeper"
    OWNERS_REPRESENTATIVE = "owners_rep", "Owner's representative"
```

The legacy `VillaRole` table existed but the rows were static. If business asks to add custom roles later, swap to a `Role` lookup model and FK; cheap to do, but don't pre-empt it.

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
