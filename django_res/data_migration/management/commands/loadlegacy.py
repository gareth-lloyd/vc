"""`./manage.py loadlegacy <name> [...]` or `./manage.py loadlegacy --all`."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

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

        reports = [LOADERS[name]().load() for name in names]
        self._print_summary(reports)

    def _print_summary(self, reports: list[LoadReport]) -> None:
        header = ("loader", "created", "updated", "skipped", "errors", "duration")
        rows: list[tuple[str | int, ...]] = [header]
        for r in reports:
            rows.append(
                (r.loader, r.created, r.updated, r.skipped, len(r.errors), f"{r.duration_s:.2f}s"),
            )
        widths = [max(len(str(c)) for c in col) for col in zip(*rows, strict=True)]
        for i, row in enumerate(rows):
            self.stdout.write(
                "  ".join(str(c).ljust(w) for c, w in zip(row, widths, strict=True)),
            )
            if i == 0:
                self.stdout.write("  ".join("-" * w for w in widths))

        for r in reports:
            if r.errors:
                self.stdout.write(self.style.ERROR(f"\nErrors in {r.loader}:"))
                for legacy_id, message in r.errors:
                    self.stdout.write(f"  {legacy_id}: {message}")
