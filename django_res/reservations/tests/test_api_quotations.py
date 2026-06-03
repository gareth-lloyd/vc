"""API tests for /quotations CRUD + line CRUD + :send + :convert."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from pricing.models import Currency
from properties.enums import PrefilledChangeOverDay
from properties.models import Property
from properties.models.settings import PropertySettings
from reservations.enums import QuotationStatus
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
        email="quo-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def quotation(
    db: None,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
) -> Quotation:
    return Quotation.objects.create(
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )


@pytest.fixture
def line(quotation: Quotation, property_: Property) -> QuotationLine:
    return QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )


@pytest.mark.django_db
def test_list_quotations(api_client: APIClient, staff: User, quotation: Quotation) -> None:
    api_client.force_login(staff)
    response = api_client.get("/api/v1/quotations")

    assert response.status_code == 200
    assert response.data["count"] == 1
    row = response.data["results"][0]
    # Surface human-readable values alongside the FK ids so the FE doesn't
    # display opaque #ids (regression: STAY-style "Guest #64" / "Enquiry #66").
    assert row["guest_name"] == "Ada Lovelace"
    assert row["enquiry_reference"] is None
    assert row["agent_name"] is None


@pytest.mark.django_db
def test_retrieve_quotation_exposes_readable_names(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/quotations/{quotation.pk}")

    assert response.status_code == 200
    assert response.data["guest_name"] == "Ada Lovelace"
    expected_property_name = line.property.display_name or line.property.name
    assert response.data["lines"][0]["property_name"] == expected_property_name


@pytest.mark.django_db
def test_create_quotation(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/quotations",
        {
            "guest": guest.pk,
            "currency": gbp.pk,
            "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            "terms_version": terms.pk,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert Quotation.objects.count() == 1
    # The 201 must echo the *detail* shape (with id + status), not the write
    # serializer — the SPA parses the response as a QuotationDetail and
    # navigates to /quotations/{id} on save.
    created = Quotation.objects.get()
    assert response.data["id"] == created.pk
    assert response.data["status"] == QuotationStatus.DRAFT


@pytest.mark.django_db
def test_retrieve_quotation_includes_lines(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/quotations/{quotation.pk}")

    assert response.status_code == 200
    assert len(response.data["lines"]) == 1
    assert response.data["lines"][0]["id"] == line.pk


@pytest.mark.django_db
def test_send_quotation(api_client: APIClient, staff: User, quotation: Quotation) -> None:
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/quotations/{quotation.pk}:send")

    assert response.status_code == 200
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.SENT.value


@pytest.mark.django_db
def test_duplicate_quotation_clones_lines(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/quotations/{quotation.pk}:duplicate")

    assert response.status_code == 201
    clone_id = response.data["id"]
    assert clone_id != quotation.pk
    assert QuotationLine.objects.filter(quotation_id=clone_id).count() == 1


@pytest.mark.django_db
def test_duplicate_quotation_clones_line_money_and_override_fields(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
) -> None:
    """The clone must carry discount/inclusions and the manual-override fields.

    Dropping `price_override_reason` would leave a cloned manual line that
    can't be PATCHed (the write serializer requires a reason); dropping
    `discount`/`inclusions` silently re-prices and re-reads the clone.
    """
    source = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("900.00"),
        discount=Decimal("125.00"),
        inclusions="Welcome hamper",
        is_manual=True,
        price_override_reason="Repeat guest goodwill",
    )

    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/quotations/{quotation.pk}:duplicate")

    assert response.status_code == 201
    clone = QuotationLine.objects.get(quotation_id=response.data["id"])
    assert clone.pk != source.pk
    assert clone.discount == Decimal("125.00")
    assert clone.inclusions == "Welcome hamper"
    assert clone.is_manual is True
    assert clone.total == Decimal("900.00")
    assert clone.price_override_reason == "Repeat guest goodwill"


@pytest.mark.django_db
def test_lines_crud(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    # rate_rule gives the property a priceable rate so the create/patch
    # repricing path resolves a quote rather than 409-ing on no rates.
    api_client.force_login(staff)

    # Create
    create = api_client.post(
        f"/api/v1/quotations/{quotation.pk}/lines",
        {
            "property": property_.pk,
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 2,
            "children": 0,
        },
        format="json",
    )
    assert create.status_code == 201

    line_pk = QuotationLine.objects.get().pk

    # List
    listing = api_client.get(f"/api/v1/quotations/{quotation.pk}/lines")
    assert listing.status_code == 200
    assert listing.data["count"] == 1

    # Patch
    patch = api_client.patch(
        f"/api/v1/quotations/{quotation.pk}/lines/{line_pk}",
        {"adults": 3},
        format="json",
    )
    assert patch.status_code == 200

    # Delete
    delete = api_client.delete(f"/api/v1/quotations/{quotation.pk}/lines/{line_pk}")
    assert delete.status_code == 204


@pytest.mark.django_db
def test_create_line_prices_via_pricing_engine(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    """A line created via POST is repriced — non-zero total + populated snapshot."""
    api_client.force_login(staff)

    create = api_client.post(
        f"/api/v1/quotations/{quotation.pk}/lines",
        {
            "property": property_.pk,
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 2,
            "children": 0,
        },
        format="json",
    )
    assert create.status_code == 201, create.data

    line = QuotationLine.objects.get()
    # 7 nights @ £200 = £1400.00
    assert line.total == Decimal("1400.00")
    assert line.pricing_snapshot != {}
    # Response echoes the priced values.
    assert Decimal(str(create.data["total"])) == Decimal("1400.00")
    assert create.data["pricing_snapshot"] != {}


@pytest.mark.django_db
def test_create_off_changeover_line_shifts_and_surfaces_dates(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    """Builder line on a Saturday-changeover property: a Wednesday arrival is
    nudged to Saturday, and the create response carries the shifted dates plus
    `changeover_shifted_from` for the "we moved your dates" note (GAP-007)."""
    PropertySettings.objects.create(
        property=property_,
        changeover_day=PrefilledChangeOverDay.SAT.value,
    )
    api_client.force_login(staff)

    create = api_client.post(
        f"/api/v1/quotations/{quotation.pk}/lines",
        {
            "property": property_.pk,
            "date_from": "2026-06-10",  # Wednesday
            "date_to": "2026-06-17",
            "adults": 2,
            "children": 0,
        },
        format="json",
    )
    assert create.status_code == 201, create.data
    assert create.data["date_from"] == "2026-06-13"  # next Saturday
    assert create.data["date_to"] == "2026-06-20"  # nights preserved
    assert create.data["changeover_shifted_from"] == "2026-06-10"

    line = QuotationLine.objects.get()
    assert line.date_from == date(2026, 6, 13)
    assert line.date_to == date(2026, 6, 20)


@pytest.mark.django_db
def test_update_line_reprices(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    """PATCHing a non-manual line reprices it from scratch."""
    api_client.force_login(staff)
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
    )
    assert line.total == Decimal("0")

    patch = api_client.patch(
        f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}",
        {"adults": 3},
        format="json",
    )
    assert patch.status_code == 200, patch.data

    line.refresh_from_db()
    assert line.total == Decimal("1400.00")
    assert line.pricing_snapshot != {}
    assert Decimal(str(patch.data["total"])) == Decimal("1400.00")


@pytest.mark.django_db
def test_manual_line_is_not_repriced(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    """is_manual lines are NOT touched by the pricing engine.

    A manual line honours the operator-supplied total and requires a reason;
    crucially the engine does not stamp it, so its total stays the operator's
    figure rather than the 7-night @ £200 = £1400 engine price.
    """
    api_client.force_login(staff)

    create = api_client.post(
        f"/api/v1/quotations/{quotation.pk}/lines",
        {
            "property": property_.pk,
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 2,
            "children": 0,
            "is_manual": True,
            "total": "750.00",
            "price_override_reason": "Negotiated package rate",
        },
        format="json",
    )
    assert create.status_code == 201, create.data

    line = QuotationLine.objects.get()
    assert line.is_manual is True
    assert line.total == Decimal("750.00")
    assert line.pricing_snapshot == {}


@pytest.mark.django_db
def test_convert_creates_booking(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    quotation.send()
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk},
        format="json",
    )

    assert response.status_code == 201, response.data
    assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_quotation_convert_endpoint_attributes_to_request_user(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """The auto-conversion `EnquiryEvent.actor` must be the request user.

    Bug #5: `QuotationViewSet.convert` called `quotation.accept(line)`
    without `actor=`, so the resulting CONVERTED event was attributed to
    `None` instead of the logged-in operator — the audit trail lost the
    actor for every quote-to-booking conversion via the API.
    """
    from reservations.enums import EnquiryEventKind
    from reservations.models import Enquiry, EnquiryEvent

    enquiry = Enquiry.objects.create(
        guest=guest, email=guest.email, first_name="Ada", last_name="Lovelace"
    )
    quotation = Quotation.objects.create(
        enquiry=enquiry,
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
    quotation.send()
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk},
        format="json",
    )
    assert response.status_code == 201, response.data

    converted_event = EnquiryEvent.objects.get(
        enquiry=enquiry,
        kind=EnquiryEventKind.CONVERTED.value,
    )
    assert converted_event.actor_id == staff.pk


@pytest.mark.django_db
def test_convert_never_rejects_off_changeover_arrival(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    """Convert never 422s on changeover (GAP-007): any shift happened at
    pricing time, so converting succeeds and the booking inherits the line's
    persisted dates."""
    PropertySettings.objects.create(
        property=line.property,
        changeover_day=PrefilledChangeOverDay.SAT.value,
    )
    quotation.send()
    api_client.force_login(staff)

    # 2026-06-10 (line fixture) is a Wednesday; the line was never repriced, so
    # its dates stand and the booking copies them.
    response = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk},
        format="json",
    )
    assert response.status_code == 201, response.data
    assert Booking.objects.count() == 1
    booking = Booking.objects.get()
    assert booking.date_from == line.date_from
    assert booking.date_to == line.date_to


@pytest.mark.django_db
def test_convert_overlap_rolls_back_quotation_acceptance(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """If the booking service raises OverlappingBooking, the quotation must NOT
    be left ACCEPTED — the whole convert is one transaction."""
    from reservations.enums import BookingStatus, PaymentMethod
    from reservations.models import Booking as BookingModel

    # Pre-existing AWAITING_DEPOSIT booking holds 2026-06-10..06-17 on the
    # same property, so converting the overlapping quotation must fail.
    other_quotation = Quotation.objects.create(
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    other_line = QuotationLine.objects.create(
        quotation=other_quotation,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )
    existing = BookingModel.objects.create(
        quotation_line=other_line,
        guest=guest,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
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
    assert existing.status == BookingStatus.AWAITING_DEPOSIT.value

    quotation.send()
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk},
        format="json",
    )

    # Domain error → 409 from canonical_exception_handler.
    assert response.status_code == 409, response.data
    assert response.data["code"] == "overlapping_booking"

    # Quotation must NOT have been left ACCEPTED.
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.SENT.value
    # No second booking created.
    assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_withdraw_quotation(api_client: APIClient, staff: User, quotation: Quotation) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:withdraw",
        {"reason": "guest cancelled"},
        format="json",
    )

    assert response.status_code == 200
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.CANCELLED.value


# ----------------------------------------------------------------------
# Task 1a — :preview + send-time copy overrides
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_preview_returns_html_subject_intro_signoff(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
    property_: Property,
) -> None:
    from reservations.services.quotation_render import DEFAULT_INTRO, DEFAULT_SIGNOFF

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/quotations/{quotation.pk}:preview")

    assert response.status_code == 200, response.data
    assert set(response.data) >= {"html", "subject", "intro", "signoff"}
    assert response.data["subject"] == f"Your quotation {quotation.reference}"
    assert response.data["intro"] == DEFAULT_INTRO
    assert response.data["signoff"] == DEFAULT_SIGNOFF
    expected_name = property_.display_name or property_.name
    assert expected_name in response.data["html"]


@pytest.mark.django_db
def test_preview_applies_query_param_overrides(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    """`:preview` reads subject/intro/signoff from query params so the preview
    reflects the operator's in-flight edits, not just the defaults."""
    api_client.force_login(staff)
    response = api_client.get(
        f"/api/v1/quotations/{quotation.pk}:preview",
        {"subject": "Custom", "intro": "Hello"},
    )

    assert response.status_code == 200, response.data
    assert response.data["subject"] == "Custom"
    assert response.data["intro"] == "Hello"
    assert "Hello" in response.data["html"]


