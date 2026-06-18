"""API tests for /quotations CRUD + line CRUD + :send + :convert."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from pricing.models import Currency, RateCard, RatePlan, RateRule
from properties.enums import PrefilledChangeOverDay
from properties.models import Property
from properties.models.settings import PropertySettings
from reservations.enums import QuotationStatus
from reservations.models import (
    Booking,
    BookingHold,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)
from reservations.services.person_sync import person_for_guest
from reservations.services.quotations import QuotationService


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
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
    person = person_for_guest(guest)
    return Quotation.objects.create(
        enquiry=guest.enquiries.create(person=person),
        guest=guest,
        person=person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )


@pytest.fixture
def line(quotation: Quotation, property_: Property, gbp: Currency) -> QuotationLine:
    return QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
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
    # Every quotation now has an enquiry (auto-created for agent-direct quotes).
    assert row["enquiry_reference"] == quotation.enquiry.reference
    assert row["agent_name"] is None


@pytest.mark.django_db
def test_list_quotations_excludes_legacy_synthetic_quotations(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
) -> None:
    """SMELL-014: the `/quotations` list is a Quotation-surfacing read, so the
    BookingLoader's `booking-`-prefixed synthetic fill rows (internal artefacts
    that satisfy the QuotationLine PROTECT FK for imported bookings) must never
    reach the operator's list — the viewset routes through `.real()`."""
    assert quotation.guest is not None
    synthetic = Quotation.objects.create(
        enquiry=quotation.guest.enquiries.create(),
        guest=quotation.guest,
        person=person_for_guest(quotation.guest),
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=quotation.terms_version,
        legacy_id="booking-9999",
    )
    api_client.force_login(staff)

    response = api_client.get("/api/v1/quotations")

    assert response.status_code == 200
    refs = {row["reference"] for row in response.data["results"]}
    assert quotation.reference in refs
    assert synthetic.reference not in refs


@pytest.mark.django_db
def test_patch_quotation_with_null_enquiry_keeps_existing(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
) -> None:
    """A PATCH that nulls `enquiry` must not violate the NOT-NULL FK.

    The write serializer allows a null enquiry only so an agent-direct *create*
    can omit it (the view mints one). On update there's always an enquiry — a
    `{"enquiry": null}` body keeps the existing one rather than 500ing on the
    PROTECT/NOT-NULL column.
    """
    api_client.force_login(staff)
    existing_enquiry_id = quotation.enquiry_id

    response = api_client.patch(
        f"/api/v1/quotations/{quotation.pk}",
        {"enquiry": None},
        format="json",
    )

    assert response.status_code == 200, response.data
    quotation.refresh_from_db()
    assert quotation.enquiry_id == existing_enquiry_id


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
def test_duplicate_quotation_places_no_holds(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    """Duplicating a quote never blocks availability — quotes are the soft
    part of the sales process; a hold is a separate, deliberate operator
    action on a line."""
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/quotations/{quotation.pk}:duplicate")
    assert response.status_code == 201

    assert QuotationLine.objects.filter(quotation_id=response.data["id"]).count() == 1
    assert BookingHold.objects.count() == 0


@pytest.mark.django_db
def test_withdraw_releases_holds(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    """Withdrawing (cancelling) a quote frees its held dates immediately rather
    than leaving the villa blocked until the hold's natural expiry."""
    api_client.force_login(staff)
    api_client.post(
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
    # Holds are manual now — place one on the line the way an operator would.
    QuotationService.hold_line(QuotationLine.objects.get(quotation=quotation))
    assert BookingHold.objects.filter(quotation=quotation, released_at__isnull=True).count() == 1

    withdraw = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:withdraw",
        {"reason": "guest cancelled"},
        format="json",
    )
    assert withdraw.status_code == 200

    assert not BookingHold.objects.filter(quotation=quotation, released_at__isnull=True).exists()
    assert not BookingHold.live_overlapping(
        property=property_, date_from=date(2026, 6, 10), date_to=date(2026, 6, 17)
    ).exists()


@pytest.mark.django_db
def test_duplicate_quotation_clones_line_money_and_override_fields(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    gbp: Currency,
) -> None:
    """The clone must carry discount/inclusions and the manual-override fields.

    Dropping `price_override_reason` would leave a cloned manual line that
    can't be PATCHed (the write serializer requires a reason); dropping
    `discount`/`inclusions` silently re-prices and re-reads the clone.
    """
    source = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
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
    gbp: Currency,
) -> None:
    """PATCHing a non-manual line reprices it from scratch."""
    api_client.force_login(staff)
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
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


def _priced_plan_in(
    property_: Property, currency: Currency, effective_from: date, nightly: str
) -> RatePlan:
    plan = RatePlan.objects.create(
        property=property_,
        name=f"{currency.code} plan",
        currency=currency,
        effective_from=effective_from,
        effective_to=date(2026, 12, 31),
    )
    card = RateCard.objects.create(plan=plan, name="Default", sort_order=0)
    RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal(nightly),
    )
    return plan


