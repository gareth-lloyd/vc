"""Tests for the `DamageClaim` model (BUG-008).

Covers the database-allocated reference, the positive-amount constraint, the
status default, and the AuditLog registration — the shape the
`SecurityDeposit.damage_claim` FK relies on.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, cast

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError

from core.audit import get_spec
from core.models import AuditLog
from reservations.enums import DamageClaimStatus
from reservations.factories import DamageClaimFactory, make_occupying_booking
from reservations.models import Booking, DamageClaim, DamageClaimPhoto

if TYPE_CHECKING:
    from accounts.models import Person
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import TermsVersion


@pytest.fixture
def booking(property_: Property, customer: Person, gbp: Currency, terms: TermsVersion) -> Booking:
    return make_occupying_booking(
        property=property_,
        person=customer,
        currency=gbp,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )


@pytest.mark.django_db
def test_reference_is_db_allocated_and_status_defaults_open(
    booking: Booking, gbp: Currency
) -> None:
    claim = DamageClaim.objects.create(
        booking=booking,
        currency=gbp,
        amount=Decimal("250.00"),
        description="Broken bedroom window",
    )
    claim.refresh_from_db()

    assert claim.reference.startswith("DC-")
    assert claim.status == DamageClaimStatus.OPEN.value
    assert str(claim) == claim.reference
    # The itemized_lines scaffold defaults to an empty list, not null.
    assert claim.itemized_lines == []
    # Photos are a real relation now, empty until uploaded.
    assert list(claim.photos.all()) == []


@pytest.mark.django_db
def test_amount_must_be_positive(booking: Booking, gbp: Currency) -> None:
    with pytest.raises(IntegrityError):
        DamageClaim.objects.create(
            booking=booking,
            currency=gbp,
            amount=Decimal("0.00"),
            description="Zero-value claim is not a claim",
        )


@pytest.mark.django_db
def test_factory_builds_a_valid_claim(booking: Booking, gbp: Currency) -> None:
    claim = cast(DamageClaim, DamageClaimFactory(booking=booking, currency=gbp))

    assert claim.pk is not None
    assert claim.booking_id == booking.pk
    assert claim.currency_id == gbp.pk
    assert claim.amount == Decimal("500.00")


@pytest.mark.django_db
def test_status_change_writes_an_audit_row(booking: Booking, gbp: Currency) -> None:
    assert get_spec(DamageClaim) is not None
    claim = DamageClaim.objects.create(
        booking=booking,
        currency=gbp,
        amount=Decimal("100.00"),
        description="Carpet stain",
    )

    claim.status = DamageClaimStatus.APPROVED.value
    claim.save(update_fields=["status"])

    ct = ContentType.objects.get_for_model(DamageClaim)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(claim.pk))
    status_rows = [r for r in rows if "status" in r.field_diffs]
    assert status_rows, "expected an AuditLog row capturing the status change"
    assert status_rows[-1].field_diffs["status"] == [
        DamageClaimStatus.OPEN.value,
        DamageClaimStatus.APPROVED.value,
    ]


# --- DamageClaimPhoto (wf8) ----------------------------------------------------


def _image() -> SimpleUploadedFile:
    return SimpleUploadedFile("evidence.jpg", b"fake-image-bytes", content_type="image/jpeg")


@pytest.mark.django_db
def test_photo_str_and_ordering(booking: Booking, gbp: Currency) -> None:
    claim = cast(DamageClaim, DamageClaimFactory(booking=booking, currency=gbp))
    p1 = DamageClaimPhoto.objects.create(damage_claim=claim, image=_image(), caption="first")
    p2 = DamageClaimPhoto.objects.create(damage_claim=claim, image=_image())

    assert str(p1) == f"Photo #{p1.pk} for damage claim #{claim.pk}"
    # Meta.ordering = [damage_claim_id, id]
    assert list(claim.photos.all()) == [p1, p2]


@pytest.mark.django_db
def test_photo_cascade_deletes_with_claim(booking: Booking, gbp: Currency) -> None:
    claim = cast(DamageClaim, DamageClaimFactory(booking=booking, currency=gbp))
    photo = DamageClaimPhoto.objects.create(damage_claim=claim, image=_image())

    claim.delete()

    assert not DamageClaimPhoto.objects.filter(pk=photo.pk).exists()


@pytest.mark.django_db
def test_photo_is_audited(booking: Booking, gbp: Currency) -> None:
    # Registered for audit (the create row rides pre_save before the pk exists,
    # so it lands with an empty object_id — the convention; the delete row below
    # carries the real pk).
    assert get_spec(DamageClaimPhoto) is not None
    claim = cast(DamageClaim, DamageClaimFactory(booking=booking, currency=gbp))
    photo = DamageClaimPhoto.objects.create(
        damage_claim=claim, image=_image(), caption="broken window"
    )
    photo_pk = photo.pk

    photo.delete()

    ct = ContentType.objects.get_for_model(DamageClaimPhoto)
    delete_rows = AuditLog.objects.filter(content_type=ct, object_id=str(photo_pk))
    assert delete_rows.exists(), "expected an AuditLog row for the photo deletion"
    assert delete_rows.latest("created_at").field_diffs["__deleted__"] is True
