"""The `companies` stage seeds a realistic pool of `accounts.Organisation`.

Pins the spread the Companies directory + status filter demos rely on: an
agency-dominant pool that always carries all three org_types and a couple
INACTIVE rows, with distinct names/emails. See `seeding/stages/companies.py`.
"""

from __future__ import annotations

import dataclasses
import random

import pytest

from accounts.enums import OrgStatus, OrgType
from accounts.models import Organisation
from seeding.context import _PROFILES, Profile, SeedContext
from seeding.stages.companies import _run

pytestmark = pytest.mark.django_db


def _ctx(profile: Profile) -> SeedContext:
    """A minimal context carrying just the profile knobs the stage reads."""
    return SeedContext(
        rng=random.Random(0),
        knobs=_PROFILES[profile],
        n_properties=0,
        n_bookings=0,
        n_users=0,
    )


def test_happy_seeds_a_populated_companies_pool() -> None:
    # A populated Companies screen is the deliverable, so happy is nonzero.
    ctx = _ctx(Profile.HAPPY)

    made = _run(ctx)

    assert made == 4
    assert len(ctx.organisations) == 4
    assert Organisation.objects.count() == 4
    # Even the smallest pool carries all three org_types.
    assert set(Organisation.objects.values_list("org_type", flat=True)) == {
        OrgType.AGENCY,
        OrgType.SUPPLIER,
        OrgType.MANAGEMENT_COMPANY,
    }


def test_mixed_seeds_agency_dominant_spread() -> None:
    ctx = _ctx(Profile.MIXED)

    made = _run(ctx)

    assert made == 8
    assert Organisation.objects.count() == 8

    counts = {
        t: Organisation.objects.filter(org_type=t).count()
        for t in (OrgType.AGENCY, OrgType.SUPPLIER, OrgType.MANAGEMENT_COMPANY)
    }
    # Every org_type screen has data, and agencies dominate the directory.
    assert all(c >= 1 for c in counts.values())
    assert counts[OrgType.AGENCY] > counts[OrgType.SUPPLIER]
    assert counts[OrgType.AGENCY] > counts[OrgType.MANAGEMENT_COMPANY]


def test_status_spread_has_active_majority_and_some_inactive() -> None:
    # The status filter needs a dominant ACTIVE cohort AND ≥1 INACTIVE to demo;
    # a probabilistic draw could silently produce zero INACTIVE, so the stage
    # guarantees the spread deterministically.
    ctx = _ctx(Profile.MIXED)

    _run(ctx)

    active = Organisation.objects.filter(status=OrgStatus.ACTIVE).count()
    inactive = Organisation.objects.filter(status=OrgStatus.INACTIVE).count()
    assert inactive >= 1
    assert active > inactive


def test_names_and_emails_are_distinct() -> None:
    # Distinct names/emails (RUN_TOKEN-folded) so an additive reseed in a fresh
    # process never renders duplicate directory rows or collides on email.
    ctx = _ctx(Profile.CHAOS)

    _run(ctx)

    names = list(Organisation.objects.values_list("name", flat=True))
    emails = list(Organisation.objects.values_list("email", flat=True))
    assert len(set(names)) == len(names) == 14
    assert len(set(emails)) == len(emails) == 14
    urls = Organisation.objects.values_list("website_url", flat=True)
    assert all(url.startswith("https://") for url in urls)


def test_zero_knob_seeds_nothing() -> None:
    ctx = _ctx(Profile.HAPPY)
    # Force the knob off without mutating the shared frozen singleton.
    ctx.knobs = dataclasses.replace(ctx.knobs, n_organisations=0)

    made = _run(ctx)

    assert made == 0
    assert ctx.organisations == []
    assert Organisation.objects.count() == 0


def test_stage_does_not_perturb_shared_rng() -> None:
    """The stage is index-driven and must never draw from `ctx.rng`, so the
    shared deterministic stream downstream stages depend on is untouched."""
    ctx = _ctx(Profile.MIXED)
    before = ctx.rng.getstate()

    _run(ctx)

    assert ctx.rng.getstate() == before
