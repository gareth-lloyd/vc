"""Tests for the `reconcile_legacy` gap-enforcement gate.

The command's legacy side is mocked: a fake cursor returns a scripted result
per query (keyed by a query substring, so tests don't depend on execute()
call order), while the loaded count comes from the real (test) DB. This lets
us assert the gap-vs-expected pass/fail logic without a live SQL Server.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from io import StringIO
from typing import cast

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.enums import OrgType
from accounts.models import Organisation, Person
from data_migration.loaders.integrations import SyncRecordZohoLoader
from data_migration.management.commands import reconcile_legacy
from data_migration.management.commands.reconcile_legacy import _Check
from integrations.enums import SyncProvider
from integrations.factories import SyncRecordFactory
from pricing.models.currency import Currency
from properties.factories import FeatureFactory, PropertyFactory
from properties.models.property import Property
from reservations.factories import EnquiryFactory
from reservations.models.booking import Booking
from reservations.models.enquiry import Enquiry


class _FakeCursor:
    """Returns a scripted result keyed by a substring of the executed query.

    A scalar response is read via `fetchone()[0]` (COUNT queries); a list
    response is read via `fetchall()` (the continuity `SELECT Id ...` query),
    yielded as one-tuples — or as-is when the scripted items are already
    tuples (multi-column rows, e.g. the night-parity `(VillaId, From, To)`
    query). Keying by query rather than by position means adding or
    reordering a check can't silently feed the wrong number to a query.
    """

    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses
        self._last: object = None

    def execute(self, query: str) -> None:
        # Exact match first, so a check can be keyed on its full
        # `legacy_query` when a shorter needle is a substring of it.
        if query in self._responses:
            self._last = self._responses[query]
            return
        for needle, value in self._responses.items():
            if needle in query:
                self._last = value
                return
        raise AssertionError(f"no scripted result for query: {query!r}")

    def fetchone(self) -> tuple[object]:
        return (self._last,)

    def fetchall(self) -> list[tuple[object, ...]]:
        assert isinstance(self._last, list), "fetchall() called on a scalar response"
        return [v if isinstance(v, tuple) else (v,) for v in self._last]


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    checks: list[_Check],
    responses: dict[str, object],
) -> None:
    # The night-parity section runs unconditionally; tests that don't script
    # it see an empty legacy side (no villas → no mismatches).
    responses = {**responses}
    responses.setdefault(reconcile_legacy.NIGHT_PARITY_QUERY, [])

    @contextmanager
    def _fake_cursor() -> Iterator[_FakeCursor]:
        yield _FakeCursor(responses)

    monkeypatch.setattr(reconcile_legacy, "_CHECKS", checks)
    monkeypatch.setattr(reconcile_legacy, "legacy_cursor", _fake_cursor)


def _zero_zoho_expected_gaps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero the calibrated per-table continuity gaps (VillaMaster carries 1 for
    the Temenos duplicate pair) so generic section tests can script arbitrary
    legacy data without tripping the calibration. The calibrated value itself
    is pinned by its own dedicated tests below."""
    monkeypatch.setattr(
        SyncRecordZohoLoader,
        "SPECS",
        tuple(replace(spec, expected_gap=0) for spec in SyncRecordZohoLoader.SPECS),
    )


def _integration_responses(
    *,
    master: list[str] | None = None,
    contact: list[str] | None = None,
    enquire: list[str] | None = None,
    quotation: list[str] | None = None,
    booking_url: int = 0,
    syncdetail_rows: int = 0,
    syncdetail_sites: int = 0,
    without_zoho_column: set[str] | None = None,
) -> dict[str, object]:
    """Scripted results for the --integrations sections.

    The four continuity values are the legacy Ids returned by
    `SELECT Id FROM <table> WHERE ZohoId ...`; the three WordPress values are
    scalar COUNTs. Keys are distinctive query substrings. Every table answers
    the INFORMATION_SCHEMA ZohoId probe with 1 (column present) unless listed
    in `without_zoho_column`.
    """
    zoho_tables = (
        "VillaMaster",
        "VillaContact",
        "VillaEnquire",
        "VillaQuotationMaster",
    )
    probes: dict[str, object] = {
        f"TABLE_NAME = '{table}'": 0 if table in (without_zoho_column or set()) else 1
        for table in zoho_tables
    }
    return {
        **probes,
        "VillaMaster WHERE ZohoId": master or [],
        "VillaContact WHERE ZohoId": contact or [],
        "VillaEnquire WHERE ZohoId": enquire or [],
        "VillaQuotationMaster WHERE ZohoId": quotation or [],
        "BookingUrl": booking_url,
        # ResProd's table is `VillaSyncDetails` (GAP-108); the full table name
        # in the key means the old singular name finds no scripted result.
        "COUNT(*) FROM VillaSyncDetails": syncdetail_rows,
        "COUNT(DISTINCT SiteId) FROM VillaSyncDetails": syncdetail_sites,
    }


