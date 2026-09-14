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
from dataclasses import dataclass
from datetime import date, timedelta
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
from data_migration.loaders._util import (
    ensure_enquiry,
    legacy_currency_for,
    legacy_quotation_no,
    person_for_client,
)
from data_migration.loaders.pricing import PRICED_ROW_PREDICATE
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

# Legacy calculation-type codes: 10 = Percentage, 20 = Fixed
# (`ResSystem/Common/Enums.cs:173-177`; `DepositType` seeds in `DbScript.sql`).
# 0 / NULL mean "not set".
_COMMISSION_TYPE_MAP = {
    10: CommissionCalcType.PERCENT,
    20: CommissionCalcType.FIXED,
}
_DEPOSIT_TYPE_MAP = {
    10: DepositCalcType.PERCENT,
    20: DepositCalcType.FIXED,
}
_SEC_DEPOSIT_TYPE_MAP = {
    10: SecurityDepositCalcType.PERCENT,
    20: SecurityDepositCalcType.FIXED,
}


def _calc_type(mapping: dict[int, Any], value: Any) -> Any:
    """Map a legacy type code; `None` for unset (NULL/0) or unknown codes."""
    return mapping.get(value) if value else None


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
    "SecurityDepositDaysDueBeforeArrival, SecurityDepositDaysRefundedAfterDeparture, "
    "IsDefaultCommission, IsDefaultPaysched, IsDefaultSecDep"
)

# The global `VillaConfigPropertyDefault` (CPD) singleton row.
CPD_QUERY = (
    "SELECT Id, IsBookingsRequirePreApproval, CurrencyId, "
    "CommissionType, CommissionAmount, CheckinTime, CheckOutTime, "
    "ChangeOverDay, MinimumNightsRental, "
    "IsDepositRequired, DepositType, DepositAmount, "
    "IsInterimRequired, InterimType, InterimAmount, "
    "DaysInterimDueBeforeArrival, DaysBalanceDueBeforeArrival, "
    "SecurityDepositRequired, SecurityDepositAmountType, "
    "SecurityDepositAmount, SecurityDepositDaysDueBeforeArrival, "
    "SecurityDepositDaysDefundedAfterDeparture "
    "FROM VillaConfigPropertyDefault ORDER BY Id"
)

# (VillaFinance column, CPD column) pairs per `IsDefault*` block, from
# `PropertyService2.cs:169-238`. Sec-dep days due read the CPD's
# DaysBalanceDueBeforeArrival — legacy never reads its sec-dep days column.
_COMMISSION_FROM_CPD = (
    ("CommissionTypeId", "CommissionType"),
    ("CommissionAmount", "CommissionAmount"),
)
_PAYSCHED_NUMERICS = (
    ("PaymentScheduleDepositTypeId", "DepositType"),
    ("PaymentScheduleDepositAmount", "DepositAmount"),
    ("PaymentScheduleInterimTypeId", "InterimType"),
    ("PaymentScheduleInterimAmount", "InterimAmount"),
    ("PaymentScheduleDaysInterimDueBeforeArrival", "DaysInterimDueBeforeArrival"),
    ("PaymentScheduleDaysBalanceDueBeforeArrival", "DaysBalanceDueBeforeArrival"),
)
_PAYSCHED_BOOLS = (
    ("PaymentScheduleIsDepositRequired", "IsDepositRequired"),
    ("PaymentScheduleIsInterimRequired", "IsInterimRequired"),
)
_SECDEP_NUMERICS = (
    ("SecurityDepositAmountTypeId", "SecurityDepositAmountType"),
    ("SecurityDepositAmount", "SecurityDepositAmount"),
    ("SecurityDepositDaysDueBeforeArrival", "DaysBalanceDueBeforeArrival"),
    ("SecurityDepositDaysRefundedAfterDeparture", "SecurityDepositDaysDefundedAfterDeparture"),
)
_SECDEP_BOOLS = (("SecurityDepositIsRequired", "SecurityDepositRequired"),)


def fetch_config_property_default() -> dict[str, Any]:
    """The legacy CPD row. Raises when absent — a silent `None` would
    reproduce BUG-028's mis-load without a trace."""
    with legacy_cursor() as cursor:
        cursor.execute(CPD_QUERY)
        row = next(rows_as_dicts(cursor), None)
    if row is None:
        raise RuntimeError("VillaConfigPropertyDefault has no row")
    return row


