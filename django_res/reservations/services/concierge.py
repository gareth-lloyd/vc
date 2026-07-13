"""ConciergeService — concierge-line orchestration.

Concierge money is deliberately NON-SCHEDULING (SMELL-020): concierge lines
never enter `booking_total()` (the single guest-total authority in
`reservations.services.charges`), never fire `booking_total_changed`, and
never resize the payment schedule or the security deposit. Guests settle
concierge lines on their own track — the (pending) implementation opens a
`Payment(purpose=CONCIERGE)` per line via `request_payment`.

`request_payment(...)` is a stub: the concierge COLLECTION FLOW is the
pending piece (the payments app itself is fully landed, including the
`PaymentPurpose.CONCIERGE` enum value). The real implementation will open a
`Payment(purpose=CONCIERGE)` for the chosen `BookingConciergeItem`; the seam
is exposed now so that work can land without churn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from reservations.models.concierge import BookingConciergeItem


class ConciergeService:
    """Concierge-line orchestration (non-scheduling money — see module doc)."""

    @classmethod
    def request_payment(
        cls,
        item: BookingConciergeItem,
        *,
        actor: Any = None,
    ) -> None:
        """Open a `Payment(purpose=CONCIERGE)` for a concierge line.

        TODO: implement the concierge collection flow. The shape is fixed so
        the `payments` service layer can call back into here without churn.
        """
        raise NotImplementedError(
            "Concierge collection flow (Payment purpose=CONCIERGE) is pending"
        )
