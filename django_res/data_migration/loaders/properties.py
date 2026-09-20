"""Property + Location + Capacity + Settings + Description loaders.

The Property loader is the big one: a single VillaMaster row creates five
Django rows (Property + four 1:1 children). Description is multi-row per
property — one per non-empty section.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import unquote, urlsplit

import structlog
from django.db import transaction
from django.utils.text import slugify

from data_migration.base import BaseLoader, LoadReport
from data_migration.loaders._util import legacy_active_sql, live_villa_sql, region_for_legacy_id
from data_migration.loaders.finance import fetch_config_property_default
from data_migration.loaders.sentinels import (
    unknown_country,
    unknown_region,
)
from pricing.models.currency import Currency
from properties.enums import (
    AvailabilityDefault,
    DescriptionSection,
    PrefilledChangeOverDay,
    PriceBasis,
    PropertyChannel,
    PropertyStatus,
)
from properties.models.capacity import PropertyCapacity
from properties.models.descriptions import PropertyDescription
from properties.models.features import Collection, CollectionMembership
from properties.models.geo import Region
from properties.models.location import PropertyLocation
from properties.models.property import Property
from properties.models.settings import PropertySettings
from properties.services.location import location_defaults

logger = structlog.get_logger(__name__)

_PROPERTY_STATUS_MAP = {
    # VillaStatus.Id → PropertyStatus. 3 ("Pending") is a villa still being
    # set up, not a retired one — BUG-030 §2 lands it as DRAFT.
    1: PropertyStatus.ACTIVE,
    2: PropertyStatus.DRAFT,
    3: PropertyStatus.DRAFT,
    4: PropertyStatus.ARCHIVED,
}

# Legacy changeover columns (`VillaMaster.SettingChangeoverDayId`,
# `VillaConfigPropertyDefault.ChangeOverDay`) store `ChangeOverDays.Code`,
# NOT the table's identity Id — the Blazor selects bind `Item1 = [Code]`
# (`PropertyService.GetChangeOverDays` selects `[Code], [Name]`). Seeded
# codes: -1 = Open/flexible, 0 = Sunday, 1 = Monday .. 6 = Saturday.
_DAY_MAP = {
    -1: PrefilledChangeOverDay.ANY,
    0: PrefilledChangeOverDay.SUN,
    1: PrefilledChangeOverDay.MON,
    2: PrefilledChangeOverDay.TUE,
    3: PrefilledChangeOverDay.WED,
    4: PrefilledChangeOverDay.THU,
    5: PrefilledChangeOverDay.FRI,
    6: PrefilledChangeOverDay.SAT,
}


# (VillaMaster flag, VillaMaster setting column, CPD column). Legacy settings
# substitution is flag-only — no `<= 0` branch (`PropertyService2.cs:668-686`).
# Availability and prices-entered are not listed: the loader stamps AVAILABLE
# and GROSS regardless (BUG-028 §2: 91 villas store Net but are flagged to the
# CPD's Gross, and the legacy rate screens price everything as gross anyway).
_SETTING_DEFAULTS = (
    ("IsDefaultSettingCurrencyId", "SettingCurrencyId", "CurrencyId"),
    ("IsDefaultSettingChangeoverDayId", "SettingChangeoverDayId", "ChangeOverDay"),
    ("IsDefaultSettingMinNightsRental", "SettingMinNightsRental", "MinimumNightsRental"),
    ("IsDefaultSettingCheckInTime", "SettingCheckInTime", "CheckinTime"),
    ("IsDefaultSettingCheckOutTime", "SettingCheckOutTime", "CheckOutTime"),
    (
        "IsDefaultSettingBookingreqPreApp",
        "SettingIsBookingsRequirePreApproval",
        "IsBookingsRequirePreApproval",
    ),
)


def _decimal_or_none(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _property_slug(raw: object, name: str, legacy_id: object) -> str:
    """BUG-030 §1: legacy `VillaMaster.Slug` is the villa's full website URL
    (`https://www.villacollective.com/<region>/<slug>/`), so keep only its
    last non-empty path segment; blank → the name. Suffix `-{Id}` for
    uniqueness (legacy slugs collide), without doubling a suffix the legacy
    segment already carries, and fit `Property.slug` (255)."""
    path = urlsplit(str(raw or "").strip()).path
    segment = next((part for part in reversed(path.split("/")) if part), "")
    base = slugify(unquote(segment)) or slugify(name) or "property"
    suffix = f"-{legacy_id}"
    # Exact-id match only: `agios-isavros-438` for villa 8 must still become
    # `agios-isavros-438-8` (legacy slugs collide across villas).
    if base.rsplit("-", 1)[-1] == str(legacy_id):
        base = base[: -len(suffix)]
    return f"{base[: 255 - len(suffix)]}{suffix}"


# GAP-090: the four website blocks on `VillaPropertyImagesDescription`, in
# the order the legacy edit screen lays them out. One column, one section —
# the sub and the para of a block are separately editable.
_BLOCK_COLUMNS: tuple[tuple[str, DescriptionSection], ...] = (
    ("WebDesc1", DescriptionSection.WEB_DES_1),
    ("WebDesc2", DescriptionSection.WEB_DES_2),
    ("Interior1", DescriptionSection.INTERIOR_SUB),
    ("Interior2", DescriptionSection.INTERIOR_PARA),
    ("Exterior1", DescriptionSection.EXTERIOR_SUB),
    ("Exterior2", DescriptionSection.EXTERIOR_PARA),
    ("Location1", DescriptionSection.LOCATION_SUB),
    ("Location2", DescriptionSection.LOCATION_PARA),
)

# The two blocks that had a pre-GAP-090 fused section, as
# (sub section, retired section name, the columns the old join read).
# See `PropertyLoader._drop_fused_block_row`.
_FUSED_BLOCK_ROWS: tuple[tuple[DescriptionSection, str, tuple[str, str]], ...] = (
    (DescriptionSection.WEB_DES_1, "web_description", ("WebDesc1", "WebDesc2")),
    (DescriptionSection.LOCATION_SUB, "location", ("Location1", "Location2")),
)


class PropertyLoader(BaseLoader):
    """VillaMaster -> Property (+ Location + Capacity + Settings + Descriptions).

    All five children are written in the same transaction. Property is the
    canonical legacy_id holder; children use property as their PK so they
    inherit identity from it.
    """

    name = "property"
    target_model = Property
    # `VillaPropertyImagesDescription` holds customer-facing website copy in
    # four column pairs — WebDesc1/2, Interior1/2, Exterior1/2, Location1/2,
    # each a short sub plus a longer para — and a video URL (VodeoUrl, legacy
    # misspelling) not carried by VillaMaster. It is one row per villa except
    # for junk duplicates, so the MAX(Id) subselect pins the join to a single
    # row — mirroring `PropertyImageLoader`.
    #
    # GAP-090: the Interior*/Exterior* columns are read here as description
    # blocks, and `PropertyImageLoader` still reads the same four columns as
    # image captions. That is deliberate, not a double import: the
    # IsInterior1/2 + IsExterior1/2 flags live on `VillaPropertyImages` and
    # mark which *photo* sits beside each block (~1 per villa per slot), so
    # the caption has always been a second rendering of this same prose —
    # 1 572 flagged images carry no `Description` of their own. Dropping
    # either surface would blank the other's copy.
    legacy_query = (
        "SELECT m.Id, m.Name, m.DisplayName, m.Slug, m.OverView, m.HouseRules, "
        "m.FeatureDescription, m.RoomDescription, m.Notes, "
        "m.LocalityRegion, m.LocalityTown, m.AddressLine1, m.AddressLine2, m.AddressLine3, "
        "m.PostCode, m.LicenceNumber, m.Latitude, m.Longitude, "
        "m.Guests, m.AdditionalGuests, m.Bedrooms, m.Ensuites, "
        "m.Bathrooms, m.Size, "
        "m.RegionId, m.ViilaStatus, "
        "m.SettingIsBookingsRequirePreApproval, m.SettingCurrencyId, "
        "m.SettingCheckInTime, m.SettingCheckOutTime, m.SettingChangeoverDayId, "
        "m.SettingMinNightsRental, m.SettingMinNightsRentalNote, "
        f"{', '.join(f'm.{flag}' for flag, _, _ in _SETTING_DEFAULTS)}, "
        "d.WebDesc1, d.WebDesc2, d.Interior1, d.Interior2, "
        "d.Exterior1, d.Exterior2, d.Location1, d.Location2, d.VodeoUrl "
        "FROM VillaMaster m "
        "LEFT JOIN VillaPropertyImagesDescription d ON d.Id = ("
        "SELECT MAX(d2.Id) FROM VillaPropertyImagesDescription d2 "
        "WHERE d2.VillaId = m.Id) "
        f"WHERE {live_villa_sql('m.')}"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        name = (row.get("Name") or "").strip()[:255]
        # Backstop for `live_villa_sql`: T-SQL LTRIM/RTRIM strip only spaces,
        # so a tab/newline-only Name still reaches Python.
        if not name:
            return None

        region = region_for_legacy_id(str(row.get("RegionId") or ""), legacy_id=str(row["Id"]))
        if region is None:
            region = self._sentinel_region()

        return {
            "name": name,
            "display_name": (row.get("DisplayName") or name)[:255],
            "slug": _property_slug(row.get("Slug"), name, row["Id"]),
            "licence_number": (row.get("LicenceNumber") or "").strip()[:128],
            "video_url": (row.get("VodeoUrl") or "").strip()[:200],
            "status": _PROPERTY_STATUS_MAP.get(
                row.get("ViilaStatus") or 0,
                PropertyStatus.DRAFT,
            ),
            "channel": PropertyChannel.DIRECT,
            "region": region,
        }

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        super()._process_row(row, report)
        legacy_id = row.get(self.legacy_pk_column)
        if legacy_id is None:
            return
        prop = Property.objects.filter(legacy_id=str(legacy_id)).first()
        if prop is None:
            return
        with transaction.atomic():
            self._write_location(prop, row)
            self._write_capacity(prop, row)
            self._write_settings(prop, row)
            self._write_descriptions(prop, row)

    def _sentinel_region(self) -> Region:
        # 1:N rows in the source data hit this fallback; resolving the
        # sentinel once per loader saves ~3 queries per missing-FK property.
        if not hasattr(self, "_sentinel_region_cache"):
            self._sentinel_region_cache = unknown_region(unknown_country())
        return self._sentinel_region_cache

    def _write_location(self, prop: Property, row: dict[str, Any]) -> None:
        PropertyLocation.objects.update_or_create(
            property=prop,
            defaults={
                **location_defaults(prop),
                "address_line_1": (row.get("AddressLine1") or "")[:255],
                "address_line_2": (row.get("AddressLine2") or "")[:255],
                "address_line_3": (row.get("AddressLine3") or "")[:255],
                "post_code": (row.get("PostCode") or "")[:32],
                "locality_town": (row.get("LocalityTown") or "")[:128],
                "locality_region": (row.get("LocalityRegion") or "")[:128],
                "latitude": _decimal_or_none(row.get("Latitude")),
                "longitude": _decimal_or_none(row.get("Longitude")),
            },
        )

    def _write_capacity(self, prop: Property, row: dict[str, Any]) -> None:
        size = _decimal_or_none(row.get("Size"))
        PropertyCapacity.objects.update_or_create(
            property=prop,
            defaults={
                "guests": int(row.get("Guests") or 0),
                "additional_guests": int(row.get("AdditionalGuests") or 0),
                "bedrooms": int(row.get("Bedrooms") or 0),
                "ensuites": int(row.get("Ensuites") or 0),
                "bathrooms": int(row.get("Bathrooms") or 0),
                "size_sqm": size,
            },
        )

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        # Fetch the CPD before the per-row savepoints (fail fast), and only
        # when some row is flagged — a flag-less load never touches it.
        if any(row.get(flag) for row in rows for flag, _, _ in _SETTING_DEFAULTS):
            self._cpd()
        super()._load_rows(rows, report)

    def _cpd(self) -> dict[str, Any]:
        if not hasattr(self, "_cpd_cache"):
            self._cpd_cache = fetch_config_property_default()
        return self._cpd_cache

    def _resolve_setting_defaults(self, row: dict[str, Any]) -> dict[str, Any]:
        """BUG-028: a flagged `IsDefaultSetting*` column means the villa uses
        the global CPD value; the stored setting behind it is stale."""
        flagged = [(own, cpd_col) for flag, own, cpd_col in _SETTING_DEFAULTS if row.get(flag)]
        if not flagged:
            return row
        cpd = self._cpd()
        return {**row, **{own: cpd.get(cpd_col) for own, cpd_col in flagged}}

    def _write_settings(self, prop: Property, row: dict[str, Any]) -> None:
        row = self._resolve_setting_defaults(row)
        # NOT `or 0` — 0 is a real code (Sunday), only NULL means unset.
        day_code = row.get("SettingChangeoverDayId")
        changeover = _DAY_MAP.get(day_code) if day_code is not None else None
        currency = (
            Currency.objects.filter(legacy_id=str(row["SettingCurrencyId"])).first()
            if row.get("SettingCurrencyId")
            else None
        )
        PropertySettings.objects.update_or_create(
            property=prop,
            defaults={
                "availability_default": AvailabilityDefault.AVAILABLE,
                "bookings_require_pre_approval": bool(
                    row.get("SettingIsBookingsRequirePreApproval"),
                ),
                "requires_enquiry_first": False,
                "currency": currency,
                "check_in_time": row.get("SettingCheckInTime"),
                "check_out_time": row.get("SettingCheckOutTime"),
                "changeover_day": changeover,
                "min_nights_rental": int(row.get("SettingMinNightsRental") or 1),
                "min_nights_rental_note": (row.get("SettingMinNightsRentalNote") or "")[:1000],
                "prices_entered_as": PriceBasis.GROSS,
            },
        )

    def _write_descriptions(self, prop: Property, row: dict[str, Any]) -> None:
        # Per 09-departures.md: WebsiteDescription/OverView->OVERVIEW;
        # HouseRules->HOUSE_RULES. GAP-091: FeatureDescription (the legacy
        # Features page's "Other information description") -> OTHER_INFORMATION
        # and RoomDescription (the bedrooms blurb, GAP-092) -> ROOMS. They were
        # fused into `villa_info` before 2026-09; see `_drop_fused_row` below.
        sections: dict[str, str] = {}
        if overview := (row.get("OverView") or "").strip():
            sections[DescriptionSection.OVERVIEW] = overview
        if rules := (row.get("HouseRules") or "").strip():
            sections[DescriptionSection.HOUSE_RULES] = rules
        if feat := (row.get("FeatureDescription") or "").strip():
            sections[DescriptionSection.OTHER_INFORMATION] = feat
        if rooms := (row.get("RoomDescription") or "").strip():
            sections[DescriptionSection.ROOMS] = rooms
        # GAP-090: Notes is staff copy, so it lands in INTERNAL_NOTES — write
        # guarded, see `_write_internal_notes`.
        if notes := (row.get("Notes") or "").strip():
            sections[DescriptionSection.INTERNAL_NOTES] = notes
        # Website copy from VillaPropertyImagesDescription (PRESERVE ALL,
        # 2026-07-06). GAP-090: one legacy column per section, so the sub and
        # the para of each block stay separately editable. They used to be
        # fused with a blank line, which no string split could undo.
        for column, block_section in _BLOCK_COLUMNS:
            if text := (row.get(column) or "").strip():
                sections[block_section] = text

        for section, body in sections.items():
            if section == DescriptionSection.INTERNAL_NOTES:
                self._write_internal_notes(prop, row, body)
                continue
            PropertyDescription.objects.update_or_create(
                property=prop,
                section=section,
                defaults={
                    "body": body,
                    "legacy_id": f"{row['Id']}-{section}",
                },
            )
        self._drop_fused_row(prop, row, feat, rooms)
        self._drop_fused_block_row(prop, row)

    @staticmethod
    def _drop_fused_block_row(prop: Property, row: dict[str, Any]) -> None:
        """One-off for DBs loaded before GAP-090 (CUTOVER §6i).

        Migration 0010 parked each fused website body in the block's *sub*
        slot (`web_description` -> `web_des_1`, `location` -> `location_sub`)
        with its pre-0010 provenance intact, on the understanding that this
        re-run would overwrite it with the true part-1 text. That only happens
        when part 1 is non-blank — the old join skipped blanks, so a villa
        with only part 2 (346 Location1 vs 347 Location2 on ResProd) had its
        *para* text parked in the sub slot. The loop above then writes the
        para section and leaves the sub row behind, rendering the same
        paragraph twice with no way to tell which row is stale.

        So: a sub row still carrying pre-0010 provenance after the writes is
        one this re-run did not claim. Drop it — but, exactly as
        `_drop_fused_row` does, only while its body still equals what the old
        join would produce from the current legacy columns. Anything else is
        a staff rewrite and is kept and logged. Interior/Exterior need no
        entry here: they had no pre-GAP-090 section to be parked in.
        """
        for section, retired, columns in _FUSED_BLOCK_ROWS:
            fused = "\n\n".join(
                part for part in ((row.get(c) or "").strip() for c in columns) if part
            )
            for desc in PropertyDescription.objects.filter(
                property=prop, section=section, legacy_id=f"{row['Id']}-{retired}"
            ):
                if desc.body == fused:
                    logger.info(
                        "data_migration.fused_block_dropped",
                        property_id=prop.pk,
                        legacy_id=desc.legacy_id,
                    )
                    desc.delete()
                else:
                    logger.warning(
                        "data_migration.fused_block_kept",
                        property_id=prop.pk,
                        legacy_id=desc.legacy_id,
                        reason="body_differs_from_legacy_join",
                    )

    @staticmethod
    def _write_internal_notes(prop: Property, row: dict[str, Any], body: str) -> None:
        """Create-only: never overwrite staff-written internal notes (GAP-090).

        Every other section is loader-owned, so the `update_or_create` above
        can safely rewrite it on the CUTOVER §6i re-run. `internal_notes` is
        not: it has been an editable staff surface since 2026-08-12, and
        migration 0010 folded the retired `further_info` bodies into the same
        rows. Overwriting would delete copy nobody can recover, so the row is
        written once and then left alone — the same posture as
        `_drop_fused_row`'s refusal to delete copy it cannot prove is its own.

        The *body* is what's protected, not the row's provenance: a kept row
        still stands in for this villa's `VillaMaster.Notes`, so an unstamped
        one (staff-typed) or one migration 0010 renamed off `further_info` is
        re-stamped to the `<Id>-<section>` convention. `reconcile_legacy`
        counts loaded rows by `legacy_id` (`_Check.count_loaded`), so leaving
        those alone reports a false gap against `expected_gap=0`.
        """
        section = DescriptionSection.INTERNAL_NOTES
        legacy_id = f"{row['Id']}-{section}"
        existing, created = PropertyDescription.objects.get_or_create(
            property=prop,
            section=section,
            defaults={"body": body, "legacy_id": legacy_id},
        )
        if created:
            return
        if existing.legacy_id in (None, "", f"{row['Id']}-further_info"):
            existing.legacy_id = legacy_id
            existing.save(update_fields=["legacy_id"])
        if existing.body != body:
            logger.info(
                "data_migration.internal_notes_kept",
                property_id=prop.pk,
                reason="existing_body_not_overwritten",
            )

    @staticmethod
    def _drop_fused_row(prop: Property, row: dict[str, Any], feat: str, rooms: str) -> None:
        """One-off for DBs loaded before GAP-091 (CUTOVER §6e).

        Migration `properties.0007` renamed the fused `villa_info` row to
        `other_information` with its `<Id>-villa_info` provenance intact. When
        `FeatureDescription` is non-blank the `update_or_create` above has just
        rewritten that row in place (body + `legacy_id`), so there is nothing
        left to do. When it is blank the fused text would survive as
        `other_information` for every rooms-only villa, so drop it — but only
        while its body still equals what the old join would produce from the
        current legacy columns. Anything else (staff rewrote it after the
        rename, or legacy changed since) is kept and logged; deleting copy we
        cannot prove is ours is worse than a stale row someone can clear.

        Deliberately not a general stale-row sweep: the loader has never
        removed a description whose legacy source went blank (any section),
        and that policy is unchanged. Per-instance `.delete()` so the
        `PropertyDescription` audit tombstone is written.
        """
        fused = "\n\n".join(p for p in (feat, rooms) if p)
        for desc in PropertyDescription.objects.filter(
            property=prop,
            section=DescriptionSection.OTHER_INFORMATION,
            legacy_id=f"{row['Id']}-villa_info",
        ):
            if desc.body == fused:
                logger.info(
                    "data_migration.fused_description_dropped",
                    property_id=prop.pk,
                    legacy_id=desc.legacy_id,
                )
                desc.delete()
            else:
                logger.warning(
                    "data_migration.fused_description_kept",
                    property_id=prop.pk,
                    legacy_id=desc.legacy_id,
                    reason="body_differs_from_legacy_join",
                )


class CollectionLoader(BaseLoader):
    """Live `VillaCollection` rows only. Five collections deleted together on
    2024-05-28 ("Chef Included" 66, "Exceptional Design" 55, "Walk to
    restaurants" 34, "Water Front" 59, "WALK TO THE BEACH" 67) are dropped
    with their 283 live memberships — BUG-030 §13 decision (2026-09-11).
    """

    name = "collection"
    target_model = Collection
    legacy_query = "SELECT Id, Name, Description FROM VillaCollection WHERE DeletedAt IS NULL"

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        name = (row.get("Name") or "").strip()[:128]
        if not name:
            return None
        slug = slugify(name)[:120] + f"-{row['Id']}"
        return {
            "name": name,
            "slug": slug[:128],
            "description": (row.get("Description") or "").strip(),
            "is_active": True,
        }


class CollectionMembershipLoader(BaseLoader):
    """`VillaCollectionsMappings` → CollectionMembership. Rows on a deleted
    collection or an unloaded villa skip (see `CollectionLoader`); duplicate
    (collection, villa) pairs keep the first row in query order. The
    reconcile gap itemises those buckets.
    """

    name = "collection_membership"
    target_model = CollectionMembership
    legacy_query = (
        "SELECT Id, VillaMasterId, VillaCollectionId, VillaOrder, Description "
        # GAP-108: inactive (incl. NULL) memberships are soft-deleted in ResProd.
        # NULL = the pre-soft-delete generation (Ids 2-1984); the admin view
        # `vw_getVillaCollectionsMap` hides it and `sp_getVillaByCollection`
        # re-inserts live mappings with IsActive = 1.
        f"FROM VillaCollectionsMappings WHERE {legacy_active_sql()} "
        # Duplicate pairs keep the lowest VillaOrder (NULL last), then lowest Id.
        "ORDER BY VillaMasterId, VillaCollectionId, ISNULL(VillaOrder, 2147483647), Id"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        prop = Property.objects.filter(legacy_id=str(row.get("VillaMasterId") or "")).first()
        coll = Collection.objects.filter(legacy_id=str(row.get("VillaCollectionId") or "")).first()
        if prop is None or coll is None:
            return None
        # Legacy has multiple mapping rows for the same (collection, property)
        # — keep the first in query order (lowest VillaOrder).
        existing = (
            CollectionMembership.objects.filter(property=prop, collection=coll)
            .exclude(legacy_id=str(row["Id"]))
            .exists()
        )
        if existing:
            return None
        return {
            "property": prop,
            "collection": coll,
            "sort_order": int(row.get("VillaOrder") or 0),
            "description": (row.get("Description") or "").strip(),
        }
