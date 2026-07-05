"""Room API — GAP-064 facets + attribute links, plus the catalog endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from core.tests import assert_max_queries
from properties.factories import PropertyFactory, RoomAttributeFactory, RoomFactory
from properties.models import Property, Room, RoomAttribute, RoomAttributeAssignment

if TYPE_CHECKING:
    from rest_framework.test import APIClient

    from accounts.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def prop(db: None) -> Property:
    return cast(Property, PropertyFactory())


@pytest.fixture
def room(prop: Property) -> Room:
    return cast(Room, RoomFactory(property=prop))


def _rooms_url(prop: Property) -> str:
    return f"/api/v1/properties/{prop.pk}/rooms"


def _room_url(room: Room) -> str:
    return f"/api/v1/properties/{room.property_id}/rooms/{room.pk}"


def _attr(**kwargs: object) -> RoomAttribute:
    return cast(RoomAttribute, RoomAttributeFactory(**kwargs))


class TestRoomRead:
    def test_detail_includes_facets_and_attribute_links(
        self, api_client: APIClient, staff: User, room: Room
    ) -> None:
        attr = _attr(name="Sea view test", icon="waves")
        RoomAttributeAssignment.objects.create(room=room, attribute=attr, note="from balcony")
        room.ensuite_type = "shower"
        room.is_ensuite = True
        room.access = "outside"
        room.save()

        api_client.force_authenticate(staff)
        data = api_client.get(_room_url(room)).json()

        assert data["ensuite_type"] == "shower"
        assert data["access"] == "outside"
        (link,) = data["attribute_links"]
        assert link["attribute"] == attr.pk
        assert link["slug"] == attr.slug
        assert link["name"] == "Sea view test"
        assert link["icon"] == "waves"
        assert link["is_active"] is True
        assert link["note"] == "from balcony"

    def test_links_ordered_by_catalog_rank(
        self, api_client: APIClient, staff: User, room: Room
    ) -> None:
        second = _attr(name="B", sort_order=20)
        first = _attr(name="A", sort_order=10)
        RoomAttributeAssignment.objects.create(room=room, attribute=second)
        RoomAttributeAssignment.objects.create(room=room, attribute=first)

        api_client.force_authenticate(staff)
        data = api_client.get(_room_url(room)).json()
        assert [link["attribute"] for link in data["attribute_links"]] == [first.pk, second.pk]

    def test_write_response_uses_catalog_rank_too(
        self, api_client: APIClient, staff: User, room: Room
    ) -> None:
        # The PATCH/POST body must match what the next GET returns — no
        # submission-order flicker.
        second = _attr(name="B", sort_order=20)
        first = _attr(name="A", sort_order=10)
        api_client.force_authenticate(staff)
        data = api_client.patch(
            _room_url(room),
            {"attribute_links": [{"attribute": second.pk}, {"attribute": first.pk}]},
            format="json",
        ).json()
        assert [link["attribute"] for link in data["attribute_links"]] == [first.pk, second.pk]

    def test_list_query_count_is_pinned(
        self, api_client: APIClient, staff: User, prop: Property
    ) -> None:
        for _ in range(4):
            r = cast(Room, RoomFactory(property=prop))
            RoomAttributeAssignment.objects.create(room=r, attribute=_attr())
        api_client.force_authenticate(staff)
        # user + COUNT + rooms(+beds via join) + links(+attributes via join) —
        # tight enough that any per-room N+1 (4 rooms) blows the pin.
        with assert_max_queries(4):
            resp = api_client.get(_rooms_url(prop))
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 4


class TestRoomWrite:
    def test_post_with_name_only_is_201(
        self, api_client: APIClient, staff: User, prop: Property
    ) -> None:
        api_client.force_authenticate(staff)
        resp = api_client.post(_rooms_url(prop), {"name": "Attic room"}, format="json")
        assert resp.status_code == 201, resp.content
        data = resp.json()
        assert data["ensuite_type"] == ""
        assert data["access"] == ""
        assert data["attribute_links"] == []

    def test_post_with_links_and_facets(
        self, api_client: APIClient, staff: User, prop: Property
    ) -> None:
        attr = _attr()
        api_client.force_authenticate(staff)
        resp = api_client.post(
            _rooms_url(prop),
            {
                "name": "Master suite",
                "ensuite_type": "both",
                "access": "inside",
                "attribute_links": [{"attribute": attr.pk, "note": "quiet side"}],
            },
            format="json",
        )
        assert resp.status_code == 201, resp.content
        data = resp.json()
        assert data["is_ensuite"] is True  # non-blank type refines the bool
        (link,) = data["attribute_links"]
        assert link["attribute"] == attr.pk
        assert link["note"] == "quiet side"

    def test_patch_sync_ticks_and_unticks(
        self, api_client: APIClient, staff: User, room: Room
    ) -> None:
        keep = _attr()
        drop = _attr()
        add = _attr()
        RoomAttributeAssignment.objects.create(room=room, attribute=keep)
        RoomAttributeAssignment.objects.create(room=room, attribute=drop)

        api_client.force_authenticate(staff)
        resp = api_client.patch(
            _room_url(room),
            {"attribute_links": [{"attribute": keep.pk}, {"attribute": add.pk}]},
            format="json",
        )
        assert resp.status_code == 200, resp.content
        assert set(
            RoomAttributeAssignment.objects.filter(room=room).values_list("attribute_id", flat=True)
        ) == {keep.pk, add.pk}

    def test_patch_without_field_leaves_links_alone(
        self, api_client: APIClient, staff: User, room: Room
    ) -> None:
        attr = _attr()
        RoomAttributeAssignment.objects.create(room=room, attribute=attr, note="keep me")

        api_client.force_authenticate(staff)
        resp = api_client.patch(_room_url(room), {"name": "Renamed"}, format="json")
        assert resp.status_code == 200
        link = RoomAttributeAssignment.objects.get(room=room)
        assert link.attribute_id == attr.pk
        assert link.note == "keep me"

    def test_patch_updates_note_on_existing_link(
        self, api_client: APIClient, staff: User, room: Room
    ) -> None:
        attr = _attr()
        RoomAttributeAssignment.objects.create(room=room, attribute=attr, note="old")

        api_client.force_authenticate(staff)
        api_client.patch(
            _room_url(room),
            {"attribute_links": [{"attribute": attr.pk, "note": "new"}]},
            format="json",
        )
        assert RoomAttributeAssignment.objects.get(room=room).note == "new"

    def test_patch_keeps_a_retired_attribute_link_when_resubmitted(
        self, api_client: APIClient, staff: User, room: Room
    ) -> None:
        # B1: the form re-submits the full list including links to retired
        # attributes — the sync must keep them, not 400 on inactive rows.
        retired = _attr(is_active=False)
        RoomAttributeAssignment.objects.create(room=room, attribute=retired)

        api_client.force_authenticate(staff)
        resp = api_client.patch(
            _room_url(room),
            {"attribute_links": [{"attribute": retired.pk}]},
            format="json",
        )
        assert resp.status_code == 200, resp.content
        assert RoomAttributeAssignment.objects.filter(room=room, attribute=retired).exists()

    def test_duplicate_attribute_ids_are_deduped(
        self, api_client: APIClient, staff: User, room: Room
    ) -> None:
        attr = _attr()
        api_client.force_authenticate(staff)
        resp = api_client.patch(
            _room_url(room),
            {
                "attribute_links": [
                    {"attribute": attr.pk, "note": "first wins"},
                    {"attribute": attr.pk, "note": "dropped"},
                ]
            },
            format="json",
        )
        assert resp.status_code == 200, resp.content
        link = RoomAttributeAssignment.objects.get(room=room)
        assert link.note == "first wins"

    def test_invalid_attribute_id_is_400(
        self, api_client: APIClient, staff: User, room: Room
    ) -> None:
        api_client.force_authenticate(staff)
        resp = api_client.patch(
            _room_url(room),
            {"attribute_links": [{"attribute": 999999}]},
            format="json",
        )
        assert resp.status_code == 400

    def test_nonblank_ensuite_type_sets_is_ensuite(
        self, api_client: APIClient, staff: User, room: Room
    ) -> None:
        assert room.is_ensuite is False
        api_client.force_authenticate(staff)
        resp = api_client.patch(_room_url(room), {"ensuite_type": "bath"}, format="json")
        assert resp.status_code == 200, resp.content
        room.refresh_from_db()
        assert room.is_ensuite is True
        assert room.ensuite_type == "bath"

    def test_blank_ensuite_type_clears_without_touching_bool(
        self, api_client: APIClient, staff: User, room: Room
    ) -> None:
        room.is_ensuite = True
        room.ensuite_type = "shower"
        room.save()
        api_client.force_authenticate(staff)
        api_client.patch(_room_url(room), {"ensuite_type": ""}, format="json")
        room.refresh_from_db()
        assert room.ensuite_type == ""
        assert room.is_ensuite is True  # unknown type never implies "not ensuite"

    def test_unsetting_is_ensuite_clears_a_stale_type(
        self, api_client: APIClient, staff: User, room: Room
    ) -> None:
        # Unchecking the box alone must clear the typed facet too, not trip
        # the DB coherence constraint (a 500).
        room.is_ensuite = True
        room.ensuite_type = "shower"
        room.save()
        api_client.force_authenticate(staff)
        resp = api_client.patch(_room_url(room), {"is_ensuite": False}, format="json")
        assert resp.status_code == 200, resp.content
        room.refresh_from_db()
        assert room.is_ensuite is False
        assert room.ensuite_type == ""


class TestRoomAttributeCatalogEndpoint:
    def test_anonymous_read(self, api_client: APIClient) -> None:
        resp = api_client.get("/api/v1/room-attributes")
        assert resp.status_code == 200
        results = resp.json()["results"]
        slugs = {row["slug"] for row in results}
        assert "aircon" in slugs  # migration-seeded starter row
        row = next(r for r in results if r["slug"] == "aircon")
        assert set(row) >= {"id", "slug", "name", "icon", "sort_order", "is_active"}

    def test_honours_page_size_for_the_whole_catalog_fetch(self, api_client: APIClient) -> None:
        # The room form fetches everything in one request (taxonomy pattern);
        # growth past the default page must not silently truncate the picker.
        for i in range(60):
            _attr(slug=f"bulk-attr-{i}")
        resp = api_client.get("/api/v1/room-attributes?page_size=500")
        assert len(resp.json()["results"]) >= 60

    def test_includes_inactive_rows(self, api_client: APIClient) -> None:
        # The form needs retired rows it must keep ticked (B1); filtering to
        # active-only is the client's job.
        retired = _attr(is_active=False)
        resp = api_client.get("/api/v1/room-attributes")
        assert retired.pk in {row["id"] for row in resp.json()["results"]}

    def test_write_is_staff_only(self, api_client: APIClient) -> None:
        resp = api_client.post("/api/v1/room-attributes", {"name": "X", "slug": "x"})
        assert resp.status_code in (403, 405)
