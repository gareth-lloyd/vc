"""API tests for `/enquiries` CRUD + colon-verb actions + nested notes."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from core.tests import assert_max_queries
from pricing.models import Currency
from properties.enums import ImageKind
from properties.models import Property, PropertyImage
from reservations.enums import ContactMethod, EnquiryLostReason, EnquiryStatus, LeadStatus
from reservations.models import (
    Enquiry,
    EnquiryEvent,
    EnquiryNote,
    Guest,
    Quotation,
    QuotationLine,
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
def test_enquiry_exposes_guest_contact_fields(
    api_client: APIClient, staff: User, guest: Guest
) -> None:
    """Guest-linked enquiries often have blank denormalised contact fields;
    the API exposes read-only `guest_email` / `guest_phone` /
    `guest_contact_method` sourced from the linked Guest (mirroring the
    `guest_name` fallback) so the FE Guest panel isn't all em-dashes."""
    guest.phone = "+447700900123"
    guest.contact_method = "phone"
    guest.save()
    enquiry = Enquiry.objects.create(guest=guest, adults=2)
    api_client.force_login(staff)

    for payload in (
        api_client.get("/api/v1/enquiries").data["results"][0],
        api_client.get(f"/api/v1/enquiries/{enquiry.pk}").data,
    ):
        assert payload["guest_email"] == "ada@example.com"
        assert payload["guest_phone"] == "+447700900123"
        assert payload["guest_contact_method"] == "phone"


@pytest.mark.django_db
def test_enquiry_guest_contact_fields_null_without_guest(
    api_client: APIClient, staff: User
) -> None:
    Enquiry.objects.create(first_name="Solo", last_name="Lead", email="solo@example.com", adults=1)
    api_client.force_login(staff)
    row = api_client.get("/api/v1/enquiries").data["results"][0]

    assert row["guest_email"] is None
    assert row["guest_phone"] is None
    assert row["guest_contact_method"] is None


@pytest.mark.django_db
def test_list_enquiries__filter_by_status(api_client: APIClient, staff: User, guest: Guest) -> None:
    Enquiry.objects.create(guest=guest, first_name="A", last_name="B", email="a@b.com")
    lost = Enquiry.objects.create(
        guest=guest,
        first_name="C",
        last_name="D",
        email="c@d.com",
        status=EnquiryStatus.DEAD.value,
        lost_reason=EnquiryLostReason.UNKNOWN.value,
    )
    api_client.force_login(staff)

    response = api_client.get("/api/v1/enquiries", {"status": EnquiryStatus.DEAD.value})

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == lost.pk


@pytest.mark.django_db
def test_enquiry_exposes_lead_status_and_lost_reason(
    api_client: APIClient, staff: User, guest: Guest
) -> None:
    """The lead temperature + structured lost-reason land on both list and
    detail payloads (read-only) so the dashboard can render + filter them."""
    enquiry = Enquiry.objects.create(
        guest=guest,
        first_name="C",
        last_name="D",
        email="c@d.com",
        status=EnquiryStatus.DEAD.value,
        lead_status=LeadStatus.HOT.value,
        lost_reason=EnquiryLostReason.AVAILABILITY.value,
    )
    api_client.force_login(staff)

    for payload in (
        api_client.get("/api/v1/enquiries").data["results"][0],
        api_client.get(f"/api/v1/enquiries/{enquiry.pk}").data,
    ):
        assert payload["lead_status"] == LeadStatus.HOT.value
        assert payload["lost_reason"] == EnquiryLostReason.AVAILABILITY.value


@pytest.mark.django_db
def test_enquiry_lead_status_is_read_only_on_write(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    """`lead_status` is mutated only via the audited :set-lead-status action; a
    plain PATCH must not change it (it isn't on the write serializer)."""
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/enquiries/{enquiry.pk}",
        {"lead_status": LeadStatus.HOT.value},
        format="json",
    )

    assert response.status_code == 200
    enquiry.refresh_from_db()
    assert enquiry.lead_status == LeadStatus.WARM.value  # unchanged (model default)


