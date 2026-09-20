"""Tests for the `fetch_legacy_images` management command (GAP-012).

The command downloads the legacy image tree from the legacy host into
`<dest>/<legacy_id>/<filename>` — the exact layout `import_legacy_images
--source` consumes. Fully offline: every HTTP call goes through respx, and the
one test that matters most hands the fetched tree to the sibling command.

Two structural notes:

- The house convention prints the summary *then* raises, so a `_run()` that
  returns `out.getvalue()` loses the output when `CommandError` propagates.
  `_run_expecting_error` builds the buffer itself and hands back both.
- Every test runs at `--concurrency 1` except `test_concurrency_*`. respx's
  router records call history without a lock, so per-route `call_count`
  assertions across threads can flake; the one threaded test asserts files on
  disk, which is an idempotent assertion. Do not "fix" this by parallelising
  the rest.
"""

from __future__ import annotations

import re
import shutil
import time
import uuid
from collections.abc import Callable
from io import StringIO
from pathlib import Path

import httpx
import pytest
import respx
from django.core.management import call_command
from django.core.management.base import CommandError

from properties.enums import ImageKind
from properties.management.commands import fetch_legacy_images as cmd
from properties.models import Property, PropertyImage, Region
from properties.services.legacy_images import LEGACY_PREFIX

BASE_URL = "https://legacy.test/PropertyImages"

JPEG = b"\xff\xd8\xff" + b"\x00" * 2048
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048
BLAZOR_HTML = b"<!DOCTYPE html><html><head><base href='/'/></head><body>app</body></html>" * 40

MakeProperty = Callable[[str | None], Property]

pytestmark = pytest.mark.django_db


def _filename() -> str:
    return f"{uuid.uuid4()}.jpg"


@pytest.fixture
def make_property(region: Region) -> MakeProperty:
    def make(legacy_id: str | None) -> Property:
        token = uuid.uuid4().hex[:8]
        return Property.objects.create(
            name=f"Villa {token}",
            display_name=f"Villa {token}",
            slug=f"villa-{token}",
            region=region,
            legacy_id=legacy_id,
        )

    return make


@pytest.fixture
def dest(tmp_path: Path) -> Path:
    return tmp_path / "archive"


def _legacy_row(property_: Property, filename: str) -> PropertyImage:
    return PropertyImage.objects.create(
        property=property_,
        image=f"{LEGACY_PREFIX}{filename}",
        kind=ImageKind.GALLERY,
    )


def _url(legacy_id: str, filename: str) -> str:
    return f"{BASE_URL}/{legacy_id}/{filename}"


def _image_route(legacy_id: str, filename: str, body: bytes = JPEG) -> respx.Route:
    return respx.get(_url(legacy_id, filename)).respond(
        200, content=body, headers={"Content-Type": "image/jpeg"}
    )


def _run(dest: Path, *args: str) -> str:
    out = StringIO()
    call_command(
        "fetch_legacy_images",
        "--dest",
        str(dest),
        "--base-url",
        BASE_URL,
        "--concurrency",
        "1",
        *args,
        stdout=out,
        stderr=out,
    )
    return out.getvalue()


def _run_expecting_error(dest: Path, *args: str) -> tuple[str, CommandError]:
    out = StringIO()
    with pytest.raises(CommandError) as excinfo:
        call_command(
            "fetch_legacy_images",
            "--dest",
            str(dest),
            "--base-url",
            BASE_URL,
            "--concurrency",
            "1",
            *args,
            stdout=out,
            stderr=out,
        )
    return out.getvalue(), excinfo.value


def _assert_count(out: str, bucket: str, count: int) -> None:
    assert re.search(rf"{re.escape(bucket)}\s+{count}\b", out), (
        f"expected {bucket!r} = {count} in output:\n{out}"
    )


# --------------------------------------------------------------------------
# Pre-flight — no respx routes are registered, so any request would raise.
# --------------------------------------------------------------------------


@respx.mock
def test_dry_run_makes_no_requests_and_reports_planned_count(
    make_property: MakeProperty, dest: Path
) -> None:
    filename = _filename()
    _legacy_row(make_property("101"), filename)

    out = _run(dest, "--dry-run")

    assert "DRY RUN" in out
    _assert_count(out, "downloaded", 1)
    _assert_count(out, "total", 1)
    assert respx.calls.call_count == 0
    assert not (dest / "101").exists()


