"""API tests for nested /bookings/{id}/damage-claims/{id}/photos (wf8).

The photo pipeline mirrors `PropertyImage` (multipart upload, `image_url` read,
10 MB guard) but double-scopes its queryset by booking *and* claim so a
cross-booking photo delete is impossible (IDOR).
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import TYPE_CHECKING, cast

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from reservations.factories import DamageClaimFactory, make_occupying_booking
from reservations.models import Booking, DamageClaim, DamageClaimPhoto

if TYPE_CHECKING:
    from accounts.models import Person
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import TermsVersion


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="dcp-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def accounts_user(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="dcp-accounts@example.com",
        password="x",
        role=StaffRole.ACCOUNTS,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="dcp-viewer@example.com",
        password="x",
        role=StaffRole.VIEWER,
    )


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


@pytest.fixture
def claim(booking: Booking, gbp: Currency) -> DamageClaim:
    return cast(DamageClaim, DamageClaimFactory(booking=booking, currency=gbp))


def _image(name: str = "evidence.png") -> SimpleUploadedFile:
    # A real, Pillow-decodable PNG so the serializer's ImageField accepts it.
    buf = BytesIO()
    Image.new("RGB", (1, 1)).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _photos_url(booking: Booking, claim: DamageClaim) -> str:
    return f"/api/v1/bookings/{booking.pk}/damage-claims/{claim.pk}/photos"


@pytest.mark.django_db
def test_upload_returns_201_and_image_url(
    api_client: APIClient, staff: User, booking: Booking, claim: DamageClaim
) -> None:
    api_client.force_login(staff)
    resp = api_client.post(
        _photos_url(booking, claim),
        {"image": _image(), "caption": "cracked tile"},
        format="multipart",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["caption"] == "cracked tile"
    assert resp.data["image_url"].endswith(".png")
    photo = DamageClaimPhoto.objects.get()
    assert photo.damage_claim_id == claim.pk


@pytest.mark.django_db
def test_upload_over_max_bytes_is_400(
    api_client: APIClient, staff: User, booking: Booking, claim: DamageClaim, settings: object
) -> None:
    # Shrink the cap rather than fabricating 10 MB of bytes.
    settings.MAX_IMAGE_BYTES = 4  # type: ignore[attr-defined]
    api_client.force_login(staff)
    resp = api_client.post(
        _photos_url(booking, claim),
        {"image": _image()},
        format="multipart",
    )
    assert resp.status_code == 400, resp.data
    assert "image" in resp.data["field_errors"]
    assert not DamageClaimPhoto.objects.exists()


@pytest.mark.django_db
def test_list_is_scoped_to_claim(
    api_client: APIClient, staff: User, booking: Booking, claim: DamageClaim, gbp: Currency
) -> None:
    other_claim = cast(DamageClaim, DamageClaimFactory(booking=booking, currency=gbp))
    DamageClaimPhoto.objects.create(damage_claim=claim, image=_image(), caption="mine")
    DamageClaimPhoto.objects.create(damage_claim=other_claim, image=_image(), caption="theirs")

    api_client.force_login(staff)
    resp = api_client.get(_photos_url(booking, claim))
    assert resp.status_code == 200, resp.data
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["caption"] == "mine"


@pytest.mark.django_db
def test_delete_photo(
    api_client: APIClient, staff: User, booking: Booking, claim: DamageClaim
) -> None:
    photo = DamageClaimPhoto.objects.create(damage_claim=claim, image=_image())
    api_client.force_login(staff)
    resp = api_client.delete(f"{_photos_url(booking, claim)}/{photo.pk}")
    assert resp.status_code == 204
    assert not DamageClaimPhoto.objects.filter(pk=photo.pk).exists()


@pytest.mark.django_db
def test_viewer_can_list_but_not_upload(
    api_client: APIClient, viewer: User, booking: Booking, claim: DamageClaim
) -> None:
    api_client.force_login(viewer)
    # Read is open to any staff.
    assert api_client.get(_photos_url(booking, claim)).status_code == 200
    resp = api_client.post(_photos_url(booking, claim), {"image": _image()}, format="multipart")
    assert resp.status_code == 403
    assert not DamageClaimPhoto.objects.exists()


@pytest.mark.django_db
def test_accounts_can_list_but_not_upload(
    api_client: APIClient, accounts_user: User, booking: Booking, claim: DamageClaim
) -> None:
    api_client.force_login(accounts_user)
    assert api_client.get(_photos_url(booking, claim)).status_code == 200
    resp = api_client.post(_photos_url(booking, claim), {"image": _image()}, format="multipart")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_viewer_cannot_delete(
    api_client: APIClient, viewer: User, booking: Booking, claim: DamageClaim
) -> None:
    photo = DamageClaimPhoto.objects.create(damage_claim=claim, image=_image())
    api_client.force_login(viewer)
    resp = api_client.delete(f"{_photos_url(booking, claim)}/{photo.pk}")
    assert resp.status_code == 403
    assert DamageClaimPhoto.objects.filter(pk=photo.pk).exists()


@pytest.mark.django_db
def test_cross_booking_delete_is_404(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    claim: DamageClaim,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    # A photo belongs to `claim`/`booking`; deleting it through a *different*
    # booking's URL must 404, not silently destroy it (double-scope IDOR guard).
    other_booking = make_occupying_booking(
        property=property_,
        person=customer,
        currency=gbp,
        terms=terms,
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 8),
    )
    photo = DamageClaimPhoto.objects.create(damage_claim=claim, image=_image())
    api_client.force_login(staff)

    resp = api_client.delete(
        f"/api/v1/bookings/{other_booking.pk}/damage-claims/{claim.pk}/photos/{photo.pk}"
    )
    assert resp.status_code == 404
    assert DamageClaimPhoto.objects.filter(pk=photo.pk).exists()
