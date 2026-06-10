"""Charge-item money helpers (and, later, the charge-item CRUD service).

Owner-side accounting follows legacy: manual charges enter the
commissionable base. The guest always pays the entered amount verbatim;
this module only answers how that money splits between owner and agency.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

from properties.enums import CommissionCalcType

ZERO = Decimal("0.00")


class OwnerEffect(NamedTuple):
    """How a bookings' charge lines move the owner statement."""

    commission_on_charges: Decimal
    owner_delta: Decimal


def owner_effect(
    charges_total: Decimal,
    calculation_type: str | None,
    commission_amount: Decimal | None,
) -> OwnerEffect:
    """Split `charges_total` between agency commission and owner net.

    PERCENT commission skims its percentage off every charge (credits are
    symmetric — owner and agency share a credit by the same split). FIXED
    commission never moves with charges, so they flow to the owner in
    full; so do charges on properties with no commission configured.
    Charges are entered gross/tax-inclusive — tax is never recomputed.
    """
    if not charges_total:
        return OwnerEffect(ZERO, ZERO)
    if calculation_type == CommissionCalcType.PERCENT.value and commission_amount is not None:
        commission = (charges_total * commission_amount / Decimal("100")).quantize(Decimal("0.01"))
        return OwnerEffect(commission, charges_total - commission)
    return OwnerEffect(ZERO, charges_total)
