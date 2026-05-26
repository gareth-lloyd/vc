"""API tests for `/enquiries` CRUD + colon-verb actions + nested notes."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.enums import StaffRole
from accounts.models import User
from pricing.models import Currency
from reservations.enums import EnquiryStatus
from reservations.models import (
    Enquiry,
    EnquiryEvent,
    EnquiryNote,
    Guest,
    Quotation,
    TermsVersion,
)


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        email="res-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        email="res-viewer@example.com",
        password="x",
        role=StaffRole.VIEWER,
    )


@pytest.fixture
def enquiry(guest: Guest) -> Enquiry:
    return Enquiry.objects.create(
        guest=guest,
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        adults=2,
    )


@pytest.mark.django_db
def test_list_enquiries__staff_sees_all(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    api_client.force_login(staff)
    response = api_client.get("/api/v1/enquiries")

    assert response.status_code == 200
    assert response.data["count"] == 1
    row = response.data["results"][0]
    assert row["reference"] == enquiry.reference
    # Surface human-readable values so the FE doesn't render "Property #28".
    assert row["guest_name"] == "Ada Lovelace"
    assert "property_name" in row
    assert "region_name" in row
    assert "assigned_to_name" in row
    assert "agent_name" in row


@pytest.mark.django_db
def test_list_enquiries__filter_by_status(api_client: APIClient, staff: User, guest: Guest) -> None:
    Enquiry.objects.create(guest=guest, first_name="A", last_name="B", email="a@b.com")
    lost = Enquiry.objects.create(
        guest=guest,
        first_name="C",
        last_name="D",
        email="c@d.com",
        status=EnquiryStatus.LOST.value,
    )
    api_client.force_login(staff)

    response = api_client.get("/api/v1/enquiries", {"status": EnquiryStatus.LOST.value})

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == lost.pk


@pytest.mark.django_db
def test_create_enquiry(api_client: APIClient, staff: User, guest: Guest) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/enquiries",
        {
            "guest": guest.pk,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@new.example.com",
            "adults": 2,
            "children": 0,
        },
        format="json",
    )

    assert response.status_code == 201
    assert Enquiry.objects.filter(email="ada@new.example.com").exists()


@pytest.mark.django_db
def test_retrieve_enquiry_returns_detail(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/enquiries/{enquiry.pk}")

    assert response.status_code == 200
    assert response.data["id"] == enquiry.pk
    assert "inbound_message" in response.data


@pytest.mark.django_db
def test_assign_enquiry__sets_assigned_to(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/enquiries/{enquiry.pk}:assign",
        {"user": staff.pk},
        format="json",
    )

    assert response.status_code == 200
    enquiry.refresh_from_db()
    assert enquiry.assigned_to_id == staff.pk
    assert EnquiryEvent.objects.filter(enquiry=enquiry, kind="assigned").exists()


@pytest.mark.django_db
def test_convert_enquiry__transitions_to_converted(
    api_client: APIClient,
    staff: User,
    enquiry: Enquiry,
    gbp: Currency,
    terms: TermsVersion,
    guest: Guest,
) -> None:
    # Move enquiry through CONTACTED → QUOTED first; convert is allowed from
    # QUOTED or CONTACTED per the state machine.
    enquiry.contact()
    quotation = Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/enquiries/{enquiry.pk}:convert",
        {"quotation": quotation.pk},
        format="json",
    )

    assert response.status_code == 200
    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.CONVERTED.value


@pytest.mark.django_db
def test_close_enquiry__marks_lost(api_client: APIClient, staff: User, enquiry: Enquiry) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/enquiries/{enquiry.pk}:close",
        {"reason": "guest went elsewhere"},
        format="json",
    )

    assert response.status_code == 200
    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.LOST.value


@pytest.mark.django_db
def test_activity_returns_event_timeline(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    enquiry.contact()
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/enquiries/{enquiry.pk}/activity")

    assert response.status_code == 200
    assert any(row["to_status"] == EnquiryStatus.CONTACTED.value for row in response.data)


@pytest.mark.django_db
def test_notes__list_and_create(api_client: APIClient, staff: User, enquiry: Enquiry) -> None:
    api_client.force_login(staff)

    create = api_client.post(
        f"/api/v1/enquiries/{enquiry.pk}/notes",
        {"body": "guest mentioned anniversary", "kind": "preferences"},
        format="json",
    )
    assert create.status_code == 201

    listing = api_client.get(f"/api/v1/enquiries/{enquiry.pk}/notes")
    assert listing.status_code == 200
    assert listing.data["count"] == 1
    note = EnquiryNote.objects.get()
    assert note.author_id == staff.pk


@pytest.mark.django_db
def test_viewer_cannot_create_enquiry(api_client: APIClient, viewer: User, guest: Guest) -> None:
    api_client.force_login(viewer)
    response = api_client.post(
        "/api/v1/enquiries",
        {
            "guest": guest.pk,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@viewer.com",
            "adults": 2,
        },
        format="json",
    )
    assert response.status_code == 403
