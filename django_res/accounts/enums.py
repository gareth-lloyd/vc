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
