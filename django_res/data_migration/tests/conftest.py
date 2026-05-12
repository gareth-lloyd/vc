from __future__ import annotations

from decimal import Decimal

import pytest


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
