"""WebhookDelivery rows: one per `pct_webhooks` fraction of payments.

Spreads across the three operational shapes:
  * delivered  — signature_valid=True, processed_at set, no error
  * failed     — processing_error populated
  * retrying   — retry_count > 0, processed_at still null

Skipped when `pct_webhooks == 0`.
"""

from __future__ import annotations

from django.utils import timezone

from core.seed.context import SeedContext
from core.seed.registry import Stage, register
from payments.factories import WebhookDeliveryFactory
from payments.models.payment import Payment


def _run(ctx: SeedContext) -> int:
    if ctx.knobs.pct_webhooks <= 0:
        return 0
    # Scope to payments tied to bookings this run created — additive reruns
    # must not inflate webhook deliveries on prior-run payments.
    if not ctx.booking_pks:
        return 0
    payment_pks = list(
        Payment.objects.filter(booking_id__in=ctx.booking_pks).values_list("pk", flat=True)
    )
    if not payment_pks:
        return 0
    n = int(len(payment_pks) * ctx.knobs.pct_webhooks)
    if n <= 0:
        return 0
    chosen = ctx.rng.sample(payment_pks, k=min(n, len(payment_pks)))
    now = timezone.now()
    made = 0
    for i, pk in enumerate(chosen):
        outcome = i % 3
        kwargs: dict[str, object] = {"payment_id": pk}
        if outcome == 0:
            kwargs.update(
                signature_valid=True,
                processed_at=now,
            )
        elif outcome == 1:
            kwargs.update(
                signature_valid=True,
                processed_at=now,
                processing_error="Mock processing failure (seeded)",
            )
        else:
            kwargs.update(
                signature_valid=True,
                processed_at=None,
                retry_count=ctx.rng.randint(1, 4),
            )
        WebhookDeliveryFactory(**kwargs)
        made += 1
    return made


register(Stage(name="webhooks", run=_run, depends_on=("bookings",)))
