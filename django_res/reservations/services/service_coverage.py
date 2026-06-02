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
        """Upsert the coverage cell for `(booking, service)` to `status`."""
        coverage, _ = BookingServiceCoverage.objects.update_or_create(
            booking=booking,
            service=service,
            defaults={"status": status},
        )
        return coverage
