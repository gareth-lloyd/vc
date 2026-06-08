"""Project middleware: audit threadlocal + WhiteNoise media serving."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING

import structlog
from django.conf import settings as django_settings
from whitenoise.middleware import WhiteNoiseMiddleware

from core.threadlocal import (
    clear_current_user,
    correlation,
    set_current_user,
)

if TYPE_CHECKING:
    from django.conf import LazySettings
    from django.http import HttpRequest, HttpResponse


class MediaWhiteNoiseMiddleware(WhiteNoiseMiddleware):
    """WhiteNoise that also serves uploaded/seeded media under ``MEDIA_URL``.

    The base middleware serves the Django/admin static files and the SPA
    build; this additionally mounts ``MEDIA_ROOT`` so ``/media/...`` is served
    by one mechanism in every environment, rather than a ``DEBUG``-only
    ``static()`` URL route. That is what makes seeded villa imagery render on
    staging (``DEBUG=False``).

    WhiteNoise indexes files at boot; files written *afterwards* — a live
    ``seed_dev`` run, a user upload — are only served when
    ``WHITENOISE_AUTOREFRESH`` is on (the default under ``DEBUG``, enabled
    explicitly on staging). Real production uploads belong in remote storage,
    which would replace this mount entirely.
    """

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse] | None = None,
        settings: LazySettings = django_settings,
    ) -> None:
        super().__init__(get_response, settings)
        media_root = getattr(settings, "MEDIA_ROOT", None)
        media_url = getattr(settings, "MEDIA_URL", None)
        # In autorefresh mode `add_files` just registers the directory (served
        # via a live filesystem lookup), so a not-yet-created MEDIA_ROOT is
        # fine; without it, `add_files` scans at boot and warns on a missing
        # dir, so guard with isdir to keep that path quiet.
        if media_root and media_url and (self.autorefresh or os.path.isdir(media_root)):
            self.add_files(media_root, prefix=media_url)


class AuditMiddleware:
    """Set the audit user/correlation context for the request.

    Runs just inside ``django_structlog``'s ``RequestMiddleware``, which has
    already bound a ``request_id`` into structlog's contextvars. We adopt that
    id as the audit ``correlation_id`` so a structured log line (carrying
    ``request_id``) joins directly to the ``AuditLog`` rows written during the
    same request (stamped with ``correlation_id``). If no usable ``request_id``
    is present (admin, non-HTTP, or RequestMiddleware not in the chain),
    ``correlation()`` mints its own — the join is best-effort, never required.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            set_current_user(user)
        else:
            set_current_user(None)
        try:
            with correlation(self._adopted_request_id()) as cid:
                # Alias the id under `correlation_id` too, so a log search can
                # match either key and they are guaranteed identical.
                structlog.contextvars.bind_contextvars(correlation_id=str(cid))
                return self.get_response(request)
        finally:
            clear_current_user()

    @staticmethod
    def _adopted_request_id() -> uuid.UUID | None:
        """The structlog-bound request_id as a UUID, or None to mint a fresh one."""
        request_id = structlog.contextvars.get_contextvars().get("request_id")
        if not isinstance(request_id, str):
            return None
        try:
            return uuid.UUID(request_id)
        except ValueError:
            # An inbound X-Request-ID header need not be a UUID; fall back.
            return None
