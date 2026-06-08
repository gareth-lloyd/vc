"""API tests for `/enquiries` CRUD + colon-verb actions + nested notes."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from core.tests import assert_max_queries
from pricing.models import Currency
from reservations.enums import ContactMethod, EnquiryStatus
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
        is_staff=True,
        email="res-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
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
    # The 201 body must be detail-shaped so the SPA can parse it: it carries
    # the server-assigned id/reference/status and computed name fields that the
    # write serializer omits.
    created = Enquiry.objects.get(email="ada@new.example.com")
    assert response.data["id"] == created.pk
    assert response.data["reference"] == created.reference
    assert response.data["reference"]
    assert response.data["status"] == EnquiryStatus.NEW.value
    assert response.data["guest_name"] == "Ada Lovelace"
    assert response.data["quotations"] == []


@pytest.mark.django_db
def test_create_enquiry_persists_contact_method(
    api_client: APIClient, staff: User, guest: Guest
) -> None:
    """The write serializer accepts contact_method so the capture form can
    record the lead's preferred channel."""
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/enquiries",
        {
            "guest": guest.pk,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@pref.example.com",
            "adults": 2,
            "contact_method": ContactMethod.PHONE.value,
        },
        format="json",
    )

    assert response.status_code == 201
    created = Enquiry.objects.get(email="ada@pref.example.com")
    assert created.contact_method == ContactMethod.PHONE.value
    assert response.data["contact_method"] == ContactMethod.PHONE.value


@pytest.mark.django_db
def test_update_enquiry_contact_method(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/enquiries/{enquiry.pk}",
        {"contact_method": ContactMethod.SMS.value},
        format="json",
    )

    assert response.status_code == 200
    enquiry.refresh_from_db()
    assert enquiry.contact_method == ContactMethod.SMS.value
    assert response.data["contact_method"] == ContactMethod.SMS.value


@pytest.mark.django_db
def test_create_enquiry__stays_query_bounded(
    api_client: APIClient, staff: User, guest: Guest
) -> None:
    """The detail re-serialisation must re-fetch through the prefetched
    queryset — no N+1 walking the (empty) quote-stack."""
    api_client.force_login(staff)
    with assert_max_queries(12):
        response = api_client.post(
            "/api/v1/enquiries",
            {
                "guest": guest.pk,
                "first_name": "Grace",
                "last_name": "Hopper",
                "email": "grace@new.example.com",
                "adults": 2,
            },
            format="json",
        )
    assert response.status_code == 201


@pytest.mark.django_db
def test_update_enquiry_returns_detail_shape(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/enquiries/{enquiry.pk}",
        {"first_name": "Augusta"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["id"] == enquiry.pk
    assert response.data["reference"] == enquiry.reference
    assert response.data["status"] == enquiry.status
    assert response.data["first_name"] == "Augusta"
    assert "quotations" in response.data


@pytest.mark.django_db
def test_retrieve_enquiry_returns_detail(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/enquiries/{enquiry.pk}")

    assert response.status_code == 200
    assert response.data["id"] == enquiry.pk
    assert "inbound_message" in response.data
    # phone + contact_method are now exposed on the read shape so the FE can
    # pass an enquiry's phone through when creating a Guest.
    assert "phone" in response.data
    assert "contact_method" in response.data


@pytest.mark.django_db
def test_enquiry_detail_includes_nested_quotations(
    api_client: APIClient,
    staff: User,
    enquiry: Enquiry,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """Detail view exposes the quote-stack for the staff grouped-list UI."""
    q1 = Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    q2 = Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=14),
        terms_version=terms,
    )
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/enquiries/{enquiry.pk}")

    assert response.status_code == 200
    assert "quotations" in response.data
    quotation_refs = {row["reference"] for row in response.data["quotations"]}
    assert quotation_refs == {q1.reference, q2.reference}
    # Conversion rollup also exposed.
    assert response.data["is_converted"] is False


@pytest.mark.django_db
def test_enquiry_detail_excludes_synthetic_booking_quotations(
    api_client: APIClient,
    staff: User,
    enquiry: Enquiry,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """Booking-synthesised quotations (`legacy_id` prefixed `booking-`) are an
    internal fill artefact and must never surface in the enquiry quote-stack —
    the same exclusion every other Quotation-surfacing viewset applies."""
    real = Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
        legacy_id="booking-12345",
    )
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/enquiries/{enquiry.pk}")

    assert response.status_code == 200
    quotation_refs = {row["reference"] for row in response.data["quotations"]}
    assert quotation_refs == {real.reference}


@pytest.mark.django_db
def test_enquiry_list_does_not_include_nested_quotations(
    api_client: APIClient,
    staff: User,
    enquiry: Enquiry,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """List endpoint stays slim — no nested quotation array."""
    Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    api_client.force_login(staff)

    response = api_client.get("/api/v1/enquiries")

    assert response.status_code == 200
    row = response.data["results"][0]
    assert "quotations" not in row


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
def test_enquiry_convert_endpoint_idempotent_when_already_converted(
    api_client: APIClient,
    staff: User,
    enquiry: Enquiry,
    gbp: Currency,
    terms: TermsVersion,
    guest: Guest,
) -> None:
    """A second `:convert` on an already-CONVERTED enquiry returns 200, not 422.

    The auto-conversion path (e.g. Quotation.accept flipping the parent
    enquiry inline) means an explicit operator call to convert can race
    the implicit one. The endpoint must short-circuit to the current
    serialized state — no state change, no new event, no error.
    """
    enquiry.contact()
    quotation = Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    api_client.force_login(staff)
    url = f"/api/v1/enquiries/{enquiry.pk}:convert"
    payload = {"quotation": quotation.pk}

    first = api_client.post(url, payload, format="json")
    assert first.status_code == 200

    second = api_client.post(url, payload, format="json")

    assert second.status_code == 200
    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.CONVERTED.value
    converted_events = EnquiryEvent.objects.filter(
        enquiry=enquiry,
        kind="converted",
    )
    assert converted_events.count() == 1


@pytest.mark.django_db
def test_enquiry_convert_endpoint_still_works_when_quoted(
    api_client: APIClient,
    staff: User,
    enquiry: Enquiry,
    gbp: Currency,
    terms: TermsVersion,
    guest: Guest,
) -> None:
    """Regression guard: the idempotency short-circuit must not skip work on
    enquiries that haven't been converted yet.
    """
    enquiry.contact()
    quotation = Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    enquiry.quote_sent(quotation, send_path="smtp")
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/enquiries/{enquiry.pk}:convert",
        {"quotation": quotation.pk},
        format="json",
    )

    assert response.status_code == 200
    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.CONVERTED.value
    assert EnquiryEvent.objects.filter(enquiry=enquiry, kind="converted").count() == 1


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


@pytest.mark.django_db
def test_enquiry_status_counts__groups_by_status(
    api_client: APIClient, staff: User, guest: Guest
) -> None:
    Enquiry.objects.create(guest=guest, first_name="A", last_name="B", email="a@b.com")
    Enquiry.objects.create(
        guest=guest,
        first_name="C",
        last_name="D",
        email="c@d.com",
        status=EnquiryStatus.LOST.value,
    )
    api_client.force_login(staff)

    response = api_client.get("/api/v1/enquiries/status-counts")

    assert response.status_code == 200
    assert response.data == {EnquiryStatus.NEW.value: 1, EnquiryStatus.LOST.value: 1}