@respx.mock
def test_dest_inside_the_git_work_tree_is_rejected(
    make_property: MakeProperty, tmp_path: Path
) -> None:
    (tmp_path / ".git").mkdir()
    _legacy_row(make_property("101"), _filename())

    _out, error = _run_expecting_error(tmp_path / "images" / "PropertyImages")

    assert "git work tree" in str(error)
    assert not (tmp_path / "images").exists()


@respx.mock
def test_dest_is_created_and_its_resolved_path_is_printed_first(
    make_property: MakeProperty, dest: Path
) -> None:
    _legacy_row(make_property("101"), _filename())

    out = _run(dest, "--dry-run")

    assert dest.is_dir()
    assert str(dest.resolve()) in out.splitlines()[0]


@respx.mock
def test_colliding_keys_abort_before_any_request(make_property: MakeProperty, dest: Path) -> None:
    shared = _filename()
    row_a = _legacy_row(make_property("101"), shared)
    row_b = _legacy_row(make_property("102"), shared)

    _out, error = _run_expecting_error(dest)

    assert "colliding" in str(error)
    assert str(row_a.pk) in str(error)
    assert str(row_b.pk) in str(error)
    assert respx.calls.call_count == 0


@respx.mock
def test_case_only_colliding_keys_abort_before_any_request(
    make_property: MakeProperty, dest: Path
) -> None:
    """Distinct keys in Postgres and S3; one file on a case-insensitive disk."""
    stem = uuid.uuid4().hex
    property_ = make_property("101")
    _legacy_row(property_, f"{stem}.jpg")
    _legacy_row(property_, f"{stem.upper()}.jpg")

    _out, error = _run_expecting_error(dest)

    assert "case" in str(error).lower()
    assert respx.calls.call_count == 0


@respx.mock
@pytest.mark.parametrize("filename", ["../escape.jpg", "sub/dir.jpg", "..", "with space.jpg"])
def test_filename_escaping_dest_aborts_before_any_request(
    make_property: MakeProperty, dest: Path, filename: str
) -> None:
    _legacy_row(make_property("101"), filename)

    _out, error = _run_expecting_error(dest)

    assert "unsafe" in str(error).lower()
    assert respx.calls.call_count == 0


@respx.mock
def test_legacy_id_escaping_dest_aborts_before_any_request(
    make_property: MakeProperty, dest: Path
) -> None:
    _legacy_row(make_property("../.."), _filename())

    _out, error = _run_expecting_error(dest)

    assert "unsafe" in str(error).lower()
    assert respx.calls.call_count == 0


@respx.mock
@pytest.mark.parametrize("legacy_id", [None, ""])
def test_row_without_property_legacy_id_is_reported_not_fetched(
    make_property: MakeProperty, dest: Path, legacy_id: str | None
) -> None:
    row = _legacy_row(make_property(legacy_id), _filename())

    out = _run(dest)

    _assert_count(out, "no property legacy_id", 1)
    _assert_count(out, "downloaded", 0)
    assert str(row.pk) in out
    assert respx.calls.call_count == 0


@respx.mock
def test_second_run_refused_while_lock_file_present(
    make_property: MakeProperty, dest: Path
) -> None:
    _legacy_row(make_property("101"), _filename())
    dest.mkdir(parents=True)
    (dest / cmd.LOCK_NAME).touch()

    _out, error = _run_expecting_error(dest, "--dry-run")

    assert "in progress" in str(error)
    assert cmd.LOCK_NAME in str(error)
    assert respx.calls.call_count == 0


@respx.mock
def test_lock_released_after_successful_run(make_property: MakeProperty, dest: Path) -> None:
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    _image_route("101", filename)

    _run(dest)

    assert not (dest / cmd.LOCK_NAME).exists()


@respx.mock
def test_lock_released_after_an_aborting_run(make_property: MakeProperty, dest: Path) -> None:
    shared = _filename()
    _legacy_row(make_property("101"), shared)
    _legacy_row(make_property("102"), shared)

    _run_expecting_error(dest)

    assert not (dest / cmd.LOCK_NAME).exists()


@respx.mock
def test_insufficient_free_disk_aborts_before_any_request(
    make_property: MakeProperty, dest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _legacy_row(make_property("101"), _filename())
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: shutil._ntuple_diskusage(1, 1, 0))

    _out, error = _run_expecting_error(dest)

    assert "free space" in str(error)
    assert respx.calls.call_count == 0


@respx.mock
def test_limit_fetches_only_the_first_n_rows(make_property: MakeProperty, dest: Path) -> None:
    property_ = make_property("101")
    for _ in range(3):
        filename = _filename()
        _legacy_row(property_, filename)
        _image_route("101", filename)

    out = _run(dest, "--limit", "2")

    _assert_count(out, "downloaded", 2)
    assert len(list((dest / "101").glob("*.jpg"))) == 2
    assert respx.calls.call_count == 2


