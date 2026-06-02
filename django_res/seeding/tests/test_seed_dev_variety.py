"""Variety contract: `seed_dev --scale small --profile mixed` populates every
gap surfaced in `seed_audit_before.md`.

This is the executable counterpart to the audit doc: if a stage stops
producing a model the gap-detection assertions below catch it.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from comms.models import EmailTemplate, SmtpProfile
from integrations.models.oauth_credential import OAuthCredential
from integrations.models.sync_issue import SyncIssue
from integrations.models.sync_record import SyncRecord
from integrations.models.sync_run import SyncRun
from payments.enums import RefundStatus
from payments.models.refund import Refund
from payments.models.webhook_delivery import WebhookDelivery
from pricing.models import Currency, FxRate
from properties.enums import ImageKind, PropertyStatus
from properties.models import (
    ChangeOverRule,
    Collection,
    CollectionMembership,
    Feature,
    FeatureCategory,
    NearbyPlaceType,
    Property,
    PropertyContactAssignment,
    PropertyImage,
    PropertyNearbyPlace,
    Room,
)
from properties.models.rooms import RoomBeds
from reservations.enums import BookingStatus
from reservations.models import (
    Booking,
    BookingNote,
    EnquiryNote,
    TermsVersion,
)
from reservations.models.concierge import BookingConciergeItem


@pytest.mark.django_db(transaction=True)
def test_seed_dev_mixed_closes_audit_gaps() -> None:
    """`seed_dev --scale small --profile mixed --seed 42` writes at least one
    row to every model the `seed_audit_before.md` baseline listed as a gap,
    plus the shape contracts on currencies / terms / refunds / bookings /
    properties."""

    # `--scale small` (5 properties / 8 bookings) is too thin to exercise the
    # mod-4 refund walk *and* leave a property free of overlap-blocking
    # bookings (the lifecycle stage skips properties with bookings in any
    # OVERLAP_BLOCKING state). Bump both knobs so variety contracts hold
    # without paying the full `--scale medium` cost.
    call_command(
        "seed_dev",
        "--scale",
        "small",
        "--properties",
        "20",
        "--bookings",
        "24",
        "--profile",
        "mixed",
        "--seed",
        "42",
        stdout=StringIO(),
    )

    # ---- Multi-currency: GBP/EUR/USD all present ----
    assert Currency.objects.filter(code__in=["GBP", "EUR", "USD"]).count() == 3, (
        "system_setup should seed GBP, EUR, USD"
    )
    assert FxRate.objects.exists(), "FX matrix should land at least one row"

    # ---- Comms: SMTP + templates ----
    assert SmtpProfile.objects.exists()
    assert EmailTemplate.objects.exists()

    # ---- TermsVersion history (current + ≥1 historical) ----
    assert TermsVersion.objects.count() >= 2

    # ---- Property graph extras ----
    assert Room.objects.exists()
    assert RoomBeds.objects.exists()
    assert Feature.objects.exists()
    assert FeatureCategory.objects.exists()
    assert PropertyImage.objects.exclude(kind=ImageKind.HERO).exists(), (
        "gallery stage should add non-HERO images"
    )
    assert NearbyPlaceType.objects.exists()
    assert PropertyNearbyPlace.objects.exists()
    assert Collection.objects.exists()
    assert CollectionMembership.objects.exists()
    assert PropertyContactAssignment.objects.exists()
    assert ChangeOverRule.objects.exists()

    # ---- Notes ----
    assert BookingNote.objects.exists()
    assert EnquiryNote.objects.exists()

    # ---- Integrations ----
    assert OAuthCredential.objects.exists()
    assert SyncRun.objects.exists()
    assert SyncRecord.objects.exists()
    assert SyncIssue.objects.exists()

    # ---- Payments side-channels ----
    assert WebhookDelivery.objects.exists()

    # ---- Concierge + refunds (previously zero on small profile) ----
    assert BookingConciergeItem.objects.exists()
    assert Refund.objects.exists()

    # ---- Refund status spread: at least two interesting outcomes ----
    # Small-profile pulls 1-3 refundable bookings; the mod-4 walk in the
    # refunds stage means 4 distinct statuses need ≥4 refunds, which
    # `--scale small` doesn't reliably produce. Match the existing contract
    # in `test_seed_dev_mixed_emits_refund_lifecycle` (≥2 of the 4 realistic
    # statuses) and let larger scales widen the spread.
    refund_statuses = set(Refund.objects.values_list("status", flat=True))
    realistic = {
        RefundStatus.REJECTED.value,
        RefundStatus.APPROVED.value,
        RefundStatus.FAILED.value,
        RefundStatus.SUCCEEDED.value,
    }
    assert len(refund_statuses & realistic) >= 2, (
        f"expected ≥2 of {realistic} in refund statuses, got {refund_statuses}"
    )

    # ---- Booking status spread: pre-approval path is exercised ----
    booking_statuses = set(Booking.objects.values_list("status", flat=True))
    assert BookingStatus.PENDING_OWNER_APPROVAL.value in booking_statuses

    # ---- Property status spread: at least one DRAFT or ARCHIVED ----
    property_statuses = set(Property.objects.values_list("status", flat=True))
    assert (
        PropertyStatus.DRAFT.value in property_statuses
        or PropertyStatus.ARCHIVED.value in property_statuses
    )
