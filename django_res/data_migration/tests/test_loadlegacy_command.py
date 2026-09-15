"""Per-loader crash isolation in `loadlegacy` (dry-run item 2).

A crash inside one loader must not abort the run: the remaining loaders still
run, the quotation-sequence sync still happens, and the summary table still
prints (with the crash recorded in the failed loader's errors column). The
command then exits non-zero — a `CommandError` *after* the summary — when any
loader crashed or reported errors, mirroring how `reconcile_legacy` signals
blockers.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from data_migration.base import LoadReport
from data_migration.management.commands import loadlegacy
from data_migration.registry import LOADERS

pytestmark = pytest.mark.django_db


class _OkLoader:
    name = "ok"

    def load(self) -> LoadReport:
        return LoadReport(loader=self.name, created=2)


class _CrashLoader:
    name = "crash"

    def load(self) -> LoadReport:
        raise RuntimeError("legacy schema surprise")


class _ErrorReportLoader:
    name = "haserrors"

    def load(self) -> LoadReport:
        report = LoadReport(loader=self.name)
        report.errors.append(("7", "bad row"))
        return report


@pytest.fixture()
def synced(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Replace the quotation-sequence sync with a call recorder."""
    calls: list[bool] = []

    def _fake_sync() -> int:
        calls.append(True)
        return 123

    monkeypatch.setattr(loadlegacy, "sync_quotation_sequence", _fake_sync)
    return calls


def _run(*args: str) -> tuple[str, str]:
    out, err = StringIO(), StringIO()
    call_command("loadlegacy", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def test_clean_run_prints_summary_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, synced: list[bool]
) -> None:
    monkeypatch.setattr(loadlegacy, "LOADERS", {"ok": _OkLoader})

    out, _ = _run("--all")

    assert "ok" in out
    assert "high-water mark 123" in out
    assert synced == [True]


def test_crash_is_isolated_and_run_continues(
    monkeypatch: pytest.MonkeyPatch, synced: list[bool]
) -> None:
    # `crash` registered first: the loaders after it must still run.
    monkeypatch.setattr(loadlegacy, "LOADERS", {"crash": _CrashLoader, "ok": _OkLoader})
    out, err = StringIO(), StringIO()

    with pytest.raises(CommandError, match="crash"):
        call_command("loadlegacy", "--all", stdout=out, stderr=err)

    output = out.getvalue()
    # The summary still printed, with a row for both loaders.
    assert "crash" in output and "ok" in output
    # The crash is recorded as that loader's error, with the exception visible.
    assert "RuntimeError" in output and "legacy schema surprise" in output
    # The sequence sync still ran for whatever loaded.
    assert synced == [True]
    assert "high-water mark 123" in output


def test_reported_errors_exit_nonzero_after_summary(
    monkeypatch: pytest.MonkeyPatch, synced: list[bool]
) -> None:
    monkeypatch.setattr(loadlegacy, "LOADERS", {"haserrors": _ErrorReportLoader})
    out, err = StringIO(), StringIO()

    with pytest.raises(CommandError, match="haserrors"):
        call_command("loadlegacy", "--all", stdout=out, stderr=err)

    output = out.getvalue()
    assert "bad row" in output  # summary (incl. error detail) printed first
    assert synced == [True]


def test_sequence_sync_failure_still_prints_summary_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # BUG-029 §4: the sync used to run outside the isolation — a raise lost
    # every loader's report.
    def _broken_sync() -> int:
        raise RuntimeError("sequence missing")

    monkeypatch.setattr(loadlegacy, "sync_quotation_sequence", _broken_sync)
    monkeypatch.setattr(loadlegacy, "LOADERS", {"ok": _OkLoader})
    out, err = StringIO(), StringIO()

    with pytest.raises(CommandError, match="sync_quotation_sequence"):
        call_command("loadlegacy", "--all", stdout=out, stderr=err)

    output = out.getvalue()
    assert "ok" in output and "sequence missing" in output
    assert "high-water mark" not in output


def test_since_flag_is_retired() -> None:
    # BUG-029: the load is a one-shot into a fresh DB; there is no delta mode.
    with pytest.raises(CommandError, match="since"):
        call_command("loadlegacy", "--all", "--since", "2026-01-01T00:00:00")


def test_every_registered_loader_constructs_without_arguments() -> None:
    for name, loader_cls in LOADERS.items():
        assert loader_cls().name == name


# --- one-shot guard (BUG-029) ---


def _legacy_country() -> None:
    from properties.models.geo import Country

    country, _ = Country.objects.get_or_create(iso2="QA", defaults={"name": "Qatar", "iso3": "QAT"})
    country.legacy_id = "1"
    country.save(update_fields=["legacy_id"])


def _legacy_currency() -> None:
    from pricing.models.currency import Currency

    Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")


def _legacy_property() -> None:
    from properties.factories import PropertyFactory

    PropertyFactory(legacy_id="900")


@pytest.mark.parametrize("seed", [_legacy_country, _legacy_currency, _legacy_property])
def test_all_refuses_a_db_that_already_holds_legacy_rows(
    seed: object, monkeypatch: pytest.MonkeyPatch, synced: list[bool]
) -> None:
    calls: list[str] = []

    class _Recording(_OkLoader):
        def load(self) -> LoadReport:
            calls.append(self.name)
            return super().load()

    monkeypatch.setattr(loadlegacy, "LOADERS", {"ok": _Recording})
    seed()  # type: ignore[operator]

    with pytest.raises(CommandError, match="fresh"):
        _run("--all")

    assert calls == []
    assert synced == []


def test_all_ignores_seeded_rows_without_legacy_id(
    monkeypatch: pytest.MonkeyPatch, synced: list[bool]
) -> None:
    # The country seed migration and blank legacy_ids are not a prior load.
    from properties.models.geo import Country

    Country.objects.get_or_create(iso2="QA", defaults={"name": "Qatar", "iso3": "QAT"})
    Country.objects.filter(iso2="QA").update(legacy_id="")
    monkeypatch.setattr(loadlegacy, "LOADERS", {"ok": _OkLoader})

    _run("--all")

    assert synced == [True]


def test_named_loader_still_runs_on_a_loaded_db(
    monkeypatch: pytest.MonkeyPatch, synced: list[bool]
) -> None:
    # Debug aid: only the production `--all` path is guarded.
    _legacy_country()
    monkeypatch.setattr(loadlegacy, "LOADERS", {"ok": _OkLoader})

    out, _ = _run("ok")

    assert "ok" in out
