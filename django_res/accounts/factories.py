"""factory-boy factories for the `accounts` app."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from accounts import models
from accounts.enums import (
    EmailLabel,
    OrgStatus,
    OrgType,
    PersonKind,
    PersonStatus,
    PhoneLabel,
)
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


class OrganisationFactory(DjangoModelFactory):
    class Meta:
        model = models.Organisation

    name = factory.Sequence(lambda n: f"Org {RUN_TOKEN}-{n}")
    org_type = OrgType.AGENCY
    status = OrgStatus.ACTIVE


class PersonFactory(DjangoModelFactory):
    class Meta:
        model = models.Person

    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    company = factory.Faker("company")
    status = PersonStatus.ACTIVE


class CustomerPersonFactory(PersonFactory):
    """A CUSTOMER `Person` that carries exactly one PRIMARY email + phone child.

    The drop-in replacement for the retired `reservations.GuestFactory`
    (GAP-045 D5-1): serializer / comms reads of a customer's email & phone go
    through `Person.primary_email()` / `primary_phone()`, which read the child
    rows, so a factory-built customer must have them — just as `GuestFactory`
    populated `Guest.email` / `Guest.phone`.

    Set a specific channel with `primary_email="x@y.com"` / `primary_phone=...`.
    Pass `primary_email=""` (empty string) to build a customer with NO email
    (likewise `primary_phone=""`); the Person model has no contactability
    constraint, unlike Guest. (factory-boy can't distinguish an omitted
    post-generation arg from an explicit `None`, so empty-string is the
    "suppress this channel" signal.)
    """

    class Meta:
        model = models.Person
        skip_postgeneration_save = True

    kind = PersonKind.CUSTOMER

    @factory.post_generation
    def primary_email(obj, create, extracted, **kwargs):  # type: ignore[no-untyped-def]
        if not create:
            return
        email = extracted if extracted is not None else f"customer-{RUN_TOKEN}-{obj.pk}@example.com"
        if email:
            PersonEmailFactory(contact=obj, email=email)

    @factory.post_generation
    def primary_phone(obj, create, extracted, **kwargs):  # type: ignore[no-untyped-def]
        if not create:
            return
        number = extracted if extracted is not None else f"+44 7700 9{obj.pk:05d} x{RUN_TOKEN}"
        if number:
            PersonPhoneFactory(contact=obj, number=number)


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