@pytest.mark.django_db
def test_list_enquiries__filter_by_lead_status(
    api_client: APIClient, staff: User, guest: Guest
) -> None:
    Enquiry.objects.create(guest=guest, email="warm@x.com")  # default warm
    hot = Enquiry.objects.create(guest=guest, email="hot@x.com", lead_status=LeadStatus.HOT.value)
    api_client.force_login(staff)

    response = api_client.get("/api/v1/enquiries", {"lead_status": LeadStatus.HOT.value})

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == hot.pk


@pytest.mark.django_db
def test_list_enquiries__filter_by_lost_reason(
    api_client: APIClient, staff: User, guest: Guest
) -> None:
    Enquiry.objects.create(guest=guest, email="open@x.com")
    dead = Enquiry.objects.create(
        guest=guest,
        email="dead@x.com",
        status=EnquiryStatus.DEAD.value,
        lost_reason=EnquiryLostReason.AVAILABILITY.value,
    )
    api_client.force_login(staff)

    response = api_client.get(
        "/api/v1/enquiries", {"lost_reason": EnquiryLostReason.AVAILABILITY.value}
    )

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == dead.pk


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
def test_create_enquiry__rejects_end_date_before_start_date(
    api_client: APIClient, staff: User, guest: Guest
) -> None:
    """When both dates are supplied, an inverted range is rejected with a
    field error on `date_to` (the SPA renders it beside the end-date input)."""
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/enquiries",
        {
            "guest": guest.pk,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@order.example.com",
            "adults": 2,
            "date_from": "2026-07-10",
            "date_to": "2026-07-05",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "date_to" in response.data["field_errors"]
    assert not Enquiry.objects.filter(email="ada@order.example.com").exists()


@pytest.mark.django_db
def test_create_enquiry__allows_start_date_without_end_date(
    api_client: APIClient, staff: User, guest: Guest
) -> None:
    """Enquiry dates are an optional, independent capture surface — a start with
    no end is a valid lead. Only an inverted range is rejected."""
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/enquiries",
        {
            "guest": guest.pk,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@openend.example.com",
            "adults": 2,
            "date_from": "2026-07-10",
        },
        format="json",
    )

    assert response.status_code == 201
    created = Enquiry.objects.get(email="ada@openend.example.com")
    assert created.date_from == date(2026, 7, 10)
    assert created.date_to is None


@pytest.mark.django_db
def test_create_enquiry__persists_flexibility_days(
    api_client: APIClient, staff: User, guest: Guest
) -> None:
    """`flexibility_days` is the structured "± N days" spread captured on the
    enquiry form. Dates stay the client's true requested dates; the quote
    search widens by this value instead of destructively shifting them."""
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/enquiries",
        {
            "guest": guest.pk,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@flex.example.com",
            "adults": 2,
            "date_from": "2026-07-10",
            "date_to": "2026-07-17",
            "flexibility_days": 2,
        },
        format="json",
    )

    assert response.status_code == 201
    created = Enquiry.objects.get(email="ada@flex.example.com")
    assert created.flexibility_days == 2
    assert created.date_from == date(2026, 7, 10)
    assert created.date_to == date(2026, 7, 17)
    assert response.data["flexibility_days"] == 2


@pytest.mark.django_db
def test_create_enquiry__flexibility_days_defaults_to_zero(
    api_client: APIClient, staff: User, guest: Guest
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/enquiries",
        {
            "guest": guest.pk,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@noflex.example.com",
            "adults": 2,
        },
        format="json",
    )

    assert response.status_code == 201
    created = Enquiry.objects.get(email="ada@noflex.example.com")
    assert created.flexibility_days == 0
    assert response.data["flexibility_days"] == 0


