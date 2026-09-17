"""Tests for the top-level `conftest.py` reference-data restore.

A test gets the DB either from a `django_db` marker or by requesting the `db` /
`transactional_db` fixture (directly or through another fixture). Both routes
must get the migration-seeded reference rows back, or a reused per-worker DB
flushed by a `seeding/` transactional test fails them with
`Country.DoesNotExist`.
"""

from __future__ import annotations

import pytest

from conftest import _db_fixture_for


def test_no_marker_and_no_db_fixture_needs_no_db() -> None:
    assert _db_fixture_for(None, ["settings", "monkeypatch"]) is None


def test_django_db_marker_uses_db() -> None:
    assert _db_fixture_for(pytest.mark.django_db.mark, []) == "db"


@pytest.mark.parametrize(
    "mark",
    [pytest.mark.django_db(transaction=True).mark, pytest.mark.django_db(True).mark],
)
def test_transactional_django_db_marker_uses_transactional_db(mark: pytest.Mark) -> None:
    assert _db_fixture_for(mark, []) == "transactional_db"


def test_requesting_db_fixture_without_marker_uses_db() -> None:
    assert _db_fixture_for(None, ["db", "_django_db_helper"]) == "db"


def test_requesting_transactional_db_fixture_without_marker_uses_transactional_db() -> None:
    assert _db_fixture_for(None, ["transactional_db"]) == "transactional_db"
