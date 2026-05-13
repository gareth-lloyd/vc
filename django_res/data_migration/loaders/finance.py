"""PropertyFinance + Quotation loaders.

VillaFinance -> PropertyFinance (per-property; group/parent inheritance
left at defaults). Tiny QuotationMaster (19 rows) and Lines (23) round out
the data. A default TermsVersion is created if none exists so Quotation's
PROTECT FK resolves.

Booking + Payment loaders are skipped intentionally: only 3 bookings and
1 payment in the live snapshot, with heavy FK requirements (quotation_line,
terms_version, etc.) and the EXCLUDE-constraint risk. Easier for ops to
re-key them post-migration.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone

from accounts.models import Contact
from data_migration.base import BaseLoader, LoadReport
from pricing.models.currency import Currency
from properties.enums import (
    CommissionCalcType,
    DepositCalcType,
    SecurityDepositCalcFrom,
    SecurityDepositCalcType,
    SecurityDepositPaymentMethod,
)
from properties.models.finance import PropertyFinance
from properties.models.property import Property
from reservations.enums import QuotationStatus
from reservations.models.guest import Guest
from reservations.models.quotation import Quotation, QuotationLine
from reservations.models.terms import TermsVersion

_COMMISSION_TYPE_MAP = {
    1: CommissionCalcType.PERCENT,
    2: CommissionCalcType.FIXED,
}
_DEPOSIT_TYPE_MAP = {
    1: DepositCalcType.PERCENT,
    2: DepositCalcType.FIXED,
}
_SEC_DEPOSIT_TYPE_MAP = {
    1: SecurityDepositCalcType.PERCENT,
    2: SecurityDepositCalcType.FIXED,
}
_SEC_DEPOSIT_FROM_MAP = {
    1: SecurityDepositCalcFrom.NIGHTLY,
    2: SecurityDepositCalcFrom.WEEKLY,
    3: SecurityDepositCalcFrom.TOTAL_STAY,
}


def _decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


class PropertyFinanceLoader(BaseLoader):
    """VillaFinance -> PropertyFinance (one row per VillaId).

    PropertyFinance is a OneToOne with property as primary key, so we upsert
    via property, not legacy_id. Group-level rows (no VillaId) are skipped.
    """

    name = "property_finance"
    target_model = PropertyFinance
    legacy_query = (
        "SELECT Id, VillaId, ContactId, CommissionTypeId, CommissionAmount, "
        "CommissionNote, TaxNumber, TaxExempt, TaxPercentage, "
        "BankAccAccountname, BankAccAccountnumber, BankAccAccountSortCode, "
        "BankAccAccountIBAN, BankAccAccountBIC, BankAccAddres1, BankAccAddres2, "
        "BankAccPostCode, BankAccTown, "
        "PaymentScheduleIsDepositRequired, PaymentScheduleDepositTypeId, "
        "PaymentScheduleDepositAmount, "
        "PaymentScheduleIsInterimRequired, PaymentScheduleInterimTypeId, "
        "PaymentScheduleInterimAmount, "
        "PaymentScheduleDaysInterimDueBeforeArrival, "
        "PaymentScheduleDaysBalanceDueBeforeArrival, "
        "SecurityDepositIsRequired, SecurityDepositAmountTypeId, "
        "SecurityDepositAmount, SecurityDepositCalculateFromId, "
        "SecurityDepositDaysDueBeforeArrival, SecurityDepositDaysRefundedAfterDeparture "
        "FROM VillaFinance WHERE VillaId IS NOT NULL"
    )

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        prop = Property.objects.filter(legacy_id=str(row.get("VillaId") or "")).first()
        if prop is None:
            report.skipped += 1
            return
        contact = (
            Contact.objects.filter(legacy_id=str(row["ContactId"])).first()
            if row.get("ContactId")
            else None
        )

        defaults: dict[str, Any] = {
            "contact": contact,
            "commission_calculation_type": _COMMISSION_TYPE_MAP.get(
                row.get("CommissionTypeId") or 0,
            ),
            "commission_amount": _decimal(row.get("CommissionAmount")),
            "commission_note": (row.get("CommissionNote") or "")[:1000],
            "tax_number": (row.get("TaxNumber") or "")[:64],
            "tax_is_exempt": (bool(row["TaxExempt"]) if row.get("TaxExempt") is not None else None),
            "tax_percentage": _decimal(row.get("TaxPercentage")),
            "bank_account_name": (row.get("BankAccAccountname") or "")[:128],
            "bank_account_number": (row.get("BankAccAccountnumber") or "")[:255],
            "bank_sort_code": (row.get("BankAccAccountSortCode") or "")[:255],
            "bank_iban": (row.get("BankAccAccountIBAN") or "")[:255],
            "bank_bic": (row.get("BankAccAccountBIC") or "")[:255],
            "bank_address_line_1": (row.get("BankAccAddres1") or "")[:255],
            "bank_address_line_2": (row.get("BankAccAddres2") or "")[:255],
            "bank_post_code": (row.get("BankAccPostCode") or "")[:32],
            "bank_city": (row.get("BankAccTown") or "")[:128],
            "deposit_required": (
                bool(row["PaymentScheduleIsDepositRequired"])
                if row.get("PaymentScheduleIsDepositRequired") is not None
                else None
            ),
            "deposit_calculation_type": _DEPOSIT_TYPE_MAP.get(
                row.get("PaymentScheduleDepositTypeId") or 0,
            ),
            "deposit_amount": _decimal(row.get("PaymentScheduleDepositAmount")),
            "interim_required": (
                bool(row["PaymentScheduleIsInterimRequired"])
                if row.get("PaymentScheduleIsInterimRequired") is not None
                else None
            ),
            "interim_calculation_type": _DEPOSIT_TYPE_MAP.get(
                row.get("PaymentScheduleInterimTypeId") or 0,
            ),
            "interim_amount": _decimal(row.get("PaymentScheduleInterimAmount")),
            "days_interim_due_before_arrival": row.get(
                "PaymentScheduleDaysInterimDueBeforeArrival",
            ),
            "days_balance_due_before_arrival": row.get(
                "PaymentScheduleDaysBalanceDueBeforeArrival",
            ),
            "security_deposit_required": (
                bool(row["SecurityDepositIsRequired"])
                if row.get("SecurityDepositIsRequired") is not None
                else None
            ),
            "security_deposit_calculation_type": _SEC_DEPOSIT_TYPE_MAP.get(
                row.get("SecurityDepositAmountTypeId") or 0,
            ),
            "security_deposit_amount": _decimal(row.get("SecurityDepositAmount")),
            "security_deposit_calculate_from": _SEC_DEPOSIT_FROM_MAP.get(
                row.get("SecurityDepositCalculateFromId") or 0,
            ),
            "security_deposit_days_due_before_arrival": row.get(
                "SecurityDepositDaysDueBeforeArrival",
            ),
            "security_deposit_days_refunded_after_departure": row.get(
                "SecurityDepositDaysRefundedAfterDeparture",
            ),
            "security_deposit_payment_method": SecurityDepositPaymentMethod.BANK_TRANSFER,
        }
        # Drop keys whose values are negative numbers (legacy junk).
        for k in list(defaults):
            v = defaults[k]
            if isinstance(v, (int, Decimal)) and v < 0:
                defaults[k] = None

        _, created = PropertyFinance.objects.update_or_create(
            property=prop,
            defaults=defaults,
        )
        if created:
            report.created += 1
        else:
            report.updated += 1


def _ensure_default_terms() -> TermsVersion:
    tv, _ = TermsVersion.objects.get_or_create(
        version="legacy-import-v1",
        defaults={
            "body_markdown": "Legacy import terms — replace before re-issuing.",
            "is_current": False,
        },
    )
    return tv


class QuotationLoader(BaseLoader):
    name = "quotation"
    target_model = Quotation
    legacy_query = (
        "SELECT q.Id, q.ClientDetailsId, q.AgentId, q.FromDate, q.ToDate, "
        "q.EnquireId, q.QuotationNo, q.EnquiryNote, q.DeletedAt, "
        "(SELECT TOP 1 d.CurrencyId FROM VillaQuotationDetails d "
        " WHERE d.QuotationMasterId = q.Id ORDER BY d.Id) AS CurrencyId "
        "FROM VillaQuotationMaster q WHERE q.DeletedAt IS NULL"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        guest = Guest.objects.filter(legacy_id=str(row.get("ClientDetailsId") or "")).first()
        if guest is None:
            return None
        currency = (
            Currency.objects.filter(legacy_id=str(row["CurrencyId"])).first()
            if row.get("CurrencyId")
            else Currency.objects.first()
        )
        if currency is None:
            return None
        agent = (
            Contact.objects.filter(legacy_id=str(row["AgentId"])).first()
            if row.get("AgentId")
            else None
        )
        terms = _ensure_default_terms()
        return {
            "reference": f"Q-{int(row.get('QuotationNo') or row['Id']):06d}"[:32],
            "guest": guest,
            "agent": agent,
            "currency": currency,
            "expires_at": timezone.now() + timedelta(days=7),
            "status": QuotationStatus.DRAFT,
            "terms_version": terms,
        }


class QuotationLineLoader(BaseLoader):
    name = "quotation_line"
    target_model = QuotationLine
    legacy_query = (
        "SELECT Id, QuotationMasterId, VillaId, FromDate, ToDate, Price, "
        "CurrencyId, IsManual FROM VillaQuotationDetails"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        quotation = Quotation.objects.filter(
            legacy_id=str(row.get("QuotationMasterId") or ""),
        ).first()
        prop = Property.objects.filter(legacy_id=str(row.get("VillaId") or "")).first()
        if quotation is None or prop is None:
            return None
        date_from = row.get("FromDate")
        date_to = row.get("ToDate")
        if not (date_from and date_to):
            return None
        if hasattr(date_from, "date"):
            date_from = date_from.date()
        if hasattr(date_to, "date"):
            date_to = date_to.date()
        if date_from >= date_to:
            return None
        return {
            "quotation": quotation,
            "property": prop,
            "date_from": date_from,
            "date_to": date_to,
            "adults": 2,
            "children": 0,
            "total": _decimal(row.get("Price")) or Decimal("0"),
            "is_selected": False,
            "is_manual": bool(row.get("IsManual")),
        }
