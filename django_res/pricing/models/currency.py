"""Currency lookup table and append-only FX rates."""

from __future__ import annotations

from django.db import models

from core.models.base import TimestampedModel


class Currency(TimestampedModel):
    """ISO 4217 currency lookup. Staff-curated; `is_active` gates usage."""

    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=64)
    symbol = models.CharField(max_length=8, blank=True)
    decimal_places = models.PositiveSmallIntegerField(default=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "currencies"

    def __str__(self) -> str:
        return self.code


class FxRate(TimestampedModel):
    """Append-only daily FX rates. Most recent rate ≤ `as_of` wins."""

    base = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="fx_rates_as_base",
    )
    quote = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="fx_rates_as_quote",
    )
    rate = models.DecimalField(max_digits=18, decimal_places=8)
    as_of = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["base", "quote", "as_of"],
                name="fxrate_unique_base_quote_as_of",
            ),
        ]
        indexes = [
            models.Index(fields=["base", "quote", "-as_of"]),
        ]

    def __str__(self) -> str:
        return f"{self.base_id}->{self.quote_id} @ {self.as_of}: {self.rate}"