@pytest.mark.django_db
def test_send_applies_subject_and_intro_overrides(
    api_client: APIClient,
    staff: User,
    system_profile: object,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    from comms.management.commands.seed_email_templates import sync_templates
    from comms.models import EmailLog

    sync_templates()
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:send",
        {"subject": "A bespoke subject", "intro": "A bespoke intro paragraph."},
        format="json",
    )
    assert response.status_code == 200, response.data

    log = EmailLog.objects.get(template_key="quotation.sent")
    assert log.rendered_subject == "A bespoke subject"
    assert "A bespoke intro paragraph." in log.rendered_body_html


# ----------------------------------------------------------------------
# Task 2a — hero_image_url + N+1 guard
# ----------------------------------------------------------------------
def _add_hero(property_: Property) -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile

    from properties.enums import ImageKind
    from properties.models import PropertyImage

    PropertyImage.objects.create(
        property=property_,
        kind=ImageKind.HERO,
        image=SimpleUploadedFile("hero.jpg", b"x", content_type="image/jpeg"),
    )


@pytest.mark.django_db
def test_line_serializer_exposes_hero_image_url(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
    property_: Property,
) -> None:
    _add_hero(property_)
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}")
    assert response.status_code == 200
    assert response.data["hero_image_url"] is not None
    assert ".jpg" in response.data["hero_image_url"]


