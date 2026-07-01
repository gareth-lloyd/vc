"""API tests for nested /bookings/{id}/damage-claims (BUG-008 / workflow 8)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from core.tests import assert_max_queries
from pricing.models import Currency
from reservations.enums import BookingStatus, DamageClaimStatus, PaymentMethod
from reservations.models import Booking, DamageClaim, Quotation, QuotationLine, TermsVersion

if TYPE_CHECKING:
    from accounts.models import Person
    from properties.models import Property


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="dc-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def accounts_user(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="dc-accounts@example.com",
        password="x",
        role=StaffRole.ACCOUNTS,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="dc-viewer@example.com",
        password="x",
        role=StaffRole.VIEWER,
    )


@pytest.fixture
def booking(
    db: None,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Booking:
    quotation = Quotation.objects.create(
        enquiry=customer.enquiries_as_customer.create(),
        person=customer,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        person=customer,
        property=property_,
        date_from=line.date_from,
        date_to=line.date_to,
        adults=line.adults,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )


@pytest.mark.django_db
def test_damage_claim_crud(api_client: APIClient, staff: User, booking: Booking) -> None:
    api_client.force_login(staff)

    create = api_client.post(
        f"/api/v1/bookings/{booking.pk}/damage-claims",
        {"amount": "250.00", "description": "Broken window"},
        format="json",
    )
    assert create.status_code == 201, create.data
    claim = DamageClaim.objects.get()
    assert claim.amount == Decimal("250.00")
    assert claim.currency == booking.currency
    # Writes respond with the read representation.
    assert create.data["id"] == claim.pk
    assert create.data["reference"].startswith("DC-")
    assert create.data["currency_code"] == "GBP"
    assert create.data["status"] == DamageClaimStatus.OPEN.value

    listing = api_client.get(f"/api/v1/bookings/{booking.pk}/damage-claims")
    assert listing.data["count"] == 1
    assert listing.data["results"][0]["description"] == "Broken window"

    patch = api_client.patch(
        f"/api/v1/bookings/{booking.pk}/damage-claims/{claim.pk}",
        {"amount": "300.00"},
        format="json",
    )
    assert patch.status_code == 200, patch.data
    assert patch.data["amount"] == "300.00"
    claim.refresh_from_db()
    assert claim.amount == Decimal("300.00")

    delete = api_client.delete(f"/api/v1/bookings/{booking.pk}/damage-claims/{claim.pk}")
    assert delete.status_code == 204
    assert not DamageClaim.objects.exists()


@pytest.mark.django_db
def test_withdraw_action(api_client: APIClient, staff: User, booking: Booking) -> None:
    api_client.force_login(staff)
    create = api_client.post(
        f"/api/v1/bookings/{booking.pk}/damage-claims",
        {"amount": "100.00", "description": "Stain"},
        format="json",
    )
    claim_pk = create.data["id"]

    resp = api_client.post(
        f"/api/v1/bookings/{booking.pk}/damage-claims/{claim_pk}:withdraw",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == DamageClaimStatus.WITHDRAWN.value
    assert DamageClaim.objects.get(pk=claim_pk).status == DamageClaimStatus.WITHDRAWN.value


@pytest.mark.django_db
def test_approve_action(api_client: APIClient, staff: User, booking: Booking) -> None:
    api_client.force_login(staff)
    create = api_client.post(
        f"/api/v1/bookings/{booking.pk}/damage-claims",
        {"amount": "100.00", "description": "Stain"},
        format="json",
    )
    claim_pk = create.data["id"]

    resp = api_client.post(
        f"/api/v1/bookings/{booking.pk}/damage-claims/{claim_pk}:approve",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == DamageClaimStatus.APPROVED.value
    assert DamageClaim.objects.get(pk=claim_pk).status == DamageClaimStatus.APPROVED.value


@pytest.mark.django_db
def test_approve_settled_claim_is_409(
    api_client: APIClient, staff: User, booking: Booking, gbp: Currency
) -> None:
    claim = DamageClaim.objects.create(
        booking=booking,
        currency=gbp,
        amount=Decimal("100.00"),
        description="x",
        status=DamageClaimStatus.SETTLED.value,
    )
    api_client.force_login(staff)

    resp = api_client.post(
        f"/api/v1/bookings/{booking.pk}/damage-claims/{claim.pk}:approve",
    )
    assert resp.status_code == 409, resp.data
    assert resp.data["code"] == "invalid_transition"


@pytest.mark.django_db
def test_approve_viewer_cannot_write(
    api_client: APIClient, viewer: User, booking: Booking, gbp: Currency
) -> None:
    claim = DamageClaim.objects.create(
        booking=booking, currency=gbp, amount=Decimal("100.00"), description="x"
    )
    api_client.force_login(viewer)
    resp = api_client.post(
        f"/api/v1/bookings/{booking.pk}/damage-claims/{claim.pk}:approve",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_approve_accounts_cannot_write(
    api_client: APIClient, accounts_user: User, booking: Booking, gbp: Currency
) -> None:
    claim = DamageClaim.objects.create(
        booking=booking, currency=gbp, amount=Decimal("100.00"), description="x"
    )
    api_client.force_login(accounts_user)
    resp = api_client.post(
        f"/api/v1/bookings/{booking.pk}/damage-claims/{claim.pk}:approve",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_approve_is_scoped_to_booking(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    # A claim on a different booking is not reachable via this booking's URL.
    other = Booking.objects.create(
        quotation_line=QuotationLine.objects.create(
            quotation=Quotation.objects.create(
                enquiry=customer.enquiries_as_customer.create(),
                person=customer,
                expires_at=timezone.now() + timedelta(days=7),
                terms_version=terms,
            ),
            property=property_,
            currency=gbp,
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 8),
            adults=2,
            total=Decimal("1400.00"),
        ),
        person=customer,
        property=property_,
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 8),
        adults=2,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )
    other_claim = DamageClaim.objects.create(
        booking=other, currency=gbp, amount=Decimal("50.00"), description="theirs"
    )
    api_client.force_login(staff)

    resp = api_client.post(
        f"/api/v1/bookings/{booking.pk}/damage-claims/{other_claim.pk}:approve",
    )
    assert resp.status_code == 404
    other_claim.refresh_from_db()
    assert other_claim.status == DamageClaimStatus.OPEN.value


@pytest.mark.django_db
def test_claim_read_embeds_photos(
    api_client: APIClient, staff: User, booking: Booking, gbp: Currency
) -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile

    from reservations.models import DamageClaimPhoto

    claim = DamageClaim.objects.create(
        booking=booking, currency=gbp, amount=Decimal("100.00"), description="x"
    )
    DamageClaimPhoto.objects.create(
        damage_claim=claim,
        image=SimpleUploadedFile("e.jpg", b"bytes", content_type="image/jpeg"),
        caption="cracked tile",
    )
    api_client.force_login(staff)

    resp = api_client.get(f"/api/v1/bookings/{booking.pk}/damage-claims/{claim.pk}")
    assert resp.status_code == 200, resp.data
    assert len(resp.data["photos"]) == 1
    photo = resp.data["photos"][0]
    assert photo["caption"] == "cracked tile"
    assert photo["image_url"].endswith(".jpg")


@pytest.mark.django_db
def test_non_positive_amount_is_a_400(api_client: APIClient, staff: User, booking: Booking) -> None:
    api_client.force_login(staff)
    resp = api_client.post(
        f"/api/v1/bookings/{booking.pk}/damage-claims",
        {"amount": "0.00", "description": "Nope"},
        format="json",
    )
    assert resp.status_code == 400
    assert "amount" in resp.data["field_errors"]
    assert not DamageClaim.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("bad_lines", ["garbage", {"foo": 1}, [{"label": "no amount"}], [42]])
def test_malformed_itemized_lines_rejected(
    api_client: APIClient, staff: User, booking: Booking, bad_lines: object
) -> None:
    api_client.force_login(staff)
    resp = api_client.post(
        f"/api/v1/bookings/{booking.pk}/damage-claims",
        {"amount": "100.00", "description": "x", "itemized_lines": bad_lines},
        format="json",
    )
    assert resp.status_code == 400
    assert "itemized_lines" in resp.data["field_errors"]
    assert not DamageClaim.objects.exists()


@pytest.mark.django_db
def test_valid_itemized_lines_accepted(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    api_client.force_login(staff)
    lines = [{"label": "Sofa", "amount": "60.00"}, {"label": "Rug", "amount": "40.00"}]
    resp = api_client.post(
        f"/api/v1/bookings/{booking.pk}/damage-claims",
        {"amount": "100.00", "description": "Lounge", "itemized_lines": lines},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["itemized_lines"] == lines


@pytest.mark.django_db
def test_viewer_cannot_write(api_client: APIClient, viewer: User, booking: Booking) -> None:
    api_client.force_login(viewer)
    resp = api_client.post(
        f"/api/v1/bookings/{booking.pk}/damage-claims",
        {"amount": "100.00", "description": "x"},
        format="json",
    )
    assert resp.status_code == 403
    # Reads are allowed for any staff.
    assert api_client.get(f"/api/v1/bookings/{booking.pk}/damage-claims").status_code == 200


@pytest.mark.django_db
def test_accounts_role_cannot_write(
    api_client: APIClient, accounts_user: User, booking: Booking
) -> None:
    # Filing a claim is RESERVATIONS-gated; the money move it justifies is the
    # separately accounts-gated SD :claim endpoint.
    api_client.force_login(accounts_user)
    resp = api_client.post(
        f"/api/v1/bookings/{booking.pk}/damage-claims",
        {"amount": "100.00", "description": "x"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_list_is_scoped_to_booking(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    other = Booking.objects.create(
        quotation_line=QuotationLine.objects.create(
            quotation=Quotation.objects.create(
                enquiry=customer.enquiries_as_customer.create(),
                person=customer,
                expires_at=timezone.now() + timedelta(days=7),
                terms_version=terms,
            ),
            property=property_,
            currency=gbp,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 8),
            adults=2,
            total=Decimal("1400.00"),
        ),
        person=customer,
        property=property_,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        adults=2,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )
    DamageClaim.objects.create(
        booking=booking, currency=gbp, amount=Decimal("10.00"), description="mine"
    )
    DamageClaim.objects.create(
        booking=other, currency=gbp, amount=Decimal("20.00"), description="theirs"
    )

    api_client.force_login(staff)
    resp = api_client.get(f"/api/v1/bookings/{booking.pk}/damage-claims")
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["description"] == "mine"


@pytest.mark.django_db
def test_list_query_count_is_pinned(
    api_client: APIClient, staff: User, booking: Booking, gbp: Currency
) -> None:
    for i in range(3):
        DamageClaim.objects.create(
            booking=booking, currency=gbp, amount=Decimal(f"{i + 1}0.00"), description=f"c{i}"
        )
    api_client.force_login(staff)
    # +1 vs the pre-photos pin: a single prefetch_related("photos") query covers
    # the nested DamageClaimPhotoSerializer for the whole page (no N+1).
    with assert_max_queries(7):
        resp = api_client.get(f"/api/v1/bookings/{booking.pk}/damage-claims")
    assert resp.data["count"] == 3
