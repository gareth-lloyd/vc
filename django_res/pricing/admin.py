"""Pricing admin registrations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin, messages

from core.exceptions import NoRateAvailable
from pricing.models import (
    Currency,
    Discount,
    Extra,
    FxRate,
    RateCard,
    RatePlan,
    RateRule,
    VillaPricingSummary,
)
from pricing.services.carryover import RateCarryoverService

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "symbol", "decimal_places", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(FxRate)
class FxRateAdmin(admin.ModelAdmin):
    list_display = ("base", "quote", "rate", "as_of")
    list_filter = ("base", "quote")
    search_fields = ("base__code", "quote__code")
    date_hierarchy = "as_of"


@admin.register(RatePlan)
class RatePlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "property",
        "currency",
        "price_basis",
        "fallback_nightly",
        "effective_from",
        "is_active",
    )
    list_filter = ("price_basis", "is_active", "currency")
    search_fields = ("name",)
    actions = ("carry_forward_next_year",)

    @admin.action(description="Carry forward to next year (editable rows)")
    def carry_forward_next_year(self, request: HttpRequest, queryset: QuerySet[RatePlan]) -> None:
        """Materialise editable rows for each selected plan's following year.

        Idempotent: a plan whose next year already exists is left untouched. The
        anchor is resolved per (property, currency), so selecting any plan for a
        villa carries that villa's most recent year forward.
        """
        created = 0
        for plan in queryset:
            try:
                RateCarryoverService.materialise(
                    plan.property,
                    target_year=plan.effective_from.year + 1,
                    currency=plan.currency,
                )
                created += 1
            except NoRateAvailable as exc:
                self.message_user(request, str(exc), level=messages.WARNING)
        if created:
            self.message_user(
                request,
                f"Carried forward {created} plan(s) to the following year.",
                level=messages.SUCCESS,
            )


@admin.register(RateCard)
class RateCardAdmin(admin.ModelAdmin):
    list_display = ("name", "plan", "min_nights", "max_nights", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(RateRule)
class RateRuleAdmin(admin.ModelAdmin):
    list_display = (
        "card",
        "date_from",
        "date_to",
        "min_party",
        "max_party",
        "nightly",
        "weekly",
        "is_poa",
        "is_approved",
    )
    list_filter = ("is_poa", "is_approved", "is_locked")


@admin.register(Extra)
class ExtraAdmin(admin.ModelAdmin):
    list_display = ("name", "property", "kind", "calc", "amount", "currency", "is_mandatory")
    list_filter = ("kind", "calc", "is_mandatory", "is_active")
    search_fields = ("name",)


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ("name", "property", "card", "rule_kind", "kind", "amount", "is_active")
    list_filter = ("rule_kind", "kind", "is_active")
    search_fields = ("name", "code")


@admin.register(VillaPricingSummary)
class VillaPricingSummaryAdmin(admin.ModelAdmin):
    list_display = (
        "property",
        "currency",
        "min_nightly",
        "max_nightly",
        "min_weekly",
        "max_weekly",
        "rebuilt_at",
    )
    readonly_fields = (
        "property",
        "currency",
        "min_nightly",
        "max_nightly",
        "min_weekly",
        "max_weekly",
        "next_available_date",
        "min_party",
        "max_party",
        "rebuilt_at",
    )
