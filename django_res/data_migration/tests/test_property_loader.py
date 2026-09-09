from __future__ import annotations

import pytest
import structlog
from django.contrib.contenttypes.models import ContentType

from core.models import AuditLog
from data_migration.base import LoadReport
from data_migration.loaders.properties import PropertyLoader
from data_migration.loaders.sentinels import unknown_country, unknown_region
from properties.enums import DescriptionSection
from properties.models.descriptions import PropertyDescription
from properties.models.geo import Country, Region
from properties.models.property import Property


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
def test_transform_skips_property_with_no_name() -> None:
    assert PropertyLoader().transform(_row(Name="")) is None


@pytest.mark.django_db
def test_transform_falls_back_to_unknown_region() -> None:
    """Plan 1.2: a property whose RegionId can't be resolved attaches to the
    unknown sentinel rather than getting skipped.
    """
    kwargs = PropertyLoader().transform(_row(RegionId=999))
    assert kwargs is not None
    sentinel_region = unknown_region(unknown_country())
    assert kwargs["region"].pk == sentinel_region.pk


@pytest.mark.django_db
def test_transform_uses_explicit_fks_when_present() -> None:
    country = Country.objects.get(iso2="GR")
    region = Region.objects.create(
        country=country,
        name="Crete",
        slug="crete",
        legacy_id="55",
    )
    kwargs = PropertyLoader().transform(_row(RegionId=55))
    assert kwargs is not None
    assert kwargs["region"].pk == region.pk


@pytest.mark.django_db
def test_process_row_creates_property_with_sentinel_when_fks_missing() -> None:
    loader = PropertyLoader()
    report = LoadReport(loader=loader.name)
    loader._process_row(_row(RegionId=999), report)
    p = Property.objects.get(legacy_id="100")
    assert p.region.legacy_id == "__unknown__"


@pytest.mark.django_db
def test_changeover_day_maps_the_code_domain() -> None:
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


# --- Website copy from VillaPropertyImagesDescription (PRESERVE ALL) --------


@pytest.mark.django_db
def test_transform_maps_vodeo_url_to_video_url() -> None:
    kwargs = PropertyLoader().transform(_row(VodeoUrl="  https://player.vimeo.com/video/1  "))
    assert kwargs is not None
    assert kwargs["video_url"] == "https://player.vimeo.com/video/1"


@pytest.mark.django_db
def test_transform_blank_vodeo_url_leaves_video_url_empty() -> None:
    assert PropertyLoader().transform(_row())["video_url"] == ""  # type: ignore[index]


def _write_and_fetch(**overrides: object) -> dict[str, str]:
    """Run `_process_row` and return {section: body} for the created property."""
    loader = PropertyLoader()
    loader._process_row(_row(**overrides), LoadReport(loader=loader.name))
    prop = Property.objects.get(legacy_id="100")
    return {d.section: d.body for d in PropertyDescription.objects.filter(property=prop)}


@pytest.mark.django_db
def test_web_description_concatenates_both_parts() -> None:
    sections = _write_and_fetch(WebDesc1="  Marketing copy  ", WebDesc2="  Activities  ")
    assert sections[DescriptionSection.WEB_DESCRIPTION] == "Marketing copy\n\nActivities"


@pytest.mark.django_db
def test_web_description_single_part_no_blank_join() -> None:
    sections = _write_and_fetch(WebDesc1="Only first", WebDesc2="")
    assert sections[DescriptionSection.WEB_DESCRIPTION] == "Only first"


@pytest.mark.django_db
def test_location_concatenates_both_parts() -> None:
    sections = _write_and_fetch(Location1="Near the beach", Location2="10 min to town")
    assert sections[DescriptionSection.LOCATION] == "Near the beach\n\n10 min to town"


@pytest.mark.django_db
def test_no_website_copy_writes_no_extra_sections() -> None:
    sections = _write_and_fetch()
    assert DescriptionSection.WEB_DESCRIPTION not in sections
    assert DescriptionSection.LOCATION not in sections


# GAP-091: FeatureDescription and RoomDescription are unrelated legacy columns
# (Features-page prose vs the bedrooms blurb) and land in their own sections.


@pytest.mark.django_db
def test_feature_and_room_descriptions_land_in_separate_sections() -> None:
    sections = _write_and_fetch(
        FeatureDescription="  Licence 0829K. Pool cannot be heated.  ",
        RoomDescription="  All bedrooms have sea views.  ",
    )
    assert sections[DescriptionSection.OTHER_INFORMATION] == "Licence 0829K. Pool cannot be heated."
    assert sections[DescriptionSection.ROOMS] == "All bedrooms have sea views."
    assert "villa_info" not in sections


@pytest.mark.django_db
def test_blank_feature_description_writes_no_other_information() -> None:
    sections = _write_and_fetch(FeatureDescription="", RoomDescription="Rooms only")
    assert DescriptionSection.OTHER_INFORMATION not in sections
    assert sections[DescriptionSection.ROOMS] == "Rooms only"


@pytest.mark.django_db
def test_both_blank_writes_neither_section() -> None:
    sections = _write_and_fetch()
    assert DescriptionSection.OTHER_INFORMATION not in sections
    assert DescriptionSection.ROOMS not in sections


