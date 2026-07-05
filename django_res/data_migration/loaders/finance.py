"""PropertyFinance + Quotation loaders.

VillaFinance is a multi-purpose table:
- `VillaId > 0` rows → per-property `PropertyFinance` (PropertyFinanceLoader).
- `VillaId IS NULL/0, ContactId NOT NULL, ParentId NULL` rows are per-contact
  defaults (`_fetch_contact_default_finance`); PropertyFinanceLoader applies
  them concretely to villas that have no VillaFinance row of their own
  (GAP-070 decision 7).
- `VillaId IS NULL/0, ParentId NOT NULL` rows are parent-child overrides;
  not migrated (no schema equivalent).
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import timedelta
from decimal import Decimal
from typing import Any

import structlog
from django.db import transaction
from django.utils import timezone

from accounts.enums import ContactRole
from accounts.models import Person
from core.refs import quotation_reference
from data_migration.base import BaseLoader, LoadReport
from data_migration.legacy_db import legacy_cursor, rows_as_dicts
from data_migration.loaders._util import ensure_enquiry, legacy_quotation_no, person_for_client
from pricing.models.currency import Currency
from pricing.services.currency import resolve_property_currency
from properties.enums import (
    CommissionCalcType,
    DepositCalcType,
    SecurityDepositCalcType,
    SecurityDepositPaymentMethod,
)
from properties.models.contacts import PropertyContactAssignment
from properties.models.finance import PropertyFinance
from properties.models.property import Property
from reservations.enums import QuotationStatus
from reservations.models.enquiry import Enquiry
from reservations.models.quotation import Quotation, QuotationLine
from reservations.models.terms import TermsVersion

logger = structlog.get_logger(__name__)

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

_VILLAFINANCE_COLUMNS = (
    "Id, VillaId, ContactId, ParentId, CommissionTypeId, CommissionAmount, "
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
    "SecurityDepositAmount, "
    "SecurityDepositDaysDueBeforeArrival, SecurityDepositDaysRefundedAfterDeparture"
)


def _decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _finance_defaults(row: dict[str, Any]) -> dict[str, Any]:
    """Translate a VillaFinance row into model-field defaults.

    All PropertyFinance policy fields are nullable, so `None`s pass through
    (a NULL means the legacy column was unset).
    """
    defaults: dict[str, Any] = {
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
        "security_deposit_days_due_before_arrival": row.get(
            "SecurityDepositDaysDueBeforeArrival",
        ),
        "security_deposit_days_refunded_after_departure": row.get(
            "SecurityDepositDaysRefundedAfterDeparture",
        ),
        "security_deposit_payment_method": SecurityDepositPaymentMethod.BANK_TRANSFER,
    }
    # Drop negative numerics (legacy junk).
    for k in list(defaults):
        v = defaults[k]
        if isinstance(v, (int, Decimal)) and v < 0:
            defaults[k] = None
    return defaults


class PropertyFinanceLoader(BaseLoader):
    """VillaFinance -> PropertyFinance (one row per VillaId).

    PropertyFinance is a OneToOne with property as primary key, so we upsert
    via property, not legacy_id. After the per-villa pass, villas with no
    VillaFinance row of their own get their primary-OWNER contact's default
    template written concretely (GAP-070 decision 7) — pre-GAP-070 those
    defaults reached the villa via GroupFinance + ``effective()`` at read
    time; post-GAP-070 the resolution happens once, at load time.
    """

    name = "property_finance"
    target_model = PropertyFinance
    legacy_query = f"SELECT {_VILLAFINANCE_COLUMNS} FROM VillaFinance WHERE VillaId IS NOT NULL"

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        super()._load_rows(rows, report)
        # A villa whose legacy row appeared in THIS pass is never
        # fallback-filled — even when its write errored into report.errors
        # (a template row masking a persistent write failure would freeze
        # wrong money terms with only a buried error line as a clue).
        seen = {str(r["VillaId"]) for r in rows if r.get("VillaId")}
        self._apply_contact_defaults(report, exclude_legacy_ids=seen)

    def _by_contact(self) -> dict[str, dict[str, Any]]:
        # One legacy round trip per load, shared by the per-villa merge and
        # the fallback pass; fetched lazily on first use.
        if not hasattr(self, "_by_contact_cache"):
            self._by_contact_cache = _fetch_contact_default_finance()
        return self._by_contact_cache

    def _apply_contact_defaults(
        self,
        report: LoadReport,
        *,
        exclude_legacy_ids: Collection[str] = frozenset(),
    ) -> None:
        """Fill financeless villas from their owner-contact default template.

        Only creates rows where none exist, so the per-villa pass is never
        overwritten and re-runs are idempotent (create-only: a template edit
        in legacy after the row is written does NOT propagate — the rows
        carry no origin marker to refresh by). Non-migrated properties (no
        legacy_id) are out of scope — they get rows via `snapshot_defaults`.
        """
        villas = (
            Property.objects.filter(legacy_id__isnull=False, finance__isnull=True)
            .exclude(legacy_id="")
            .exclude(legacy_id__in=exclude_legacy_ids)
        )
        if not villas.exists():
            return
        outcomes = {"applied": 0, "contact_only": 0, "skipped": 0}
        with transaction.atomic():
            for prop in villas:
                try:
                    with transaction.atomic():
                        outcomes[self._fallback_one(prop, report)] += 1
                except Exception as exc:  # isolate one bad villa from the rest
                    report.errors.append((str(prop.legacy_id), repr(exc)))
        # Deliberately not folded into report.skipped: the loadlegacy summary
        # row reconciles against the legacy `VillaId IS NOT NULL` count, and
        # these are Postgres-side villas, not legacy rows.
        logger.info(
            "data_migration.finance_contact_defaults_applied",
            applied=outcomes["applied"],
            contact_only=outcomes["contact_only"],
            skipped=outcomes["skipped"],
        )

    def _fallback_one(self, prop: Property, report: LoadReport) -> str:
        # Live assignments only, primary preferred, deterministic tie-break;
        # a primary owner without a legacy_id can't match a template, so the
        # filter lets a migrated non-primary owner resolve instead.
        owner = (
            PropertyContactAssignment.objects.filter(
                property=prop,
                role=ContactRole.OWNER,
                end_date__isnull=True,
                contact__legacy_id__isnull=False,
            )
            .exclude(contact__legacy_id="")
            .order_by("-is_primary", "pk")
            .values_list("contact__legacy_id", "contact_id")
            .first()
        )
        if owner is None:
            return "skipped"
        owner_legacy_id, owner_pk = owner
        if not owner_legacy_id:  # filtered above; narrows the Optional for mypy
            return "skipped"
        template = self._by_contact().get(owner_legacy_id)
        if template is None:
            # Owner known but no legacy template: still record the finance
            # contact (the old GroupFinance mirror carried the contact even
            # without one); NULL policy columns read as the frozen floor,
            # which equals the old GroupFinance schema defaults.
            PropertyFinance.objects.create(property=prop, contact_id=owner_pk)
            report.created += 1
            return "contact_only"
        defaults = _finance_defaults(template)
        defaults["contact_id"] = owner_pk
        PropertyFinance.objects.create(property=prop, **defaults)
        report.created += 1
        return "applied"

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        prop = Property.objects.filter(legacy_id=str(row.get("VillaId") or "")).first()
        if prop is None:
            report.skipped += 1
            return
        contact = (
            Person.objects.filter(legacy_id=str(row["ContactId"])).first()
            if row.get("ContactId")
            else None
        )
        defaults = _finance_defaults(row)
        # GAP-070 parity: pre-cutover, a NULL/"" field on a villa's own row
        # resolved through the owner-contact default template at read time
        # (GroupFinance + effective()). Reproduce that merge concretely —
        # own value wins unless it is None/"" (0/False are own values).
        template = self._by_contact().get(str(row["ContactId"])) if row.get("ContactId") else None
        if template is not None:
            template_defaults = _finance_defaults(template)
            for field, own in defaults.items():
                fallback = template_defaults.get(field)
                if (own is None or own == "") and fallback not in (None, ""):
                    defaults[field] = fallback
        defaults["contact"] = contact

        _, created = PropertyFinance.objects.update_or_create(
            property=prop,
            defaults=defaults,
        )
        if created:
            report.created += 1
        else:
            report.updated += 1


def _fetch_contact_default_finance() -> dict[str, dict[str, Any]]:
    """Pull all per-contact default VillaFinance rows, keyed by legacy ContactId.

    These are rows with `VillaId IS NULL/0, ContactId IS NOT NULL,
    ParentId IS NULL`. If a contact has multiple such rows, the first one
    wins.
    """
    query = (
        f"SELECT {_VILLAFINANCE_COLUMNS} FROM VillaFinance "
        "WHERE (VillaId IS NULL OR VillaId = 0) "
        "AND ContactId IS NOT NULL AND ParentId IS NULL"
    )
    by_contact: dict[str, dict[str, Any]] = {}
    with legacy_cursor() as cursor:
        cursor.execute(query)
        for row in rows_as_dicts(cursor):
            cid = str(row["ContactId"])
            by_contact.setdefault(cid, row)
    return by_contact


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
    # No currency here: the header has none (GAP-014, legacy parity) — each
    # line carries its own, resolved by QuotationLineLoader from the legacy
    # per-detail CurrencyId.
    legacy_query = (
        "SELECT q.Id, q.ClientDetailsId, q.AgentId, q.FromDate, q.ToDate, "
        "q.EnquireId, q.QuotationNo, q.EnquiryNote, q.DeletedAt "
        "FROM VillaQuotationMaster q WHERE q.DeletedAt IS NULL"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        person = person_for_client(row.get("ClientDetailsId"))
        if person is None:
            return None
        agent = (
            Person.objects.filter(legacy_id=str(row["AgentId"])).first()
            if row.get("AgentId")
            else None
        )
        # `Quotation.enquiry` is mandatory. Resolve the legacy EnquireId to its
        # imported Enquiry; for agent-direct quotes (EnquireId 0/NULL/unresolved)
        # back-create a minimal one, mirroring legacy `sp_quotationMaster`.
        enquiry = None
        if row.get("EnquireId"):
            enquiry = Enquiry.objects.filter(legacy_id=str(row["EnquireId"])).first()
        if enquiry is None:
            enquiry = ensure_enquiry(person, legacy_id=f"q{row['Id']}-autoenquiry", agent=agent)
        terms = _ensure_default_terms()
        # Carry the legacy QuotationNo forward as the canonical `number` so the
        # booking can derive `VC{number}` from `QVC{number}`. Setting both
        # `number` and `reference` short-circuits Quotation.save()'s sequence
        # draw, preserving the exact legacy digits.
        #
        # When QuotationNo is missing/0, we still want a numeric, customer-safe
        # reference (`QVC{Id}` — not a `QVC-TMP` sentinel that would leak into
        # the public quotation list), but we must NOT claim a `number`: the Id
        # namespace overlaps real QuotationNos and `number` is unique. So the
        # `number` key is set only when a genuine QuotationNo is present.
        qn = legacy_quotation_no(row)
        display = qn if qn is not None else int(row["Id"])
        defaults: dict[str, Any] = {
            "reference": quotation_reference(display)[:32],
            "enquiry": enquiry,
            # GAP-045 D5-3: `person` (resolved from the legacy client id via
            # `person_for_client`) is the sole customer FK written on the real
            # legacy quotation upsert. No `Guest` is touched.
            "person": person,
            "agent": agent,
            "expires_at": timezone.now() + timedelta(days=7),
            "status": QuotationStatus.DRAFT,
            "terms_version": terms,
        }
        if qn is not None:
            defaults["number"] = qn
        return defaults


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
        # Per-line currency (GAP-014, legacy VillaQuotationDetails.CurrencyId):
        # row value, else the villa's canonical chain — never `.first()`.
        currency: Currency | None = None
        if row.get("CurrencyId"):
            currency = Currency.objects.filter(legacy_id=str(row["CurrencyId"])).first()
        if currency is None:
            currency = resolve_property_currency(prop)
        if currency is None:
            return None
        return {
            "quotation": quotation,
            "property": prop,
            "currency": currency,
            "date_from": date_from,
            "date_to": date_to,
            "adults": 2,
            "children": 0,
            "total": _decimal(row.get("Price")) or Decimal("0"),
            "is_selected": False,
            "is_manual": bool(row.get("IsManual")),
        }
