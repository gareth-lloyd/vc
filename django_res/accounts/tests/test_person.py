from __future__ import annotations

from datetime import datetime

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError

from accounts.enums import PersonStatus, PersonTag
from accounts.models import Person, PersonEmail, PersonPhone
from core.audit import REDACTED
from core.models import AuditLog


@pytest.fixture
def contact(db: None) -> Person:
    return Person.objects.create(first_name="Ada", last_name="Lovelace")


@pytest.mark.django_db
def test_contact_email_lowercased() -> None:
    c = Person.objects.create(first_name="Ada", last_name="Lovelace")
    email = PersonEmail.objects.create(contact=c, email="Ada@EXAMPLE.com")

    email.refresh_from_db()
    assert email.email == "ada@example.com"


@pytest.mark.django_db
def test_only_one_primary_email_per_contact(contact: Person) -> None:
    PersonEmail.objects.create(contact=contact, email="a@x.com", is_primary=True)

    with pytest.raises(IntegrityError):
        PersonEmail.objects.create(contact=contact, email="b@x.com", is_primary=True)


@pytest.mark.django_db
def test_only_one_primary_phone_per_contact(contact: Person) -> None:
    PersonPhone.objects.create(contact=contact, number="111", is_primary=True)

    with pytest.raises(IntegrityError):
        PersonPhone.objects.create(contact=contact, number="222", is_primary=True)


@pytest.mark.django_db
def test_new_address_and_marketing_fields_default_blank() -> None:
    """town/post_code default to "", country to NULL, marketing_consent False."""
    c = Person.objects.create(first_name="Ada", last_name="Lovelace")

    c.refresh_from_db()
    assert c.town == ""
    assert c.post_code == ""
    assert c.country is None
    assert c.marketing_consent is False


@pytest.mark.django_db
def test_anonymize_clears_town_and_post_code() -> None:
    c = Person.objects.create(
        first_name="Ada",
        last_name="Lovelace",
        town="London",
        post_code="EC1A 1BB",
    )

    c.anonymize()

    c.refresh_from_db()
    assert c.town == ""
    assert c.post_code == ""


@pytest.mark.django_db
def test_anonymize_preserves_country_and_marketing_consent() -> None:
    """country (an FK, not PII) and marketing_consent survive anonymize,
    matching Guest's convention."""
    from typing import cast

    from properties.factories import CountryFactory
    from properties.models import Country

    country = cast(Country, CountryFactory())
    c = Person.objects.create(
        first_name="Ada",
        last_name="Lovelace",
        country=country,
        marketing_consent=True,
    )

    c.anonymize()

    c.refresh_from_db()
    assert c.country_id == country.pk
    assert c.marketing_consent is True


@pytest.mark.django_db
def test_anonymize_scrubs_town_and_post_code_from_audit_log() -> None:
    """town/post_code are audit-tracked PII; anonymize must scrub them from
    the AuditLog trail (BUG-012)."""
    c = Person.objects.create(first_name="Ada", last_name="Lovelace")
    c.town = "Secretville"
    c.post_code = "ZZ9 9ZZ"
    c.save(update_fields=["town", "post_code"])

    ct = ContentType.objects.get_for_model(Person)
    pre_rows = AuditLog.objects.filter(content_type=ct, object_id=str(c.pk))
    assert any("Secretville" in str(r.field_diffs) for r in pre_rows)

    c.anonymize()

    rows = list(AuditLog.objects.filter(content_type=ct, object_id=str(c.pk)))
    for r in rows:
        blob = str(r.field_diffs)
        assert "Secretville" not in blob
        assert "ZZ9 9ZZ" not in blob


@pytest.mark.django_db
def test_anonymize_blanks_pii_and_cascades(contact: Person) -> None:
    email = PersonEmail.objects.create(contact=contact, email="ada@example.com")
    phone = PersonPhone.objects.create(contact=contact, number="0123 456")

    contact.anonymize()

    contact.refresh_from_db()
    email.refresh_from_db()
    phone.refresh_from_db()
    assert contact.status == PersonStatus.ANONYMIZED
    assert contact.first_name == "[REDACTED]"
    assert contact.last_name == "[REDACTED]"
    assert isinstance(contact.anonymized_at, datetime)
    assert email.email == f"redacted-{email.pk}@anonymized.local"
    assert phone.number == ""


