"""GAP-112: `relink_enquiry_customers` — the post-sheet-import pass that moves
customer-less legacy enquiries (and the quotations / preferences that fell to
the unknown-client sentinel with them) onto the person the sheet import minted.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from typing import cast

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from accounts.models import Person, PersonEmail
from core.models import AuditLog
from data_migration.loaders.finance import _ensure_default_terms
from data_migration.loaders.sentinels import unknown_client
from integrations.models import SyncRecord
from reservations.factories import EnquiryFactory
from reservations.models import Enquiry, GuestPreference, GuestPreferenceType, Quotation

pytestmark = pytest.mark.django_db


def _run(*args: str) -> str:
    out = StringIO()
    call_command("relink_enquiry_customers", *args, stdout=out)
    return out.getvalue()


def _person(first: str, last: str, email: str) -> Person:
    person = Person.objects.create(first_name=first, last_name=last, legacy_id=f"sheet-{email}")
    PersonEmail.objects.create(contact=person, email=email, is_primary=True)
    return person


def _enquiry(
    email: str = "ada@example.com", legacy_id: str | None = "101", person: Person | None = None
) -> Enquiry:
    return cast(
        Enquiry,
        EnquiryFactory(
            person=person,
            first_name="Ada",
            last_name="Lovelace",
            email=email,
            legacy_id=legacy_id,
        ),
    )


def _quotation(enquiry: Enquiry, person: Person | None = None) -> Quotation:
    return Quotation.objects.create(
        enquiry=enquiry,
        person=person or unknown_client(),
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=_ensure_default_terms(),
        legacy_id=f"q-{Quotation.objects.count() + 1}",
    )


def _preference(quotation: Quotation, person: Person | None = None) -> GuestPreference:
    kind, _ = GuestPreferenceType.objects.get_or_create(name="Late checkout")
    return GuestPreference.objects.create(
        person=person or unknown_client(), preference_type=kind, quotation=quotation
    )


def _audited_fields(obj: Enquiry | Quotation) -> list[str]:
    ct = ContentType.objects.get_for_model(type(obj))
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(obj.pk))
    return [field for row in rows for field in row.field_diffs]


def test_relinks_the_enquiry_and_its_sentinel_quotation_with_an_audit_trail() -> None:
    ada = _person("Ada", "Lovelace", "ada@example.com")
    enquiry = _enquiry()
    quotation = _quotation(enquiry)

    out = _run()

    enquiry.refresh_from_db()
    quotation.refresh_from_db()
    assert enquiry.person == ada
    assert quotation.person == ada
    assert "person_id" in _audited_fields(enquiry)
    assert "person_id" in _audited_fields(quotation)
    assert "enquiry" in out and "quotation" in out


@pytest.mark.parametrize(
    ("email", "category"),
    [
        ("shared@example.com", "shared_email"),
        ("byron@example.com", "names_disagree"),
        ("nobody@example.com", "unmatched"),
        ("", "no_email"),
    ],
)
def test_ambiguous_and_unresolvable_rows_are_reported_and_untouched(
    email: str, category: str
) -> None:
    _person("Ada", "Lovelace", "shared@example.com")
    _person("Charles", "Babbage", "shared@example.com")
    _person("Ada", "Byron", "byron@example.com")
    enquiry = _enquiry(email=email)
    quotation = _quotation(enquiry)

    out = _run()

    enquiry.refresh_from_db()
    quotation.refresh_from_db()
    assert enquiry.person is None
    assert quotation.person == unknown_client()
    assert f"enquiry: {category}" in out
    assert f"quotation: {category}" in out


def test_a_quotation_on_a_real_client_is_never_repointed() -> None:
    _person("Ada", "Lovelace", "ada@example.com")
    client = Person.objects.create(first_name="Grace", last_name="Hopper", legacy_id="client-9")
    enquiry = _enquiry()
    quotation = _quotation(enquiry, person=client)

    _run()

    quotation.refresh_from_db()
    assert quotation.person == client


def test_a_sentinel_quotation_whose_enquiry_is_already_linked_follows_it() -> None:
    # QuotationLoader back-fills Enquiry.person from a later quotation (q.Id
    # order), which can leave an earlier quotation on the sentinel.
    grace = Person.objects.create(first_name="Grace", last_name="Hopper", legacy_id="client-9")
    enquiry = _enquiry(person=grace)
    quotation = _quotation(enquiry)

    out = _run()

    quotation.refresh_from_db()
    assert quotation.person == grace
    assert "quotation (enquiry already linked)" in out


def test_a_quotation_whose_enquiry_is_itself_on_the_sentinel_is_left_alone() -> None:
    # A booking stand-in for an unloaded client puts both rows on the sentinel.
    sentinel = unknown_client()
    _preference(_quotation(_enquiry(email="", person=sentinel)))

    out = _run()

    assert "updated" not in out
    assert "conflict" not in out


@pytest.mark.parametrize("legacy_id", [None, "sheet-enquiry-7"])
def test_enquiries_the_legacy_loader_did_not_write_are_ignored(legacy_id: str | None) -> None:
    _person("Ada", "Lovelace", "ada@example.com")
    enquiry = _enquiry(legacy_id=legacy_id)

    _run()

    enquiry.refresh_from_db()
    assert enquiry.person is None


def test_a_sentinel_preference_follows_its_relinked_quotation() -> None:
    ada = _person("Ada", "Lovelace", "ada@example.com")
    preference = _preference(_quotation(_enquiry()))

    _run()

    preference.refresh_from_db()
    assert preference.person == ada


def test_a_preference_that_would_collide_stays_on_the_sentinel_and_is_reported() -> None:
    ada = _person("Ada", "Lovelace", "ada@example.com")
    quotation = _quotation(_enquiry())
    preference = _preference(quotation)
    _preference(quotation, person=ada)  # the same preference already on Ada

    out = _run()

    preference.refresh_from_db()
    assert preference.person == unknown_client()
    assert "guest_preference: conflict" in out


def test_a_sentinel_preference_on_an_unmoved_quotation_stays() -> None:
    # The loader may have refused to borrow a quotation's real client
    # (GAP-108 U8d); only quotations this pass moves carry their preferences.
    client = Person.objects.create(first_name="Grace", last_name="Hopper", legacy_id="client-9")
    preference = _preference(_quotation(_enquiry(email=""), person=client))

    _run()

    preference.refresh_from_db()
    assert preference.person == unknown_client()


def test_a_second_run_changes_nothing() -> None:
    _person("Ada", "Lovelace", "ada@example.com")
    _preference(_quotation(_enquiry()))
    _run()
    audit_rows = AuditLog.objects.count()

    out = _run()

    assert AuditLog.objects.count() == audit_rows
    assert "updated" not in out


def test_dry_run_rolls_back() -> None:
    _person("Ada", "Lovelace", "ada@example.com")
    enquiry = _enquiry()
    quotation = _quotation(enquiry)

    out = _run("--dry-run")

    enquiry.refresh_from_db()
    quotation.refresh_from_db()
    assert enquiry.person is None
    assert quotation.person == unknown_client()
    assert "[dry-run]" in out


def test_no_zoho_push_is_queued() -> None:
    _person("Ada", "Lovelace", "ada@example.com")
    enquiry = _enquiry()
    records = SyncRecord.objects.count()

    with override_settings(ZOHO_FLOW_WEBHOOKS={"enquiry": "https://flow.example/enquiry"}):
        _run()

    enquiry.refresh_from_db()
    assert enquiry.person is not None
    assert SyncRecord.objects.count() == records
