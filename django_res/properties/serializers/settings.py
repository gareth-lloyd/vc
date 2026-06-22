"""Serializers for `PropertySettings` and `GroupSettings`."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

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
        # of the place, never inherited from the group). It is surfaced here
        # read-only for context beside the check-in/out times; the location
        # endpoint (`/properties/{id}/location`) is the sole writer.
        try:
            data["timezone"] = instance.property.location.timezone
        except ObjectDoesNotExist:
            data["timezone"] = None
        # `currency_code` (GAP-026): the group-resolved *effective* currency as a
        # string code, so money inputs can label which currency they commit to
        # without the client re-deriving the FK id or the inheritance chain. The
        # raw `currency` FK stays writable; this is its read-only display
        # projection. `None` when neither property nor group sets a currency.
        data["currency_code"] = self._effective_currency_code(instance)
        # GAP-035 rate-entry derivation context (read-only). The rate-band form
        # derives the net/gross counterpart on display from three group-resolved
        # inputs; surfacing them here (beside `currency_code`) lets the form read
        # one already-loaded endpoint rather than re-fetching the finance config
        # and re-walking the inheritance chain client-side:
        #   - `prices_entered_as_effective` — the property's *default* basis,
        #     used to pre-fill a new season's `price_basis`;
        #   - `commission` / `tax` — `PropertyFinance.effective_*()` resolved
        #     property → group, the same figures the engine prices with.
        data["prices_entered_as_effective"] = self._effective_prices_entered_as(instance)
        data["commission"], data["tax"] = self._rate_entry_finance(instance)
        return data

    @staticmethod
    def _effective_currency_code(instance: PropertySettings) -> str | None:
        try:
            currency = instance.effective("currency")
        except ObjectDoesNotExist:
            # The group has no settings row, so the fallback leg is absent; only
            # the property-level value — null on this branch — applies.
            currency = instance.currency
        return currency.code if currency is not None else None

    @staticmethod
    def _effective_prices_entered_as(instance: PropertySettings) -> str | None:
        try:
            return instance.effective("prices_entered_as")
        except ObjectDoesNotExist:
            # Missing GroupSettings row — fall back to the (possibly null)
            # property-level value rather than 500.
            return instance.prices_entered_as or None

    @staticmethod
    def _rate_entry_finance(
        instance: PropertySettings,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Group-resolved commission + tax for the net↔gross derivation.

        Defers to the canonical `PropertyFinance.effective_commission()` /
        `effective_tax_policy()` resolvers (the same figures the engine prices
        with — never hand-roll the property→group chain), then narrows to the
        two fields the rate-band form needs. The resolvers' `self.property`
        back-leg and the group fallback both ride the `finance` /
        `group__finance` chain the view prefetches, so the query-count pin
        holds. When the property has no `PropertyFinance` row the effective
        value *is* the group floor, read off `GroupFinance` directly (it has no
        inheritance of its own). `None` only when the floor itself is absent.
        """

        def money(value: Any) -> str | None:
            return str(value) if value is not None else None

        try:
            finance = instance.property.finance
        except ObjectDoesNotExist:
            finance = None

        if finance is not None:
            commission_src = finance.effective_commission()
            tax_src = finance.effective_tax_policy()
        else:
            try:
                group_finance = instance.property.group.finance
            except ObjectDoesNotExist:
                return None, None
            commission_src = {
                "calculation_type": group_finance.commission_calculation_type,
                "amount": group_finance.commission_amount,
            }
            tax_src = {
                "is_exempt": group_finance.tax_is_exempt,
                "percentage": group_finance.tax_percentage,
            }

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
