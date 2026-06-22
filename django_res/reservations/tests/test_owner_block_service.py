"""Tests for OwnerBlockService: created-approved lifecycle + overlap guards."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, cast

import pytest
from django.utils import timezone

from accounts.factories import UserFactory
from accounts.models import User
from core.exceptions import HoldUnavailable, InvalidTransition, OverlappingBooking
from reservations.enums import (
    BookingHoldReason,
    BookingStatus,
    OwnerBlockKind,
    OwnerBlockStatus,
    OwnerBlockUpdateKind,
    PaymentMethod,
)
from reservations.models import (
    Booking,
    BookingHold,
    OwnerBlockUpdateSeen,
    Quotation,
    QuotationLine,
)
from reservations.services.holds import HoldService
from reservations.services.owner_block import OwnerBlockService
from reservations.signals import owner_block_contested

if TYPE_CHECKING:
    from accounts.models import Person
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import TermsVersion

pytestmark = pytest.mark.django_db

FROM = date(2026, 7, 1)
TO = date(2026, 7, 8)


def _user() -> User:
    return cast(User, UserFactory())


def _booking(
    *,
    property: Property,
    person: Person,
    currency: Currency,
    terms: TermsVersion,
    date_from: date,
    date_to: date,
    status: str,
) -> Booking:
    quotation = Quotation.objects.create(
        enquiry=person.enquiries_as_customer.create(),
        person=person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
        adults=2,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        person=person,
        property=property,
        date_from=date_from,
        date_to=date_to,
        adults=2,
        currency=currency,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        status=status,
    )


def test_create_makes_approved_block_with_indefinite_hold(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_,
        created_by=_user(),
        date_from=FROM,
        date_to=TO,
        kind=OwnerBlockKind.OWNER_STAY.value,
    )
    assert block.status == OwnerBlockStatus.APPROVED.value
    hold = block.resulting_hold
    assert hold is not None
    assert hold.expires_at is None  # indefinite
    assert hold.reason == BookingHoldReason.OWNER_BLOCK.value
    assert hold.is_live() is True


def test_create_maintenance_kind_maps_to_maintenance_reason(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_,
        created_by=_user(),
        date_from=FROM,
        date_to=TO,
        kind=OwnerBlockKind.MAINTENANCE.value,
    )
    assert block.resulting_hold is not None
    assert block.resulting_hold.reason == BookingHoldReason.MAINTENANCE.value


def test_create_rejects_overlapping_booking(
    property_: Property, customer: Person, gbp: Currency, terms: TermsVersion
) -> None:
    _booking(
        property=property_,
        person=customer,
        currency=gbp,
        terms=terms,
        date_from=FROM,
        date_to=TO,
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )
    with pytest.raises(OverlappingBooking):
        OwnerBlockService.create(
            property=property_,
            created_by=_user(),
            date_from=date(2026, 7, 3),
            date_to=date(2026, 7, 10),
        )


def test_create_rejects_overlapping_live_hold(property_: Property) -> None:
    HoldService.place(
        property=property_,
        date_from=FROM,
        date_to=TO,
        reason=BookingHoldReason.OWNER_BLOCK.value,
        never_expires=True,
    )
    with pytest.raises(HoldUnavailable):
        OwnerBlockService.create(
            property=property_,
            created_by=_user(),
            date_from=date(2026, 7, 3),
            date_to=date(2026, 7, 10),
        )


def test_cancel_releases_hold(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_, created_by=_user(), date_from=FROM, date_to=TO
    )
    hold_id = block.resulting_hold_id
    assert hold_id is not None

    OwnerBlockService.cancel(block, actor=_user())
    block.refresh_from_db()
    assert block.status == OwnerBlockStatus.CANCELLED.value
    hold = BookingHold.objects.get(pk=hold_id)
    assert hold.released_at is not None
    assert hold.is_live() is False


def test_cancel_rejects_already_cancelled(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_, created_by=_user(), date_from=FROM, date_to=TO
    )
    OwnerBlockService.cancel(block, actor=_user())
    with pytest.raises(InvalidTransition):
        OwnerBlockService.cancel(block, actor=_user())


# --- feed updates -----------------------------------------------------------


def test_create_appends_created_update(property_: Property) -> None:
    creator = _user()
    block = OwnerBlockService.create(
        property=property_, created_by=creator, date_from=FROM, date_to=TO
    )
    updates = list(block.updates.all())
    assert len(updates) == 1
    assert updates[0].kind == OwnerBlockUpdateKind.CREATED.value
    assert updates[0].actor_id == creator.id


def test_cancel_appends_cancelled_update(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_, created_by=_user(), date_from=FROM, date_to=TO
    )
    canceller = _user()
    OwnerBlockService.cancel(block, actor=canceller)

    kinds = list(block.updates.order_by("created_at").values_list("kind", flat=True))
    assert kinds == [OwnerBlockUpdateKind.CREATED.value, OwnerBlockUpdateKind.CANCELLED.value]
    cancelled = block.updates.get(kind=OwnerBlockUpdateKind.CANCELLED.value)
    assert cancelled.actor_id == canceller.id


# --- contest ----------------------------------------------------------------


def test_contest_flags_block_and_keeps_it_approved(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_, created_by=_user(), date_from=FROM, date_to=TO
    )
    hold_id = block.resulting_hold_id
    assert hold_id is not None
    staff = _user()

    OwnerBlockService.contest(block, actor=staff, reason="Guest enquiry for these dates")
    block.refresh_from_db()

    assert block.status == OwnerBlockStatus.APPROVED.value  # stays approved
    assert block.contested_at is not None
    assert block.contested_by_id == staff.id
    assert block.contest_reason == "Guest enquiry for these dates"
    hold = BookingHold.objects.get(pk=hold_id)
    assert hold.is_live() is True  # the hold is untouched


def test_contest_fires_signal_once(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_, created_by=_user(), date_from=FROM, date_to=TO
    )
    received: list[dict[str, object]] = []

    def _receiver(sender: object, **kwargs: object) -> None:
        received.append(kwargs)

    owner_block_contested.connect(_receiver, dispatch_uid="test.contest")
    try:
        OwnerBlockService.contest(block, actor=_user(), reason="please confirm")
    finally:
        owner_block_contested.disconnect(dispatch_uid="test.contest")

    assert len(received) == 1
    assert received[0]["block"] is block
    assert received[0]["reason"] == "please confirm"


def test_contest_rejects_empty_reason(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_, created_by=_user(), date_from=FROM, date_to=TO
    )
    with pytest.raises(ValueError):
        OwnerBlockService.contest(block, actor=_user(), reason="   ")
    block.refresh_from_db()
    assert block.contested_at is None


def test_contest_rejects_cancelled_block(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_, created_by=_user(), date_from=FROM, date_to=TO
    )
    OwnerBlockService.cancel(block, actor=_user())
    with pytest.raises(InvalidTransition):
        OwnerBlockService.contest(block, actor=_user(), reason="too late")
    block.refresh_from_db()
    assert block.contested_at is None  # a cancelled block cannot be contested


def test_contest_is_idempotent_and_preserves_original(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_, created_by=_user(), date_from=FROM, date_to=TO
    )
    first, second = _user(), _user()
    received: list[dict[str, object]] = []

    def _receiver(sender: object, **kwargs: object) -> None:
        received.append(kwargs)

    owner_block_contested.connect(_receiver, dispatch_uid="test.contest.idem")
    try:
        OwnerBlockService.contest(block, actor=first, reason="original reason")
        OwnerBlockService.contest(block, actor=second, reason="different reason")
    finally:
        owner_block_contested.disconnect(dispatch_uid="test.contest.idem")

    block.refresh_from_db()
    # The second contest is a no-op: the owner is emailed once and the original
    # disputer + reason are preserved.
    assert len(received) == 1
    assert block.contested_by_id == first.id
    assert block.contest_reason == "original reason"


# --- mark_seen --------------------------------------------------------------


def test_mark_seen_is_idempotent_and_per_user(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_, created_by=_user(), date_from=FROM, date_to=TO
    )
    update = block.updates.get()
    alice, bob = _user(), _user()

    OwnerBlockService.mark_seen(update, user=alice)
    OwnerBlockService.mark_seen(update, user=alice)  # idempotent
    assert OwnerBlockUpdateSeen.objects.filter(update=update, user=alice).count() == 1
    # Bob's view is independent — he has not seen it.
    assert not OwnerBlockUpdateSeen.objects.filter(update=update, user=bob).exists()
