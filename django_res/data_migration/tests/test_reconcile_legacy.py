"""Tests for the `reconcile_legacy` gap-enforcement gate.

The command's legacy side is mocked: a fake cursor returns a scripted legacy
count per check, while the loaded count comes from the real (test) DB. This
lets us assert the gap == expected_gap pass/fail logic without a live SQL
Server.
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
    """Returns scripted COUNT(*) results in `execute` order."""

    def __init__(self, counts: list[int]) -> None:
        self._counts = iter(counts)
        self._last = 0

    def execute(self, query: str) -> None:
        self._last = next(self._counts)

    def fetchone(self) -> tuple[int]:
        return (self._last,)


def _patch(monkeypatch: pytest.MonkeyPatch, checks: list[_Check], counts: list[int]) -> None:
    @contextmanager
    def _fake_cursor() -> Iterator[_FakeCursor]:
        yield _FakeCursor(counts)

    monkeypatch.setattr(reconcile_legacy, "_CHECKS", checks)
    monkeypatch.setattr(reconcile_legacy, "legacy_cursor", _fake_cursor)


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
        counts=[7],  # legacy 7 - loaded 2 = gap 5 == expected
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
        counts=[8],  # legacy 8 - loaded 2 = gap 6 != expected 5
    )

    with pytest.raises(CommandError, match="Enquiry: gap 6 != expected 5"):
        _run()


@pytest.mark.django_db
def test_unexpected_gap_on_zero_expected_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    # The common case: expected_gap defaults to 0, so any loss is a blocker.
    _patch(
        monkeypatch,
        [_Check("SELECT COUNT(*) FROM VillaEnquire", Enquiry, "Enquiry")],
        counts=[3],  # legacy 3 - loaded 0 = gap 3 != expected 0
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
        counts=[1, 2],
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


# --- --integrations flag (P0b) ---
#
# With _CHECKS patched to [], the cursor is driven only by the integration
# sections: 5 Zoho-source COUNTs (one per SyncRecordZohoLoader.SPECS) then 3
# WordPress informational COUNTs — 8 scripted values total.


@pytest.mark.django_db
def test_no_integration_sections_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, [_Check("q", Enquiry, "Enquiry")], counts=[0])

    output = _run()

    assert "Zoho external-ID continuity" not in output
    assert "WordPress external-ID surface" not in output


@pytest.mark.django_db
def test_integrations_flag_renders_both_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, [], counts=[0, 0, 0, 0, 0, 7, 12, 2])

    output = _run("--integrations")

    assert "Zoho external-ID continuity" in output
    assert "VillaMaster.ZohoId" in output
    assert "WordPress external-ID surface" in output
    assert "VillaBooking.BookingUrl" in output
    # WordPress counts are informational, never a blocker.
    assert "INFO" in output
    assert "BLOCKER" not in output


@pytest.mark.django_db
def test_zoho_id_without_sync_record_is_a_blocker(monkeypatch: pytest.MonkeyPatch) -> None:
    # VillaMaster has 3 non-blank ZohoIds but no SyncRecord rows exist.
    _patch(monkeypatch, [], counts=[3, 0, 0, 0, 0, 0, 0, 0])

    with pytest.raises(CommandError, match=r"VillaMaster\.ZohoId: 3 external id"):
        _run("--integrations")


@pytest.mark.django_db
def test_zoho_continuity_ok_when_sync_record_present(monkeypatch: pytest.MonkeyPatch) -> None:
    prop = PropertyFactory()
    SyncRecordFactory(target=prop, provider=SyncProvider.ZOHO_CRM)
    # VillaMaster legacy ext-id count 1 matches the one SyncRecord → gap 0.
    _patch(monkeypatch, [], counts=[1, 0, 0, 0, 0, 0, 0, 0])

    output = _run("--integrations")

    assert "BLOCKER" not in output


def test_documented_expected_gaps_are_encoded() -> None:
    # The six documented carve-outs from CUTOVER.md must live in code (this
    # module is their single source of truth).
    by_label = {c.label: c.expected_gap for c in reconcile_legacy._CHECKS}
    assert by_label["CollectionMembership"] == 308
    assert by_label["PropertyFinance"] == 1236
    assert by_label["Currency"] == 4
    assert by_label["RateRule"] == 3462
    assert by_label["Property"] == 1
    assert by_label["PropertyContactAssignment"] == 1
