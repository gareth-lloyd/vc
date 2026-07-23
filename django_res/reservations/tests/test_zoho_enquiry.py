"""Tests for the Enquiry → Zoho Flow push (GAP-081 Unit 2).

The `Enquiry` model is registered by `reservations.apps.ready()`; these tests
NEVER unregister it (xdist worker leak) — behaviour is toggled via
`override_settings(ZOHO_FLOW_WEBHOOKS=…)`.
"""

from __future__ import annotations

import json
from typing import Any, cast
from unittest import mock

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings

from accounts.factories import CustomerPersonFactory, PersonFactory, UserFactory
from accounts.models import Organisation, Person, User
from integrations import tasks
from integrations.enums import SyncProvider, SyncStatus
from integrations.models import SyncRecord
from integrations.services.zoho_flow import get_zoho_spec
from reservations.enums import EnquiryLostReason, EnquiryNoteKind, EnquiryStatus, LeadStatus
from reservations.factories import EnquiryFactory
from reservations.models import Enquiry
from reservations.models.enquiry import EnquiryNote
from reservations.services.zoho_payload import build_enquiry_payload

ENQUIRY_URL = "https://flow.zoho.example/enquiry"
WEBHOOKS = {"contact": "", "enquiry": ENQUIRY_URL, "quote": "", "booking": ""}


def _enquiry(**kwargs: Any) -> Enquiry:
    return cast(Enquiry, EnquiryFactory(**kwargs))


def _enquiry_ct() -> ContentType:
    return ContentType.objects.get_for_model(Enquiry)


def _record_for(enquiry: Enquiry) -> SyncRecord:
    return SyncRecord.objects.get(
        content_type=_enquiry_ct(),
        object_id=enquiry.pk,
        provider=SyncProvider.ZOHO_CRM.value,
    )


@pytest.fixture
def enquiry_webhook() -> Any:
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        yield


