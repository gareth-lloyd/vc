from __future__ import annotations

from typing import cast

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from accounts.enums import OrgStatus, OrgType
from accounts.factories import OrganisationFactory, PersonFactory
from accounts.models import Organisation, Person
from core.models import AuditLog


@pytest.mark.django_db
def test_str_is_name() -> None:
    org = Organisation.objects.create(name="Dune Travel")
    assert str(org) == "Dune Travel"


@pytest.mark.django_db
def test_defaults_to_active_agency() -> None:
    org = Organisation.objects.create(name="Dune Travel")
    assert org.org_type == OrgType.AGENCY
    assert org.status == OrgStatus.ACTIVE


@pytest.mark.django_db
def test_dedup_key_unique_when_present() -> None:
    """The content-hash backfill keys on dedup_key; a duplicate must raise,
    never silently mint a second org (B3/BL-3)."""
    Organisation.objects.create(name="Alpha", dedup_key="org-abc")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Organisation.objects.create(name="Beta", dedup_key="org-abc")


@pytest.mark.django_db
def test_dedup_key_null_allows_many() -> None:
    """NULL dedup_keys are distinct (partial-unique on non-null), so API/FE
    orgs with no backfill key never collide."""
    Organisation.objects.create(name="Alpha")
    Organisation.objects.create(name="Beta")
    assert Organisation.objects.filter(dedup_key__isnull=True).count() == 2


@pytest.mark.django_db
def test_merge_into_self_raises() -> None:
    org = Organisation.objects.create(name="Alpha")
    with pytest.raises(ValueError, match="into itself"):
        org.merge(org)


@pytest.mark.django_db
def test_merge_deletes_source_and_records_merged_into() -> None:
    """With no inbound FKs yet (Person.agency lands in Unit 2), merge deletes
    the source and stamps __merged_into__ on the deletion AuditLog row. The
    agent-repoint + PROTECT path is exercised in Unit 2 once Person.agency exists.
    """
    keep = Organisation.objects.create(name="Keep")
    dup = Organisation.objects.create(name="Dup")
    dup_pk = dup.pk

    dup.merge(keep)

    assert not Organisation.objects.filter(pk=dup_pk).exists()
    assert Organisation.objects.filter(pk=keep.pk).exists()
    ct = ContentType.objects.get_for_model(Organisation)
    rows = list(AuditLog.objects.filter(content_type=ct, object_id=str(dup_pk)))
    deletion_rows = [r for r in rows if r.field_diffs.get("__deleted__")]
    assert deletion_rows
    assert deletion_rows[-1].field_diffs["__merged_into__"] == str(keep.pk)


@pytest.mark.django_db
def test_merge_repoints_agents_then_deletes_source() -> None:
    """Now that Person.agency exists, merge must move the source org's agents
    onto the target and record the rewrite count (the Unit-1 deferred case)."""
    source = cast(Organisation, OrganisationFactory())
    target = cast(Organisation, OrganisationFactory())
    agent = cast(Person, PersonFactory(agency=source))
    source_pk = source.pk

    source.merge(target)

    agent.refresh_from_db()
    assert agent.agency_id == target.pk
    assert not Organisation.objects.filter(pk=source_pk).exists()
    ct = ContentType.objects.get_for_model(Organisation)
    rows = list(AuditLog.objects.filter(content_type=ct, object_id=str(source_pk)))
    deletion_rows = [r for r in rows if r.field_diffs.get("__deleted__")]
    assert deletion_rows
    assert deletion_rows[-1].field_diffs["__rewrites__"]["accounts.Person.agency"] == 1


@pytest.mark.django_db
def test_org_with_agents_is_protected_but_merge_rewrites_first() -> None:
    """A naive delete of an org with agents is blocked by PROTECT; merge works
    because it repoints the agents before deleting (rewrite-before-delete)."""
    source = cast(Organisation, OrganisationFactory())
    target = cast(Organisation, OrganisationFactory())
    PersonFactory(agency=source)

    with pytest.raises(ProtectedError):
        with transaction.atomic():
            source.delete()

    source.merge(target)
    assert not Organisation.objects.filter(pk=source.pk).exists()


@pytest.mark.django_db
def test_person_merge_survivor_keeps_its_own_agency() -> None:
    """Person.merge repoints the source's relations onto the survivor; the
    survivor's own forward agency FK is untouched (R-B)."""
    org_keep = cast(Organisation, OrganisationFactory())
    org_dup = cast(Organisation, OrganisationFactory())
    keep = Person.objects.create(first_name="Keep", last_name="Me", agency=org_keep)
    dup = Person.objects.create(first_name="Dup", last_name="Me", agency=org_dup)

    dup.merge(keep)

    keep.refresh_from_db()
    assert keep.agency_id == org_keep.pk
