"""GAP-094 retro — Django system check for the contract pipeline's
environment dependency.

`auto_generate_contract` swallows every failure and only logs, and there is
no worker or alerting. WeasyPrint's native toolchain missing from the image
would otherwise mean no guest gets a contract until someone opens a
Documents tab. The check runs on every `manage.py` command that keeps the
default system checks — including Render's `migrate` pre-deploy — so the
fault is loud at deploy time instead.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from django.core.checks import CheckMessage, Error, Warning, run_checks
from django.test import override_settings

from core.pdf import native_toolchain_error
from reservations.checks import TAG


def _ours() -> list[CheckMessage]:
    return run_checks(tags=[TAG])


def _block_weasyprint(monkeypatch: pytest.MonkeyPatch) -> None:
    # The real import path: `from weasyprint import HTML` in `core.pdf` is
    # where a missing package (ImportError) or missing native library
    # (cffi's OSError) surfaces. Blocking the module makes it fail for real.
    monkeypatch.setitem(sys.modules, "weasyprint", None)


def test_check_is_clean_on_the_real_environment() -> None:
    # WeasyPrint's native libraries are a hard dependency of the suite.
    assert _ours() == []


@override_settings(DEBUG=False)
def test_missing_native_toolchain_is_an_error_outside_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_weasyprint(monkeypatch)

    messages = _ours()

    assert [m.id for m in messages] == ["reservations.E001"]
    assert isinstance(messages[0], Error)
    assert messages[0].hint is not None
    assert "brew install pango harfbuzz libffi" in messages[0].hint


@override_settings(DEBUG=True)
def test_missing_native_toolchain_is_only_a_warning_under_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pango-less dev must still be able to `runserver`."""
    _block_weasyprint(monkeypatch)

    messages = _ours()

    assert [m.id for m in messages] == ["reservations.W001"]
    assert isinstance(messages[0], Warning)
    assert not isinstance(messages[0], Error)


def _install_fake_weasyprint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str) -> None:
    """Swap the real package for a throwaway one so the *import itself* is
    what misbehaves — the probe is exercised end to end, not mocked."""
    pkg = tmp_path / "weasyprint"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(body)
    for name in [m for m in sys.modules if m == "weasyprint" or m.startswith("weasyprint.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()


def test_probe_reports_a_host_with_libraries_but_no_fonts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """WeasyPrint only *warns* when FontConfig has no fonts, then renders
    glyph-less output (or crashes) — the silent failure the check exists
    for, so the probe must treat that warning as a failure."""
    _install_fake_weasyprint(
        monkeypatch,
        tmp_path,
        "import warnings\n"
        "warnings.warn('No fonts configured in FontConfig. Expect ugly output.')\n"
        "HTML = object\n",
    )

    assert native_toolchain_error() == "No fonts configured in FontConfig. Expect ugly output."


def test_probe_captures_the_stdout_banner_weasyprint_prints_before_raising(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """On a missing native library WeasyPrint print()s an explanatory banner
    to stdout and then raises. A `manage.py dumpdata > file` under DEBUG
    (Warning only, the command proceeds) must not get that banner spliced
    into its output — it rides in the check message instead."""
    _install_fake_weasyprint(
        monkeypatch,
        tmp_path,
        "print('WeasyPrint could not import some external libraries.')\n"
        "raise OSError('cannot load library libgobject-2.0-0')\n",
    )

    failure = native_toolchain_error()

    assert failure is not None
    assert failure.startswith("OSError: cannot load library libgobject-2.0-0")
    assert "could not import some external libraries" in failure
    assert capsys.readouterr().out == ""