@pytest.mark.django_db
def test_line_serializer_hero_image_url_null_without_hero(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}")
    assert response.status_code == 200
    assert response.data["hero_image_url"] is None


@pytest.mark.django_db
def test_lines_list_constant_query_count(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
) -> None:
    from core.tests import assert_max_queries

    _add_hero(property_)
    for offset in range(4):
        QuotationLine.objects.create(
            quotation=quotation,
            property=property_,
            date_from=date(2026, 6, 10 + offset),
            date_to=date(2026, 6, 17 + offset),
            adults=2,
            total=Decimal("1400.00"),
        )
    api_client.force_login(staff)
    with assert_max_queries(12):
        response = api_client.get(f"/api/v1/quotations/{quotation.pk}/lines")
    assert response.status_code == 200
    assert response.data["count"] == 4


@pytest.mark.django_db
def test_quotation_detail_constant_query_count(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
) -> None:
    from core.tests import assert_max_queries

    _add_hero(property_)
    for offset in range(4):
        QuotationLine.objects.create(
            quotation=quotation,
            property=property_,
            date_from=date(2026, 6, 10 + offset),
            date_to=date(2026, 6, 17 + offset),
            adults=2,
            total=Decimal("1400.00"),
        )
    api_client.force_login(staff)
    with assert_max_queries(12):
        response = api_client.get(f"/api/v1/quotations/{quotation.pk}")
    assert response.status_code == 200
    assert len(response.data["lines"]) == 4


