"""Serializer for the Clients (renter) directory list (GAP-047)."""

from __future__ import annotations

from rest_framework import serializers

from accounts.models import Person


class ClientListSerializer(serializers.ModelSerializer[Person]):
    """Read-only row for `GET /clients`.

    A renter `Person` (`kind=CUSTOMER`) flattened for the directory: the
    booking-channel `is_agent` flag (annotated on the queryset) plus the primary
    email/phone read from the `emails`/`phones` prefetch cache via the Person
    methods (which fail closed for an ANONYMIZED person).
    """

    primary_email = serializers.SerializerMethodField()
    primary_phone = serializers.SerializerMethodField()
    is_agent = serializers.BooleanField(read_only=True)
    quoted_region_slugs = serializers.SerializerMethodField()
    booked_region_slugs = serializers.SerializerMethodField()

    class Meta:
        model = Person
        fields = [
            "id",
            "title",
            "first_name",
            "last_name",
            "primary_email",
            "primary_phone",
            "is_agent",
            "quoted_region_slugs",
            "booked_region_slugs",
            "status",
        ]

    def get_primary_email(self, obj: Person) -> str | None:
        return obj.primary_email()

    def get_primary_phone(self, obj: Person) -> str | None:
        return obj.primary_phone()

    def get_quoted_region_slugs(self, obj: Person) -> list[str]:
        # The ArrayAgg subquery returns NULL for a client with no quoted deals.
        return getattr(obj, "quoted_region_slugs", None) or []

    def get_booked_region_slugs(self, obj: Person) -> list[str]:
        return getattr(obj, "booked_region_slugs", None) or []
