"""Upload legacy property-image binaries into the default storage.

The data-migration loader created `PropertyImage` rows with flat keys
(`properties/legacy/<filename>`) and no backing files — the legacy .NET app
stores binaries nested as `PropertyImages/<VillaId>/<filename>`, and the
loader dropped the `<VillaId>` subfolder. This command reconstructs each
row's source path from `property.legacy_id` (== the legacy VillaId) and
uploads the binary to the row's *existing* key via the default storage, so
`AWS_LOCATION` prefixing applies automatically and no row is edited.

Idempotent: existing objects under the prefix are enumerated once
(`storage.listdir`, not a per-key `exists()`), and present keys are skipped.
Accepted risk: "skipped" assumes presence ⇒ correctness — an object already
at the key (manual upload, interrupted prior run) is trusted as-is, since
verifying content would cost a per-key round-trip.

Missing-at-source files are the documented expected-loss bucket: reported,
never fatal. Colliding keys (two rows flattened onto one filename) abort
before any upload — they would silently overwrite one another.

Cutover runbook: `django_res_design/todo/gap-012-s3-image-hosting.md`.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from django.core.files import File
from django.core.files.storage import Storage, default_storage
from django.core.management.base import BaseCommand, CommandError

from core.console import render_table
from properties.models import PropertyImage

LEGACY_PREFIX = "properties/legacy/"
PROGRESS_EVERY = 250
DETAIL_CAP = 20

# (image pk, image key, property pk, property legacy_id)
_Row = tuple[int, str, int, str | None]


def _existing_filenames(storage: Storage) -> set[str]:
    try:
        _dirs, files = storage.listdir(LEGACY_PREFIX)
    except FileNotFoundError:  # FileSystemStorage, prefix not created yet
        return set()
    return set(files)


class Command(BaseCommand):
    help = (
        "Upload legacy property-image binaries to their existing "
        f"{LEGACY_PREFIX}<filename> keys via the default storage."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--source",
            required=True,
            help=(
                "Path to the exported legacy PropertyImages/ directory — the one "
                "containing the per-villa-id subfolders (source file for a row is "
                "<source>/<property.legacy_id>/<filename>)."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Classify and report without uploading anything.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        source = Path(options["source"])
        if not source.is_dir():
            raise CommandError(f"--source {source} is not a directory")
        dry_run: bool = options["dry_run"]

        rows: list[_Row] = list(
            PropertyImage.objects.filter(image__startswith=LEGACY_PREFIX).values_list(
                "pk", "image", "property_id", "property__legacy_id"
            )
        )
        self._abort_on_key_collisions(rows)
        existing = _existing_filenames(default_storage)

        skipped = 0
        missing: list[str] = []
        no_legacy_id: list[int] = []
        to_upload: list[tuple[str, Path]] = []  # (key, source path)
        for pk, key, _property_pk, legacy_id in rows:
            filename = key.removeprefix(LEGACY_PREFIX)
            if filename in existing:
                skipped += 1
                continue
            if not legacy_id:
                no_legacy_id.append(pk)
                continue
            src_path = source / legacy_id / filename
            if not src_path.is_file():
                missing.append(str(src_path))
                continue
            to_upload.append((key, src_path))

        if not dry_run:
            total = len(to_upload)
            for index, (key, src_path) in enumerate(to_upload, start=1):
                self._upload(src_path, key)
                if index % PROGRESS_EVERY == 0:
                    self.stdout.write(f"uploaded {index}/{total}")

        self._report(
            dry_run=dry_run,
            uploaded=len(to_upload),
            skipped=skipped,
            missing=missing,
            no_legacy_id=no_legacy_id,
        )

    def _abort_on_key_collisions(self, rows: list[_Row]) -> None:
        """Two rows flattened onto one key would silently overwrite each other.

        Re-verifies the global-uniqueness property of the legacy GUID filenames
        on every run (12,293/12,293 on the 2026-06-09 dump) — it is a property
        of the data, not a guarantee.
        """
        counts = Counter(key for _pk, key, _property_pk, _legacy_id in rows)
        duplicated = {key for key, count in counts.items() if count > 1}
        if not duplicated:
            return
        details = sorted(
            f"{key} (image pk={pk}, property pk={property_pk})"
            for pk, key, property_pk, _legacy_id in rows
            if key in duplicated
        )
        raise CommandError(
            f"{len(duplicated)} colliding image key(s) — flattening is unsafe, "
            "nothing was uploaded:\n  " + "\n  ".join(details)
        )

    def _upload(self, src_path: Path, key: str) -> None:
        with src_path.open("rb") as fh:
            saved = default_storage.save(key, File(fh))
        if saved != key:
            # file_overwrite=False suffixes instead of clobbering: an object
            # appeared at this key after enumeration (race or collision).
            default_storage.delete(saved)
            raise CommandError(f"storage returned {saved!r} for intended key {key!r} — aborting")

    def _report(
        self,
        *,
        dry_run: bool,
        uploaded: int,
        skipped: int,
        missing: list[str],
        no_legacy_id: list[int],
    ) -> None:
        if dry_run:
            self.stdout.write("DRY RUN — no uploads performed\n")
        header = ("bucket", "count")
        table_rows = [
            ("uploaded", uploaded),
            ("skipped (already present)", skipped),
            ("missing at source", len(missing)),
            ("no property legacy_id", len(no_legacy_id)),
        ]
        self.stdout.write(render_table(header, table_rows))
        if missing:
            self.stdout.write(f"\nmissing at source (first {DETAIL_CAP}):")
            for path in missing[:DETAIL_CAP]:
                self.stdout.write(f"  {path}")
        if no_legacy_id:
            self.stdout.write(f"\nno property legacy_id (image pks, first {DETAIL_CAP}):")
            self.stdout.write("  " + ", ".join(str(pk) for pk in no_legacy_id[:DETAIL_CAP]))
