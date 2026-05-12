from __future__ import annotations

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
        "TaxRate": "20.00",
    }
