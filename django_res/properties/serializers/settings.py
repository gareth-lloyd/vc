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

        Resolves each field property → group from the already-prefetched
        `finance` / `group__finance` chain (no `finance.property` back-trip, so
        the query-count pin holds). `None` only when the group floor itself is
        absent (no `GroupFinance`), which the auto-create signal makes unusual.
        """
        try:
            prop_finance = instance.property.finance
        except ObjectDoesNotExist:
            prop_finance = None
        try:
            group_finance = instance.property.group.finance
        except ObjectDoesNotExist:
            group_finance = None
        if group_finance is None and prop_finance is None:
            return None, None

        def eff(field: str) -> Any:
            if prop_finance is not None:
                own = getattr(prop_finance, field)
                if own is not None and own != "":
                    return own
            return getattr(group_finance, field) if group_finance is not None else None

        def money(value: Any) -> str | None:
            return str(value) if value is not None else None

        commission = {
            "calculation_type": eff("commission_calculation_type"),
            "amount": money(eff("commission_amount")),
        }
        tax = {
            "percentage": money(eff("tax_percentage")),
            "is_exempt": eff("tax_is_exempt"),
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
