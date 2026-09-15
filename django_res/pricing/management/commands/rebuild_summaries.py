"""Rebuild every `VillaPricingSummary` row synchronously.

`data_migration.BaseLoader` suppresses the per-edit Celery rebuild
(`pricing.signals.suppress_summary_rebuild`, GAP-108); `loadlegacy` rebuilds
once at the end of its run. This command is the manual equivalent.
Idempotent — safe to re-run any time.

Usage:

    manage.py rebuild_summaries
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from pricing.tasks import rebuild_all_summaries


class Command(BaseCommand):
    help = "Rebuild VillaPricingSummary for every (property, currency) with a RatePlan."

    def handle(self, *args: Any, **options: Any) -> None:
        count = rebuild_all_summaries()
        self.stdout.write(self.style.SUCCESS(f"Rebuilt {count} pricing summaries."))
