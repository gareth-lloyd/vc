"""Seed staff users (one Contact + email/phone per user).

Also ensures two well-known superusers exist on every run so a developer can
log in without hunting through generated rows. These are upserted by email
(password is reset each run) and are independent of the per-run batch.
"""

from __future__ import annotations

from accounts.enums import StaffRole
from accounts.factories import ContactEmailFactory, ContactPhoneFactory, UserFactory
from accounts.models import User
from core.seed.context import SeedContext
from core.seed.registry import Stage, register

# (email, password, first_name, last_name) for the always-on dev superusers.
_SUPERUSERS: tuple[tuple[str, str, str, str], ...] = (
    ("glloyd@gmail.com", "fiery-kite-pumpkin-eton", "Gareth", "Lloyd"),
    ("nick@villacollective.com", "purple-octagon-ferry-palace", "Nick", "Villa"),
)


def _ensure_superuser(email: str, password: str, first_name: str, last_name: str) -> int:
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            "first_name": first_name,
            "last_name": last_name,
            "is_staff": True,
            "is_superuser": True,
            "role": StaffRole.ADMIN,
        },
    )
    user.first_name = first_name
    user.last_name = last_name
    user.is_staff = True
    user.is_superuser = True
    user.role = StaffRole.ADMIN
    user.set_password(password)
    user.save()
    return int(created)


def _run(ctx: SeedContext) -> int:
    made = 0
    for email, password, first_name, last_name in _SUPERUSERS:
        made += _ensure_superuser(email, password, first_name, last_name)

    for _ in range(ctx.n_users):
        contact = ContactEmailFactory().contact
        ContactPhoneFactory(contact=contact)
        UserFactory()
        made += 1
    return made


register(Stage(name="users", run=_run))
