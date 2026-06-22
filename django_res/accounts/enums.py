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
