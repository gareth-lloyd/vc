"""Enquiries that never get a quote — some CONTACTED only, some LOST."""

from __future__ import annotations

from typing import cast

from core.seed._booking_helpers import pick_guest
from core.seed.context import SeedContext
from core.seed.registry import Stage, register
from reservations.factories import EnquiryFactory
from reservations.models.enquiry import Enquiry


def _run(ctx: SeedContext) -> int:
    if not ctx.properties:
        return 0
    active_properties = [p for p in ctx.properties if p.status == "active"] or ctx.properties
    lost = (
        max(1, int(len(active_properties) * ctx.knobs.pct_enquiry_lost_only))
        if ctx.knobs.pct_enquiry_lost_only
        else 0
    )
    contacted = (
        max(1, int(len(active_properties) * ctx.knobs.pct_enquiry_contacted_only))
        if ctx.knobs.pct_enquiry_contacted_only
        else 0
    )
    made = 0
    for i in range(lost):
        prop = active_properties[i % len(active_properties)]
        enquiry = cast(Enquiry, EnquiryFactory(guest=pick_guest(ctx), property=prop))
        ctx.enquiry_pks.append(enquiry.pk)
        enquiry.lose("No suitable match")
        made += 1
    for i in range(contacted):
        prop = active_properties[(i + 1) % len(active_properties)]
        enquiry = cast(Enquiry, EnquiryFactory(guest=pick_guest(ctx), property=prop))
        ctx.enquiry_pks.append(enquiry.pk)
        enquiry.contact()
        made += 1
    return made


register(Stage(name="orphan_enquiries", run=_run, depends_on=("bookings",)))
