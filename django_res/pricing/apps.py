from __future__ import annotations

from django.apps import AppConfig


class PricingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pricing"

    def ready(self) -> None:
        from core.audit import track
        from pricing import signals  # noqa: F401
        from pricing.models import (
            Discount,
            Extra,
            FxRate,
            RatePeriod,
            RatePlan,
            RateRule,
        )

        # Rate-card editing is operator-facing: every price-bearing change
        # needs an AuditLog trail. Field lists stay tight — lifecycle, money
        # and date-range columns; no timestamps or free-text notes.
        track(
            RatePlan,
            fields=[
                "name",
                "currency_id",
                "price_basis",
                "fallback_nightly",
                "effective_from",
                "effective_to",
                "is_active",
            ],
        )
        track(
            RatePeriod,
            fields=[
                "name",
                "date_from",
                "date_to",
                "min_nights",
                "max_nights",
                "is_active",
            ],
        )
        track(
            RateRule,
            fields=[
                # GAP-056: dates live on RatePeriod (tracked above). A band is a
                # partyxprice row; its date-range edits are audited on the period.
                "min_party",
                "max_party",
                "nightly",
                "weekly",
                "is_poa",
                "is_locked",
                "is_approved",
            ],
        )
        track(
            Discount,
            fields=[
                "name",
                "code",
                "rule_kind",
                "kind",
                "amount",
                "min_nights",
                "threshold_days",
                "valid_from",
                "valid_to",
                "max_uses",
                "is_active",
            ],
        )
        track(
            Extra,
            fields=[
                "name",
                "kind",
                "calc",
                "amount",
                "currency_id",
                "is_mandatory",
                "applies_from",
                "applies_to",
                "is_active",
            ],
        )
        track(
            FxRate,
            fields=[
                "base_id",
                "quote_id",
                "rate",
                "as_of",
            ],
        )
