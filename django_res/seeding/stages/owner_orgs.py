"""Owner-portal demo fixture — Kostas Hospitality Ltd (mockup Appendix A).

Builds one loginable owner persona so the `/owner/*` portal has real data in
dev/staging:

  * an `OwnerOrganisation` "Kostas Hospitality Ltd",
  * an ACTIVE ADMIN `OwnerMembership` for andreas.kostas@example.com
    (password `seed-password`), a non-staff owner-only login,
  * `OwnerOrgProperty` grants over the first few seeded villas, with the first
    villa fully visible (view_full_money + view_guest_details) and the rest
    hidden — so every redaction state is demoable.

Idempotent + additive: every write is a `get_or_create`, so reruns reuse the
same org / membership / grants rather than duplicating them.
"""

from __future__ import annotations

from accounts.models import User
from core.enums import StaffRole
from owners.enums import OwnerMembershipStatus, OwnerRole
from owners.models import OwnerMembership, OwnerOrganisation, OwnerOrgProperty
from seeding.context import SeedContext
from seeding.registry import Stage, register

_OWNER_EMAIL = "andreas.kostas@example.com"
_OWNER_PASSWORD = "seed-password"
_ORG_NAME = "Kostas Hospitality Ltd"
_VILLA_NAMES = ["Villa Anemoi", "Villa Petalon", "Villa Ariadne", "Villa Selene"]


def _run(ctx: SeedContext) -> int:
    if not ctx.properties:
        return 0

    made = 0

    user, user_created = User.objects.get_or_create(
        email=_OWNER_EMAIL,
        defaults={
            "first_name": "Andreas",
            "last_name": "Kostas",
            "is_staff": False,
            "role": StaffRole.VIEWER,
        },
    )
    if user_created:
        user.set_password(_OWNER_PASSWORD)
        user.save(update_fields=["password"])
        made += 1

    org, org_created = OwnerOrganisation.objects.get_or_create(name=_ORG_NAME)
    if org_created:
        made += 1

    _, membership_created = OwnerMembership.objects.get_or_create(
        organisation=org,
        user=user,
        defaults={"role": OwnerRole.ADMIN, "status": OwnerMembershipStatus.ACTIVE},
    )
    if membership_created:
        made += 1

    for index, prop in enumerate(ctx.properties[: len(_VILLA_NAMES)]):
        fully_visible = index == 0
        _, grant_created = OwnerOrgProperty.objects.get_or_create(
            organisation=org,
            property=prop,
            end_date=None,
            defaults={
                "view_full_money": fully_visible,
                "view_guest_details": fully_visible,
            },
        )
        if grant_created:
            made += 1
        # Cosmetic: give the demo villas the mockup names (Appendix A).
        name = _VILLA_NAMES[index]
        if prop.display_name != name:
            prop.display_name = name
            prop.save(update_fields=["display_name"])

    return made


register(Stage(name="owner_orgs", run=_run, depends_on=("properties", "bookings")))
