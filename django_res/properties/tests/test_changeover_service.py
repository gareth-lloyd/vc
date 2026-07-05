"""ChangeoverService — resolve the effective changeover day and align arrivals.

Resolution order: a ChangeOverRule window covering the arrival date wins;
otherwise the PropertySettings.effective() chain (property -> group);
`any` means no constraint. A non-conforming arrival is never rejected — it is
nudged forward to the next valid changeover day (GAP-007).
"""

from __future__ import annotations

from datetime import date

import pytest

from properties.enums import PrefilledChangeOverDay
from properties.models import ChangeOverRule, Property
from properties.models.settings import PropertySettings
from properties.services.changeover import ChangeoverService

pytestmark = pytest.mark.django_db

# 2026-06-10 is a Wednesday; 2026-06-13 is a Saturday.
WEDNESDAY = date(2026, 6, 10)
SATURDAY = date(2026, 6, 13)


# ---------------------------------------------------------------------------
# effective_day / required_weekday — resolution order
# ---------------------------------------------------------------------------
def test_effective_day_from_property_settings(property_: Property) -> None:
    PropertySettings.objects.create(
        property=property_,
        changeover_day=PrefilledChangeOverDay.SAT.value,
    )
    assert ChangeoverService.effective_day(property_, WEDNESDAY) == PrefilledChangeOverDay.SAT.value
    assert ChangeoverService.required_weekday(property_, WEDNESDAY) == 5  # Saturday


def test_effective_day_defaults_to_any(property_: Property) -> None:
    # No PropertySettings row → ANY (unconstrained).
    assert ChangeoverService.effective_day(property_, WEDNESDAY) == PrefilledChangeOverDay.ANY.value
    assert ChangeoverService.required_weekday(property_, WEDNESDAY) is None


def test_changeover_rule_window_overrides_settings(property_: Property) -> None:
    # Property default is ANY (group), but a rule forces Saturday in the window.
    ChangeOverRule.objects.create(
        property=property_,
        day=PrefilledChangeOverDay.SAT.value,
        starts_on=date(2026, 6, 1),
        ends_on=date(2026, 6, 30),
    )
    assert ChangeoverService.required_weekday(property_, WEDNESDAY) == 5  # in-window Saturday
    # Outside the rule window the ANY default applies again.
    assert ChangeoverService.required_weekday(property_, date(2026, 7, 8)) is None


# ---------------------------------------------------------------------------
# align_forward — pure night-count-preserving shift
# ---------------------------------------------------------------------------
def test_align_forward_shifts_to_next_allowed_weekday() -> None:
    new_from, new_to, shifted_from = ChangeoverService.align_forward(
        {5},
        WEDNESDAY,
        date(2026, 6, 17),  # Wed..Wed, 7 nights
    )
    assert new_from == SATURDAY  # next Saturday
    assert new_to == date(2026, 6, 20)  # nights preserved
    assert shifted_from == WEDNESDAY


def test_align_forward_no_shift_when_already_on_weekday() -> None:
    new_from, new_to, shifted_from = ChangeoverService.align_forward(
        {5}, SATURDAY, date(2026, 6, 20)
    )
    assert (new_from, new_to, shifted_from) == (SATURDAY, date(2026, 6, 20), None)


def test_align_forward_no_shift_when_unconstrained() -> None:
    new_from, new_to, shifted_from = ChangeoverService.align_forward(
        set(), WEDNESDAY, date(2026, 6, 17)
    )
    assert (new_from, new_to, shifted_from) == (WEDNESDAY, date(2026, 6, 17), None)