@respx.mock
def test_concurrency_above_max_is_rejected(make_property: MakeProperty, dest: Path) -> None:
    _legacy_row(make_property("101"), _filename())

    out = StringIO()
    with pytest.raises(CommandError) as excinfo:
        call_command(
            "fetch_legacy_images",
            "--dest",
            str(dest),
            "--base-url",
            BASE_URL,
            "--concurrency",
            str(cmd.MAX_CONCURRENCY + 1),
            stdout=out,
        )

    assert str(cmd.MAX_CONCURRENCY) in str(excinfo.value)


@respx.mock
def test_non_https_base_url_is_rejected(make_property: MakeProperty, dest: Path) -> None:
    _legacy_row(make_property("101"), _filename())

    out = StringIO()
    with pytest.raises(CommandError, match="https"):
        call_command(
            "fetch_legacy_images",
            "--dest",
            str(dest),
            "--base-url",
            "http://legacy.test/PropertyImages",
            stdout=out,
        )


@respx.mock
def test_base_url_trailing_slash_is_stripped(make_property: MakeProperty, dest: Path) -> None:
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    route = _image_route("101", filename)

    out = StringIO()
    call_command(
        "fetch_legacy_images",
        "--dest",
        str(dest),
        "--base-url",
        f"{BASE_URL}/",
        "--concurrency",
        "1",
        stdout=out,
    )

    assert route.call_count == 1


# --------------------------------------------------------------------------
# Download path
# --------------------------------------------------------------------------


@respx.mock
def test_downloads_to_the_nested_villa_id_layout(make_property: MakeProperty, dest: Path) -> None:
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    _image_route("101", filename)

    out = _run(dest)

    assert (dest / "101" / filename).read_bytes() == JPEG
    _assert_count(out, "downloaded", 1)


@respx.mock
def test_downloaded_tree_is_consumable_by_import_legacy_images(
    make_property: MakeProperty, dest: Path
) -> None:
    """The load-bearing test: it pins the contract between the two commands."""
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    _image_route("101", filename)

    _run(dest)

    out = StringIO()
    call_command("import_legacy_images", "--source", str(dest), "--dry-run", stdout=out)

    _assert_count(out.getvalue(), "uploaded", 1)
    _assert_count(out.getvalue(), "missing at source", 0)


@respx.mock
def test_png_body_is_accepted(make_property: MakeProperty, dest: Path) -> None:
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    respx.get(_url("101", filename)).respond(
        200, content=PNG, headers={"Content-Type": "image/png"}
    )

    out = _run(dest)

    assert (dest / "101" / filename).read_bytes() == PNG
    _assert_count(out, "downloaded", 1)


@respx.mock
def test_blazor_html_page_with_status_200_is_rejected_and_not_saved(
    make_property: MakeProperty, dest: Path
) -> None:
    """The measured trap: a directory URL answers 200 with the SPA fallback."""
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    respx.get(_url("101", filename)).respond(
        200, content=BLAZOR_HTML, headers={"Content-Type": "text/html; charset=utf-8"}
    )

    out, error = _run_expecting_error(dest)

    _assert_count(out, "rejected (not an image)", 1)
    _assert_count(out, "downloaded", 0)
    assert not (dest / "101" / filename).exists()
    assert "failed" in str(error) or "rejected" in str(error)


@respx.mock
def test_non_image_body_with_image_content_type_is_rejected(
    make_property: MakeProperty, dest: Path
) -> None:
    """The magic-byte guard is independent of the header."""
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    respx.get(_url("101", filename)).respond(
        200, content=BLAZOR_HTML, headers={"Content-Type": "image/jpeg"}
    )

    out, _error = _run_expecting_error(dest)

    _assert_count(out, "rejected (not an image)", 1)
    assert not (dest / "101" / filename).exists()
    assert not list((dest / "101").glob("*.part"))


@respx.mock
def test_body_below_minimum_size_is_rejected(make_property: MakeProperty, dest: Path) -> None:
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    respx.get(_url("101", filename)).respond(
        200, content=b"\xff\xd8\xff\x00", headers={"Content-Type": "image/jpeg"}
    )

    out, _error = _run_expecting_error(dest)

    _assert_count(out, "rejected (not an image)", 1)
    assert not (dest / "101" / filename).exists()


