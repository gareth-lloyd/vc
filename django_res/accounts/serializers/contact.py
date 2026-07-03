"""Person / PersonEmail / PersonPhone serializers."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from rest_framework import serializers

from accounts.enums import ContactType, PersonKind, PersonStatus, PersonTag
from accounts.models import Organisation, Person, PersonEmail, PersonPhone
from accounts.serializers.organisation import OrganisationSummarySerializer


class ContactMergeSerializer(serializers.Serializer[None]):
    """Body of `POST /contacts/{id}:merge` — the surviving contact's id."""

    target_contact_id = serializers.IntegerField()


class ContactEmailSerializer(serializers.ModelSerializer[PersonEmail]):
    class Meta:
        model = PersonEmail
        fields = ["id", "email", "label", "is_primary", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ContactPhoneSerializer(serializers.ModelSerializer[PersonPhone]):
    class Meta:
        model = PersonPhone
        fields = ["id", "number", "label", "is_primary", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ContactSerializer(serializers.ModelSerializer[Person]):
    """Full Person representation with inline emails/phones.

    `emails`/`phones` are writable on **create** so a new active contact can be
    born reachable in one request (see `validate`/`create`). On **update** the
    inline lists are ignored — channels are managed through the nested
    `/contacts/{id}/emails` and `/phones` endpoints.
    """

    emails = ContactEmailSerializer(many=True, required=False)
    phones = ContactPhoneSerializer(many=True, required=False)
    # `user` is a OneToOne to the swappable AUTH_USER_MODEL, which DRF can't
    # auto-discover; surface it read-only for now (link operations land in a
    # dedicated endpoint when the portal flow is wired).
    user: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(
        read_only=True, allow_null=True
    )
    # GAP-046: writable agency by pk + a read-only nested view under a distinct
    # name so the write pk and the read object don't collide on `source`.
    agency = serializers.PrimaryKeyRelatedField(
        queryset=Organisation.objects.all(), allow_null=True, required=False
    )
    agency_detail = OrganisationSummarySerializer(source="agency", read_only=True)
    # GAP-040: operator tags as a writable list of `PersonTag` values. ChoiceField
    # rejects unknown values with a clean 400; the model `save()` canonicalizes
    # order/dups, so no sort is needed here. A PATCH replaces the whole set.
    tags = serializers.ListField(
        child=serializers.ChoiceField(choices=PersonTag.choices),
        required=False,
    )
    # GAP-052: country is operator-editable via a picker (overturns the GAP-042
    # display-only interim). No explicit declaration — ModelSerializer
    # auto-generates a writable, `allow_null`, `required=False` PK field from the
    # nullable `country` model FK, resolving `properties.Country` through the
    # model meta at bind time (runtime, app-registry ready). That keeps `accounts`
    # off an import of `properties` (import-spine floor) without resolving the FK
    # eagerly at module-import time. `country_name` carries the derived label.
    country_name = serializers.SerializerMethodField()
    # GAP-042: derived booking summary for the "Repeat" badge. Reads the
    # `booking_count` annotation applied by ContactViewSet when present (one
    # GROUP BY, no N+1); falls back to a count query for callers that render the
    # serializer off an un-annotated instance (merge/anonymize responses).
    booking_count = serializers.SerializerMethodField()
    is_repeat_customer = serializers.SerializerMethodField()
    # GAP-052: every capacity this person holds, surfaced as type badges on the
    # detail (a person can be customer + owner + agent at once — show all hats).
    # Derived, never stored; distinct from `tags` (the client-only flag set).
    contact_types = serializers.SerializerMethodField()

    class Meta:
        model = Person
        fields = [
            "id",
            "title",
            "first_name",
            "last_name",
            "agency",
            "agency_detail",
            "website_url",
            "preferred_method",
            "address_line_1",
            "address_line_2",
            "town",
            "post_code",
            "country",
            "country_name",
            "notes",
            "status",
            "kind",
            "tags",
            "booking_count",
            "is_repeat_customer",
            "contact_types",
            "anonymized_at",
            "user",
            "emails",
            "phones",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "anonymized_at",
            "user",
            "created_at",
            "updated_at",
        ]

    def get_country_name(self, obj: Person) -> str | None:
        country = obj.country
        return country.name if country is not None else None

    def get_booking_count(self, obj: Person) -> int:
        count = getattr(obj, "booking_count", None)
        if count is None:
            count = obj.bookings_as_customer.count()
        return count

    def get_is_repeat_customer(self, obj: Person) -> bool:
        # GAP-042 (confirmed): a returning client is one with >= 1 booking,
        # property-agnostic. Distinct from the owner API's property-scoped flag.
        return self.get_booking_count(obj) >= 1

    def get_contact_types(self, obj: Person) -> list[str]:
        # GAP-052: union of every capacity, sorted for a stable response. Values
        # come from `ContactType`; the set dedups any overlap.
        # - CUSTOMER: classified as one, or has booked.
        # - AGENT: belongs to an agency (GAP-046) AND/OR holds an `agent`
        #   property role — both collapse to the single AGENT badge, which is why
        #   ContactType.AGENT shares ContactRole.AGENT's value. A pure
        #   deal-channel agent (used as `.agent` on a deal, no agency, no
        #   agent-role) is not surfaced here — accounts-only derivation, full
        #   fidelity deferred; still in Clients.
        # - property roles (owner/manager/…): from the `active_roles` annotation
        #   (ACTIVE assignments only, raw ContactRole values — every one is a
        #   valid ContactType member), coalesced to [] for un-annotated callers.
        types: set[str] = set()
        if obj.kind == PersonKind.CUSTOMER.value or self.get_booking_count(obj) > 0:
            types.add(ContactType.CUSTOMER.value)
        if obj.agency_id is not None:
            types.add(ContactType.AGENT.value)
        types.update(getattr(obj, "active_roles", None) or [])
        return sorted(types)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Enforce contactability: an ACTIVE contact must be reachable by at
        least one channel (email or phone).

        Email/phone live in the `PersonEmail`/`PersonPhone` child tables, so this
        cannot be a DB CHECK (unlike `reservations.Guest`); this app-level gate
        is the floor. Wording mirrors `GuestSerializer.validate` — the two
        converge when Guest folds into Person. The *actionable-preference*
        invariant (`preferred_method=EMAIL ⇒ has email`) is deliberately
        deferred (see plan): `preferred_method` defaults to EMAIL, so enforcing
        it now would silently make an email mandatory for every active contact.
        """
        # GAP-029: a contact must carry at least a name OR an agency — mirrors the
        # FE `contactWriteInputSchema` refine. Read the effective (attrs over
        # instance) value of all three so a PATCH that clears the names but leaves the agency
        # untouched (agency absent from the payload) still passes. Keyed on
        # `first_name` so `applyApiErrorToForm` renders it inline under the name
        # field, matching the FE refine's `path: ["first_name"]`.
        first_name = attrs.get("first_name", getattr(self.instance, "first_name", ""))
        last_name = attrs.get("last_name", getattr(self.instance, "last_name", ""))
        agency = attrs.get("agency", getattr(self.instance, "agency", None))
        if not (first_name or last_name or agency):
            raise serializers.ValidationError(
                {"first_name": "A contact must have a name or an agency."}
            )

        emails = attrs.get("emails", [])
        phones = attrs.get("phones", [])

        # Reject >1 primary per channel up front so a bad inline payload returns
        # a clean 400 instead of tripping the partial-unique constraint as a 500.
        if sum(1 for e in emails if e.get("is_primary")) > 1:
            raise serializers.ValidationError(
                {"emails": "At most one email can be marked primary."}
            )
        if sum(1 for p in phones if p.get("is_primary")) > 1:
            raise serializers.ValidationError(
                {"phones": "At most one phone can be marked primary."}
            )

        new_status = attrs.get(
            "status",
            self.instance.status if self.instance is not None else PersonStatus.ACTIVE.value,
        )
        if new_status != PersonStatus.ACTIVE.value:
            return attrs

        message = "An active contact must be reachable by at least one channel (email or phone)."
        if self.instance is None:
            # Create: an active contact must arrive with a channel inline.
            if not emails and not phones:
                raise serializers.ValidationError(message)
        else:
            # Update: only guard the ARCHIVED/ANONYMIZED → ACTIVE *transition*.
            # Editing a legacy channel-less active contact in place stays
            # allowed (the deliberate divergence from Guest's validator).
            becoming_active = (
                "status" in attrs and self.instance.status != PersonStatus.ACTIVE.value
            )
            if becoming_active:
                reachable = (
                    bool(emails)
                    or bool(phones)
                    or self.instance.emails.exists()
                    or self.instance.phones.exists()
                )
                if not reachable:
                    raise serializers.ValidationError(message)
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Person:
        emails = validated_data.pop("emails", [])
        phones = validated_data.pop("phones", [])
        with transaction.atomic():
            person = Person.objects.create(**validated_data)
            for email in emails:
                PersonEmail.objects.create(contact=person, **email)
            for phone in phones:
                PersonPhone.objects.create(contact=person, **phone)
        return person

    def update(self, instance: Person, validated_data: dict[str, Any]) -> Person:
        # Channels are managed via the nested /emails and /phones endpoints;
        # ignore any inline lists on update so the edit flow stays unchanged.
        validated_data.pop("emails", None)
        validated_data.pop("phones", None)
        # GAP-045 D2: `kind` is create-only — a PATCH must not reclassify a
        # customer/contact (and on a mirror would be silently reverted by the
        # next Guest sync). Settable on POST, ignored on PATCH.
        validated_data.pop("kind", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
