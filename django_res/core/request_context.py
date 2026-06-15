"""Async-safe current-user/correlation context used by audit middleware + signals.

Backed by :class:`contextvars.ContextVar` rather than ``threading.local`` so the
request actor and correlation id propagate correctly across ``sync_to_async`` /
``async_to_sync`` boundaries (SMELL-016). This is the same mechanism structlog
already uses for ``request_id``, collapsing the two halves of "request context"
onto one propagation primitive.

Under WSGI a ContextVar behaves exactly like the old threadlocal (each request
runs start-to-finish on its own thread, with its own context); under ASGI it
additionally tracks the per-coroutine context, where a threadlocal would leak or
lose the actor and silently write the wrong ``actor`` onto audit rows.
"""

from __future__ import annotations

import contextlib
import contextvars
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from django.contrib.auth.models import AbstractBaseUser

_current_user: contextvars.ContextVar[AbstractBaseUser | None] = contextvars.ContextVar(
    "audit_current_user", default=None
)
_correlation_id: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "audit_correlation_id", default=None
)


def set_current_user(user: AbstractBaseUser | None) -> None:
    _current_user.set(user)


def get_current_user() -> AbstractBaseUser | None:
    return _current_user.get()


def clear_current_user() -> None:
    _current_user.set(None)


def set_correlation_id(value: uuid.UUID | None) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> uuid.UUID | None:
    return _correlation_id.get()


@contextlib.contextmanager
def current_user_as(user: AbstractBaseUser | None) -> Iterator[None]:
    token = _current_user.set(user)
    try:
        yield
    finally:
        _current_user.reset(token)


@contextlib.contextmanager
def correlation(correlation_id: uuid.UUID | None = None) -> Iterator[uuid.UUID]:
    cid = correlation_id or uuid.uuid4()
    token = _correlation_id.set(cid)
    try:
        yield cid
    finally:
        _correlation_id.reset(token)
