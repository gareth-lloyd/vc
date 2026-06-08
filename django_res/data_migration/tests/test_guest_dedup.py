"""Advisory duplicate-Guest reporting — no auto-merge."""

from __future__ import annotations

import pytest

from data_migration.guest_dedup import find_duplicate_candidates
from reservations.models import Guest

pytestmark = pytest.mark.django_db


def test_groups_guests_sharing_an_email() -> None:
    g1 = Guest.objects.create(first_name="A", last_name="X", email="dup@x.com")
    g2 = Guest.objects.create(first_name="B", last_name="Y", email="dup@x.com")
    Guest.objects.create(first_name="C", last_name="Z", email="unique@x.com")

    clusters = find_duplicate_candidates()

    assert any({g1.pk, g2.pk} == {g.pk for g in c} for c in clusters)


def test_groups_guests_sharing_a_phone() -> None:
    g1 = Guest.objects.create(first_name="A", last_name="X", phone="+447911123456")
    g2 = Guest.objects.create(first_name="B", last_name="Y", phone="+447911123456")

    clusters = find_duplicate_candidates()

    assert any({g1.pk, g2.pk} == {g.pk for g in c} for c in clusters)


def test_distinct_channels_are_not_clustered() -> None:
    Guest.objects.create(first_name="A", last_name="X", email="a@x.com")
    Guest.objects.create(first_name="B", last_name="Y", email="b@x.com")

    assert find_duplicate_candidates() == []
