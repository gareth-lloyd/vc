"""Unit tests for `comms.contexts.resolve_context`.

The domain-object → merge-field builders (`booking_context`, `payment_context`)
are exercised end-to-end by the signal tests (booking/payment emails render
their fields). These tests cover only the resolver's dispatch logic.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from django.http import Http404

from comms.contexts import booking_context, resolve_context


def test_booking_context_formats_dates_for_customers() -> None:
    booking = SimpleNamespace(
        reference="VC-1",
        person=None,  # person-first greeting falls back to the guest
        guest=SimpleNamespace(first_name="Ada"),
        property=SimpleNamespace(display_name="Villa Sol", name="villa-sol"),
        date_from=date(2025, 7, 8),
        date_to=date(2025, 7, 14),
    )

    ctx = booking_context(booking)

    assert ctx["date_from"] == "8 July 2025"
    assert ctx["date_to"] == "14 July 2025"


def test_explicit_context_wins_and_is_copied() -> None:
    source = {"booking_reference": "VC-1"}
    resolved = resolve_context(context=source)

    assert resolved == source
    assert resolved is not source  # defensive copy


def test_no_inputs_returns_empty_skeleton() -> None:
    assert resolve_context() == {}


@pytest.mark.django_db
def test_unknown_booking_id_raises_404() -> None:
    with pytest.raises(Http404):
        resolve_context(booking_id=9_999_999)
