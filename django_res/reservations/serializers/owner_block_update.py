"""Staff-facing serializer for the owner-block awareness feed.

One row per change event (created / cancelled). The `contested` block is sourced
from the *block*, not the event — so every update row for a contested block
shows the dispute. `is_seen` is annotated per calling staff user by the viewset.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from reservations.models import OwnerBlockUpdate


class OwnerBlockUpdateSerializer(serializers.ModelSerializer[OwnerBlockUpdate]):
    block = serializers.SerializerMethodField()
    contested = serializers.SerializerMethodField()
    is_seen = serializers.BooleanField(read_only=True)

    class Meta:
        model = OwnerBlockUpdate
        fields = ["id", "kind", "actor", "created_at", "block", "contested", "is_seen"]
        read_only_fields = fields

    def get_block(self, obj: OwnerBlockUpdate) -> dict[str, Any]:
        block = obj.block
        prop = block.property if block.property_id else None
        return {
            "id": block.id,
            "property": block.property_id,
            "property_name": ((prop.display_name or prop.name) or None) if prop else None,
            "date_from": block.date_from,
            "date_to": block.date_to,
            "kind": block.kind,
            "notes": block.notes,
            "status": block.status,
            "created_by": block.created_by_id,
        }

    def get_contested(self, obj: OwnerBlockUpdate) -> dict[str, Any] | None:
        block = obj.block
        if block.contested_at is None:
            return None
        return {
            "at": block.contested_at,
            "by": block.contested_by_id,
            "reason": block.contest_reason,
        }


class OwnerBlockContestSerializer(serializers.Serializer):
    """Validate the staff contest payload — a non-empty reason is required."""

    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)
