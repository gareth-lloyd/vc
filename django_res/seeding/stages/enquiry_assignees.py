"""Assign most seeded enquiries to a sales (RESERVATIONS) staff owner.

Knob: `pct_enquiry_assigned` — fraction of run-scoped enquiries that pick up an
owner; the rest stay an unassigned queue.

There is no `SALES` staff role, so "sales people" maps to `StaffRole.RESERVATIONS`
(the ops/sales-facing role). Assignment goes through `Enquiry.assign`, which
writes the `ASSIGNED` event so the activity timeline stays coherent.

This stage draws from its **own** `random.Random`, never `ctx.rng`, so it can be
sequenced anywhere without shifting the shared RNG stream that other stages
depend on for reproducibility.
"""

from __future__ import annotations

import random

from accounts.models import User
from core.enums import StaffRole
from reservations.models.enquiry import Enquiry
from seeding.context import SeedContext
from seeding.registry import Stage, register

# Stable, private seed: keeps selection reproducible for a given enquiry-pk list
# while staying decoupled from ctx.rng.
_ASSIGN_SEED = 0xA55169


def _run(ctx: SeedContext) -> int:
    pct = ctx.knobs.pct_enquiry_assigned
    if pct <= 0 or not ctx.enquiry_pks:
        return 0
    staff = list(User.objects.filter(is_staff=True, role=StaffRole.RESERVATIONS).order_by("pk"))
    if not staff:
        return 0  # no sales staff to assign to; skip cleanly
    rng = random.Random(_ASSIGN_SEED)
    n = int(len(ctx.enquiry_pks) * pct)
    chosen = rng.sample(ctx.enquiry_pks, k=min(n, len(ctx.enquiry_pks)))
    for pk in chosen:
        Enquiry.objects.get(pk=pk).assign(rng.choice(staff))
    return len(chosen)


register(
    Stage(
        name="enquiry_assignees",
        run=_run,
        depends_on=(
            "users",
            "bookings",
            "extra_quotations",
            "orphan_enquiries",
            "dashboard_activity",
        ),
    )
)
