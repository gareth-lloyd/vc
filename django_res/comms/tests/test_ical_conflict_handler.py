"""An imported iCal block clashing with a live VC booking must alert ops.

`ICalIngestService` fires `ical_conflict_detected` when an imported busy range
overlaps a booking VC already sold. The comms handler turns it into an ops-only
email — but only when `OPS_EMAIL_RECIPIENTS` is configured, and never to the
guest. This asserts a real send against the migration-seeded template.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.test import override_settings

from comms.models import EmailLog, SmtpProfile
from comms.signals import ical_conflict_detected_handler
from properties.models import (
    Country,
    Property,
    PropertyCategory,
    PropertyGroup,
    Region,
)


def _property() -> Property:
    country, _ = Country.objects.get_or_create(
        iso2="GB",
        defaults={"name": "United Kingdom", "iso3": "GBR"},
    )
    region, _ = Region.objects.get_or_create(
        slug="sw-ical-conflict",
        defaults={"country": country, "name": "South West"},
    )
    category, _ = PropertyCategory.objects.get_or_create(slug="villa", defaults={"name": "Villa"})
    group = PropertyGroup.objects.create(name="iCal conflict group")
    return Property.objects.create(
        name="Conflict Villa",
        display_name="Conflict Villa",
        slug="conflict-villa",
        category=category,
        group=group,
        region=region,
    )


class _FakeBooking:
    pk = 4321
    reference = "VC-4321"


@pytest.mark.django_db
@override_settings(OPS_EMAIL_RECIPIENTS=["ops@villacollective.test"])
def test_conflict_emails_ops(system_profile: SmtpProfile) -> None:
    property_ = _property()

    ical_conflict_detected_handler(
        sender=None,
        property=property_,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 8),
        booking=_FakeBooking(),
        feed_labels="Airbnb",
    )

    log = EmailLog.objects.get(template_key="ical.conflict")
    assert log.to == ["ops@villacollective.test"]
    assert "Conflict Villa" in log.rendered_body
    # Booking kind: reference falls back to the booking when not passed explicitly.
    assert "booking" in log.rendered_body
    assert "VC-4321" in log.rendered_body


@pytest.mark.django_db
@override_settings(OPS_EMAIL_RECIPIENTS=["ops@villacollective.test"])
def test_quotation_conflict_emails_ops(system_profile: SmtpProfile) -> None:
    property_ = _property()

    ical_conflict_detected_handler(
        sender=None,
        property=property_,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 8),
        conflict_kind="quotation",
        conflict_reference="QVC-9001",
        booking=None,
        feed_labels="Vrbo",
    )

    log = EmailLog.objects.get(template_key="ical.conflict")
    assert log.to == ["ops@villacollective.test"]
    assert "quotation" in log.rendered_body
    assert "QVC-9001" in log.rendered_body


@pytest.mark.django_db
@override_settings(OPS_EMAIL_RECIPIENTS=["ops@villacollective.test"])
def test_distinct_ranges_are_not_deduped(system_profile: SmtpProfile) -> None:
    """Two materially-different clashes on one property each send their own email.

    The date range is part of the dedupe correlation, so the second send is not
    suppressed as a re-emission of the first.
    """
    property_ = _property()

    ranges = [(date(2026, 9, 1), date(2026, 9, 8)), (date(2026, 10, 1), date(2026, 10, 5))]
    for date_from, date_to in ranges:
        ical_conflict_detected_handler(
            sender=None,
            property=property_,
            date_from=date_from,
            date_to=date_to,
            booking=_FakeBooking(),
            feed_labels="Airbnb",
        )

    assert EmailLog.objects.filter(template_key="ical.conflict").count() == 2


@pytest.mark.django_db
@override_settings(OPS_EMAIL_RECIPIENTS=[])
def test_conflict_without_ops_recipients_sends_nothing(system_profile: SmtpProfile) -> None:
    property_ = _property()

    ical_conflict_detected_handler(
        sender=None,
        property=property_,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 8),
        booking=_FakeBooking(),
        feed_labels="Airbnb",
    )

    assert not EmailLog.objects.filter(template_key="ical.conflict").exists()
