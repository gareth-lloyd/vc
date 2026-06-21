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
    made = 0
    for i in range(target):
        prop = active_properties[i % len(active_properties)]
        # 21-day stride: a constrained villa's stay conforms to 7 nights plus
        # an up-to-6-day forward alignment (13 days end-to-end), so the old
        # 11-day stride would collide consecutive holds on a small portfolio.
        date_from, date_to = conforming_stay(ctx, prop, ctx.today + timedelta(days=30 + i * 21), 5)
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
