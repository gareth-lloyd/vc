"""Tests for the villa Zoho Flow push (GAP-082 Unit 3).

`properties.Property` is registered by `properties.apps.ready()`; these tests
NEVER unregister it (xdist worker leak) — behaviour is toggled via
`override_settings(ZOHO_FLOW_WEBHOOKS=…)` only.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any, cast
from unittest import mock

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from accounts.enums import ContactRole, OrgType
from accounts.factories import OrganisationFactory, PersonFactory, UserFactory
from accounts.models import Organisation, Person, User
from core.tests import assert_max_queries
from integrations import tasks
from integrations.enums import SyncProvider, SyncStatus
from integrations.models import SyncRecord
from integrations.services.zoho_flow import get_zoho_spec, suppress_zoho_push
from pricing.enums import ExtraCalc, ExtraKind
from pricing.factories import CurrencyFactory, ExtraFactory
from pricing.models import Extra
from properties.enums import BedSize, DescriptionSection, PropertyStatus
from properties.factories import (
    FeatureCategoryFactory,
    FeatureFactory,
    PropertyContactAssignmentFactory,
    PropertyFactory,
    RegionFactory,
    RoomAttributeFactory,
    RoomFactory,
)
from properties.models.contacts import PropertyContactAssignment
from properties.models.descriptions import PropertyDescription
from properties.models.features import Feature, PropertyFeature
from properties.models.geo import Region
from properties.models.location import PropertyLocation
from properties.models.property import Property
from properties.models.rooms import Room, RoomAttribute, RoomAttributeAssignment
from properties.other_information_catalog import OTHER_INFORMATION_CATEGORY_SLUG
from properties.services.availability import PropertyAvailabilityService
from properties.services.zoho_payload import build_property_payload

VILLA_URL = "https://flow.zoho.example/villa"
WEBHOOKS = {"contact": "", "villa": VILLA_URL, "enquiry": "", "quote": "", "booking": ""}

pytestmark = pytest.mark.django_db


def _property(**kwargs: Any) -> Property:
    return cast(Property, PropertyFactory(**kwargs))


def _assignment(**kwargs: Any) -> PropertyContactAssignment:
    return cast(PropertyContactAssignment, PropertyContactAssignmentFactory(**kwargs))


def _feature(**kwargs: Any) -> Feature:
    return cast(Feature, FeatureFactory(**kwargs))


def _bare_property() -> Property:
    """A Property WITHOUT the factory's child rows (location/capacity/image)."""
    return Property.objects.create(
        name="Bare Villa",
        display_name="Bare Villa",
        slug=f"bare-villa-{uuid.uuid4().hex[:8]}",
        region=cast(Region, RegionFactory()),
    )


@pytest.fixture
def villa_webhook() -> Iterator[None]:
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        yield