def _seed_fused_row(body: str) -> Property:
    """A property loaded before GAP-091 whose fused `villa_info` row migration
    0007 renamed to `other_information`, provenance intact."""
    loader = PropertyLoader()
    loader._process_row(_row(), LoadReport(loader=loader.name))
    prop = Property.objects.get(legacy_id="100")
    PropertyDescription.objects.create(
        property=prop,
        section=DescriptionSection.OTHER_INFORMATION,
        body=body,
        legacy_id="100-villa_info",
    )
    return prop


@pytest.mark.django_db
def test_rerun_drops_the_fused_row_when_only_rooms_copy_remains() -> None:
    """Migration 0007 renamed the fused `villa_info` row with its old
    `legacy_id`; a re-run over a rooms-only villa must drop it (no string split
    can recover the halves) and write the `rooms` row — with an audit tombstone
    and a log event for the drop."""
    prop = _seed_fused_row("All bedrooms have sea views.")

    with structlog.testing.capture_logs() as logs:
        sections = _write_and_fetch(
            FeatureDescription="", RoomDescription="All bedrooms have sea views."
        )

    assert DescriptionSection.OTHER_INFORMATION not in sections
    assert sections[DescriptionSection.ROOMS] == "All bedrooms have sea views."
    rooms = PropertyDescription.objects.get(property=prop, section=DescriptionSection.ROOMS)
    assert rooms.legacy_id == "100-rooms"
    assert any(log["event"] == "data_migration.fused_description_dropped" for log in logs)
    ct = ContentType.objects.get_for_model(PropertyDescription)
    tombstones = AuditLog.objects.filter(
        content_type=ct, field_diffs__section=["other_information", None]
    )
    assert tombstones.count() == 1


@pytest.mark.django_db
def test_rerun_replaces_the_fused_row_when_feature_copy_is_present() -> None:
    """The replace half: a non-blank FeatureDescription rewrites the renamed
    row in place — one `other_information` row, loader provenance refreshed."""
    prop = _seed_fused_row("Licence 0829K.\n\nAll bedrooms have sea views.")

    sections = _write_and_fetch(
        FeatureDescription="Licence 0829K.", RoomDescription="All bedrooms have sea views."
    )

    assert sections[DescriptionSection.OTHER_INFORMATION] == "Licence 0829K."
    other = PropertyDescription.objects.get(
        property=prop, section=DescriptionSection.OTHER_INFORMATION
    )
    assert other.legacy_id == "100-other_information"
    assert not PropertyDescription.objects.filter(legacy_id="100-villa_info").exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("body", "overrides"),
    [
        pytest.param(
            "Staff rewrote this after the rename.",
            {"FeatureDescription": "", "RoomDescription": "All bedrooms have sea views."},
            id="staff-rewrote-it",
        ),
        pytest.param(
            "Licence 0829K.\n\nAll bedrooms have sea views.",
            {"FeatureDescription": "", "RoomDescription": ""},
            id="legacy-blanked-both-since",
        ),
    ],
)
def test_rerun_keeps_a_fused_row_whose_body_no_longer_matches_the_legacy_join(
    body: str, overrides: dict[str, str]
) -> None:
    """The drop is gated on the body still equalling the old join of the
    current legacy columns. Anything else — staff rewrote the renamed row, or
    legacy changed since the earlier load — is kept and logged, never deleted."""
    _seed_fused_row(body)

    with structlog.testing.capture_logs() as logs:
        sections = _write_and_fetch(**overrides)

    assert sections[DescriptionSection.OTHER_INFORMATION] == body
    assert PropertyDescription.objects.filter(legacy_id="100-villa_info").exists()
    assert any(
        log["event"] == "data_migration.fused_description_kept"
        and log["reason"] == "body_differs_from_legacy_join"
        for log in logs
    )


@pytest.mark.django_db
def test_rerun_never_sweeps_a_loader_row_whose_source_went_blank() -> None:
    """Policy pin: the fused-row drop is a targeted one-off, not a stale-row
    sweep. A row the split loader itself wrote survives a later run where the
    legacy column is blank — the same as every other section has always
    behaved."""
    _write_and_fetch(FeatureDescription="Licence 0829K.", RoomDescription="Rooms blurb")

    sections = _write_and_fetch(FeatureDescription="", RoomDescription="")

    assert sections[DescriptionSection.OTHER_INFORMATION] == "Licence 0829K."
    assert sections[DescriptionSection.ROOMS] == "Rooms blurb"


@pytest.mark.django_db
def test_rerun_keeps_a_hand_written_other_information_row() -> None:
    """Staff copy typed into the Features tab after cutover (no `legacy_id`)
    survives a delta load with a blank source."""
    loader = PropertyLoader()
    loader._process_row(_row(), LoadReport(loader=loader.name))
    prop = Property.objects.get(legacy_id="100")
    PropertyDescription.objects.create(
        property=prop,
        section=DescriptionSection.OTHER_INFORMATION,
        body="Typed by staff",
        legacy_id=None,
    )

    sections = _write_and_fetch(FeatureDescription="")

    assert sections[DescriptionSection.OTHER_INFORMATION] == "Typed by staff"
