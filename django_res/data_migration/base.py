"""Base loader contract.

A loader pulls rows from the legacy SQL Server, transforms them per the
mapping in `django_res_design/09-departures.md`, and upserts into the new
Django schema keyed on `legacy_id`.

Loaders are idempotent: re-running creates nothing new on the second pass,
only updates fields that drifted. This lets us iterate per-domain without
needing to reset the target DB between runs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, ClassVar

from django.db import transaction
from django.db.models import Model

from data_migration.legacy_db import legacy_cursor, rows_as_dicts


@dataclass
class LoadReport:
    loader: str
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)
    duration_s: float = 0.0

    def as_row(self) -> tuple[str, int, int, int, int, str]:
        return (
            self.loader,
            self.created,
            self.updated,
            self.skipped,
            len(self.errors),
            f"{self.duration_s:.2f}s",
        )


class BaseLoader:
    """Subclass per legacy → new mapping.

    Subclasses must set `name`, `legacy_query`, `target_model`, and override
    `transform(row)` to produce kwargs for the upsert (or `None` to skip).
    """

    name: ClassVar[str] = ""
    legacy_query: ClassVar[str] = ""
    target_model: ClassVar[type[Model]]
    legacy_pk_column: ClassVar[str] = "Id"

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError

    def load(self) -> LoadReport:
        report = LoadReport(loader=self.name)
        started = time.monotonic()

        with legacy_cursor() as cursor:
            cursor.execute(self.legacy_query)
            rows = list(rows_as_dicts(cursor))

        with transaction.atomic():
            for row in rows:
                self._process_row(row, report)

        report.duration_s = time.monotonic() - started
        return report

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        legacy_id = row.get(self.legacy_pk_column)
        if legacy_id is None:
            report.skipped += 1
            return

        try:
            kwargs = self.transform(row)
        except Exception as exc:
            report.errors.append((str(legacy_id), repr(exc)))
            return

        if kwargs is None:
            report.skipped += 1
            return

        _, created = self.target_model._default_manager.update_or_create(
            legacy_id=str(legacy_id),
            defaults=kwargs,
        )
        if created:
            report.created += 1
        else:
            report.updated += 1