@pytest.mark.django_db
def test_patch_pins_currency_against_a_newer_plan_in_another_currency(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
    gbp: Currency,
) -> None:
    """An edit must never silently re-denominate a priced line (GAP-014 /
    FG-001): after the villa activates a newer EUR plan, a notes-style PATCH
    repriced WITHOUT a pin would flip the line to EUR — the pin exact-matches
    the line's own GBP instead."""
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
    assert line.currency == gbp

    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    # Newer effective_from — an unpinned reprice would prefer this plan.
    _priced_plan_in(property_, eur, date(2026, 2, 1), "300.00")

    patch = api_client.patch(
        f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}",
        {"adults": 3},
        format="json",
    )
    assert patch.status_code == 200, patch.data
    line.refresh_from_db()
    assert line.currency == gbp
    assert line.total == Decimal("1400.00")


@pytest.mark.django_db
def test_patch_fails_loud_when_pinned_currency_no_longer_priceable(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
    plan: RatePlan,
    gbp: Currency,
) -> None:
    """If the villa's plan currency switched outright, a reprice of an
    existing line raises instead of silently changing what the guest pays in."""
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

    plan.is_active = False
    plan.save(update_fields=["is_active"])
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    _priced_plan_in(property_, eur, date(2026, 2, 1), "300.00")

    patch = api_client.patch(
        f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}",
        {"adults": 3},
        format="json",
    )
    assert patch.status_code == 409, patch.data
    line.refresh_from_db()
    assert line.currency == gbp  # unchanged — the failed reprice rolled back


# ---------------------------------------------------------------------------
# Inclusion seeding — a created line with blank `inclusions` is seeded from
# the winning plan's `inclusion` text (legacy ResService.cs:1241 seeded line
# inclusions from the season). Seeding happens at CREATION only: an operator
# who deliberately blanks the field must not have text resurrected by a
# date/party edit's reprice.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_line_seeds_inclusions_from_winning_plan(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
    plan: RatePlan,
) -> None:
    plan.inclusion = "Daily maid service, pool heating"
    plan.save(update_fields=["inclusion"])
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
    assert line.inclusions == "Daily maid service, pool heating"
    assert create.data["inclusions"] == "Daily maid service, pool heating"


@pytest.mark.django_db
def test_create_line_keeps_operator_supplied_inclusions(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
    plan: RatePlan,
) -> None:
    plan.inclusion = "Daily maid service"
    plan.save(update_fields=["inclusion"])
    api_client.force_login(staff)

    create = api_client.post(
        f"/api/v1/quotations/{quotation.pk}/lines",
        {
            "property": property_.pk,
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 2,
            "children": 0,
            "inclusions": "Welcome hamper only",
        },
        format="json",
    )

    assert create.status_code == 201, create.data
    line = QuotationLine.objects.get()
    assert line.inclusions == "Welcome hamper only"


@pytest.mark.django_db
def test_reprice_does_not_resurrect_blanked_inclusions(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
    plan: RatePlan,
) -> None:
    """An edit that triggers a reprice must not re-seed a deliberately
    blanked `inclusions` from the plan."""
    plan.inclusion = "Daily maid service"
    plan.save(update_fields=["inclusion"])
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
    assert line.inclusions == "Daily maid service"

    patch = api_client.patch(
        f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}",
        {"inclusions": "", "adults": 3},
        format="json",
    )

    assert patch.status_code == 200, patch.data
    line.refresh_from_db()
    assert line.inclusions == ""


