"""Tests for the `import_legacy_images` management command.

The legacy loader stored flat keys (`properties/legacy/<filename>`) with no
backing binaries; the command uploads each row's source file
(`<source>/<property.legacy_id>/<filename>`) to its existing key via the
default storage. Fully offline: test settings use `FileSystemStorage` on a
tmpdir `MEDIA_ROOT` shared across tests, so every test uses unique GUID-ish
filenames and never asserts the prefix is globally empty.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import Any, cast

import pytest
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError

from properties.enums import ImageKind
from properties.models import (
    Property,
    PropertyCategory,
    PropertyGroup,
    PropertyImage,
    Region,
)

LEGACY_PREFIX = "properties/legacy/"

MakeProperty = Callable[[str | None], Property]

pytestmark = pytest.mark.django_db


def _filename() -> str:
    return f"{uuid.uuid4()}.jpg"


@pytest.fixture
def make_property(category: PropertyCategory, group: PropertyGroup, region: Region) -> MakeProperty:
    def make(legacy_id: str | None) -> Property:
        token = uuid.uuid4().hex[:8]
        return Property.objects.create(
            name=f"Villa {token}",
            display_name=f"Villa {token}",
            slug=f"villa-{token}",
            category=category,
            group=group,
            region=region,
            legacy_id=legacy_id,
        )

    return make


def _legacy_row(property_: Property, filename: str) -> PropertyImage:
    return PropertyImage.objects.create(
        property=property_,
        image=f"{LEGACY_PREFIX}{filename}",
        kind=ImageKind.GALLERY,
    )


def _write_source(source: Path, legacy_id: str, filename: str, data: bytes) -> None:
    subdir = source / legacy_id
    subdir.mkdir(parents=True, exist_ok=True)
    (subdir / filename).write_bytes(data)


def _run(source: Path, *args: str) -> str:
    out = StringIO()
    call_command("import_legacy_images", "--source", str(source), *args, stdout=out)
    return out.getvalue()


def _assert_count(out: str, bucket: str, count: int) -> None:
    assert re.search(rf"{re.escape(bucket)}\s+{count}\b", out), (
        f"expected {bucket!r} = {count} in output:\n{out}"
    )


def test_uploads_legacy_rows_and_ignores_non_legacy(
    make_property: MakeProperty, tmp_path: Path
) -> None:
    f1, f2 = _filename(), _filename()
    key_1, key_2 = f"{LEGACY_PREFIX}{f1}", f"{LEGACY_PREFIX}{f2}"
    row_1 = _legacy_row(make_property("101"), f1)
    _legacy_row(make_property("102"), f2)
    _write_source(tmp_path, "101", f1, b"bytes-one")
    _write_source(tmp_path, "102", f2, b"bytes-two")
    non_legacy_key = f"properties/2026/06/{_filename()}"
    PropertyImage.objects.create(
        property=row_1.property,
        image=non_legacy_key,
        kind=ImageKind.GALLERY,
    )

    out = _run(tmp_path)

    assert default_storage.exists(key_1)
    assert default_storage.exists(key_2)
    with default_storage.open(key_1) as fh:
        assert fh.read() == b"bytes-one"
    with default_storage.open(key_2) as fh:
        assert fh.read() == b"bytes-two"
    # No row edits: key unchanged, URL resolves through the storage.
    row_1.refresh_from_db()
    assert row_1.image.name == key_1
    assert row_1.image.url.endswith(f1)
    assert not default_storage.exists(non_legacy_key)
    _assert_count(out, "uploaded", 2)
    _assert_count(out, "skipped (already present)", 0)


def test_rerun_skips_existing_without_suffixing(
    make_property: MakeProperty, tmp_path: Path
) -> None:
    f1, f2 = _filename(), _filename()
    _legacy_row(make_property("201"), f1)
    _legacy_row(make_property("202"), f2)
    _write_source(tmp_path, "201", f1, b"x")
    _write_source(tmp_path, "202", f2, b"y")

    _run(tmp_path)
    out = _run(tmp_path)

    _assert_count(out, "uploaded", 0)
    _assert_count(out, "skipped (already present)", 2)
    # The file_overwrite=False regression guard: no `<stem>_<suffix>.jpg`
    # duplicates appeared alongside the originals.
    _dirs, files = default_storage.listdir(LEGACY_PREFIX)
    for filename in (f1, f2):
        stem = filename.removesuffix(".jpg")
        assert [f for f in files if f.startswith(stem)] == [filename]


def test_dry_run_uploads_nothing(make_property: MakeProperty, tmp_path: Path) -> None:
    f1 = _filename()
    _legacy_row(make_property("301"), f1)
    _write_source(tmp_path, "301", f1, b"x")

    out = _run(tmp_path, "--dry-run")

    assert "DRY RUN" in out
    _assert_count(out, "uploaded", 1)
    assert not default_storage.exists(f"{LEGACY_PREFIX}{f1}")


def test_missing_at_source_reported_not_raised(make_property: MakeProperty, tmp_path: Path) -> None:
    present, absent = _filename(), _filename()
    _legacy_row(make_property("401"), present)
    _legacy_row(make_property("402"), absent)
    _write_source(tmp_path, "401", present, b"x")

    out = _run(tmp_path)

    _assert_count(out, "uploaded", 1)
    _assert_count(out, "missing at source", 1)
    assert absent in out


@pytest.mark.parametrize("legacy_id", [None, ""])
def test_row_without_property_legacy_id_skipped(
    make_property: MakeProperty, tmp_path: Path, legacy_id: str | None
) -> None:
    filename = _filename()
    row = _legacy_row(make_property(legacy_id), filename)

    out = _run(tmp_path)

    _assert_count(out, "uploaded", 0)
    _assert_count(out, "no property legacy_id", 1)
    assert str(row.pk) in out
    assert not default_storage.exists(f"{LEGACY_PREFIX}{filename}")


def test_colliding_keys_abort_before_any_upload(
    make_property: MakeProperty, tmp_path: Path
) -> None:
    shared, importable = _filename(), _filename()
    row_a = _legacy_row(make_property("501"), shared)
    row_b = _legacy_row(make_property("502"), shared)
    _legacy_row(make_property("503"), importable)
    _write_source(tmp_path, "501", shared, b"x")
    _write_source(tmp_path, "502", shared, b"y")
    _write_source(tmp_path, "503", importable, b"z")

    with pytest.raises(CommandError, match="colliding"):
        _run(tmp_path)

    assert not default_storage.exists(f"{LEGACY_PREFIX}{shared}")
    assert not default_storage.exists(f"{LEGACY_PREFIX}{importable}")
    # The error names the rows so the operator can pick the right one.
    with pytest.raises(CommandError) as excinfo:
        _run(tmp_path)
    assert str(row_a.pk) in str(excinfo.value)
    assert str(row_b.pk) in str(excinfo.value)


def test_saved_name_mismatch_aborts(
    make_property: MakeProperty, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f1 = _filename()
    _legacy_row(make_property("601"), f1)
    _write_source(tmp_path, "601", f1, b"x")

    # Force `save` to return a suffixed name the way file_overwrite=False
    # would on a key that appeared after enumeration. `default_storage` is a
    # lazy proxy, so resolve it and patch the wrapped instance.
    default_storage.exists("probe")
    wrapped = cast(Any, default_storage)._wrapped
    suffixed = f"{LEGACY_PREFIX}{f1.removesuffix('.jpg')}_clash.jpg"
    monkeypatch.setattr(wrapped, "save", lambda name, content: suffixed)

    with pytest.raises(CommandError) as excinfo:
        _run(tmp_path)

    message = str(excinfo.value)
    assert f"{LEGACY_PREFIX}{f1}" in message
    assert suffixed in message


def test_nonexistent_source_dir_rejected(tmp_path: Path) -> None:
    with pytest.raises(CommandError, match="not a directory"):
        _run(tmp_path / "nope")
