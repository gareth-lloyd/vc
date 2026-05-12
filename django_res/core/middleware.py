"""Middleware that populates the threadlocal current-user for audit signals."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from core.threadlocal import (
    clear_current_user,
    correlation,
    set_current_user,
)

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


class AuditMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            set_current_user(user)
        else:
            set_current_user(None)
        try:
            with correlation():
                return self.get_response(request)
        finally:
            clear_current_user()
