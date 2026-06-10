"""Top-level cross-cutting endpoints (health, system, audit-log)."""

from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import DatabaseError, connection, models
from django.http import FileResponse, Http404, HttpRequest
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import filters, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import IsStaff, IsStaffRoleAdmin
from core.models import AuditLog, SystemSettings
from core.serializers.audit_log import AuditLogSerializer
from core.serializers.system_settings import SystemSettingsSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request: Request) -> Response:
    """Liveness probe — always 200 if the process is up."""
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
def health_ready(request: Request) -> Response:
    """Readiness probe — DB connectivity smoke test."""
    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        db_ok = False
    status_code = 200 if db_ok else 503
    return Response({"status": "ok" if db_ok else "degraded", "db": db_ok}, status=status_code)


@api_view(["GET"])
@permission_classes([AllowAny])
def system_version(request: Request) -> Response:
    """Build version + git SHA for client-side diagnostics."""
    return Response(
        {
            "version": os.environ.get("APP_VERSION", "dev"),
            "git_sha": os.environ.get("GIT_SHA", "unknown"),
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def system_time(request: Request) -> Response:
    """Server clock — used by the SPA to detect client clock skew."""
    return Response({"now": timezone.now().isoformat()})


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet[AuditLog]):
    """Read-only audit-log query surface.

    Filters: `actor`, `entity_type` (app_label.model), `entity_id`, `action`,
    `created_after`, `created_before`. Admin-only.
    """

    serializer_class = AuditLogSerializer
    permission_classes = [IsStaffRoleAdmin]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_queryset(self) -> models.QuerySet[AuditLog]:
        qs = AuditLog.objects.all().select_related("content_type", "actor")
        params = self.request.query_params

        if actor := params.get("actor"):
            qs = qs.filter(actor_id=int(actor))
        if entity_type := params.get("entity_type"):
            # Format: "app_label.model"
            if "." in entity_type:
                app_label, model = entity_type.split(".", 1)
                ct = ContentType.objects.filter(app_label=app_label, model=model).first()
                qs = qs.filter(content_type=ct) if ct else qs.none()
        if entity_id := params.get("entity_id"):
            qs = qs.filter(object_id=entity_id)
        if action := params.get("action"):
            # field_diffs is a free JSON blob; expose a coarse "any diff contains key"
            # filter. Stored procedure / GIN index would be the production path.
            qs = qs.filter(field_diffs__has_key=action)
        if created_after := params.get("created_after"):
            qs = qs.filter(created_at__gte=created_after)
        if created_before := params.get("created_before"):
            qs = qs.filter(created_at__lte=created_before)
        return qs


class SystemSettingsView(APIView):
    """`GET / PATCH /system/settings` — admin-managed singleton."""

    permission_classes = [IsStaffRoleAdmin]

    def get(self, request: Request) -> Response:
        instance = SystemSettings.get_solo()
        return Response(SystemSettingsSerializer(instance).data)

    def patch(self, request: Request) -> Response:
        instance = SystemSettings.get_solo()
        new_blob = request.data.get("settings") if isinstance(request.data, dict) else None
        if isinstance(new_blob, dict):
            instance.settings = {**(instance.settings or {}), **new_blob}
            instance.save(update_fields=["settings", "updated_at"])
        return Response(SystemSettingsSerializer(instance).data)


class CurrentPermissionsView(APIView):
    """Return the caller's `auth.Permission` codenames and staff role."""

    permission_classes = [IsStaff]

    def get(self, request: Request) -> Response:
        user = request.user
        codenames = sorted(user.get_all_permissions())
        role = getattr(user, "role", None)
        return Response(
            {
                "role": role,
                "is_superuser": bool(getattr(user, "is_superuser", False)),
                "permissions": codenames,
            }
        )


@ensure_csrf_cookie
def spa_index(request: HttpRequest) -> FileResponse:
    """Serve the built SPA's `index.html` for client-side routes.

    Single-origin deployment: WhiteNoise serves the hashed asset files
    directly; this is the history-fallback so deep links and refreshes on
    client-side routes return the SPA shell. Wired as the URLconf catch-all
    *after* `/api/`, `/admin/`, `/static/`.

    `@ensure_csrf_cookie` primes the `csrftoken` cookie with the HTML shell:
    the first session-authenticated POST (typically `/auth/login`) needs it
    already set, otherwise `CsrfViewMiddleware` rejects it and the user has
    to submit twice. The SPA additionally primes via `GET /auth/csrf`
    (`accounts.views.CsrfView`) on boot, which also covers the Vite dev
    server origin where this view never runs.

    `settings.SPA_ROOT` is read per-request so tests can override it and so
    a build-less local checkout (Vite proxy serves the SPA) cleanly 404s
    instead of 500-ing.
    """
    index = Path(settings.SPA_ROOT) / "index.html"
    if not index.is_file():
        raise Http404("SPA build not present")
    return FileResponse(index.open("rb"), content_type="text/html")
