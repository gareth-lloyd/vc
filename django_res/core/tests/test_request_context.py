"""Async-safe current-user/correlation context (SMELL-016).

Pins the public API of ``core.request_context`` and, crucially, that the actor
and correlation id survive a ``sync_to_async`` / ``async_to_sync`` round-trip —
the property a ``threading.local`` backing store could not guarantee under ASGI.
"""

from __future__ import annotations

import uuid

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth import get_user_model

from core.request_context import (
    clear_current_user,
    correlation,
    current_user_as,
    get_correlation_id,
    get_current_user,
    set_correlation_id,
    set_current_user,
)


def _user(pk: int):  # type: ignore[no-untyped-def]
    """In-memory actor (never saved) with the given pk; context only reads .pk."""
    return get_user_model()(pk=pk)


@pytest.fixture(autouse=True)
def _clean_context() -> None:
    clear_current_user()
    set_correlation_id(None)


def test_set_get_clear_current_user() -> None:
    assert get_current_user() is None
    user = _user(1)
    set_current_user(user)
    assert get_current_user() is user
    clear_current_user()
    assert get_current_user() is None


def test_current_user_as_restores_previous() -> None:
    outer = _user(1)
    set_current_user(outer)
    with current_user_as(_user(2)):
        assert getattr(get_current_user(), "pk", None) == 2
        with current_user_as(_user(3)):
            assert getattr(get_current_user(), "pk", None) == 3
        assert getattr(get_current_user(), "pk", None) == 2
    assert get_current_user() is outer


def test_correlation_mints_and_restores() -> None:
    assert get_correlation_id() is None
    with correlation() as cid:
        assert isinstance(cid, uuid.UUID)
        assert get_correlation_id() == cid
    assert get_correlation_id() is None


def test_correlation_adopts_supplied_id() -> None:
    given = uuid.uuid4()
    with correlation(given) as cid:
        assert cid == given
        assert get_correlation_id() == given


def test_actor_propagates_across_async_boundary() -> None:
    """The actor set in the sync caller is visible inside an async coroutine.

    ``async_to_sync(sync_to_async(...))`` round-trips through the asgiref
    threadpool; a ``threading.local`` would lose the actor here, a ContextVar
    carries it. This is the SMELL-016 regression guard.
    """
    user = _user(42)
    set_current_user(user)
    cid = uuid.uuid4()
    set_correlation_id(cid)

    @sync_to_async
    def _read_in_threadpool() -> tuple[object, object]:
        return getattr(get_current_user(), "pk", None), get_correlation_id()

    async def _coro() -> tuple[object, object]:
        return await _read_in_threadpool()

    seen_pk, seen_cid = async_to_sync(_coro)()
    assert seen_pk == 42
    assert seen_cid == cid
