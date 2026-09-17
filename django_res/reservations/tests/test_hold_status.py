"""BookingHold `status` column — LIVE / RELEASED / EXPIRED (BUG-015).

The column is the lifecycle record: release and expiry both stamp
`released_at`, but only `status` says which one happened (expiry emails the
agent, release doesn't). DB constraints gate on `status`; expiry of a LIVE
hold stays a runtime predicate because Postgres rejects `now()` in an index.
"""

from __future__ import annotations

import importlib
from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.exceptions import InvalidTransition
from reservations.enums import HOLD_ALLOWED_TRANSITIONS, BookingHoldReason, BookingHoldStatus
from reservations.models import BookingHold

if TYPE_CHECKING:
    from properties.models import Property

LIVE = BookingHoldStatus.LIVE.value
RELEASED = BookingHoldStatus.RELEASED.value
EXPIRED = BookingHoldStatus.EXPIRED.value


def _hold(property_: Property, **kwargs: object) -> BookingHold:
    fields: dict[str, object] = {
        "property": property_,
        "date_from": date(2026, 6, 10),
        "date_to": date(2026, 6, 17),
        "expires_at": timezone.now() + timedelta(hours=1),
        "reason": BookingHoldReason.MANUAL.value,
    }
    fields.update(kwargs)
    return BookingHold.objects.create(**fields)


def test_hold_table_lists_every_status() -> None:
    assert set(HOLD_ALLOWED_TRANSITIONS) == set(BookingHoldStatus.values)
    assert HOLD_ALLOWED_TRANSITIONS[LIVE] == frozenset({RELEASED, EXPIRED})
    assert HOLD_ALLOWED_TRANSITIONS[RELEASED] == frozenset()
    assert HOLD_ALLOWED_TRANSITIONS[EXPIRED] == frozenset()


def test_bulk_release_filter_matches_table_from_set() -> None:
    """`HoldService.release_for_*` bulk-update `status=LIVE` rows only; that
    filter must stay the table's from-set for RELEASED (and EXPIRED, whose
    sweep selects LIVE rows too)."""
    for to in (RELEASED, EXPIRED):
        assert {s for s, tos in HOLD_ALLOWED_TRANSITIONS.items() if to in tos} == {LIVE}


def test_status_field_defaults_to_live_in_python_and_db() -> None:
    field = BookingHold._meta.get_field("status")
    assert field.default == LIVE
    # db_default keeps inserts from pre-migration code valid during a deploy.
    assert field.db_default == LIVE


@pytest.mark.django_db
def test_new_hold_is_live(property_: Property) -> None:
    hold = _hold(property_)
    hold.refresh_from_db()
    assert hold.status == LIVE
    assert hold.is_live() is True


@pytest.mark.django_db
@pytest.mark.parametrize(("method", "status"), [("release", RELEASED), ("expire", EXPIRED)])
def test_model_close_sets_status_and_released_at(
    property_: Property, method: str, status: str
) -> None:
    hold = _hold(property_)
    now = timezone.now()

    getattr(hold, method)(now=now)

    hold.refresh_from_db()
    assert hold.status == status
    assert hold.released_at == now
    assert hold.is_live() is False


@pytest.mark.django_db
@pytest.mark.parametrize("closed", [RELEASED, EXPIRED])
@pytest.mark.parametrize("method", ["release", "expire"])
def test_model_close_refuses_closed_hold(property_: Property, closed: str, method: str) -> None:
    released_at = timezone.now() - timedelta(minutes=1)
    hold = _hold(property_, status=closed, released_at=released_at)

    with pytest.raises(InvalidTransition):
        getattr(hold, method)()

    hold.refresh_from_db()
    assert hold.status == closed
    assert hold.released_at == released_at


@pytest.mark.django_db
def test_model_close_guards_locked_state_not_stale_instance(property_: Property) -> None:
    hold = _hold(property_)
    stale = BookingHold.objects.get(pk=hold.pk)
    hold.release()

    with pytest.raises(InvalidTransition):
        stale.expire()
    assert stale.status == RELEASED


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status", "released"),
    [(LIVE, True), (RELEASED, False), (EXPIRED, False)],
)
def test_check_constraint_ties_status_to_released_at(
    property_: Property, status: str, released: bool
) -> None:
    with pytest.raises(IntegrityError, match="bookinghold_status_matches_released_at"):
        with transaction.atomic():
            _hold(property_, status=status, released_at=timezone.now() if released else None)


@pytest.mark.django_db
@pytest.mark.parametrize("closed", [RELEASED, EXPIRED])
def test_exclusion_constraint_ignores_closed_holds(property_: Property, closed: str) -> None:
    _hold(property_, status=closed, released_at=timezone.now())

    live = _hold(property_)

    assert live.status == LIVE


@pytest.mark.django_db
def test_migration_0014_backfill_classifies_rows(property_: Property) -> None:
    """The backfill derives status from `released_at`/`expires_at` alone.

    Rows are seeded with a status that satisfies the CHECK constraint but is
    the "wrong" closed label, so the assertion proves reclassification.
    """
    from django.apps import apps

    backfill = importlib.import_module(
        "reservations.migrations.0014_bookinghold_status"
    ).backfill_hold_status
    now = timezone.now()
    live = _hold(property_, date_from=date(2026, 1, 1), date_to=date(2026, 1, 5))
    # Released after it lapsed → the sweeper's work → EXPIRED.
    lapsed = _hold(
        property_,
        date_from=date(2026, 2, 1),
        date_to=date(2026, 2, 5),
        expires_at=now - timedelta(hours=2),
        released_at=now - timedelta(hours=1),
        status=RELEASED,
    )
    # Released before its expiry → an operator release → RELEASED.
    early = _hold(
        property_,
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 5),
        expires_at=now + timedelta(hours=2),
        released_at=now,
        status=EXPIRED,
    )
    # Indefinite block that was released → RELEASED (it can never expire).
    indefinite = _hold(
        property_,
        date_from=date(2026, 4, 1),
        date_to=date(2026, 4, 5),
        expires_at=None,
        released_at=now,
        status=EXPIRED,
    )

    backfill(apps, None)

    statuses = dict(BookingHold.objects.values_list("pk", "status"))
    assert statuses == {
        live.pk: LIVE,
        lapsed.pk: EXPIRED,
        early.pk: RELEASED,
        indefinite.pk: RELEASED,
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status", "expires_in", "live"),
    [
        (LIVE, timedelta(hours=1), True),
        (LIVE, None, True),
        (LIVE, -timedelta(minutes=5), False),
        (RELEASED, timedelta(hours=1), False),
        (RELEASED, None, False),
        (EXPIRED, -timedelta(minutes=5), False),
    ],
)
def test_live_q_agrees_with_is_live(
    property_: Property, status: str, expires_in: timedelta | None, live: bool
) -> None:
    now = timezone.now()
    hold = _hold(
        property_,
        status=status,
        expires_at=now + expires_in if expires_in is not None else None,
        released_at=None if status == LIVE else now,
    )

    assert hold.is_live() is live
    assert BookingHold.objects.filter(BookingHold.live_q(), pk=hold.pk).exists() is live