@pytest.mark.django_db
def test_manual_line_inclusions_not_seeded(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
    plan: RatePlan,
) -> None:
    """Manual lines skip the engine, so there is no winning plan to seed from."""
    plan.inclusion = "Daily maid service"
    plan.save(update_fields=["inclusion"])
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
    assert line.inclusions == ""


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
def test_create_line_places_no_hold(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    """A line built through the UI (POST /lines) never blocks availability —
    quoting is the soft part of the sales process; holds are a separate,
    deliberate operator action."""
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

    assert QuotationLine.objects.count() == 1
    assert BookingHold.objects.count() == 0


@pytest.mark.django_db
def test_create_line_succeeds_over_foreign_live_hold(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    """Quoting dates someone else holds is allowed — a quote is an offer, not
    a claim on inventory. The conflict only surfaces if/when an operator
    tries to HOLD or BOOK the line."""
    from reservations.services.holds import HoldService

    HoldService.place(
        property=property_,
        date_from=date(2026, 6, 12),
        date_to=date(2026, 6, 15),
        never_expires=True,
    )
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


@pytest.mark.django_db
def test_update_line_moves_its_hold(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    """PATCHing a held line's dates moves its single hold rather than
    orphaning the old one or creating a second — and the operator-set expiry
    survives the move."""
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
    placed = QuotationService.hold_line(line)
    original_expiry = placed.expires_at

    patch = api_client.patch(
        f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}",
        {"date_from": "2026-06-12", "date_to": "2026-06-19"},
        format="json",
    )
    assert patch.status_code == 200, patch.data

    # Exactly one hold, relocated to the new range, expiry untouched.
    hold = BookingHold.objects.get(quotation=quotation)
    assert hold.quotation_line_id == line.pk
    assert hold.date_from == date(2026, 6, 12)
    assert hold.date_to == date(2026, 6, 19)
    assert hold.expires_at == original_expiry
    assert hold.is_live() is True


@pytest.mark.django_db
def test_update_unheld_line_stays_unheld(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    """Editing a line that has no hold must not conjure one up."""
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
        {"date_from": "2026-06-12", "date_to": "2026-06-19"},
        format="json",
    )
    assert patch.status_code == 200, patch.data
    assert BookingHold.objects.count() == 0


@pytest.mark.django_db
def test_delete_line_releases_its_hold(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    """DELETEing a line releases its hold so the dates free up on the calendar."""
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
    QuotationService.hold_line(QuotationLine.objects.get())

    delete = api_client.delete(f"/api/v1/quotations/{quotation.pk}/lines/{line_pk}")
    assert delete.status_code == 204

    # The hold survives (history) but is released — no longer live, frees dates.
    hold = BookingHold.objects.get(quotation=quotation)
    assert hold.released_at is not None
    assert hold.is_live() is False
    assert not BookingHold.live_overlapping(
        property=property_, date_from=date(2026, 6, 10), date_to=date(2026, 6, 17)
    ).exists()


@pytest.mark.django_db
def test_hold_line_endpoint_places_hold(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    """POST :hold places a QUOTATION_OPEN hold on the line's dates and echoes
    the line with its `hold` populated."""
    from reservations.enums import BookingHoldReason

    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}:hold")
    assert response.status_code == 200, response.data

    hold = BookingHold.objects.get(quotation_line=line)
    assert hold.reason == BookingHoldReason.QUOTATION_OPEN.value
    assert hold.quotation_id == quotation.pk
    assert hold.date_from == line.date_from
    assert hold.date_to == line.date_to
    assert hold.is_live() is True
    # Expiry comes from the property's effective setting, not the quotation.
    assert hold.expires_at is not None
    assert hold.expires_at != quotation.expires_at

    assert response.data["hold"] is not None
    assert response.data["hold"]["id"] == hold.pk
    assert response.data["hold"]["expires_at"] is not None


@pytest.mark.django_db
def test_hold_line_endpoint_is_idempotent(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    api_client.force_login(staff)
    first = api_client.post(f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}:hold")
    second = api_client.post(f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}:hold")

    assert first.status_code == second.status_code == 200
    assert first.data["hold"]["id"] == second.data["hold"]["id"]
    assert BookingHold.objects.count() == 1


@pytest.mark.django_db
def test_hold_line_endpoint_conflict_is_409(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
    property_: Property,
) -> None:
    """Held-by-someone-else dates 409 with the operator-facing message."""
    from reservations.services.holds import HoldService

    HoldService.place(
        property=property_,
        date_from=date(2026, 6, 12),
        date_to=date(2026, 6, 15),
        never_expires=True,
    )
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}:hold")
    assert response.status_code == 409, response.data
    assert response.data["code"] == "hold_unavailable"
    assert "already held" in response.data["detail"]
    assert not BookingHold.objects.filter(quotation_line=line).exists()


@pytest.mark.django_db
def test_hold_line_endpoint_locked_quotation_is_409(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    """A cancelled/expired quote can't gain new holds."""
    quotation.cancel(reason="guest went elsewhere")
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}:hold")
    assert response.status_code == 409, response.data
    assert response.data["code"] == "quotation_locked"
    assert BookingHold.objects.count() == 0


@pytest.mark.django_db
def test_release_hold_endpoint_releases_and_is_idempotent(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    api_client.force_login(staff)
    QuotationService.hold_line(line)

    release = api_client.post(f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}:release-hold")
    assert release.status_code == 200, release.data
    assert release.data["hold"] is None
    hold = BookingHold.objects.get(quotation_line=line)
    assert hold.released_at is not None

    again = api_client.post(f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}:release-hold")
    assert again.status_code == 200
    assert again.data["hold"] is None


@pytest.mark.django_db
def test_release_hold_allowed_on_expired_quotation(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    """Releasing inventory must always be possible — a hold may outlive its
    quotation (own expiry), so :release-hold is NOT status-guarded."""
    QuotationService.hold_line(line)
    quotation.send()
    quotation.expire()
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}:release-hold")
    assert response.status_code == 200, response.data
    assert not BookingHold.objects.filter(quotation_line=line, released_at__isnull=True).exists()


@pytest.mark.django_db
def test_hold_endpoints_require_reservations_role(
    api_client: APIClient,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    viewer = User.objects.create_user(
        is_staff=True,
        email="quo-viewer@example.com",
        password="x",
    )
    api_client.force_login(viewer)

    held = api_client.post(f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}:hold")
    released = api_client.post(f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}:release-hold")
    assert held.status_code == 403
    assert released.status_code == 403
    assert BookingHold.objects.count() == 0


@pytest.mark.django_db
def test_line_serializer_hold_is_null_when_expired_but_unreaped(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    """A hold past its expiry but not yet swept by the beat task must not
    render a stale "Held until" in the UI."""
    hold = QuotationService.hold_line(line)
    hold.expires_at = timezone.now() - timedelta(minutes=1)
    hold.save(update_fields=["expires_at"])
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}")
    assert response.status_code == 200
    assert response.data["hold"] is None


@pytest.mark.django_db
def test_convert_releases_manual_hold(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    """Booking a line releases every hold on the quotation — the quote is
    settled, the booking row itself now occupies the dates."""
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
    QuotationService.hold_line(line)
    quotation.send()

    convert = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk, "terms_accepted": True},
        format="json",
    )
    assert convert.status_code == 201, convert.data
    assert not BookingHold.objects.filter(quotation=quotation, released_at__isnull=True).exists()


@pytest.mark.django_db
def test_convert_refused_over_foreign_live_hold(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    """With quoting no longer auto-holding its dates, another party may have
    held the villa between quote and accept — convert must refuse rather
    than book straight over a live hold, and the acceptance must roll back."""
    from reservations.services.holds import HoldService

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
    quotation.send()
    HoldService.place(
        property=property_,
        date_from=date(2026, 6, 12),
        date_to=date(2026, 6, 15),
        never_expires=True,
    )

    convert = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk, "terms_accepted": True},
        format="json",
    )
    assert convert.status_code == 409, convert.data
    assert convert.data["code"] == "hold_unavailable"
    assert Booking.objects.count() == 0
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.SENT.value


@pytest.mark.django_db
def test_convert_succeeds_over_own_quotation_hold(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    rate_rule: object,
) -> None:
    """The quotation's own line hold must never block its own conversion."""
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
    QuotationService.hold_line(line)
    quotation.send()

    convert = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk, "terms_accepted": True},
        format="json",
    )
    assert convert.status_code == 201, convert.data


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
        {"line": line.pk, "terms_accepted": True},
        format="json",
    )

    assert response.status_code == 201, response.data
    assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_convert_without_terms_accepted_400s(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    """Converting requires the explicit `terms_accepted: true` signal (SMELL-006).

    `terms_accepted_at` is stamped server-side from that signal — a request
    that omits it (or sends false) must fail with a domain-meaningful error,
    not mint a booking.
    """
    quotation.send()
    api_client.force_login(staff)

    for body in ({"line": line.pk}, {"line": line.pk, "terms_accepted": False}):
        response = api_client.post(
            f"/api/v1/quotations/{quotation.pk}:convert",
            body,
            format="json",
        )
        assert response.status_code == 400, response.data
        assert response.data["code"] == "terms_not_accepted"

    assert Booking.objects.count() == 0
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.SENT


@pytest.mark.django_db
def test_convert_stamps_terms_accepted_at_server_side(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    quotation.send()
    api_client.force_login(staff)
    before = timezone.now()

    response = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk, "terms_accepted": True},
        format="json",
    )

    assert response.status_code == 201, response.data
    booking = Booking.objects.get()
    assert before <= booking.terms_accepted_at <= timezone.now()


