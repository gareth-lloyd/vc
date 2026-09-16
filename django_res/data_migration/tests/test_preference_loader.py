"""GuestPreferenceLoader — customer resolution, person-keyed dedup, idempotency.

The loader writes only the unified `person` FK (GAP-045 D5-3 — the `client-{id}`
Person, no Guest in the graph), resolved client → the row's own quotation →
unknown-client sentinel (GAP-108 U8d), and dedups on (person, preference_type,
quotation) to match the `unique_person_preference` constraint. Duplicates (same
triple) collapse to the first occurrence.
"""

from __future__ import annotations

import pytest
import structlog

from data_migration.base import LoadReport
from data_migration.loaders.finance import QuotationLoader
from data_migration.loaders.preferences import GuestPreferenceLoader
from data_migration.loaders.reservations import ClientLoader
from data_migration.loaders.sentinels import UNKNOWN_CLIENT_LEGACY_ID
from reservations.models.preferences import GuestPreference, GuestPreferenceType
from reservations.models.quotation import Quotation


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": 1,
        "ClientDetailsId": 55,
        "ClientPrefMasterId": 7,
        "QuotationMasterId": None,
        # Read only by `_may_borrow_quotation_person`: whether the legacy client
        # row exists at all, and which client the quotation itself names.
        "ClientRowExists": 1,
        "QuotationClientId": None,
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


def _quotation_for_another_client() -> Quotation:
    """A loaded Quotation (legacy_id=541) whose customer is a DIFFERENT named
    client (`client-99`) — the person GAP-108 U8d's fallback must borrow."""
    ClientLoader()._process_row(
        {
            "Id": 99,
            "FirstName": "Grace",
            "LastName": "Hopper",
            "Email": "grace@example.com",
            "MobileNo": "",
        },
        LoadReport(loader="client"),
    )
    kwargs = QuotationLoader().transform(
        {"Id": 541, "ClientDetailsId": 99, "AgentId": None, "QuotationNo": 1806}
    )
    assert kwargs is not None
    return Quotation.objects.create(legacy_id="541", **kwargs)


@pytest.mark.django_db
def test_unresolvable_client_borrows_its_quotations_person(
    _guest_and_pref_type: None,
) -> None:
    """GAP-108 U8d: a preference whose ClientDetailsId never loaded takes the
    customer its own quotation already resolved, not the unknown-client
    sentinel — 474 of the 569 such rows on ResProd reach a real named person
    this way (`QuotationLoader` runs first; registry order guarantees it)."""
    quotation = _quotation_for_another_client()

    kwargs = GuestPreferenceLoader().transform(
        _row(ClientDetailsId=4242, ClientRowExists=0, QuotationMasterId=541)
    )

    assert kwargs is not None
    assert kwargs["person"] == quotation.person
    assert kwargs["person"].legacy_id != UNKNOWN_CLIENT_LEGACY_ID


@pytest.mark.django_db
def test_resolvable_client_wins_over_its_quotations_person(
    _guest_and_pref_type: None,
) -> None:
    """The fallback is a LAST resort: a preference whose own client loaded keeps
    that client even when its quotation names somebody else."""
    from data_migration.loaders._util import person_for_client

    _quotation_for_another_client()

    kwargs = GuestPreferenceLoader().transform(_row(ClientDetailsId=55, QuotationMasterId=541))

    assert kwargs is not None
    assert kwargs["person"] == person_for_client(55)


@pytest.mark.django_db
def test_unresolvable_client_without_a_quotation_keeps_the_sentinel(
    _guest_and_pref_type: None,
) -> None:
    """No quotation, no hop: the row still LOADS on the sentinel rather than
    being dropped (30 loaded rows on ResProd), per the sentinel-fallback rule."""
    kwargs = GuestPreferenceLoader().transform(
        _row(ClientDetailsId=4242, ClientRowExists=0, QuotationMasterId=None)
    )

    assert kwargs is not None
    assert kwargs["person"].legacy_id == UNKNOWN_CLIENT_LEGACY_ID


