"""Person / PersonEmail / PersonPhone serializers."""

from __future__ import annotations

from rest_framework import serializers

from accounts.models import Person, PersonEmail, PersonPhone


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
    """Full Person representation with inline emails/phones."""

    emails = ContactEmailSerializer(many=True, read_only=True)
    phones = ContactPhoneSerializer(many=True, read_only=True)
    # `user` is a OneToOne to the swappable AUTH_USER_MODEL, which DRF can't
    # auto-discover; surface it read-only for now (link operations land in a
    # dedicated endpoint when the portal flow is wired).
    user: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(
        read_only=True, allow_null=True
    )

    class Meta:
        model = Person
        fields = [
            "id",
            "title",
            "first_name",
            "last_name",
            "company",
            "website_url",
            "preferred_method",
            "address_line_1",
            "address_line_2",
            "notes",
            "status",
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
            "emails",
            "phones",
            "created_at",
            "updated_at",
        ]
