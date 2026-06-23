"""Contacts CRUD + nested emails/phones + properties + invite-portal."""

from __future__ import annotations

from django.db import models, transaction
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import CharFilter, DjangoFilterBackend, FilterSet
from rest_framework import filters, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from accounts.enums import PersonStatus, PersonTag
from accounts.models import Person, PersonEmail, PersonPhone
from accounts.serializers import (
    ContactEmailSerializer,
    ContactMergeSerializer,
    ContactPhoneSerializer,
    ContactSerializer,
)
from core.api import IsStaff, IsStaffRoleAdmin, not_implemented_response

_LAST_CHANNEL_MESSAGE = "Cannot remove the last contact channel of an active contact."


def _guard_last_channel(contact: Person, *, keeping_emails: int, keeping_phones: int) -> None:
    """Block a channel deletion that would leave an ACTIVE contact unreachable.

    Counts the *other* channel type too: an active contact may drop its last
    email as long as a phone remains, and vice versa. INACTIVE/ANONYMIZED
    contacts are exempt (mirrors the contactability gate in ContactSerializer).
    """
    if contact.status != PersonStatus.ACTIVE.value:
        return
    if keeping_emails == 0 and keeping_phones == 0:
        raise serializers.ValidationError(_LAST_CHANNEL_MESSAGE)


class ContactFilterSet(FilterSet):
    # GAP-040: `?tags=vip,trade` → customers carrying ANY of the listed tags
    # (overlap). A method filter because the Meta dict shorthand can't express
    # the `__overlap` array lookup.
    tags = CharFilter(method="filter_tags")

    class Meta:
        model = Person
        fields = {
            "status": ["exact"],
            "preferred_method": ["exact"],
            # GAP-045 D2: filter the directory to customers vs business contacts.
            # No `?kind=` → all (fork 3). The owner/agent assignment picker passes
            # `kind=contact` so it never offers customer mirrors.
            "kind": ["exact"],
        }

    def filter_tags(
        self, queryset: models.QuerySet[Person], _name: str, value: str
    ) -> models.QuerySet[Person]:
        valid = {t.value for t in PersonTag}
        wanted = [tok for tok in (raw.strip() for raw in value.split(",")) if tok in valid]
        if not wanted:
            # All tokens unknown (or empty) — ignore the filter rather than 400
            # or return a silently-empty page.
            return queryset
        return queryset.filter(tags__overlap=wanted)


class ContactViewSet(viewsets.ModelViewSet[Person]):
    """`/contacts` — owner/agent/manager records."""

    # GAP-045 D2: `/contacts` is a kind-aware directory of ALL Persons —
    # customers included. Filter with `?kind=customer` / `?kind=contact`; no
    # param lists both (fork 3).
    queryset = Person.objects.select_related("agency").prefetch_related("emails", "phones")
    serializer_class = ContactSerializer
    permission_classes = [IsStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ContactFilterSet
    # GAP-046: search the structured `agency__name` (a single-valued forward FK →
    # no row multiplication, so no COUNT inflation — the CLAUDE.md multi-valued
    # search_fields caveat is N/A), not the free-text `company` it replaced.
    search_fields = ["first_name", "last_name", "agency__name", "emails__email"]
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
        get_object_or_404(Person, pk=contact_pk)
        return not_implemented_response("Owner-portal invitation flow is not yet wired.")


class ContactMergeView(viewsets.ViewSet):
    """`POST /contacts/{id}:merge` — delegates to `Person.merge(target)`.

    Destructive (hard-deletes the source) so we gate on `IsStaffRoleAdmin`.
    Operates on any Person — customers included (GAP-045 D5: dedup customers
    via this verb, the canonical `Person.merge` path).
    """

    permission_classes = [IsStaffRoleAdmin]

    def create(self, request: Request, contact_pk: str | None = None) -> Response:
        source = get_object_or_404(Person, pk=contact_pk)
        serializer = ContactMergeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_id = serializer.validated_data["target_contact_id"]
        target = get_object_or_404(Person, pk=target_id)
        try:
            source.merge(target)
        except ValueError as exc:
            return Response(
                {"code": "merge_invalid", "detail": str(exc), "field_errors": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(ContactSerializer(target).data, status=status.HTTP_200_OK)


class ContactAnonymizeView(viewsets.ViewSet):
    """`POST /contacts/{id}:anonymize` — delegates to `Person.anonymize()`.

    Admin-only — GDPR-class operation. Idempotent (running twice on an
    already-anonymized contact leaves the redacted state intact). Operates on
    any Person — customers included (GAP-045 D5: Guest is retired).
    """

    permission_classes = [IsStaffRoleAdmin]

    def create(self, request: Request, contact_pk: str | None = None) -> Response:
        contact = get_object_or_404(Person, pk=contact_pk)
        contact.anonymize()
        return Response(ContactSerializer(contact).data, status=status.HTTP_200_OK)


class ContactEmailViewSet(viewsets.ModelViewSet[PersonEmail]):
    """Nested `/contacts/{contact_id}/emails`."""

    serializer_class = ContactEmailSerializer
    permission_classes = [IsStaff]

    def get_queryset(self) -> models.QuerySet[PersonEmail]:
        return PersonEmail.objects.filter(contact_id=self.kwargs["contact_pk"]).order_by(
            "-is_primary", "id"
        )

    def perform_create(self, serializer: BaseSerializer[PersonEmail]) -> None:
        contact = get_object_or_404(Person, pk=self.kwargs["contact_pk"])
        serializer.save(contact=contact)

    def perform_destroy(self, instance: PersonEmail) -> None:
        contact = instance.contact
        _guard_last_channel(
            contact,
            keeping_emails=contact.emails.exclude(pk=instance.pk).count(),
            keeping_phones=contact.phones.count(),
        )
        instance.delete()


class ContactPhoneViewSet(viewsets.ModelViewSet[PersonPhone]):
    """Nested `/contacts/{contact_id}/phones`."""

    serializer_class = ContactPhoneSerializer
    permission_classes = [IsStaff]

    def get_queryset(self) -> models.QuerySet[PersonPhone]:
        return PersonPhone.objects.filter(contact_id=self.kwargs["contact_pk"]).order_by(
            "-is_primary", "id"
        )

    def perform_create(self, serializer: BaseSerializer[PersonPhone]) -> None:
        contact = get_object_or_404(Person, pk=self.kwargs["contact_pk"])
        serializer.save(contact=contact)

    def perform_destroy(self, instance: PersonPhone) -> None:
        contact = instance.contact
        _guard_last_channel(
            contact,
            keeping_emails=contact.emails.count(),
            keeping_phones=contact.phones.exclude(pk=instance.pk).count(),
        )
        instance.delete()


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
        email = get_object_or_404(PersonEmail, pk=email_pk, contact_id=contact_id)
        # Demote the existing primary first so we don't violate the partial
        # unique constraint on (contact, is_primary=True).
        PersonEmail.objects.filter(contact_id=contact_id, is_primary=True).exclude(
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
        phone = get_object_or_404(PersonPhone, pk=phone_pk, contact_id=contact_id)
        PersonPhone.objects.filter(contact_id=contact_id, is_primary=True).exclude(
            pk=phone.pk
        ).update(is_primary=False)
        phone.is_primary = True
        phone.save(update_fields=["is_primary", "updated_at"])
        return Response(ContactPhoneSerializer(phone).data, status=status.HTTP_200_OK)