@pytest.mark.django_db
def test_borrow_is_refused_when_the_quotation_names_a_different_real_client(
    _guest_and_pref_type: None,
) -> None:
    """The guard that keeps U8d from merging two people: the preference names a
    client row that EXISTS but did not load (one of the 184 named nowhere), and
    its quotation names somebody else. Borrowing there would put this person's
    dietary/access notes on another person's profile, so the row keeps the
    sentinel. Zero rows on the 13-Aug-2026 dump — this bounds a newer one."""
    _quotation_for_another_client()
    report = LoadReport(loader="guest_preference")
    loader = GuestPreferenceLoader()
    with structlog.testing.capture_logs() as logs:
        loader._load_rows(
            [
                _row(
                    ClientDetailsId=4242,
                    ClientRowExists=1,
                    QuotationMasterId=541,
                    QuotationClientId=99,
                )
            ],
            report,
        )

    assert GuestPreference.objects.get(legacy_id="1").person.legacy_id == UNKNOWN_CLIENT_LEGACY_ID
    borrowed = [
        e
        for e in logs
        if e["event"] == "data_migration.preference_customer_borrowed_from_quotation"
    ]
    assert borrowed[0] == {**borrowed[0], "count": 0, "refused": 1}


@pytest.mark.django_db
def test_borrow_is_allowed_when_the_quotation_names_the_same_client(
    _guest_and_pref_type: None,
) -> None:
    """The mirror case: the client row exists but never loaded, and the
    quotation names that SAME id — so its `person` is the same human, reached
    through the enquiry hop U8b gave `QuotationLoader`. Safe to borrow."""
    quotation = _quotation_for_another_client()

    kwargs = GuestPreferenceLoader().transform(
        _row(
            ClientDetailsId=4242,
            ClientRowExists=1,
            QuotationMasterId=541,
            QuotationClientId=4242,
        )
    )

    assert kwargs is not None
    assert kwargs["person"] == quotation.person


@pytest.mark.django_db
def test_client_less_row_takes_the_quotations_person_but_skips_without_one(
    _guest_and_pref_type: None,
) -> None:
    """A row with no ClientDetailsId at all still reaches the customer its
    quotation names; with neither, it references nobody and is dropped rather
    than piled onto the sentinel."""
    quotation = _quotation_for_another_client()

    borrowed = GuestPreferenceLoader().transform(
        _row(ClientDetailsId=0, ClientRowExists=0, QuotationMasterId=541)
    )
    orphan = GuestPreferenceLoader().transform(
        _row(Id=2, ClientDetailsId=0, ClientRowExists=0, QuotationMasterId=None)
    )

    assert borrowed is not None
    assert borrowed["person"] == quotation.person
    assert orphan is None


@pytest.mark.django_db
def test_unresolved_quotation_id_cannot_supply_a_person(
    _guest_and_pref_type: None,
) -> None:
    """BUG-030 §30 rows are untouched by U8d: a QuotationMasterId pointing at no
    loaded quotation has no person to lend, so the row keeps the sentinel and
    still counts towards `preference_quotation_unresolved`."""
    report = LoadReport(loader="guest_preference")
    loader = GuestPreferenceLoader()
    with structlog.testing.capture_logs() as logs:
        loader._load_rows([_row(ClientDetailsId=4242, QuotationMasterId=999)], report)

    pref = GuestPreference.objects.get(legacy_id="1")
    assert pref.quotation is None
    assert pref.person.legacy_id == UNKNOWN_CLIENT_LEGACY_ID
    summary = [e for e in logs if e["event"] == "data_migration.preference_quotation_unresolved"]
    assert summary[0]["count"] == 1


@pytest.mark.django_db
def test_unresolved_quotation_context_loads_flat_and_is_counted(
    _guest_and_pref_type: None,
) -> None:
    """BUG-030 §30: most legacy QuotationMasterIds point at no quotation; the
    preference still loads (quotation=None) and the run logs how many."""
    report = LoadReport(loader="guest_preference")
    with structlog.testing.capture_logs() as logs:
        GuestPreferenceLoader()._load_rows(
            [
                _row(Id=1, QuotationMasterId=541),
                _row(Id=2, ClientPrefMasterId=7, QuotationMasterId=None),
            ],
            report,
        )

    pref = GuestPreference.objects.get(legacy_id="1")
    assert pref.quotation is None
    summary = [e for e in logs if e["event"] == "data_migration.preference_quotation_unresolved"]
    assert len(summary) == 1
    assert summary[0]["count"] == 1
