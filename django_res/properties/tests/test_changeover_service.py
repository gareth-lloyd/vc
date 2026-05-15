"""ChangeoverService — resolve the effective changeover day and enforce it.

Resolution order: a ChangeOverRule window covering the arrival date wins;
otherwise the PropertySettings.effective() chain (property -> group);
`any` means no constraint.
"""

from __future__ import annotations

from datetime import date

import pytest

from core.exceptions import ChangeoverViolation
from properties.enums import PrefilledChangeOverDay
from properties.models import ChangeOverRule, Property
from properties.models.settings import PropertySettings
from properties.services.changeover import ChangeoverService

pytestmark = pytest.mark.django_db

# 2026-06-10 is a Wednesday; 2026-06-13 is a Saturday.
WEDNESDAY = date(2026, 6, 10)
SATURDAY = date(2026, 6, 13)


def test_arrival_on_required_day_passes(property_: Property) -> None:
    PropertySettings.objects.create(
        property=property_,
        changeover_day=PrefilledChangeOverDay.SAT.value,
    )
    ChangeoverService.validate_arrival(property_, SATURDAY)  # no raise


def test_arrival_on_wrong_day_raises(property_: Property) -> None:
    PropertySettings.objects.create(
        property=property_,
        changeover_day=PrefilledChangeOverDay.SAT.value,
    )
    with pytest.raises(ChangeoverViolation):
        ChangeoverService.validate_arrival(property_, WEDNESDAY)


def test_override_bypasses_violation(property_: Property) -> None:
    PropertySettings.objects.create(
        property=property_,
        changeover_day=PrefilledChangeOverDay.SAT.value,
    )
    ChangeoverService.validate_arrival(property_, WEDNESDAY, allow_override=True)  # no raise


def test_any_day_default_never_raises(property_: Property) -> None:
    # No PropertySettings row; group default is ANY.
    ChangeoverService.validate_arrival(property_, WEDNESDAY)  # no raise


def test_changeover_rule_window_overrides_default(property_: Property) -> None:
    # Property default is ANY (group), but a rule forces Saturday in the window.
    ChangeOverRule.objects.create(
        property=property_,
        day=PrefilledChangeOverDay.SAT.value,
        starts_on=date(2026, 6, 1),
        ends_on=date(2026, 6, 30),
    )
    with pytest.raises(ChangeoverViolation):
        ChangeoverService.validate_arrival(property_, WEDNESDAY)

    # Outside the rule window the ANY default applies again.
    ChangeoverService.validate_arrival(property_, date(2026, 7, 8))  # Wednesday, no raise
