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
    PropertySeasonListCreateView,
    RateCardDetailView,
    RateCardDiscountListCreateView,
    RateCardDuplicateView,
    RateCardRuleListCreateView,
    RateRuleDetailView,
    SeasonDetailView,
    SeasonDuplicateView,
    SeasonRateCardListCreateView,
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
    # Seasons / rate cards / rate rules
    path(
        "properties/<int:property_id>/seasons",
        PropertySeasonListCreateView.as_view(),
        name="property-season-list",
    ),
    path(
        "seasons/<int:pk>",
        SeasonDetailView.as_view(),
        name="season-detail",
    ),
    path(
        "seasons/<int:pk>:duplicate",
        SeasonDuplicateView.as_view(),
        name="season-duplicate",
    ),
    path(
        "seasons/<int:season_id>/rate-cards",
        SeasonRateCardListCreateView.as_view(),
        name="season-rate-card-list",
    ),
    path(
        "rate-cards/<int:pk>",
        RateCardDetailView.as_view(),
        name="rate-card-detail",
    ),
    path(
        "rate-cards/<int:pk>:duplicate",
        RateCardDuplicateView.as_view(),
        name="rate-card-duplicate",
    ),
    path(
        "rate-cards/<int:rate_card_id>/rules",
        RateCardRuleListCreateView.as_view(),
        name="rate-card-rule-list",
    ),
    path(
        "rules/<int:pk>",
        RateRuleDetailView.as_view(),
        name="rate-rule-detail",
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
        "rate-cards/<int:rate_card_id>/discounts",
        RateCardDiscountListCreateView.as_view(),
        name="rate-card-discount-list",
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
