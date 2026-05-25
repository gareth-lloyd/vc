"""API tests for /bookings — list/detail/patch + state-machine action set."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.enums import EmailLabel, PhoneLabel, StaffRole
from accounts.models import Contact, ContactEmail, ContactPhone, User
from core.tests import assert_max_queries
from pricing.models import Currency, RateRule
from properties.enums import CommissionCalcType
from properties.models import Property, PropertyFinance
from reservations.enums import BookingStatus, PaymentMethod
from reservations.models import (
    Booking,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        email="book-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        email="book-viewer@example.com",
        password="x",
        role=StaffRole.VIEWER,
    )


@pytest.fixture
def booking(
    db: None,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,
) -> Booking:
    quotation = Quotation.objects.create(
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        guest=guest,
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
def test_list_bookings(api_client: APIClient, staff: User, booking: Booking) -> None:
    api_client.force_login(staff)
    response = api_client.get("/api/v1/bookings")

    assert response.status_code == 200
    assert response.data["count"] == 1
    row = response.data["results"][0]
    assert row["reference"] == booking.reference
    assert row["property_name"] == "Test Villa"
    assert row["guest_name"] == "Ada Lovelace"
    # The FE formats money against `currency_code`; the raw FK is also
    # exposed, but the ISO code is what the UI needs.
    assert row["currency_code"] == "GBP"


@pytest.mark.django_db
def test_list_bookings__exclude_terminal_drops_cancelled(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    booking.cancel("test")
    api_client.force_login(staff)

    assert api_client.get("/api/v1/bookings").data["count"] == 1
    assert api_client.get("/api/v1/bookings?exclude_terminal=true").data["count"] == 0


@pytest.mark.django_db
def test_list_bookings__hides_archived_by_default(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    booking.cancel("test")
    booking.archive()
    api_client.force_login(staff)

    response = api_client.get("/api/v1/bookings")
    assert response.data["count"] == 0


@pytest.mark.django_db
def test_archived_listing_returns_archived_bookings(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    booking.cancel("test")
    booking.archive()
    api_client.force_login(staff)

    response = api_client.get("/api/v1/bookings/archived")
    assert response.status_code == 200
    assert response.data["count"] == 1


@pytest.mark.django_db
def test_archived_listing_has_no_n_plus_one(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """`BookingArchiveViewSet.get_queryset` must `select_related` the FKs the
    list serializer walks; without it, each archived row triggers an extra
    SELECT and the steady-state query count grows linearly with row count."""
    quotation = Quotation.objects.create(
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    for offset in range(10):
        line = QuotationLine.objects.create(
            quotation=quotation,
            property=property_,
            date_from=date(2026, 6, 10) + timedelta(days=offset * 30),
            date_to=date(2026, 6, 17) + timedelta(days=offset * 30),
            adults=2,
            total=Decimal("1400.00"),
        )
        archived = Booking.objects.create(
            quotation_line=line,
            guest=guest,
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
            status=BookingStatus.CANCELLED.value,
        )
        archived.is_archived = True
        archived.archived_at = timezone.now()
        archived.save(update_fields=["is_archived", "archived_at"])

    api_client.force_login(staff)
    # Warm any per-test session caches.
    api_client.get("/api/v1/bookings/archived")

    with assert_max_queries(10):
        response = api_client.get("/api/v1/bookings/archived")
    assert response.status_code == 200
    assert response.data["count"] == 10


@pytest.mark.django_db
def test_detail_booking(api_client: APIClient, staff: User, booking: Booking) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")
    assert response.status_code == 200
    assert response.data["reference"] == booking.reference
    assert "pricing_snapshot" in response.data


@pytest.mark.django_db
def test_patch_booking__updates_non_state_fields(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/bookings/{booking.pk}",
        {"site_source": "agent_portal"},
        format="json",
    )
    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.site_source == "agent_portal"


@pytest.mark.django_db
def test_cancel_booking(api_client: APIClient, staff: User, booking: Booking) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}:cancel",
        {"reason": "guest changed plans"},
        format="json",
    )
    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.status == BookingStatus.CANCELLED.value


@pytest.mark.django_db
def test_owner_decline(api_client: APIClient, staff: User, booking: Booking) -> None:
    booking.status = BookingStatus.PENDING_OWNER_APPROVAL.value
    booking.save(update_fields=["status"])
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}:owner-decline",
        {"reason": "calendar conflict"},
        format="json",
    )

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.status == BookingStatus.DECLINED.value


@pytest.mark.django_db
def test_owner_approve(api_client: APIClient, staff: User, booking: Booking) -> None:
    booking.status = BookingStatus.PENDING_OWNER_APPROVAL.value
    booking.save(update_fields=["status"])
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/bookings/{booking.pk}:owner-approve")

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.status == BookingStatus.AWAITING_DEPOSIT.value


@pytest.mark.django_db
def test_modify_guests_recomputes_pricing(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}:modify-guests",
        {"adults": 4, "children": 1, "reason": "extended family"},
        format="json",
    )
    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.adults == 4
    assert booking.children == 1


@pytest.mark.django_db
def test_archive_blocked_on_active_booking(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/bookings/{booking.pk}:archive")

    # AWAITING_DEPOSIT is not terminal — archive raises InvalidTransition → 409.
    assert response.status_code == 409


@pytest.mark.django_db
def test_archive_then_restore_round_trip(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    booking.cancel("test")
    api_client.force_login(staff)

    archive = api_client.post(f"/api/v1/bookings/{booking.pk}:archive")
    assert archive.status_code == 200

    booking.refresh_from_db()
    assert booking.is_archived is True

    restore = api_client.post(f"/api/v1/bookings/{booking.pk}:restore")
    assert restore.status_code == 200

    booking.refresh_from_db()
    assert booking.is_archived is False


@pytest.mark.django_db
def test_activity_returns_event_timeline(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    booking.cancel("test")
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/bookings/{booking.pk}/activity")
    assert response.status_code == 200
    assert any(row["to_status"] == BookingStatus.CANCELLED.value for row in response.data)


@pytest.mark.django_db
def test_viewer_cannot_cancel_booking(
    api_client: APIClient, viewer: User, booking: Booking
) -> None:
    api_client.force_login(viewer)
    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}:cancel",
        {"reason": "viewer attempt"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_bookings_have_no_delete(api_client: APIClient, staff: User, booking: Booking) -> None:
    api_client.force_login(staff)
    response = api_client.delete(f"/api/v1/bookings/{booking.pk}")
    assert response.status_code == 405


# ---------------------------------------------------------------------------
# Owner tab — surfaces `property.finance.contact` + commission terms on detail.
# ---------------------------------------------------------------------------


def _make_owner_contact(
    *,
    first_name: str = "Olivia",
    last_name: str = "Owner",
    company: str = "Owner Holdings Ltd",
    address_line_1: str = "12 Marina Way",
    address_line_2: str = "",
    email: str | None = "olivia@owner.example",
    phone: str | None = "+44 7700 900111",
) -> Contact:
    contact = Contact.objects.create(
        first_name=first_name,
        last_name=last_name,
        company=company,
        address_line_1=address_line_1,
        address_line_2=address_line_2,
    )
    if email is not None:
        ContactEmail.objects.create(
            contact=contact,
            email=email,
            label=EmailLabel.PRIMARY,
            is_primary=True,
        )
    if phone is not None:
        ContactPhone.objects.create(
            contact=contact,
            number=phone,
            label=PhoneLabel.MOBILE,
            is_primary=True,
        )
    return contact


@pytest.mark.django_db
def test_owner_payload_populated_when_finance_and_contact_exist(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    owner = _make_owner_contact()
    PropertyFinance.objects.create(
        property=booking.property,
        contact=owner,
        commission_calculation_type=CommissionCalcType.PERCENT.value,
        commission_amount=Decimal("12.50"),
        commission_note="Includes seasonal uplift",
    )

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    assert response.data["owner"] == {
        "id": owner.pk,
        "first_name": "Olivia",
        "last_name": "Owner",
        "company": "Owner Holdings Ltd",
        "primary_email": "olivia@owner.example",
        "primary_phone": "+44 7700 900111",
        "address_line_1": "12 Marina Way",
        "address_line_2": "",
    }
    assert response.data["commission"] == {
        "calculation_type": "percent",
        "amount": "12.50",
        "note": "Includes seasonal uplift",
    }


@pytest.mark.django_db
def test_owner_primary_email_phone_null_when_no_primary_rows(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    owner = _make_owner_contact(email=None, phone=None)
    PropertyFinance.objects.create(property=booking.property, contact=owner)

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    assert response.data["owner"] is not None
    assert response.data["owner"]["primary_email"] is None
    assert response.data["owner"]["primary_phone"] is None


@pytest.mark.django_db
def test_owner_is_null_when_finance_has_no_contact(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    PropertyFinance.objects.create(
        property=booking.property,
        contact=None,
        commission_calculation_type=CommissionCalcType.FIXED.value,
        commission_amount=Decimal("500.00"),
        commission_note="",
    )

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    assert response.data["owner"] is None
    # Commission still resolves from the property row.
    assert response.data["commission"] == {
        "calculation_type": "fixed",
        "amount": "500.00",
        "note": "",
    }


@pytest.mark.django_db
def test_owner_and_commission_null_when_finance_missing(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    # No PropertyFinance row at all.
    assert not PropertyFinance.objects.filter(property=booking.property).exists()
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    assert response.data["owner"] is None
    assert response.data["commission"] is None


@pytest.mark.django_db
def test_owner_commission_falls_back_to_group_finance(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    # Property finance with everything null on commission — should fall back
    # to GroupFinance, which `properties.signals` auto-creates with defaults.
    PropertyFinance.objects.create(
        property=booking.property,
        contact=None,
        commission_calculation_type=None,
        commission_amount=None,
        commission_note="",
    )
    group_finance = booking.property.group.finance
    group_finance.commission_calculation_type = CommissionCalcType.PERCENT.value
    group_finance.commission_amount = Decimal("8.00")
    group_finance.commission_note = "Group default"
    group_finance.save()

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    assert response.data["commission"] == {
        "calculation_type": "percent",
        "amount": "8.00",
        "note": "Group default",
    }


@pytest.mark.django_db
def test_owner_commission_null_when_group_finance_missing(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """Legacy/imported groups can lack a GroupFinance row. PropertyFinance.
    effective_commission() raises GroupFinance.DoesNotExist when it tries
    the group fallback; the serializer must catch it and return None
    rather than 500.
    """
    PropertyFinance.objects.create(
        property=booking.property,
        contact=None,
        commission_calculation_type=None,
        commission_amount=None,
        commission_note="",
    )
    # Drop the auto-created GroupFinance to simulate the legacy-import case.
    booking.property.group.finance.delete()

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    assert response.data["commission"] is None


@pytest.mark.django_db
def test_owner_commission_note_empty_string_round_trips(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    # An explicit empty string at the property level should overshadow the
    # group default and stay an empty string in the serialized payload —
    # never null.
    PropertyFinance.objects.create(
        property=booking.property,
        contact=None,
        commission_calculation_type=CommissionCalcType.PERCENT.value,
        commission_amount=Decimal("10.00"),
        commission_note="",
    )

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    assert response.data["commission"]["note"] == ""


@pytest.mark.django_db
def test_detail_query_count_bound_with_owner_and_commission(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    owner = _make_owner_contact()
    PropertyFinance.objects.create(
        property=booking.property,
        contact=owner,
        commission_calculation_type=CommissionCalcType.PERCENT.value,
        commission_amount=Decimal("12.50"),
    )
    api_client.force_login(staff)

    with assert_max_queries(14):
        response = api_client.get(f"/api/v1/bookings/{booking.pk}")
    assert response.status_code == 200


@pytest.mark.django_db
def test_notes_crud(api_client: APIClient, staff: User, booking: Booking) -> None:
    api_client.force_login(staff)

    create = api_client.post(
        f"/api/v1/bookings/{booking.pk}/notes",
        {"body": "guest gluten-free", "kind": "concierge"},
        format="json",
    )
    assert create.status_code == 201

    note_id = create.data["id"]

    listing = api_client.get(f"/api/v1/bookings/{booking.pk}/notes")
    assert listing.data["count"] == 1

    patch = api_client.patch(
        f"/api/v1/bookings/{booking.pk}/notes/{note_id}",
        {"is_pinned": True},
        format="json",
    )
    assert patch.status_code == 200
