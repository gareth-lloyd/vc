"""Quotations that never become bookings: SENT / EXPIRED / CANCELLED."""

from __future__ import annotations

from datetime import timedelta
from typing import cast

from django.db import transaction
from django.utils import timezone

from reservations.factories import EnquiryFactory
from reservations.models.enquiry import Enquiry
from reservations.services.quotations import QuotationService
from seeding._booking_helpers import conforming_stay, pick_guest
from seeding.context import SeedContext
from seeding.registry import Stage, register


def _run(ctx: SeedContext) -> int:
    if not ctx.knobs.pct_extra_quotation_per_booking or not ctx.properties:
        return 0
    active_properties = [p for p in ctx.properties if p.status == "active"] or ctx.properties
    target = max(1, int(ctx.n_bookings * ctx.knobs.pct_extra_quotation_per_booking))
    outcomes = ("sent", "expired", "cancelled")
    # Longer live window on dense runs so SENT quotation cells stay visible
    # across the demo calendar; the legacy 7 days otherwise.
    expires_at = timezone.now() + timedelta(days=30 if ctx.knobs.dense_calendar else 7)
    # Keep stays inside the seeded rate-coverage window. The `properties` stage
    # seeds RatePeriods out to `today + (spread + 60)` (or the factory default
    # `today + 400`); an unbounded `i * 21` stride marches years past that and
    # trips NoRateAvailable, which aborts the whole stage. Wrap the forward
    # offset within the covered window, leaving a 13-day tail for the longest
    # conforming stay (min-nights + up-to-6-day changeover alignment).
    spread = ctx.knobs.booking_date_spread_days
    coverage_days = spread + 60 if spread > 30 else 400
    span = max(1, coverage_days - 30 - 13)
    made = 0
    for i in range(target):
        prop = active_properties[i % len(active_properties)]
        # 21-day stride spaces consecutive holds on the same villa apart; the
        # modulo wrap keeps every stay inside the rate-coverage window. On the
        # same property, quotes are `len(active_properties)` iterations apart,
        # so wrapping never lands two holds on the same dates.
        offset = 30 + (i * 21) % span
        date_from, date_to = conforming_stay(ctx, prop, ctx.today + timedelta(days=offset), 5)
        customer = pick_guest(ctx)
        terms = ctx.terms[0]
        enquiry = cast(
            Enquiry,
            EnquiryFactory(person=customer, property=prop, date_from=date_from, date_to=date_to),
        )
        ctx.enquiry_pks.append(enquiry.pk)
        with transaction.atomic():
            quotation = QuotationService.create_from_enquiry(
                enquiry,
                [
                    {
                        "property": prop,
                        "date_from": date_from,
                        "date_to": date_to,
                        "adults": 2,
                        "children": 0,
                    }
                ],
                terms_version=terms,
                expires_at=expires_at,
            )
            quotation.send()
            outcome = outcomes[i % len(outcomes)]
            if outcome == "expired":
                quotation.expire()
            elif outcome == "cancelled":
                quotation.cancel("Guest never replied")
            else:
                # Holds are a manual operator action now — mirror an operator
                # protecting a live SENT quote's dates, then stretch the
                # expiry so quotation cells stay visible across the demo
                # calendar window (the effective-setting default is ~48h).
                hold = QuotationService.hold_line(quotation.lines.get())
                hold.expires_at = expires_at
                hold.save(update_fields=["expires_at", "updated_at"])
        made += 1
    return made


register(Stage(name="extra_quotations", run=_run, depends_on=("bookings",)))
