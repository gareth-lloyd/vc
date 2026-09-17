"""`core.transitions` — the one lock → guard → save → record primitive.

Exercised against `Enquiry` (any `AuditedModel` with a `status` column would
do; `core.tests` is exempt from the no-domain-import contract). The table here
is a local fixture, not the real enquiry table, so these tests pin the
primitive's behaviour rather than a business rule.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from core.exceptions import InvalidTransition
from core.transitions import assert_allowed, can_transition, transition
from reservations.enums import EnquiryStatus
from reservations.factories import EnquiryFactory
from reservations.models import Enquiry

NEW = EnquiryStatus.NEW.value
PROGRESSING = EnquiryStatus.PROGRESSING.value
DEAD = EnquiryStatus.DEAD.value

TABLE: dict[str, frozenset[str]] = {
    NEW: frozenset({PROGRESSING, DEAD}),
    PROGRESSING: frozenset({DEAD}),
    DEAD: frozenset(),
}

pytestmark = pytest.mark.django_db


def _enquiry(**kwargs: Any) -> Enquiry:
    return cast(Enquiry, EnquiryFactory(**kwargs))


def test_transition_moves_status_and_returns_prev() -> None:
    enquiry = _enquiry(status=NEW)

    prev = transition(enquiry, PROGRESSING, table=TABLE)

    assert prev == NEW
    assert enquiry.status == PROGRESSING
    enquiry.refresh_from_db()
    assert enquiry.status == PROGRESSING


def test_transition_refuses_edge_not_in_table() -> None:
    enquiry = _enquiry(status=PROGRESSING)
    recorded: list[tuple[str, str]] = []

    with pytest.raises(InvalidTransition) as exc:
        transition(enquiry, NEW, table=TABLE, record=lambda a, b: recorded.append((a, b)))

    assert exc.value.from_state == PROGRESSING
    assert exc.value.to_state == NEW
    assert exc.value.allowed == [DEAD]
    assert enquiry.status == PROGRESSING
    assert recorded == []
    enquiry.refresh_from_db()
    assert enquiry.status == PROGRESSING


def test_transition_unknown_from_status_is_terminal() -> None:
    enquiry = _enquiry(status=EnquiryStatus.CONVERTED)

    with pytest.raises(InvalidTransition) as exc:
        transition(enquiry, DEAD, table=TABLE)

    assert exc.value.allowed == []


def test_transition_applies_extra_updates_in_same_save() -> None:
    enquiry = _enquiry(status=NEW)

    transition(enquiry, DEAD, table=TABLE, extra_updates={"lost_reason": "gone quiet"})

    enquiry.refresh_from_db()
    assert enquiry.status == DEAD
    assert enquiry.lost_reason == "gone quiet"


def test_transition_calls_record_with_prev_and_to() -> None:
    enquiry = _enquiry(status=NEW)
    recorded: list[tuple[str, str]] = []

    transition(enquiry, PROGRESSING, table=TABLE, record=lambda a, b: recorded.append((a, b)))

    assert recorded == [(NEW, PROGRESSING)]


def test_transition_record_raising_rolls_back_status() -> None:
    enquiry = _enquiry(status=NEW, lost_reason="")

    def boom(prev: str, to: str) -> None:
        raise RuntimeError("event write failed")

    with pytest.raises(RuntimeError, match="event write failed"):
        transition(enquiry, DEAD, table=TABLE, extra_updates={"lost_reason": "x"}, record=boom)

    # In-memory state restored, so a caller that catches and carries on
    # doesn't hold an instance claiming a move that never committed.
    assert enquiry.status == NEW
    assert enquiry.lost_reason == ""
    fresh = Enquiry.objects.get(pk=enquiry.pk)
    assert fresh.status == NEW
    assert fresh.lost_reason == ""


def test_transition_refreshes_from_db_before_guard() -> None:
    enquiry = _enquiry(status=NEW)
    stale = Enquiry.objects.get(pk=enquiry.pk)

    transition(enquiry, DEAD, table=TABLE, extra_updates={"lost_reason": "gone quiet"})

    # `stale` still reads NEW in memory; the guard must see the locked DEAD row.
    with pytest.raises(InvalidTransition) as exc:
        transition(stale, PROGRESSING, table=TABLE)
    assert exc.value.from_state == DEAD
    assert stale.status == DEAD


def test_can_transition_and_assert_allowed() -> None:
    enquiry = _enquiry(status=NEW)

    assert can_transition(enquiry, PROGRESSING, table=TABLE)
    assert not can_transition(enquiry, NEW, table=TABLE)
    assert_allowed(enquiry, DEAD, table=TABLE)
    with pytest.raises(InvalidTransition) as exc:
        assert_allowed(enquiry, NEW, table=TABLE)
    assert exc.value.allowed == [DEAD, PROGRESSING]
