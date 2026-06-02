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
from datetime import datetime
from typing import Any, ClassVar, Protocol, runtime_checkable

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


def legacy_datetime_literal(value: datetime) -> str:
    """Format a parsed `--since` datetime as a SQL Server literal.

    Whole-second precision; the value is a validated `datetime`, not user SQL.
    Shared by every loader that threads `--since` into an inline ``WHERE`` so
    the literal format can't drift between implementations.
    """
    return value.strftime("%Y-%m-%dT%H:%M:%S")


@runtime_checkable
class Loader(Protocol):
    """Structural contract the registry and `loadlegacy` rely on.

    `BaseLoader` is the common implementation, but a loader that doesn't fit
    its one-query / `legacy_id`-keyed-upsert shape (e.g. the cross-table
    `SyncRecordZohoLoader`) only needs to satisfy this protocol to register
    and run like any other loader.
    """

    name: ClassVar[str]

    def __init__(self, since: str | None = None) -> None: ...

    def load(self) -> LoadReport: ...


class BaseLoader:
    """Subclass per legacy → new mapping.

    Subclasses must set `name`, `legacy_query`, `target_model`, and override
    `transform(row)` to produce kwargs for the upsert (or `None` to skip).

    `since`: an ISO-8601 datetime string. When set, the loader appends
    ``AND UpdatedAt > @since`` to its legacy query (subclasses with a
    custom WHERE clause must include the placeholder ``-- /*SINCE*/`` if
    they want it threaded in automatically). Loaders that target legacy
    tables without an `UpdatedAt` column should override `_apply_since` to
    no-op.
    """

    name: ClassVar[str] = ""
    legacy_query: ClassVar[str] = ""
    target_model: ClassVar[type[Model]]
    legacy_pk_column: ClassVar[str] = "Id"
    since_column: ClassVar[str] = "UpdatedAt"

    def __init__(self, since: str | None = None) -> None:
        # Validate up-front so an invalid CLI arg fails fast and so the
        # parsed value can be safely re-formatted into SQL below.
        self.since: datetime | None = datetime.fromisoformat(since) if since else None

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError

    def _apply_since(self, query: str) -> str:
        if not self.since:
            return query
        clause = f"{self.since_column} > '{legacy_datetime_literal(self.since)}'"
        if " where " in query.lower():
            return f"{query} AND {clause}"
        return f"{query} WHERE {clause}"

    def load(self) -> LoadReport:
        report = LoadReport(loader=self.name)
        started = time.monotonic()

        with legacy_cursor() as cursor:
            cursor.execute(self._apply_since(self.legacy_query))
            rows = list(rows_as_dicts(cursor))

        self._load_rows(rows, report)

        report.duration_s = time.monotonic() - started
        return report

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        """Process every row, isolating each write in its own savepoint.

        The outer `atomic` keeps the whole load as one transaction; the inner
        `atomic` per row is a savepoint, so a write-time failure on one row
        (e.g. an `IntegrityError` from a unique collision) is rolled back to the
        savepoint, recorded in `report.errors`, and skipped — without aborting
        the rows that follow. `_process_row` already catches `transform()`
        errors itself (recording them once and returning), so only write-time
        exceptions reach the `except` here.
        """
        with transaction.atomic():
            for row in rows:
                try:
                    with transaction.atomic():
                        self._process_row(row, report)
                except Exception as exc:  # isolate one bad row from the rest
                    report.errors.append((str(row.get(self.legacy_pk_column)), repr(exc)))

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
