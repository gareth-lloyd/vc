"""`PropertyContactAssignmentLoader._process_row` (BUG-030 test-coverage
sweep)."""

from __future__ import annotations

from datetime import date

import pytest

from accounts.enums import ContactRole
from accounts.factories import PersonFactory
from data_migration.base import LoadReport
from data_migration.loaders.reservations import PropertyContactAssignmentLoader
from properties.factories import PropertyFactory
from properties.models.contacts import PropertyContactAssignment

pytestmark = pytest.mark.django_db


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "MappingId": 11,
        "PropertyId": "500",
        "ContactId": "70",
        "IsPrimaryContact": 1,
        "RoleId": 10,
        "RoleMappingId": 3,
    }
    row.update(overrides)
    return row


def _load(*rows: dict[str, object]) -> LoadReport:
    loader = PropertyContactAssignmentLoader()
    report = LoadReport(loader=loader.name)
    for row in rows:
        loader._process_row(row, report)
    return report


def test_process_row_creates_a_composite_keyed_assignment() -> None:
    prop = PropertyFactory(legacy_id="500")
    person = PersonFactory(legacy_id="70")

    report = _load(_row())

    assert (report.created, report.updated, report.skipped) == (1, 0, 0)
    assignment = PropertyContactAssignment.objects.get(legacy_id="11-10")
    assert assignment.property == prop
    assert assignment.contact == person
    assert assignment.role == ContactRole.OWNER
    assert assignment.is_primary is True


def test_process_row_without_a_role_mapping_keys_on_zero_and_defaults_to_owner() -> None:
    PropertyFactory(legacy_id="500")
    PersonFactory(legacy_id="70")

    _load(_row(RoleId=None, RoleMappingId=-11, IsPrimaryContact=0))

    assignment = PropertyContactAssignment.objects.get(legacy_id="11-0")
    assert assignment.role == ContactRole.OWNER
    assert assignment.is_primary is False


def test_second_primary_for_the_same_property_and_role_is_demoted() -> None:
    PropertyFactory(legacy_id="500")
    PersonFactory(legacy_id="70")
    PersonFactory(legacy_id="71")

    report = _load(_row(), _row(MappingId=12, ContactId="71"))

    assert report.created == 2
    assert PropertyContactAssignment.objects.get(legacy_id="11-10").is_primary is True
    assert PropertyContactAssignment.objects.get(legacy_id="12-10").is_primary is False


def test_rerun_updates_in_place() -> None:
    PropertyFactory(legacy_id="500")
    PersonFactory(legacy_id="70")

    report = _load(_row(), _row(IsPrimaryContact=0))

    assert (report.created, report.updated) == (1, 1)
    assert PropertyContactAssignment.objects.count() == 1
    assert PropertyContactAssignment.objects.get().is_primary is False


def test_rerun_of_the_primary_row_does_not_demote_itself() -> None:
    PropertyFactory(legacy_id="500")
    PersonFactory(legacy_id="70")

    _load(_row(), _row())

    assert PropertyContactAssignment.objects.get(legacy_id="11-10").is_primary is True


def test_primary_in_another_role_does_not_demote() -> None:
    PropertyFactory(legacy_id="500")
    PersonFactory(legacy_id="70")
    PersonFactory(legacy_id="71")

    _load(_row(), _row(MappingId=12, ContactId="71", RoleId=20))  # owner, then agent

    assert PropertyContactAssignment.objects.get(legacy_id="12-20").is_primary is True


def test_ended_primary_does_not_demote_a_successor() -> None:
    PropertyFactory(legacy_id="500")
    PersonFactory(legacy_id="70")
    PersonFactory(legacy_id="71")
    _load(_row())
    PropertyContactAssignment.objects.filter(legacy_id="11-10").update(end_date=date(2024, 1, 1))

    _load(_row(MappingId=12, ContactId="71"))

    assert PropertyContactAssignment.objects.get(legacy_id="12-10").is_primary is True


def test_unresolved_property_is_skipped() -> None:
    PersonFactory(legacy_id="70")
    assert _load(_row()).skipped == 1
    assert PropertyContactAssignment.objects.count() == 0


def test_unresolved_contact_is_skipped() -> None:
    PropertyFactory(legacy_id="500")
    assert _load(_row()).skipped == 1
    assert PropertyContactAssignment.objects.count() == 0
