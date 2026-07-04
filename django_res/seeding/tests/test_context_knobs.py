"""Knob defaults on ProfileKnobs / _PROFILES."""

from __future__ import annotations

import pytest

from seeding.context import _PROFILES


def test_pct_enquiry_assigned_active_in_every_profile() -> None:
    # Every profile (happy/mixed/chaos) should assign ~80% of enquiries to
    # sales staff during seed_dev — the field defaults on ProfileKnobs, so no
    # profile opts out.
    for knobs in _PROFILES.values():
        assert knobs.pct_enquiry_assigned == pytest.approx(0.8)
