"""The `enquiry_assignees` stage assigns most seeded enquiries to a sales
(RESERVATIONS) staff owner, leaving a realistic unassigned remainder.

See ``seeding/stages/enquiry_assignees.py``.
"""

from __future__ import annotations

import random
from typing import cast

import pytest

from accounts.factories import UserFactory
from core.enums import StaffRole
from reservations.enums import EnquiryEventKind
from reservations.factories import EnquiryFactory
from reservations.models.enquiry import Enquiry
from seeding.context import _PROFILES, Profile, SeedContext
from seeding.stages.enquiry_assignees import _run

pytestmark = pytest.mark.django_db


def _ctx(enquiry_pks: list[int], *, profile: Profile = Profile.MIXED) -> SeedContext:
    ctx = SeedContext(
        rng=random.Random(0),
        knobs=_PROFILES[profile],
        n_properties=0,
        n_bookings=0,
        n_users=0,
    )
    ctx.enquiry_pks.extend(enquiry_pks)
    return ctx


def _make_enquiries(n: int) -> list[int]:
    return [cast(Enquiry, EnquiryFactory()).pk for _ in range(n)]


def _sales_users(n: int = 2) -> list:
    return [UserFactory(role=StaffRole.RESERVATIONS) for _ in range(n)]


def test_assigns_roughly_80_percent_to_reservations_staff() -> None:
    _sales_users(2)
    pks = _make_enquiries(20)
    ctx = _ctx(pks)

    made = _run(ctx)

    assert made == 16  # int(20 * 0.8)
    assigned = Enquiry.objects.filter(pk__in=pks, assigned_to__isnull=False)
    unassigned = Enquiry.objects.filter(pk__in=pks, assigned_to__isnull=True)
    assert assigned.count() == 16
    assert unassigned.count() == 4
    # Every chosen owner is a RESERVATIONS user — never ADMIN/ACCOUNTS/VIEWER.
    owners = [e.assigned_to for e in assigned.select_related("assigned_to")]
    assert owners and all(o is not None and o.role == StaffRole.RESERVATIONS for o in owners)


def test_writes_an_assigned_event_per_assignment() -> None:
    _sales_users(1)
    pks = _make_enquiries(10)

    _run(_ctx(pks))

    assigned = Enquiry.objects.filter(pk__in=pks, assigned_to__isnull=False)
    for enquiry in assigned:
        assert enquiry.events.filter(kind=EnquiryEventKind.ASSIGNED).count() == 1


def test_only_reservations_users_are_eligible() -> None:
    # A pool of non-sales staff (admin/accounts/viewer) yields no assignments.
    UserFactory(role=StaffRole.ADMIN)
    UserFactory(role=StaffRole.ACCOUNTS)
    UserFactory(role=StaffRole.VIEWER)
    pks = _make_enquiries(10)

    made = _run(_ctx(pks))

    assert made == 0
    assert Enquiry.objects.filter(pk__in=pks, assigned_to__isnull=False).count() == 0


def test_empty_enquiry_list_is_a_noop() -> None:
    _sales_users(1)
    assert _run(_ctx([])) == 0


def test_zero_knob_disables_the_stage() -> None:
    _sales_users(1)
    pks = _make_enquiries(10)
    ctx = _ctx(pks, profile=Profile.MIXED)
    ctx.knobs = _PROFILES[Profile.MIXED].__class__(name="test", pct_enquiry_assigned=0.0)

    assert _run(ctx) == 0
    assert Enquiry.objects.filter(pk__in=pks, assigned_to__isnull=False).count() == 0


def test_deterministic_selection_over_the_same_pk_list() -> None:
    _sales_users(3)
    pks = _make_enquiries(20)

    _run(_ctx(pks))
    first = {
        e.pk: e.assigned_to_id
        for e in Enquiry.objects.filter(pk__in=pks, assigned_to__isnull=False)
    }
    # Reset and run again: identical pk list -> identical selection + owners.
    Enquiry.objects.filter(pk__in=pks).update(assigned_to=None)
    _run(_ctx(pks))
    second = {
        e.pk: e.assigned_to_id
        for e in Enquiry.objects.filter(pk__in=pks, assigned_to__isnull=False)
    }
    assert first == second


def test_does_not_perturb_the_shared_ctx_rng() -> None:
    # The stage must draw from its own RNG so it never shifts ctx.rng for any
    # stage the runner sequences after it (determinism guard).
    _sales_users(2)
    pks = _make_enquiries(10)
    ctx = _ctx(pks)
    before = ctx.rng.getstate()

    _run(ctx)

    assert ctx.rng.getstate() == before
