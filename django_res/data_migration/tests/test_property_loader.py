from __future__ import annotations

from datetime import time
from decimal import Decimal

import pytest
import structlog
from django.contrib.contenttypes.models import ContentType

from core.models import AuditLog
from data_migration.base import LoadReport
from data_migration.loaders.properties import PropertyLoader
from data_migration.loaders.sentinels import unknown_country, unknown_region
from pricing.models.currency import Currency
from properties.enums import DescriptionSection, PrefilledChangeOverDay, PropertyStatus
from properties.models.descriptions import PropertyDescription
from properties.models.geo import Country, Region
from properties.models.property import Property
from properties.models.settings import PropertySettings


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": 100,
        "Name": "Casa Test",
        "DisplayName": "Casa Test",
        "Slug": "https://www.villacollective.com/paxos/casa-test-100/",
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
def test_web_description_parts_land_in_separate_sections() -> None:
    sections = _write_and_fetch(WebDesc1="  Marketing copy  ", WebDesc2="  Activities  ")
    assert sections[DescriptionSection.WEB_DES_1] == "Marketing copy"
    assert sections[DescriptionSection.WEB_DES_2] == "Activities"


@pytest.mark.django_db
def test_web_description_single_part_writes_one_section() -> None:
    sections = _write_and_fetch(WebDesc1="Only first", WebDesc2="")
    assert sections[DescriptionSection.WEB_DES_1] == "Only first"
    assert DescriptionSection.WEB_DES_2 not in sections


@pytest.mark.django_db
def test_legacy_overview_is_dropped_not_remapped() -> None:
    """`VillaMaster.OverView` is retired (2026-09-22): its 8 ResProd rows are
    an expected loss. It must never land in `web_des_1` — that section is
    widely populated from `WebDesc1` and the two were different copy."""
    sections = _write_and_fetch(OverView="Scant overview text", WebDesc1="", WebDesc2="")
    assert "overview" not in sections
    assert DescriptionSection.WEB_DES_1 not in sections


@pytest.mark.django_db
def test_legacy_overview_never_joins_web_des_1() -> None:
    """6 of the 8 villas hold both columns: `web_des_1` is `WebDesc1` verbatim,
    with no appended or prepended `OverView` text."""
    sections = _write_and_fetch(OverView="Scant overview text", WebDesc1="Top text")
    assert sections[DescriptionSection.WEB_DES_1] == "Top text"
    assert "overview" not in sections


@pytest.mark.django_db
def test_location_parts_land_in_separate_sections() -> None:
    sections = _write_and_fetch(Location1="Near the beach", Location2="10 min to town")
    assert sections[DescriptionSection.LOCATION_SUB] == "Near the beach"
    assert sections[DescriptionSection.LOCATION_PARA] == "10 min to town"


@pytest.mark.django_db
def test_interior_parts_land_in_separate_sections() -> None:
    sections = _write_and_fetch(Interior1="  Ensuite bedrooms  ", Interior2="  Soft linen  ")
    assert sections[DescriptionSection.INTERIOR_SUB] == "Ensuite bedrooms"
    assert sections[DescriptionSection.INTERIOR_PARA] == "Soft linen"


@pytest.mark.django_db
def test_exterior_parts_land_in_separate_sections() -> None:
    sections = _write_and_fetch(Exterior1="  Infinity pool  ", Exterior2="  Shaded terraces  ")
    assert sections[DescriptionSection.EXTERIOR_SUB] == "Infinity pool"
    assert sections[DescriptionSection.EXTERIOR_PARA] == "Shaded terraces"


@pytest.mark.django_db
def test_each_block_column_is_stamped_with_its_own_section() -> None:
    loader = PropertyLoader()
    loader._process_row(_row(Interior1="Sub", Interior2="Para"), LoadReport(loader=loader.name))
    prop = Property.objects.get(legacy_id="100")
    stamps = {d.section: d.legacy_id for d in PropertyDescription.objects.filter(property=prop)}
    assert stamps[DescriptionSection.INTERIOR_SUB] == "100-interior_sub"
    assert stamps[DescriptionSection.INTERIOR_PARA] == "100-interior_para"


@pytest.mark.django_db
def test_no_website_copy_writes_no_extra_sections() -> None:
    sections = _write_and_fetch()
    for section in (
        DescriptionSection.WEB_DES_1,
        DescriptionSection.WEB_DES_2,
        DescriptionSection.INTERIOR_SUB,
        DescriptionSection.INTERIOR_PARA,
        DescriptionSection.EXTERIOR_SUB,
        DescriptionSection.EXTERIOR_PARA,
        DescriptionSection.LOCATION_SUB,
        DescriptionSection.LOCATION_PARA,
    ):
        assert section not in sections


