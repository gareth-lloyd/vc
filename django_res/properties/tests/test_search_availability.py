"""Search behaviour for `GET /properties` — change-over weekday filter and
availability-window filter.

Implements ticket T2.2 (`changeover_day=ANY` must match every weekday-filtered
search) and T3.1 (default response excludes properties with overlapping live
holds or active bookings; `?include_unavailable=true` returns the full set).

The availability filter is bulk: a single round-trip per request that yields the
unavailable-property-id set, used as an `.exclude(id__in=…)` against the main
queryset — no per-property `AvailabilityService.is_available()` loop.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

import pytest
from rest_framework.test import APIClient

from accounts.factories import CustomerPersonFactory
from accounts.models import Person, User
from core.tests import assert_max_queries
from pricing.models import Currency
from properties.enums import PrefilledChangeOverDay
from properties.models import (
    Country,
    Property,
    PropertyCategory,
    PropertySettings,
    Region,
)
from reservations.enums import BookingHoldReason, BookingStatus, PaymentMethod
from reservations.models import (
    Booking,
    BookingHold,
    Enquiry,
    Quotation,
    QuotationLine,
    TermsVersion,
)

# ---------------------------------------------------------------------------
# Local fixtures — kept private to this module so the test data shape is
# explicit at the top of every test.
# ---------------------------------------------------------------------------


@pytest.fixture
def category(db: None) -> PropertyCategory:
    return PropertyCategory.objects.create(name="Villa", slug="villa-search")


@pytest.fixture
def country(db: None) -> Country:
    country, _ = Country.objects.get_or_create(
        iso2="GB",
        defaults={"name": "United Kingdom", "iso3": "GBR"},
    )
    return country


@pytest.fixture
def region(country: Country) -> Region:
    return Region.objects.create(country=country, name="Search Region", slug="search-region")


def _make_property(
    *,
    slug: str,
    category: PropertyCategory,
    region: Region,
    changeover_day: str | None,
) -> Property:
    """Create a property with a `PropertySettings` row holding `changeover_day`.

    Bypasses the factory's full child graph to keep the test queryset focused;
    the search filter only needs the property row + `settings.changeover_day`.
    """
    prop = Property.objects.create(
        name=slug,
        display_name=slug,
        slug=slug,
        category=category,
        region=region,
    )
    PropertySettings.objects.create(property=prop, changeover_day=changeover_day)
    return prop


@pytest.fixture
def gbp(db: None) -> Currency:
    currency, _ = Currency.objects.get_or_create(
        code="GBP",
        defaults={"name": "Pound sterling", "symbol": "£"},
    )
    return currency


@pytest.fixture
def terms(db: None) -> TermsVersion:
    return TermsVersion.objects.create(
        version="search-test",
        body_markdown="**T&Cs**",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        is_current=True,
    )


@pytest.fixture
def customer(db: None) -> Person:
    return cast(
        Person,
        CustomerPersonFactory(
            first_name="Search",
            last_name="Tester",
            primary_email="search@example.com",
        ),
    )


def _make_active_booking(
    *,
    property_: Property,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    date_from: date,
    date_to: date,
) -> Booking:
    quotation = Quotation.objects.create(
        enquiry=Enquiry.objects.create(
            person=customer,
            property=property_,
            date_from=date_from,
            date_to=date_to,
        ),
        person=customer,
        expires_at=datetime(2027, 1, 1, tzinfo=UTC),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date_from,
        date_to=date_to,
        adults=2,
        total=Decimal("1000.00"),
    )
    booking = Booking.objects.create(
        quotation_line=line,
        person=customer,
        property=property_,
        date_from=date_from,
        date_to=date_to,
        adults=2,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=datetime(2026, 1, 1, tzinfo=UTC),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1000.00"),
        balance_due=Decimal("1000.00"),
    )
    booking.status = BookingStatus.AWAITING_DEPOSIT.value
    booking.save(update_fields=["status", "updated_at"])
    return booking


def _make_live_hold(
    *,
    property_: Property,
    date_from: date,
    date_to: date,
) -> BookingHold:
    return BookingHold.objects.create(
        property=property_,
        date_from=date_from,
        date_to=date_to,
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )


# ---------------------------------------------------------------------------
# T2.2 — change-over `ANY` inclusion on weekday-filtered search
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_search_includes_any_changeover_on_weekday(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    region: Region,
) -> None:
    """A property whose effective `changeover_day=ANY` must appear in a
    weekday-filtered search."""
    any_prop = _make_property(
        slug="any-villa",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.ANY.value,
    )
    sat_prop = _make_property(
        slug="sat-villa",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.SAT.value,
    )
    mon_prop = _make_property(
        slug="mon-villa",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.MON.value,
    )
    api_client.force_login(staff)

    response = api_client.get(
        "/api/v1/properties",
        {"changeover_day": PrefilledChangeOverDay.SAT.value},
    )

    assert response.status_code == 200, response.content
    slugs = {row["slug"] for row in response.json()["results"]}
    assert any_prop.slug in slugs
    assert sat_prop.slug in slugs
    assert mon_prop.slug not in slugs


@pytest.mark.django_db
def test_search_specific_changeover_still_matches(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    region: Region,
) -> None:
    """A property with `changeover_day=SAT` only matches a Saturday-filtered
    search — not, e.g., a Monday-filtered one."""
    sat_prop = _make_property(
        slug="sat-only",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.SAT.value,
    )
    api_client.force_login(staff)

    sat_response = api_client.get(
        "/api/v1/properties",
        {"changeover_day": PrefilledChangeOverDay.SAT.value},
    )
    mon_response = api_client.get(
        "/api/v1/properties",
        {"changeover_day": PrefilledChangeOverDay.MON.value},
    )

    assert sat_prop.slug in {row["slug"] for row in sat_response.json()["results"]}
    assert sat_prop.slug not in {row["slug"] for row in mon_response.json()["results"]}


@pytest.mark.django_db
def test_search_changeover_null_matches_every_weekday(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    region: Region,
) -> None:
    """When `PropertySettings.changeover_day` is null, the effective value is
    `ANY` — the property must not vanish from weekday-filtered search."""
    inherited = _make_property(
        slug="null-changeover",
        category=category,
        region=region,
        changeover_day=None,
    )
    api_client.force_login(staff)

    response = api_client.get(
        "/api/v1/properties",
        {"changeover_day": PrefilledChangeOverDay.SAT.value},
    )

    assert response.status_code == 200, response.content
    slugs = {row["slug"] for row in response.json()["results"]}
    assert inherited.slug in slugs


# ---------------------------------------------------------------------------
# T3.1 — search default = available-only, `?include_unavailable=true` toggle
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_search_default_excludes_booked_properties(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    region: Region,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    booked = _make_property(
        slug="booked-villa",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.ANY.value,
    )
    free = _make_property(
        slug="free-villa",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.ANY.value,
    )
    _make_active_booking(
        property_=booked,
        customer=customer,
        gbp=gbp,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )
    api_client.force_login(staff)

    response = api_client.get(
        "/api/v1/properties",
        {"date_from": "2026-06-12", "date_to": "2026-06-15"},
    )

    assert response.status_code == 200, response.content
    slugs = {row["slug"] for row in response.json()["results"]}
    assert booked.slug not in slugs
    assert free.slug in slugs


@pytest.mark.django_db
def test_search_default_excludes_held_properties(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    region: Region,
) -> None:
    held = _make_property(
        slug="held-villa",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.ANY.value,
    )
    free = _make_property(
        slug="not-held-villa",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.ANY.value,
    )
    _make_live_hold(
        property_=held,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
    )
    api_client.force_login(staff)

    response = api_client.get(
        "/api/v1/properties",
        {"date_from": "2026-07-03", "date_to": "2026-07-05"},
    )

    assert response.status_code == 200, response.content
    slugs = {row["slug"] for row in response.json()["results"]}
    assert held.slug not in slugs
    assert free.slug in slugs


@pytest.mark.django_db
def test_search_include_unavailable_returns_all(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    region: Region,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    booked = _make_property(
        slug="booked-villa-iu",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.ANY.value,
    )
    held = _make_property(
        slug="held-villa-iu",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.ANY.value,
    )
    free = _make_property(
        slug="free-villa-iu",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.ANY.value,
    )
    _make_active_booking(
        property_=booked,
        customer=customer,
        gbp=gbp,
        terms=terms,
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 8),
    )
    _make_live_hold(
        property_=held,
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 8),
    )
    api_client.force_login(staff)

    response = api_client.get(
        "/api/v1/properties",
        {
            "date_from": "2026-08-02",
            "date_to": "2026-08-05",
            "include_unavailable": "true",
        },
    )

    assert response.status_code == 200, response.content
    slugs = {row["slug"] for row in response.json()["results"]}
    assert booked.slug in slugs
    assert held.slug in slugs
    assert free.slug in slugs


@pytest.mark.django_db
def test_include_unavailable_rows_carry_per_row_availability_flag(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    region: Region,
) -> None:
    """With a date range + `include_unavailable=true`, every row reports
    `available_for_range` so callers (the quote builder) can badge blocked
    villas instead of silently offering them."""
    held = _make_property(
        slug="held-villa-flag",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.ANY.value,
    )
    free = _make_property(
        slug="free-villa-flag",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.ANY.value,
    )
    _make_live_hold(
        property_=held,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
    )
    api_client.force_login(staff)

    response = api_client.get(
        "/api/v1/properties",
        {
            "date_from": "2026-07-03",
            "date_to": "2026-07-05",
            "include_unavailable": "true",
        },
    )

    assert response.status_code == 200, response.content
    by_slug = {row["slug"]: row for row in response.json()["results"]}
    assert by_slug[held.slug]["available_for_range"] is False
    assert by_slug[free.slug]["available_for_range"] is True


@pytest.mark.django_db
def test_no_date_range_availability_flag_is_null(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    region: Region,
) -> None:
    """Without a date range "available" is undefined — the flag is null, not a
    misleading true."""
    prop = _make_property(
        slug="flagless-villa",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.ANY.value,
    )
    api_client.force_login(staff)

    response = api_client.get("/api/v1/properties")

    assert response.status_code == 200, response.content
    by_slug = {row["slug"]: row for row in response.json()["results"]}
    assert by_slug[prop.slug]["available_for_range"] is None


@pytest.mark.django_db
def test_search_no_date_range_no_availability_filter(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    region: Region,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """Without a date range, "available" is undefined — bookings/holds must
    not silently filter the response."""
    booked = _make_property(
        slug="booked-villa-nodates",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.ANY.value,
    )
    _make_active_booking(
        property_=booked,
        customer=customer,
        gbp=gbp,
        terms=terms,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 8),
    )
    api_client.force_login(staff)

    response = api_client.get("/api/v1/properties")

    assert response.status_code == 200, response.content
    slugs = {row["slug"] for row in response.json()["results"]}
    assert booked.slug in slugs


@pytest.mark.django_db
@pytest.mark.parametrize("include_unavailable", [None, "true"])
def test_dated_search_runs_conflict_queries_once(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    region: Region,
    include_unavailable: str | None,
) -> None:
    """The unavailable-id set is resolved once per request, whether it feeds
    the row-exclusion filter (default) or the per-row flag
    (`include_unavailable=true`) — never both."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    held = _make_property(
        slug=f"once-villa-{include_unavailable or 'default'}",
        category=category,
        region=region,
        changeover_day=PrefilledChangeOverDay.ANY.value,
    )
    _make_live_hold(
        property_=held,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
    )
    api_client.force_login(staff)

    params = {"date_from": "2026-07-03", "date_to": "2026-07-05"}
    if include_unavailable is not None:
        params["include_unavailable"] = include_unavailable

    with CaptureQueriesContext(connection) as ctx:
        response = api_client.get("/api/v1/properties", params)

    assert response.status_code == 200, response.content
    hold_queries = [q for q in ctx.captured_queries if "bookinghold" in q["sql"].lower()]
    assert len(hold_queries) == 1, [q["sql"] for q in hold_queries]


