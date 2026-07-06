from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, cast

import pytest
import structlog.testing
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from accounts.factories import PersonFactory
from accounts.models import Person
from data_migration.base import LoadReport
from data_migration.loaders import integrations as integrations_module
from data_migration.loaders.integrations import (
    SyncRecordZohoLoader,
    _ZohoSpec,
    zoho_id_column_exists,
)
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
        "SELECT Id, ZohoId, CreatedAt, UpdatedAt FROM VillaMaster ORDER BY Id"
    )


def test_query_omits_timestamps_when_absent() -> None:
    loader = SyncRecordZohoLoader()
    assert loader._query(_contact_spec()) == ("SELECT Id, ZohoId FROM VillaContact ORDER BY Id")


def test_query_orders_by_id_for_deterministic_duplicate_resolution() -> None:
    # When two source rows share one ZohoId (VillaMaster 88 & 339), the link
    # must attach to the lowest legacy Id reproducibly — so every fetch is
    # ordered by Id, including the --since delta path.
    loader = SyncRecordZohoLoader(since="2026-05-13T17:00:00")
    assert loader._query(_property_spec()).endswith("ORDER BY Id")


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


# --- ZohoId column probe (live dump has no ZohoId on two of the five tables) ---


class _FakeLegacyCursor:
    """Scripted legacy cursor: answers the INFORMATION_SCHEMA probe from
    `zoho_tables` and returns zero data rows for every `SELECT Id, ZohoId ...`.
    Records executed queries so tests can assert absent tables are never
    queried for data."""

    description = (("Id",), ("ZohoId",))

    def __init__(self, zoho_tables: set[str]) -> None:
        self.zoho_tables = zoho_tables
        self.queries: list[str] = []
        self._scalar = 0

    def execute(self, query: str) -> None:
        self.queries.append(query)
        if "INFORMATION_SCHEMA.COLUMNS" in query:
            # The probe quotes the exact table name, so 'VillaMaster' can't
            # false-positive against 'VillaQuotationMaster'.
            self._scalar = int(any(f"'{t}'" in query for t in self.zoho_tables))

    def fetchone(self) -> tuple[int]:
        return (self._scalar,)

    def __iter__(self) -> Iterator[tuple[Any, ...]]:
        return iter(())


def test_zoho_id_column_probe_hits_information_schema() -> None:
    cursor = _FakeLegacyCursor(zoho_tables={"VillaMaster"})

    assert zoho_id_column_exists(cursor, "VillaMaster") is True
    assert zoho_id_column_exists(cursor, "VillaQuotationMaster") is False
    assert all("INFORMATION_SCHEMA.COLUMNS" in q for q in cursor.queries)
    assert all("ZohoId" in q for q in cursor.queries)


@pytest.mark.django_db
def test_load_skips_tables_without_zoho_id_column(monkeypatch: pytest.MonkeyPatch) -> None:
    """The 24-Apr-2025 prod dump has no ZohoId on VillaQuotationMaster or
    VillaBooking — the loader must skip them with a warning instead of
    crashing, and still sweep the three tables that do carry the column."""
    cursor = _FakeLegacyCursor(zoho_tables={"VillaMaster", "VillaContact", "VillaEnquire"})

    @contextmanager
    def _fake_cursor() -> Iterator[_FakeLegacyCursor]:
        yield cursor

    monkeypatch.setattr(integrations_module, "legacy_cursor", _fake_cursor)

    with structlog.testing.capture_logs() as logs:
        report = SyncRecordZohoLoader().load()

    selects = [q for q in cursor.queries if q.startswith("SELECT Id, ZohoId")]
    assert len(selects) == 3
    assert not any("VillaQuotationMaster" in q or "VillaBooking" in q for q in selects)
    missing = [entry for entry in logs if entry["event"] == "data_migration.zoho_column_missing"]
    assert {entry["table"] for entry in missing} == {"VillaQuotationMaster", "VillaBooking"}
    assert report.errors == []


@pytest.mark.django_db
def test_load_queries_all_tables_when_column_present(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = _FakeLegacyCursor(zoho_tables={spec.table for spec in SyncRecordZohoLoader.SPECS})

    @contextmanager
    def _fake_cursor() -> Iterator[_FakeLegacyCursor]:
        yield cursor

    monkeypatch.setattr(integrations_module, "legacy_cursor", _fake_cursor)

    with structlog.testing.capture_logs() as logs:
        SyncRecordZohoLoader().load()

    selects = [q for q in cursor.queries if q.startswith("SELECT Id, ZohoId")]
    assert len(selects) == 5
    assert not any(entry["event"] == "data_migration.zoho_column_missing" for entry in logs)


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
def test_duplicate_external_id_on_another_target_is_a_counted_skip() -> None:
    """Duplicate source rows sharing one ZohoId are a legacy data reality
    (VillaMaster 88 & 339 are both "Temenos"): the SyncRecord attaches to the
    first loaded row and the duplicate is a deliberate, counted skip with a
    warning — not a load failure. An error row here would make every cutover
    run exit 1 under loadlegacy's strict exit behaviour."""
    PropertyFactory(legacy_id="14")
    PropertyFactory(legacy_id="15")
    loader = SyncRecordZohoLoader()
    report = LoadReport(loader=loader.name)

    loader._process_row(
        _property_spec(),
        {"Id": 14, "ZohoId": "DUP", "CreatedAt": None, "UpdatedAt": None},
        report,
    )
    with structlog.testing.capture_logs() as logs:
        loader._process_row(
            _property_spec(),
            {"Id": 15, "ZohoId": "DUP", "CreatedAt": None, "UpdatedAt": None},
            report,
        )

    # The second row would violate unique(provider, external_id); skipped
    # (never allowed to raise and poison the transaction), not an error.
    assert SyncRecord.objects.count() == 1
    assert report.errors == []
    assert report.created == 1 and report.skipped == 1
    (entry,) = [e for e in logs if e["event"] == "data_migration.zoho_id_duplicate"]
    assert entry["table"] == "VillaMaster"
    assert entry["legacy_pk"] == 15
    assert entry["zoho_id"] == "DUP"
    assert entry["existing_target"] == f"property:{SyncRecord.objects.get().object_id}"
