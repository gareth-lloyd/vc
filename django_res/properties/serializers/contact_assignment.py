"""Serializer for `PropertyContactAssignment`."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from accounts.enums import ContactRole
from accounts.serializers import OrganisationSummarySerializer
from properties.models import PropertyContactAssignment


class PropertyContactAssignmentSerializer(serializers.ModelSerializer[PropertyContactAssignment]):
    # Lean nested org for display on an org-assignee row (null for a Person
    # row). Mirrors `ContactSerializer.agency_detail` so the FE renders the org
    # chip without a second fetch; reads the `select_related("organisation")`
    # cache.
    organisation_detail = OrganisationSummarySerializer(source="organisation", read_only=True)

    class Meta:
        model = PropertyContactAssignment
        fields = [
            "id",
            "property",
            "contact",
            "organisation",
            "organisation_detail",
            "role",
            "start_date",
            "end_date",
            "is_primary",
        ]
        read_only_fields = ["id", "property"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Enforce the contact-XOR-organisation rule (mirrors the DB check) and
        restrict the organisation assignee to the `management_company` role.

        Validating here as well as at the DB layer gives a 400 with a field
        message instead of a 500 from the IntegrityError.
        """
        # On PATCH, fall back to the instance's current values for fields the
        # payload omits, so a partial update doesn't read a half-empty picture.
        contact = attrs.get("contact", getattr(self.instance, "contact", None))
        organisation = attrs.get("organisation", getattr(self.instance, "organisation", None))
        role = attrs.get("role", getattr(self.instance, "role", None))

        if (contact is not None) == (organisation is not None):
            raise serializers.ValidationError("Provide exactly one of contact or organisation.")
        if organisation is not None and role != ContactRole.MANAGEMENT_COMPANY:
            raise serializers.ValidationError(
                {
                    "organisation": "An organisation assignee is only valid for the "
                    "management_company role."
                }
            )
        return attrs