@pytest.fixture
def delay_mock(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    m = mock.Mock()
    monkeypatch.setattr(tasks.push_sync_record, "delay", m)
    return m


# --- registration ---------------------------------------------------------


def test_enquiry_is_registered_by_app_ready() -> None:
    spec = get_zoho_spec(Enquiry)
    assert spec is not None
    assert spec.kind == "enquiry"
    assert spec.auto_push is True
    assert spec.build_payload is build_enquiry_payload


# --- payload --------------------------------------------------------------


@pytest.mark.django_db
def test_payload_has_res_id_and_core_fields() -> None:
    enquiry = _enquiry(adults=4, children=2, min_bedrooms=3)
    payload = build_enquiry_payload(enquiry)

    assert payload["RES_ID"] == enquiry.pk
    assert payload["id"] == enquiry.pk
    assert payload["reference"] == enquiry.reference
    assert payload["adults"] == 4
    assert payload["children"] == 2
    assert payload["min_bedrooms"] == 3
    assert payload["status"] == EnquiryStatus.NEW.value
    assert payload["lead_status"] == LeadStatus.WARM.value
    assert payload["lost_reason"] == ""
    assert enquiry.date_from is not None and enquiry.date_to is not None
    assert payload["date_from"] == enquiry.date_from.isoformat()
    assert payload["date_to"] == enquiry.date_to.isoformat()
    assert payload["nights"] == 7
    assert payload["site_source"] == enquiry.site_source
    assert payload["request_type"] == enquiry.request_type
    assert payload["inbound_message"] == enquiry.inbound_message


@pytest.mark.django_db
def test_payload_covers_zoho_enquiry_post_data_minimums() -> None:
    """`ZohoEnquiryPostData` (legacy zoho-crm.md ~line 73) mapped onto current
    models, snake_case: Name→full_name, Date_From/To→date_from/to,
    Length_of_Stay→nights, Bedrooms_From/To→min_bedrooms,
    Number_of_Adults/Children→adults/children, Stage→status(+lead_status),
    Agency/Agent→agent, Enquiry_Notes→inbound_message,
    Enquiry_Source→site_source, Regions/Countries_of_Interest→region,
    Where_did_you_hear_from_us→referral_code, Contact→person, Villa→property.
    Zoho_ID and the hardcoded Owner email have no current-model equivalent."""
    payload = build_enquiry_payload(_enquiry())
    minimum = {
        "RES_ID",
        "id",
        "full_name",
        "date_from",
        "date_to",
        "nights",
        "min_bedrooms",
        "adults",
        "children",
        "status",
        "lead_status",
        "agent",
        "inbound_message",
        "site_source",
        "region",
        "referral_code",
        "person",
        "property",
        "assigned_to",
    }
    assert minimum <= payload.keys()


@pytest.mark.django_db
def test_payload_person_sub_object() -> None:
    person = cast(
        Person,
        CustomerPersonFactory(
            first_name="Ada",
            last_name="Lovelace",
            primary_email="ada@example.com",
            primary_phone="+447700900001",
        ),
    )
    enquiry = _enquiry(person=person)
    payload = build_enquiry_payload(enquiry)

    sub = payload["person"]
    assert sub["RES_ID"] == person.pk
    assert sub["id"] == person.pk
    assert sub["full_name"] == "Ada Lovelace"
    assert sub["primary_email"] == "ada@example.com"
    assert sub["primary_phone"] == "+447700900001"
    assert payload["full_name"] == "Ada Lovelace"


@pytest.mark.django_db
def test_payload_property_and_region_sub_objects() -> None:
    enquiry = _enquiry()
    prop = enquiry.property
    assert prop is not None
    payload = build_enquiry_payload(enquiry)

    sub = payload["property"]
    assert sub["RES_ID"] == prop.pk
    assert sub["id"] == prop.pk
    assert sub["name"] == prop.name
    assert sub["region"]["RES_ID"] == prop.region_id
    assert sub["region"]["country"]["iso2"] == prop.region.country.iso2


@pytest.mark.django_db
def test_payload_assigned_to_sub_object() -> None:
    staff = cast(User, UserFactory(first_name="Olivia", last_name="Operator"))
    enquiry = _enquiry(assigned_to=staff)
    payload = build_enquiry_payload(enquiry)

    sub = payload["assigned_to"]
    assert sub["id"] == staff.pk
    assert sub["full_name"] == "Olivia Operator"
    assert sub["email"] == staff.email


@pytest.mark.django_db
def test_payload_assigned_to_none_when_unassigned() -> None:
    payload = build_enquiry_payload(_enquiry(assigned_to=None))
    assert payload["assigned_to"] is None


@pytest.mark.django_db
def test_payload_agent_sub_object() -> None:
    agent = cast(Person, PersonFactory(first_name="Alex", last_name="Agent"))
    enquiry = _enquiry(agent=agent)
    payload = build_enquiry_payload(enquiry)

    sub = payload["agent"]
    assert sub["RES_ID"] == agent.pk
    assert sub["full_name"] == "Alex Agent"
    assert sub["agency"] is None


@pytest.mark.django_db
def test_payload_agent_carries_keyed_agency_sub_object() -> None:
    """`agency_name` alone gives Flow nothing to key-join on — the summary
    also carries a {RES_ID, id, name} agency sub-object (user decision
    2026-07-23)."""
    org = Organisation.objects.create(name="Acme Travel")
    agent = cast(Person, PersonFactory(first_name="Alex", last_name="Agent", agency=org))
    enquiry = _enquiry(agent=agent)
    payload = build_enquiry_payload(enquiry)

    sub = payload["agent"]
    assert sub["agency_name"] == "Acme Travel"
    assert sub["agency"] == {"RES_ID": org.pk, "id": org.pk, "name": "Acme Travel"}


@pytest.mark.django_db
def test_payload_notes_list() -> None:
    staff = cast(User, UserFactory(first_name="Olivia", last_name="Operator"))
    enquiry = _enquiry()
    first = EnquiryNote.objects.create(
        enquiry=enquiry,
        author=staff,
        kind=EnquiryNoteKind.GENERAL,
        body="called back, chasing dates",
        is_pinned=True,
    )
    second = EnquiryNote.objects.create(enquiry=enquiry, author=None, body="prefers August")

    payload = build_enquiry_payload(enquiry)

    notes = payload["notes"]
    # RES_ID is the Zoho-side dedupe key for note rows.
    assert [n["RES_ID"] for n in notes] == [first.pk, second.pk]
    head = notes[0]
    assert head["id"] == first.pk
    assert head["kind"] == EnquiryNoteKind.GENERAL.value
    assert head["body"] == "called back, chasing dates"
    assert head["is_pinned"] is True
    assert head["author"]["id"] == staff.pk
    assert head["author"]["full_name"] == "Olivia Operator"
    assert notes[1]["author"] is None
    assert json.loads(json.dumps(payload)) == payload


@pytest.mark.django_db
def test_payload_blanks_notes_when_person_anonymized() -> None:
    """Operator free text routinely names the guest and cannot be selectively
    scrubbed — mirror the capture-column blanking and push no notes at all
    once the linked person is erased."""
    person = cast(Person, CustomerPersonFactory())
    enquiry = _enquiry(person=person)
    EnquiryNote.objects.create(enquiry=enquiry, body="guest wants ground-floor room")
    person.anonymize()
    enquiry.refresh_from_db()

    payload = build_enquiry_payload(enquiry)

    assert payload["notes"] == []


@pytest.mark.django_db
def test_payload_handles_anonymous_enquiry() -> None:
    enquiry = _enquiry(
        person=None,
        property=None,
        region=None,
        date_from=None,
        date_to=None,
        first_name="Walk",
        last_name="In",
        email="walkin@example.com",
        phone="+441603000000",
    )
    payload = build_enquiry_payload(enquiry)

    assert payload["person"] is None
    assert payload["property"] is None
    assert payload["region"] is None
    assert payload["agent"] is None
    assert payload["date_from"] is None
    assert payload["nights"] is None
    assert payload["full_name"] == "Walk In"
    assert payload["email"] == "walkin@example.com"
    assert payload["phone"] == "+441603000000"
    assert json.loads(json.dumps(payload)) == payload


@pytest.mark.django_db
def test_payload_anonymized_person_fails_closed() -> None:
    """After `Person.anonymize()` the payload must leak NEITHER the person
    sub-object's [REDACTED] sentinels NOR the enquiry's own denormalised
    capture columns (which the erasure flow does not scrub) — the payload
    blanks them when the linked person is anonymized."""
    person = cast(Person, CustomerPersonFactory())
    enquiry = _enquiry(
        person=person,
        first_name="Erased",
        last_name="Subject",
        email="erased.subject@example.com",
        phone="+447700900666",
    )
    person.anonymize()
    enquiry.refresh_from_db()

    payload = build_enquiry_payload(enquiry)

    assert payload["person"] is None
    blob = json.dumps(payload)
    assert "[REDACTED]" not in blob
    assert "Erased" not in blob
    assert "Subject" not in blob
    assert "erased.subject@example.com" not in blob
    assert "+447700900666" not in blob
    assert payload["full_name"] == ""


@pytest.mark.django_db
def test_payload_json_round_trips() -> None:
    payload = build_enquiry_payload(_enquiry())
    assert json.loads(json.dumps(payload)) == payload


@pytest.mark.django_db
def test_payload_lost_reason_after_lose() -> None:
    enquiry = _enquiry()
    enquiry.lose(lost_reason=EnquiryLostReason.AVAILABILITY.value)
    payload = build_enquiry_payload(enquiry)

    assert payload["status"] == EnquiryStatus.DEAD.value
    assert payload["lost_reason"] == EnquiryLostReason.AVAILABILITY.value


# --- enqueue wiring -------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately", "enquiry_webhook")
def test_create_enqueues_pending_record_and_dispatches(delay_mock: mock.Mock) -> None:
    enquiry = _enquiry()

    record = _record_for(enquiry)
    assert record.status == SyncStatus.PENDING
    delay_mock.assert_any_call(record.pk)


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately", "enquiry_webhook", "delay_mock")
def test_set_lead_status_bumps_pending() -> None:
    enquiry = _enquiry()
    record = _record_for(enquiry)
    record.status = SyncStatus.IN_SYNC.value
    record.save(update_fields=["status", "updated_at"])

    enquiry.set_lead_status(LeadStatus.HOT.value)

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately", "enquiry_webhook", "delay_mock")
def test_lose_transition_bumps_pending() -> None:
    enquiry = _enquiry()
    record = _record_for(enquiry)
    record.status = SyncStatus.IN_SYNC.value
    record.save(update_fields=["status", "updated_at"])

    enquiry.lose(lost_reason=EnquiryLostReason.AVAILABILITY.value)

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately")
def test_unset_url_is_full_noop(delay_mock: mock.Mock) -> None:
    enquiry = _enquiry()

    assert not SyncRecord.objects.filter(content_type=_enquiry_ct(), object_id=enquiry.pk).exists()
    delay_mock.assert_not_called()


# --- person_merged --------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately")
def test_person_merge_re_enqueues_repointed_enquiries(delay_mock: mock.Mock) -> None:
    survivor = cast(Person, CustomerPersonFactory())
    absorbed = cast(Person, CustomerPersonFactory())
    as_customer = _enquiry(person=absorbed)
    as_agent = _enquiry(person=None, agent=absorbed)

    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        absorbed.merge(survivor)

    assert _record_for(as_customer).status == SyncStatus.PENDING
    assert _record_for(as_agent).status == SyncStatus.PENDING