@respx.mock
def test_404_is_counted_missing_at_source_and_not_retried(
    make_property: MakeProperty, dest: Path
) -> None:
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    route = respx.get(_url("101", filename)).respond(404)

    out = _run(dest)

    _assert_count(out, "missing at source (404)", 1)
    assert route.call_count == 1
    assert filename in out


@respx.mock
def test_redirect_is_not_followed_and_counted_unexpected(
    make_property: MakeProperty, dest: Path
) -> None:
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    respx.get(_url("101", filename)).respond(302, headers={"Location": "/maintenance"})

    out, _error = _run_expecting_error(dest)

    _assert_count(out, "unexpected redirect", 1)
    assert "/maintenance" in out


@respx.mock
def test_retryable_status_is_retried_then_succeeds(
    make_property: MakeProperty, dest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    route = respx.get(_url("101", filename))
    route.side_effect = [
        httpx.Response(500),
        httpx.Response(503),
        httpx.Response(200, content=JPEG, headers={"Content-Type": "image/jpeg"}),
    ]

    out = _run(dest)

    _assert_count(out, "downloaded", 1)
    assert route.call_count == 3
    assert (dest / "101" / filename).read_bytes() == JPEG


@respx.mock
def test_timeout_exhausts_retries_and_counts_as_failed(
    make_property: MakeProperty, dest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    route = respx.get(_url("101", filename))
    route.side_effect = httpx.ConnectTimeout("too slow")

    out, error = _run_expecting_error(dest, "--retries", "2")

    _assert_count(out, "failed", 1)
    assert route.call_count == 3
    assert "failed" in str(error)


@respx.mock
def test_no_part_file_or_final_file_remains_after_a_failure(
    make_property: MakeProperty, dest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    respx.get(_url("101", filename)).mock(side_effect=httpx.ConnectError("refused"))

    _run_expecting_error(dest, "--retries", "0")

    assert not (dest / "101" / filename).exists()
    assert list((dest / "101").glob("*.part")) == []


@respx.mock
def test_stale_part_file_is_swept_at_startup_and_counted(
    make_property: MakeProperty, dest: Path
) -> None:
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    _image_route("101", filename)
    stale = dest / "101" / f"{filename}{cmd.PART_SUFFIX}"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"half a file")

    out = _run(dest)

    _assert_count(out, "stale .part swept", 1)
    assert not stale.exists()
    assert (dest / "101" / filename).read_bytes() == JPEG


@respx.mock
def test_rerun_skips_existing_files_and_makes_no_requests(
    make_property: MakeProperty, dest: Path
) -> None:
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    (dest / "101").mkdir(parents=True)
    (dest / "101" / filename).write_bytes(JPEG)

    out = _run(dest)

    _assert_count(out, "skipped (already present)", 1)
    _assert_count(out, "downloaded", 0)
    assert respx.calls.call_count == 0


@respx.mock
def test_zero_byte_existing_file_is_redownloaded(make_property: MakeProperty, dest: Path) -> None:
    """A truncated artefact from an earlier era must not be trusted as complete."""
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    _image_route("101", filename)
    (dest / "101").mkdir(parents=True)
    (dest / "101" / filename).write_bytes(b"")

    out = _run(dest)

    _assert_count(out, "downloaded", 1)
    assert (dest / "101" / filename).read_bytes() == JPEG


@respx.mock
def test_dotfiles_are_not_mistaken_for_images(make_property: MakeProperty, dest: Path) -> None:
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    _image_route("101", filename)
    (dest / "101").mkdir(parents=True)
    (dest / "101" / ".DS_Store").write_bytes(b"x" * 4096)

    out = _run(dest)

    _assert_count(out, "downloaded", 1)


# --------------------------------------------------------------------------
# Run level
# --------------------------------------------------------------------------


@respx.mock
def test_consecutive_failures_trip_the_breaker_and_stop_early(
    make_property: MakeProperty, dest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves we stop hammering a box that has started refusing us."""
    monkeypatch.setattr(cmd, "CONSECUTIVE_FAILURE_ABORT", 2)
    property_ = make_property("101")
    for _ in range(20):
        filename = _filename()
        _legacy_row(property_, filename)
        respx.get(_url("101", filename)).respond(403)

    out, error = _run_expecting_error(dest, "--retries", "0")

    assert "consecutive failures" in str(error)
    # Bounded by the in-flight window, NOT by the row count: submitting all 20
    # up front would let the pool drain the queue before the breaker could bite.
    assert respx.calls.call_count <= 2 * cmd.IN_FLIGHT_PER_WORKER, (
        f"the breaker should stop the run, not drain the queue ({respx.calls.call_count} calls)"
    )
    assert "failed" in out


@respx.mock
def test_high_missing_rate_aborts_with_a_remedy_sentence(
    make_property: MakeProperty, dest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """18k 404s must not be reported as the never-fatal expected-loss bucket."""
    monkeypatch.setattr(cmd, "MISSING_ABORT_FLOOR", 3)
    property_ = make_property("101")
    for _ in range(6):
        filename = _filename()
        _legacy_row(property_, filename)
        respx.get(_url("101", filename)).respond(404)

    out, error = _run_expecting_error(dest)

    assert "missing at source" in str(error)
    assert "re-run" in str(error)
    assert "missing at source (404)" in out


@respx.mock
def test_summary_is_printed_before_the_non_zero_exit(
    make_property: MakeProperty, dest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    good, bad = _filename(), _filename()
    property_ = make_property("101")
    _legacy_row(property_, good)
    _legacy_row(property_, bad)
    _image_route("101", good)
    respx.get(_url("101", bad)).respond(418)

    out, _error = _run_expecting_error(dest, "--retries", "0")

    assert "bucket" in out and "count" in out
    _assert_count(out, "downloaded", 1)
    _assert_count(out, "failed", 1)


@respx.mock
def test_report_file_lists_failures_and_is_overwritten_on_rerun(
    make_property: MakeProperty, dest: Path
) -> None:
    missing_a, missing_b = _filename(), _filename()
    property_ = make_property("101")
    _legacy_row(property_, missing_a)
    row_b = _legacy_row(property_, missing_b)
    respx.get(_url("101", missing_a)).respond(404)
    respx.get(_url("101", missing_b)).respond(404)

    _run(dest)
    report = (dest / cmd.REPORT_NAME).read_text()
    assert missing_a in report
    assert missing_b in report

    row_b.delete()
    _run(dest)
    report = (dest / cmd.REPORT_NAME).read_text()
    assert missing_a in report
    assert missing_b not in report, "the report is overwritten, never appended"


@respx.mock
def test_report_file_is_not_mistaken_for_an_image(make_property: MakeProperty, dest: Path) -> None:
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    respx.get(_url("101", filename)).respond(404)

    _run(dest)
    out = _run(dest)

    _assert_count(out, "missing at source (404)", 1)
    _assert_count(out, "skipped (already present)", 0)


@respx.mock
def test_disk_full_mid_run_stops_the_run_with_its_own_message(
    make_property: MakeProperty, dest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import errno

    property_ = make_property("101")
    for _ in range(4):
        filename = _filename()
        _legacy_row(property_, filename)
        _image_route("101", filename)

    def full(_response: object, _part: Path) -> int:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(cmd, "_stream_to_part", full)

    _out, error = _run_expecting_error(dest, "--retries", "0")

    assert "no space left" in str(error).lower()
    assert respx.calls.call_count <= cmd.IN_FLIGHT_PER_WORKER, (
        "ENOSPC must stop the run, not fail every remaining file"
    )


@respx.mock
def test_concurrency_two_downloads_every_file_exactly_once(
    make_property: MakeProperty, dest: Path
) -> None:
    property_ = make_property("101")
    filenames = [_filename() for _ in range(4)]
    for filename in filenames:
        _legacy_row(property_, filename)
        _image_route("101", filename)

    out = StringIO()
    call_command(
        "fetch_legacy_images",
        "--dest",
        str(dest),
        "--base-url",
        BASE_URL,
        "--concurrency",
        "2",
        stdout=out,
    )

    for filename in filenames:
        assert (dest / "101" / filename).read_bytes() == JPEG
    _assert_count(out.getvalue(), "downloaded", 4)


@respx.mock
def test_delay_sleeps_before_each_request(
    make_property: MakeProperty, dest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", slept.append)
    filename = _filename()
    _legacy_row(make_property("101"), filename)
    _image_route("101", filename)

    _run(dest, "--delay", "0.25")

    assert 0.25 in slept


@respx.mock
def test_interrupt_prints_the_summary_and_exits_non_zero(
    make_property: MakeProperty, dest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ctrl-C must report and stop, not dump a traceback or drain the queue."""
    property_ = make_property("101")
    for _ in range(4):
        filename = _filename()
        _legacy_row(property_, filename)
        _image_route("101", filename)

    def interrupt(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cmd, "wait", interrupt)

    out, error = _run_expecting_error(dest)

    assert "interrupted" in str(error)
    assert "re-run to resume" in str(error)
    assert "bucket" in out, "the summary must print before the non-zero exit"
    assert (dest / cmd.REPORT_NAME).exists()
