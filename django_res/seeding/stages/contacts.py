"""Extra PropertyContactAssignment rows per property (non-owner roles).

`PropertyFactory(with_owner_contact=True)` already wires an Owner contact
onto the finance row. This stage layers in housekeeper / manager / agent
assignments so dev/staging contact tabs show more than the single owner, and
links each seeded AGENT to a seeded agency (from the `companies` stage) so the
contact→agency filter and the org-detail "agents" list have data.

Constraint: `unique_active_role_assignment(property, contact, role)` is
enforced on rows with `end_date IS NULL`. Because each call mints a fresh
Person, there is no collision.
"""

from __future__ import annotations

from accounts.enums import ContactRole, OrgStatus, OrgType
from accounts.factories import PersonFactory
from properties.factories import PropertyContactAssignmentFactory
from seeding.context import SeedContext
from seeding.registry import Stage, register

# Non-owner roles. Owner is already wired via PropertyFactory's owner-contact
# branch, and rotating it here would double-up that role.
_ROLES = [
    ContactRole.HOUSEKEEPER,
    ContactRole.MANAGER,
    ContactRole.AGENT,
    ContactRole.OWNERS_REPRESENTATIVE,
]


def _run(ctx: SeedContext) -> int:
    low, high = ctx.knobs.pct_per_property
    if high <= 0:
        return 0
    if not ctx.properties:
        return 0
    # Link seeded AGENT contacts to a seeded agency so the contact→agency filter
    # and the org-detail "agents" list have data. Round-robin (not rng) over the
    # ACTIVE agency-typed orgs the `companies` stage minted — deterministic and,
    # unlike a ctx.rng draw, it can't perturb the seed-tuned streams. INACTIVE
    # agencies are excluded so the deactivated cohort stays agent-free (its whole
    # point is to demo the status filter as retired).
    agencies = [
        o
        for o in ctx.organisations
        if o.org_type == OrgType.AGENCY and o.status == OrgStatus.ACTIVE
    ]
    agent_seq = 0
    made = 0
    for prop in ctx.properties:
        n = min(ctx.rng.randint(low, high), len(_ROLES))
        roles = ctx.rng.sample(_ROLES, k=n)
        for role in roles:
            if role == ContactRole.AGENT and agencies:
                contact = PersonFactory(agency=agencies[agent_seq % len(agencies)])
                agent_seq += 1
            else:
                contact = PersonFactory()
            PropertyContactAssignmentFactory(
                property=prop,
                contact=contact,
                role=role,
            )
            made += 1
    return made


register(Stage(name="contacts", run=_run, depends_on=("properties", "companies")))
