from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from properties.models.property import Property


@pytest.fixture
def seeded(db: None) -> Property:
    """The booking-loader prerequisite graph: a Property (legacy_id=900), the
    `client-55` Person minted via ClientLoader, and a GBP Currency
    (legacy_id="2"). Shared by the booking + charge-item loader suites so the
    graph only has to be maintained in one place."""
    from data_migration.base import LoadReport
    from data_migration.loaders.reservations import ClientLoader
    from pricing.models.currency import Currency
    from properties.models import Country, PropertyCategory, PropertyGroup, Region
    from properties.models.property import Property

    country, _ = Country.objects.get_or_create(
        iso2="GB", defaults={"name": "United Kingdom", "iso3": "GBR"}
    )
    region = Region.objects.create(country=country, name="South West", slug="south-west")
    category = PropertyCategory.objects.create(name="Villa", slug="villa")
    group = PropertyGroup.objects.create(name="Test group")
    prop = Property.objects.create(
        name="Test Villa",
        display_name="Test Villa",
        slug="test-villa",
        category=category,
        group=group,
        region=region,
        legacy_id="900",
    )
    # GAP-045 D5-3: the booking's customer is a `client-55` Person, written by
    # ClientLoader from a legacy VillaClientDetails row (Id=55) — the loader now
    # resolves it via `person_for_client`, no Guest in the graph.
    ClientLoader()._process_row(
        {
            "Id": 55,
            "FirstName": "Ada",
            "LastName": "Lovelace",
            "Email": "ada@example.com",
            "MobileNo": "",
        },
        LoadReport(loader="client"),
    )
    Currency.objects.create(code="GBP", name="Pound sterling", symbol="£", legacy_id="2")
    return prop


@pytest.fixture
def villa_country_row() -> dict[str, object]:
    """One canonical legacy `VillaCountry` row as it comes off pyodbc."""
    return {
        "Id": 42,
        "Name": "France",
        "ShortName1": "fr",
        "ShortName2": "fra",
        "Code": 33,
        "CountryOrder": 5,
        "IsActive": True,
        "TaxRate": Decimal("20.00"),
    }
