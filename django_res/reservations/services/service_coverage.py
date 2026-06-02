"""ConciergeCoverageService — set the progress status of one service cell.

Backs the concierge matrix's per-cell status control. Rows are created
lazily: the first time an operator moves a (booking, service) off the
implicit ``not_started`` default, a `BookingServiceCoverage` row is born.

Write access is gated at the view by `IsReservationsWriter` (the same gate
the sibling concierge-item `:confirm` action uses), so this service does not
re-check `actor_has_perm`. `actor` is kept on the signature for symmetry with
the rest of the service layer and to document intent at the call site; the
audit trail attributes the change via the request's thread-local user.
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction

from reservations.models import Booking, BookingServiceCoverage


class ConciergeCoverageService:
    @classmethod
    def set_status(
        cls,
        *,
        booking: Booking,
        service: str,
        status: str,
        actor: Any = None,
    ) -> BookingServiceCoverage:
        """Upsert the coverage cell for `(booking, service)` to `status`.

        ``update_or_create`` is read-then-write, so a concurrent insert (e.g. a
        double-click) can lose the `(booking, service)` unique-constraint race.
        The except sits *outside* the `atomic()` block — a failed statement
        poisons the surrounding transaction — and recovers by re-fetching the
        row the racer created and applying our status (last-write-wins).
        """
        try:
            with transaction.atomic():
                coverage, _ = BookingServiceCoverage.objects.update_or_create(
                    booking=booking,
                    service=service,
                    defaults={"status": status},
                )
            return coverage
        except IntegrityError:
            coverage = BookingServiceCoverage.objects.get(booking=booking, service=service)
            coverage.status = status
            coverage.save(update_fields=["status"])
            return coverage
