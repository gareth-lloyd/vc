"""factory-boy factories for the `properties` app.

These double as the canonical test-data builders and as the building blocks
the `seed_dev` management command composes. Faker drives realistic values;
unique fields combine a per-run `RUN_TOKEN` with a `factory.Sequence` so
additive seed runs never collide on a unique constraint (slug, name).

`CountryFactory` / `PropertyCategoryFactory` use `django_get_or_create` so
they reuse the rows pre-seeded by migrations instead of fighting unique
constraints.
"""

from __future__ import annotations

import io
import random
from decimal import Decimal
from typing import cast
from uuid import uuid4

import factory
from django.core.files.base import ContentFile
from factory.django import DjangoModelFactory
from faker import Faker
from PIL import Image

from properties import models
from properties.enums import (
    CommissionCalcType,
    DescriptionSection,
    FeatureServiceType,
    ImageKind,
    PropertyChannel,
    PropertyStatus,
    RoomPlacement,
)

# Villa-rental markets. Every iso2 here is in the 249-row ISO-3166 seed
# (`properties.0009`), so `django_get_or_create=("iso2",)` resolves to the
# seeded row and the iso3/name defaults below are only a safety net.
_VILLA_COUNTRIES = [
    ("GB", "GBR", "United Kingdom"),
    ("FR", "FRA", "France"),
    ("ES", "ESP", "Spain"),
    ("IT", "ITA", "Italy"),
    ("GR", "GRC", "Greece"),
    ("PT", "PRT", "Portugal"),
]

_CATEGORIES = [
    ("Villa", "villa"),
    ("Apartment", "apartment"),
    ("Chalet", "chalet"),
    ("Townhouse", "townhouse"),
]

_faker = Faker("en_GB")

# `factory.Sequence` is an in-process counter — it restarts at 0 every
# command invocation, so a bare `f"villa-{n}"` collides with rows a previous
# run already wrote. A per-process token keeps additive re-runs unique while
# in-process builds stay unique via `n`. Exported for sibling factory modules.
RUN_TOKEN = uuid4().hex[:8]


def _tiny_png() -> ContentFile:
    """A 1x1 PNG so `PropertyImage.image` (a required ImageField) is valid
    without shipping fixture binaries."""
    buf = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buf, format="PNG")
    return ContentFile(buf.getvalue(), name="seed.png")


class CountryFactory(DjangoModelFactory):
    class Meta:
        model = models.Country
        django_get_or_create = ("iso2",)

    class Params:
        spec = factory.Iterator(_VILLA_COUNTRIES)

    iso2 = factory.LazyAttribute(lambda o: o.spec[0])
    iso3 = factory.LazyAttribute(lambda o: o.spec[1])
    name = factory.LazyAttribute(lambda o: o.spec[2])


class RegionFactory(DjangoModelFactory):
    class Meta:
        model = models.Region

    country = factory.SubFactory(CountryFactory)
    name = factory.Faker("city")
    slug = factory.Sequence(lambda n: f"region-{RUN_TOKEN}-{n}")


class PropertyCategoryFactory(DjangoModelFactory):
    class Meta:
        model = models.PropertyCategory
        django_get_or_create = ("slug",)

    class Params:
        spec = factory.Iterator(_CATEGORIES)

    name = factory.LazyAttribute(lambda o: o.spec[0])
    slug = factory.LazyAttribute(lambda o: o.spec[1])


class PropertyGroupFactory(DjangoModelFactory):
    class Meta:
        model = models.PropertyGroup

    # `properties.signals` auto-creates GroupSettings + GroupFinance on insert
    # (the rows `PropertySettings.effective()` / `PropertyFinance.effective()`
    # fall back to), so the factory must not create them again.
    name = factory.Sequence(lambda n: f"Portfolio {RUN_TOKEN}-{n}")


class FeatureCategoryFactory(DjangoModelFactory):
    class Meta:
        model = models.FeatureCategory
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Feature group {RUN_TOKEN}-{n}")
    slug = factory.Sequence(lambda n: f"feature-group-{RUN_TOKEN}-{n}")


class FeatureFactory(DjangoModelFactory):
    class Meta:
        model = models.Feature

    category = factory.SubFactory(FeatureCategoryFactory)
    name = factory.Faker("word")
    slug = factory.Sequence(lambda n: f"feature-{RUN_TOKEN}-{n}")
    service_type = FeatureServiceType.AMENITY


