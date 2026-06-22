"""GuestPreferenceLoader — person-keyed dedup + idempotency (GAP-045 D5-3).

The loader resolves the customer via `person_for_client` (the `client-{id}`
Person — no Guest in the graph) and writes only the unified `person` FK, dedups
on (person, preference_type, quotation) to match the `unique_person_preference`
constraint. Duplicates (same triple) collapse to the first occurrence.
"""

from __future__ import annotations

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.preferences import GuestPreferenceLoader
from data_migration.loaders.reservations import ClientLoader
from reservations.models.preferences import GuestPreference, GuestPreferenceType


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
    # GAP-045 D5-3: the preference's customer is a `client-55` Person, written by
    # ClientLoader from a legacy VillaClientDetails row (Id=55); the loader
    # resolves it via `person_for_client`, no Guest in the graph.
    ClientLoader()._process_row(
        {
            "Id": 55,
            "FirstName": "Ada",
            "LastName": "Lovelace",
            "Email": "ada@example.com",
            "MobileNo": "",
        },
        LoadReport(loader="client"),
    )
    GuestPreferenceType.objects.create(name="Late checkout", legacy_id="7")


@pytest.mark.django_db
def test_loader_writes_person_not_guest(_guest_and_pref_type: None) -> None:
    from data_migration.loaders._util import person_for_client

    GuestPreferenceLoader()._process_row(_row(), LoadReport(loader="guest_preference"))

    person = person_for_client(55)
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