# GAP-090 §6i repair: migration 0010 parked each fused body in the *sub* slot
# (`web_description` -> `web_des_1`, `location` -> `location_sub`) for the
# re-run to overwrite. That only lands when part 1 is non-blank — on ResProd
# Location1 is set on 346 villas and Location2 on 347 — so a part-2-only villa
# would otherwise keep the sub row *and* gain an identical para row.


def _seed_fused(prop: Property, section: str, old_section: str, body: str) -> PropertyDescription:
    return PropertyDescription.objects.create(
        property=prop, section=section, body=body, legacy_id=f"100-{old_section}"
    )


@pytest.mark.django_db
def test_rerun_drops_the_fused_sub_row_when_only_part_two_survives() -> None:
    loader = PropertyLoader()
    loader._process_row(_row(), LoadReport(loader=loader.name))
    prop = Property.objects.get(legacy_id="100")
    _seed_fused(prop, DescriptionSection.LOCATION_SUB, "location", "10 min to town")

    loader._process_row(_row(Location1="", Location2="10 min to town"), LoadReport(loader="p"))

    sections = {d.section: d.body for d in PropertyDescription.objects.filter(property=prop)}
    assert sections == {DescriptionSection.LOCATION_PARA: "10 min to town"}


@pytest.mark.django_db
def test_rerun_rewrites_the_sub_row_in_place_when_part_one_survives() -> None:
    loader = PropertyLoader()
    loader._process_row(_row(), LoadReport(loader=loader.name))
    prop = Property.objects.get(legacy_id="100")
    _seed_fused(prop, DescriptionSection.WEB_DES_1, "web_description", "Sub\n\nPara")

    loader._process_row(_row(WebDesc1="Sub", WebDesc2="Para"), LoadReport(loader="p"))

    rows = {d.section: d for d in PropertyDescription.objects.filter(property=prop)}
    assert rows[DescriptionSection.WEB_DES_1].body == "Sub"
    assert rows[DescriptionSection.WEB_DES_1].legacy_id == "100-web_des_1"
    assert rows[DescriptionSection.WEB_DES_2].body == "Para"


@pytest.mark.django_db
def test_rerun_keeps_a_fused_sub_row_a_staff_edit_has_changed() -> None:
    loader = PropertyLoader()
    loader._process_row(_row(), LoadReport(loader=loader.name))
    prop = Property.objects.get(legacy_id="100")
    _seed_fused(prop, DescriptionSection.LOCATION_SUB, "location", "Staff rewrote this")

    with structlog.testing.capture_logs() as logs:
        loader._process_row(_row(Location1="", Location2="10 min to town"), LoadReport(loader="p"))

    sections = {d.section: d.body for d in PropertyDescription.objects.filter(property=prop)}
    assert sections[DescriptionSection.LOCATION_SUB] == "Staff rewrote this"
    assert any(entry["event"] == "data_migration.fused_block_kept" for entry in logs)


# GAP-090: `VillaMaster.Notes` is staff copy, so it loads into INTERNAL_NOTES
# (the retired FURTHER_INFO section) — and, uniquely, never overwrites.


@pytest.mark.django_db
def test_notes_load_into_internal_notes() -> None:
    sections = _write_and_fetch(Notes="  Gate code is on the key safe.  ")
    assert sections[DescriptionSection.INTERNAL_NOTES] == "Gate code is on the key safe."


@pytest.mark.django_db
def test_existing_internal_notes_body_is_never_overwritten() -> None:
    _write_and_fetch(Notes="Legacy note")
    prop = Property.objects.get(legacy_id="100")
    row = PropertyDescription.objects.get(property=prop, section=DescriptionSection.INTERNAL_NOTES)
    row.body = "Staff rewrote this after cutover"
    row.save(update_fields=["body"])

    with structlog.testing.capture_logs() as logs:
        sections = _write_and_fetch(Notes="Legacy note")

    assert sections[DescriptionSection.INTERNAL_NOTES] == "Staff rewrote this after cutover"
    assert any(entry["event"] == "data_migration.internal_notes_kept" for entry in logs)


@pytest.mark.django_db
def test_kept_internal_notes_row_is_re_stamped_with_its_provenance() -> None:
    """A staff-typed row, and one migration 0010 renamed off `further_info`,
    both stand in for this villa's `VillaMaster.Notes` — `reconcile_legacy`
    counts loaded rows by `legacy_id`, so an unstamped one is a false gap.
    """
    loader = PropertyLoader()
    loader._process_row(_row(), LoadReport(loader=loader.name))
    prop = Property.objects.get(legacy_id="100")
    staff_row = PropertyDescription.objects.create(
        property=prop,
        section=DescriptionSection.INTERNAL_NOTES,
        body="Typed by staff",
        legacy_id=None,
    )

    loader._process_row(_row(Notes="Legacy note"), LoadReport(loader=loader.name))

    staff_row.refresh_from_db()
    assert staff_row.body == "Typed by staff"
    assert staff_row.legacy_id == "100-internal_notes"


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


