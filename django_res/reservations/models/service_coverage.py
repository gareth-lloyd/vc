"""BookingServiceCoverage — one row per (booking, service) coverage cell.

Backs the concierge service-status matrix (mock-up 01): unlike the free-form
`BookingConciergeItem` cost lines, this tracks *where each fixed service is up
to* for a booking — exactly one status per service. Rows are created lazily
when an operator first sets a status; an absent service reads as
``not_started``.
"""

from __future__ import annotations

from django.db import models

from core.models.base import AuditedModel
from reservations.enums import ConciergeService, ServiceStatus


class BookingServiceCoverage(AuditedModel):
    booking = models.ForeignKey(
        "reservations.Booking",
        on_delete=models.CASCADE,
        related_name="service_coverage",
    )
    service = models.CharField(max_length=16, choices=ConciergeService.choices)
    status = models.CharField(
        max_length=24,
        choices=ServiceStatus.choices,
        default=ServiceStatus.NOT_STARTED,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["service"]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "service"],
                name="uniq_booking_service_coverage",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.booking_id}/{self.service}={self.status}"