# ----------------------------------------------------------------------
# Task 3 — discount, inclusions, reasoned price override
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_create_line_with_discount_reduces_total(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    api_client.force_login(staff)
    create = api_client.post(
        f"/api/v1/quotations/{quotation.pk}/lines",
        {
            "property": property_.pk,
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 2,
            "children": 0,
            "discount": "150.00",
            "inclusions": "Welcome hamper",
        },
        format="json",
    )
    assert create.status_code == 201, create.data

    line_obj = QuotationLine.objects.get()
    # Gross = 7 nights @ £200 = £1400; net = 1400 - 150 = 1250.
    assert line_obj.total == Decimal("1250.00")
    assert line_obj.discount == Decimal("150.00")
    assert line_obj.inclusions == "Welcome hamper"
    assert create.data["total"] == "1250.00"
    assert create.data["discount"] == "150.00"
    assert create.data["inclusions"] == "Welcome hamper"


@pytest.mark.django_db
def test_discount_clamps_total_at_zero(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    api_client.force_login(staff)
    create = api_client.post(
        f"/api/v1/quotations/{quotation.pk}/lines",
        {
            "property": property_.pk,
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 2,
            "children": 0,
            "discount": "99999.00",
        },
        format="json",
    )
    assert create.status_code == 201, create.data
    assert QuotationLine.objects.get().total == Decimal("0")


@pytest.mark.django_db
def test_negative_discount_rejected(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    """A negative discount must 400, not inflate the total.

    `price_line` computes `total = max(gross - discount, 0)`, so a negative
    discount would charge the guest MORE than the engine price under a label
    that reads as a reduction. Reject it at the field level.
    """
    api_client.force_login(staff)
    create = api_client.post(
        f"/api/v1/quotations/{quotation.pk}/lines",
        {
            "property": property_.pk,
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 2,
            "children": 0,
            "discount": "-500.00",
        },
        format="json",
    )
    assert create.status_code == 400, create.data
    assert "discount" in create.data["field_errors"]
    assert QuotationLine.objects.count() == 0


@pytest.mark.django_db
def test_manual_line_missing_total_is_clean_field_error(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    """A manual line with no/blank total returns a clean 400 field error on
    `total`, not DRF's opaque generic 'A valid number is required.'"""
    api_client.force_login(staff)
    create = api_client.post(
        f"/api/v1/quotations/{quotation.pk}/lines",
        {
            "property": property_.pk,
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 2,
            "children": 0,
            "is_manual": True,
            "price_override_reason": "Negotiated rate",
        },
        format="json",
    )
    assert create.status_code == 400, create.data
    assert "total" in create.data["field_errors"]


@pytest.mark.django_db
def test_manual_line_patch_missing_total_is_clean_field_error(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    line: QuotationLine,
    rate_rule: object,
) -> None:
    """PATCHing a line to is_manual=True with a blank total is a clean 400 on
    `total`, reading is_manual from the body and total fallback from instance."""
    api_client.force_login(staff)
    patch = api_client.patch(
        f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}",
        {"is_manual": True, "total": "", "price_override_reason": "Negotiated rate"},
        format="json",
    )
    assert patch.status_code == 400, patch.data
    assert "total" in patch.data["field_errors"]


@pytest.mark.django_db
def test_manual_line_requires_override_reason(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    api_client.force_login(staff)
    create = api_client.post(
        f"/api/v1/quotations/{quotation.pk}/lines",
        {
            "property": property_.pk,
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 2,
            "children": 0,
            "is_manual": True,
            "total": "999.00",
        },
        format="json",
    )
    assert create.status_code == 400
    assert "price_override_reason" in create.data["field_errors"]


@pytest.mark.django_db
def test_manual_line_with_reason_persists_operator_total(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    api_client.force_login(staff)
    create = api_client.post(
        f"/api/v1/quotations/{quotation.pk}/lines",
        {
            "property": property_.pk,
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 2,
            "children": 0,
            "is_manual": True,
            "total": "999.00",
            "price_override_reason": "Repeat guest goodwill discount",
        },
        format="json",
    )
    assert create.status_code == 201, create.data
    line_obj = QuotationLine.objects.get()
    assert line_obj.is_manual is True
    assert line_obj.total == Decimal("999.00")
    assert line_obj.price_override_reason == "Repeat guest goodwill discount"
    assert create.data["price_override_reason"] == "Repeat guest goodwill discount"


@pytest.mark.django_db
def test_discount_change_writes_audit_log(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    from django.contrib.contenttypes.models import ContentType

    from core.models import AuditLog

    api_client.force_login(staff)
    create = api_client.post(
        f"/api/v1/quotations/{quotation.pk}/lines",
        {
            "property": property_.pk,
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 2,
            "children": 0,
        },
        format="json",
    )
    assert create.status_code == 201, create.data
    line_pk = QuotationLine.objects.get().pk

    patch = api_client.patch(
        f"/api/v1/quotations/{quotation.pk}/lines/{line_pk}",
        {"discount": "200.00"},
        format="json",
    )
    assert patch.status_code == 200, patch.data
    assert patch.data["total"] == "1200.00"

    ct = ContentType.objects.get_for_model(QuotationLine)
    audited = AuditLog.objects.filter(content_type=ct, object_id=str(line_pk))
    assert audited.exists()
    assert any("discount" in row.field_diffs for row in audited)
