"""Owner-facing booking serializers — a strict redaction allowlist.

Built as an explicit `to_representation` rather than a ModelSerializer: every
exposed key is written by hand, so a future model field can never leak into the
owner surface by accident. Redaction is per-property and server-keyed off
`context["visibility"]` (from `owners.scoping.owner_visibility_map`):

  - money (`rental_price`, `balance_due`, and the detail breakdown) appears only
    when the property's grant has `view_full_money`;
  - `guest_contact` (email + phone) appears only when `view_guest_details`.

The guest is always *named* — full name, country, repeat flag — but their
contact channel and any internal notes are never present without the grant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rest_framework import serializers

from reservations.services.owner_finance import owner_money_from_snapshot

if TYPE_CHECKING:
    from reservations.models import Booking
    from reservations.models.guest import Guest

_HIDDEN_VISIBILITY = {"view_full_money": False, "view_guest_details": False}


class OwnerBookingListSerializer(serializers.Serializer):
    """List representation. Money columns are gated per property."""

    detail = False

    def _visibility(self, obj: Booking) -> dict[str, bool]:
        return self.context["visibility"].get(obj.property_id, _HIDDEN_VISIBILITY)

    @staticmethod
    def _country(guest: Guest | None) -> dict[str, str] | None:
        country = guest.country if guest is not None else None
        if country is None:
            return None
        return {"code": country.iso2, "name": country.name}

    def to_representation(self, instance: Booking) -> dict[str, Any]:
        obj = instance
        vis = self._visibility(obj)
        guest = obj.guest if obj.guest_id else None
        prop = obj.property if obj.property_id else None

        data: dict[str, Any] = {
            "id": obj.id,
            "reference": obj.reference,
            "status": obj.status,
            "property_id": obj.property_id,
            "property_name": ((prop.display_name or prop.name) or None) if prop else None,
            "date_from": obj.date_from,
            "date_to": obj.date_to,
            "adults": obj.adults,
            "children": obj.children,
            "currency_code": obj.currency.code if obj.currency_id else None,
            "guest_name": (
                (f"{guest.first_name} {guest.last_name}".strip() or None) if guest else None
            ),
            "guest_country": self._country(guest),
            "is_repeat_guest": bool(getattr(obj, "is_repeat_guest", False)),
        }

        if vis["view_full_money"]:
            data["rental_price"] = f"{obj.rental_price:.2f}"
            data["balance_due"] = f"{obj.balance_due:.2f}"
        if vis["view_guest_details"] and guest is not None:
            data["guest_contact"] = {"email": guest.email, "phone": guest.phone}
        if self.detail:
            self._add_financial_detail(data, obj, vis)
        return data

    def _add_financial_detail(
        self, data: dict[str, Any], obj: Booking, vis: dict[str, bool]
    ) -> None:
        if not vis["view_full_money"]:
            return
        money = owner_money_from_snapshot(obj.pricing_snapshot)
        if money is None:
            return
        data["gross_total"] = f"{money['gross_total']:.2f}"
        data["commission"] = f"{money['commission']:.2f}"
        data["net_to_owner"] = f"{money['net_to_owner']:.2f}"


class OwnerBookingDetailSerializer(OwnerBookingListSerializer):
    """Detail representation. Adds the gated gross/commission/net breakdown."""

    detail = True
