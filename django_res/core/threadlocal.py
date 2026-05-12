"""Threadlocal current-user/correlation context used by audit middleware + signals."""

from __future__ import annotations

import contextlib
import threading
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from django.contrib.auth.models import AbstractBaseUser

_local = threading.local()


def set_current_user(user: AbstractBaseUser | None) -> None:
    _local.user = user


def get_current_user() -> AbstractBaseUser | None:
    return getattr(_local, "user", None)


def clear_current_user() -> None:
    if hasattr(_local, "user"):
        del _local.user


def set_correlation_id(value: uuid.UUID | None) -> None:
    _local.correlation_id = value


def get_correlation_id() -> uuid.UUID | None:
    return getattr(_local, "correlation_id", None)


@contextlib.contextmanager
def current_user_as(user: AbstractBaseUser | None) -> Iterator[None]:
    prev = get_current_user()
    set_current_user(user)
    try:
        yield
    finally:
        set_current_user(prev)


@contextlib.contextmanager
def correlation(correlation_id: uuid.UUID | None = None) -> Iterator[uuid.UUID]:
    prev = get_correlation_id()
    cid = correlation_id or uuid.uuid4()
    set_correlation_id(cid)
    try:
        yield cid
    finally:
        set_correlation_id(prev)
