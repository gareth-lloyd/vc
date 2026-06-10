from __future__ import annotations

from django.apps import AppConfig


class ReservationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reservations"

    def ready(self) -> None:
        from core.audit import track
        from reservations import signals  # noqa: F401
        from reservations.models import (
            Booking,
            BookingChargeItem,
            BookingGuest,
            BookingServiceCoverage,
            Guest,
            OwnerBlock,
            QuotationLine,
        )

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
                "contact_method",
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
        # BookingChargeItem: staff-entered money on the guest total. Every
        # add/edit/delete moves what the guest owes, so the full row is the
        # audit trail a billing dispute needs.
        track(
            BookingChargeItem,
            fields=[
                "booking_id",
                "label",
                "amount",
                "currency_id",
                "notes",
            ],
        )
        # BookingGuest: who is on a booking, in what role. PII via the
        # guest FK + an optional `email_override`; LEAD/PAYER changes
        # affect comms routing and downstream invoicing, so the change
        # trail is load-bearing for an audit review.
        track(
            BookingGuest,
            fields=[
                "booking_id",
                "guest_id",
                "role",
                "email_override",
            ],
        )
        # QuotationLine money + decision fields. Like Booking, the chatty
        # `pricing_snapshot` JSON is skipped; the dollar and override columns
        # capture what an auditor needs to reconstruct a quoted price —
        # especially a manual override and its stated reason.
        track(
            QuotationLine,
            fields=[
                "total",
                "discount",
                "is_manual",
                "is_selected",
                "price_override_reason",
            ],
        )
        # BookingServiceCoverage: one progress status per (booking, service)
        # behind the concierge matrix. The status transition is the only
        # actionable column — who moved a service to `done`/`waiting` and when
        # is exactly the trail a concierge review needs.
        track(
            BookingServiceCoverage,
            fields=[
                "booking_id",
                "service",
                "status",
            ],
        )
        # OwnerBlock: the owner-initiated availability-block lifecycle.
        # Who created, cancelled, or contested a block and the hold it produced
        # is the trail an operator review of owner actions needs.
        track(
            OwnerBlock,
            fields=[
                "property_id",
                "created_by_id",
                "date_from",
                "date_to",
                "kind",
                "status",
                "resulting_hold_id",
                "contested_at",
                "contested_by_id",
            ],
        )