@pytest.mark.django_db
@pytest.mark.parametrize("value", [4, 99, -1])
def test_create_enquiry__rejects_out_of_range_flexibility_days(
    api_client: APIClient, staff: User, guest: Guest, value: int
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/enquiries",
        {
            "guest": guest.pk,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@badflex.example.com",
            "adults": 2,
            "flexibility_days": value,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "flexibility_days" in response.data["field_errors"]
    assert not Enquiry.objects.filter(email="ada@badflex.example.com").exists()


@pytest.mark.django_db
def test_update_enquiry__flexibility_days_round_trips(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/enquiries/{enquiry.pk}",
        {"flexibility_days": 3},
        format="json",
    )

    assert response.status_code == 200
    enquiry.refresh_from_db()
    assert enquiry.flexibility_days == 3
    assert response.data["flexibility_days"] == 3


@pytest.mark.django_db
def test_update_enquiry__rejects_end_before_existing_start(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    """A PATCH that sets only `date_to` is judged against the stored
    `date_from`, so a partial edit can't sneak in an inverted range."""
    enquiry.date_from = date(2026, 7, 10)
    enquiry.date_to = date(2026, 7, 17)
    enquiry.save(update_fields=["date_from", "date_to"])
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/enquiries/{enquiry.pk}",
        {"date_to": "2026-07-05"},
        format="json",
    )

    assert response.status_code == 400
    assert "date_to" in response.data["field_errors"]
    enquiry.refresh_from_db()
    assert enquiry.date_to == date(2026, 7, 17)


@pytest.mark.django_db
def test_update_enquiry__unrelated_patch_ignores_stored_inverted_dates(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    """The range check must judge only dates the caller is writing — a PATCH
    that touches neither date must not be rejected because of a pre-existing
    (e.g. legacy) inverted pair already stored on the row."""
    Enquiry.objects.filter(pk=enquiry.pk).update(
        date_from=date(2026, 7, 17), date_to=date(2026, 7, 10)
    )
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/enquiries/{enquiry.pk}",
        {"contact_method": ContactMethod.SMS.value},
        format="json",
    )

    assert response.status_code == 200
    enquiry.refresh_from_db()
    assert enquiry.contact_method == ContactMethod.SMS.value


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
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    q2 = Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
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
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
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
def test_enquiry_detail_quote_stack_constant_query_count(
    api_client: APIClient,
    staff: User,
    enquiry: Enquiry,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """The merged workspace inlines the quote-stack, and each line serialises
    its property name + hero image. The detail prefetch must reach
    `lines__property__images` so the payload stays constant-query no matter how
    many quotes/lines hang off the enquiry — without it every line fires a
    property lookup plus a hero-image walk (the dedicated quotation endpoint
    already guards this; the enquiry workspace must too)."""
    PropertyImage.objects.create(
        property=property_,
        kind=ImageKind.HERO,
        image=SimpleUploadedFile("hero.jpg", b"x", content_type="image/jpeg"),
    )
    for q_offset in range(2):
        quotation = Quotation.objects.create(
            enquiry=enquiry,
            guest=guest,
            expires_at=timezone.now() + timedelta(days=7 + q_offset),
            terms_version=terms,
        )
        for line_offset in range(2):
            QuotationLine.objects.create(
                quotation=quotation,
                property=property_,
                currency=gbp,
                date_from=date(2026, 6, 10 + line_offset),
                date_to=date(2026, 6, 17 + line_offset),
                adults=2,
                total=Decimal("1400.00"),
            )
    # One held line — its `hold` must resolve from the prefetch cache, not a
    # per-line fallback query (the line serializer's `hold` field walks
    # `live_holds`).
    from reservations.services.quotations import QuotationService

    QuotationService.hold_line(QuotationLine.objects.order_by("pk")[0])
    api_client.force_login(staff)

    with assert_max_queries(9):
        response = api_client.get(f"/api/v1/enquiries/{enquiry.pk}")

    assert response.status_code == 200
    assert len(response.data["quotations"]) == 2
    assert all(len(row["lines"]) == 2 for row in response.data["quotations"])
    # Hero image resolved from the prefetch cache, not a per-line query.
    assert response.data["quotations"][0]["lines"][0]["hero_image_url"] is not None
    held = [
        row["hold"]
        for quotation_row in response.data["quotations"]
        for row in quotation_row["lines"]
        if row["hold"] is not None
    ]
    assert len(held) == 1


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
    assert enquiry.status == EnquiryStatus.DEAD.value
    # No structured reason supplied → defaults to UNKNOWN (constraint-safe).
    assert enquiry.lost_reason == EnquiryLostReason.UNKNOWN.value


@pytest.mark.django_db
def test_close_enquiry__stores_structured_lost_reason(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/enquiries/{enquiry.pk}:close",
        {"reason": "found a villa with a pool", "lost_reason": "found_alternative"},
        format="json",
    )

    assert response.status_code == 200
    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.DEAD.value
    assert enquiry.lost_reason == EnquiryLostReason.FOUND_ALTERNATIVE.value


@pytest.mark.django_db
def test_close_enquiry__rejects_unknown_lost_reason(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/enquiries/{enquiry.pk}:close",
        {"lost_reason": "not_a_real_reason"},
        format="json",
    )

    assert response.status_code == 400
    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.NEW.value  # unchanged


@pytest.mark.django_db
def test_set_lead_status__updates_field_and_writes_event(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    """`:set-lead-status` mutates the temperature through the audited model
    method (writing a LEAD_STATUS_CHANGED event) and returns the detail shape."""
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/enquiries/{enquiry.pk}:set-lead-status",
        {"lead_status": LeadStatus.HOT.value},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["lead_status"] == LeadStatus.HOT.value
    assert "quotations" in response.data  # detail shape, not the bare instance
    enquiry.refresh_from_db()
    assert enquiry.lead_status == LeadStatus.HOT.value
    assert EnquiryEvent.objects.filter(enquiry=enquiry, kind="lead_status_changed").count() == 1


@pytest.mark.django_db
def test_set_lead_status__rejects_invalid_value(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    """An unknown value is rejected with 400 (not surfaced as the model's 500
    ValueError); the row and timeline are untouched."""
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/enquiries/{enquiry.pk}:set-lead-status",
        {"lead_status": "banana"},
        format="json",
    )

    assert response.status_code == 400
    enquiry.refresh_from_db()
    assert enquiry.lead_status == LeadStatus.WARM.value  # unchanged default
    assert not EnquiryEvent.objects.filter(enquiry=enquiry, kind="lead_status_changed").exists()


@pytest.mark.django_db
def test_set_lead_status__noop_when_unchanged(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    """Re-setting the current value returns 200 without padding the timeline."""
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/enquiries/{enquiry.pk}:set-lead-status",
        {"lead_status": LeadStatus.WARM.value},  # already the model default
        format="json",
    )

    assert response.status_code == 200
    assert not EnquiryEvent.objects.filter(enquiry=enquiry, kind="lead_status_changed").exists()


@pytest.mark.django_db
def test_set_lead_status__requires_writer(
    api_client: APIClient, viewer: User, enquiry: Enquiry
) -> None:
    api_client.force_login(viewer)

    response = api_client.post(
        f"/api/v1/enquiries/{enquiry.pk}:set-lead-status",
        {"lead_status": LeadStatus.HOT.value},
        format="json",
    )

    assert response.status_code == 403
    enquiry.refresh_from_db()
    assert enquiry.lead_status == LeadStatus.WARM.value


@pytest.mark.django_db
def test_activity_returns_event_timeline(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    enquiry.contact()
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/enquiries/{enquiry.pk}/activity")

    assert response.status_code == 200
    assert any(row["to_status"] == EnquiryStatus.PROGRESSING.value for row in response.data)


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
        status=EnquiryStatus.DEAD.value,
        lost_reason=EnquiryLostReason.UNKNOWN.value,
    )
    api_client.force_login(staff)

    response = api_client.get("/api/v1/enquiries/status-counts")

    assert response.status_code == 200
    assert response.data == {EnquiryStatus.NEW.value: 1, EnquiryStatus.DEAD.value: 1}


@pytest.mark.django_db
def test_enquiry_convert_rejects_foreign_quotation(
    api_client: APIClient,
    staff: User,
    enquiry: Enquiry,
    gbp: Currency,
    terms: TermsVersion,
    guest: Guest,
) -> None:
    """`:convert` must only accept a quotation belonging to *this* enquiry —
    citing another enquiry's quote would mark this one converted with an
    audit pointer at an unrelated quotation."""
    enquiry.contact()
    other_enquiry = Enquiry.objects.create(guest=guest, email=guest.email or "")
    foreign_quotation = Quotation.objects.create(
        enquiry=other_enquiry,
        guest=guest,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/enquiries/{enquiry.pk}:convert",
        {"quotation": foreign_quotation.pk},
        format="json",
    )

    assert response.status_code == 404
    enquiry.refresh_from_db()
    assert enquiry.status != EnquiryStatus.CONVERTED.value
