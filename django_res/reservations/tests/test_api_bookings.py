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
from properties.enums import CommissionCalcType, PriceBasis
from properties.models import Property, PropertyFinance, PropertySettings
from reservations.enums import BookingStatus, PaymentMethod
from reservations.models import (
    Booking,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)


# A pricing snapshot is the JSON blob the engine writes onto the booking at
# confirmation time (see `pricing.services.engine.PricingEngine.quote`). The
# helper hand-rolls one here so the owner-net tests don't depend on running
# the full engine — the serializer reads the snapshot as-is.
def _snapshot(
    *,
    rate_subtotal: str = "1400.00",
    extras_total: str = "100.00",
    discount: str = "50.00",
    commission: str = "180.00",
    tax: str = "70.00",
) -> dict[str, str]:
    rate = Decimal(rate_subtotal)
    extras = Decimal(extras_total)
    disc = Decimal(discount)
    comm = Decimal(commission)
    tax_amt = Decimal(tax)
    total = rate + extras - disc + comm + tax_amt
    return {
        "rate_subtotal": rate_subtotal,
        "extras_total": extras_total,
        "discount": discount,
        "commission": commission,
        "tax": tax,
        "total": f"{total:.2f}",
    }


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
            cancelled_at=timezone.now(),
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


# ---------------------------------------------------------------------------
# Net-to-owner / prices_entered_as — `09-departures.md` correctness-bug fix.
# Owner-facing booking detail must surface the effective `prices_entered_as`
# flag and a `net_to_owner` breakdown derived from `Booking.pricing_snapshot`
# so the operator UI can label the rate column correctly and render the
# owner statement without recomputing money in the serializer.
# ---------------------------------------------------------------------------


def _set_prices_entered_as(property_: Property, basis: PriceBasis | None) -> None:
    """Pin the property-level `prices_entered_as` value (no group fallback)."""
    settings_, _ = PropertySettings.objects.get_or_create(property=property_)
    settings_.prices_entered_as = basis.value if basis is not None else None
    settings_.save(update_fields=["prices_entered_as"])