@pytest.mark.django_db
def test_search_availability_is_single_bulk_query(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    region: Region,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """Query count must stay flat as the property set scales — the availability
    check is bulk, not one per property.

    Strategy: capture the query count at two scales of the *same* property set
    (10 then 30 rows, both above the pagination threshold so the COUNT(*) is
    consistently present). The availability filter must contribute a constant
    overhead independent of N.
    """

    def _make_batch(n_start: int, n: int) -> None:
        for idx in range(n_start, n_start + n):
            prop = _make_property(
                slug=f"scale-prop-{idx}",
                category=category,
                region=region,
                changeover_day=PrefilledChangeOverDay.ANY.value,
            )
            if idx % 2 == 0:
                _make_active_booking(
                    property_=prop,
                    customer=customer,
                    gbp=gbp,
                    terms=terms,
                    date_from=date(2026, 10, 1),
                    date_to=date(2026, 10, 8),
                )
            else:
                _make_live_hold(
                    property_=prop,
                    date_from=date(2026, 10, 1),
                    date_to=date(2026, 10, 8),
                )

    _make_batch(0, 10)
    api_client.force_login(staff)

    # Baseline: 10 properties.
    with assert_max_queries(15) as ctx_small:
        response = api_client.get(
            "/api/v1/properties",
            {"date_from": "2026-10-02", "date_to": "2026-10-05"},
        )
    assert response.status_code == 200, response.content
    baseline = len(ctx_small.captured_queries)

    # Triple the property set; query count must not grow.
    _make_batch(10, 20)

    with assert_max_queries(baseline) as ctx_large:
        response = api_client.get(
            "/api/v1/properties",
            {"date_from": "2026-10-02", "date_to": "2026-10-05"},
        )
    assert response.status_code == 200, response.content
    assert len(ctx_large.captured_queries) <= baseline
