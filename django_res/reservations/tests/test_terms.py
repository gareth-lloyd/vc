"""Tests for `TermsVersion.publish()` — atomic current-row flip."""

from __future__ import annotations

import pytest

from reservations.models import TermsVersion


@pytest.mark.django_db
def test_publish_sets_current_and_clears_previous() -> None:
    old = TermsVersion.objects.create(version="2025-01", body_markdown="old")
    old.publish()
    new = TermsVersion.objects.create(version="2026-01", body_markdown="new")

    new.publish()

    old.refresh_from_db()
    new.refresh_from_db()
    assert old.is_current is False
    assert new.is_current is True
    assert new.published_at is not None


@pytest.mark.django_db
def test_publish_idempotent_on_same_row() -> None:
    v = TermsVersion.objects.create(version="2026-01", body_markdown="x")
    v.publish()
    v.publish()
    v.refresh_from_db()
    assert v.is_current is True