@pytest.mark.django_db
def test_primary_email_and_phone_fail_closed_when_anonymized(contact: Person) -> None:
    """GAP-045 Unit 3c-2b: an ANONYMIZED Person keeps its email/phone rows,
    rewritten to ``redacted-…@anonymized.local`` sentinels. ``primary_email``
    / ``primary_phone`` must return ``None`` so a person-first read (staff
    list) or send (comms) never surfaces or mails the sentinel."""
    PersonEmail.objects.create(contact=contact, email="ada@example.com", is_primary=True)
    PersonPhone.objects.create(contact=contact, number="+15125550100", is_primary=True)
    assert contact.primary_email() == "ada@example.com"
    assert contact.primary_phone() == "+15125550100"

    contact.anonymize()

    # The sentinel row still exists, but the resolvers fail closed.
    assert contact.emails.filter(email__endswith="@anonymized.local").exists()
    assert contact.primary_email() is None
    assert contact.primary_phone() is None


@pytest.mark.django_db
def test_tags_default_empty(contact: Person) -> None:
    """GAP-040: a Person carries no tags by default."""
    contact.refresh_from_db()
    assert contact.tags == []


@pytest.mark.django_db
def test_tags_persist_normalized_sorted_and_deduped(contact: Person) -> None:
    """save() canonicalizes tags to a sorted, de-duplicated list so the same set
    in any order is one value (no spurious audit row on reorder)."""
    contact.tags = [PersonTag.VIP, PersonTag.TRADE, PersonTag.VIP]
    contact.save(update_fields=["tags"])

    contact.refresh_from_db()
    assert contact.tags == ["trade", "vip"]


@pytest.mark.django_db
def test_tags_change_is_audited(contact: Person) -> None:
    """GAP-040: tag changes land in the AuditLog trail (not PII — kept in clear)."""
    contact.tags = [PersonTag.VIP]
    contact.save(update_fields=["tags"])

    ct = ContentType.objects.get_for_model(Person)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(contact.pk))
    assert any(r.field_diffs.get("tags") == [[], ["vip"]] for r in rows)


@pytest.mark.django_db
def test_anonymize_clears_tags() -> None:
    """GAP-040: tags (Disability / Approach-with-care are special-category data)
    are dropped on erasure."""
    c = Person.objects.create(
        first_name="Ada",
        last_name="Lovelace",
        tags=[PersonTag.DISABILITY, PersonTag.VIP],
    )

    c.anonymize()

    c.refresh_from_db()
    assert c.tags == []


@pytest.mark.django_db
def test_anonymize_scrubs_tags_from_audit_log() -> None:
    """A Disability tag is special-category data — anonymize must scrub it from
    the AuditLog trail, not just the live record (else it stays recoverable)."""
    c = Person.objects.create(first_name="Ada", last_name="Lovelace")
    c.tags = [PersonTag.DISABILITY]
    c.save(update_fields=["tags"])

    ct = ContentType.objects.get_for_model(Person)
    pre_rows = AuditLog.objects.filter(content_type=ct, object_id=str(c.pk))
    assert any("disability" in str(r.field_diffs) for r in pre_rows)

    c.anonymize()

    rows = AuditLog.objects.filter(content_type=ct, object_id=str(c.pk))
    for r in rows:
        assert "disability" not in str(r.field_diffs)


@pytest.mark.django_db
def test_merge_rewrites_fks_and_deletes_source() -> None:
    keep = Person.objects.create(first_name="Keep", last_name="Me")
    duplicate = Person.objects.create(first_name="Dup", last_name="Me")
    PersonEmail.objects.create(contact=duplicate, email="dup@example.com")
    duplicate.merge(keep)

    assert not Person.objects.filter(pk=duplicate.pk).exists()
    assert keep.emails.filter(email="dup@example.com").exists()


