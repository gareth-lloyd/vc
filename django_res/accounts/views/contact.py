"""Contacts CRUD + nested emails/phones + properties + invite-portal."""

from __future__ import annotations

from django.db import models, transaction
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from accounts.models import Contact, ContactEmail, ContactPhone
from accounts.serializers import (
    ContactEmailSerializer,
    ContactPhoneSerializer,
    ContactSerializer,
)
from core.api import IsStaff, not_implemented_response


class ContactFilterSet(FilterSet):
    class Meta:
        model = Contact
        fields = {
            "status": ["exact"],
            "preferred_method": ["exact"],
        }


class ContactViewSet(viewsets.ModelViewSet[Contact]):
    """`/contacts` — owner/agent/manager records."""

    queryset = Contact.objects.all().prefetch_related("emails", "phones")
    serializer_class = ContactSerializer
    permission_classes = [IsStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ContactFilterSet
    search_fields = ["first_name", "last_name", "company", "emails__email"]
    ordering_fields = ["last_name", "first_name", "created_at"]

    @action(detail=True, methods=["get"], url_path="properties")
    def properties(self, request: Request, pk: str | None = None) -> Response:
        """Reverse-list: properties this contact is assigned to.

        Returns the through-row representation (role + flags) keyed by
        property id. Hard-codes a shallow representation to avoid a circular
        import of properties.serializers.
        """
        contact = self.get_object()
        assignments = contact.property_assignments.select_related("property")
        data = [
            {
                "id": a.pk,
                "property_id": a.property_id,
                "property_slug": getattr(a.property, "slug", None),
                "role": a.role,
                "is_primary": a.is_primary,
                "start_date": a.start_date,
                "end_date": a.end_date,
            }
            for a in assignments
        ]
        return Response(data)


class ContactInvitePortalView(viewsets.ViewSet):
    """`POST /contacts/{id}:invite-portal` — owner portal invite (501)."""

    permission_classes = [IsStaff]

    def create(self, request: Request, contact_pk: str | None = None) -> Response:
        get_object_or_404(Contact, pk=contact_pk)
        return not_implemented_response("Owner-portal invitation flow is not yet wired.")


class ContactEmailViewSet(viewsets.ModelViewSet[ContactEmail]):
    """Nested `/contacts/{contact_id}/emails`."""

    serializer_class = ContactEmailSerializer
    permission_classes = [IsStaff]

    def get_queryset(self) -> models.QuerySet[ContactEmail]:
        return ContactEmail.objects.filter(contact_id=self.kwargs["contact_pk"]).order_by(
            "-is_primary", "id"
        )

    def perform_create(self, serializer: BaseSerializer[ContactEmail]) -> None:
        contact = get_object_or_404(Contact, pk=self.kwargs["contact_pk"])
        serializer.save(contact=contact)


class ContactPhoneViewSet(viewsets.ModelViewSet[ContactPhone]):
    """Nested `/contacts/{contact_id}/phones`."""

    serializer_class = ContactPhoneSerializer
    permission_classes = [IsStaff]

    def get_queryset(self) -> models.QuerySet[ContactPhone]:
        return ContactPhone.objects.filter(contact_id=self.kwargs["contact_pk"]).order_by(
            "-is_primary", "id"
        )

    def perform_create(self, serializer: BaseSerializer[ContactPhone]) -> None:
        contact = get_object_or_404(Contact, pk=self.kwargs["contact_pk"])
        serializer.save(contact=contact)


class ContactPropertiesView(viewsets.ViewSet):
    """Alias for `GET /contacts/{id}/properties` mounted off the colon-verb URL.

    The viewset's `properties` action above covers the canonical path; this
    placeholder reserves the import for routing modules that wish to wire it
    flat.
    """

    permission_classes = [IsStaff]


class SetPrimaryEmailView(viewsets.ViewSet):
    """`POST /contacts/{id}/emails/{email_id}:set-primary`."""

    permission_classes = [IsStaff]

    @transaction.atomic
    def create(
        self,
        request: Request,
        contact_pk: str | None = None,
        email_pk: str | None = None,
    ) -> Response:
        contact_id = int(contact_pk) if contact_pk is not None else 0
        email = get_object_or_404(ContactEmail, pk=email_pk, contact_id=contact_id)
        # Demote the existing primary first so we don't violate the partial
        # unique constraint on (contact, is_primary=True).
        ContactEmail.objects.filter(contact_id=contact_id, is_primary=True).exclude(
            pk=email.pk
        ).update(is_primary=False)
        email.is_primary = True
        email.save(update_fields=["is_primary", "updated_at"])
        return Response(ContactEmailSerializer(email).data, status=status.HTTP_200_OK)


class SetPrimaryPhoneView(viewsets.ViewSet):
    """`POST /contacts/{id}/phones/{phone_id}:set-primary`."""

    permission_classes = [IsStaff]

    @transaction.atomic
    def create(
        self,
        request: Request,
        contact_pk: str | None = None,
        phone_pk: str | None = None,
    ) -> Response:
        contact_id = int(contact_pk) if contact_pk is not None else 0
        phone = get_object_or_404(ContactPhone, pk=phone_pk, contact_id=contact_id)
        ContactPhone.objects.filter(contact_id=contact_id, is_primary=True).exclude(
            pk=phone.pk
        ).update(is_primary=False)
        phone.is_primary = True
        phone.save(update_fields=["is_primary", "updated_at"])
        return Response(ContactPhoneSerializer(phone).data, status=status.HTTP_200_OK)
