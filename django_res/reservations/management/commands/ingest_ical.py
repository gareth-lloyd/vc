"""Poll per-villa iCal feeds and reconcile owner-availability blocks (GAP-011).

Cron-invokable today; once Celery + beat land, `reservations.tasks.ingest_ical_feeds`
wraps with `@shared_task` and this command becomes a manual escape hatch.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser


class Command(BaseCommand):
    help = "Poll active per-villa iCal feeds and reconcile owner-availability blocks."

    def add_arguments(self, parser: CommandParser) -> None:
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--property-id",
            type=int,
            help="Only poll the feeds of this property (default: every property).",
        )
        group.add_argument(
            "--all",
            action="store_true",
            help="Poll every property's feeds (the default behaviour).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        from properties.models import Property
        from reservations.services.ical_ingest import ICalIngestService

        property_id = options.get("property_id")
        if property_id is not None:
            queryset = Property.objects.filter(pk=property_id)
            if not queryset.exists():
                raise CommandError(f"No property with id {property_id}.")
        else:
            queryset = None

        results = ICalIngestService.run(properties=queryset)

        created = sum(r.created for r in results)
        cancelled = sum(r.cancelled for r in results)
        conflicts = sum(r.conflicts for r in results)
        skipped_holds = sum(r.skipped_holds for r in results)
        skipped_props = sum(1 for r in results if r.skipped)

        self.stdout.write(
            self.style.SUCCESS(
                f"iCal ingest: {len(results)} properties with feeds — "
                f"{created} blocks created, {cancelled} cancelled, "
                f"{conflicts} conflicts, {skipped_holds} hold-overlaps skipped, "
                f"{skipped_props} properties skipped (feed errors)."
            )
        )