# --- BUG-028: IsDefaultSetting* flags resolve to the legacy CPD row --------

_CPD = {
    "CurrencyId": 3,
    "ChangeOverDay": -1,
    "MinimumNightsRental": Decimal("7.00"),
    "CheckinTime": time(16, 0),
    "CheckOutTime": time(10, 0),
    "IsBookingsRequirePreApproval": True,
}


def _settings_for(loader: PropertyLoader, **overrides: object) -> PropertySettings:
    loader._process_row(_row(**overrides), LoadReport(loader=loader.name))
    return PropertySettings.objects.get(property__legacy_id="100")


@pytest.mark.django_db
def test_flagged_settings_take_the_cpd_values() -> None:
    eur = Currency.objects.create(code="EUR", name="Euro", legacy_id="3")
    loader = PropertyLoader()
    loader._cpd_cache = _CPD
    settings = _settings_for(
        loader,
        IsDefaultSettingCurrencyId=True,
        SettingCurrencyId=2,  # the deleted EUR twin, stale behind the flag
        IsDefaultSettingChangeoverDayId=True,
        SettingChangeoverDayId=0,
        IsDefaultSettingMinNightsRental=True,
        SettingMinNightsRental=0,
        IsDefaultSettingCheckInTime=True,
        SettingCheckInTime=None,
        IsDefaultSettingCheckOutTime=-1,  # any truthy flag counts
        SettingCheckOutTime=time(11, 0),
        IsDefaultSettingBookingreqPreApp=True,
        SettingIsBookingsRequirePreApproval=False,
    )
    assert settings.currency == eur
    assert settings.changeover_day == PrefilledChangeOverDay.ANY
    assert settings.min_nights_rental == 7
    assert settings.check_in_time == time(16, 0)
    assert settings.check_out_time == time(10, 0)
    assert settings.bookings_require_pre_approval is True


@pytest.mark.django_db
def test_unflagged_settings_keep_their_own_values_even_when_zero() -> None:
    # Settings substitution is flag-only in legacy (no `<= 0` branch):
    # changeover 0 is a real Sunday and min nights 0 keeps the floor of 1.
    loader = PropertyLoader()  # no CPD cache: must never be fetched
    settings = _settings_for(
        loader,
        IsDefaultSettingChangeoverDayId=False,
        SettingChangeoverDayId=0,
        IsDefaultSettingMinNightsRental=None,
        SettingMinNightsRental=0,
    )
    assert settings.changeover_day == PrefilledChangeOverDay.SUN
    assert settings.min_nights_rental == 1
    assert not hasattr(loader, "_cpd_cache")


def test_property_query_selects_the_setting_flags() -> None:
    for flag in (
        "IsDefaultSettingCurrencyId",
        "IsDefaultSettingChangeoverDayId",
        "IsDefaultSettingMinNightsRental",
        "IsDefaultSettingCheckInTime",
        "IsDefaultSettingCheckOutTime",
        "IsDefaultSettingBookingreqPreApp",
    ):
        assert f"m.{flag}" in PropertyLoader.legacy_query


@pytest.mark.django_db
def test_load_rows_fetches_cpd_once_up_front_when_a_row_is_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from data_migration.loaders import properties as properties_module

    calls: list[int] = []

    def _missing() -> dict[str, object]:
        calls.append(1)
        raise RuntimeError("VillaConfigPropertyDefault has no row")

    monkeypatch.setattr(properties_module, "fetch_config_property_default", _missing)
    loader = PropertyLoader()
    with pytest.raises(RuntimeError):
        loader._load_rows(
            [_row(), _row(Id=101, IsDefaultSettingCurrencyId=True)],
            LoadReport(loader=loader.name),
        )
    assert calls == [1]


# --- BUG-030 §1 slug / §2 status / §8 region remap / unused SELECT columns ---


@pytest.mark.django_db
@pytest.mark.parametrize(
    "raw_slug",
    [
        "https://www.villacollective.com/paxos/agios-isavros/",
        "https://www.villacollective.com/paxos/agios-isavros",
        "agios-isavros",
    ],
)
def test_slug_is_the_last_url_segment_suffixed_with_the_legacy_id(raw_slug: str) -> None:
    # BUG-030 §1: legacy `Slug` is a full website URL, not a slug. Keep the
    # last non-empty path segment, slugify it, and suffix `-{Id}`.
    kwargs = PropertyLoader().transform(_row(Id=438, Slug=raw_slug))
    assert kwargs is not None
    assert kwargs["slug"] == "agios-isavros-438"


