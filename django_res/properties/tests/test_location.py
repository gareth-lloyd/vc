from __future__ import annotations

from typing import cast

import pytest
from django.core.exceptions import ValidationError

from properties.factories import PropertyFactory
from properties.models import Property, PropertyLocation


class TestTimezoneField:
    def test_field_default_is_utc(self) -> None:
        assert PropertyLocation().timezone == "UTC"

    @pytest.mark.django_db
    def test_rejects_bogus_timezone(self) -> None:
        prop = cast(Property, PropertyFactory())
        location = prop.location
        location.timezone = "Mars/Phobos"
        with pytest.raises(ValidationError):
            location.full_clean()

    @pytest.mark.django_db
    def test_valid_timezone_passes_full_clean(self) -> None:
        prop = cast(Property, PropertyFactory())
        location = prop.location
        location.timezone = "Europe/Paris"
        location.full_clean()  # no raise


class TestTimezoneDerivedFromCountry:
    @pytest.mark.django_db
    def test_factory_derives_zone_from_mapped_country(self) -> None:
        prop = cast(Property, PropertyFactory(region__country__iso2="IT"))
        assert prop.location.timezone == "Europe/Rome"

    @pytest.mark.django_db
    def test_factory_unmapped_country_stays_utc(self) -> None:
        # Iceland (IS) is a real ISO row but not in COUNTRY_TIMEZONES.
        prop = cast(Property, PropertyFactory(region__country__iso2="IS"))
        assert prop.location.timezone == "UTC"
