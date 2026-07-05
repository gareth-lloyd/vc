from __future__ import annotations

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.properties import PropertyLoader
from data_migration.loaders.sentinels import unknown_country, unknown_region
from properties.models.geo import Country, Region
from properties.models.property import Property, PropertyCategory


@pytest.fixture
def category(db: None) -> PropertyCategory:
    return PropertyCategory.objects.create(name="Villa", slug="villa")


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": 100,
        "Name": "Casa Test",
        "DisplayName": "Casa Test",
        "Slug": "casa-test",
        "OverView": "",
        "HouseRules": "",
        "FeatureDescription": "",
        "RoomDescription": "",
        "Notes": "",
        "LocalityRegion": "",
        "LocalityTown": "",
        "AddressLine1": "",
        "AddressLine2": "",
        "AddressLine3": "",
        "PostCode": "",
        "LicenceNumber": "",
        "Latitude": None,
        "Longitude": None,
        "Category": None,
        "Channel": None,
        "Guests": 0,
        "AdditionalGuests": 0,
        "Bedrooms": 0,
        "Ensuites": 0,
        "Bathrooms": 0,
        "Size": None,
        "RegionId": None,
        "ViilaStatus": 1,
        "SettingAvailabilityStatusId": None,
        "SettingIsBookingsRequirePreApproval": False,
        "SettingPricesEnteredTypeId": None,
        "SettingCurrencyId": None,
        "SettingCheckInTime": None,
        "SettingCheckOutTime": None,
        "SettingChangeoverDayId": None,
        "SettingMinNightsRental": 1,
        "SettingMinNightsRentalNote": "",
    }
    base.update(overrides)
    return base


@pytest.mark.django_db
def test_transform_skips_property_with_no_name(category: PropertyCategory) -> None:
    assert PropertyLoader().transform(_row(Name="")) is None


@pytest.mark.django_db
def test_transform_falls_back_to_unknown_region(
    category: PropertyCategory,
) -> None:
    """Plan 1.2: a property whose RegionId can't be resolved attaches to the
    unknown sentinel rather than getting skipped.
    """
    kwargs = PropertyLoader().transform(_row(RegionId=999))
    assert kwargs is not None
    sentinel_region = unknown_region(unknown_country())
    assert kwargs["region"].pk == sentinel_region.pk


@pytest.mark.django_db
def test_transform_uses_explicit_fks_when_present(category: PropertyCategory) -> None:
    country = Country.objects.get(iso2="GR")
    region = Region.objects.create(
        country=country,
        name="Crete",
        slug="crete",
        legacy_id="55",
    )
    kwargs = PropertyLoader().transform(
        _row(RegionId=55, Category=str(category.legacy_id or "")),
    )
    assert kwargs is not None
    assert kwargs["region"].pk == region.pk


@pytest.mark.django_db
def test_process_row_creates_property_with_sentinel_when_fks_missing(
    category: PropertyCategory,
) -> None:
    loader = PropertyLoader()
    report = LoadReport(loader=loader.name)
    loader._process_row(_row(RegionId=999), report)
    p = Property.objects.get(legacy_id="100")
    assert p.region.legacy_id == "__unknown__"


@pytest.mark.django_db
def test_changeover_day_maps_the_code_domain(category: PropertyCategory) -> None:
    """`SettingChangeoverDayId` stores `ChangeOverDays.Code` (the Blazor
    select binds `[Code]`, not the identity Id): -1 = Open/flexible,
    0 = Sunday, 1 = Monday .. 6 = Saturday. 0 is a real value — it must land
    as SUN, not be dropped as falsy."""
    from properties.enums import PrefilledChangeOverDay
    from properties.models.settings import PropertySettings

    loader = PropertyLoader()
    loader._process_row(_row(SettingChangeoverDayId=0), LoadReport(loader=loader.name))
    settings = PropertySettings.objects.get(property__legacy_id="100")
    assert settings.changeover_day == PrefilledChangeOverDay.SUN

    loader._process_row(
        _row(Id=101, SettingChangeoverDayId=-1),
        LoadReport(loader=loader.name),
    )
    assert (
        PropertySettings.objects.get(property__legacy_id="101").changeover_day
        == PrefilledChangeOverDay.ANY
    )