def _run(*args: str) -> str:
    out = StringIO()
    call_command("reconcile_legacy", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_gap_equal_to_expected_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    EnquiryFactory(legacy_id="1")
    EnquiryFactory(legacy_id="2")  # loaded = 2
    _patch(
        monkeypatch,
        [_Check("SELECT COUNT(*) FROM VillaEnquire", Enquiry, "Enquiry", expected_gap=5)],
        responses={"VillaEnquire": 7},  # legacy 7 - loaded 2 = gap 5 == expected
    )

    output = _run()

    assert "expected" in output and "status" in output
    assert "OK" in output and "BLOCKER" not in output


@pytest.mark.django_db
def test_gap_over_expected_is_blocker_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    EnquiryFactory(legacy_id="1")
    EnquiryFactory(legacy_id="2")  # loaded = 2
    _patch(
        monkeypatch,
        [_Check("SELECT COUNT(*) FROM VillaEnquire", Enquiry, "Enquiry", expected_gap=5)],
        responses={"VillaEnquire": 8},  # legacy 8 - loaded 2 = gap 6 != expected 5
    )

    with pytest.raises(CommandError, match="Enquiry: gap 6 != expected 5"):
        _run()


@pytest.mark.django_db
def test_unexpected_gap_on_zero_expected_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    # The common case: expected_gap defaults to 0, so any loss is a blocker.
    _patch(
        monkeypatch,
        [_Check("SELECT COUNT(*) FROM VillaEnquire", Enquiry, "Enquiry")],
        responses={"VillaEnquire": 3},  # legacy 3 - loaded 0 = gap 3 != expected 0
    )

    with pytest.raises(CommandError, match="cutover must not proceed"):
        _run()


@pytest.mark.django_db
def test_multiple_blockers_are_all_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(
        monkeypatch,
        [
            _Check("q1", Enquiry, "First", expected_gap=0),
            _Check("q2", Enquiry, "Second", expected_gap=0),
        ],
        responses={"q1": 1, "q2": 2},
    )

    with pytest.raises(CommandError) as exc:
        _run()

    message = str(exc.value)
    assert "2 reconcile blocker(s)" in message
    assert "First" in message and "Second" in message


def test_check_has_no_dead_extra_filter_field() -> None:
    # extra_filter was unused; ensure it's gone so no dead config lingers.
    field_names = {f for f in _Check.__dataclass_fields__}
    assert "extra_filter" not in field_names


@pytest.mark.django_db
def test_person_checks_count_their_own_legacy_id_slice(monkeypatch: pytest.MonkeyPatch) -> None:
    """GAP-045 D5-3: VillaContact (owner/agent) and VillaClientDetails (client)
    both land in `accounts.Person`. Each reconcile check must count only its own
    `legacy_id` slice — a bare `Person.count()` would double-count and turn both
    RED. The `unknown_client` sentinel is in neither slice.
    """
    from accounts.factories import PersonFactory
    from data_migration.management.commands.reconcile_legacy import _CHECKS

    PersonFactory(legacy_id="10")  # owner/agent (bare legacy_id)
    PersonFactory(legacy_id="11")  # owner/agent
    PersonFactory(legacy_id="client-55")  # client
    PersonFactory(legacy_id="client-__unknown__")  # sentinel — counted by neither

    by_label = {c.label: c for c in _CHECKS}
    owner_check = by_label["Person (owner/agent)"]
    client_check = by_label["Person (client)"]
    assert owner_check.loaded_count is not None
    assert client_check.loaded_count is not None

    # owner/agent slice = the two bare-legacy_id rows (excludes both client rows).
    assert owner_check.loaded_count(owner_check.model) == 2
    # client slice = the one real client row (excludes owner/agent AND sentinel).
    assert client_check.loaded_count(client_check.model) == 1
    # The client check keeps the documented no-name gap.
    assert client_check.expected_gap == 1


@pytest.mark.django_db
def test_sheet_imported_rows_do_not_move_the_legacy_counts() -> None:
    """GAP-089: the spreadsheet importers write Person / PersonEmail /
    PersonPhone / Enquiry rows keyed `sheet-…`. They have no legacy-DB twin, so
    every count that compares against the res dump must leave them out or the
    checks go RED after the import (an unexplained gap blocks cutover)."""
    from accounts.factories import PersonEmailFactory, PersonFactory, PersonPhoneFactory
    from data_migration.management.commands.reconcile_legacy import _CHECKS

    legacy = PersonFactory(legacy_id="10")
    PersonEmailFactory(contact=legacy, email="legacy@example.com", legacy_id="1")
    PersonPhoneFactory(contact=legacy, number="+441234567890", legacy_id="1")
    sheet = PersonFactory(legacy_id="sheet-person-0123456789abcdef")
    PersonEmailFactory(contact=sheet, email="sheet@example.com")
    PersonPhoneFactory(contact=sheet, number="+449876543210")
    EnquiryFactory(legacy_id="enquiry-1", person=None)
    EnquiryFactory(legacy_id="sheet-enquiry-0123456789abcdef", person=sheet)
    Organisation.objects.create(name="Legacy Travel", dedup_key="k1", org_type=OrgType.AGENCY)
    Organisation.objects.create(
        name="Sheet Travel", dedup_key="k2", org_type=OrgType.AGENCY, legacy_id="sheet-org-k2"
    )

    by_label = {c.label: c for c in _CHECKS}
    for label in (
        "Person (owner/agent)",
        "PersonEmail",
        "PersonPhone",
        "Enquiry",
        "Organisation (agency)",
    ):
        check = by_label[label]
        assert check.loaded_count is not None, label
        assert check.loaded_count(check.model) == 1, label


@pytest.mark.django_db
def test_rate_plan_basis_check_counts_only_legacy_non_gross() -> None:
    """SMELL-021: legacy cannot express NET, so the loader stamps GROSS on every
    imported plan — the basis-invariant check must count only *legacy* plans
    that ended up non-GROSS (a stamp regression), never staff-created NET plans.
    """
    from data_migration.management.commands.reconcile_legacy import _CHECKS
    from pricing.factories import RatePlanFactory
    from properties.enums import PriceBasis

    RatePlanFactory(legacy_id="1", price_basis=PriceBasis.GROSS)  # correct stamp
    RatePlanFactory(legacy_id="2", price_basis=PriceBasis.NET)  # regression → counted
    RatePlanFactory(price_basis=PriceBasis.NET)  # staff-created NET — not counted

    by_label = {c.label: c for c in _CHECKS}
    basis_check = by_label["RatePlan non-GROSS basis (must be 0)"]
    assert basis_check.loaded_count is not None
    assert basis_check.loaded_count(basis_check.model) == 1
    assert basis_check.expected_gap == 0


@pytest.mark.django_db
def test_geo_parity_checks_split_active_from_retired(monkeypatch: pytest.MonkeyPatch) -> None:
    """GAP-107: legacy-deleted regions/countries load `is_active=False`, so
    the bare `Region` total says nothing about *which* rows are active. The
    imported / active slices (both `legacy_id IS NOT NULL` only, sentinels
    excluded) pin the split — retired = imported - active on both sides —
    so a single misclassification cannot hide inside the total (an
    equal-and-opposite swap still can; these are counts, not row diffs).
    The legacy side carries the same OR deletion predicate as the loaders
    (`legacy_deleted_sql`).
    """
    from data_migration.loaders._util import legacy_deleted_sql
    from data_migration.loaders.sentinels import unknown_country, unknown_region
    from data_migration.management.commands.reconcile_legacy import _CHECKS
    from properties.factories import CountryFactory, RegionFactory
    from properties.models.geo import Country

    def _country(iso2: str, **fields: object) -> Country:
        # CountryFactory is get-or-create on iso2 (the ISO seed already holds
        # the row), so stamp the legacy state explicitly.
        CountryFactory(iso2=iso2)
        Country.objects.filter(iso2=iso2).update(**fields)
        return Country.objects.get(iso2=iso2)

    live_country = _country("FR", legacy_id="1", is_active=True)
    retired_country = _country("IN", legacy_id="2", is_active=False)
    _country("DE", is_active=True)  # seeded ISO row, no legacy twin
    RegionFactory(country=live_country, name="Provence", legacy_id="10", is_active=True)
    RegionFactory(country=live_country, name="Old Riviera", legacy_id="11", is_active=False)
    RegionFactory(country=retired_country, name="Goa", legacy_id="12", is_active=False)
    RegionFactory(country=live_country, name="Staff-made")  # no legacy twin
    unknown_region(unknown_country())  # sentinel — in neither slice

    # The XX country sentinel: inactive, and its legacy_id is re-pointed by
    # CountryLoader to a real legacy id — must stay out by identity.
    Country.objects.filter(iso2="XX").update(legacy_id="99", is_active=True)

    by_label = {c.label: c for c in _CHECKS}
    imported = by_label["Region (imported)"]
    active = by_label["Region (active)"]
    country_active = by_label["Country (active)"]
    counts = {}
    for check in (imported, active, country_active):
        assert check.loaded_count is not None, check.label
        counts[check.label] = check.loaded_count(check.model)
    assert counts == {"Region (imported)": 3, "Region (active)": 1, "Country (active)": 1}

    # Legacy side mirrors the loader: deletion is the OR predicate, a region
    # is live only under a live, `IsActive = 1` country.
    assert legacy_deleted_sql("r.") in active.legacy_query
    assert legacy_deleted_sql("c.") in active.legacy_query
    assert "c.IsActive = 1" in active.legacy_query
    assert legacy_deleted_sql() in country_active.legacy_query
    assert "IsActive = 1" in country_active.legacy_query

    geo_checks = [c for c in _CHECKS if c.model.__name__ in ("Region", "Country")]
    _patch(
        monkeypatch,
        geo_checks,
        responses={
            # Keyed on the full query where a shorter needle is a substring.
            imported.legacy_query: 3 + imported.expected_gap,
            active.legacy_query: 1 + active.expected_gap,
            country_active.legacy_query: 1 + country_active.expected_gap,
            # Bare totals: every stamped Region (4: the imported three + the
            # sentinel; staff-made is organic, GAP-108) and every Country
            # (the ISO seed + sentinel — the one explicit whole-table count).
            "COUNT(*) FROM VillaRegion": 4 + by_label["Region"].expected_gap,
            "COUNT(*) FROM VillaCountry": (
                Country.objects.count() + by_label["Country (legacy)"].expected_gap
            ),
        },
    )
    output = _run()
    assert "BLOCKER" not in output


@pytest.mark.django_db
def test_rate_plan_check_counts_regime_plans_against_villas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GAP-110: a plan is one (villa, currency) regime, so the legacy side is
    distinct priced villas and the loaded side is `villa:`-keyed plans only —
    a staff-created plan or a stale season-keyed one must not move it."""
    from datetime import date

    from data_migration.management.commands.reconcile_legacy import _CHECKS
    from pricing.factories import RatePeriodFactory, RatePlanFactory
    from properties.factories import PropertyFactory

    villa_900 = PropertyFactory(legacy_id="900")
    eur = RatePlanFactory(property=villa_900, legacy_id="villa:900:EUR")
    gbp = RatePlanFactory(property=villa_900, legacy_id="villa:900:GBP")
    RatePeriodFactory(
        plan=eur, date_from=date(2025, 6, 1), date_to=date(2025, 6, 30), legacy_id="a"
    )
    RatePeriodFactory(
        plan=gbp, date_from=date(2025, 6, 1), date_to=date(2025, 6, 30), legacy_id="b"
    )
    RatePeriodFactory(
        plan=RatePlanFactory(legacy_id="villa:901:EUR"),
        date_from=date(2025, 6, 1),
        date_to=date(2025, 6, 30),
        legacy_id="c",
    )
    RatePlanFactory(legacy_id="villa:902:EUR")  # minted, but no period ever landed
    RatePeriodFactory(
        plan=RatePlanFactory(legacy_id="123"),  # pre-regroup key — not a regime plan
        date_from=date(2025, 6, 1),
        date_to=date(2025, 6, 30),
        legacy_id="d",
    )
    RatePeriodFactory(plan=RatePlanFactory())  # staff-created plan + UI period

    check = next(c for c in _CHECKS if c.label.startswith("RatePlan (villas"))
    assert "COUNT(DISTINCT s.VillaId)" in check.legacy_query
    assert check.loaded_count is not None
    assert check.loaded_count(check.model) == 2  # villas 900 (two currencies) + 901
    assert check.expected_gap == 0


@pytest.mark.django_db
def test_night_parity_check_counts_villas_with_a_coverage_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GAP-110 U0b: per villa, the set of nights legacy priced (union of its
    live priced rate rows, ToDate inclusive) must equal the nights its loaded
    legacy periods cover — the regroup must not lose or invent priced nights.
    The section lists every mismatched villa with both night counts and
    returns one blocker per villa, so a dump residue can be itemised."""
    from datetime import date

    from pricing.factories import RatePeriodFactory, RatePlanFactory
    from pricing.models.rate import RatePeriod
    from properties.factories import PropertyFactory

    ok_villa = PropertyFactory(legacy_id="900")
    bad_villa = PropertyFactory(legacy_id="901")
    ok_plan = RatePlanFactory(property=ok_villa, legacy_id="villa:900:EUR")
    bad_plan = RatePlanFactory(property=bad_villa, legacy_id="villa:901:EUR")
    # Villa 900: two contiguous legacy rows, loaded as two trimmed periods —
    # identical night set.
    RatePeriodFactory(
        plan=ok_plan,
        date_from=date(2025, 6, 1),
        date_to=date(2025, 6, 7),
        legacy_id="villa:900:EUR:p0",
    )
    RatePeriodFactory(
        plan=ok_plan,
        date_from=date(2025, 6, 8),
        date_to=date(2025, 6, 15),
        legacy_id="villa:900:EUR:p1",
    )
    # Villa 901: legacy priced June, loaded only the first week.
    RatePeriodFactory(
        plan=bad_plan,
        date_from=date(2025, 6, 1),
        date_to=date(2025, 6, 7),
        legacy_id="villa:901:EUR:p0",
    )
    # A UI-created period never counts (legacy_id NULL).
    RatePeriodFactory(plan=bad_plan, date_from=date(2025, 6, 8), date_to=date(2025, 6, 30))
    assert RatePeriod.objects.filter(legacy_id__isnull=True).count() == 1

    legacy_rows = [
        (900, date(2025, 6, 1), date(2025, 6, 8)),
        (900, date(2025, 6, 8), date(2025, 6, 15)),
        (901, date(2025, 6, 1), date(2025, 6, 30)),
    ]
    assert reconcile_legacy.night_parity_mismatches(legacy_rows) == [("901", 30, 7)]

    _patch(monkeypatch, [], responses={reconcile_legacy.NIGHT_PARITY_QUERY: legacy_rows})
    with pytest.raises(CommandError, match="villa 901 legacy 30 nights, loaded 7"):
        _run()


def test_night_parity_compares_coalesced_spans_not_individual_nights() -> None:
    """Touching and overlapping legacy spans fuse; a sentinel far-future row
    must not expand to a date per night."""
    from datetime import date

    spans = [
        (date(2025, 6, 8), date(2025, 6, 15)),
        (date(2025, 6, 1), date(2025, 6, 7)),
        (date(2025, 6, 10), date(2099, 12, 31)),
    ]
    assert reconcile_legacy._coalesce(spans) == [(date(2025, 6, 1), date(2099, 12, 31))]


@pytest.mark.django_db
def test_night_parity_section_is_ok_when_nothing_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(monkeypatch, [], responses={})
    output = _run()
    assert "RatePeriod night parity" in output and "BLOCKER" not in output


@pytest.mark.django_db
def test_room_placement_check_counts_preserved_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    """GAP-065: legacy rooms with a non-NULL PlacementId reconcile against
    rooms that landed with a preserved `placement_note` — the no-loss gate.
    Runs both real Room checks together: the plain-count query is a substring
    of the placement one, so the scripted needles must key the placement check
    on "PlacementId" (and list it first) to avoid first-substring collisions.
    """
    from data_migration.management.commands.reconcile_legacy import _CHECKS
    from properties.factories import RoomFactory

    RoomFactory(legacy_id="1", placement_note="First floor")
    RoomFactory(legacy_id="2", placement_note="Guest house")
    RoomFactory(legacy_id="3")  # legacy NULL PlacementId → no note
    # placement_note is API-writable: a staff note on a NON-legacy room during
    # the cutover window must not shift the gap into a false BLOCKER.
    RoomFactory(placement_note="Staff-entered note")

    by_label = {c.label: c for c in _CHECKS}
    placement_check = by_label["Room placement (GAP-065)"]
    assert placement_check.loaded_count is not None
    assert placement_check.loaded_count(placement_check.model) == 2
    assert "PlacementId IS NOT NULL" in placement_check.legacy_query

    room_checks = [c for c in _CHECKS if c.model.__name__ == "Room"]
    _patch(
        monkeypatch,
        room_checks,
        responses={
            # Order matters: the fake cursor matches first-substring, and the
            # plain Room needle is a substring of the placement query.
            "PlacementId IS NOT NULL": 2 + placement_check.expected_gap,
            # The plain Room check counts every legacy room (3; the
            # staff-created one is organic, GAP-108 default).
            "COUNT(*) FROM VillaRooms": 3 + by_label["Room"].expected_gap,
        },
    )
    output = _run()
    assert "BLOCKER" not in output


# --- --integrations flag (P0b) ---


@pytest.mark.django_db
def test_no_integration_sections_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, [_Check("q", Enquiry, "Enquiry")], responses={"q": 0})

    output = _run()

    assert "Zoho external-ID continuity" not in output
    assert "WordPress external-ID surface" not in output


