"""Serializer for the Clients (renter) directory list (GAP-047)."""

from __future__ import annotations

from rest_framework import serializers

from accounts.models import Person


class ClientListSerializer(serializers.ModelSerializer[Person]):
    """Read-only row for `GET /clients`.

    A directory `Person` flattened for the list. Membership is customers PLUS
    agent-capacity people (GAP-053), so `is_agent` is the agent-capacity flag
    (belongs to an agency, or deals through an agent) — not `kind`-bound. Primary
    email/phone read from the `emails`/`phones` prefetch cache via the Person
    methods (which fail closed for an ANONYMIZED person). `is_repeat_customer`
    and `tags` back the VIP/Trade/Repeat chips.
    """

    primary_email = serializers.SerializerMethodField()
    primary_phone = serializers.SerializerMethodField()
    is_agent = serializers.BooleanField(read_only=True)
    # GAP-053: chip active-state. `is_repeat_customer` is the annotated >=1-booking
    # flag; `tags` is the stored client flag set (VIP/Trade chips read off it).
    is_repeat_customer = serializers.BooleanField(read_only=True)
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
            "is_repeat_customer",
            "tags",
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
