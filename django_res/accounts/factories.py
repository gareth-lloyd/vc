"""factory-boy factories for the `accounts` app."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from accounts import models
from accounts.enums import EmailLabel, PersonStatus, PhoneLabel
from core.enums import StaffRole
from core.factories import RUN_TOKEN


class UserFactory(DjangoModelFactory):
    class Meta:
        model = models.User
        django_get_or_create = ("email",)
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"staff-{RUN_TOKEN}-{n}@villacollective.test")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    # Spread across the operator roles so permission-gated UI looks realistic.
    role = factory.Iterator(
        [StaffRole.ADMIN, StaffRole.RESERVATIONS, StaffRole.ACCOUNTS, StaffRole.VIEWER]
    )
    is_staff = True
    password = factory.PostGenerationMethodCall("set_password", "seed-password")


class PersonFactory(DjangoModelFactory):
    class Meta:
        model = models.Person

    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    company = factory.Faker("company")
    status = PersonStatus.ACTIVE


class PersonEmailFactory(DjangoModelFactory):
    class Meta:
        model = models.PersonEmail

    contact = factory.SubFactory(PersonFactory)
    email = factory.Sequence(lambda n: f"contact-{RUN_TOKEN}-{n}@example.com")
    label = EmailLabel.PRIMARY
    is_primary = True


class PersonPhoneFactory(DjangoModelFactory):
    class Meta:
        model = models.PersonPhone

    contact = factory.SubFactory(PersonFactory)
    number = factory.Sequence(lambda n: f"+44 7700 9{n:05d} x{RUN_TOKEN}")
    label = PhoneLabel.MOBILE
    is_primary = True