@pytest.mark.django_db
def test_integrations_flag_renders_both_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    _zero_zoho_expected_gaps(monkeypatch)
    _patch(
        monkeypatch,
        [],
        responses=_integration_responses(booking_url=7, syncdetail_rows=12, syncdetail_sites=2),
    )

    output = _run("--integrations")

    assert "Zoho external-ID continuity" in output
    assert "VillaMaster.ZohoId" in output
    assert "WordPress external-ID surface" in output
    assert "VillaBooking.BookingUrl" in output
    assert "VillaSyncDetails (rows)" in output
    assert "VillaSyncDetails (sites)" in output
    assert "n/a" not in output  # every WordPress query hit a real table
    # WordPress counts are informational, never a blocker.
    assert "INFO" in output
    assert "BLOCKER" not in output


@pytest.mark.django_db
def test_zoho_id_on_loaded_row_without_sync_record_is_a_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Three VillaMaster rows carry a ZohoId and all three were imported, but no
    # SyncRecord exists for them → a real continuity gap that must block.
    for legacy_id in ("10", "11", "12"):
        PropertyFactory(legacy_id=legacy_id)
    _zero_zoho_expected_gaps(monkeypatch)
    _patch(
        monkeypatch,
        [],
        responses=_integration_responses(master=["10", "11", "12"]),
    )

    with pytest.raises(CommandError, match=r"VillaMaster\.ZohoId: continuity gap 3"):
        _run("--integrations")


@pytest.mark.django_db
def test_zoho_continuity_ok_when_sync_record_present(monkeypatch: pytest.MonkeyPatch) -> None:
    prop = PropertyFactory(legacy_id="10")
    SyncRecordFactory(target=prop, provider=SyncProvider.ZOHO_CRM)  # non-blank external_id
    _zero_zoho_expected_gaps(monkeypatch)
    _patch(monkeypatch, [], responses=_integration_responses(master=["10"]))

    output = _run("--integrations")

    assert "BLOCKER" not in output


@pytest.mark.django_db
def test_unimported_zoho_row_is_not_a_continuity_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression: a legacy ZohoId on a row the domain loader dropped
    # (soft-deleted / empty-name / unresolvable) has no Property target and so
    # no SyncRecord — but it is NOT a continuity failure (nothing to push), and
    # must not block. Property "10" was imported and has its record; "99" was
    # not imported. The continuity COUNT must reconcile against loaded rows only.
    prop = PropertyFactory(legacy_id="10")
    SyncRecordFactory(target=prop, provider=SyncProvider.ZOHO_CRM)
    _zero_zoho_expected_gaps(monkeypatch)
    _patch(monkeypatch, [], responses=_integration_responses(master=["10", "99"]))

    output = _run("--integrations")

    assert "BLOCKER" not in output
    # The raw legacy count (2) is still surfaced even though only 1 was loaded.
    assert "VillaMaster.ZohoId" in output


