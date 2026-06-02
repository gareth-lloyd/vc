"""Loader: legacy Zoho external IDs → integrations.SyncRecord.

Preserving the external IDs Zoho already issued against legacy rows is the
critical-path integrations migration: they are the routing keys for every
subsequent push, so dropping them makes the first post-cutover sync create
duplicate Zoho records and orphan years of CRM activity. See
`django_res_design/08-integrations.md` → "Migrating legacy external IDs" and
`data_migration/CUTOVER.md` step 4b.

The legacy DB is the only home of these keys and is decommissioned shortly
after cutover, so the backfill must run inside the cutover window even though
the outbound sync engine itself is deferred (`integrations/tasks.py`).

This is deliberately **not** a `BaseLoader` subclass: that contract assumes a
single legacy query and an upsert keyed on `legacy_id`, whereas this loader
sweeps five source tables, resolves into five different models, and keys
`SyncRecord` on the content-type tuple `(content_type, object_id, provider)`.
It satisfies the `Loader` protocol (`name`, `load() -> LoadReport`) and reuses
the same cursor/report helpers so it registers and reports like any other
loader.

Note on the design spec: `08-integrations.md` shows the Zoho upsert keyed on
`(..., provider, provider_instance)` with `provider_instance=""`, but the
actual `SyncRecord` model has no `provider_instance` field (its unique key is
`(content_type, object_id, provider)`). Zoho is single-tenant, so it fits the
real model cleanly; `provider_instance` only matters for the WordPress
multi-site side, which is handled separately.

`VillaArchiveBooking` also carries `ZohoId`, but archived bookings are not
loaded into `reservations.Booking`, so there is no local target to point at;
that keep/drop decision is tracked in the audit, not handled here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils import timezone

from accounts.models import Contact
from data_migration.base import LoadReport, legacy_datetime_literal
from data_migration.legacy_db import legacy_cursor, rows_as_dicts
from integrations.enums import SyncDirection, SyncProvider, SyncStatus
from integrations.models import SyncRecord
from properties.models.property import Property
from reservations.models.booking import Booking
from reservations.models.enquiry import Enquiry
from reservations.models.quotation import Quotation


@dataclass(frozen=True)
class _ZohoSpec:
    """One legacy `ZohoId`-carrying table and the local model it maps to.

    `has_timestamps` is False for tables without `CreatedAt`/`UpdatedAt`
    (only `VillaContact`); those skip the `last_pushed_at` backfill and ignore
    `--since`.
    """

    table: str
    model: type[models.Model]
    has_timestamps: bool


class SyncRecordZohoLoader:
    name: ClassVar[str] = "syncrecord_zoho"

    # Order mirrors the domain loaders that populate these models' `legacy_id`.
    SPECS: ClassVar[tuple[_ZohoSpec, ...]] = (
        _ZohoSpec("VillaMaster", Property, has_timestamps=True),
        _ZohoSpec("VillaContact", Contact, has_timestamps=False),
        _ZohoSpec("VillaEnquire", Enquiry, has_timestamps=True),
        _ZohoSpec("VillaQuotationMaster", Quotation, has_timestamps=True),
        _ZohoSpec("VillaBooking", Booking, has_timestamps=True),
    )

    def __init__(self, since: str | None = None) -> None:
        # Validate up-front so an invalid CLI arg fails fast.
        self.since: datetime | None = datetime.fromisoformat(since) if since else None

    def _query(self, spec: _ZohoSpec) -> str:
        cols = "Id, ZohoId, CreatedAt, UpdatedAt" if spec.has_timestamps else "Id, ZohoId"
        query = f"SELECT {cols} FROM {spec.table}"
        if self.since and spec.has_timestamps:
            query = f"{query} WHERE UpdatedAt > '{legacy_datetime_literal(self.since)}'"
        return query

    def load(self) -> LoadReport:
        report = LoadReport(loader=self.name)
        started = time.monotonic()

        # Fetch every source row first (cheap: Id + ZohoId + timestamps), then
        # write under one transaction — mirrors BaseLoader so the legacy cursor
        # isn't held open during Postgres writes.
        fetched: list[tuple[_ZohoSpec, dict[str, Any]]] = []
        with legacy_cursor() as cursor:
            for spec in self.SPECS:
                cursor.execute(self._query(spec))
                fetched.extend((spec, row) for row in rows_as_dicts(cursor))

        with transaction.atomic():
            for spec, row in fetched:
                self._process_row(spec, row, report)

        report.duration_s = time.monotonic() - started
        return report

    def _process_row(self, spec: _ZohoSpec, row: dict[str, Any], report: LoadReport) -> None:
        external_id = (row.get("ZohoId") or "").strip()
        if not external_id:
            report.skipped += 1
            return

        legacy_id = row.get("Id")
        local = spec.model._default_manager.filter(legacy_id=str(legacy_id)).first()
        if local is None:
            # A SyncRecord must point at a real row — no sentinel fallback.
            report.skipped += 1
            return

        content_type = ContentType.objects.get_for_model(spec.model)

        # Guard the unique(provider, external_id) constraint explicitly: a
        # legacy ZohoId that already maps to a different target is recorded as
        # an error rather than allowed to raise IntegrityError and poison the
        # surrounding transaction.
        clash = (
            SyncRecord.objects.filter(provider=SyncProvider.ZOHO_CRM, external_id=external_id)
            .exclude(content_type=content_type, object_id=local.pk)
            .first()
        )
        if clash is not None:
            report.errors.append(
                (
                    f"{spec.table}:{legacy_id}",
                    f"ZohoId {external_id!r} already mapped to "
                    f"{clash.content_type.model}:{clash.object_id}",
                )
            )
            return

        last_pushed = row.get("UpdatedAt") or row.get("CreatedAt")
        if last_pushed is not None and timezone.is_naive(last_pushed):
            last_pushed = timezone.make_aware(last_pushed)

        _, created = SyncRecord.objects.update_or_create(
            content_type=content_type,
            object_id=local.pk,
            provider=SyncProvider.ZOHO_CRM,
            defaults={
                "external_id": external_id,
                "direction": SyncDirection.PUSH,
                "status": SyncStatus.IN_SYNC,
                "last_pushed_at": last_pushed,
            },
        )
        if created:
            report.created += 1
        else:
            report.updated += 1