def apply_legacy_finance_defaults(
    row: dict[str, Any], cpd: dict[str, Any] | None
) -> dict[str, Any]:
    """Resolve a raw VillaFinance row's `IsDefault*` flags against the CPD.

    Port of `PropertyService2.cs:169-238`: a flagged block is copied from the
    CPD wholesale; an unflagged block has each numeric `<= 0` replaced (the
    legacy view model is non-nullable, so NULL reads as 0 and a NULL boolean
    as False). Returns a new dict.

    One deliberate deviation: legacy applies `<= 0` to the unflagged
    commission *amount* only, leaving a 0 type that renders blank. We fill
    the type the same way (as for deposit/sec-dep types), so an amount taken
    from the CPD never pairs with a type from elsewhere (BUG-028 review).
    """
    if cpd is None:
        raise RuntimeError("VillaConfigPropertyDefault row is required")
    out = dict(row)

    def from_cpd(column: str) -> Any:
        return cpd.get(column) or 0  # C# ChangeType(NULL) -> 0

    blocks: tuple[tuple[str, tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]], ...] = (
        ("IsDefaultCommission", _COMMISSION_FROM_CPD, ()),
        ("IsDefaultPaysched", _PAYSCHED_NUMERICS, _PAYSCHED_BOOLS),
        ("IsDefaultSecDep", _SECDEP_NUMERICS, _SECDEP_BOOLS),
    )
    for flag, numerics, bools in blocks:
        if row.get(flag):
            for own, default in numerics:
                out[own] = from_cpd(default)
            for own, default in bools:
                out[own] = bool(cpd.get(default))
            continue
        for own, default in numerics:
            if (out.get(own) or 0) <= 0:
                out[own] = from_cpd(default)
        for own, _default in bools:
            out[own] = bool(out.get(own))
    return out


# A calculation type only means something next to its own amount: the
# template merge must not fill one half of a pair the CPD already resolved.
_AMOUNT_FOR_TYPE = {
    "commission_calculation_type": "commission_amount",
    "deposit_calculation_type": "deposit_amount",
    "interim_calculation_type": "interim_amount",
    "security_deposit_calculation_type": "security_deposit_amount",
}


@dataclass(frozen=True)
class RateRowFinance:
    """A villa's majority commission / tax across its current rate rows."""

    commission: tuple[int, Decimal] | None  # (type code, amount)
    tax: tuple[Decimal, bool] | None  # (rate, exempt)
    commission_mixed: bool
    tax_mixed: bool


def rate_row_finance_query(reference_date: date) -> str:
    """Current, quotable, non-POA rate rows grouped by villa and finance terms
    (the rows `RateBandLoader` loads, from `reference_date` onwards)."""
    return (
        "SELECT s.VillaId, r.CommissionType, r.Commission, r.TaxRate, r.IsTaxExempt, "
        "COUNT(*) AS N "
        "FROM VillaSeasonRate r "
        "JOIN VillaSeason s ON s.ID = r.SeasonId AND s.DeletedAt IS NULL "
        f"WHERE {PRICED_ROW_PREDICATE} AND ISNULL(r.IsPOA, 0) = 0 "
        f"AND r.ToDate >= '{reference_date.isoformat()}' "
        "GROUP BY s.VillaId, r.CommissionType, r.Commission, r.TaxRate, r.IsTaxExempt"
    )


def _majority(votes: dict[Any, int]) -> tuple[Any, bool]:
    """(winner, mixed): highest row count, ties to the lowest key."""
    if not votes:
        return None, False
    winner = min(votes, key=lambda k: (-votes[k], k))
    return winner, len(votes) > 1


def rate_row_finance_by_villa(groups: list[dict[str, Any]]) -> dict[str, RateRowFinance]:
    """Per legacy VillaId: the majority commission (positive amount with a
    10/20 type) and tax (exempt, or a positive rate) over the grouped rows."""
    commission: dict[str, dict[tuple[int, Decimal], int]] = {}
    tax: dict[str, dict[tuple[Decimal, bool], int]] = {}
    for g in groups:
        villa = str(g["VillaId"])
        commission.setdefault(villa, {})
        tax.setdefault(villa, {})
        n = int(g.get("N") or 0)
        amount = _decimal(g.get("Commission"))
        if g.get("CommissionType") in _COMMISSION_TYPE_MAP and amount is not None and amount > 0:
            key = (int(g["CommissionType"]), amount.quantize(Decimal("0.01")))
            commission[villa][key] = commission[villa].get(key, 0) + n
        rate = _decimal(g.get("TaxRate"))
        if g.get("IsTaxExempt"):
            tax_key = (Decimal("0"), True)
        elif rate is not None and rate > 0:
            tax_key = (rate, False)
        else:
            continue
        tax[villa][tax_key] = tax[villa].get(tax_key, 0) + n
    out: dict[str, RateRowFinance] = {}
    for villa in commission:
        commission_winner, commission_mixed = _majority(commission[villa])
        tax_winner, tax_mixed = _majority(tax[villa])
        out[villa] = RateRowFinance(commission_winner, tax_winner, commission_mixed, tax_mixed)
    return out