@pytest.mark.django_db
def test_blank_external_id_record_does_not_mask_a_missing_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression: a transmitted-but-not-pushed SyncRecord (quotation_transmission
    # mints one with provider=ZOHO_CRM but a BLANK external_id) must not be
    # counted as a captured external id. Here the enquiry's legacy ZohoId was
    # never backfilled; only the blank record exists. A naive count would see
    # one record and call it even (masking the miss); the gate must still block.
    enq = EnquiryFactory(legacy_id="100")
    SyncRecordFactory(target=enq, provider=SyncProvider.ZOHO_CRM, external_id="")
    _zero_zoho_expected_gaps(monkeypatch)
    _patch(monkeypatch, [], responses=_integration_responses(enquire=["100"]))

    with pytest.raises(CommandError, match=r"VillaEnquire\.ZohoId: continuity gap 1"):
        _run("--integrations")


@pytest.mark.django_db
def test_missing_zoho_id_column_is_marked_not_a_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 24-Apr-2025 prod dump has no ZohoId column on VillaQuotationMaster.
    The continuity section must render a clearly-marked "no ZohoId column"
    row for that table — never crash, never block — while still checking the
    tables that do carry the column. VillaBooking is not probed at all
    (GAP-108: bookings are not loaded, so there is no continuity target)."""
    prop = PropertyFactory(legacy_id="10")
    SyncRecordFactory(target=prop, provider=SyncProvider.ZOHO_CRM)
    _zero_zoho_expected_gaps(monkeypatch)
    _patch(
        monkeypatch,
        [],
        responses=_integration_responses(
            master=["10"],
            without_zoho_column={"VillaQuotationMaster"},
        ),
    )

    output = _run("--integrations")

    assert "no ZohoId column" in output
    assert "VillaQuotationMaster.ZohoId" in output
    assert "VillaBooking.ZohoId" not in output
    assert "BLOCKER" not in output


@pytest.mark.django_db
def test_missing_zoho_id_column_does_not_mask_real_blockers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A genuine continuity gap on a column-bearing table must still block even
    # when other tables lack the column entirely.
    PropertyFactory(legacy_id="10")  # loaded, but no SyncRecord backfilled
    _zero_zoho_expected_gaps(monkeypatch)
    _patch(
        monkeypatch,
        [],
        responses=_integration_responses(
            master=["10"],
            without_zoho_column={"VillaQuotationMaster"},
        ),
    )

    with pytest.raises(CommandError, match=r"VillaMaster\.ZohoId: continuity gap 1"):
        _run("--integrations")


@pytest.mark.django_db
def test_calibrated_zoho_expected_gap_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """VillaMaster's calibrated continuity expected_gap=1 (the Temenos
    duplicate pair — legacy 88 & 339 share one ZohoId, only the first loaded
    row gets the SyncRecord) must pass without blocking, and the continuity
    table must show the expected column like the main table does."""
    first = PropertyFactory(legacy_id="88")
    PropertyFactory(legacy_id="339")  # duplicate "Temenos" — no SyncRecord
    SyncRecordFactory(target=first, provider=SyncProvider.ZOHO_CRM)
    _patch(monkeypatch, [], responses=_integration_responses(master=["88", "339"]))

    output = _run("--integrations")

    assert "BLOCKER" not in output
    # Pin the calibrated value where it is used, not just in the SPECS tuple.
    master_spec = next(s for s in SyncRecordZohoLoader.SPECS if s.table == "VillaMaster")
    assert master_spec.expected_gap == 1
    assert all(s.expected_gap == 0 for s in SyncRecordZohoLoader.SPECS if s.table != "VillaMaster")
    # The continuity table shows an expected column (header printed once for
    # the section, alongside the main table's own).
    zoho_section = output.split("Zoho external-ID continuity:")[1]
    assert "expected" in zoho_section


@pytest.mark.django_db
def test_zoho_gap_beyond_calibrated_expected_still_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Two loaded VillaMaster rows with a ZohoId and no SyncRecord at all:
    # gap 2 != the calibrated expected 1 → must still block.
    PropertyFactory(legacy_id="88")
    PropertyFactory(legacy_id="339")
    _patch(monkeypatch, [], responses=_integration_responses(master=["88", "339"]))

    with pytest.raises(CommandError, match=r"VillaMaster\.ZohoId: continuity gap 2 != expected 1"):
        _run("--integrations")


@pytest.mark.django_db
def test_person_channel_checks_exclude_the_client_slice() -> None:
    """Dry-run item 3: `ClientLoader` reconciles VillaClientDetails email/phone
    columns onto `client-` Persons, but the legacy side of these checks counts
    only VillaContactEmail/VillaContactTele. Channels owned by a client-Person
    must be excluded from the loaded count (mirrors the "Person (owner/agent)"
    slice split) or every client channel shows as a negative gap."""
    from accounts.factories import PersonEmailFactory, PersonFactory, PersonPhoneFactory
    from data_migration.management.commands.reconcile_legacy import _CHECKS

    owner = PersonFactory(legacy_id="10")  # VillaContact slice
    client = PersonFactory(legacy_id="client-55")  # VillaClientDetails slice
    PersonEmailFactory(contact=owner, email="owner@example.com", legacy_id="1")
    PersonEmailFactory(contact=client, email="client@example.com", legacy_id="2")  # excluded
    PersonPhoneFactory(contact=owner, number="+44 1", legacy_id="1")
    PersonPhoneFactory(contact=client, number="+44 2", legacy_id="2")  # excluded
    # GAP-108: a staff-added channel on a loaded owner has no legacy twin.
    PersonEmailFactory(contact=owner, email="staff@example.com", is_primary=False)
    PersonPhoneFactory(contact=owner, number="+44 3", is_primary=False)

    by_label = {c.label: c for c in _CHECKS}
    email_check = by_label["PersonEmail"]
    phone_check = by_label["PersonPhone"]
    assert email_check.loaded_count is not None
    assert phone_check.loaded_count is not None

    assert email_check.loaded_count(email_check.model) == 1
    assert phone_check.loaded_count(phone_check.model) == 1


@pytest.mark.django_db
def test_organisation_agency_check_counts_only_agencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """GAP-046: the Organisation check compares distinct normalised legacy
    companies against the loaded *agency* count (non-agency orgs are excluded),
    catching a silent 'zero orgs created' backfill regression."""
    from accounts.enums import OrgType
    from accounts.factories import OrganisationFactory

    OrganisationFactory(org_type=OrgType.AGENCY)
    OrganisationFactory(org_type=OrgType.AGENCY)
    OrganisationFactory(org_type=OrgType.SUPPLIER)  # excluded from the agency count

    org_check = next(c for c in reconcile_legacy._CHECKS if c.label == "Organisation (agency)")
    _patch(
        monkeypatch,
        [org_check],
        responses={"DISTINCT LTRIM(RTRIM(Company))": 2},  # legacy 2 - loaded 2 agencies = gap 0
    )

    output = _run()

    assert "Organisation (agency)" in output
    assert "OK" in output and "BLOCKER" not in output


_BOOKING_INVARIANT_LABELS = (
    "Booking with legacy_id (must be 0)",
    "Payment with legacy_id (must be 0)",
    "BookingChargeItem with legacy_id (must be 0)",
)


@pytest.mark.parametrize("label", _BOOKING_INVARIANT_LABELS)
def test_booking_checks_are_inverted_to_must_be_zero(label: str) -> None:
    """GAP-089 / GAP-108: the booking, payment and charge-item loaders are
    unregistered (bookings come from the Past Bookers sheet), so the legacy
    side is `SELECT 0` and the old legacy-count checks are gone."""
    _check(label)
    legacy_queries = " ".join(c.legacy_query for c in reconcile_legacy._CHECKS)
    assert "VillaBooking" not in legacy_queries
    assert "VillaPayment" not in legacy_queries


@pytest.mark.django_db
def test_booking_invariants_count_only_legacy_stamped_rows(booking: Booking) -> None:
    """Organic rows (legacy_id NULL — sheet imports, staff writes) never count;
    any row carrying a legacy_id means a booking loader ran."""
    from decimal import Decimal

    from payments.enums import PaymentMethod, PaymentPurpose, PaymentStatus
    from payments.models.payment import Payment
    from reservations.factories import BookingChargeItemFactory
    from reservations.models.charge_item import BookingChargeItem

    booking_check, payment_check, charge_check = (_check(lbl) for lbl in _BOOKING_INVARIANT_LABELS)
    assert booking_check.model is Booking
    assert payment_check.model is Payment
    assert charge_check.model is BookingChargeItem
    assert booking_check.loaded_count is not None
    assert payment_check.loaded_count is not None
    assert charge_check.loaded_count is not None

    assert booking_check.loaded_count(Booking) == 1  # the fixture is loader-minted
    Booking.objects.filter(pk=booking.pk).update(legacy_id=None)
    assert booking_check.loaded_count(Booking) == 0

    common = {"booking": booking, "currency": booking.currency}
    BookingChargeItemFactory(legacy_id=None, **common)
    assert charge_check.loaded_count(BookingChargeItem) == 0
    BookingChargeItemFactory(legacy_id="31", **common)
    assert charge_check.loaded_count(BookingChargeItem) == 1

    payment_kwargs = {
        "booking": booking,
        "status": PaymentStatus.PENDING,
        "amount": Decimal("10.00"),
        "currency": booking.currency,
        "payment_method": PaymentMethod.CARD,
    }
    Payment.objects.filter(booking=booking).delete()
    Payment.objects.create(purpose=PaymentPurpose.BALANCE, legacy_id=None, **payment_kwargs)
    assert payment_check.loaded_count(Payment) == 0
    Payment.objects.create(purpose=PaymentPurpose.ADJUSTMENT, legacy_id="d-1", **payment_kwargs)
    assert payment_check.loaded_count(Payment) == 1


@pytest.mark.django_db
def test_loaded_booking_with_legacy_id_blocks_reconcile(
    monkeypatch: pytest.MonkeyPatch, booking: Booking
) -> None:
    check = _check("Booking with legacy_id (must be 0)")
    _patch(monkeypatch, [check], responses={"SELECT 0": 0})

    with pytest.raises(CommandError, match="Booking with legacy_id"):
        _run()


@pytest.mark.django_db
def test_extra_check_counts_only_ported_live_catalogue_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GAP-107: legacy live extras on villas PropertyLoader loads (`IsExTra
    = 1`, `DeletedAt IS NULL` on the rate row AND the villa, non-blank villa
    name) reconcile gap-0 against `pricing.Extra` rows ExtraLoader stamped
    with a legacy_id and left active; a retired ported extra (the full-run
    sweep) and staff-created extras never move the gap."""
    from pricing.factories import ExtraFactory
    from pricing.models.extra import Extra

    ExtraFactory(legacy_id="7")
    ExtraFactory(legacy_id="8", is_active=False)  # retired — legacy side drops it too
    ExtraFactory()  # staff-created — excluded

    check = next(c for c in reconcile_legacy._CHECKS if c.label == "Extra")
    assert check.model is Extra
    assert check.expected_gap == 0
    assert "r.IsExTra = 1" in check.legacy_query
    assert "r.DeletedAt IS NULL" in check.legacy_query
    assert "JOIN VillaMaster m" in check.legacy_query
    assert "m.DeletedAt IS NULL" in check.legacy_query
    assert check.loaded_count is not None
    assert check.loaded_count(check.model) == 1

    # Keyed on the full query: the RateBand check shares its shorter needles.
    _patch(monkeypatch, [check], responses={check.legacy_query: 1})
    assert "BLOCKER" not in _run()


