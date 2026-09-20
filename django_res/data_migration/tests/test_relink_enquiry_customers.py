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

from accounts.enums import PersonKind, PersonStatus
from accounts.models import Person, PersonEmail
from core.models import AuditLog
from data_migration.loaders.finance import _ensure_default_terms
from data_migration.loaders.sentinels import (
    ENQUIRY_PERSON_LEGACY_PREFIX,
    unknown_client,
)
from data_migration.relink import enquiry_person_legacy_id
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


# --- GAP-118 §3: `--mint-unmatched` mints a customer per unmatched address ---


def _named(first: str, last: str, *, legacy_id: str, phone: str = "") -> Enquiry:
    return cast(
        Enquiry,
        EnquiryFactory(
            person=None,
            first_name=first,
            last_name=last,
            email="nobody@example.com",
            phone=phone,
            legacy_id=legacy_id,
        ),
    )


def _anonymous(*, legacy_id: str) -> Enquiry:
    """`EnquiryLoader` stores `(anon)` for a legacy row with no name."""
    return _named("(anon)", "", legacy_id=legacy_id)


def _minted() -> list[Person]:
    return list(Person.objects.filter(legacy_id__startswith=ENQUIRY_PERSON_LEGACY_PREFIX))


def test_mint_is_opt_in() -> None:
    """The cutover runs this pass twice; minting on the first run would create
    people `import_archive_stays` is about to mint properly (GAP-112's own
    "why not in GAP-108" objection). So the default stays relink-only."""
    enquiry = _enquiry(email="nobody@example.com")

    out = _run()

    enquiry.refresh_from_db()
    assert enquiry.person is None
    assert _minted() == []
    assert "enquiry: unmatched" in out


def test_mint_creates_one_customer_and_moves_its_sentinel_quotation() -> None:
    enquiry = _enquiry(email="nobody@example.com")
    quotation = _quotation(enquiry)

    _run("--mint-unmatched")

    enquiry.refresh_from_db()
    quotation.refresh_from_db()
    person = enquiry.person
    assert person is not None
    assert person.legacy_id == enquiry_person_legacy_id("nobody@example.com")
    assert (person.kind, person.status) == (PersonKind.CUSTOMER, PersonStatus.ACTIVE)
    assert (person.first_name, person.last_name) == ("Ada", "Lovelace")
    assert person.emails.get(is_primary=True).email == "nobody@example.com"
    # The quotation must follow in the SAME run, or reconcile_legacy's
    # "relinkable sentinel quotation" invariant (must be 0) goes RED.
    assert quotation.person == person
    assert "person_id" in _audited_fields(enquiry)


def test_enquiries_sharing_an_unmatched_address_mint_one_person() -> None:
    first = _enquiry(email="nobody@example.com", legacy_id="101")
    second = _enquiry(email="nobody@example.com", legacy_id="102")

    _run("--mint-unmatched")

    first.refresh_from_db()
    second.refresh_from_db()
    assert len(_minted()) == 1
    assert first.person == second.person


def test_the_minted_name_comes_from_the_lowest_id_enquiry_carrying_one() -> None:
    _anonymous(legacy_id="101")
    _named("Grace", "Hopper", legacy_id="102")
    _named("Ada", "Lovelace", legacy_id="103")

    _run("--mint-unmatched")

    person = _minted()[0]
    assert (person.first_name, person.last_name) == ("Grace", "Hopper")


def test_the_minted_phone_is_taken_independently_of_the_name() -> None:
    """The name comes from the first enquiry that HAS one; the phone must not
    ride along with that pick. Both sheet importers guard on
    `not person.phones.exists()` (`sheets/import_enquiry_sheet.py:177`), so a
    number dropped here is never added later."""
    _named("(anon)", "", legacy_id="101", phone="+441234567890")
    _named("Grace", "Hopper", legacy_id="102")

    _run("--mint-unmatched")

    person = _minted()[0]
    assert (person.first_name, person.last_name) == ("Grace", "Hopper")
    assert person.phones.get(is_primary=True).number == "+441234567890"


