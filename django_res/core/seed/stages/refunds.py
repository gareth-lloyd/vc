"""Drive refunds across the four interesting terminal outcomes.

Sources two cohorts:
  * cancelled bookings with settled deposit/balance -> `from_cancellation`
  * paid-up bookings (BALANCE_PAID / CHECKED_OUT) -> small goodwill refunds
    via `RefundService.request`

Combining both ensures REJECTED / APPROVED / FAILED / SUCCEEDED are all
reachable even when only one cancellation landed with money on it.
"""

from __future__ import annotations

from decimal import Decimal

from core.seed.context import SeedContext
from core.seed.registry import Stage, register


def _run(ctx: SeedContext) -> int:
    if not ctx.knobs.pct_refund_of_cancelled:
        return 0
    from payments.enums import (
        PaymentStatus,
        RefundPurposeTrack,
        RefundReasonCode,
        RefundStatus,
    )
    from payments.services.refund import RefundService
    from reservations.enums import BookingStatus
    from reservations.models.booking import Booking

    refundable_cancelled = list(
        Booking.objects.filter(
            status=BookingStatus.CANCELLED.value,
            payments__status=PaymentStatus.SUCCEEDED.value,
        )
        .exclude(refunds__isnull=False)
        .distinct()
        .values_list("pk", flat=True)
    )
    paid_up = list(
        Booking.objects.filter(
            status__in=(
                BookingStatus.BALANCE_PAID.value,
                BookingStatus.CHECKED_OUT.value,
            )
        )
        .exclude(refunds__isnull=False)
        .values_list("pk", flat=True)
    )
    candidates: list[tuple[int, str]] = [(pk, "cancellation") for pk in refundable_cancelled] + [
        (pk, "goodwill") for pk in paid_up
    ]
    if not candidates:
        return 0
    target = max(1, int(len(candidates) * ctx.knobs.pct_refund_of_cancelled))
    chosen = ctx.rng.sample(candidates, k=min(target, len(candidates)))

    made = 0
    for i, (pk, source) in enumerate(chosen):
        booking = Booking.objects.select_related("currency", "property").get(pk=pk)
        if source == "cancellation":
            refund = RefundService.from_cancellation(
                booking, reason="seed_dev cancellation", requested_by=None
            )
        else:
            refund = RefundService.request(
                booking=booking,
                amount=Decimal("25.00"),
                currency=booking.currency,
                purpose_track=RefundPurposeTrack.GOODWILL.value,
                reason_code=RefundReasonCode.GOODWILL.value,
                reason_notes="seed_dev goodwill gesture",
            )
        if refund is None:
            continue
        outcome = i % 4
        if outcome == 0:
            RefundService.reject(refund, actor=None, reason="Out-of-policy")
        elif outcome == 1:
            RefundService.approve(refund, actor=None)
        elif outcome == 2:
            RefundService.approve(refund, actor=None)
            RefundService.execute(refund, actor=None)
            refund._transition(RefundStatus.FAILED.value, kind="seed_dev_failed")
        else:
            RefundService.approve(refund, actor=None)
            RefundService.execute(refund, actor=None)
            refund._transition(RefundStatus.SUCCEEDED.value, kind="seed_dev_succeeded")
        made += 1
    return made


register(Stage(name="refunds", run=_run, depends_on=("bookings",)))
