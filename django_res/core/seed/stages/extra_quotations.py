"""Quotations that never become bookings: SENT / EXPIRED / CANCELLED."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

from django.db import transaction
from django.utils import timezone

from core.seed._booking_helpers import pick_guest
from core.seed.context import SeedContext
from core.seed.registry import Stage, register
from reservations.factories import EnquiryFactory
from reservations.models.enquiry import Enquiry
from reservations.services.quotations import QuotationService


def _run(ctx: SeedContext) -> int:
    if not ctx.knobs.pct_extra_quotation_per_booking or not ctx.properties:
        return 0
    active_properties = [p for p in ctx.properties if p.status == "active"] or ctx.properties
    target = max(1, int(ctx.n_bookings * ctx.knobs.pct_extra_quotation_per_booking))
    outcomes = ("sent", "expired", "cancelled")
    expires_at = timezone.now() + timedelta(days=7)
    made = 0
    for i in range(target):
        prop = active_properties[i % len(active_properties)]
        date_from = ctx.today + timedelta(days=30 + i * 11)
        date_to = date_from + timedelta(days=5)
        guest = pick_guest(ctx)
        terms = ctx.terms[0]
        plan = prop.rate_plans.first()
        currency: Any = plan.currency if plan is not None else ctx.default_currency
        enquiry = cast(
            Enquiry,
            EnquiryFactory(guest=guest, property=prop, date_from=date_from, date_to=date_to),
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
                currency=currency,
                terms_version=terms,
                expires_at=expires_at,
            )
            quotation.send()
            outcome = outcomes[i % len(outcomes)]
            if outcome == "expired":
                quotation.expire()
            elif outcome == "cancelled":
                quotation.cancel("Guest never replied")
        made += 1
    return made


register(Stage(name="extra_quotations", run=_run, depends_on=("bookings",)))
