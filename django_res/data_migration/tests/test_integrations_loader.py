from __future__ import annotations

from datetime import datetime
from typing import cast

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from accounts.factories import PersonFactory
from accounts.models import Person
from data_migration.base import LoadReport
from data_migration.loaders.integrations import SyncRecordZohoLoader, _ZohoSpec
from integrations.enums import SyncDirection, SyncProvider, SyncStatus
from integrations.models import SyncRecord
from properties.factories import PropertyFactory
from properties.models.property import Property


def _property_spec() -> _ZohoSpec:
    return _ZohoSpec(table="VillaMaster", model=Property, has_timestamps=True)


def _contact_spec() -> _ZohoSpec:
    return _ZohoSpec(table="VillaContact", model=Person, has_timestamps=False)


# --- pure query-builder tests (no DB) ---


def test_query_includes_timestamps_when_present() -> None:
    loader = SyncRecordZohoLoader()
    assert loader._query(_property_spec()) == (
        "SELECT Id, ZohoId, CreatedAt, UpdatedAt FROM VillaMaster"
    )


def test_query_omits_timestamps_when_absent() -> None:
    loader = SyncRecordZohoLoader()
    assert loader._query(_contact_spec()) == "SELECT Id, ZohoId FROM VillaContact"


def test_query_applies_since_only_to_timestamped_tables() -> None:
    loader = SyncRecordZohoLoader(since="2026-05-13T17:00:00")
    assert "UpdatedAt > '2026-05-13T17:00:00'" in loader._query(_property_spec())
    # VillaContact has no UpdatedAt column → --since is silently ignored
    # (mirrors the documented behaviour for timestamp-less legacy tables).
    assert "UpdatedAt" not in loader._query(_contact_spec())


def test_specs_cover_all_five_zoho_tables() -> None:
    tables = {spec.table for spec in SyncRecordZohoLoader.SPECS}
    assert tables == {
        "VillaMaster",
        "VillaContact",
        "VillaEnquire",
        "VillaQuotationMaster",
        "VillaBooking",
    }


# --- behaviour tests (DB) ---


@pytest.mark.django_db
def test_non_blank_zoho_id_creates_sync_record() -> None:
    prop = cast(Property, PropertyFactory(legacy_id="10"))
    loader = SyncRecordZohoLoader()
    report = LoadReport(loader=loader.name)
    updated = datetime(2026, 1, 2, 3, 4, 5)

    loader._process_row(
        _property_spec(),
        {"Id": 10, "ZohoId": "ZCRM_555", "CreatedAt": datetime(2025, 1, 1), "UpdatedAt": updated},
        report,
    )

    rec = SyncRecord.objects.get()
    assert rec.provider == SyncProvider.ZOHO_CRM
    assert rec.external_id == "ZCRM_555"
    assert rec.object_id == prop.pk
    assert rec.content_type == ContentType.objects.get_for_model(Property)
    assert rec.direction == SyncDirection.PUSH
    assert rec.status == SyncStatus.IN_SYNC
    assert rec.last_pushed_at == timezone.make_aware(updated)
    assert report.created == 1 and report.skipped == 0


@pytest.mark.django_db
def test_falls_back_to_created_at_when_no_updated_at() -> None:
    PropertyFactory(legacy_id="11")
    loader = SyncRecordZohoLoader()
    report = LoadReport(loader=loader.name)
    created = datetime(2025, 6, 1, 12, 0, 0)

    loader._process_row(
        _property_spec(),
        {"Id": 11, "ZohoId": "Z1", "CreatedAt": created, "UpdatedAt": None},
        report,
    )

    assert SyncRecord.objects.get().last_pushed_at == timezone.make_aware(created)


@pytest.mark.django_db
def test_contact_without_timestamps_has_null_last_pushed_at() -> None:
    contact = cast(Person, PersonFactory(legacy_id="20"))
    loader = SyncRecordZohoLoader()
    report = LoadReport(loader=loader.name)

    loader._process_row(_contact_spec(), {"Id": 20, "ZohoId": "Z2"}, report)

    rec = SyncRecord.objects.get()
    assert rec.object_id == contact.pk
    assert rec.content_type == ContentType.objects.get_for_model(Person)
    assert rec.last_pushed_at is None


@pytest.mark.django_db
@pytest.mark.parametrize("zoho_id", ["", "   ", None])
def test_blank_zoho_id_is_skipped(zoho_id: str | None) -> None:
    PropertyFactory(legacy_id="12")
    loader = SyncRecordZohoLoader()
    report = LoadReport(loader=loader.name)

    loader._process_row(
        _property_spec(),
        {"Id": 12, "ZohoId": zoho_id, "CreatedAt": None, "UpdatedAt": None},
        report,
    )

    assert SyncRecord.objects.count() == 0
    assert report.skipped == 1 and report.created == 0


@pytest.mark.django_db
def test_unresolvable_legacy_id_is_skipped_and_counted() -> None:
    # No Property with legacy_id="999" exists — a SyncRecord must point at a
    # real row, so this is skipped (and counted), never sentinel-mapped.
    loader = SyncRecordZohoLoader()
    report = LoadReport(loader=loader.name)

    loader._process_row(
        _property_spec(),
        {"Id": 999, "ZohoId": "Z3", "CreatedAt": None, "UpdatedAt": None},
        report,
    )

    assert SyncRecord.objects.count() == 0
    assert report.skipped == 1


@pytest.mark.django_db
def test_rerun_is_idempotent_and_updates_drifted_external_id() -> None:
    PropertyFactory(legacy_id="13")
    loader = SyncRecordZohoLoader()
    row = {"Id": 13, "ZohoId": "Z4", "CreatedAt": None, "UpdatedAt": datetime(2026, 1, 1)}

    first = LoadReport(loader=loader.name)
    loader._process_row(_property_spec(), row, first)
    second = LoadReport(loader=loader.name)
    loader._process_row(_property_spec(), {**row, "ZohoId": "Z4-renamed"}, second)

    assert SyncRecord.objects.count() == 1
    assert first.created == 1 and second.updated == 1
    assert SyncRecord.objects.get().external_id == "Z4-renamed"


@pytest.mark.django_db
def test_duplicate_external_id_on_another_target_is_an_error() -> None:
    PropertyFactory(legacy_id="14")
    PropertyFactory(legacy_id="15")
    loader = SyncRecordZohoLoader()
    report = LoadReport(loader=loader.name)

    loader._process_row(
        _property_spec(),
        {"Id": 14, "ZohoId": "DUP", "CreatedAt": None, "UpdatedAt": None},
        report,
    )
    loader._process_row(
        _property_spec(),
        {"Id": 15, "ZohoId": "DUP", "CreatedAt": None, "UpdatedAt": None},
        report,
    )

    # The second row would violate unique(provider, external_id); recorded as
    # an error rather than allowed to poison the transaction.
    assert SyncRecord.objects.count() == 1
    assert len(report.errors) == 1