@pytest.mark.django_db
def test_convert_schedules_payments_on_booking(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    """A booking created via the accept-quotation API arrives with its payment
    schedule attached — the bug this regression pins was an empty ledger on
    every API-created booking."""
    from payments.enums import PaymentPurpose
    from payments.models import Payment
    from properties.models.finance import PropertyFinance

    # All-null finance row inherits the group's default deposit policy.
    PropertyFinance.objects.get_or_create(property=line.property)
    quotation.send()
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk, "terms_accepted": True},
        format="json",
    )

    assert response.status_code == 201, response.data
    booking_id = response.data["id"]
    purposes = set(Payment.objects.filter(booking_id=booking_id).values_list("purpose", flat=True))
    assert PaymentPurpose.DEPOSIT.value in purposes
    assert PaymentPurpose.BALANCE.value in purposes


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

    person = person_for_guest(guest)
    enquiry = Enquiry.objects.create(
        guest=guest,
        person=person,
        email=guest.email or "",
        first_name="Ada",
        last_name="Lovelace",
    )
    quotation = Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
        person=person,
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
    quotation.send()
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk, "terms_accepted": True},
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
        {"line": line.pk, "terms_accepted": True},
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
    person = person_for_guest(guest)
    other_quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        person=person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    other_line = QuotationLine.objects.create(
        quotation=other_quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )
    existing = BookingModel.objects.create(
        quotation_line=other_line,
        guest=guest,
        person=person,
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
        {"line": line.pk, "terms_accepted": True},
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
    gbp: Currency,
) -> None:
    from core.tests import assert_max_queries

    _add_hero(property_)
    for offset in range(4):
        QuotationLine.objects.create(
            quotation=quotation,
            property=property_,
            currency=gbp,
            date_from=date(2026, 6, 10 + offset),
            date_to=date(2026, 6, 17 + offset),
            adults=2,
            total=Decimal("1400.00"),
        )
    # One held line — the `hold` field must come from the prefetch, not a
    # per-row query.
    QuotationService.hold_line(QuotationLine.objects.order_by("pk")[0])
    api_client.force_login(staff)
    with assert_max_queries(13):
        response = api_client.get(f"/api/v1/quotations/{quotation.pk}/lines")
    assert response.status_code == 200
    assert response.data["count"] == 4
    holds = [row["hold"] for row in response.data["results"]]
    assert sum(1 for h in holds if h is not None) == 1


