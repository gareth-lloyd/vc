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


class _OkLoader:
    name = "ok"

    def __init__(self, since: str | None = None) -> None:
        self.since = since

    def load(self) -> LoadReport:
        return LoadReport(loader=self.name, created=2)


class _CrashLoader:
    name = "crash"

    def __init__(self, since: str | None = None) -> None:
        self.since = since

    def load(self) -> LoadReport:
        raise RuntimeError("legacy schema surprise")


class _ErrorReportLoader:
    name = "haserrors"

    def __init__(self, since: str | None = None) -> None:
        self.since = since

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
