"""GAP-094 — `Booking.house_rules_snapshot` is stamped at confirmation.

"Confirmation" is the transition into AWAITING_DEPOSIT (auto-accept or owner
approval). The snapshot is what the booking contract renders, so a later
edit to the property's house rules must never rewrite what a guest agreed to.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from properties.enums import DescriptionSection
from properties.models import PropertyDescription
from properties.models.settings import PropertySettings
from reservations.enums import BookingStatus
from reservations.serializers import BookingDetailSerializer
from reservations.services.bookings import BookingService

if TYPE_CHECKING:
    from properties.models import Property
    from reservations.models import QuotationLine, TermsVersion


RULES = "No parties. Quiet after 23:00.\nNo smoking indoors."


def _set_house_rules(property_: Property, body: str) -> PropertyDescription:
    return PropertyDescription.objects.update_or_create(
        property=property_,
        section=DescriptionSection.HOUSE_RULES,
        defaults={"body": body},
    )[0]


@pytest.mark.django_db
def test_auto_accept_stamps_house_rules_snapshot(
    quotation_line: QuotationLine, terms: TermsVersion
) -> None:
    _set_house_rules(quotation_line.property, RULES)

    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    booking.refresh_from_db()
    assert booking.status == BookingStatus.AWAITING_DEPOSIT
    assert booking.house_rules_snapshot == RULES


@pytest.mark.django_db
def test_owner_approve_stamps_house_rules_snapshot(
    quotation_line: QuotationLine, terms: TermsVersion
) -> None:
    property_ = quotation_line.property
    PropertySettings.objects.create(property=property_, bookings_require_pre_approval=True)
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    assert booking.status == BookingStatus.PENDING_OWNER_APPROVAL
    assert booking.house_rules_snapshot == ""

    # Rules written *after* creation but *before* approval are the ones agreed.
    _set_house_rules(property_, RULES)
    booking.owner_approve()

    booking.refresh_from_db()
    assert booking.house_rules_snapshot == RULES


@pytest.mark.django_db
def test_snapshot_blank_when_property_has_no_house_rules(
    quotation_line: QuotationLine, terms: TermsVersion
) -> None:
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    booking.refresh_from_db()
    assert booking.status == BookingStatus.AWAITING_DEPOSIT
    assert booking.house_rules_snapshot == ""


@pytest.mark.django_db
def test_editing_property_rules_does_not_change_snapshot(
    quotation_line: QuotationLine, terms: TermsVersion
) -> None:
    desc = _set_house_rules(quotation_line.property, RULES)
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    desc.body = "Parties welcome."
    desc.save()

    booking.refresh_from_db()
    assert booking.house_rules_snapshot == RULES


@pytest.mark.django_db
def test_existing_snapshot_is_never_overwritten_on_transition(
    quotation_line: QuotationLine, terms: TermsVersion
) -> None:
    """Re-entering AWAITING_DEPOSIT must keep the originally agreed text."""
    property_ = quotation_line.property
    PropertySettings.objects.create(property=property_, bookings_require_pre_approval=True)
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    booking.house_rules_snapshot = "AGREED EARLIER"
    booking.save(update_fields=["house_rules_snapshot"])
    _set_house_rules(property_, RULES)

    booking.owner_approve()

    booking.refresh_from_db()
    assert booking.house_rules_snapshot == "AGREED EARLIER"


@pytest.mark.django_db
def test_detail_serializer_exposes_snapshot_read_only(
    quotation_line: QuotationLine, terms: TermsVersion
) -> None:
    _set_house_rules(quotation_line.property, RULES)
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    data = BookingDetailSerializer(booking).data

    assert data["house_rules_snapshot"] == RULES
    assert "house_rules_snapshot" in BookingDetailSerializer.Meta.read_only_fields


@pytest.mark.django_db
def test_migration_backfill_stamps_confirmed_bookings_only(
    quotation_line: QuotationLine, terms: TermsVersion
) -> None:
    """Backfill: confirmed bookings (by status, or by a transition event into
    AWAITING_DEPOSIT) get today's rules; a never-confirmed booking does not."""
    import importlib

    from django.apps import apps

    from reservations.factories import make_occupying_booking
    from reservations.models import Booking, BookingEvent

    backfill = importlib.import_module(
        "reservations.migrations.0010_booking_house_rules_snapshot"
    ).backfill
    property_ = quotation_line.property
    PropertySettings.objects.create(property=property_, bookings_require_pre_approval=True)
    # Never confirmed: created before the rules exist, still pending approval.
    unconfirmed = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    assert unconfirmed.status == BookingStatus.PENDING_OWNER_APPROVAL
    # Confirmed by status only (no events) — the pre-column factory shape.
    by_status = make_occupying_booking(
        property=property_,
        person=unconfirmed.person,
        currency=quotation_line.currency,
        terms=terms,
        date_from=unconfirmed.date_from + timedelta(days=60),
        date_to=unconfirmed.date_to + timedelta(days=60),
    )
    # Confirmed then cancelled: only the event trail says it was confirmed.
    by_event = make_occupying_booking(
        property=property_,
        person=unconfirmed.person,
        currency=quotation_line.currency,
        terms=terms,
        date_from=unconfirmed.date_from + timedelta(days=120),
        date_to=unconfirmed.date_to + timedelta(days=120),
    )
    BookingEvent.objects.create(
        booking=by_event,
        from_status=BookingStatus.PENDING_OWNER_APPROVAL,
        to_status=BookingStatus.AWAITING_DEPOSIT,
    )
    by_event.cancel("changed plans")
    _set_house_rules(property_, RULES)
    # The factory stamps on insert; blank both to simulate pre-column rows.
    Booking.objects.filter(pk__in=[by_status.pk, by_event.pk]).update(house_rules_snapshot="")

    backfill(apps, None)

    unconfirmed.refresh_from_db()
    by_status.refresh_from_db()
    by_event.refresh_from_db()
    assert unconfirmed.house_rules_snapshot == ""
    assert by_status.house_rules_snapshot == RULES
    assert by_event.house_rules_snapshot == RULES