@pytest.mark.django_db
def test_quotation_detail_constant_query_count(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
    gbp: Currency,
) -> None:
    from core.tests import assert_max_queries

    _add_hero(property_)
    for offset in range(4):
        QuotationLine.objects.create(
            quotation=quotation,
            property=property_,
            currency=gbp,
            date_from=date(2026, 6, 10 + offset),
            date_to=date(2026, 6, 17 + offset),
            adults=2,
            total=Decimal("1400.00"),
        )
    QuotationService.hold_line(QuotationLine.objects.order_by("pk")[0])
    api_client.force_login(staff)
    with assert_max_queries(13):
        response = api_client.get(f"/api/v1/quotations/{quotation.pk}")
    assert response.status_code == 200
    assert len(response.data["lines"]) == 4
    assert sum(1 for row in response.data["lines"] if row["hold"] is not None) == 1


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


# ---------------------------------------------------------------------------
# Atomic create — POST /quotations with nested `lines` (header + lines +
# pricing + holds, all-or-nothing). The header-then-lines two-step left a
# half-populated draft when a line POST failed mid-fan-out.
# ---------------------------------------------------------------------------


def _second_property(template: Property) -> Property:
    """A sibling villa on the same graph, for multi-line quotes."""
    from properties.models import Property as PropertyModel

    return PropertyModel.objects.create(
        name="Second Villa",
        display_name="Second Villa",
        slug="second-villa",
        category=template.category,
        group=template.group,
        region=template.region,
    )


