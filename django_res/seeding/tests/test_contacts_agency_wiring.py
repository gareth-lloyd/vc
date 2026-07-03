"""The `contacts` stage links seeded AGENT contacts to a seeded agency, so the
contact→agency filter and the org-detail "agents" list have data.

Pairs with the `companies` stage (which populates `ctx.organisations`); the
agency pick is deterministic round-robin over agency-typed orgs — it must not
draw from `ctx.rng`, so the seed-tuned streams stay byte-identical.
"""

from __future__ import annotations

import dataclasses
import random

import pytest

from accounts.enums import ContactRole, OrgStatus, OrgType
from accounts.models import Organisation
from properties.factories import PropertyFactory
from properties.models import PropertyContactAssignment
from seeding.context import _PROFILES, Profile, SeedContext
from seeding.stages import companies, contacts

pytestmark = pytest.mark.django_db


def _ctx_with_properties(n_props: int) -> SeedContext:
    # pct_per_property=(4,4): every property gets all four non-owner roles, so an
    # AGENT contact is guaranteed on each — no reliance on a lucky rng sample.
    ctx = SeedContext(
        rng=random.Random(0),
        knobs=dataclasses.replace(_PROFILES[Profile.MIXED], pct_per_property=(4, 4)),
        n_properties=0,
        n_bookings=0,
        n_users=0,
    )
    ctx.properties = [PropertyFactory() for _ in range(n_props)]
    return ctx


def test_agent_contacts_are_linked_to_agencies() -> None:
    ctx = _ctx_with_properties(3)
    companies._run(ctx)

    contacts._run(ctx)

    agent_links = PropertyContactAssignment.objects.filter(role=ContactRole.AGENT)
    assert agent_links.exists()
    # Every seeded agent carries an agency; always an ACTIVE AGENCY org (a
    # deactivated agency must stay agent-free so it reads as retired).
    for link in agent_links.select_related("contact__agency"):
        assert link.contact is not None
        assert link.contact.agency is not None
        assert link.contact.agency.org_type == OrgType.AGENCY
        assert link.contact.agency.status == OrgStatus.ACTIVE
    # At least one org actually surfaces agents (org-detail "agents" list).
    assert Organisation.objects.filter(agents__isnull=False).exists()


def test_non_agent_contacts_have_no_agency() -> None:
    ctx = _ctx_with_properties(3)
    companies._run(ctx)

    contacts._run(ctx)

    non_agents = PropertyContactAssignment.objects.exclude(role=ContactRole.AGENT)
    assert non_agents.exists()
    agency_ids = non_agents.values_list("contact__agency_id", flat=True)
    assert all(agency_id is None for agency_id in agency_ids)


def test_agency_pick_adds_no_ctx_rng_draw() -> None:
    # contacts draws role counts/samples from ctx.rng; the agency pick must add
    # nothing on top. Two runs from an identical rng state — one with agencies to
    # assign, one without — must advance ctx.rng identically, proving the
    # round-robin pick is rng-free (so the seed-tuned streams stay byte-identical).
    ctx_with = _ctx_with_properties(3)
    companies._run(ctx_with)
    ctx_without = _ctx_with_properties(3)  # organisations left empty

    start = ctx_with.rng.getstate()
    ctx_without.rng.setstate(start)

    contacts._run(ctx_with)
    contacts._run(ctx_without)

    assert ctx_with.rng.getstate() == ctx_without.rng.getstate()
