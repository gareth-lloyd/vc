"""API tests for the availability surface."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import Property
from reservations.enums import BookingHoldReason
from reservations.models.booking import BookingHold


@pytest.mark.django_db
def test_calendar_get_requires_from_and_to(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/availability")
    assert response.status_code == 400


@pytest.mark.django_db
def test_calendar_get_returns_cells(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.get(
        f"/api/v1/properties/{property_.pk}/availability?from=2026-06-01&to=2026-06-03"
    )
    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["property_id"] == property_.pk
    assert len(payload["cells"]) == 3


@pytest.mark.django_db
def test_calendar_cell_includes_block_id_for_manual(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    hold = BookingHold.objects.create(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 12),
        expires_at=timezone.now() + timedelta(days=30),
        reason=BookingHoldReason.MANUAL.value,
    )
    api_client.force_login(staff)
    response = api_client.get(
        f"/api/v1/properties/{property_.pk}/availability?from=2026-06-10&to=2026-06-11"
    )
    assert response.status_code == 200, response.content
    cells = {c["date"]: c for c in response.json()["cells"]}
    assert cells["2026-06-10"]["block_id"] == hold.pk
    assert cells["2026-06-10"]["reason"] == "manual"


@pytest.mark.django_db
def test_calendar_cell_links_quotation_hold_to_its_quotation(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """A quotation hold's cell carries `quotation_id` (read-only click-through)
    while `block_id` stays null — no edit affordance on system holds."""
    from datetime import UTC, datetime

    from reservations.models import Guest, Quotation, TermsVersion

    guest = Guest.objects.create(first_name="Cal", last_name="Endar", email="cal@example.com")
    terms = TermsVersion.objects.create(
        version="cal-test",
        body_markdown="**T&Cs**",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        is_current=True,
    )
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    BookingHold.objects.create(
        property=property_,
        quotation=quotation,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 12),
        expires_at=timezone.now() + timedelta(days=30),
        reason=BookingHoldReason.QUOTATION_OPEN.value,
    )
    api_client.force_login(staff)
    response = api_client.get(
        f"/api/v1/properties/{property_.pk}/availability?from=2026-06-10&to=2026-06-11"
    )
    assert response.status_code == 200, response.content
    cells = {c["date"]: c for c in response.json()["cells"]}
    assert cells["2026-06-10"]["reason"] == "quotation"
    assert cells["2026-06-10"]["block_id"] is None
    assert cells["2026-06-10"]["quotation_id"] == quotation.pk


@pytest.mark.django_db
def test_calendar_cell_includes_segments_on_changeover(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    from datetime import time

    from properties.models import PropertySettings

    PropertySettings.objects.update_or_create(
        property=property_,
        defaults={"check_out_time": time(10, 0), "check_in_time": time(16, 0)},
    )
    BookingHold.objects.create(
        property=property_,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 8),
        expires_at=timezone.now() + timedelta(days=30),
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )
    BookingHold.objects.create(
        property=property_,
        date_from=date(2026, 6, 8),
        date_to=date(2026, 6, 12),
        expires_at=timezone.now() + timedelta(days=30),
        reason=BookingHoldReason.MANUAL.value,
    )
    api_client.force_login(staff)
    response = api_client.get(
        f"/api/v1/properties/{property_.pk}/availability?from=2026-06-01&to=2026-06-15"
    )
    assert response.status_code == 200, response.content
    cells = {c["date"]: c for c in response.json()["cells"]}
    split = cells["2026-06-08"]
    assert split["segments"]["am"]["reason"] == "owner_block"
    assert split["segments"]["pm"]["reason"] == "manual"
    assert "segments" not in cells["2026-06-05"]


@pytest.mark.django_db
def test_post_creates_manual_hold(api_client: APIClient, staff: User, property_: Property) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/availability",
        data={
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "reason": BookingHoldReason.OWNER_BLOCK.value,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    assert BookingHold.objects.filter(property=property_).count() == 1


@pytest.mark.django_db
def test_post_block_persists_notes(api_client: APIClient, staff: User, property_: Property) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/availability",
        data={
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "reason": BookingHoldReason.OWNER_BLOCK.value,
            "notes": "Owner staying with family",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    hold = BookingHold.objects.get(property=property_)
    assert hold.notes == "Owner staying with family"
    assert response.json()["notes"] == "Owner staying with family"


@pytest.mark.django_db
def test_extend_hold_action(api_client: APIClient, staff: User, property_: Property) -> None:
    hold = BookingHold.objects.create(
        property=property_,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 7),
        expires_at=timezone.now() + timedelta(days=1),
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )
    new_expiry = timezone.now() + timedelta(days=60)
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/availability/{hold.pk}:extend-hold",
        data={"expires_at": new_expiry.isoformat()},
        format="json",
    )
    assert response.status_code == 200, response.content
    hold.refresh_from_db()
    assert hold.expires_at is not None
    assert abs((hold.expires_at - new_expiry).total_seconds()) < 5


@pytest.mark.django_db
def test_extend_hold_rejects_indefinite_block(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """An indefinite (NULL-expiry) owner block has no expiry to extend.

    Writing a finite `expires_at` would make `expire_holds` reap a block the
    owner reserved and an operator approved — so extend-hold must refuse it and
    leave the hold indefinite. Releasing is the correct way to remove it.
    """
    hold = BookingHold.objects.create(
        property=property_,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 7),
        expires_at=None,
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/availability/{hold.pk}:extend-hold",
        data={"expires_at": (timezone.now() + timedelta(days=60)).isoformat()},
        format="json",
    )
    assert response.status_code == 409, response.content
    assert response.json()["code"] == "read_only_hold"
    hold.refresh_from_db()
    assert hold.expires_at is None


@pytest.mark.django_db
def test_release_hold_action(api_client: APIClient, staff: User, property_: Property) -> None:
    hold = BookingHold.objects.create(
        property=property_,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 7),
        expires_at=timezone.now() + timedelta(days=10),
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/availability/{hold.pk}:release-hold")
    assert response.status_code == 200
    hold.refresh_from_db()
    assert hold.released_at is not None


def _system_quotation_hold(property_: Property) -> BookingHold:
    """A read-only hold backed by an open quotation (not operator-editable)."""
    from datetime import timedelta

    from reservations.models import Guest, Quotation, TermsVersion

    guest = Guest.objects.create(first_name="Ada", last_name="Lovelace", email="ada@x.com")
    terms = TermsVersion.objects.create(
        version="2026-01", body_markdown="x", published_at=timezone.now(), is_current=True
    )
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    return BookingHold.objects.create(
        property=property_,
        quotation=quotation,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 7),
        expires_at=timezone.now() + timedelta(days=5),
        reason=BookingHoldReason.QUOTATION_OPEN.value,
    )


@pytest.mark.django_db
def test_post_overlapping_block_returns_409(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    BookingHold.objects.create(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() + timedelta(days=30),
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/availability",
        data={
            "date_from": "2026-06-12",
            "date_to": "2026-06-14",
            "reason": BookingHoldReason.MAINTENANCE.value,
        },
        format="json",
    )
    assert response.status_code == 409, response.content
    assert response.json()["code"] == "hold_unavailable"


@pytest.mark.django_db
def test_patch_manual_block_updates_dates_and_notes(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    hold = BookingHold.objects.create(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() + timedelta(days=30),
        reason=BookingHoldReason.MANUAL.value,
        notes="old",
    )
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/availability/{hold.pk}",
        data={"date_from": "2026-06-11", "date_to": "2026-06-15", "notes": "new note"},
        format="json",
    )
    assert response.status_code == 200, response.content
    hold.refresh_from_db()
    assert hold.date_from == date(2026, 6, 11)
    assert hold.date_to == date(2026, 6, 15)
    assert hold.notes == "new note"


@pytest.mark.django_db
def test_patch_manual_block_overlap_returns_409(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    BookingHold.objects.create(
        property=property_,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        expires_at=timezone.now() + timedelta(days=30),
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )
    target = BookingHold.objects.create(
        property=property_,
        date_from=date(2026, 7, 20),
        date_to=date(2026, 7, 25),
        expires_at=timezone.now() + timedelta(days=30),
        reason=BookingHoldReason.MANUAL.value,
    )
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/availability/{target.pk}",
        data={"date_from": "2026-07-03", "date_to": "2026-07-06"},
        format="json",
    )
    assert response.status_code == 409, response.content
    assert response.json()["code"] == "hold_unavailable"


@pytest.mark.django_db
def test_patch_system_hold_is_forbidden(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    hold = _system_quotation_hold(property_)
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/availability/{hold.pk}",
        data={"date_to": "2026-06-09"},
        format="json",
    )
    assert response.status_code == 409, response.content
    assert response.json()["code"] == "read_only_hold"


@pytest.mark.django_db
def test_delete_system_hold_is_forbidden(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    hold = _system_quotation_hold(property_)
    api_client.force_login(staff)
    response = api_client.delete(f"/api/v1/availability/{hold.pk}")
    assert response.status_code == 409, response.content
    assert response.json()["code"] == "read_only_hold"
    hold.refresh_from_db()
    assert hold.released_at is None


@pytest.mark.django_db
def test_availability_search(api_client: APIClient, staff: User, property_: Property) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/availability:search",
        data={
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 2,
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    results = response.json()["results"]
    assert any(r["property_id"] == property_.pk for r in results)