@pytest.mark.django_db
def test_merge_folds_source_email_keeping_target_primary() -> None:
    """GAP-045 Unit 3c-3b: merging two Persons that EACH own a PRIMARY email must
    not trip ``one_primary_email_per_contact``. The survivor keeps its own
    primary; the source's other address folds in as a non-primary so no
    contactable address is lost."""
    keep = Person.objects.create(first_name="Keep", last_name="Me")
    dup = Person.objects.create(first_name="Dup", last_name="Me")
    PersonEmail.objects.create(contact=keep, email="keep@example.com", is_primary=True)
    PersonEmail.objects.create(contact=dup, email="dup@example.com", is_primary=True)

    dup.merge(keep)

    assert not Person.objects.filter(pk=dup.pk).exists()
    primaries = keep.emails.filter(is_primary=True)
    assert primaries.count() == 1
    assert primaries.get().email == "keep@example.com"
    assert keep.emails.filter(email="dup@example.com", is_primary=False).exists()


@pytest.mark.django_db
def test_merge_folds_source_phone_keeping_target_primary() -> None:
    keep = Person.objects.create(first_name="Keep", last_name="Me")
    dup = Person.objects.create(first_name="Dup", last_name="Me")
    PersonPhone.objects.create(contact=keep, number="111", is_primary=True)
    PersonPhone.objects.create(contact=dup, number="222", is_primary=True)

    dup.merge(keep)

    primaries = keep.phones.filter(is_primary=True)
    assert primaries.count() == 1
    assert primaries.get().number == "111"
    assert keep.phones.filter(number="222", is_primary=False).exists()


@pytest.mark.django_db
def test_merge_drops_duplicate_source_address() -> None:
    """A source address already on the target is dropped (would violate
    ``unique_contact_email``), not duplicated."""
    keep = Person.objects.create(first_name="Keep", last_name="Me")
    dup = Person.objects.create(first_name="Dup", last_name="Me")
    PersonEmail.objects.create(contact=keep, email="shared@example.com", is_primary=True)
    PersonEmail.objects.create(contact=dup, email="shared@example.com", is_primary=True)

    dup.merge(keep)

    assert keep.emails.filter(email="shared@example.com").count() == 1
    assert keep.emails.filter(is_primary=True).count() == 1


@pytest.mark.django_db
def test_merge_promotes_source_primary_when_target_has_none() -> None:
    """If the survivor has no primary, the source's primary becomes the merged
    primary rather than being silently demoted to nothing."""
    keep = Person.objects.create(first_name="Keep", last_name="Me")
    dup = Person.objects.create(first_name="Dup", last_name="Me")
    # keep has a non-primary email only; dup has a primary.
    PersonEmail.objects.create(contact=keep, email="keep@example.com", is_primary=False)
    PersonEmail.objects.create(contact=dup, email="dup@example.com", is_primary=True)

    dup.merge(keep)

    primaries = keep.emails.filter(is_primary=True)
    assert primaries.count() == 1
    assert primaries.get().email == "dup@example.com"


@pytest.mark.django_db
def test_merge_dropped_duplicate_may_leave_survivor_without_primary_flag() -> None:
    """Edge: the survivor's only copy of an address is non-primary and the
    source's duplicate is its primary. The duplicate is dropped (not moved), so
    no ``is_primary`` flag is carried over — but ``primary_email`` still resolves
    via its oldest-by-pk fallback, so the merged Person stays contactable."""
    keep = Person.objects.create(first_name="Keep", last_name="Me")
    dup = Person.objects.create(first_name="Dup", last_name="Me")
    PersonEmail.objects.create(contact=keep, email="shared@example.com", is_primary=False)
    PersonEmail.objects.create(contact=dup, email="shared@example.com", is_primary=True)

    dup.merge(keep)

    assert keep.emails.count() == 1
    assert keep.emails.filter(is_primary=True).count() == 0
    keep.refresh_from_db()
    assert keep.primary_email() == "shared@example.com"


@pytest.mark.django_db
def test_merge_rewrite_count_excludes_dropped_channel_duplicates() -> None:
    """FG-016 deletion-row summary counts MOVED channel rows; a dropped
    duplicate (the address already on the survivor) is excluded from the count."""
    keep = Person.objects.create(first_name="Keep", last_name="Me")
    dup = Person.objects.create(first_name="Dup", last_name="Me")
    PersonEmail.objects.create(contact=keep, email="shared@example.com", is_primary=True)
    PersonEmail.objects.create(contact=dup, email="shared@example.com", is_primary=True)  # dropped
    PersonEmail.objects.create(contact=dup, email="extra@example.com", is_primary=False)  # moved

    dup.merge(keep)

    ct = ContentType.objects.get_for_model(Person)
    rows = list(AuditLog.objects.filter(content_type=ct, object_id=str(dup.pk)))
    row = next(r for r in rows if r.field_diffs.get("__deleted__"))
    assert row.field_diffs["__rewrites__"]["accounts.PersonEmail.contact"] == 1
    assert keep.emails.filter(email="extra@example.com").exists()