@pytest.mark.django_db
def test_property_finance_check_counts_only_rows_with_a_legacy_twin() -> None:
    """GAP-107: the GAP-070 owner-contact fallback mints `PropertyFinance`
    rows with no `VillaFinance` twin (legacy_id NULL), and `snapshot_defaults`
    mints one per organically-created property. Neither may move the
    documented 1236 gap, so the loaded side counts only stamped rows."""
    from properties.models.finance import PropertyFinance

    # PropertyFactory snapshots a finance row per property (the real
    # `snapshot_defaults` shape, legacy_id NULL); stamp only the per-villa one.
    PropertyFactory(legacy_id="900")
    PropertyFactory(legacy_id="901")  # fallback villa: row stays NULL
    PropertyFactory()  # organic: snapshot row stays NULL
    assert PropertyFinance.objects.filter(legacy_id__isnull=True).count() == 3
    PropertyFinance.objects.filter(property__legacy_id="900").update(legacy_id="10")

    check = next(c for c in reconcile_legacy._CHECKS if c.label == "PropertyFinance")
    assert check.model is PropertyFinance
    assert "VillaFinance" in check.legacy_query
    assert check.expected_gap == 1236
    assert check.loaded_count is not None
    assert check.loaded_count(check.model) == 1


def test_documented_expected_gaps_are_encoded() -> None:
    # The documented carve-outs from CUTOVER.md §5 must live in code (this
    # module is their single source of truth).
    by_label = {c.label: c.expected_gap for c in reconcile_legacy._CHECKS}
    assert by_label["CollectionMembership"] == 9
    # BUG-030 §6: the England row (`UK`) no longer mints a 24th Country.
    assert by_label["Country (legacy)"] == -227
    # BUG-030 §11: pinned 0 until the GAP-108 dry run executes the SQL.
    assert by_label["PropertyFeature"] == 0
    assert by_label["PropertyFinance"] == 1236
    assert by_label["Currency"] == 4
    # Recalibrated 2026-09-14 (BUG-028) against the 24-Apr-2025 prod dump —
    # itemised decomposition lives on the _CHECKS entry (reconcile_legacy).
    assert by_label["RateBand"] == 4492
    # GAP-108: the blank-name villa left the legacy side (`live_villa_sql`).
    assert by_label["Property"] == 0
    # GAP-108: (mapping, role) composites on the 3 soft-deleted villas.
    assert by_label["PropertyContactAssignment"] == 6
    # GAP-107: the legacy side mirrors PropertyLoader's villa filter, so the
    # 12 extras on unloaded villas (24-Apr-2025 dump) never enter the gap.
    assert by_label["Extra"] == 0


@pytest.mark.django_db
def test_currency_active_check_counts_imported_live_currencies() -> None:
    """BUG-028: deleted VillaCurrency rows load retired, so the bare total
    cannot say whether the live rows came in active."""
    from data_migration.loaders._util import legacy_deleted_sql
    from data_migration.management.commands.reconcile_legacy import _CHECKS

    Currency.objects.create(code="EUR", name="Euro", legacy_id="3")
    Currency.objects.create(code="GBP", name="Pound", legacy_id="1", is_active=False)
    Currency.objects.create(code="USD", name="Dollar")  # staff/seeded — not counted

    check = {c.label: c for c in _CHECKS}["Currency (active)"]
    assert check.loaded_count is not None
    assert check.loaded_count(check.model) == 1
    assert check.expected_gap == 0
    assert legacy_deleted_sql() in check.legacy_query


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("eur_legacy_id", "expected"),
    [("3", 3), ("2", 2), (None, 0), ("junk", 0), ("absent", 0)],
)
def test_currency_eur_check_reports_the_claiming_legacy_id(
    eur_legacy_id: str | None, expected: int
) -> None:
    """BUG-028: EUR must carry the LIVE legacy row's id (3 on the dump). The
    loaded side must never raise — the reconcile driver has no try/except."""
    from data_migration.management.commands.reconcile_legacy import _CHECKS

    if eur_legacy_id != "absent":
        Currency.objects.create(code="EUR", name="Euro", legacy_id=eur_legacy_id)

    check = {c.label: c for c in _CHECKS}["Currency EUR legacy_id (live row)"]
    assert check.loaded_count is not None
    assert check.loaded_count(check.model) == expected
    assert check.expected_gap == 0
    assert "Code = 'EUR'" in check.legacy_query


def _check(label: str) -> _Check:
    check = next(c for c in reconcile_legacy._CHECKS if c.label == label)
    assert check.legacy_query == "SELECT 0"
    assert check.expected_gap == 0
    assert check.loaded_count is not None
    return check


@pytest.mark.django_db
def test_finance_null_calculation_type_check_counts_stamped_rows_only() -> None:
    """BUG-028: any of the four calculation types NULL on a stamped row is a
    type-map regression; unstamped (fallback / organic) rows are not counted."""
    from properties.enums import CommissionCalcType, DepositCalcType
    from properties.models.finance import PropertyFinance

    full = {
        "commission_calculation_type": CommissionCalcType.PERCENT,
        "deposit_calculation_type": DepositCalcType.PERCENT,
        "interim_calculation_type": DepositCalcType.PERCENT,
        "security_deposit_calculation_type": DepositCalcType.PERCENT,
    }
    PropertyFactory(legacy_id="900")
    PropertyFactory(legacy_id="901")
    PropertyFactory()  # organic: all-NULL snapshot row, legacy_id NULL
    PropertyFinance.objects.filter(property__legacy_id="900").update(legacy_id="10", **full)
    PropertyFinance.objects.filter(property__legacy_id="901").update(
        legacy_id="11", **{**full, "interim_calculation_type": None}
    )

    check = _check("PropertyFinance NULL calculation type (must be 0)")
    assert check.model is PropertyFinance
    assert check.loaded_count(check.model) == 1  # type: ignore[misc]


@pytest.mark.django_db
def test_settings_without_currency_check_counts_imported_villas_only() -> None:
    from properties.models.settings import PropertySettings

    eur = Currency.objects.create(code="EUR", name="Euro", symbol="E", legacy_id="3")
    PropertyFactory(legacy_id="900")
    PropertyFactory(legacy_id="901")  # imported, currency unset → counted
    PropertyFactory()  # organic, currency unset → not counted
    PropertySettings.objects.filter(property__legacy_id="900").update(currency=eur)

    check = _check("PropertySettings without currency (must be 0)")
    assert check.model is PropertySettings
    assert check.loaded_count(check.model) == 1  # type: ignore[misc]


@pytest.mark.django_db
def test_rate_band_value_checks_count_imported_bands_only() -> None:
    """BUG-028: an imported non-POA band priced at 0.00 would quote a free
    stay, and an imported unapproved band would never price."""
    from decimal import Decimal

    from pricing.factories import RateBandFactory

    RateBandFactory(legacy_id="1", nightly=Decimal("250.00"))  # fine
    RateBandFactory(legacy_id="2", nightly=Decimal("0.00"))  # counted (price)
    RateBandFactory(legacy_id="3", nightly=Decimal("250.00"), weekly=Decimal("0"))  # counted
    RateBandFactory(legacy_id="4", nightly=None, is_poa=True)  # POA: not counted
    RateBandFactory(legacy_id="5", is_approved=False)  # counted (approval)
    RateBandFactory(nightly=Decimal("0.00"), is_approved=False)  # staff: neither

    priced = _check("RateBand non-POA priced <= 0 (must be 0)")
    assert priced.loaded_count(priced.model) == 2  # type: ignore[misc]
    unapproved = _check("RateBand unapproved imported (must be 0)")
    assert unapproved.loaded_count(unapproved.model) == 1  # type: ignore[misc]


