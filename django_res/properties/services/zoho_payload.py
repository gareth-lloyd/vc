"""Property → Zoho Flow villa payload builder (GAP-082 Unit 3).

Full-fat, JSON-safe payload (dates → ISO-8601, Decimals → str), `RES_ID` +
`id` on the record and on every nested sub-object. Upsert semantics in the
Flow are keyed on `RES_ID`.

Covers the legacy `ZohoVillaPostData` checklist
(`legacy/workflows/11-integrations/zoho-crm.md`), mapped onto the current
models: Name→`name`, VillaId→`RES_ID` (with `legacy_id` as legacy-row
provenance), CountryName/Region/Country→nested `region.country`,
Owner→`contacts[role=owner]` (a clean equivalent exists now via
`PropertyContactAssignment` — the ticket note predates it),
Co_ordinates→`location.latitude`/`location.longitude` (typed fields),
Villa_Name_Other→`display_name`, Created_Time/Modified_Time/
Last_Activity_Time→`created_at`/`updated_at`.
**Omitted, no placeholders**: `Villa_URL` (no public site URL exists) and
`Note` (no single note field; descriptions are guest-facing copy).

Deliberately NO availability or pricing data — res stays the sole source of
truth for both; the Zoho record is for segmentation/reporting only.

Embedded copies of catalog/related rows (feature + room-attribute names,
region/country, organisation details, person summaries) refresh
only when the villa itself next pushes — a catalog rename does NOT fan out
re-pushes to every villa embedding it. Accepted trade-off for
segmentation-only data; person/organisation records push their own `contact`
kind and stay current there.

`_iso`/`_person_summary`/`_region_payload` are duplicated byte-identical from
`reservations/services/zoho_payload.py` (the established cross-app pattern —
the import spine forbids properties importing reservations).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from django.db.models import Prefetch

from integrations.services.zoho_flow import is_anonymized_person

if TYPE_CHECKING:
    from accounts.models import Organisation, Person
    from properties.models.capacity import PropertyCapacity
    from properties.models.contacts import PropertyContactAssignment
    from properties.models.features import PropertyFeature
    from properties.models.geo import Region
    from properties.models.location import PropertyLocation
    from properties.models.property import Property
    from properties.models.rooms import Room


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _person_summary(person: Person | None) -> dict[str, Any] | None:
    if person is None or is_anonymized_person(person):
        return None
    return {
        "RES_ID": person.pk,
        "id": person.pk,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "full_name": person.display_name or "",
        "agency_name": person.agency_name,
        "agency": (
            {"RES_ID": person.agency.pk, "id": person.agency.pk, "name": person.agency.name}
            if person.agency is not None
            else None
        ),
        "primary_email": person.primary_email(),
        "primary_phone": person.primary_phone(),
    }


def _region_payload(region: Region | None) -> dict[str, Any] | None:
    if region is None:
        return None
    country = region.country
    return {
        "RES_ID": region.pk,
        "id": region.pk,
        "name": region.name,
        "country": {
            "RES_ID": country.pk,
            "id": country.pk,
            "name": country.name,
            "iso2": country.iso2,
        },
    }


def _location_payload(location: PropertyLocation | None) -> dict[str, Any] | None:
    if location is None:
        return None
    country = location.country
    return {
        "address_line_1": location.address_line_1,
        "address_line_2": location.address_line_2,
        "address_line_3": location.address_line_3,
        "post_code": location.post_code,
        "locality_town": location.locality_town,
        "locality_region": location.locality_region,
        "country": {
            "RES_ID": country.pk,
            "id": country.pk,
            "name": country.name,
            "iso2": country.iso2,
        },
        # Decimals as strings: not JSON-serialisable, floats drift.
        "latitude": str(location.latitude) if location.latitude is not None else None,
        "longitude": str(location.longitude) if location.longitude is not None else None,
        "timezone": location.timezone,
    }


def _capacity_payload(capacity: PropertyCapacity | None) -> dict[str, Any] | None:
    if capacity is None:
        return None
    return {
        "guests": capacity.guests,
        "additional_guests": capacity.additional_guests,
        "bedrooms": capacity.bedrooms,
        "ensuites": capacity.ensuites,
        "bathrooms": capacity.bathrooms,
        "size_sqm": str(capacity.size_sqm) if capacity.size_sqm is not None else None,
    }


def _organisation_summary(organisation: Organisation | None) -> dict[str, Any] | None:
    if organisation is None:
        return None
    return {
        "RES_ID": organisation.pk,
        "id": organisation.pk,
        "name": organisation.name,
        "org_type": organisation.org_type,
        "email": organisation.email,
        "phone": organisation.phone,
    }


def _contact_payload(assignment: PropertyContactAssignment) -> dict[str, Any]:
    return {
        "RES_ID": assignment.pk,
        "id": assignment.pk,
        "role": assignment.role,
        "is_primary": assignment.is_primary,
        "start_date": _iso(assignment.start_date),
        "end_date": _iso(assignment.end_date),
        "person": _person_summary(assignment.contact),
        "organisation": _organisation_summary(assignment.organisation),
    }


def _room_payload(room: Room) -> dict[str, Any]:
    beds = getattr(room, "beds", None)
    return {
        "RES_ID": room.pk,
        "id": room.pk,
        "name": room.name,
        "placement": room.placement,
        "floor": room.floor,
        "placement_note": room.placement_note,
        "is_ensuite": room.is_ensuite,
        "ensuite_type": room.ensuite_type,
        "access": room.access,
        "sort_order": room.sort_order,
        "beds": (
            {
                "double": beds.double,
                "double_size": beds.double_size,
                "twin_double": beds.twin_double,
                "twin": beds.twin,
                "single": beds.single,
                "bunk": beds.bunk,
                "sofa": beds.sofa,
                "childrens": beds.childrens,
            }
            if beds is not None
            else None
        ),
        "attributes": [
            {
                "RES_ID": link.pk,
                "id": link.pk,
                "slug": link.attribute.slug,
                "name": link.attribute.name,
                "note": link.note,
            }
            for link in room.attribute_links.all()
        ],
    }


def _feature_payload(link: PropertyFeature) -> dict[str, Any]:
    feature = link.feature
    return {
        "RES_ID": link.pk,
        "id": link.pk,
        "feature_id": feature.pk,
        "name": feature.name,
        "slug": feature.slug,
        "category": feature.category.name,
        "service_type": feature.service_type,
        "sort_order": link.sort_order,
        "is_derived": link.is_derived,
    }


def build_property_payload(prop: Property) -> dict[str, Any]:
    """Full-field JSON-safe payload for one `properties.Property`.

    Built at push time from the live row (see
    `integrations.tasks.push_sync_record`) — the delivery task hands over a
    bare instance, so each nested collection is fetched here with its own
    select/prefetch rather than walked lazily per row.
    """
    from properties.models.rooms import RoomAttributeAssignment

    assignments = (
        prop.contact_assignments.select_related("contact__agency", "organisation")
        # primary_email()/primary_phone() iterate the prefetched collections.
        .prefetch_related("contact__emails", "contact__phones")
        # Meta ordering has no pk tiebreaker — same-role rows (ended + current
        # owner) would otherwise reorder between pushes.
        .order_by("role", "pk")
    )
    rooms = prop.rooms.select_related("beds").prefetch_related(
        Prefetch(
            "attribute_links",
            queryset=RoomAttributeAssignment.objects.select_related("attribute"),
        )
    )
    feature_links = prop.feature_links.select_related("feature__category")
    return {
        "RES_ID": prop.pk,
        "id": prop.pk,
        "name": prop.name,
        "display_name": prop.display_name,
        "slug": prop.slug,
        "legacy_id": prop.legacy_id,
        "licence_number": prop.licence_number,
        "video_url": prop.video_url,
        "status": prop.status,
        "channel": prop.channel,
        "region": _region_payload(prop.region),
        "location": _location_payload(getattr(prop, "location", None)),
        "capacity": _capacity_payload(getattr(prop, "capacity", None)),
        "contacts": [_contact_payload(assignment) for assignment in assignments],
        "rooms": [_room_payload(room) for room in rooms],
        "features": [_feature_payload(link) for link in feature_links],
        "hero_image_url": prop.hero_image_url(),
        "created_at": _iso(prop.created_at),
        "updated_at": _iso(prop.updated_at),
    }
