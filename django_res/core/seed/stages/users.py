"""Seed staff users (one Contact + email/phone per user)."""

from __future__ import annotations

from accounts.factories import ContactEmailFactory, ContactPhoneFactory, UserFactory
from core.seed.context import SeedContext
from core.seed.registry import Stage, register


def _run(ctx: SeedContext) -> int:
    for _ in range(ctx.n_users):
        contact = ContactEmailFactory().contact
        ContactPhoneFactory(contact=contact)
        UserFactory()
    return ctx.n_users


register(Stage(name="users", run=_run))
