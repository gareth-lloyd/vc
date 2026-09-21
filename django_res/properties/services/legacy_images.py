"""Shared helpers for the legacy property-image migration (GAP-012).

The data-migration loader created `PropertyImage` rows with flat keys
(`properties/legacy/<filename>`) and no backing files; the binaries live on the
legacy host nested as `PropertyImages/<VillaId>/<filename>`. Two management
commands work that seam — `fetch_legacy_images` downloads the tree and
`import_legacy_images` uploads it — and both need the same row query and the
same pre-flight assertions about the data.

Those assertions all guard *silent* corruption, which is why they run before
either command does any work rather than being discovered halfway through:

- `duplicate_keys` — two rows flattened onto one key would overwrite each other
  in storage.
- `case_collisions` — two keys differing only in case are distinct rows in
  Postgres and distinct objects in S3, but become ONE file on a
  case-insensitive filesystem (APFS). The second download clobbers the first,
  then the upload sends the same bytes to two different keys with no error
  anywhere. `os.replace()` does not help: it clobbers a differently-cased
  sibling just as happily.
- `unsafe_rows` — both path segments are DB-sourced free text (`legacy_id` is an
  unconstrained `CharField`; the filename is a slice of an `ImageField` name)
  and the legacy app did no sanitisation at all, so `<dest>/../..` is reachable
  in principle. Verified clean on the current load; checked, not assumed.

Framework-free by contract (`pyproject.toml` "services are framework-free"):
these are pure functions that return data. Each *command* formats the operator
message and raises its own `CommandError` — that is a CLI-delivery concern.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import NamedTuple

from properties.models import PropertyImage

LEGACY_PREFIX = "properties/legacy/"

# One safe path segment: no separators, no traversal, no whitespace. Both
# patterns are deliberately stricter than "doesn't contain a slash" — the
# resolved path is also re-checked at write time, but a pre-flight abort that
# names the offending rows beats a per-file failure bucket.
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
_SAFE_LEGACY_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# `.` and `..` match the patterns above but are not filenames.
_RESERVED_SEGMENTS = frozenset({".", ".."})


class LegacyRow(NamedTuple):
    """One `PropertyImage` row under the legacy prefix, as both commands read it."""

    pk: int
    key: str
    property_pk: int
    legacy_id: str | None


def legacy_image_rows() -> list[LegacyRow]:
    """Every image row under the legacy prefix, read in one query."""
    return [
        LegacyRow(*row)
        for row in PropertyImage.objects.filter(image__startswith=LEGACY_PREFIX).values_list(
            "pk", "image", "property_id", "property__legacy_id"
        )
    ]


def filename_for(key: str) -> str:
    """The on-disk filename for a storage key (the key minus the legacy prefix)."""
    return key.removeprefix(LEGACY_PREFIX)


def duplicate_keys(rows: list[LegacyRow]) -> set[str]:
    """Keys held by more than one row — flattening them is unsafe.

    Re-verifies the global-uniqueness property of the legacy GUID filenames on
    every run. It is a property of the data, not a guarantee.
    """
    counts = Counter(row.key for row in rows)
    return {key for key, count in counts.items() if count > 1}


def case_collisions(rows: list[LegacyRow]) -> list[tuple[tuple[str, str], list[LegacyRow]]]:
    """Groups of rows that differ only by case in their `<legacy_id>/<filename>` path.

    Returns `[((folder, filename) casefolded, rows), ...]`, empty when safe.
    Rows with no `legacy_id` are skipped (they have their own reported bucket),
    and a group whose rows all share one exact path is an exact-duplicate key —
    `duplicate_keys`' finding, not re-reported here.
    """
    grouped: dict[tuple[str, str], list[LegacyRow]] = defaultdict(list)
    for row in rows:
        if not row.legacy_id:
            continue
        filename = filename_for(row.key)
        grouped[(row.legacy_id.casefold(), filename.casefold())].append(row)
    return [
        (segments, group)
        for segments, group in grouped.items()
        if len({(row.legacy_id, filename_for(row.key)) for row in group}) > 1
    ]


def unsafe_rows(rows: list[LegacyRow]) -> list[LegacyRow]:
    """Rows whose path segments are not safe to join onto a destination directory.

    A blank `legacy_id` is not a safety failure — it is its own reported bucket.
    """
    return [row for row in rows if not _is_safe(row)]


def _is_safe(row: LegacyRow) -> bool:
    filename = filename_for(row.key)
    if filename in _RESERVED_SEGMENTS or not _SAFE_FILENAME.fullmatch(filename):
        return False
    if not row.legacy_id:
        return True
    return (
        row.legacy_id not in _RESERVED_SEGMENTS
        and _SAFE_LEGACY_ID.fullmatch(row.legacy_id) is not None
    )
