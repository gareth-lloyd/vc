"""Tests for the shared legacy-image helpers (GAP-012).

The predicates are the pre-flight assertions both migration commands run
before touching the network or S3. They are pure — they take a row list and
return data — so most of these tests build `LegacyRow`s directly and need no
database; only `legacy_image_rows` does.
"""

from __future__ import annotations

import uuid

import pytest

from properties.enums import ImageKind
from properties.models import Property, PropertyImage, Region
from properties.services.legacy_images import (
    LEGACY_PREFIX,
    LegacyRow,
    case_collisions,
    duplicate_keys,
    filename_for,
    legacy_image_rows,
    unsafe_rows,
)


def _row(pk: int, filename: str, legacy_id: str | None = "101") -> LegacyRow:
    return LegacyRow(
        pk=pk, key=f"{LEGACY_PREFIX}{filename}", property_pk=pk * 10, legacy_id=legacy_id
    )


def test_filename_for_strips_the_prefix() -> None:
    assert filename_for(f"{LEGACY_PREFIX}abc.jpg") == "abc.jpg"


def test_filename_for_leaves_a_non_legacy_key_alone() -> None:
    assert filename_for("properties/2026/06/abc.jpg") == "properties/2026/06/abc.jpg"


def test_duplicate_keys_empty_when_all_distinct() -> None:
    rows = [_row(1, "a.jpg"), _row(2, "b.jpg")]

    assert duplicate_keys(rows) == set()


def test_duplicate_keys_names_the_shared_key() -> None:
    rows = [_row(1, "same.jpg"), _row(2, "same.jpg"), _row(3, "other.jpg")]

    assert duplicate_keys(rows) == {f"{LEGACY_PREFIX}same.jpg"}


def test_case_collisions_empty_when_filenames_differ_beyond_case() -> None:
    rows = [_row(1, "abc.jpg"), _row(2, "def.jpg")]

    assert case_collisions(rows) == []


def test_case_collisions_groups_filenames_differing_only_by_case() -> None:
    """Distinct in Postgres and S3, one file on a case-insensitive filesystem."""
    rows = [_row(1, "ABC.jpg"), _row(2, "abc.jpg"), _row(3, "other.jpg")]

    collisions = case_collisions(rows)

    assert len(collisions) == 1
    _segments, group = collisions[0]
    assert {row.pk for row in group} == {1, 2}


def test_case_collisions_ignores_same_filename_in_different_villa_folders() -> None:
    """Different folders are different paths — not a filesystem collision."""
    rows = [_row(1, "abc.jpg", legacy_id="101"), _row(2, "abc.jpg", legacy_id="102")]

    assert case_collisions(rows) == []


def test_case_collisions_catches_villa_folders_differing_only_by_case() -> None:
    rows = [_row(1, "abc.jpg", legacy_id="a1"), _row(2, "abc.jpg", legacy_id="A1")]

    assert len(case_collisions(rows)) == 1


def test_case_collisions_does_not_re_report_an_exact_duplicate_key() -> None:
    """An exact duplicate is `duplicate_keys`'s finding; don't double-count it."""
    rows = [_row(1, "same.jpg"), _row(2, "same.jpg")]

    assert case_collisions(rows) == []


def test_case_collisions_skips_rows_without_a_legacy_id() -> None:
    rows = [_row(1, "abc.jpg", legacy_id=None), _row(2, "abc.jpg", legacy_id=None)]

    assert case_collisions(rows) == []


def test_unsafe_rows_empty_for_guid_filenames() -> None:
    rows = [_row(1, f"{uuid.uuid4()}.jpg"), _row(2, f"{uuid.uuid4()}.JPG")]

    assert unsafe_rows(rows) == []


@pytest.mark.parametrize(
    "filename",
    [
        "../escape.jpg",
        "..",
        ".",
        "sub/dir.jpg",
        "back\\slash.jpg",
        "with space.jpg",
        "",
        "x" * 121,
    ],
)
def test_unsafe_rows_rejects_a_filename_that_is_not_one_safe_segment(filename: str) -> None:
    rows = [_row(1, filename)]

    assert [row.pk for row in unsafe_rows(rows)] == [1]


@pytest.mark.parametrize("legacy_id", ["../101", "..", "a/b", "x" * 65])
def test_unsafe_rows_rejects_an_unsafe_legacy_id(legacy_id: str) -> None:
    rows = [_row(1, "abc.jpg", legacy_id=legacy_id)]

    assert [row.pk for row in unsafe_rows(rows)] == [1]


def test_unsafe_rows_ignores_a_blank_legacy_id() -> None:
    """Blank is its own reported bucket, not a path-safety failure."""
    rows = [_row(1, "abc.jpg", legacy_id=None), _row(2, "abc.jpg", legacy_id="")]

    assert unsafe_rows(rows) == []


@pytest.mark.django_db
def test_legacy_image_rows_returns_only_prefixed_rows(region: Region) -> None:
    token = uuid.uuid4().hex[:8]
    property_ = Property.objects.create(
        name=f"Villa {token}",
        display_name=f"Villa {token}",
        slug=f"villa-{token}",
        region=region,
        legacy_id="901",
    )
    filename = f"{uuid.uuid4()}.jpg"
    legacy = PropertyImage.objects.create(
        property=property_, image=f"{LEGACY_PREFIX}{filename}", kind=ImageKind.GALLERY
    )
    PropertyImage.objects.create(
        property=property_, image=f"properties/2026/06/{filename}", kind=ImageKind.GALLERY
    )

    rows = legacy_image_rows()

    row = next(r for r in rows if r.pk == legacy.pk)
    assert row.key == f"{LEGACY_PREFIX}{filename}"
    assert row.property_pk == property_.pk
    assert row.legacy_id == "901"
    assert not any(r.key.startswith("properties/2026/") for r in rows)
