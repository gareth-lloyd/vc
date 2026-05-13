from __future__ import annotations

from django.apps import AppConfig


class ReservationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reservations"

    def ready(self) -> None:
        from core.audit import track
        from reservations import signals  # noqa: F401
        from reservations.models import Booking, Guest

        # Guest PII: track verbatim so anonymisation runs are auditable.
        # No `sensitive=` fields — staff need to see what was redacted
        # to support the GDPR data-export trail.
        track(
            Guest,
            fields=[
                "first_name",
                "last_name",
                "email",
                "phone",
                "address_line_1",
                "address_line_2",
                "town",
                "post_code",
                "marketing_consent",
                "status",
                "anonymized_at",
            ],
        )
        # Booking state machine + money fields. The chatty `pricing_snapshot`
        # JSON is skipped; the dollar columns capture the deltas that matter
        # for an audit trail.
        track(
            Booking,
            fields=[
                "status",
                "date_from",
                "date_to",
                "adults",
                "children",
                "rental_price",
                "discount",
                "adjustment",
                "balance_due",
                "balance_due_at",
                "agent_id",
                "assigned_to_id",
                "payment_method",
                "cancel_reason",
                "cancelled_at",
                "is_archived",
                "archived_at",
            ],
        )
