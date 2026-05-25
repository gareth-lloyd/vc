from __future__ import annotations

from rest_framework import serializers

from comms.models import EmailLog


class EmailLogSerializer(serializers.ModelSerializer):
    """Read serializer for `/bookings/{id}/emails`.

    Excludes the rendered body — the list surface only needs subject,
    recipients, status, and timestamps. Bodies are large and rarely
    inspected from the SPA; surface them on a per-row detail endpoint
    later if needed.
    """

    sender_user_id = serializers.IntegerField(read_only=True)
    smtp_profile_id = serializers.IntegerField(read_only=True)
    subject = serializers.CharField(source="rendered_subject", read_only=True)

    class Meta:
        model = EmailLog
        fields = (
            "id",
            "template_key",
            "template_version",
            "to",
            "cc",
            "bcc",
            "from_email",
            "subject",
            "status",
            "queued_at",
            "sent_at",
            "failure_reason",
            "sender_user_id",
            "smtp_profile_id",
            "provider_reference",
            "correlation",
        )
        read_only_fields = fields