@pytest.mark.django_db
def test_create_quotation_with_lines_atomic_happy_path(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    terms: TermsVersion,
    property_: Property,
    rate_rule: object,
) -> None:
    """One POST creates header + a priced and a manual line — no holds — and
    echoes the detail shape with the server-priced values."""
    api_client.force_login(staff)
    enquiry = guest.enquiries.create()
    status_before = enquiry.status
    second = _second_property(property_)

    response = api_client.post(
        "/api/v1/quotations",
        {
            "enquiry": enquiry.pk,
            "guest": guest.pk,
            "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            "terms_version": terms.pk,
            "lines": [
                {
                    "property": property_.pk,
                    "date_from": "2026-06-10",
                    "date_to": "2026-06-17",
                    "adults": 2,
                    "children": 0,
                },
                {
                    "property": second.pk,
                    "date_from": "2026-06-10",
                    "date_to": "2026-06-17",
                    "adults": 2,
                    "children": 0,
                    "is_manual": True,
                    "total": "5000.00",
                    "price_override_reason": "Agreed rate",
                    "currency": "GBP",
                },
            ],
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    quotation = Quotation.objects.get()
    assert response.data["id"] == quotation.pk
    assert response.data["status"] == QuotationStatus.DRAFT
    lines = response.data["lines"]
    assert len(lines) == 2
    priced = next(row for row in lines if not row["is_manual"])
    manual = next(row for row in lines if row["is_manual"])
    # 7 nights @ £200 = £1400, engine-priced with a populated snapshot.
    assert Decimal(str(priced["total"])) == Decimal("1400.00")
    assert priced["pricing_snapshot"] != {}
    # Manual line keeps the operator total and its pinned currency.
    assert Decimal(str(manual["total"])) == Decimal("5000.00")
    assert manual["currency"] == "GBP"
    # Saving a quote never blocks availability — holds are manual.
    assert BookingHold.objects.filter(quotation=quotation).count() == 0
    # Saving a draft is not sending: the enquiry must NOT advance to QUOTED
    # (that transition belongs to :send / :mark-manually-sent).
    enquiry.refresh_from_db()
    assert enquiry.status == status_before


@pytest.mark.django_db
def test_create_with_lines_invalid_line_is_nested_400_and_writes_nothing(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    terms: TermsVersion,
    property_: Property,
    rate_rule: object,
) -> None:
    api_client.force_login(staff)
    enquiry = guest.enquiries.create()
    second = _second_property(property_)

    response = api_client.post(
        "/api/v1/quotations",
        {
            "enquiry": enquiry.pk,
            "guest": guest.pk,
            "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            "terms_version": terms.pk,
            "lines": [
                {
                    "property": property_.pk,
                    "date_from": "2026-06-10",
                    "date_to": "2026-06-17",
                    "adults": 2,
                    "children": 0,
                },
                # Manual line with no override reason — invalid.
                {
                    "property": second.pk,
                    "date_from": "2026-06-10",
                    "date_to": "2026-06-17",
                    "adults": 2,
                    "children": 0,
                    "is_manual": True,
                    "total": "5000.00",
                    "currency": "GBP",
                },
            ],
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    # DRF nests many=True errors as a list aligned with the input rows.
    assert "price_override_reason" in response.data["field_errors"]["lines"][1]
    assert Quotation.objects.count() == 0
    assert QuotationLine.objects.count() == 0
    assert BookingHold.objects.count() == 0


@pytest.mark.django_db
def test_create_with_lines_succeeds_over_foreign_live_hold(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    terms: TermsVersion,
    property_: Property,
    rate_rule: object,
) -> None:
    """A quote over dates someone else holds saves fine — quotes are offers,
    not claims on inventory; the conflict surfaces only at hold/book time."""
    from reservations.services.holds import HoldService

    api_client.force_login(staff)
    enquiry = guest.enquiries.create()
    second = _second_property(property_)
    # Another live hold already owns the second villa's dates.
    HoldService.place(
        property=second,
        date_from=date(2026, 6, 12),
        date_to=date(2026, 6, 15),
        never_expires=True,
    )

    response = api_client.post(
        "/api/v1/quotations",
        {
            "enquiry": enquiry.pk,
            "guest": guest.pk,
            "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            "terms_version": terms.pk,
            "lines": [
                {
                    "property": property_.pk,
                    "date_from": "2026-06-10",
                    "date_to": "2026-06-17",
                    "adults": 2,
                    "children": 0,
                },
                {
                    "property": second.pk,
                    "date_from": "2026-06-10",
                    "date_to": "2026-06-17",
                    "adults": 2,
                    "children": 0,
                    "is_manual": True,
                    "total": "5000.00",
                    "price_override_reason": "Agreed rate",
                    "currency": "GBP",
                },
            ],
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert QuotationLine.objects.count() == 2
    # The pre-existing hold is untouched and no new ones appeared.
    assert BookingHold.objects.count() == 1


@pytest.mark.django_db
def test_agent_direct_create_with_lines_rolls_back_minted_enquiry(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    terms: TermsVersion,
    property_: Property,
    rate_rule: object,
) -> None:
    """The auto-minted enquiry (agent-direct: no `enquiry` in the body) is part
    of the same transaction and must vanish with everything else. Trigger:
    a priced line on a villa with no rates (`NoRateAvailable`)."""
    from reservations.models import Enquiry

    api_client.force_login(staff)
    # `_second_property` has no rate plan — pricing it raises NoRateAvailable.
    unrated = _second_property(property_)
    enquiries_before = Enquiry.objects.count()

    response = api_client.post(
        "/api/v1/quotations",
        {
            "guest": guest.pk,
            "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            "terms_version": terms.pk,
            "lines": [
                {
                    "property": unrated.pk,
                    "date_from": "2026-06-10",
                    "date_to": "2026-06-17",
                    "adults": 2,
                    "children": 0,
                    # Explicit currency gets past currency resolution so the
                    # engine itself raises (no rate plan on this villa).
                    "currency": "GBP",
                },
            ],
        },
        format="json",
    )

    assert response.status_code == 409, response.data
    assert response.data["code"] == "no_rate_available"
    assert Quotation.objects.count() == 0
    assert Enquiry.objects.count() == enquiries_before


@pytest.mark.django_db
def test_create_with_lines_nets_discount(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    terms: TermsVersion,
    property_: Property,
    rate_rule: object,
) -> None:
    api_client.force_login(staff)
    enquiry = guest.enquiries.create()

    response = api_client.post(
        "/api/v1/quotations",
        {
            "enquiry": enquiry.pk,
            "guest": guest.pk,
            "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            "terms_version": terms.pk,
            "lines": [
                {
                    "property": property_.pk,
                    "date_from": "2026-06-10",
                    "date_to": "2026-06-17",
                    "adults": 2,
                    "children": 0,
                    "discount": "150.00",
                    "inclusions": "Welcome hamper",
                },
            ],
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    row = response.data["lines"][0]
    # Gross = 7 nights @ £200 = £1400; net = 1400 - 150 = 1250.
    assert row["total"] == "1250.00"
    assert row["discount"] == "150.00"
    assert row["inclusions"] == "Welcome hamper"


@pytest.mark.django_db
def test_create_with_lines_pins_supplied_currency(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    terms: TermsVersion,
    property_: Property,
    rate_rule: object,
    gbp: Currency,
) -> None:
    """An explicitly supplied currency exact-matches its plan even when a newer
    plan in another currency would win an unpinned search (GAP-014)."""
    api_client.force_login(staff)
    enquiry = guest.enquiries.create()
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    # Newer effective_from — an unpinned pricing would prefer this plan.
    _priced_plan_in(property_, eur, date(2026, 2, 1), "300.00")

    response = api_client.post(
        "/api/v1/quotations",
        {
            "enquiry": enquiry.pk,
            "guest": guest.pk,
            "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            "terms_version": terms.pk,
            "lines": [
                {
                    "property": property_.pk,
                    "date_from": "2026-06-10",
                    "date_to": "2026-06-17",
                    "adults": 2,
                    "children": 0,
                    "currency": "GBP",
                },
            ],
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    row = response.data["lines"][0]
    assert row["currency"] == "GBP"
    assert row["total"] == "1400.00"


@pytest.mark.django_db
def test_create_with_lines_records_changeover_shift(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    terms: TermsVersion,
    property_: Property,
    rate_rule: object,
) -> None:
    """A nested line off the changeover day is shifted exactly like the
    per-line endpoint (GAP-007)."""
    PropertySettings.objects.create(
        property=property_,
        changeover_day=PrefilledChangeOverDay.SAT.value,
    )
    api_client.force_login(staff)
    enquiry = guest.enquiries.create()

    response = api_client.post(
        "/api/v1/quotations",
        {
            "enquiry": enquiry.pk,
            "guest": guest.pk,
            "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            "terms_version": terms.pk,
            "lines": [
                {
                    "property": property_.pk,
                    "date_from": "2026-06-10",  # Wednesday
                    "date_to": "2026-06-17",
                    "adults": 2,
                    "children": 0,
                },
            ],
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    row = response.data["lines"][0]
    assert row["date_from"] == "2026-06-13"  # next Saturday
    assert row["date_to"] == "2026-06-20"
    assert row["changeover_shifted_from"] == "2026-06-10"
    assert BookingHold.objects.count() == 0


@pytest.mark.django_db
def test_patch_quotation_rejects_lines(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
) -> None:
    """`lines` is a create-only convenience — a PATCH must reject it loudly
    rather than silently ignoring it."""
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/quotations/{quotation.pk}",
        {"lines": []},
        format="json",
    )
    assert response.status_code == 400, response.data
    assert "lines" in response.data["field_errors"]


# ----------------------------------------------------------------------
# Lifecycle guards — :convert requires SENT; post-send writes are frozen
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_convert_draft_quotation_409s(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    """Converting a quote the guest never received must be refused.

    The guard this pins: `:convert` used to skip `accept()` for any non-SENT
    status but still create the booking — converting a DRAFT yielded a live
    booking with the quotation stuck in DRAFT and the enquiry never CONVERTED.
    """
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk, "terms_accepted": True},
        format="json",
    )

    assert response.status_code == 409, response.data
    assert response.data["code"] == "invalid_transition"
    assert Booking.objects.count() == 0
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.DRAFT.value


@pytest.mark.django_db
@pytest.mark.parametrize("kill", ["expire", "cancel"])
def test_convert_dead_quotation_409s(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
    kill: str,
) -> None:
    """EXPIRED/CANCELLED quotes (holds released, price stale) cannot convert."""
    getattr(quotation, kill)()
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk, "terms_accepted": True},
        format="json",
    )

    assert response.status_code == 409, response.data
    assert Booking.objects.count() == 0


@pytest.mark.django_db
def test_convert_retry_on_accepted_quotation_is_idempotent(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    """A double-click retry (quotation now ACCEPTED, same line) returns the
    original booking rather than 409ing — the retry contract `:convert` has
    always had via the line-FK idempotency check."""
    quotation.send()
    api_client.force_login(staff)
    url = f"/api/v1/quotations/{quotation.pk}:convert"

    first = api_client.post(url, {"line": line.pk, "terms_accepted": True}, format="json")
    assert first.status_code == 201, first.data

    second = api_client.post(url, {"line": line.pk, "terms_accepted": True}, format="json")

    assert second.status_code == 201, second.data
    assert second.data["id"] == first.data["id"]
    assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_convert_accepted_quotation_with_unselected_line_409s(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
    property_: Property,
    gbp: Currency,
) -> None:
    """Once a quote is ACCEPTED on one line, converting a *different* line
    must be refused — it would mint a second booking off the same quote."""
    other_line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 7, 10),
        date_to=date(2026, 7, 17),
        adults=2,
        total=Decimal("900.00"),
    )
    quotation.send()
    api_client.force_login(staff)
    url = f"/api/v1/quotations/{quotation.pk}:convert"

    first = api_client.post(url, {"line": line.pk, "terms_accepted": True}, format="json")
    assert first.status_code == 201, first.data

    second = api_client.post(url, {"line": other_line.pk, "terms_accepted": True}, format="json")

    assert second.status_code == 409, second.data
    assert Booking.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("freeze", ["accept", "expire", "cancel"])
def test_patch_quotation_locked_once_closed(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
    freeze: str,
) -> None:
    """ACCEPTED/EXPIRED/CANCELLED quotations refuse header edits — the terms
    the guest accepted (or the dead quote's audit shape) must not drift."""
    if freeze == "accept":
        quotation.send()
        quotation.accept(line)
    else:
        getattr(quotation, freeze)()
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/quotations/{quotation.pk}",
        {"is_unbranded": True},
        format="json",
    )

    assert response.status_code == 409, response.data
    assert response.data["code"] == "quotation_locked"
    quotation.refresh_from_db()
    assert quotation.is_unbranded is False


@pytest.mark.django_db
def test_patch_sent_quotation_still_allowed(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
) -> None:
    """SENT quotes stay editable — renegotiation before acceptance is a real
    operator workflow (edit + re-send)."""
    quotation.send()
    api_client.force_login(staff)
    new_expiry = (timezone.now() + timedelta(days=14)).isoformat()

    response = api_client.patch(
        f"/api/v1/quotations/{quotation.pk}",
        {"expires_at": new_expiry},
        format="json",
    )

    assert response.status_code == 200, response.data


@pytest.mark.django_db
def test_delete_quotation_only_when_draft(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
) -> None:
    """Hard-delete is for never-sent drafts only; a SENT quote is a
    customer-facing artefact — withdraw or expire it instead."""
    api_client.force_login(staff)

    quotation.send()
    response = api_client.delete(f"/api/v1/quotations/{quotation.pk}")
    assert response.status_code == 409, response.data
    assert Quotation.objects.filter(pk=quotation.pk).exists()


@pytest.mark.django_db
def test_delete_draft_quotation_still_allowed(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
) -> None:
    api_client.force_login(staff)

    response = api_client.delete(f"/api/v1/quotations/{quotation.pk}")

    assert response.status_code == 204, response.data
    assert not Quotation.objects.filter(pk=quotation.pk).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("freeze", ["accept", "expire", "cancel"])
def test_line_writes_locked_once_quotation_closed(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
    property_: Property,
    freeze: str,
) -> None:
    """Line create/update/delete are refused once the quotation is closed —
    the price the guest accepted must not be editable after the fact."""
    if freeze == "accept":
        quotation.send()
        quotation.accept(line)
    else:
        getattr(quotation, freeze)()
    api_client.force_login(staff)
    original_adults = line.adults

    create = api_client.post(
        f"/api/v1/quotations/{quotation.pk}/lines",
        {
            "property": property_.pk,
            "date_from": "2026-08-10",
            "date_to": "2026-08-17",
            "adults": 2,
            "children": 0,
        },
        format="json",
    )
    assert create.status_code == 409, create.data
    assert create.data["code"] == "quotation_locked"

    patch = api_client.patch(
        f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}",
        {"adults": 6},
        format="json",
    )
    assert patch.status_code == 409, patch.data
    line.refresh_from_db()
    assert line.adults == original_adults

    delete = api_client.delete(f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}")
    assert delete.status_code == 409, delete.data
    assert QuotationLine.objects.filter(pk=line.pk).exists()


@pytest.mark.django_db
def test_line_writes_allowed_while_sent(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
    rate_rule: object,
) -> None:
    """SENT lines stay editable — pre-acceptance renegotiation."""
    quotation.send()
    api_client.force_login(staff)

    patch = api_client.patch(
        f"/api/v1/quotations/{quotation.pk}/lines/{line.pk}",
        {"notes": "guest asked for late checkout"},
        format="json",
    )

    assert patch.status_code == 200, patch.data


@pytest.mark.django_db
def test_convert_race_past_idempotency_precheck_recovers_winner(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two concurrent converts can both miss the service's existing-booking
    pre-check; the loser hits `booking_one_per_quotation_line` and must serve
    the winner's booking, not a 500."""
    from django.db import IntegrityError

    from reservations.services.bookings import BookingService

    quotation.send()
    api_client.force_login(staff)
    url = f"/api/v1/quotations/{quotation.pk}:convert"

    first = api_client.post(url, {"line": line.pk, "terms_accepted": True}, format="json")
    assert first.status_code == 201, first.data

    # Simulate the loser of the race: its transaction sees no existing
    # booking, inserts, and hits the unique constraint.
    def raced(*args: object, **kwargs: object) -> None:
        raise IntegrityError(
            'duplicate key value violates unique constraint "booking_one_per_quotation_line"'
        )

    monkeypatch.setattr(BookingService, "create_from_quotation_line", raced)

    second = api_client.post(url, {"line": line.pk, "terms_accepted": True}, format="json")

    assert second.status_code == 201, second.data
    assert second.data["id"] == first.data["id"]
    assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_convert_retry_after_booking_cancelled_is_409(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    """Once the converted booking is cancelled, a convert retry must not
    resurface it as a fresh 201 — re-book via a new quotation."""
    quotation.send()
    api_client.force_login(staff)
    url = f"/api/v1/quotations/{quotation.pk}:convert"

    first = api_client.post(url, {"line": line.pk, "terms_accepted": True}, format="json")
    assert first.status_code == 201, first.data
    Booking.objects.get(pk=first.data["id"]).cancel("guest changed plans")

    second = api_client.post(url, {"line": line.pk, "terms_accepted": True}, format="json")

    assert second.status_code == 409, second.data
    assert second.data["code"] == "terminal_booking_exists"
