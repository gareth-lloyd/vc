"""The explicit loader registry (`data_migration.registry.LOADERS`)."""

from __future__ import annotations

from data_migration.registry import LOADERS


def test_booking_loaders_are_not_registered() -> None:
    """GAP-089 / GAP-108: bookings come from the Past Bookers sheet
    (`import_past_bookers`), not `VillaBooking` — the booking, payment and
    charge-item loaders stay in the tree as a schema record but never run."""
    assert {"booking", "payment", "booking_charge_item"}.isdisjoint(LOADERS)


def test_registry_size_is_pinned() -> None:
    assert len(LOADERS) == 31