@pytest.mark.django_db
def test_merge_deletion_row_records_merged_into_and_rewrite_counts() -> None:
    """FG-016: the bulk FK rewrites bypass the audit signals, so merge must
    stamp the destination pk and per-relation rewrite counts onto the
    deletion row rather than leaving them silently unaudited."""
    keep = Person.objects.create(first_name="Keep", last_name="Me")
    duplicate = Person.objects.create(first_name="Dup", last_name="Me")
    PersonEmail.objects.create(contact=duplicate, email="a@example.com")
    PersonEmail.objects.create(contact=duplicate, email="b@example.com")

    duplicate.merge(keep)

    ct = ContentType.objects.get_for_model(Person)
    rows = list(AuditLog.objects.filter(content_type=ct, object_id=str(duplicate.pk)))
    deletion_rows = [r for r in rows if r.field_diffs.get("__deleted__")]
    assert deletion_rows
    row = deletion_rows[-1]
    assert row.field_diffs["__merged_into__"] == str(keep.pk)
    rewrites = row.field_diffs["__rewrites__"]
    assert rewrites["accounts.PersonEmail.contact"] == 2
    assert all(count > 0 for count in rewrites.values())


@pytest.mark.django_db
def test_anonymize_scrubs_pii_from_audit_log(contact: Person) -> None:
    """GDPR erasure: anonymize must redact cleartext PII across the
    contact's whole AuditLog trail (BUG-012)."""
    contact.last_name = "Leaky"
    contact.notes = "secret note"
    contact.save(update_fields=["last_name", "notes"])

    ct = ContentType.objects.get_for_model(Person)
    pre_rows = AuditLog.objects.filter(content_type=ct, object_id=str(contact.pk))
    assert any("Leaky" in str(r.field_diffs) for r in pre_rows)

    contact.anonymize()

    rows = list(AuditLog.objects.filter(content_type=ct, object_id=str(contact.pk)))
    for r in rows:
        blob = str(r.field_diffs)
        assert "Leaky" not in blob
        assert "secret note" not in blob


@pytest.mark.django_db
def test_merge_scrubs_deletion_row_pii_but_keeps_structure() -> None:
    """merge() deletion row keeps __deleted__/structure, redacts PII (BUG-012)."""
    keep = Person.objects.create(first_name="Keep", last_name="Me")
    duplicate = Person.objects.create(first_name="Dup", last_name="Leaky")

    duplicate.merge(keep)

    ct = ContentType.objects.get_for_model(Person)
    rows = list(AuditLog.objects.filter(content_type=ct, object_id=str(duplicate.pk)))
    deletion_rows = [r for r in rows if r.field_diffs.get("__deleted__")]
    assert deletion_rows
    for r in deletion_rows:
        assert "Leaky" not in str(r.field_diffs)
        assert r.field_diffs["__deleted__"] is True
        assert r.field_diffs["last_name"][0] == REDACTED


@pytest.mark.django_db
def test_merge_sends_person_merged_signal() -> None:
    """GAP-081: `Person.merge` fires `person_merged` with the survivor and the
    absorbed row's (now-dead) pk so downstream apps can enqueue CRM re-pushes."""
    from accounts.signals import person_merged

    keep = Person.objects.create(first_name="Keep", last_name="Me")
    duplicate = Person.objects.create(first_name="Dup", last_name="Me")
    duplicate_pk = duplicate.pk
    received: list[tuple[Person, int]] = []

    def _capture(
        sender: type[Person], survivor: Person, absorbed_pk: int, **kwargs: object
    ) -> None:
        received.append((survivor, absorbed_pk))

    person_merged.connect(_capture)
    try:
        duplicate.merge(keep)
    finally:
        person_merged.disconnect(_capture)

    assert received == [(keep, duplicate_pk)]
