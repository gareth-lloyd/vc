"""`./manage.py loadlegacy <name> [...]` or `./manage.py loadlegacy --all`."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from core.console import render_table
from data_migration.base import LoadReport
from data_migration.registry import LOADERS


class Command(BaseCommand):
    help = "Run one or more legacy → Django data loaders."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("names", nargs="*", help="Loader names to run.")
        parser.add_argument(
            "--all",
            action="store_true",
            help="Run every registered loader in dependency order.",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List registered loaders and exit.",
        )
        parser.add_argument(
            "--since",
            default=None,
            help=(
                "ISO-8601 datetime. Loaders append "
                "`AND UpdatedAt > @since` to their legacy query so we only "
                "fetch rows changed during the cutover window."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["list"]:
            for name in LOADERS:
                self.stdout.write(name)
            return

        names: list[str] = list(options["names"])
        if options["all"]:
            names = list(LOADERS.keys())

        if not names:
            raise CommandError("Specify loader name(s), --all, or --list.")

        unknown = [n for n in names if n not in LOADERS]
        if unknown:
            raise CommandError(
                f"Unknown loader(s): {', '.join(unknown)}. Known: {', '.join(LOADERS) or '(none)'}",
            )

        since = options.get("since")
        reports = [LOADERS[name](since=since).load() for name in names]
        self._print_summary(reports)

    def _print_summary(self, reports: list[LoadReport]) -> None:
        header = ("loader", "created", "updated", "skipped", "errors", "duration")
        rows = [
            (r.loader, r.created, r.updated, r.skipped, len(r.errors), f"{r.duration_s:.2f}s")
            for r in reports
        ]
        self.stdout.write(render_table(header, rows))

        for r in reports:
            if r.errors:
                self.stdout.write(self.style.ERROR(f"\nErrors in {r.loader}:"))
                for legacy_id, message in r.errors:
                    self.stdout.write(f"  {legacy_id}: {message}")
