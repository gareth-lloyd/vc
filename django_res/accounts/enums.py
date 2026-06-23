from __future__ import annotations

from django.db import models


class TfaMethod(models.TextChoices):
    NONE = "none", "None"
    TOTP = "totp", "TOTP"
    # SMS reserved for future use; not implemented in MVP.
    SMS = "sms", "SMS (deferred)"


class PersonStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    ANONYMIZED = "anonymized", "Anonymized"


class PersonKind(models.TextChoices):
    """Directory classification: a travelling CUSTOMER (was `reservations.Guest`)
    vs a business CONTACT (owner / manager / agent). A filter hint for the
    `/contacts` directory, not access control — customer-history reads and agent
    relations work regardless. GAP-045 D2."""

    CUSTOMER = "customer", "Customer"
    CONTACT = "contact", "Contact"


class PersonTag(models.TextChoices):
    """Operator-applied flags on a customer record (GAP-040).

    A fixed taxonomy seeded from the 2026-06-17 owner Loom + the New-Quote
    client-block mockup. Stored as an `ArrayField` on `Person.tags`; surfaced as
    at-a-glance chips on the profile / enquiry screens and filterable via
    `?tags=`. "Repeat" is deliberately absent — it's derivable from prior
    bookings and ships as a derived badge in GAP-042, not a manual flag.
    """

    VIP = "vip", "VIP"
    TRADE = "trade", "Trade"
    PA = "pa", "PA"
    NICKS_FRIEND = "nicks_friend", "Nick's friend"
    NICKS_NETWORK = "nicks_network", "Nick's network"
    DISABILITY = "disability", "Disability"
    APPROACH_WITH_CARE = "approach_with_care", "Approach with care"
    PAST_ISSUES = "past_issues", "Past issues"
    SPECIFIC_PREFERENCES = "specific_preferences", "Specific preferences"
    TIME_WASTER = "time_waster", "Time waster"


class PersonPreferredMethod(models.TextChoices):
    EMAIL = "email", "Email"
    PHONE = "phone", "Phone"
    SMS = "sms", "SMS"


class EmailLabel(models.TextChoices):
    PRIMARY = "primary", "Primary"
    WORK = "work", "Work"
    PERSONAL = "personal", "Personal"
    OTHER = "other", "Other"


class PhoneLabel(models.TextChoices):
    MOBILE = "mobile", "Mobile"
    WORK = "work", "Work"
    HOME = "home", "Home"
    FAX = "fax", "Fax"
    OTHER = "other", "Other"


class ContactRole(models.TextChoices):
    OWNER = "owner", "Owner"
    MANAGER = "manager", "Manager"
    AGENT = "agent", "Agent"
    HOUSEKEEPER = "housekeeper", "Housekeeper"
    OWNERS_REPRESENTATIVE = "owners_rep", "Owner's representative"


class OrgType(models.TextChoices):
    """Capacity partition for `accounts.Organisation`: one entity, screens
    scoped by type. AGENCY backs the B2B Companies directory (GAP-046);
    MANAGEMENT_COMPANY surfaces as a property assignee (GAP-048); SUPPLIER
    backs the concierge directory (q-007). GAP-046."""

    AGENCY = "agency", "Agency"
    MANAGEMENT_COMPANY = "mgmt", "Management Company"
    SUPPLIER = "supplier", "Supplier"


class OrgStatus(models.TextChoices):
    """Lifecycle for `accounts.Organisation`. No ANONYMIZED member: an
    organisation is not a GDPR data subject — lifecycle is status + a
    PROTECT-gated hard delete, never soft-delete. GAP-046."""

    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
