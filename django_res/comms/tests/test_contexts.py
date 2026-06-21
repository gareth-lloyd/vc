"""Unit tests for `comms.contexts.resolve_context`.

The domain-object → merge-field builders (`booking_context`, `payment_context`)
are exercised end-to-end by the signal tests (booking/payment emails render
their fields). These tests cover only the resolver's dispatch logic.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.http import Http404

from comms.contexts import booking_context, resolve_context


def test_booking_context_formats_dates_for_customers() -> None:
    # `booking_context` now also itemises charge lines via the shared builder,
    # so the stand-in needs the booking shape that builder reads (an empty
    # charge set, a currency, a snapshot). Itemisation itself is covered by
    # `test_charges_breakdown` / `test_booking_confirmation_itemisation`; this
    # test still only pins the customer-facing date formatting.
    booking = SimpleNamespace(
        reference="VC-1",
        guest=SimpleNamespace(first_name="Ada"),
        property=SimpleNamespace(display_name="Villa Sol", name="villa-sol"),
        date_from=date(2025, 7, 8),
        date_to=date(2025, 7, 14),
        charge_items=SimpleNamespace(all=list),
        currency=SimpleNamespace(code="GBP"),
        pricing_snapshot={"total": "1400.00"},
        balance_due=Decimal("0"),
    )

    ctx = booking_context(booking)

    assert ctx["date_from"] == "8 July 2025"
    assert ctx["date_to"] == "14 July 2025"
    assert "charge_breakdown" in ctx


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
