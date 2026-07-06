"""Recompute GAP-067 derived property features across every property.

The room save-path (`RoomSerializer`, `RoomDetailView.perform_destroy`)
recomputes derived features live, but a legacy load followed by
`backfill_room_attrs` writes `RoomAttributeAssignment` rows in bulk without
going through that path — so migrated properties ship with no `is_derived`
links. This command sweeps all properties once at cutover (run it AFTER the
feature loader and the room-attribute backfill; see CUTOVER.md §6c).

Idempotent — the service reconciles to the implied set, so a re-run after a
delta load adds/removes only the difference. `--dry-run` runs the whole sweep
inside a transaction and rolls it back, reporting the counts a real run would
apply (the service always writes, so the rollback is the dry-run mechanism —
not a per-write guard).
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from properties.models import Property
from properties.services.features import recompute_derived_features


class Command(BaseCommand):
    help = (
        "Reconcile is_derived PropertyFeature links from room attributes across "
        "every property (GAP-067). Idempotent; --dry-run writes nothing."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing (runs in a rolled-back transaction).",
        )

    def _sweep(self) -> tuple[Counter[str], int]:
        """Recompute every property; return (added/removed totals, #touched)."""
        totals: Counter[str] = Counter()
        touched = 0
        for prop in Property.objects.all().iterator():
            result = recompute_derived_features(prop)
            if result["added"] or result["removed"]:
                touched += 1
            totals["added"] += result["added"]
            totals["removed"] += result["removed"]
        return totals, touched

    def handle(self, *args: Any, **opts: Any) -> None:
        dry_run: bool = opts["dry_run"]
        if dry_run:
            # The service always writes, so the dry-run mechanism is a single
            # transaction rolled back after collecting the counts.
            with transaction.atomic():
                totals, touched = self._sweep()
                transaction.set_rollback(True)
        else:
            # A real run stays UN-wrapped so each property commits via the
            # service's own atomic — the sweep is then resumable/idempotent
            # (a failure mid-way keeps prior work; re-run applies only the
            # delta) instead of one all-or-nothing long transaction.
            totals, touched = self._sweep()

        prefix = "[dry-run] would apply:" if dry_run else "applied:"
        self.stdout.write(
            f"{prefix} {totals['added']} added, {totals['removed']} removed "
            f"derived feature link(s) across {touched} propertie(s)"
        )
