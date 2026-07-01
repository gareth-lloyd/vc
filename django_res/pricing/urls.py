"""URL configuration for the pricing app."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, path
from rest_framework.routers import DefaultRouter

from pricing.views import (
    CurrencyFxRatesView,
    CurrencyViewSet,
    DiscountLookupCodeView,
    DiscountViewSet,
    ExtraDetailView,
    ExtraDuplicateView,
    PricingQuoteBulkView,
    PricingQuoteView,
    PropertyDiscountListCreateView,
    PropertyExtraListCreateView,
    PropertyRatePlanCarryForwardView,
    PropertyRatePlanListCreateView,
    RateBandDetailView,
    RatePeriodBandListCreateView,
    RatePeriodDetailView,
    RatePlanDetailView,
    RatePlanDuplicateView,
    RatePlanRatePeriodListCreateView,
)

router = DefaultRouter(trailing_slash=False)
router.register(r"currencies", CurrencyViewSet, basename="currency")
router.register(r"discounts", DiscountViewSet, basename="discount")


_pricing_paths: list[URLPattern] = [
    path(
        "currencies/<str:code>/rates",
        CurrencyFxRatesView.as_view(),
        name="currency-fx-rates",
    ),
    # Rate plans / rate periods / rate bands
    path(
        "properties/<int:property_id>/rate-plans",
        PropertyRatePlanListCreateView.as_view(),
        name="property-rate-plan-list",
    ),
    path(
        "properties/<int:property_id>/rate-plans:carry-forward",
        PropertyRatePlanCarryForwardView.as_view(),
        name="property-rate-plan-carry-forward",
    ),
    path(
        "rate-plans/<int:pk>",
        RatePlanDetailView.as_view(),
        name="rate-plan-detail",
    ),
    path(
        "rate-plans/<int:pk>:duplicate",
        RatePlanDuplicateView.as_view(),
        name="rate-plan-duplicate",
    ),
    path(
        "rate-plans/<int:plan_id>/rate-periods",
        RatePlanRatePeriodListCreateView.as_view(),
        name="rate-plan-rate-period-list",
    ),
    path(
        "periods/<int:pk>",
        RatePeriodDetailView.as_view(),
        name="rate-period-detail",
    ),
    path(
        "periods/<int:period_id>/bands",
        RatePeriodBandListCreateView.as_view(),
        name="rate-period-band-list",
    ),
    path(
        "bands/<int:pk>",
        RateBandDetailView.as_view(),
        name="rate-band-detail",
    ),
    # Extras
    path(
        "properties/<int:property_id>/extras",
        PropertyExtraListCreateView.as_view(),
        name="property-extra-list",
    ),
    path(
        "extras/<int:pk>",
        ExtraDetailView.as_view(),
        name="extra-detail",
    ),
    path(
        "extras/<int:pk>:duplicate",
        ExtraDuplicateView.as_view(),
        name="extra-duplicate",
    ),
    # Discounts
    path(
        "properties/<int:property_id>/discounts",
        PropertyDiscountListCreateView.as_view(),
        name="property-discount-list",
    ),
    path(
        "discounts:lookup-code",
        DiscountLookupCodeView.as_view(),
        name="discount-lookup-code",
    ),
    # Pricing helpers
    path(
        "pricing:quote",
        PricingQuoteView.as_view(),
        name="pricing-quote",
    ),
    path(
        "pricing:quote-bulk",
        PricingQuoteBulkView.as_view(),
        name="pricing-quote-bulk",
    ),
]

urlpatterns: list[URLPattern | URLResolver] = [
    *_pricing_paths,
    *router.urls,
]
