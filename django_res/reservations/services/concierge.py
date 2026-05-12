"""ConciergeService — placeholder for the payments-app integration point.

`request_payment(...)` is a stub: the real implementation will compose
with the `payments` app to open a `Payment(purpose=CONCIERGE)` for the
chosen `BookingConciergeItem`. It's exposed now only so the payments
service layer has a stable import target when it lands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from reservations.models.concierge import BookingConciergeItem


class ConciergeService:
    """Concierge-line orchestration. Currently a documented stub."""

    @classmethod
    def request_payment(
        cls,
        item: BookingConciergeItem,
        *,
        actor: Any = None,
    ) -> None:
        """Open a payment for a concierge line.

        TODO: implement once the payments app lands. The shape is fixed so the
        eventual `payments` service can call back into here without churn.
        """
        raise NotImplementedError(
            "ConciergeService.request_payment requires the payments app — pending"
        )