@pytest.mark.django_db
def test_property_feature_check_counts_manual_links_between_loaded_rows() -> None:
    """BUG-030 §11: the through table gets its own check. Loaded side = manual
    (`is_derived=False`) links whose property AND feature both carry a
    legacy_id — GAP-067 derived rows and staff-made links on organic rows
    never count."""
    from properties.models.features import Feature, PropertyFeature

    loaded_prop = cast(Property, PropertyFactory(legacy_id="500"))
    loaded_feature = cast(Feature, FeatureFactory(legacy_id="42"))
    derived_feature = cast(Feature, FeatureFactory(legacy_id="43"))
    staff_feature = cast(Feature, FeatureFactory())
    organic_prop = cast(Property, PropertyFactory())
    through = Property.features.through
    through.objects.create(property=loaded_prop, feature=loaded_feature)
    through.objects.create(property=loaded_prop, feature=derived_feature, is_derived=True)
    through.objects.create(property=loaded_prop, feature=staff_feature)  # staff-made feature
    through.objects.create(property=organic_prop, feature=loaded_feature)  # organic villa

    check = next(c for c in reconcile_legacy._CHECKS if c.label == "PropertyFeature")
    assert check.model is PropertyFeature
    assert check.expected_gap == 0
    assert "VillaFeaturesMappings" in check.legacy_query
    # The legacy side applies the same deleted → live-namesake remap as the
    # loader, in one derived table, and mirrors PropertyLoader's villa filter.
    assert "LOWER(LTRIM(RTRIM(t.Name))) = LOWER(LTRIM(RTRIM(f.Name)))" in check.legacy_query
    # The twin's category must be loadable (named), as FeatureLoader requires.
    assert "LTRIM(RTRIM(ISNULL(c.Name, ''))) <> ''" in check.legacy_query
    assert "COUNT(DISTINCT CONCAT(x.VillaId, '-', x.ResolvedId))" in check.legacy_query
    assert check.loaded_count is not None
    assert check.loaded_count(check.model) == 1


def test_collection_membership_gap_records_its_composition() -> None:
    check = next(c for c in reconcile_legacy._CHECKS if c.label == "CollectionMembership")
    assert check.expected_gap == 9
    assert "VillaCollection WHERE DeletedAt IS NULL" not in check.legacy_query


@pytest.mark.parametrize(
    ("label", "predicate"),
    [
        ("Enquiry", "DeletedAt IS NULL"),
        ("Room", "ISNULL(IsActive, 0) = 1"),
        ("Room placement (GAP-065)", "ISNULL(IsActive, 0) = 1"),
        ("PropertyFeature", "ISNULL(m.IsActive, 0) = 1"),
        ("CollectionMembership", "ISNULL(IsActive, 0) = 1"),
        ("PropertyNearbyPlace", "ISNULL(IsActive, 0) = 1"),
    ],
)
def test_soft_delete_filters_mirror_the_loaders(label: str, predicate: str) -> None:
    """GAP-108: ResProd soft-deletes these rows; each loader filters them
    out, so the legacy side of its reconcile check must too."""
    check = next(c for c in reconcile_legacy._CHECKS if c.label == label)
    assert predicate in check.legacy_query


@pytest.mark.parametrize(
    ("label", "alias"),
    [
        ("Property", ""),
        ("RatePlan (villas with a loaded regime)", "m."),
        ("Extra", "m."),
        ("PropertyFeature", "v."),
    ],
)
def test_villa_scoped_checks_use_the_live_villa_filter(label: str, alias: str) -> None:
    """GAP-108: every legacy query restricted to villas PropertyLoader loads
    shares `live_villa_sql` — live AND non-blank `Name` — so a blank-name
    villa (543 on ResProd) never enters a gap."""
    from data_migration.loaders._util import live_villa_sql

    check = next(c for c in reconcile_legacy._CHECKS if c.label == label)
    assert live_villa_sql(alias) in check.legacy_query


def test_night_parity_query_excludes_blank_name_villas() -> None:
    """The fake cursor cannot evaluate SQL, so pin the filter on the text:
    a blank-name villa's rate rows must not reach the legacy side (it has no
    Property, so it would read as a villa with every night lost)."""
    from data_migration.loaders._util import live_villa_sql

    assert f"JOIN VillaMaster m ON m.Id = s.VillaId AND {live_villa_sql('m.')} " in (
        reconcile_legacy.NIGHT_PARITY_QUERY
    )


def test_every_villa_master_query_uses_the_live_villa_filter() -> None:
    """A new check reading VillaMaster must not hand-roll a partial filter
    (e.g. `DeletedAt IS NULL` alone, which counts the blank-name villa)."""
    import re

    from data_migration.loaders._util import live_villa_sql

    queries = [c.legacy_query for c in reconcile_legacy._CHECKS]
    queries.append(reconcile_legacy.NIGHT_PARITY_QUERY)
    villa_queries = [q for q in queries if "VillaMaster" in q]
    # 5 + GAP-108 U6: Location / Capacity / Settings / Description /
    # RoomBeds / PropertyService.
    assert len(villa_queries) == 11
    for query in villa_queries:
        # `FROM VillaMaster WHERE …` (no alias), `JOIN VillaMaster m ON …` or
        # `FROM VillaMaster m LEFT JOIN …`.
        match = re.search(r"VillaMaster (?!WHERE )(\w+) ", query)
        prefix = f"{match.group(1)}." if match else ""
        assert live_villa_sql(prefix) in query, query


def test_agency_check_excludes_placeholder_companies() -> None:
    """BUG-030 §15: the loader maps NA / N/A / - to no agency, so the legacy
    side must not count them as a distinct company either."""
    check = next(c for c in reconcile_legacy._CHECKS if c.label == "Organisation (agency)")
    assert "UPPER(LTRIM(RTRIM(Company))) NOT IN ('-', 'N/A', 'NA')" in check.legacy_query


# --- GAP-108 U5: loaded counts are legacy rows only ---------------------------
#
# Organic rows (legacy_id NULL: staff writes, `createsuperuser`, seeds) must
# never move a loaded count, or the reconcile gap drifts between dry runs.
# Checks that legitimately count NULL-legacy_id rows, each with its reason:
_COUNTS_ORGANIC_ROWS: dict[str, str] = {
    "Country (legacy)": "the properties.0002 ISO seed has no legacy_id; legacy rows match onto it",
    "Organisation (agency)": "organisation_for_company_name never stamps legacy_id on agencies",
    "Organisation named NA / N/A / - (must be 0)": (
        "agencies carry no legacy_id, and a placeholder-named org is a defect whoever wrote it"
    ),
}


def _has_legacy_id(model: type[object]) -> bool:
    return any(f.name == "legacy_id" for f in model._meta.get_fields())  # type: ignore[attr-defined]


def _organic_property() -> Property:
    return cast(Property, PropertyFactory())


def _organic_customer() -> Person:
    from accounts.factories import CustomerPersonFactory

    return cast(Person, CustomerPersonFactory())


def _organic_booking() -> Booking:
    from datetime import date

    from pricing.factories import CurrencyFactory
    from reservations.factories import TermsVersionFactory, make_occupying_booking
    from reservations.models import TermsVersion

    return make_occupying_booking(
        property=_organic_property(),
        person=_organic_customer(),
        currency=cast(Currency, CurrencyFactory(code="GBP")),
        terms=cast(TermsVersion, TermsVersionFactory()),
        date_from=date(2027, 6, 1),
        date_to=date(2027, 6, 8),
    )


