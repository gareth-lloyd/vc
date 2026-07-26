"""POST /api/wordpress/enquiries — inbound enquiry capture from the WP site.

Design: 08-integrations.md §"Inbound: WordPress → Django". Token auth is
declared HERE, not in the DRF defaults, so the WP token works only on this
surface (and SessionAuthentication's CSRF dance never applies). The email pin
is defence in depth: only the WP service user's token is accepted even if
another valid token leaks. All business logic — the record-or-replay ledger,
per-call AuditLog — lives in `reservations.services.wordpress_intake`;
auth-rejected calls never reach the handler and are covered by request
logging. The Enquiry itself is audit-tracked, so a create also emits the
standard field-diff row with the service user as actor.
"""

from __future__ import annotations

from typing import cast

from django.conf import settings
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.models import User
from reservations.serializers.wordpress import WordPressEnquirySerializer
from reservations.services.wordpress_intake import handle_wordpress_enquiry


class IsWordPressServiceUser(BasePermission):
    """Pin the surface to the dedicated service principal (by email — the
    User model has no username column). A blank setting fails closed."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        pin = settings.WORDPRESS_SERVICE_EMAIL
        user = request.user
        return bool(pin and user and user.is_authenticated and user.email.lower() == pin.lower())


class WordPressEnquiryView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsWordPressServiceUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "wordpress_inbound"

    def post(self, request: Request) -> Response:
        serializer = WordPressEnquirySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        call = handle_wordpress_enquiry(
            serializer.validated_data,
            actor=cast(User, request.user),  # IsWordPressServiceUser guarantees auth
        )
        return Response(call.response_body, status=call.response_status)
