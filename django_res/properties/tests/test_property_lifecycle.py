"""`PropertyLifecycleService` — the Property status machine (BUG-015)."""

from __future__ import annotations

import pytest

from core.exceptions import InvalidTransition
from properties.enums import PROPERTY_ALLOWED_TRANSITIONS, PropertyStatus
from properties.models import Property
from properties.services.lifecycle import PropertyLifecycleService

DRAFT = PropertyStatus.DRAFT.value
ACTIVE = PropertyStatus.ACTIVE.value
ARCHIVED = PropertyStatus.ARCHIVED.value


def test_property_table_lists_every_status() -> None:
    assert set(PROPERTY_ALLOWED_TRANSITIONS) == set(PropertyStatus.values)


# Each action's exact from-set, checked against every status.
_ACTION_FROM: list[tuple[str, str, frozenset[str]]] = [
    ("activate", ACTIVE, frozenset({DRAFT, ARCHIVED})),
    ("archive", ARCHIVED, frozenset({DRAFT, ACTIVE})),
    ("restore", DRAFT, frozenset({ARCHIVED})),
]


@pytest.mark.django_db
@pytest.mark.parametrize("from_status", PropertyStatus.values)
@pytest.mark.parametrize(("action", "to_status", "allowed_from"), _ACTION_FROM)
def test_action_from_set_is_exact(
    property_: Property,
    action: str,
    to_status: str,
    allowed_from: frozenset[str],
    from_status: str,
) -> None:
    Property.objects.filter(pk=property_.pk).update(status=from_status)
    property_.refresh_from_db()
    bound = getattr(PropertyLifecycleService, action)

    if from_status in allowed_from:
        bound(property_)
        expected = to_status
    else:
        with pytest.raises(InvalidTransition):
            bound(property_)
        expected = from_status
    property_.refresh_from_db()
    assert property_.status == expected


@pytest.mark.django_db
def test_archive_guards_locked_state_not_stale_instance(property_: Property) -> None:
    stale = Property.objects.get(pk=property_.pk)
    PropertyLifecycleService.archive(property_)

    # `stale` still reads DRAFT in memory; the guard must see the locked ARCHIVED row.
    with pytest.raises(InvalidTransition) as exc:
        PropertyLifecycleService.archive(stale)
    assert exc.value.from_state == ARCHIVED