@pytest.mark.django_db
def test_owner_booking_summary_renders_net_when_prices_entered_as_net(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """When property basis is NET, owner block exposes the net-to-owner figure.

    `net_to_owner = rate_subtotal + extras_total - discount` (i.e. snapshot
    `total - commission - tax`). The `prices_entered_as` flag rides alongside
    so the UI can label the figure as "rates entered as net".
    """
    booking.pricing_snapshot = _snapshot(
        rate_subtotal="1400.00",
        extras_total="100.00",
        discount="50.00",
        commission="180.00",
        tax="70.00",
    )
    booking.save(update_fields=["pricing_snapshot"])
    _set_prices_entered_as(booking.property, PriceBasis.NET)

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    assert response.data["prices_entered_as"] == PriceBasis.NET.value
    # gross_total = 1400 + 100 - 50 + 180 + 70 = 1700; net = 1700 - 180 - 70 = 1450.
    assert response.data["net_to_owner"] == {
        "currency_code": "GBP",
        "gross_total": "1700.00",
        "commission": "180.00",
        "tax": "70.00",
        "net_to_owner": "1450.00",
    }


@pytest.mark.django_db
def test_owner_booking_summary_renders_gross_when_prices_entered_as_gross(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """GROSS basis: net_to_owner derivation is identical, but the flag differs.

    The owner-net figure is mechanically the same (gross - commission - tax);
    the basis flag is what tells the UI to label the headline rate column
    "rates entered as gross". This pins the contract: the block always
    renders when the snapshot has the numbers, and the flag round-trips.
    """
    booking.pricing_snapshot = _snapshot(
        rate_subtotal="1400.00",
        extras_total="100.00",
        discount="50.00",
        commission="180.00",
        tax="70.00",
    )
    booking.save(update_fields=["pricing_snapshot"])
    _set_prices_entered_as(booking.property, PriceBasis.GROSS)

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    assert response.data["prices_entered_as"] == PriceBasis.GROSS.value
    assert response.data["net_to_owner"]["net_to_owner"] == "1450.00"
    assert response.data["net_to_owner"]["gross_total"] == "1700.00"


@pytest.mark.django_db
def test_owner_booking_summary_resolves_basis_via_group_fallback(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """Property-level NULL `prices_entered_as` falls back to group default."""
    _set_prices_entered_as(booking.property, None)
    group_settings = booking.property.group.settings
    group_settings.prices_entered_as = PriceBasis.NET.value
    group_settings.save(update_fields=["prices_entered_as"])

    booking.pricing_snapshot = _snapshot()
    booking.save(update_fields=["pricing_snapshot"])

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    assert response.data["prices_entered_as"] == PriceBasis.NET.value


@pytest.mark.django_db
def test_owner_booking_summary_net_block_null_when_snapshot_missing(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """A booking with an empty snapshot (legacy import) renders null, not crash."""
    booking.pricing_snapshot = {}
    booking.save(update_fields=["pricing_snapshot"])
    _set_prices_entered_as(booking.property, PriceBasis.NET)

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    assert response.data["net_to_owner"] is None
    assert response.data["prices_entered_as"] == PriceBasis.NET.value


# `PricingEngine.quote` now writes `net_to_owner` directly into the
# `pricing_snapshot` blob, so the serializer's primary path is a plain read.
# Two helpers below cover both shapes: the rebuild-era snapshot carrying the
# explicit key, and the pre-engine-change shape that the serializer must
# still subtract for. Legacy/imported bookings with `snapshot = {}` are
# pinned by the existing `..._null_when_snapshot_missing` test above.
def _snapshot_with_net(
    *,
    rate_subtotal: str = "1400.00",
    extras_total: str = "100.00",
    discount: str = "50.00",
    commission: str = "180.00",
    tax: str = "70.00",
    net_to_owner: str | None = None,
) -> dict[str, str]:
    base = _snapshot(
        rate_subtotal=rate_subtotal,
        extras_total=extras_total,
        discount=discount,
        commission=commission,
        tax=tax,
    )
    if net_to_owner is None:
        total = Decimal(base["total"])
        net_to_owner = f"{(total - Decimal(commission) - Decimal(tax)):.2f}"
    return {**base, "net_to_owner": net_to_owner}


@pytest.mark.django_db
def test_owner_serializer_reads_net_from_snapshot(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """Primary path: snapshot carries `net_to_owner`; serializer reads it verbatim.

    The engine stamps owner-net at quote time, so the serializer must not
    re-derive it. We pin this by writing a snapshot whose stored
    `net_to_owner` deliberately disagrees with `total - commission - tax`;
    the response must echo the stored value, not the subtraction.
    """
    # total = 1700; would-subtract = 1450; we store a different value to
    # prove the serializer reads the snapshot rather than recomputing.
    booking.pricing_snapshot = _snapshot_with_net(net_to_owner="1234.56")
    booking.save(update_fields=["pricing_snapshot"])
    _set_prices_entered_as(booking.property, PriceBasis.NET)

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    assert response.data["net_to_owner"]["net_to_owner"] == "1234.56"
    # Other figures still round-trip from the snapshot unchanged.
    assert response.data["net_to_owner"]["gross_total"] == "1700.00"
    assert response.data["net_to_owner"]["commission"] == "180.00"
    assert response.data["net_to_owner"]["tax"] == "70.00"


@pytest.mark.django_db
def test_owner_serializer_falls_back_to_legacy_math_when_snapshot_missing_net(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """Legacy-snapshot fallback: pre-net_to_owner snapshots still render.

    Snapshots produced before `PricingEngine.quote` started stamping
    `net_to_owner` have only {total, commission, tax}. The serializer
    must subtract `total - commission - tax` so historical bookings don't
    suddenly render `net_to_owner == null` after the engine change.
    """
    # Old-shape snapshot — no `net_to_owner` key.
    booking.pricing_snapshot = _snapshot(
        rate_subtotal="1400.00",
        extras_total="100.00",
        discount="50.00",
        commission="180.00",
        tax="70.00",
    )
    assert "net_to_owner" not in booking.pricing_snapshot
    booking.save(update_fields=["pricing_snapshot"])
    _set_prices_entered_as(booking.property, PriceBasis.NET)

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    # total = 1700; net = 1700 - 180 - 70 = 1450.
    assert response.data["net_to_owner"]["net_to_owner"] == "1450.00"


@pytest.mark.django_db
def test_staff_list_view_still_shows_gross(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """List payload is unchanged: `rental_price` stays gross, no owner block.

    Net-to-owner is detail-only by design; the list endpoint is the
    operator's high-density financial overview and continues to surface
    the gross rental figure column.
    """
    booking.pricing_snapshot = _snapshot()
    booking.save(update_fields=["pricing_snapshot"])
    _set_prices_entered_as(booking.property, PriceBasis.NET)

    api_client.force_login(staff)
    response = api_client.get("/api/v1/bookings")

    assert response.status_code == 200
    row = response.data["results"][0]
    assert "rental_price" in row
    assert "net_to_owner" not in row
    assert "prices_entered_as" not in row


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
