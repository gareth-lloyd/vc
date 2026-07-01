"""Tests for the `reconcile_legacy` gap-enforcement gate.

The command's legacy side is mocked: a fake cursor returns a scripted result
per query (keyed by a query substring, so tests don't depend on execute()
call order), while the loaded count comes from the real (test) DB. This lets
us assert the gap-vs-expected pass/fail logic without a live SQL Server.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from data_migration.management.commands import reconcile_legacy
from data_migration.management.commands.reconcile_legacy import _Check
from integrations.enums import SyncProvider
from integrations.factories import SyncRecordFactory
from properties.factories import PropertyFactory
from reservations.factories import EnquiryFactory
from reservations.models.enquiry import Enquiry


class _FakeCursor:
    """Returns a scripted result keyed by a substring of the executed query.

    A scalar response is read via `fetchone()[0]` (COUNT queries); a list
    response is read via `fetchall()` (the continuity `SELECT Id ...` query),
    yielded as one-tuples. Keying by query rather than by position means adding
    or reordering a check can't silently feed the wrong number to a query.
    """

    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses
        self._last: object = None

    def execute(self, query: str) -> None:
        for needle, value in self._responses.items():
            if needle in query:
                self._last = value
                return
        raise AssertionError(f"no scripted result for query: {query!r}")

    def fetchone(self) -> tuple[object]:
        return (self._last,)

    def fetchall(self) -> list[tuple[object]]:
        assert isinstance(self._last, list), "fetchall() called on a scalar response"
        return [(v,) for v in self._last]


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    checks: list[_Check],
    responses: dict[str, object],
) -> None:
    @contextmanager
    def _fake_cursor() -> Iterator[_FakeCursor]:
        yield _FakeCursor(responses)

    monkeypatch.setattr(reconcile_legacy, "_CHECKS", checks)
    monkeypatch.setattr(reconcile_legacy, "legacy_cursor", _fake_cursor)


def _integration_responses(
    *,
    master: list[str] | None = None,
    contact: list[str] | None = None,
    enquire: list[str] | None = None,
    quotation: list[str] | None = None,
    booking: list[str] | None = None,
    booking_url: int = 0,
    syncdetail_rows: int = 0,
    syncdetail_sites: int = 0,
) -> dict[str, object]:
    """Scripted results for the --integrations sections.

    The five continuity values are the legacy Ids returned by
    `SELECT Id FROM <table> WHERE ZohoId ...`; the three WordPress values are
    scalar COUNTs. Keys are distinctive query substrings.
    """
    return {
        "VillaMaster WHERE ZohoId": master or [],
        "VillaContact WHERE ZohoId": contact or [],
        "VillaEnquire WHERE ZohoId": enquire or [],
        "VillaQuotationMaster WHERE ZohoId": quotation or [],
        "VillaBooking WHERE ZohoId": booking or [],
        "BookingUrl": booking_url,
        "COUNT(*) FROM VillaSyncDetail": syncdetail_rows,
        "DISTINCT SiteId": syncdetail_sites,
    }


def _run(*args: str) -> str:
    out = StringIO()
    call_command("reconcile_legacy", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_gap_equal_to_expected_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    EnquiryFactory.create_batch(2)  # loaded = 2
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
    EnquiryFactory.create_batch(2)  # loaded = 2
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


# --- --integrations flag (P0b) ---


@pytest.mark.django_db
def test_no_integration_sections_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, [_Check("q", Enquiry, "Enquiry")], responses={"q": 0})

    output = _run()

    assert "Zoho external-ID continuity" not in output
    assert "WordPress external-ID surface" not in output


@pytest.mark.django_db
def test_integrations_flag_renders_both_sections(monkeypatch: pytest.MonkeyPatch) -> None:
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
    _patch(monkeypatch, [], responses=_integration_responses(enquire=["100"]))

    with pytest.raises(CommandError, match=r"VillaEnquire\.ZohoId: continuity gap 1"):
        _run("--integrations")


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


def test_documented_expected_gaps_are_encoded() -> None:
    # The six documented carve-outs from CUTOVER.md must live in code (this
    # module is their single source of truth).
    by_label = {c.label: c.expected_gap for c in reconcile_legacy._CHECKS}
    assert by_label["CollectionMembership"] == 308
    assert by_label["PropertyFinance"] == 1236
    assert by_label["Currency"] == 4
    assert by_label["RateBand"] == 3727
    assert by_label["Property"] == 1
    assert by_label["PropertyContactAssignment"] == 1
