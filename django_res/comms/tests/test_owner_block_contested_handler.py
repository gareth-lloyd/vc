"""The owner-block contest notification must reach the property's owner.

`OwnerBlockService.contest` fires `owner_block_contested`; the comms handler
turns it into an email. `_safe_send` swallows `EmailTemplateNotFound`, so this
asserts a *real* send against the migration-seeded template — a missing template
would otherwise make the contest silently email no one.
"""

from __future__ import annotations

from datetime import date

import pytest

from accounts.enums import ContactRole
from accounts.models import Person, User
from accounts.models.person import PersonEmail
from comms.models import EmailLog, SmtpProfile
from comms.signals import owner_block_contested_handler
from properties.models import (
    Country,
    Property,
    PropertyCategory,
    PropertyContactAssignment,
    Region,
)
from reservations.models import OwnerBlock


def _property_with_owner(email: str) -> Property:
    country, _ = Country.objects.get_or_create(
        iso2="GB",
        defaults={"name": "United Kingdom", "iso3": "GBR"},
    )
    region, _ = Region.objects.get_or_create(
        slug="sw-contest",
        defaults={"country": country, "name": "South West"},
    )
    category, _ = PropertyCategory.objects.get_or_create(slug="villa", defaults={"name": "Villa"})
    property_ = Property.objects.create(
        name="Contest Villa",
        display_name="Contest Villa",
        slug="contest-villa",
        category=category,
        region=region,
    )
    contact = Person.objects.create(first_name="Olive", last_name="Owner")
    PersonEmail.objects.create(contact=contact, email=email, is_primary=True)
    PropertyContactAssignment.objects.create(
        property=property_,
        contact=contact,
        role=ContactRole.OWNER,
        is_primary=True,
    )
    return property_


@pytest.mark.django_db
def test_contest_emails_the_primary_owner(system_profile: SmtpProfile) -> None:
    property_ = _property_with_owner("olive@example.com")
    creator = User.objects.create_user(email="creator@example.com", password="pw")
    block = OwnerBlock.objects.create(
        property=property_,
        created_by=creator,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 8),
        contest_reason="Guest enquiry",
    )

    owner_block_contested_handler(
        sender=OwnerBlock, block=block, actor=creator, reason="Guest enquiry"
    )

    log = EmailLog.objects.get(template_key="owner_block.contested")
    assert log.to == ["olive@example.com"]
    assert "Contest Villa" in log.rendered_subject
