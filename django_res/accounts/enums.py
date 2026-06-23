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


class PersonRelationshipKind(models.TextChoices):
    """Durable person-to-person link types on a customer profile (GAP-041).

    Distinct from per-booking `BookingGuest` trip roles — these persist across
    bookings. A row `(from_person, to_person, kind)` reads "*to_person* is
    *from_person*'s *{kind}*", so the same fact renders with an inverse label on
    the other party's profile (see `RELATIONSHIP_INVERSE_LABEL`).
    """

    SPOUSE = "spouse", "Spouse"
    PARTNER = "partner", "Partner"
    CHILD = "child", "Child"
    PARENT = "parent", "Parent"
    PA = "pa", "PA"
    SIBLING = "sibling", "Sibling"
    OTHER = "other", "Other"


# Reverse-direction display label for a stored kind, used when a relationship is
# rendered on the *to_person*'s profile. Row "(Alice, Bob, PA)" = "Bob is Alice's
# PA"; on Bob's profile Alice shows as his "Principal". Most kinds are
# self-inverse; CHILD↔PARENT swap; PA's inverse ("Principal") is a display-only
# label with no storable kind of its own (you always create the PA direction).
RELATIONSHIP_INVERSE_LABEL: dict[str, str] = {
    PersonRelationshipKind.SPOUSE.value: "Spouse",
    PersonRelationshipKind.PARTNER.value: "Partner",
    PersonRelationshipKind.CHILD.value: "Parent",
    PersonRelationshipKind.PARENT.value: "Child",
    PersonRelationshipKind.PA.value: "Principal",
    PersonRelationshipKind.SIBLING.value: "Sibling",
    PersonRelationshipKind.OTHER.value: "Other",
}

# Storable inverse *kind* for a stored kind — used to detect a "mirror" row (the
# same fact recorded from the other party's side) so we never persist a second
# row that the inverse label was meant to render. Symmetric kinds map to
# themselves; CHILD↔PARENT swap. PA is omitted on purpose: its inverse
# ("Principal") has no storable kind, so the PA direction is the only form and a
# reverse `(Bob, Alice, PA)` is a genuinely different fact (a different person is
# the PA), not a mirror to dedup.
RELATIONSHIP_INVERSE_KIND: dict[str, str] = {
    PersonRelationshipKind.SPOUSE.value: PersonRelationshipKind.SPOUSE.value,
    PersonRelationshipKind.PARTNER.value: PersonRelationshipKind.PARTNER.value,
    PersonRelationshipKind.SIBLING.value: PersonRelationshipKind.SIBLING.value,
    PersonRelationshipKind.OTHER.value: PersonRelationshipKind.OTHER.value,
    PersonRelationshipKind.CHILD.value: PersonRelationshipKind.PARENT.value,
    PersonRelationshipKind.PARENT.value: PersonRelationshipKind.CHILD.value,
}


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
