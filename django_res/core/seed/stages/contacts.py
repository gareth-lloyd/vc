"""Extra PropertyContactAssignment rows per property (non-owner roles).

`PropertyFactory(with_owner_contact=True)` already wires an Owner contact
onto the finance row. This stage layers in housekeeper / manager / agent
assignments so dev/staging contact tabs show more than the single owner.

Constraint: `unique_active_role_assignment(property, contact, role)` is
enforced on rows with `end_date IS NULL`. Because each call mints a fresh
Contact, there is no collision.
"""

from __future__ import annotations

from accounts.enums import ContactRole
from accounts.factories import ContactFactory
from core.seed.context import SeedContext
from core.seed.registry import Stage, register
from properties.factories import PropertyContactAssignmentFactory

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
    made = 0
    for prop in ctx.properties:
        n = min(ctx.rng.randint(low, high), len(_ROLES))
        roles = ctx.rng.sample(_ROLES, k=n)
        for role in roles:
            contact = ContactFactory()
            PropertyContactAssignmentFactory(
                property=prop,
                contact=contact,
                role=role,
            )
            made += 1
    return made


register(Stage(name="contacts", run=_run, depends_on=("properties",)))
