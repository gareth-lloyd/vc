"""GuestPreferenceLoader — person-keyed dedup + idempotency (GAP-045 Unit 3d-B).

The loader writes only the unified `person` FK (not the legacy `guest` leg) and
dedups on (person, preference_type, quotation) to match the
`unique_person_preference` constraint. A guest-keyed dedup would stop matching
prior rows (born `guest=NULL`) on re-run and trip the constraint; guest → person
is 1:1, so the person-keyed dedup is exactly equivalent.
"""

from __future__ import annotations

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.preferences import GuestPreferenceLoader
from reservations.models.guest import Guest
from reservations.models.preferences import GuestPreference, GuestPreferenceType
from reservations.services.person_sync import person_for_guest


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": 1,
        "ClientDetailsId": 55,
        "ClientPrefMasterId": 7,
        "QuotationMasterId": None,
    }
    base.update(overrides)
    return base


@pytest.fixture
def _guest_and_pref_type(db: None) -> None:
    Guest.objects.create(
        first_name="Ada", last_name="Lovelace", email="ada@example.com", legacy_id="55"
    )
    GuestPreferenceType.objects.create(name="Late checkout", legacy_id="7")


@pytest.mark.django_db
def test_loader_writes_person_not_guest(_guest_and_pref_type: None) -> None:
    GuestPreferenceLoader()._process_row(_row(), LoadReport(loader="guest_preference"))

    person = person_for_guest(Guest.objects.get(legacy_id="55"))
    pref = GuestPreference.objects.get(legacy_id="1")
    assert pref.person_id == person.pk
    assert pref.guest_id is None


@pytest.mark.django_db
def test_loader_is_idempotent_on_person_keyed_dedup(_guest_and_pref_type: None) -> None:
    """Re-running the loader on the same legacy row leaves exactly one
    preference — the person-keyed dedup matches the prior row even though
    `guest` is NULL, so it neither duplicates nor trips the constraint."""
    report = LoadReport(loader="guest_preference")
    GuestPreferenceLoader()._process_row(_row(), report)
    GuestPreferenceLoader()._process_row(_row(), report)

    assert GuestPreference.objects.filter(legacy_id="1").count() == 1
    assert GuestPreference.objects.count() == 1


@pytest.mark.django_db
def test_loader_dedups_distinct_legacy_rows_with_same_triple(_guest_and_pref_type: None) -> None:
    """Two distinct legacy rows with the same (person, pref_type, quotation)
    triple collapse to the first — the second is skipped, not an IntegrityError
    on `unique_person_preference`."""
    report = LoadReport(loader="guest_preference")
    GuestPreferenceLoader()._process_row(_row(Id=1), report)
    GuestPreferenceLoader()._process_row(_row(Id=2), report)

    assert GuestPreference.objects.count() == 1
    assert GuestPreference.objects.filter(legacy_id="1").exists()
    assert not GuestPreference.objects.filter(legacy_id="2").exists()