def apply_rate_row_finance(
    row: dict[str, Any],
    villa_finance: RateRowFinance | None,
    *,
    row_is_villas_own: bool = True,
) -> dict[str, Any]:
    """BUG-028 D7: a default-flagged or non-positive commission, and an unset
    non-exempt tax, take the villa's rate-row majority before the CPD rule.
    An own explicit value is kept — but an owner-contact template is not the
    villa's own (`row_is_villas_own=False`), so the majority beats it.
    Returns a new dict."""
    out = dict(row)
    if villa_finance is None:
        return out
    if villa_finance.commission is not None and (
        not row_is_villas_own
        or row.get("IsDefaultCommission")
        or (row.get("CommissionAmount") or 0) <= 0
    ):
        out["CommissionTypeId"], out["CommissionAmount"] = villa_finance.commission
        out["IsDefaultCommission"] = False
    if villa_finance.tax is not None and (
        not row_is_villas_own or (not row.get("TaxExempt") and (row.get("TaxPercentage") or 0) <= 0)
    ):
        out["TaxPercentage"], out["TaxExempt"] = villa_finance.tax
    return out


def _strip_default_flags(row: dict[str, Any]) -> dict[str, Any]:
    """Drop a contact template row's own `IsDefault*` flags: they describe
    the template, not the villa it is applied to."""
    return {k: v for k, v in row.items() if not k.startswith("IsDefault")}


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
        "commission_calculation_type": _calc_type(
            _COMMISSION_TYPE_MAP, row.get("CommissionTypeId")
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
        "deposit_calculation_type": _calc_type(
            _DEPOSIT_TYPE_MAP, row.get("PaymentScheduleDepositTypeId")
        ),
        "deposit_amount": _decimal(row.get("PaymentScheduleDepositAmount")),
        "interim_required": (
            bool(row["PaymentScheduleIsInterimRequired"])
            if row.get("PaymentScheduleIsInterimRequired") is not None
            else None
        ),
        "interim_calculation_type": _calc_type(
            _DEPOSIT_TYPE_MAP, row.get("PaymentScheduleInterimTypeId")
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
        "security_deposit_calculation_type": _calc_type(
            _SEC_DEPOSIT_TYPE_MAP, row.get("SecurityDepositAmountTypeId")
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

    def __init__(self, since: str | None = None, reference_date: date | None = None) -> None:
        super().__init__(since)
        # Rate rows ending before this date don't vote on a villa's commission
        # (D7). Defaults to the load day; recorded in DRYRUN_LOG per run.
        self.reference_date = reference_date or date.today()

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        # Fetched before the per-row savepoints, so a missing CPD row or a
        # dead connection aborts the loader instead of erroring every row.
        self._cpd()
        self._rate_finance()
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

    def _rate_finance(self) -> dict[str, RateRowFinance]:
        if not hasattr(self, "_rate_finance_cache"):
            with legacy_cursor() as cursor:
                cursor.execute(rate_row_finance_query(self.reference_date))
                self._rate_finance_cache = rate_row_finance_by_villa(list(rows_as_dicts(cursor)))
            mixed = sorted(
                (
                    v
                    for v, f in self._rate_finance_cache.items()
                    if f.commission_mixed or f.tax_mixed
                ),
                key=int,
            )
            logger.warning(
                "data_migration.finance_rate_rows_mixed",
                reference_date=self.reference_date.isoformat(),
                villas_with_rate_rows=len(self._rate_finance_cache),
                mixed_count=len(mixed),
                mixed_villa_ids=mixed,
            )
        return self._rate_finance_cache

    def _cpd(self) -> dict[str, Any]:
        # The global defaults are read from legacy, not from the loaded
        # PropertyDefaults singleton (operator-editable, skipped under
        # `--since`). One round trip per load; tests seed the cache.
        if not hasattr(self, "_cpd_cache"):
            self._cpd_cache = fetch_config_property_default()
        return self._cpd_cache

    def _apply_contact_defaults(
        self,
        report: LoadReport,
        *,
        exclude_legacy_ids: Collection[str] = frozenset(),
    ) -> None:
        """Fill financeless villas from their owner-contact default template.

        BUG-028: legacy reads a villa with no VillaFinance row as an all-zero
        model, so the CPD `<= 0` rule still fills it — a villa with no owner
        or no template gets that resolution from an empty row (after its
        rate-row majority), never NULL policy columns.

        Only creates rows where none exist, so the per-villa pass is never
        overwritten and re-runs are idempotent (create-only: a template edit
        in legacy after the row is written does NOT propagate — fallback
        rows carry `legacy_id=NULL`, nothing that identifies their
        template). Non-migrated properties (no legacy_id) are out of scope —
        they get rows via `snapshot_defaults`.
        """
        villas = (
            Property.objects.filter(legacy_id__isnull=False, finance__isnull=True)
            .exclude(legacy_id="")
            .exclude(legacy_id__in=exclude_legacy_ids)
        )
        if not villas.exists():
            return
        outcomes = {"applied": 0, "contact_only": 0, "cpd_only": 0}
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
            cpd_only=outcomes["cpd_only"],
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
        owner_legacy_id, owner_pk = owner if owner is not None else (None, None)
        template = self._by_contact().get(owner_legacy_id) if owner_legacy_id else None
        # Owner known but no legacy template: still record the finance contact
        # (the old GroupFinance mirror carried it even without one). With no
        # template the CPD rule resolves an empty row.
        resolved = apply_legacy_finance_defaults(
            apply_rate_row_finance(
                _strip_default_flags(template) if template is not None else {},
                self._rate_finance().get(str(prop.legacy_id)),
                row_is_villas_own=False,
            ),
            self._cpd(),
        )
        defaults = _finance_defaults(resolved)
        defaults["contact_id"] = owner_pk
        PropertyFinance.objects.create(property=prop, **defaults)
        report.created += 1
        if template is not None:
            return "applied"
        return "contact_only" if owner_pk is not None else "cpd_only"

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        # `VillaId` is `int NOT NULL`; the contact-default template rows carry
        # 0. Skip them explicitly — `legacy_id=""` would otherwise match any
        # Property saved with a blank (not NULL) legacy_id and stamp a
        # template Id onto it.
        if not row.get("VillaId"):
            report.skipped += 1
            return
        prop = Property.objects.filter(legacy_id=str(row["VillaId"])).first()
        if prop is None:
            report.skipped += 1
            return
        contact = (
            Person.objects.filter(legacy_id=str(row["ContactId"])).first()
            if row.get("ContactId")
            else None
        )
        # BUG-028 legacy-exact fill order: the CPD `IsDefault*` / `<= 0` rule
        # runs on the raw row first; the owner template below then fills only
        # what the CPD never covers (bank, tax, notes, NULL types).
        # D7: the villa's rate-row majority fills default/zero commission and
        # unset tax before that.
        resolved = apply_rate_row_finance(row, self._rate_finance().get(str(row["VillaId"])))
        defaults = _finance_defaults(apply_legacy_finance_defaults(resolved, self._cpd()))
        # GAP-070 parity: pre-cutover, a NULL/"" field on a villa's own row
        # resolved through the owner-contact default template at read time
        # (GroupFinance + effective()). Reproduce that merge concretely —
        # own value wins unless it is None/"" (0/False are own values).
        template = self._by_contact().get(str(row["ContactId"])) if row.get("ContactId") else None
        if template is not None:
            template_defaults = _finance_defaults(template)
            for field, own in defaults.items():
                paired_amount = _AMOUNT_FOR_TYPE.get(field)
                if paired_amount is not None and defaults[paired_amount] is not None:
                    continue
                fallback = template_defaults.get(field)
                if (own is None or own == "") and fallback not in (None, ""):
                    defaults[field] = fallback
        defaults["contact"] = contact
        # Stamped here, not in `_finance_defaults`: that helper also feeds
        # the fallback path, whose rows must stay NULL (see reconcile_legacy's
        # PropertyFinance check, GAP-107).
        defaults["legacy_id"] = str(row["Id"])

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
        # Per-line currency (GAP-014, legacy VillaQuotationDetails.CurrencyId).
        currency = legacy_currency_for(row, prop)
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
