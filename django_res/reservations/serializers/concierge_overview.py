"""Serializers for the cross-booking concierge coverage matrix.

`ConciergeOverviewSerializer` flattens a Booking into one matrix row: the
fixed service columns (every `ConciergeService`, defaulting absent cells to
``not_started``), a progress percentage, the derived concierge tier, and the
at-a-glance booking facts the matrix shows down its left edge.
"""

from __future__ import annotations

from datetime import date

from rest_framework import serializers

from reservations.enums import ConciergeService, ConciergeTier, ServiceStatus
from reservations.models import Booking, BookingServiceCoverage


class ConciergeOverviewSerializer(serializers.ModelSerializer[Booking]):
    """One row of the concierge matrix, keyed on a Booking.

    Requires ``context["today"]`` for the arrival countdown and benefits from
    `prefetch_related("service_coverage", "concierge_items")` +
    `select_related("property__region", "guest", "assigned_to")` on the
    queryset — every derived field reads only prefetched data.
    """

    guest_name = serializers.SerializerMethodField()
    property_name = serializers.SerializerMethodField()
    region = serializers.SerializerMethodField()
    arrival_in_days = serializers.SerializerMethodField()
    services = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    manager = serializers.SerializerMethodField()
    tier = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "reference",
            "status",
            "guest_name",
            "property_name",
            "region",
            "date_from",
            "arrival_in_days",
            "services",
            "progress",
            "manager",
            "tier",
        ]

    def get_guest_name(self, obj: Booking) -> str | None:
        guest = obj.guest
        if guest is None:
            return None
        return f"{guest.first_name} {guest.last_name}".strip() or None

    def get_property_name(self, obj: Booking) -> str | None:
        prop = obj.property
        if prop is None:
            return None
        return (prop.display_name or prop.name) or None

    def get_region(self, obj: Booking) -> str | None:
        prop = obj.property
        if prop is None or prop.region is None:
            return None
        return prop.region.name or None

    def get_arrival_in_days(self, obj: Booking) -> int:
        today: date = self.context["today"]
        return (obj.date_from - today).days

    def get_services(self, obj: Booking) -> dict[str, str]:
        """Every service column, absent cells defaulting to ``not_started``."""
        existing = {cov.service: cov.status for cov in obj.service_coverage.all()}
        return {
            service.value: existing.get(service.value, ServiceStatus.NOT_STARTED.value)
            for service in ConciergeService
        }

    def get_progress(self, obj: Booking) -> int:
        """Percent of the *touched* (row-bearing) services marked ``done``.

        `not_required` cells drop out of the denominator; a booking nobody has
        started reads 0.
        """
        rows = [
            cov
            for cov in obj.service_coverage.all()
            if cov.status != ServiceStatus.NOT_REQUIRED.value
        ]
        if not rows:
            return 0
        done = sum(1 for cov in rows if cov.status == ServiceStatus.DONE.value)
        return round(done / len(rows) * 100)

    def get_manager(self, obj: Booking) -> str | None:
        manager = obj.assigned_to
        if manager is None:
            return None
        full_name = f"{manager.first_name} {manager.last_name}".strip()
        return full_name or manager.email or None

    def get_tier(self, obj: Booking) -> str | None:
        """Derive a booking tier from its concierge lines (no tier column).

        Signature outranks Quintessential; absent any line, the booking has no
        tier badge.
        """
        tiers = {item.tier for item in obj.concierge_items.all()}
        if ConciergeTier.SIGNATURE.value in tiers:
            return ConciergeTier.SIGNATURE.value
        if ConciergeTier.QUINTESSENTIAL.value in tiers:
            return ConciergeTier.QUINTESSENTIAL.value
        return None


class BookingServiceCoverageSerializer(serializers.ModelSerializer[BookingServiceCoverage]):
    """Response shape for a single coverage cell after a set-status write."""

    class Meta:
        model = BookingServiceCoverage
        fields = ["id", "booking", "service", "status", "notes"]
        read_only_fields = fields