def _organic_row(model: type[object]) -> None:
    """Create one organic (legacy_id NULL) row of `model`, shaped to hit the
    check filters where it can (e.g. a NET plan, a 0.00 unapproved band)."""
    from datetime import UTC, date, datetime
    from decimal import Decimal

    from accounts.factories import (
        PersonEmailFactory,
        PersonFactory,
        PersonPhoneFactory,
        UserFactory,
    )
    from accounts.models import User
    from accounts.models.person import PersonEmail, PersonPhone
    from payments.enums import PaymentMethod, PaymentPurpose, PaymentStatus
    from payments.models.payment import Payment
    from pricing.factories import (
        CurrencyFactory,
        ExtraFactory,
        RateBandFactory,
        RatePeriodFactory,
        RatePlanFactory,
    )
    from pricing.models.extra import Extra
    from pricing.models.rate import RateBand, RatePlan
    from properties.enums import ImageKind, PriceBasis
    from properties.factories import (
        CollectionFactory,
        FeatureCategoryFactory,
        NearbyPlaceTypeFactory,
        PropertyContactAssignmentFactory,
        PropertyNearbyPlaceFactory,
        PropertyServiceFactory,
        RegionFactory,
        RoomFactory,
    )
    from properties.models.contacts import PropertyContactAssignment
    from properties.models.descriptions import PropertyDescription
    from properties.models.features import (
        Collection,
        CollectionMembership,
        Feature,
        FeatureCategory,
    )
    from properties.models.finance import PropertyFinance
    from properties.models.geo import Country, NearbyPlaceType, PropertyNearbyPlace, Region
    from properties.models.images import PropertyImage
    from properties.models.rooms import Room
    from properties.models.services import PropertyService
    from reservations.enums import BookingHoldReason
    from reservations.factories import BookingChargeItemFactory
    from reservations.models.booking import BookingHold
    from reservations.models.charge_item import BookingChargeItem
    from reservations.models.preferences import GuestPreference, GuestPreferenceType
    from reservations.models.quotation import Quotation, QuotationLine

    def _payment() -> None:
        booking = _organic_booking()
        Payment.objects.create(
            booking=booking,
            purpose=PaymentPurpose.ADJUSTMENT,
            status=PaymentStatus.PENDING,
            amount=Decimal("10.00"),
            currency=booking.currency,
            payment_method=PaymentMethod.CARD,
        )

    def _charge_item() -> None:
        booking = _organic_booking()
        BookingChargeItemFactory(booking=booking, currency=booking.currency)

    builders: dict[type[object], object] = {
        Country: lambda: Country.objects.create(
            iso2="QZ", iso3="QZZ", name="Organic land", is_active=True
        ),
        Region: RegionFactory,
        Currency: lambda: CurrencyFactory(code="EUR"),
        NearbyPlaceType: NearbyPlaceTypeFactory,
        FeatureCategory: FeatureCategoryFactory,
        Feature: FeatureFactory,
        User: UserFactory,
        Person: PersonFactory,
        PersonEmail: PersonEmailFactory,
        PersonPhone: PersonPhoneFactory,
        Property: PropertyFactory,
        Collection: CollectionFactory,
        CollectionMembership: lambda: CollectionMembership.objects.create(
            collection=cast(Collection, CollectionFactory()), property=_organic_property()
        ),
        Room: lambda: RoomFactory(placement_note="Ground floor"),
        PropertyImage: lambda: PropertyImage.objects.create(
            property=_organic_property(), image="organic.jpg", kind=ImageKind.GALLERY
        ),
        PropertyNearbyPlace: PropertyNearbyPlaceFactory,
        PropertyDescription: PropertyFactory,  # factory OVERVIEW section
        PropertyService: PropertyServiceFactory,
        RatePlan: lambda: RatePeriodFactory(plan=RatePlanFactory(price_basis=PriceBasis.NET)),
        RateBand: lambda: RateBandFactory(nightly=Decimal("0.00"), is_approved=False),
        Extra: ExtraFactory,
        PropertyContactAssignment: lambda: PropertyContactAssignmentFactory(
            contact=PersonFactory()
        ),
        Enquiry: EnquiryFactory,
        PropertyFinance: PropertyFactory,  # `snapshot_defaults` row, all types NULL
        Quotation: lambda: _organic_booking(),
        QuotationLine: lambda: _organic_booking(),
        GuestPreferenceType: lambda: GuestPreferenceType.objects.create(name="Organic pref"),
        GuestPreference: lambda: GuestPreference.objects.create(
            person=_organic_customer(),
            preference_type=GuestPreferenceType.objects.create(name="Organic pref"),
        ),
        Booking: _organic_booking,
        Payment: _payment,
        BookingChargeItem: _charge_item,
        BookingHold: lambda: BookingHold.objects.create(
            property=_organic_property(),
            date_from=date(2099, 1, 1),
            date_to=date(2099, 1, 8),
            expires_at=datetime(2099, 1, 1, tzinfo=UTC),
            reason=BookingHoldReason.OWNER_BLOCK.value,
        ),
    }
    builder = builders[model]
    assert callable(builder)
    builder()
    assert model._default_manager.filter(legacy_id__isnull=True).exists()  # type: ignore[attr-defined]


_LEGACY_ID_CHECK_LABELS = [
    c.label
    for c in reconcile_legacy._CHECKS
    if _has_legacy_id(c.model) and c.label not in _COUNTS_ORGANIC_ROWS
]


@pytest.mark.django_db
@pytest.mark.parametrize("label", _LEGACY_ID_CHECK_LABELS)
def test_organic_row_does_not_move_the_loaded_count(label: str) -> None:
    check = next(c for c in reconcile_legacy._CHECKS if c.label == label)
    before = check.count_loaded()
    _organic_row(check.model)
    assert check.count_loaded() == before


def test_allowlisted_organic_counts_are_real_checks() -> None:
    labels = {c.label for c in reconcile_legacy._CHECKS}
    assert set(_COUNTS_ORGANIC_ROWS) <= labels
    assert all(reason.strip() for reason in _COUNTS_ORGANIC_ROWS.values())


def test_default_loaded_count_is_only_used_on_models_with_a_legacy_id() -> None:
    """The fallback filters `legacy_id__isnull=False`; a check on a model
    without one must supply its own `loaded_count`."""
    for check in reconcile_legacy._CHECKS:
        if check.loaded_count is None:
            assert _has_legacy_id(check.model), check.label


@pytest.mark.django_db
def test_default_loaded_count_counts_legacy_rows_only() -> None:
    check = _Check("SELECT COUNT(*) FROM VillaEnquire", Enquiry, "Enquiry")
    EnquiryFactory(legacy_id="1")
    EnquiryFactory()
    assert check.count_loaded() == 1


@pytest.mark.django_db
def test_createsuperuser_leaves_every_loaded_count_unchanged() -> None:
    """CUTOVER: the first admin is created after the load, then reconcile runs
    again — it must print the same table."""
    before = {c.label: c.count_loaded() for c in reconcile_legacy._CHECKS}
    call_command("createsuperuser", interactive=False, email="admin@example.com", verbosity=0)
    after = {c.label: c.count_loaded() for c in reconcile_legacy._CHECKS}
    assert after == before


def test_owner_agent_check_counts_deleted_contacts() -> None:
    """ContactLoader reads every VillaContact row and loads a deleted one as
    INACTIVE, so the legacy side must not filter on `DeletedAt`."""
    from data_migration.loaders.people import ContactLoader

    check = next(c for c in reconcile_legacy._CHECKS if c.label == "Person (owner/agent)")
    assert "WHERE" not in ContactLoader.legacy_query
    assert check.legacy_query == "SELECT COUNT(*) FROM VillaContact"


# --- GAP-108 U6: every registered loader has a reconcile check (ACCEPTANCE S2) --
#
# Hand-written on purpose: registering a loader (or dropping a check) must
# force a conscious edit here. Values are `_CHECKS` labels, or one of the
# `_SECTIONS` sentinels below for coverage that is not a row-count check.
_NIGHT_PARITY = "[section] RatePeriod night parity"
_ZOHO_CONTINUITY = "[section] --integrations Zoho continuity"
_SECTIONS: dict[str, str] = {
    # RatePeriod rows come out of `flatten_rate_grid` (trims, conflict
    # splits), so no SQL can count them; the per-villa night-set comparison
    # is their check.
    _NIGHT_PARITY: "_night_parity_section",
    # SyncRecord backfill is only reconciled under `--integrations`.
    _ZOHO_CONTINUITY: "_zoho_continuity_section",
}
_LOADER_CHECKS: dict[str, list[str]] = {
    "country": ["Country (legacy)", "Country (active)"],
    "region": ["Region", "Region (imported)", "Region (active)"],
    "currency": ["Currency", "Currency (active)", "Currency EUR legacy_id (live row)"],
    "nearby_place_type": ["NearbyPlaceType"],
    "feature_category": ["FeatureCategory"],
    "feature": ["Feature"],
    "property_defaults": ["PropertyDefaults currency legacy_id (CPD row)"],
    "user": ["User"],
    "contact": [
        "Person (owner/agent)",
        "Organisation (agency)",
        "Organisation named NA / N/A / - (must be 0)",
    ],
    "contact_email": ["PersonEmail", "Person (owner/agent) primary email count != 1 (must be 0)"],
    "contact_phone": ["PersonPhone"],
    "property": [
        "Property",
        "PropertyLocation",
        "PropertyCapacity",
        "PropertySettings",
        "PropertySettings without currency (must be 0)",
        "PropertyDescription",
        "Property slug containing :// (must be 0)",
    ],
    "collection": ["Collection"],
    "collection_membership": ["CollectionMembership"],
    "room": ["Room", "Room placement (GAP-065)", "RoomBeds"],
    "property_image": ["PropertyImage"],
    "nearby_place": ["PropertyNearbyPlace"],
    "property_feature": ["PropertyFeature"],
    "rate_plan": [
        "RatePlan (villas with a loaded regime)",
        "RatePlan non-GROSS basis (must be 0)",
        "PropertyService",
    ],
    "rate_rule": [
        "RateBand",
        "RateBand non-POA priced <= 0 (must be 0)",
        "RateBand unapproved imported (must be 0)",
        _NIGHT_PARITY,
    ],
    "extra": ["Extra"],
    "property_contact_assignment": ["PropertyContactAssignment"],
    "client": ["Person (client)"],
    "enquiry": ["Enquiry"],
    "property_finance": ["PropertyFinance", "PropertyFinance NULL calculation type (must be 0)"],
    "quotation": ["Quotation"],
    "quotation_line": ["QuotationLine"],
    "guest_preference_type": ["GuestPreferenceType"],
    "guest_preference": ["GuestPreference"],
    "availability_block": ["VillaAvailability (future days)"],
    "syncrecord_zoho": [_ZOHO_CONTINUITY],
}
# Checks that guard unregistered loaders (GAP-108 U1), so no key above owns them.
_UNREGISTERED_LOADER_CHECKS = set(_BOOKING_INVARIANT_LABELS)


