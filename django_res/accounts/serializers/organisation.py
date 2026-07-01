"""Organisation serializers (GAP-046)."""

from __future__ import annotations

from rest_framework import serializers

from accounts.models import Organisation


class OrganisationMergeSerializer(serializers.Serializer[None]):
    """Body of `POST /organisations/{id}:merge` — the surviving org's id."""

    target_organisation_id = serializers.IntegerField()


class OrganisationSerializer(serializers.ModelSerializer[Organisation]):
    """Full Organisation representation for the `/organisations` CRUD API.

    `country` is deliberately not exposed (no org-side picker need yet). Note
    `accounts` is the bottom of the import spine and can't import
    `properties.Country` directly — but a writable FK is still reachable without
    the import: `ContactSerializer` lets `ModelSerializer` auto-generate its
    editable `country` field from the model meta (GAP-052). Add the same here if
    an org country picker is ever wanted. `legacy_id` / `dedup_key` are internal
    migration/dedup keys, never client-facing.
    """

    class Meta:
        model = Organisation
        fields = [
            "id",
            "name",
            "org_type",
            "email",
            "phone",
            "address_line_1",
            "address_line_2",
            "town",
            "post_code",
            "website_url",
            "notes",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


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
