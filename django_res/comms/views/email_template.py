"""`/email-templates/*` — the operator-facing template admin API.

Lookup is by `key` (e.g. `booking.confirmation`), not pk. Reads (list, detail,
preview, version history) are open to any staff; publishing a new version and
firing a test-send are gated to ADMIN / RESERVATIONS via `IsReservationsWriter`.

The active row for a key is the single source of truth every live send renders
against, so publish is render-validated, versioned, idempotent and race-safe in
`EmailTemplateService.publish_version`.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from comms.contexts import resolve_context
from comms.exceptions import TemplateRenderError
from comms.models import EmailTemplate
from comms.serializers import (
    EmailLogSerializer,
    EmailTemplateDetailSerializer,
    EmailTemplateListSerializer,
    EmailTemplatePreviewRequestSerializer,
    EmailTemplatePublishSerializer,
    TestSendRequestSerializer,
)
from comms.services import TEMPLATE_RENDER_ERRORS, EmailService, EmailTemplateService
from core.api.permissions import IsReservationsWriter, IsStaff

if TYPE_CHECKING:
    from rest_framework.permissions import BasePermission as _BasePermission
    from rest_framework.serializers import BaseSerializer

    from accounts.models import User

# url_path fragments that double as serializer keys for draft overrides.
_DRAFT_OVERRIDE_FIELDS = ("subject_template", "body_template_mjml")


def _context_from_request(request: Request, data: dict[str, Any]) -> dict[str, Any]:
    """Resolve the render context from the request.

    `context` is read raw from `request.data` (it can't be a serializer field —
    the name collides with `Serializer.context`); `booking_id` / `quotation_id`
    come validated off the request serializer.
    """
    explicit = request.data.get("context")
    return resolve_context(
        context=explicit if isinstance(explicit, dict) else None,
        booking_id=data.get("booking_id"),
        quotation_id=data.get("quotation_id"),
    )


class EmailTemplateViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Key-addressed template admin. See module docstring for the authz split."""

    lookup_field = "key"
    # Keys carry dots (`booking.confirmation`); the default `[^/.]+` would split
    # them and DRF format-suffix parsing would read `.confirmation` as a format.
    # Dotted-key routing + format suffixes disabled on the router == C2.
    lookup_value_regex = r"[\w.]+"

    def get_queryset(self) -> Any:
        return (
            EmailTemplate.objects.filter(is_active=True)
            .select_related("updated_by")
            .order_by("key")
        )

    def filter_queryset(self, queryset: Any) -> Any:
        # The catalogue list supports an optional `?key=` exact filter. Detail
        # routes carry the key in the path (never a query param), so this is a
        # no-op for `get_object()`.
        key = self.request.query_params.get("key")
        if key:
            queryset = queryset.filter(key=key)
        return queryset

    def get_serializer_class(self) -> type[BaseSerializer[Any]]:
        if self.action == "list":
            return EmailTemplateListSerializer
        return EmailTemplateDetailSerializer

    def get_permissions(self) -> list[_BasePermission]:
        # Writes (publish, test-send) need a reservations/admin role; everything
        # else is a read — preview renders nothing persistent, so it's open to
        # any staff (don't block a VIEWER from previewing).
        writers: tuple[type[BasePermission], ...] = (IsAuthenticated, IsReservationsWriter)
        readers: tuple[type[BasePermission], ...] = (IsAuthenticated, IsStaff)
        classes = writers if self.action in ("update", "test_send") else readers
        return [cls() for cls in classes]

    def update(self, request: Request, key: str) -> Response:
        """PUT — publish a new active version (or v1 for a new key).

        `TemplatePublishError` (malformed template / MJML) is a 400 `DomainError`
        and propagates to the canonical exception handler untouched.
        """
        serializer = EmailTemplatePublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template = EmailTemplateService.publish_version(
            key=key,
            actor=cast("User", request.user),
            **serializer.validated_data,
        )
        return Response(EmailTemplateDetailSerializer(template).data)

    @action(detail=True, methods=["post"], url_path="preview")
    def preview(self, request: Request, key: str) -> Response:
        """Render the active row — or in-flight draft edits — against context.

        Writes no `EmailLog`. Draft MJML is compiled on the fly (C3); a compile
        or template-syntax error returns 400 with the errors, never a 500.
        """
        serializer = EmailTemplatePreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        overrides = {f: data[f] for f in _DRAFT_OVERRIDE_FIELDS if f in data}
        if overrides:
            # Previewing in-flight edits: start from the active row (a brand-new
            # key has none yet) and overlay the draft fields, compiling the
            # draft MJML on the fly.
            active = EmailTemplate.objects.filter(key=key, is_active=True).first()
            render_kwargs: dict[str, Any] = {
                "subject_template": active.subject_template if active else "",
                "body_template_mjml": active.body_template_mjml if active else "",
            }
            render_kwargs.update(overrides)
        else:
            # No edits: render the stored, already-compiled HTML — no recompile.
            template = self.get_object()
            render_kwargs = {
                "subject_template": template.subject_template,
                "body_template_html": template.body_template_html,
            }

        context = _context_from_request(request, data)
        try:
            rendered = EmailTemplateService.render(context=context, **render_kwargs)
        except TEMPLATE_RENDER_ERRORS as exc:
            # A malformed Django tag in a draft is bad input, not a server fault.
            # (`MjmlCompileError` is already a 400 `DomainError` and propagates
            # to the canonical handler on its own.)
            raise TemplateRenderError(
                "Template contains invalid Django template syntax.",
                field_errors={"body_template_mjml": [str(exc)]},
            ) from exc
        return Response(
            {
                "rendered_subject": rendered["rendered_subject"],
                "rendered_body_html": rendered["rendered_body_html"],
                "rendered_body_text": rendered["rendered_body_text"],
            }
        )

    @action(detail=True, methods=["post"], url_path="test-send")
    def test_send(self, request: Request, key: str) -> Response:
        """Dispatch the active template to a test recipient (defaults to caller).

        Correlation carries **only** `{test_send, nonce}` — never a real
        booking/quotation id, even when rendering against one — so a test never
        shows up in a booking's Comms tab. The nonce defeats send dedup so each
        test-send writes a fresh `EmailLog` (C5).
        """
        self.get_object()  # 404 if the key has no active template.
        serializer = TestSendRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        recipient = data.get("to") or getattr(request.user, "email", "")
        if not recipient:
            raise ValidationError({"to": ["No `to` address and the caller has no email on file."]})

        context = _context_from_request(request, data)
        log = EmailService.send(
            template_key=key,
            context=context,
            to=[recipient],
            sender_user=cast("User", request.user),
            correlation={"test_send": True, "nonce": str(uuid.uuid4())},
        )
        return Response(EmailLogSerializer(log).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, key: str) -> Response:
        """Full version history for a key, newest first."""
        rows = list(
            EmailTemplate.objects.filter(key=key).select_related("updated_by").order_by("-version")
        )
        if not rows:
            raise NotFound("No template for that key.")
        return Response(EmailTemplateDetailSerializer(rows, many=True).data)

    @action(detail=True, methods=["get"], url_path=r"versions/(?P<n>[0-9]+)")
    def version_detail(self, request: Request, key: str, n: str) -> Response:
        """A single historical version (read-only)."""
        template = get_object_or_404(EmailTemplate, key=key, version=int(n))
        return Response(EmailTemplateDetailSerializer(template).data)