def test_every_registered_loader_has_a_reconcile_check() -> None:
    from data_migration.registry import LOADERS

    assert set(_LOADER_CHECKS) == set(LOADERS)
    assert all(_LOADER_CHECKS.values())
    labels = {c.label for c in reconcile_legacy._CHECKS}
    for loader, checks in _LOADER_CHECKS.items():
        for label in checks:
            if label in _SECTIONS:
                assert hasattr(reconcile_legacy.Command, _SECTIONS[label]), label
            else:
                assert label in labels, f"{loader}: {label}"


def test_every_reconcile_check_belongs_to_a_loader() -> None:
    mapped = {label for checks in _LOADER_CHECKS.values() for label in checks}
    labels = {c.label for c in reconcile_legacy._CHECKS}
    assert labels - mapped == _UNREGISTERED_LOADER_CHECKS


@pytest.mark.django_db
@pytest.mark.parametrize("label", ["PropertyLocation", "PropertyCapacity", "PropertySettings"])
def test_property_satellite_checks_count_one_row_per_loaded_property(label: str) -> None:
    """PropertyLoader writes location, capacity and settings for every
    property it loads, so the legacy side is the Property query itself."""
    by_label = {c.label: c for c in reconcile_legacy._CHECKS}
    check = by_label[label]
    PropertyFactory(legacy_id="900")
    PropertyFactory(legacy_id="901")
    PropertyFactory()  # organic: its satellites never count
    assert check.legacy_query == by_label["Property"].legacy_query
    assert check.expected_gap == 0
    assert check.count_loaded() == 2


@pytest.mark.django_db
def test_property_description_check_counts_stamped_sections() -> None:
    from data_migration.loaders._util import live_villa_sql
    from properties.models.descriptions import PropertyDescription

    PropertyFactory(legacy_id="900")  # factory OVERVIEW row, legacy_id NULL
    PropertyFactory()
    PropertyDescription.objects.filter(property__legacy_id="900").update(legacy_id="900-overview")

    check = next(c for c in reconcile_legacy._CHECKS if c.label == "PropertyDescription")
    assert check.model is PropertyDescription
    assert check.expected_gap == 0
    # Mirrors the loader: one row per non-blank section, website copy from
    # the MAX(Id) `VillaPropertyImagesDescription` row, loaded villas only.
    assert "SELECT MAX(d2.Id) FROM VillaPropertyImagesDescription d2" in check.legacy_query
    assert live_villa_sql("m.") in check.legacy_query
    for column in ("OverView", "HouseRules", "FeatureDescription", "RoomDescription", "Notes"):
        assert f"m.{column}" in check.legacy_query
    for column in ("WebDesc1", "WebDesc2", "Location1", "Location2"):
        assert f"d.{column}" in check.legacy_query
    assert check.count_loaded() == 1


@pytest.mark.django_db
def test_room_beds_check_counts_beds_of_loaded_rooms() -> None:
    from data_migration.loaders._util import legacy_active_sql, live_villa_sql
    from properties.factories import RoomFactory
    from properties.models.rooms import RoomBeds

    RoomFactory(property=PropertyFactory(legacy_id="900"), legacy_id="10")
    RoomFactory()  # organic room: its beds never count

    check = next(c for c in reconcile_legacy._CHECKS if c.label == "RoomBeds")
    assert check.model is RoomBeds
    assert legacy_active_sql("r.") in check.legacy_query
    assert live_villa_sql("m.") in check.legacy_query
    assert check.count_loaded() == 1


@pytest.mark.django_db
def test_property_service_check_counts_season_inclusion_services() -> None:
    from data_migration.loaders._util import live_villa_sql
    from data_migration.loaders.pricing import PRICED_ROW_PREDICATE
    from properties.factories import PropertyServiceFactory
    from properties.models.services import PropertyService

    PropertyServiceFactory(legacy_id="season:7:svc")
    PropertyServiceFactory()  # staff-created service

    check = next(c for c in reconcile_legacy._CHECKS if c.label == "PropertyService")
    assert check.model is PropertyService
    assert "s.Inclusion" in check.legacy_query
    assert PRICED_ROW_PREDICATE in check.legacy_query
    assert "VillaSeasonDates" in check.legacy_query
    assert live_villa_sql("m.") in check.legacy_query
    assert check.count_loaded() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(("currency_legacy_id", "expected"), [("3", 3), (None, 0), ("", 0)])
def test_property_defaults_check_reports_the_singleton_currency_legacy_id(
    currency_legacy_id: str | None, expected: int
) -> None:
    """A value check, not a count: `get_solo()` auto-creates the singleton,
    so a row count would always pass. The singleton's currency must be the
    one the CPD row names (legacy `CurrencyId`)."""
    from properties.models.defaults import PropertyDefaults

    if currency_legacy_id != "":
        defaults = PropertyDefaults.get_solo()
        defaults.currency = Currency.objects.create(
            code="EUR", name="Euro", legacy_id=currency_legacy_id
        )
        defaults.save()

    check = next(
        c
        for c in reconcile_legacy._CHECKS
        if c.label == "PropertyDefaults currency legacy_id (CPD row)"
    )
    assert check.model is PropertyDefaults
    assert "VillaConfigPropertyDefault ORDER BY Id" in check.legacy_query
    assert check.expected_gap == 0
    assert check.count_loaded() == expected


# --- GAP-108 U7: structural invariants ----------------------------------------


@pytest.mark.django_db
def test_primary_email_invariant_counts_legacy_persons_without_exactly_one_primary() -> None:
    from accounts.factories import PersonEmailFactory, PersonFactory

    one = PersonFactory(legacy_id="1")
    PersonEmailFactory(contact=one, legacy_id="11")
    PersonEmailFactory(contact=one, legacy_id="12", is_primary=False)
    none = PersonFactory(legacy_id="2")
    PersonEmailFactory(contact=none, legacy_id="21", is_primary=False)  # counted
    PersonFactory(legacy_id="3")  # no loaded email: nothing to be primary
    # A staff-added primary on a legacy person is not a loaded email.
    staff_only = PersonFactory(legacy_id="4")
    PersonEmailFactory(contact=staff_only, legacy_id="41", is_primary=False)  # counted
    PersonEmailFactory(contact=staff_only)
    client = PersonFactory(legacy_id="client-5")  # other slice
    PersonEmailFactory(contact=client, legacy_id="51", is_primary=False)
    sheet = PersonFactory(legacy_id="sheet-6")  # other slice
    PersonEmailFactory(contact=sheet, legacy_id="61", is_primary=False)
    PersonEmailFactory(contact=PersonFactory(), is_primary=False)  # organic

    check = _check("Person (owner/agent) primary email count != 1 (must be 0)")
    assert check.model is Person
    assert check.count_loaded() == 2


@pytest.mark.django_db
def test_slug_invariant_counts_legacy_properties_with_a_url_slug() -> None:
    PropertyFactory(legacy_id="1", slug="villa-one")
    PropertyFactory(legacy_id="2", slug="https://villacollective.example/villa-two")  # counted
    PropertyFactory(slug="http://organic.example")  # organic: out of scope

    check = _check("Property slug containing :// (must be 0)")
    assert check.model is Property
    assert check.count_loaded() == 1


@pytest.mark.django_db
def test_placeholder_organisation_invariant_counts_na_names() -> None:
    from accounts.factories import OrganisationFactory

    for name in ("NA", " n/a ", "-", "Dune Travel", "NAVIGATOR"):
        OrganisationFactory(name=name, org_type=OrgType.AGENCY)

    check = _check("Organisation named NA / N/A / - (must be 0)")
    assert check.model is Organisation
    assert check.count_loaded() == 3


def test_property_contact_assignment_check_counts_mapping_role_composites() -> None:
    """The loader writes one row per (mapping, role) — `<MappingId>-<RoleId or
    0>` — so the legacy side counts those composites, not bare mappings."""
    check = next(c for c in reconcile_legacy._CHECKS if c.label == "PropertyContactAssignment")
    assert "LEFT JOIN VillaContactRoleMapping r" in check.legacy_query
    assert "COUNT(DISTINCT CONCAT(m.Id, '-', ISNULL(r.RoleId, 0)))" in check.legacy_query
    assert check.expected_gap == 6
