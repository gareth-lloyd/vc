from __future__ import annotations

from rest_framework import serializers

from core.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer[AuditLog]):
    entity_type = serializers.SerializerMethodField()
    actor_email = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "entity_type",
            "object_id",
            "actor",
            "actor_email",
            "field_diffs",
            "correlation_id",
            "created_at",
        ]
        read_only_fields = fields

    def get_entity_type(self, obj: AuditLog) -> str:
        ct = obj.content_type
        return f"{ct.app_label}.{ct.model}"

    def get_actor_email(self, obj: AuditLog) -> str | None:
        return obj.actor.email if obj.actor else None
