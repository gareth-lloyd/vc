"""Tests for the villa Zoho Flow push (GAP-082 Unit 3).

`properties.Property` is registered by `properties.apps.ready()`; these tests
NEVER unregister it (xdist worker leak) — behaviour is toggled via
`override_settings(ZOHO_FLOW_WEBHOOKS=…)` only.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any, cast
from unittest import mock

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings

from accounts.enums import ContactRole, OrgType
from accounts.factories import OrganisationFactory, PersonFactory, UserFactory
from accounts.models import Organisation, Person, User
from integrations import tasks
from integrations.enums import SyncProvider, SyncStatus
from integrations.models import SyncRecord
from integrations.services.zoho_flow import get_zoho_spec
from properties.enums import BedSize, PropertyStatus
from properties.factories import (
    FeatureFactory,
    PropertyContactAssignmentFactory,
    PropertyFactory,
    RoomAttributeFactory,
    RoomFactory,
)
from properties.models.contacts import PropertyContactAssignment
from properties.models.features import Feature, PropertyFeature
from properties.models.property import Property
from properties.models.rooms import Room, RoomAttribute, RoomAttributeAssignment
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
    template = _property()  # supplies reusable category + region
    return Property.objects.create(
        name="Bare Villa",
        display_name="Bare Villa",
        slug=f"bare-villa-{template.pk}",
        category=template.category,
        region=template.region,
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
    assert payload["category"] == {
        "RES_ID": prop.category.pk,
        "id": prop.category.pk,
        "name": prop.category.name,
        "slug": prop.category.slug,
    }
    region = payload["region"]
    assert region["RES_ID"] == prop.region.pk
    assert region["name"] == prop.region.name
    assert region["country"]["iso2"] == prop.region.country.iso2
    assert payload["created_at"] == prop.created_at.isoformat()
    assert payload["updated_at"] == prop.updated_at.isoformat()


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


# --- payload: hero image / JSON safety / omissions ------------------------


def test_payload_hero_image_url() -> None:
    prop = _property()  # factory attaches an active HERO image

    payload = build_property_payload(prop)

    assert payload["hero_image_url"] == prop.hero_image_url()
    assert payload["hero_image_url"] is not None


def test_payload_is_json_serializable() -> None:
    prop = _property()
    prop.location.latitude = Decimal("38.1")
    prop.location.save()
    PropertyContactAssignmentFactory(property=prop, contact=PersonFactory(), role=ContactRole.OWNER)
    RoomFactory(property=prop)
    PropertyFeature.objects.create(property=prop, feature=_feature())

    json.dumps(build_property_payload(prop))


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
    availability + pricing — none of it may ride the villa payload."""
    prop = _property()
    RoomFactory(property=prop)
    PropertyFeature.objects.create(property=prop, feature=_feature())

    keys = _all_keys(build_property_payload(prop))

    assert "Villa_URL" not in keys
    assert "Note" not in keys
    assert not [k for k in keys if "availability" in k.lower()]
    assert not [k for k in keys if "price" in k.lower() or "pricing" in k.lower()]


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
