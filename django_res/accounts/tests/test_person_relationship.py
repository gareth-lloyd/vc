"""Model + merge + erasure tests for PersonRelationship (GAP-041)."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError

from accounts.enums import PersonRelationshipKind
from accounts.models import Person, PersonRelationship
from core.models import AuditLog


def _person(first: str) -> Person:
    return Person.objects.create(first_name=first, last_name="X")


@pytest.mark.django_db
def test_create_relationship() -> None:
    alice, bob = _person("Alice"), _person("Bob")
    rel = PersonRelationship.objects.create(
        from_person=alice, to_person=bob, kind=PersonRelationshipKind.PA
    )

    assert rel.pk is not None
    assert alice.relationships_out.get().to_person_id == bob.pk
    assert bob.relationships_in.get().from_person_id == alice.pk


@pytest.mark.django_db
def test_duplicate_relationship_rejected() -> None:
    alice, bob = _person("Alice"), _person("Bob")
    PersonRelationship.objects.create(
        from_person=alice, to_person=bob, kind=PersonRelationshipKind.SPOUSE
    )

    with pytest.raises(IntegrityError):
        PersonRelationship.objects.create(
            from_person=alice, to_person=bob, kind=PersonRelationshipKind.SPOUSE
        )


@pytest.mark.django_db
def test_self_link_rejected_by_db() -> None:
    alice = _person("Alice")

    with pytest.raises(IntegrityError):
        PersonRelationship.objects.create(
            from_person=alice, to_person=alice, kind=PersonRelationshipKind.OTHER
        )


@pytest.mark.django_db
def test_relationship_cascades_on_person_delete() -> None:
    alice, bob = _person("Alice"), _person("Bob")
    PersonRelationship.objects.create(
        from_person=alice, to_person=bob, kind=PersonRelationshipKind.CHILD
    )

    bob.delete()

    assert not PersonRelationship.objects.filter(from_person=alice).exists()


# --- merge matrix ----------------------------------------------------------


@pytest.mark.django_db
def test_merge_drops_link_between_the_two_merged_people() -> None:
    """(a) A relationship directly between source and target would repoint into a
    self-link — it's dropped, not persisted (no IntegrityError)."""
    keep, dup = _person("Keep"), _person("Dup")
    PersonRelationship.objects.create(
        from_person=dup, to_person=keep, kind=PersonRelationshipKind.SPOUSE
    )

    dup.merge(keep)

    assert not Person.objects.filter(pk=dup.pk).exists()
    assert not PersonRelationship.objects.filter(from_person=keep, to_person=keep).exists()
    assert PersonRelationship.objects.count() == 0


@pytest.mark.django_db
def test_merge_drops_reciprocal_rows_between_merged_people() -> None:
    """(b) Both directions (keep→dup) and (dup→keep) collapse to self-links and
    are both dropped."""
    keep, dup = _person("Keep"), _person("Dup")
    PersonRelationship.objects.create(
        from_person=keep, to_person=dup, kind=PersonRelationshipKind.SIBLING
    )
    PersonRelationship.objects.create(
        from_person=dup, to_person=keep, kind=PersonRelationshipKind.SIBLING
    )

    dup.merge(keep)

    assert PersonRelationship.objects.count() == 0


@pytest.mark.django_db
def test_merge_drops_third_party_duplicate_keeps_distinct() -> None:
    """(c) Source and target both link to the same third party under the same
    kind → one is dropped; a distinct-kind link to the same third party
    survives."""
    keep, dup, carol = _person("Keep"), _person("Dup"), _person("Carol")
    PersonRelationship.objects.create(
        from_person=keep, to_person=carol, kind=PersonRelationshipKind.PARENT
    )
    PersonRelationship.objects.create(
        from_person=dup, to_person=carol, kind=PersonRelationshipKind.PARENT
    )  # collides → dropped
    PersonRelationship.objects.create(
        from_person=dup, to_person=carol, kind=PersonRelationshipKind.OTHER
    )  # distinct kind → moves

    dup.merge(keep)

    links = PersonRelationship.objects.filter(from_person=keep, to_person=carol)
    assert {link.kind for link in links} == {
        PersonRelationshipKind.PARENT,
        PersonRelationshipKind.OTHER,
    }
    assert not PersonRelationship.objects.filter(from_person=dup).exists()


@pytest.mark.django_db
def test_merge_repoints_relationship_to_third_party() -> None:
    """A plain link from the source to an unrelated third party is repointed onto
    the target and counted in the merge summary."""
    keep, dup, carol = _person("Keep"), _person("Dup"), _person("Carol")
    PersonRelationship.objects.create(
        from_person=dup, to_person=carol, kind=PersonRelationshipKind.PA
    )

    dup.merge(keep)

    assert PersonRelationship.objects.get(to_person=carol).from_person_id == keep.pk
    ct = ContentType.objects.get_for_model(Person)
    row = next(
        r
        for r in AuditLog.objects.filter(content_type=ct, object_id=str(dup.pk))
        if r.field_diffs.get("__deleted__")
    )
    assert row.field_diffs["__rewrites__"]["accounts.PersonRelationship.from_person"] == 1


@pytest.mark.django_db
def test_merge_moved_relationship_leaves_audit_row() -> None:
    """(d) A moved relationship is repointed per-instance, so the from_person
    change lands in the PersonRelationship audit trail (bulk update would not)."""
    keep, dup, carol = _person("Keep"), _person("Dup"), _person("Carol")
    rel = PersonRelationship.objects.create(
        from_person=dup, to_person=carol, kind=PersonRelationshipKind.PARTNER
    )

    dup.merge(keep)

    ct = ContentType.objects.get_for_model(PersonRelationship)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(rel.pk))
    assert any(r.field_diffs.get("from_person_id") == [dup.pk, keep.pk] for r in rows)


@pytest.mark.django_db
def test_anonymize_deletes_relationship_rows() -> None:
    """Erasure drops standing links in both directions (a surviving link leaks
    'X is [redacted]'s spouse')."""
    subject, spouse, child = _person("Subject"), _person("Spouse"), _person("Child")
    PersonRelationship.objects.create(
        from_person=subject, to_person=spouse, kind=PersonRelationshipKind.SPOUSE
    )
    PersonRelationship.objects.create(
        from_person=child, to_person=subject, kind=PersonRelationshipKind.CHILD
    )

    subject.anonymize()

    assert not PersonRelationship.objects.filter(from_person=subject).exists()
    assert not PersonRelationship.objects.filter(to_person=subject).exists()
    # The unrelated parties keep their rows otherwise untouched — only links
    # touching the subject go.
    assert PersonRelationship.objects.count() == 0


@pytest.mark.django_db
def test_relationship_note_is_not_audited() -> None:
    """`note` is free-text that may carry special-category PII and the row is
    hard-deleted on erasure (so its deletion audit row can't be scrubbed). It is
    deliberately kept out of the trail entirely — neither edits nor the deletion
    record the note text."""
    alice, bob = _person("Alice"), _person("Bob")
    secret = "daughter from first marriage, lives at 14 Acacia Ave"
    rel = PersonRelationship.objects.create(
        from_person=alice, to_person=bob, kind=PersonRelationshipKind.CHILD, note=secret
    )
    rel.note = secret + " (updated)"
    rel.save(update_fields=["note"])
    rel.delete()

    ct = ContentType.objects.get_for_model(PersonRelationship)
    rows = AuditLog.objects.filter(content_type=ct)
    for r in rows:
        assert secret not in str(r.field_diffs)
