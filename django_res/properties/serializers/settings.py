"""Serializers for `PropertySettings` and `GroupSettings`."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from properties.enums import PriceBasis
from properties.models import GroupSettings, PropertySettings


class PropertySettingsSerializer(serializers.ModelSerializer[PropertySettings]):
    class Meta:
        model = PropertySettings
        fields = [
            "property",
            "availability_default",
            "bookings_require_pre_approval",
            "requires_enquiry_first",
            "currency",
            "check_in_time",
            "check_out_time",
            "changeover_day",
            "min_nights_rental",
            "min_nights_rental_note",
            "prices_entered_as",
            "calendar_url",
        ]
        read_only_fields = ["property"]

    def to_representation(self, instance: PropertySettings) -> dict[str, Any]:
        data = super().to_representation(instance)
        # `timezone` physically lives on `PropertyLocation` (a geographic fact
        # of the place, never a configurable setting). It is surfaced here
        # read-only for context beside the check-in/out times; the location
        # endpoint (`/properties/{id}/location`) is the sole writer.
        try:
            data["timezone"] = instance.property.location.timezone
        except ObjectDoesNotExist:
            data["timezone"] = None
        # `currency_code` (GAP-026): the property's currency as a string code,
        # so money inputs can label which currency they commit to without the
        # client re-deriving the FK id. The raw `currency` FK stays writable;
        # this is its read-only display projection. `None` when the property
        # has no currency set.
        currency = instance.currency
        data["currency_code"] = currency.code if currency is not None else None
        # GAP-035 rate-entry derivation context (read-only). The rate-band form
        # derives the net/gross counterpart on display from three inputs the
        # settings endpoint surfaces beside `currency_code`, so the form reads
        # one already-loaded endpoint rather than re-fetching the finance
        # config:
        #   - `prices_entered_as_effective` — the property's *default* basis
        #     (GROSS when unset), used to pre-fill a new season's `price_basis`;
        #   - `commission` / `tax` — `PropertyFinance.effective_*()`, the same
        #     figures the engine prices with.
        data["prices_entered_as_effective"] = instance.prices_entered_as or PriceBasis.GROSS.value
        data["commission"], data["tax"] = self._rate_entry_finance(instance)
        return data

    @staticmethod
    def _rate_entry_finance(
        instance: PropertySettings,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Commission + tax policy for the net↔gross derivation.

        Defers to the canonical `PropertyFinance.effective_commission()` /
        `effective_tax_policy()` resolvers (the same figures the engine prices
        with), narrowed to the two fields the rate-band form needs. The
        resolvers' `self.property` back-leg rides the `finance` chain the view
        prefetches, so the query-count pin holds. `None` when the property has
        no `PropertyFinance` row (only rows created outside
        `snapshot_defaults`; the client treats null as "not configured").
        """

        def money(value: Any) -> str | None:
            return str(value) if value is not None else None

        try:
            finance = instance.property.finance
        except ObjectDoesNotExist:
            return None, None

        commission_src = finance.effective_commission()
        tax_src = finance.effective_tax_policy()
        commission = {
            "calculation_type": commission_src["calculation_type"],
            "amount": money(commission_src["amount"]),
        }
        tax = {
            "percentage": money(tax_src["percentage"]),
            "is_exempt": tax_src["is_exempt"],
        }
        return commission, tax


class GroupSettingsSerializer(serializers.ModelSerializer[GroupSettings]):
    class Meta:
        model = GroupSettings
        fields = [
            "group",
            "availability_default",
            "bookings_require_pre_approval",
            "requires_enquiry_first",
            "currency",
            "check_in_time",
            "check_out_time",
            "changeover_day",
            "min_nights_rental",
            "min_nights_rental_note",
            "prices_entered_as",
        ]
        read_only_fields = ["group"]
