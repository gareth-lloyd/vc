"""Enquiry references are DB-assigned on every insert path (BUG-007).

Parity with `payments/tests/test_reference_generation.py`: the `E-` series is
backed by its own Postgres sequence wired as the column `db_default`, so
`bulk_create` — which skips `save()` — still gets distinct, non-empty refs.
"""

from __future__ import annotations

import pytest

from reservations.models import Enquiry

pytestmark = pytest.mark.django_db


def test_bulk_create_assigns_distinct_non_empty_references() -> None:
    Enquiry.objects.bulk_create([Enquiry(), Enquiry()])

    refs = list(Enquiry.objects.values_list("reference", flat=True))
    assert all(refs), f"blank reference slipped through: {refs!r}"
    assert len(set(refs)) == 2, f"duplicate references: {refs!r}"
    assert all(r.startswith("E-") for r in refs), refs


def test_explicit_reference_is_preserved() -> None:
    enquiry = Enquiry.objects.create(reference="E-LEGACY-1")
    enquiry.refresh_from_db()
    assert enquiry.reference == "E-LEGACY-1"
