"""factory-boy factories for the `owners` app."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from accounts.factories import UserFactory
from core.factories import RUN_TOKEN
from owners import models
from owners.enums import OwnerMembershipStatus, OwnerRole
from properties.factories import PropertyFactory


class OwnerOrganisationFactory(DjangoModelFactory):
    class Meta:
        model = models.OwnerOrganisation

    name = factory.Sequence(lambda n: f"Owner Org {RUN_TOKEN}-{n}")


class OwnerMembershipFactory(DjangoModelFactory):
    class Meta:
        model = models.OwnerMembership

    organisation = factory.SubFactory(OwnerOrganisationFactory)
    user = factory.SubFactory(UserFactory)
    role = OwnerRole.ADMIN
    status = OwnerMembershipStatus.ACTIVE


class OwnerOrgPropertyFactory(DjangoModelFactory):
    class Meta:
        model = models.OwnerOrgProperty

    organisation = factory.SubFactory(OwnerOrganisationFactory)
    property = factory.SubFactory(PropertyFactory)
    view_full_money = False
    view_guest_details = False