@pytest.fixture
def delay_mock(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    m = mock.Mock()
    monkeypatch.setattr(tasks.push_sync_record, "delay", m)
    return m


def _property_ct() -> ContentType:
    return ContentType.objects.get_for_model(Property)


def _record_for(prop: Property) -> SyncRecord:
    return SyncRecord.objects.get(
        content_type=_property_ct(),
        object_id=prop.pk,
        provider=SyncProvider.ZOHO_CRM.value,
    )


def _mark_in_sync(record: SyncRecord) -> None:
    record.status = SyncStatus.IN_SYNC.value
    record.save(update_fields=["status", "updated_at"])


# --- registration ---------------------------------------------------------


def test_property_is_registered_by_app_ready() -> None:
    spec = get_zoho_spec(Property)
    assert spec is not None
    assert spec.kind == "villa"
    assert spec.auto_push is True
    assert spec.ignore_update_fields == frozenset(
        {
            "availability_owner_updated_at",
            "availability_confirmed_at",
            "availability_confirmed_by",
        }
    )


# --- payload: identity / region / location / capacity ---------------------


def test_payload_identity_and_region() -> None:
    prop = _property(legacy_id="villa-42", licence_number="LIC-9")

    payload = build_property_payload(prop)

    assert payload["RES_ID"] == prop.pk
    assert payload["id"] == prop.pk
    assert payload["name"] == prop.name
    assert payload["display_name"] == prop.display_name
    assert payload["slug"] == prop.slug
    assert payload["legacy_id"] == "villa-42"
    assert payload["licence_number"] == "LIC-9"
    assert payload["video_url"] == ""
    assert payload["status"] == prop.status
    assert payload["channel"] == prop.channel
    region = payload["region"]
    assert region["RES_ID"] == prop.region.pk
    assert region["name"] == prop.region.name
    assert region["country"]["iso2"] == prop.region.country.iso2
    assert payload["created_at"] == prop.created_at.isoformat()
    assert payload["updated_at"] == prop.updated_at.isoformat()


def test_payload_region_and_country_carry_join_keys() -> None:
    """GAP-102: geo sub-objects are keyable — region `slug` + `is_active`,
    country `iso3` + `is_active` — so Limitless stop matching on `name`.
    Covered per-module because `_region_payload` is deliberately duplicated
    in `reservations.services.zoho_payload`."""
    prop = _property(region__is_active=False)
    region = prop.region
    # CountryFactory get_or_creates on iso2 (migration-seeded rows), so the
    # flag has to be flipped on the row rather than passed as a kwarg.
    region.country.is_active = False
    region.country.save(update_fields=["is_active"])

    payload = build_property_payload(prop)

    assert payload["region"] == {
        "RES_ID": region.pk,
        "id": region.pk,
        "name": region.name,
        "slug": region.slug,
        "is_active": False,
        "country": {
            "RES_ID": region.country.pk,
            "id": region.country.pk,
            "name": region.country.name,
            "iso2": region.country.iso2,
            "iso3": region.country.iso3,
            "is_active": False,
        },
    }


def test_payload_location_and_capacity_decimals_as_strings() -> None:
    prop = _property()
    location = prop.location
    location.latitude = Decimal("38.123456")
    location.longitude = Decimal("-9.654321")
    location.save()
    capacity = prop.capacity
    capacity.size_sqm = Decimal("420.50")
    capacity.save()

    payload = build_property_payload(prop)

    loc = payload["location"]
    assert loc["address_line_1"] == location.address_line_1
    assert loc["address_line_2"] == location.address_line_2
    assert loc["address_line_3"] == location.address_line_3
    assert loc["post_code"] == location.post_code
    assert loc["locality_town"] == location.locality_town
    assert loc["locality_region"] == location.locality_region
    assert loc["country"] == {
        "RES_ID": location.country.pk,
        "id": location.country.pk,
        "name": location.country.name,
        "iso2": location.country.iso2,
        "iso3": location.country.iso3,
        "is_active": True,
    }
    assert loc["latitude"] == "38.123456"
    assert loc["longitude"] == "-9.654321"
    assert loc["timezone"] == location.timezone
    cap = payload["capacity"]
    assert cap == {
        "guests": 8,
        "additional_guests": 0,
        "bedrooms": 4,
        "ensuites": 2,
        "bathrooms": 3,
        "size_sqm": "420.50",
    }


def test_payload_null_coordinates_and_size() -> None:
    prop = _property()  # factory leaves latitude/longitude/size_sqm unset

    payload = build_property_payload(prop)

    assert payload["location"]["latitude"] is None
    assert payload["location"]["longitude"] is None
    assert payload["capacity"]["size_sqm"] is None


def test_payload_location_capacity_none_when_child_rows_absent() -> None:
    prop = _bare_property()

    payload = build_property_payload(prop)

    assert payload["location"] is None
    assert payload["capacity"] is None
    assert payload["hero_image_url"] is None


# --- payload: contacts ----------------------------------------------------


def test_payload_contacts_person_and_organisation() -> None:
    prop = _property()
    owner = cast(Person, PersonFactory(first_name="Ada", last_name="Lovelace"))
    assignment = _assignment(
        property=prop,
        contact=owner,
        role=ContactRole.OWNER,
        is_primary=True,
        start_date=date(2024, 1, 1),
    )
    org = cast(
        Organisation,
        OrganisationFactory(
            name="Villa Ops Ltd",
            org_type=OrgType.MANAGEMENT_COMPANY,
            email="ops@example.com",
            phone="+35112345678",
        ),
    )
    ended = _assignment(
        property=prop,
        contact=None,
        organisation=org,
        role=ContactRole.MANAGEMENT_COMPANY,
        start_date=date(2020, 1, 1),
        end_date=date(2023, 12, 31),
    )

    payload = build_property_payload(prop)

    contacts = {c["role"]: c for c in payload["contacts"]}
    assert set(contacts) == {ContactRole.OWNER.value, ContactRole.MANAGEMENT_COMPANY.value}
    owner_row = contacts[ContactRole.OWNER.value]
    assert owner_row["RES_ID"] == assignment.pk
    assert owner_row["id"] == assignment.pk
    assert owner_row["is_primary"] is True
    assert owner_row["start_date"] == "2024-01-01"
    assert owner_row["end_date"] is None
    assert owner_row["organisation"] is None
    assert owner_row["person"]["RES_ID"] == owner.pk
    assert owner_row["person"]["full_name"] == "Ada Lovelace"
    # Ended assignments stay in the payload (lifecycle rows are never hidden).
    org_row = contacts[ContactRole.MANAGEMENT_COMPANY.value]
    assert org_row["RES_ID"] == ended.pk
    assert org_row["end_date"] == "2023-12-31"
    assert org_row["person"] is None
    assert org_row["organisation"] == {
        "RES_ID": org.pk,
        "id": org.pk,
        "name": "Villa Ops Ltd",
        "org_type": OrgType.MANAGEMENT_COMPANY.value,
        "email": "ops@example.com",
        "phone": "+35112345678",
    }


def test_payload_anonymized_owner_fails_closed_to_none() -> None:
    prop = _property()
    owner = cast(Person, PersonFactory())
    PropertyContactAssignmentFactory(property=prop, contact=owner, role=ContactRole.OWNER)
    owner.anonymize()

    payload = build_property_payload(prop)

    # The villa record itself still builds; only the PII sub-object is dropped.
    (contact,) = payload["contacts"]
    assert contact["person"] is None
    assert contact["role"] == ContactRole.OWNER.value


# --- payload: rooms / beds / attributes -----------------------------------


def test_payload_rooms_beds_and_attributes() -> None:
    prop = _property()
    room = cast(Room, RoomFactory(property=prop, name="Master", sort_order=1))
    beds = room.beds
    beds.double_size = BedSize.SUPER_KING
    beds.save()
    attribute = cast(
        RoomAttribute, RoomAttributeFactory(name="Sea view", slug=f"sea-view-{prop.pk}")
    )
    link = RoomAttributeAssignment.objects.create(
        room=room, attribute=attribute, note="From the balcony only"
    )

    payload = build_property_payload(prop)

    (room_payload,) = payload["rooms"]
    assert room_payload["RES_ID"] == room.pk
    assert room_payload["id"] == room.pk
    assert room_payload["name"] == "Master"
    assert room_payload["placement"] == room.placement
    assert room_payload["floor"] == room.floor
    assert room_payload["placement_note"] == room.placement_note
    assert room_payload["is_ensuite"] is False
    assert room_payload["ensuite_type"] == ""
    assert room_payload["access"] == room.access
    assert room_payload["sort_order"] == 1
    assert room_payload["beds"] == {
        "double": 1,
        "double_size": beds.double_size,
        "twin_double": 0,
        "twin": 0,
        "single": 0,
        "bunk": 0,
        "sofa": 0,
        "childrens": 0,
    }
    assert room_payload["attributes"] == [
        {
            "RES_ID": link.pk,
            "id": link.pk,
            "slug": attribute.slug,
            "name": "Sea view",
            "note": "From the balcony only",
        }
    ]


def test_payload_room_without_beds_row() -> None:
    prop = _bare_property()
    Room.objects.create(property=prop, name="Annexe")

    payload = build_property_payload(prop)

    (room_payload,) = payload["rooms"]
    assert room_payload["beds"] is None
    assert room_payload["attributes"] == []


# --- payload: features ----------------------------------------------------


def test_payload_features_per_villa_order_and_is_derived() -> None:
    prop = _property()
    pool = _feature(name="Pool")
    wifi = _feature(name="WiFi")
    # Insertion order deliberately opposes sort_order — per-villa order wins.
    wifi_link = PropertyFeature.objects.create(
        property=prop, feature=wifi, sort_order=2, is_derived=True
    )
    pool_link = PropertyFeature.objects.create(property=prop, feature=pool, sort_order=1)

    payload = build_property_payload(prop)

    assert payload["features"] == [
        {
            "RES_ID": pool_link.pk,
            "id": pool_link.pk,
            "feature_id": pool.pk,
            "name": "Pool",
            "slug": pool.slug,
            "category": pool.category.name,
            "service_type": pool.service_type,
            "sort_order": 1,
            "is_derived": False,
        },
        {
            "RES_ID": wifi_link.pk,
            "id": wifi_link.pk,
            "feature_id": wifi.pk,
            "name": "WiFi",
            "slug": wifi.slug,
            "category": wifi.category.name,
            "service_type": wifi.service_type,
            "sort_order": 2,
            "is_derived": True,
        },
    ]


def _other_information_category() -> Any:
    return FeatureCategoryFactory(slug=OTHER_INFORMATION_CATEGORY_SLUG, name="Other Information")


def test_payload_other_information_block_and_features_exclusion() -> None:
    """GAP-091: other-information tags ride their own block (ordered, same row
    shape as `features[]`) and are EXCLUDED from `features[]` — WordPress
    facets on the block, and a tag in both would double-render."""
    prop = _property()
    tags_category = _other_information_category()
    pets = _feature(name="Pets allowed", category=tags_category)
    no_smoking = _feature(name="No smoking indoors", category=tags_category)
    pool = _feature(name="Pool")
    # Legacy MappingOrder is per-category, so loaded villas interleave.
    pool_link = PropertyFeature.objects.create(property=prop, feature=pool, sort_order=2)
    smoking_link = PropertyFeature.objects.create(
        property=prop, feature=no_smoking, sort_order=3, is_derived=True
    )
    pets_link = PropertyFeature.objects.create(property=prop, feature=pets, sort_order=1)
    PropertyDescription.objects.create(
        property=prop,
        section=DescriptionSection.OTHER_INFORMATION,
        body="Licence 0829K. The pool cannot be heated.",
    )

    payload = build_property_payload(prop)

    assert payload["other_information"] == {
        "tags": [
            {
                "RES_ID": pets_link.pk,
                "id": pets_link.pk,
                "feature_id": pets.pk,
                "name": "Pets allowed",
                "slug": pets.slug,
                "category": "Other Information",
                "service_type": pets.service_type,
                "sort_order": 1,
                "is_derived": False,
            },
            {
                "RES_ID": smoking_link.pk,
                "id": smoking_link.pk,
                "feature_id": no_smoking.pk,
                "name": "No smoking indoors",
                "slug": no_smoking.slug,
                "category": "Other Information",
                "service_type": no_smoking.service_type,
                "sort_order": 3,
                "is_derived": True,
            },
        ],
        "description": "Licence 0829K. The pool cannot be heated.",
    }
    assert [f["RES_ID"] for f in payload["features"]] == [pool_link.pk]
    all_link_ids = [f["RES_ID"] for f in payload["features"]] + [
        t["RES_ID"] for t in payload["other_information"]["tags"]
    ]
    assert len(all_link_ids) == len(set(all_link_ids)) == 3


def test_payload_other_information_block_present_when_empty() -> None:
    prop = _property()
    PropertyFeature.objects.create(property=prop, feature=_feature())
    PropertyDescription.objects.create(
        property=prop, section=DescriptionSection.HOUSE_RULES, body="No parties"
    )

    payload = build_property_payload(prop)

    assert payload["other_information"] == {"tags": [], "description": ""}
    assert len(payload["features"]) == 1


# --- payload: hero image / JSON safety / omissions ------------------------


def test_payload_hero_image_url() -> None:
    prop = _property()  # factory attaches an active HERO image

    payload = build_property_payload(prop)

    assert payload["hero_image_url"] == prop.hero_image_url()
    assert payload["hero_image_url"] is not None


def _full_property() -> Property:
    """One of everything the payload embeds — rooms, features, contacts AND
    the GAP-102 extras catalogue — so whole-payload invariants (JSON-safety,
    key omissions, query count) see every branch."""
    prop = _property()
    prop.location.latitude = Decimal("38.1")
    prop.location.save()
    PropertyContactAssignmentFactory(property=prop, contact=PersonFactory(), role=ContactRole.OWNER)
    RoomFactory(property=prop)
    PropertyFeature.objects.create(property=prop, feature=_feature())
    ExtraFactory(property=prop)
    ExtraFactory(property=prop)
    return prop


def test_payload_is_json_serializable() -> None:
    json.dumps(build_property_payload(_full_property()))


def _all_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(key)
            keys |= _all_keys(nested)
    elif isinstance(value, list):
        for item in value:
            keys |= _all_keys(item)
    return keys


def test_payload_omits_villa_url_note_availability_and_pricing() -> None:
    """ZohoVillaPostData's Villa_URL/Note have no model source (documented
    omissions, never placeholders), and res stays the sole source of truth for
    availability + rates — none of it may ride the villa payload. The GAP-102
    extras catalogue is the one deliberate carve-out: its rows carry `amount`,
    never a `price*`/`availability*` key — the fixture attaches extras so
    this walk actually sees them."""
    prop = _full_property()

    payload = build_property_payload(prop)
    assert payload["extras"]
    keys = _all_keys(payload)

    assert "Villa_URL" not in keys
    assert "Note" not in keys
    # GAP-093: Property.category is gone and the key was dropped outright.
    # Top-level only — feature rows (category display names) and extras rows
    # (ExtraKind slugs) legitimately carry their own `category`, in two
    # different vocabularies.
    assert "category" not in payload
    assert not [k for k in keys if "availability" in k.lower()]
    assert not [k for k in keys if "price" in k.lower() or "pricing" in k.lower()]


# --- extras catalogue (GAP-102) -------------------------------------------


def test_payload_extras_catalogue_full_row_shape_and_order() -> None:
    """Option (a): the villa carries its own extras catalogue so Zoho has the
    product BEFORE any booking references it. Ordered by (sort_order, pk),
    inactive rows included (a historic booking's reference must resolve)."""
    prop = _property()
    eur = CurrencyFactory(code="EUR")
    later = cast(
        Extra,
        ExtraFactory(
            property=prop,
            currency=eur,
            name="Chef",
            description="Private chef, per night",
            kind=ExtraKind.SERVICE_FEE,
            calc=ExtraCalc.FIXED_PER_NIGHT,
            amount=Decimal("250.00"),
            is_mandatory=False,
            commissionable=False,
            applies_from=date(2026, 6, 1),
            applies_to=date(2026, 9, 30),
            min_party=2,
            max_party=8,
            sort_order=5,
            is_active=False,
            notes="internal only",
            idempotency_key="abc",
        ),
    )
    first = cast(Extra, ExtraFactory(property=prop, currency=eur, name="Cleaning", sort_order=1))

    payload = build_property_payload(prop)

    assert payload["extras"] == [
        {
            "RES_ID": first.pk,
            "id": first.pk,
            "name": "Cleaning",
            "description": "",
            "category": "cleaning",
            "calc": "fixed_per_stay",
            "amount": "150.00",
            "currency": "EUR",
            "is_mandatory": True,
            "commissionable": True,
            "is_active": True,
            "applies_from": None,
            "applies_to": None,
            "min_party": None,
            "max_party": None,
            "sort_order": 1,
        },
        {
            "RES_ID": later.pk,
            "id": later.pk,
            "name": "Chef",
            "description": "Private chef, per night",
            "category": "service_fee",
            "calc": "fixed_per_night",
            "amount": "250.00",
            "currency": "EUR",
            "is_mandatory": False,
            "commissionable": False,
            "is_active": False,
            "applies_from": "2026-06-01",
            "applies_to": "2026-09-30",
            "min_party": 2,
            "max_party": 8,
            "sort_order": 5,
        },
    ]
    assert json.loads(json.dumps(payload["extras"])) == payload["extras"]


def test_payload_extras_catalogue_same_name_on_two_villas_has_distinct_res_ids() -> None:
    """`Extra` is property-scoped: the product key is the (villa, extra) pair,
    so two villas' "Cleaning" must never collapse into one Zoho product."""
    prop_a, prop_b = _property(), _property()
    ExtraFactory(property=prop_a, name="Cleaning")
    ExtraFactory(property=prop_b, name="Cleaning")

    ids_a = [e["RES_ID"] for e in build_property_payload(prop_a)["extras"]]
    ids_b = [e["RES_ID"] for e in build_property_payload(prop_b)["extras"]]

    assert len(ids_a) == len(ids_b) == 1
    assert ids_a != ids_b


def test_payload_extras_catalogue_empty_list_when_none() -> None:
    assert build_property_payload(_property())["extras"] == []


def test_payload_query_count_pinned() -> None:
    """Pinned on a BARE instance (a fresh `.get()`, exactly what
    `push_sync_record` hands the builder — a factory-warm instance hides the
    five lazy scalar walks: region, region.country, location, location.country,
    capacity). 14 = 5 scalar walks + 1 base row + 6 collection SELECTs + the
    GAP-102 extras SELECT + the GAP-091 `other_information` description
    SELECT; `currency` rides the extras one via select_related, and the
    two-row fixture turns a per-row currency fetch into a red test."""
    prop = Property.objects.get(pk=_full_property().pk)

    with assert_max_queries(14):
        build_property_payload(prop)


# --- enqueue behaviour ----------------------------------------------------


@pytest.mark.usefixtures("run_on_commit_immediately", "villa_webhook")
def test_property_create_enqueues_pending_record(delay_mock: mock.Mock) -> None:
    prop = _property()

    record = SyncRecord.objects.get()
    assert record.content_type == _property_ct()
    assert record.object_id == prop.pk
    assert record.status == SyncStatus.PENDING
    delay_mock.assert_called_once_with(record.pk)


@pytest.mark.usefixtures("run_on_commit_immediately", "villa_webhook")
def test_lifecycle_status_save_bumps(delay_mock: mock.Mock) -> None:
    prop = _property()
    record = _record_for(prop)
    _mark_in_sync(record)

    prop.status = PropertyStatus.ARCHIVED
    prop.save(update_fields=["status", "updated_at"])

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING
    assert delay_mock.call_count == 2  # create + bump


@pytest.mark.usefixtures("run_on_commit_immediately", "villa_webhook")
def test_availability_stamp_saves_do_not_enqueue(delay_mock: mock.Mock) -> None:
    """Acceptance criterion: availability-freshness churn (the real service's
    narrow update_fields saves) never re-pushes the villa."""
    prop = _property()
    record = _record_for(prop)
    _mark_in_sync(record)

    PropertyAvailabilityService.touch_owner_updated(prop)
    PropertyAvailabilityService.confirm(prop, actor=cast(User, UserFactory()))

    record.refresh_from_db()
    assert record.status == SyncStatus.IN_SYNC
    assert delay_mock.call_count == 1  # the create only


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_unset_url_is_full_noop(delay_mock: mock.Mock) -> None:
    _property()

    assert SyncRecord.objects.count() == 0
    delay_mock.assert_not_called()


# --- child-row bumps (Unit 4) ---------------------------------------------


def _make_feature_link(prop: Property) -> Any:
    return PropertyFeature.objects.create(property=prop, feature=_feature())


def _make_contact_assignment(prop: Property) -> Any:
    return _assignment(property=prop, contact=PersonFactory(), role=ContactRole.OWNER)


def _get_location(prop: Property) -> Any:
    return prop.location


def _get_capacity(prop: Property) -> Any:
    return prop.capacity


def _make_room(prop: Property) -> Any:
    return RoomFactory(property=prop)


def _make_beds(prop: Property) -> Any:
    return cast(Room, RoomFactory(property=prop)).beds


def _make_room_attribute_link(prop: Property) -> Any:
    room = cast(Room, RoomFactory(property=prop))
    attribute = cast(RoomAttribute, RoomAttributeFactory())
    return RoomAttributeAssignment.objects.create(room=room, attribute=attribute)


def _get_image(prop: Property) -> Any:
    return prop.images.get()


def _make_other_information_description(prop: Property) -> Any:
    return PropertyDescription.objects.create(
        property=prop, section=DescriptionSection.OTHER_INFORMATION, body="Licence 0829K"
    )


@pytest.mark.usefixtures("run_on_commit_immediately", "villa_webhook")
@pytest.mark.parametrize(
    "make_child",
    [
        _make_feature_link,
        _make_contact_assignment,
        _get_location,
        _get_capacity,
        _make_room,
        _make_beds,
        _make_room_attribute_link,
        _get_image,
        _make_other_information_description,
    ],
    ids=[
        "PropertyFeature",
        "PropertyContactAssignment",
        "PropertyLocation",
        "PropertyCapacity",
        "Room",
        "RoomBeds",
        "RoomAttributeAssignment",
        "PropertyImage",
        "PropertyDescription(other_information)",
    ],
)
def test_child_save_and_delete_bump_parent(make_child: Any, delay_mock: mock.Mock) -> None:
    prop = _property()
    child = make_child(prop)
    record = _record_for(prop)
    _mark_in_sync(record)
    delay_mock.reset_mock()

    child.save()

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING
    delay_mock.assert_called_once()  # bump-without-dispatch would strand delivery on the sweep

    _mark_in_sync(record)
    delay_mock.reset_mock()
    child.delete()

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING
    delay_mock.assert_called_once()
    assert SyncRecord.objects.filter(content_type=_property_ct()).count() == 1


@pytest.mark.usefixtures("run_on_commit_immediately", "villa_webhook")
def test_other_description_sections_do_not_bump(delay_mock: mock.Mock) -> None:
    """Only the `other_information` section rides the villa payload; editing
    house rules (or any other copy block) must not re-push the villa."""
    prop = _property()
    record = _record_for(prop)
    _mark_in_sync(record)
    delay_mock.reset_mock()

    row = PropertyDescription.objects.create(
        property=prop, section=DescriptionSection.HOUSE_RULES, body="No parties"
    )
    row.body = "No loud parties"
    row.save()
    row.delete()

    record.refresh_from_db()
    assert record.status == SyncStatus.IN_SYNC
    delay_mock.assert_not_called()


@pytest.mark.usefixtures("run_on_commit_immediately", "villa_webhook")
def test_features_m2m_set_remove_clear_bump_parent(delay_mock: mock.Mock) -> None:
    """`Property.features.set()` additions ride `bulk_create` (no per-row
    `post_save`) — only `m2m_changed` covers them. Removals DO also fire
    per-row `post_delete` (connected receivers disable fast-delete), so the
    remove/clear legs here pass through either path; the add leg is the one
    that truly needs the m2m handler."""
    prop = _property()
    pool = _feature()
    wifi = _feature()
    record = _record_for(prop)
    _mark_in_sync(record)

    prop.features.set([pool, wifi])
    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING

    _mark_in_sync(record)
    prop.features.set([pool])  # the post_remove leg
    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING

    _mark_in_sync(record)
    prop.features.clear()  # the post_clear leg
    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING


@pytest.mark.usefixtures("run_on_commit_immediately", "villa_webhook")
def test_features_reverse_m2m_write_does_not_bump(delay_mock: mock.Mock) -> None:
    """`feature.properties.add(...)` (reverse side) is deliberately skipped —
    no codebase writer uses the reverse manager; pin the skip so the handler
    comment stays honest."""
    prop = _property()
    feature = _feature()
    record = _record_for(prop)
    _mark_in_sync(record)
    delay_mock.reset_mock()

    feature.properties.add(prop)

    record.refresh_from_db()
    assert record.status == SyncStatus.IN_SYNC
    delay_mock.assert_not_called()


@pytest.mark.usefixtures("run_on_commit_immediately", "villa_webhook")
def test_property_cascade_delete_is_benign(delay_mock: mock.Mock) -> None:
    """Deleting a villa cascades every child; mid-cascade bumps must not blow
    up on the vanishing parent, and the reaper clears the villa's records."""
    prop = _property()
    room = cast(Room, RoomFactory(property=prop))
    RoomAttributeAssignment.objects.create(
        room=room, attribute=cast(RoomAttribute, RoomAttributeFactory())
    )
    PropertyFeature.objects.create(property=prop, feature=_feature())
    _assignment(property=prop, contact=PersonFactory(), role=ContactRole.OWNER)
    record = _record_for(prop)
    _mark_in_sync(record)
    delay_mock.reset_mock()

    prop.delete()

    assert not SyncRecord.objects.filter(content_type=_property_ct()).exists()
    # N child bumps must collapse to ONE dispatch via the PENDING dedupe —
    # each extra .delay would post-commit POST a dead record.
    assert delay_mock.call_count == 1


@pytest.mark.usefixtures("run_on_commit_immediately", "villa_webhook")
def test_room_reorder_endpoint_bumps_villa(
    delay_mock: mock.Mock,
    api_client: Any,
    staff: User,
) -> None:
    """The reorder view writes via `queryset.update()` — no post_save — so it
    enqueues the villa explicitly; room order is embedded in the payload."""
    prop = _property()
    room_a = cast(Room, RoomFactory(property=prop, sort_order=0))
    room_b = cast(Room, RoomFactory(property=prop, sort_order=1))
    record = _record_for(prop)
    _mark_in_sync(record)
    delay_mock.reset_mock()
    api_client.force_authenticate(staff)

    response = api_client.post(
        f"/api/v1/properties/{prop.pk}/rooms:reorder",
        {"room_ids": [room_b.pk, room_a.pk]},
        format="json",
    )

    assert response.status_code == 200
    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING
    delay_mock.assert_called_once()


@pytest.mark.usefixtures("run_on_commit_immediately", "villa_webhook")
def test_suppressed_child_bump_is_noop_without_parent_select(delay_mock: mock.Mock) -> None:
    prop = _property()
    # Fresh fetch: the reverse one-to-one accessor would have pre-cached the
    # parent, hiding an unwanted SELECT from the query capture.
    location = PropertyLocation.objects.get(pk=prop.pk)
    record = _record_for(prop)
    _mark_in_sync(record)
    delay_mock.reset_mock()

    with suppress_zoho_push(), CaptureQueriesContext(connection) as ctx:
        location.save()

    assert not [q for q in ctx.captured_queries if '"properties_property"' in q["sql"]]
    record.refresh_from_db()
    assert record.status == SyncStatus.IN_SYNC
    delay_mock.assert_not_called()


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_unset_url_child_bump_is_noop_without_parent_select(delay_mock: mock.Mock) -> None:
    prop = _property()  # no webhook → no record for the create either
    location = PropertyLocation.objects.get(pk=prop.pk)

    with CaptureQueriesContext(connection) as ctx:
        location.save()

    assert not [q for q in ctx.captured_queries if '"properties_property"' in q["sql"]]
    assert SyncRecord.objects.count() == 0
    delay_mock.assert_not_called()