def test_the_anon_placeholder_is_never_written_as_a_first_name() -> None:
    """`(anon)` is the loader's placeholder, not a name — `_has_name` says so
    for the row as a whole, and the field pick must say it per field or a
    `(anon) Smith` customer lands in the staff lists."""
    _named("(anon)", "Smith", legacy_id="101")

    _run("--mint-unmatched")

    person = _minted()[0]
    assert (person.first_name, person.last_name) == ("", "Smith")


def test_a_wholly_anonymous_group_falls_back_to_the_address() -> None:
    """`find_or_create_person`'s rule (`sheets/matching.py:424-426`): a
    nameless Person renders as "Client #id", so the address stands in."""
    _anonymous(legacy_id="101")
    _anonymous(legacy_id="102")

    _run("--mint-unmatched")

    person = _minted()[0]
    assert (person.first_name, person.last_name) == ("nobody@example.com", "")


def test_names_that_disagree_on_one_address_are_minted_once_and_reported() -> None:
    """The address IS the grouping (a shared address with a real holder is
    `shared_email` and never reaches here), so two names mint ONE person —
    but the name not taken must be visible, not silently dropped."""
    _named("Grace", "Hopper", legacy_id="101")
    _named("Alan", "Turing", legacy_id="102")

    out = _run("--mint-unmatched")

    assert len(_minted()) == 1
    assert "name not used (address carries several)" in out


def test_a_case_variant_holder_is_relinked_not_duplicated() -> None:
    """Minting for an address somebody already holds would be the one way this
    pass could duplicate a real person. It cannot: `PersonEmail.email` is a
    `CIEmailField` (lowercased on write, citext), so `classify_enquiry`'s
    lookup is case-insensitive and a mixed-case holder reads as `relinked`."""
    ada = _person("Ada", "Lovelace", "Nobody@Example.com")
    enquiry = _enquiry(email="nobody@example.com")

    _run("--mint-unmatched")

    enquiry.refresh_from_db()
    assert enquiry.person == ada
    assert _minted() == []


@pytest.mark.parametrize(
    ("email", "category"),
    [
        ("shared@example.com", "shared_email"),
        ("byron@example.com", "names_disagree"),
        ("", "no_email"),
    ],
)
def test_mint_never_touches_the_ambiguous_categories(email: str, category: str) -> None:
    _person("Ada", "Lovelace", "shared@example.com")
    _person("Charles", "Babbage", "shared@example.com")
    _person("Ada", "Byron", "byron@example.com")
    enquiry = _enquiry(email=email)

    out = _run("--mint-unmatched")

    enquiry.refresh_from_db()
    assert enquiry.person is None
    assert _minted() == []
    assert f"enquiry: {category}" in out


def test_a_second_mint_run_changes_nothing() -> None:
    _quotation(_enquiry(email="nobody@example.com"))
    _run("--mint-unmatched")
    audit_rows = AuditLog.objects.count()

    out = _run("--mint-unmatched")

    assert len(_minted()) == 1
    assert AuditLog.objects.count() == audit_rows
    assert "updated" not in out


def test_mint_dry_run_rolls_back() -> None:
    enquiry = _enquiry(email="nobody@example.com")

    out = _run("--mint-unmatched", "--dry-run")

    enquiry.refresh_from_db()
    assert enquiry.person is None
    assert _minted() == []
    assert "[dry-run]" in out


def test_mint_queues_no_zoho_push() -> None:
    enquiry = _enquiry(email="nobody@example.com")
    records = SyncRecord.objects.count()

    with override_settings(
        ZOHO_FLOW_WEBHOOKS={
            "enquiry": "https://flow.example/enquiry",
            "contact": "https://flow.example/contact",
        }
    ):
        _run("--mint-unmatched")

    enquiry.refresh_from_db()
    assert enquiry.person is not None
    assert SyncRecord.objects.count() == records
