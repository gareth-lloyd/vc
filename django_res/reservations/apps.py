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
            BookingHold,
            BookingServiceCoverage,
            DamageClaim,
            DamageClaimPhoto,
            Enquiry,
            OwnerBlock,
            Quotation,
            QuotationLine,
        )

        # Booking state machine + money fields. The chatty `pricing_snapshot`
        # JSON is skipped; the dollar columns capture the deltas that matter
        # for an audit trail. `person_id` (GAP-045) captures the customer the
        # booking was BORN with; post-create LEAD reassignment mutates it only
        # via `_booking_guest_post_save`'s `queryset.update()` (no pre_save
        # signal — bypasses this trail by design), so the LEAD change history
        # lives on the audited `BookingGuest` row, not here.
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
                "person_id",
                "agent_id",
                "assigned_to_id",
                "payment_method",
                "cancel_reason",
                "cancelled_at",
                "is_archived",
                "archived_at",
            ],
        )
        # DamageClaim (BUG-008): money + lifecycle columns behind an SD capture.
        # `description` is unbounded operator free-text that may incidentally
        # carry guest PII, and DamageClaim has no `anonymize()`/`scrub_pii`
        # erasure path — so it's skipped rather than tracked plainly, mirroring
        # how Enquiry skips its free-text `inbound_message`. The `itemized_lines`
        # JSON scaffold is a chatty blob, also skipped per the audit convention.
        # What remains is the money + lifecycle that an SD capture turns on.
        track(
            DamageClaim,
            fields=[
                "status",
                "amount",
                "currency_id",
                "booking_id",
                "accepted_by_guest_at",
            ],
        )
        # DamageClaimPhoto (wf8): evidence backing a money capture. The image
        # blob itself isn't a tracked field; the trail records that a photo was
        # attached/removed (the FK + caption) and by whom, mirroring how
        # PropertyImage is audited. Create/delete ride `.save()`/`.delete()`.
        track(
            DamageClaimPhoto,
            fields=[
                "damage_claim_id",
                "caption",
            ],
        )
        # Enquiry: the lead-capture surface carrying denormalised PII before a
        # Guest is captured (first/last name, email, phone), plus the status
        # lifecycle and the routing/assignment columns. Unlike `Guest` — which
        # has an `anonymize()` flow that runs `scrub_pii` over its trail — the
        # Enquiry has no erasure path, so its PII is registered `sensitive=` and
        # recorded as the `[REDACTED]` sentinel: cleartext never lands in the
        # AuditLog, so nothing needs scrubbing later. Skip the chatty
        # `inbound_message` free text and `auto_now` stamps.
        track(
            Enquiry,
            fields=[
                "status",
                "lost_reason",
                "lead_status",
                "first_name",
                "last_name",
                "email",
                "phone",
                "contact_method",
                "person_id",
                "property_id",
                "agent_id",
                "assigned_to_id",
                "request_type",
            ],
            sensitive=["first_name", "last_name", "email", "phone"],
        )
        # Quotation header: the issue/accept/expire/cancel state machine plus
        # the expiry and cancellation columns. Lines carry the money and are
        # tracked via `QuotationLine`; the header has no currency (per-line,
        # GAP-014). No PII — guest/agent identity lives behind FKs.
        track(
            Quotation,
            fields=[
                "status",
                "expires_at",
                "cancel_reason",
                "is_unbranded",
                "agent_id",
                "person_id",
                "enquiry_id",
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
                "commissionable",
                "notes",
            ],
        )
        # BookingGuest: who is on a booking, in what role. PII via the
        # person FK + an optional `email_override`; LEAD/PAYER changes
        # affect comms routing and downstream invoicing, so the change
        # trail is load-bearing for an audit review.
        track(
            BookingGuest,
            fields=[
                "booking_id",
                "person_id",
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
        # BookingHold: the availability-blocking lifecycle (place → release /
        # expire). The model has no `status` column — lifecycle is carried by
        # `released_at` (release) and `expires_at` (reap), so those are the
        # transition fields an inventory-dispute reconstruction needs, alongside
        # the date window and the hold's source FKs. No PII. NB: the bulk
        # release/expire paths (`HoldService.release_for_*`, `expire_holds`,
        # `tasks`) use `queryset.update()` and so bypass the pre_save trail by
        # design (CLAUDE.md "bulk writes bypass it silently"); the per-instance
        # `HoldService.place`/`move`/`release` paths are captured.
        track(
            BookingHold,
            fields=[
                "property_id",
                "quotation_id",
                "quotation_line_id",
                "booking_id",
                "date_from",
                "date_to",
                "expires_at",
                "released_at",
                "reason",
            ],
        )