@pytest.mark.django_db
def test_slug_does_not_double_the_legacy_id_suffix() -> None:
    kwargs = PropertyLoader().transform(
        _row(Id=438, Slug="https://www.villacollective.com/paxos/agios-isavros-438/")
    )
    assert kwargs is not None
    assert kwargs["slug"] == "agios-isavros-438"


@pytest.mark.django_db
def test_slug_only_strips_an_exact_legacy_id_suffix() -> None:
    # Villa 8 carrying villa 438's URL (legacy slugs collide) must not land on
    # `agios-isavros-438` — the unique slug of villa 438.
    kwargs = PropertyLoader().transform(
        _row(Id=8, Slug="https://www.villacollective.com/paxos/agios-isavros-438/")
    )
    assert kwargs is not None
    assert kwargs["slug"] == "agios-isavros-438-8"


@pytest.mark.django_db
def test_slug_unquotes_a_percent_encoded_segment() -> None:
    kwargs = PropertyLoader().transform(
        _row(Id=7, Slug="https://www.villacollective.com/paxos/villa-%C3%81rtemis/")
    )
    assert kwargs is not None
    assert kwargs["slug"] == "villa-artemis-7"


@pytest.mark.django_db
def test_slug_never_collapses_to_a_bare_suffix() -> None:
    kwargs = PropertyLoader().transform(
        _row(Id=7, Name="Βίλα Άρτεμις", Slug="https://www.villacollective.com/paxos/βίλα-άρτεμις/")
    )
    assert kwargs is not None
    assert kwargs["slug"] == "property-7"


@pytest.mark.django_db
def test_blank_slug_falls_back_to_the_name() -> None:
    kwargs = PropertyLoader().transform(_row(Id=7, Slug="   ", Name="Villa Ártemis"))
    assert kwargs is not None
    assert kwargs["slug"] == "villa-artemis-7"


@pytest.mark.django_db
@pytest.mark.parametrize("raw_slug", ["x" * 400, "x" * 400 + "-7"])
def test_slug_is_truncated_to_the_column_width_keeping_the_suffix(raw_slug: str) -> None:
    kwargs = PropertyLoader().transform(_row(Id=7, Slug=raw_slug))
    assert kwargs is not None
    assert len(kwargs["slug"]) <= 255
    assert kwargs["slug"].endswith("-7")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("legacy_status", "expected"),
    [
        (1, PropertyStatus.ACTIVE),
        (2, PropertyStatus.DRAFT),
        (3, PropertyStatus.DRAFT),  # BUG-030 §2: legacy "Pending" is not archived
        (4, PropertyStatus.ARCHIVED),
        (None, PropertyStatus.DRAFT),
    ],
)
def test_status_map(legacy_status: int | None, expected: PropertyStatus) -> None:
    kwargs = PropertyLoader().transform(_row(ViilaStatus=legacy_status))
    assert kwargs is not None
    assert kwargs["status"] == expected


@pytest.mark.django_db
@pytest.mark.parametrize(("legacy_region", "remapped_to"), [(25, "61"), (27, "60")])
def test_remapped_regions_resolve_to_their_live_twin_and_log(
    legacy_region: int, remapped_to: str
) -> None:
    # BUG-030 §8: legacy regions 25 and 27 are duplicates of 61 and 60.
    country = Country.objects.get(iso2="GR")
    twin = Region.objects.create(
        country=country,
        name=f"Twin {remapped_to}",
        slug=f"twin-{remapped_to}",
        legacy_id=remapped_to,
    )
    with structlog.testing.capture_logs() as logs:
        kwargs = PropertyLoader().transform(_row(Id=100, RegionId=legacy_region))
    assert kwargs is not None
    assert kwargs["region"].pk == twin.pk
    assert any(
        log["event"] == "data_migration.region_remapped"
        and log["legacy_region_id"] == str(legacy_region)
        and log["remapped_to"] == remapped_to
        and log["legacy_id"] == "100"
        for log in logs
    )


def test_property_query_drops_the_unused_columns() -> None:
    for column in (
        "m.Channel",
        "m.SettingAvailabilityStatusId",
        "m.SettingPricesEnteredTypeId",
    ):
        assert column not in PropertyLoader.legacy_query


def test_property_query_filters_to_live_named_villas() -> None:
    # GAP-108: the blank-name skip lives in SQL too (shared with reconcile via
    # `live_villa_sql`); `transform`'s `.strip()` guard stays as a backstop.
    from data_migration.loaders._util import live_villa_sql

    assert PropertyLoader.legacy_query.endswith(f"WHERE {live_villa_sql('m.')}")
