"""Backfill the parallel `person` FK from `guest` on the reservation models (GAP-045 Unit 3c-1b).

The five reservation models — Enquiry / Quotation / Booking / BookingGuest /
GuestPreference — each carry a nullable parallel `person` FK alongside `guest`
during the expand/contract cutover. Every *write* path now sets `person`
inline (services, serializer, factory, loaders), but two gaps remain a `person`
could stay NULL through:

- rows created during a deploy window, before the inline-setting code shipped;
- loader re-runs, where `defaults` only applies on create (so a row that
  pre-dates this change keeps its NULL `person`).

This command is the idempotent delta linker that closes those gaps: for each
model it finds rows with `person IS NULL AND guest IS NOT NULL`, resolves the
Person mirror via `person_for_guest`, and `bulk_update`s them in batches. A
second run is a no-op (nothing matches the `person__isnull=True` filter once
linked).

`bulk_update` deliberately bypasses the audit trail / `updated_at` bump: this
is a pure denorm-fill of a transitional column, not a business edit — the same
rationale as the LEAD-BookingGuest denorm sync in `reservations.signals`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.management.base import BaseCommand
from django.db import transaction

if TYPE_CHECKING:
    from django.db.models import Model

# (model import path, attribute) for every reservation model carrying the
# parallel person FK. Imported lazily in handle() to dodge AppConfig ordering.
_MODELS = (
    ("reservations.models.enquiry", "Enquiry"),
    ("reservations.models.quotation", "Quotation"),
    ("reservations.models.booking", "Booking"),
    ("reservations.models.booking_guest", "BookingGuest"),
    ("reservations.models.preferences", "GuestPreference"),
)

_BATCH_SIZE = 500


class Command(BaseCommand):
    help = (
        "Backfill the parallel `person` FK from `guest` on the reservation "
        "models (idempotent; safe to re-run)."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        from importlib import import_module

        from reservations.services.person_sync import person_for_guest

        total = 0
        for module_path, class_name in _MODELS:
            model: type[Model] = getattr(import_module(module_path), class_name)
            linked = self._link_model(model, person_for_guest)
            total += linked
            self.stdout.write(f"{class_name}: linked {linked}")

        self.stdout.write(self.style.SUCCESS(f"link_person_fks: linked {total} rows in total."))

    def _link_model(self, model: type[Model], person_for_guest: Any) -> int:
        """Fill `person` from `guest` for every NULL-person row of one model."""
        manager = model._default_manager
        linked = 0
        batch: list[Any] = []
        # `select_related("guest")` so resolving the mirror doesn't N+1 the FK.
        rows: Any = (
            manager.filter(person__isnull=True, guest__isnull=False)
            .select_related("guest")
            .iterator(chunk_size=_BATCH_SIZE)
        )
        for row in rows:
            row.person = person_for_guest(row.guest)
            batch.append(row)
            if len(batch) >= _BATCH_SIZE:
                linked += self._flush(manager, batch)
                batch = []
        linked += self._flush(manager, batch)
        return linked

    @staticmethod
    def _flush(manager: Any, batch: list[Any]) -> int:
        if not batch:
            return 0
        with transaction.atomic():
            manager.bulk_update(batch, ["person"], batch_size=_BATCH_SIZE)
        return len(batch)
