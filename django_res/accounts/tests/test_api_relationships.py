"""API tests for the /contacts/{id}/relationships sub-resource (GAP-041)."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from accounts.enums import PersonRelationshipKind
from accounts.models import Person, PersonRelationship, User
from core.enums import StaffRole


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True, email="staff@example.com", password="x", role=StaffRole.RESERVATIONS
    )


def _person(first: str) -> Person:
    return Person.objects.create(first_name=first, last_name="X")


@pytest.mark.django_db
def test_create_relationship(api_client: APIClient, staff: User) -> None:
    alice, bob = _person("Alice"), _person("Bob")
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/contacts/{alice.pk}/relationships",
        {"to_person": bob.pk, "kind": PersonRelationshipKind.PA},
        format="json",
    )

    assert response.status_code == 201
    rel = PersonRelationship.objects.get()
    assert rel.from_person_id == alice.pk
    assert rel.to_person_id == bob.pk
    assert rel.kind == PersonRelationshipKind.PA


@pytest.mark.django_db
def test_list_shows_both_directions_with_inverse_labels(api_client: APIClient, staff: User) -> None:
    """Viewing Alice's profile: an outgoing PA row shows Bob as 'PA'; an incoming
    CHILD row (Carol's child is Alice) shows Carol as 'Parent'."""
    alice, bob, carol = _person("Alice"), _person("Bob"), _person("Carol")
    PersonRelationship.objects.create(
        from_person=alice, to_person=bob, kind=PersonRelationshipKind.PA
    )
    PersonRelationship.objects.create(
        from_person=carol, to_person=alice, kind=PersonRelationshipKind.CHILD
    )
    api_client.force_login(staff)

    rows = api_client.get(f"/api/v1/contacts/{alice.pk}/relationships").json()["results"]

    by_other = {r["other_person"]["id"]: r for r in rows}
    assert by_other[bob.pk]["direction"] == "outgoing"
    assert by_other[bob.pk]["kind_label"] == "PA"
    assert by_other[carol.pk]["direction"] == "incoming"
    assert by_other[carol.pk]["kind_label"] == "Parent"


@pytest.mark.django_db
def test_list_is_single_query(
    api_client: APIClient, staff: User, django_assert_max_num_queries: Any
) -> None:
    """The list pulls both parties via select_related — no per-row N+1."""
    alice = _person("Alice")
    for name in ("Bob", "Carol", "Dave"):
        PersonRelationship.objects.create(
            from_person=alice, to_person=_person(name), kind=PersonRelationshipKind.OTHER
        )
    api_client.force_login(staff)

    # Auth/session + count + page — pinned as an upper bound; the per-row party
    # reads must NOT add to it (select_related). One extra relationship below
    # must not raise the count.
    with django_assert_max_num_queries(8):
        resp = api_client.get(f"/api/v1/contacts/{alice.pk}/relationships")
    assert len(resp.json()["results"]) == 3


@pytest.mark.django_db
def test_self_link_rejected(api_client: APIClient, staff: User) -> None:
    alice = _person("Alice")
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/contacts/{alice.pk}/relationships",
        {"to_person": alice.pk, "kind": PersonRelationshipKind.OTHER},
        format="json",
    )

    assert response.status_code == 400
    assert not PersonRelationship.objects.exists()


@pytest.mark.django_db
def test_duplicate_relationship_rejected(api_client: APIClient, staff: User) -> None:
    alice, bob = _person("Alice"), _person("Bob")
    PersonRelationship.objects.create(
        from_person=alice, to_person=bob, kind=PersonRelationshipKind.SPOUSE
    )
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/contacts/{alice.pk}/relationships",
        {"to_person": bob.pk, "kind": PersonRelationshipKind.SPOUSE},
        format="json",
    )

    assert response.status_code == 400
    assert PersonRelationship.objects.count() == 1


@pytest.mark.django_db
def test_reverse_direction_duplicate_rejected_symmetric(api_client: APIClient, staff: User) -> None:
    """A symmetric link (SPOUSE) recorded from the other party's profile is the
    SAME fact — the mirror row is blocked (one source-of-truth row, inverse label
    on the reverse side)."""
    alice, bob = _person("Alice"), _person("Bob")
    PersonRelationship.objects.create(
        from_person=alice, to_person=bob, kind=PersonRelationshipKind.SPOUSE
    )
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/contacts/{bob.pk}/relationships",
        {"to_person": alice.pk, "kind": PersonRelationshipKind.SPOUSE},
        format="json",
    )

    assert response.status_code == 400
    assert PersonRelationship.objects.count() == 1


@pytest.mark.django_db
def test_reverse_direction_duplicate_rejected_child_parent(
    api_client: APIClient, staff: User
) -> None:
    """(Alice, Bob, CHILD) = 'Bob is Alice's child'; its mirror is (Bob, Alice,
    PARENT) = 'Alice is Bob's parent' — the same fact, blocked."""
    alice, bob = _person("Alice"), _person("Bob")
    PersonRelationship.objects.create(
        from_person=alice, to_person=bob, kind=PersonRelationshipKind.CHILD
    )
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/contacts/{bob.pk}/relationships",
        {"to_person": alice.pk, "kind": PersonRelationshipKind.PARENT},
        format="json",
    )

    assert response.status_code == 400
    assert PersonRelationship.objects.count() == 1


@pytest.mark.django_db
def test_reverse_pa_is_a_distinct_link(api_client: APIClient, staff: User) -> None:
    """PA has no storable inverse, so (Bob, Alice, PA) is a genuinely different
    fact from (Alice, Bob, PA) and is allowed."""
    alice, bob = _person("Alice"), _person("Bob")
    PersonRelationship.objects.create(
        from_person=alice, to_person=bob, kind=PersonRelationshipKind.PA
    )
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/contacts/{bob.pk}/relationships",
        {"to_person": alice.pk, "kind": PersonRelationshipKind.PA},
        format="json",
    )

    assert response.status_code == 201
    assert PersonRelationship.objects.count() == 2


@pytest.mark.django_db
def test_cannot_link_to_anonymized_person(api_client: APIClient, staff: User) -> None:
    alice, ghost = _person("Alice"), _person("Ghost")
    ghost.anonymize()
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/contacts/{alice.pk}/relationships",
        {"to_person": ghost.pk, "kind": PersonRelationshipKind.OTHER},
        format="json",
    )

    assert response.status_code == 400
    assert not PersonRelationship.objects.exists()


@pytest.mark.django_db
def test_delete_relationship_from_either_profile(api_client: APIClient, staff: User) -> None:
    """The row is bidirectional — deleting via the to_person's profile removes
    the same single source-of-truth row."""
    alice, bob = _person("Alice"), _person("Bob")
    rel = PersonRelationship.objects.create(
        from_person=alice, to_person=bob, kind=PersonRelationshipKind.SIBLING
    )
    api_client.force_login(staff)

    response = api_client.delete(f"/api/v1/contacts/{bob.pk}/relationships/{rel.pk}")

    assert response.status_code == 204
    assert not PersonRelationship.objects.exists()


@pytest.mark.django_db
def test_relationships_require_staff(api_client: APIClient) -> None:
    alice = _person("Alice")

    response = api_client.get(f"/api/v1/contacts/{alice.pk}/relationships")

    assert response.status_code in (401, 403)
