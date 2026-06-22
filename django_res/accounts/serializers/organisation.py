"""Organisation serializers (GAP-046)."""

from __future__ import annotations

from rest_framework import serializers

from accounts.models import Organisation


class OrganisationSummarySerializer(serializers.ModelSerializer[Organisation]):
    """Lean read-only nested view of an Organisation.

    Used wherever an org is shown inline as a related object (e.g. a contact's
    `agency_detail`) — enough to render the chip without the full record. The
    full CRUD serializer lands with the Organisation API (Unit 3).

    The nested-object shape is a deliberate choice (not the flat
    `CharField(source="x.y")` pattern used for scalar related reads elsewhere):
    an agency chip carries several fields the FE renders as a unit, and it pairs
    naturally with the writable `agency` pk on `ContactSerializer`. Keep it
    nested.
    """

    class Meta:
        model = Organisation
        fields = ["id", "name", "org_type", "status"]
        read_only_fields = fields