class PropertyFactory(DjangoModelFactory):
    class Meta:
        model = models.Property
        skip_postgeneration_save = True

    name = factory.Faker("street_name")
    display_name = factory.LazyAttribute(lambda o: f"Villa {o.name}")
    slug = factory.Sequence(lambda n: f"villa-{RUN_TOKEN}-{n}")
    status = PropertyStatus.ACTIVE
    channel = PropertyChannel.DIRECT
    category = factory.SubFactory(PropertyCategoryFactory)
    group = factory.SubFactory(PropertyGroupFactory)
    region = factory.SubFactory(RegionFactory)

    @factory.post_generation
    def children(obj: models.Property, create: bool, extracted: object, **kwargs: object) -> None:
        if not create:
            return
        models.PropertyLocation.objects.create(
            property=obj,
            country=obj.region.country,
            address_line_1=_faker.street_address(),
            locality_town=obj.region.name,
            post_code=_faker.postcode(),
        )
        models.PropertyCapacity.objects.create(
            property=obj,
            guests=8,
            bedrooms=4,
            bathrooms=3,
            ensuites=2,
        )
        # All-null PropertySettings/PropertyFinance => inherit from the group.
        models.PropertySettings.objects.create(property=obj)
        models.PropertyFinance.objects.create(property=obj)
        models.PropertyDescription.objects.create(
            property=obj,
            section=DescriptionSection.OVERVIEW,
            body=_faker.paragraph(),
        )
        models.PropertyImage.objects.create(
            property=obj,
            image=_tiny_png(),
            kind=ImageKind.HERO,
            name="Hero",
        )

    @factory.post_generation
    def with_owner_contact(
        obj: models.Property,
        create: bool,
        extracted: object,
        **kwargs: object,
    ) -> None:
        """Opt-in: attach a Contact + commission terms to the finance row.

        Default off (preserves legacy "all-null finance, inherit from group"
        shape). Set to True via ``PropertyFactory(with_owner_contact=True)`` —
        the seeded Contact gets a primary `ContactEmail` and `ContactPhone`,
        and the finance row gets a mix of percent / fixed commission so the
        Owner tab renders both branches in dev/staging.
        """
        if not create or not extracted:
            return
        # Local imports: `accounts.factories` already imports from us, and
        # the `accounts` models live in a different app graph.
        from accounts.factories import (
            ContactEmailFactory,
            ContactFactory,
            ContactPhoneFactory,
        )
        from accounts.models import Contact

        # `get_or_create` rather than `obj.finance` removes the implicit
        # dependency on the sibling `children` post_generation hook having
        # already created the PropertyFinance row.
        finance, _ = models.PropertyFinance.objects.get_or_create(property=obj)
        contact = cast(
            Contact,
            ContactFactory(address_line_1=_faker.street_address(), address_line_2=""),
        )
        # Pin `is_primary` explicitly so a future change to the email/phone
        # factory default doesn't silently break the Owner-tab serializer,
        # which reads the primary row.
        ContactEmailFactory(contact=contact, is_primary=True)
        ContactPhoneFactory(contact=contact, is_primary=True)
        finance.contact = contact
        # Mix percent / fixed so the Owner tab renders both formatter branches.
        if random.random() < 0.7:
            finance.commission_calculation_type = CommissionCalcType.PERCENT.value
            finance.commission_amount = Decimal("12.50")
        else:
            finance.commission_calculation_type = CommissionCalcType.FIXED.value
            finance.commission_amount = Decimal("500.00")
        finance.commission_note = "Owner agreed terms"
        finance.save(
            update_fields=[
                "contact",
                "commission_calculation_type",
                "commission_amount",
                "commission_note",
                "updated_at",
            ]
        )


class RoomFactory(DjangoModelFactory):
    class Meta:
        model = models.Room
        skip_postgeneration_save = True

    property = factory.SubFactory(PropertyFactory)
    name = factory.Sequence(lambda n: f"Bedroom {n}")
    placement = RoomPlacement.MAIN_HOUSE

    @factory.post_generation
    def beds(obj: models.Room, create: bool, extracted: object, **kwargs: object) -> None:
        if create:
            models.RoomBeds.objects.create(room=obj, double=1)
