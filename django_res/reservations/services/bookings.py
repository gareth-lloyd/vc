"""BookingService — create a Booking off an accepted QuotationLine."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog
from django.db import transaction
from django.utils import timezone

from core.exceptions import TerminalBookingExists
from reservations.enums import TERMINAL_BOOKING_STATUSES, BookingGuestRole, PaymentMethod
from reservations.models.booking import Booking
from reservations.models.booking_guest import BookingGuest
from reservations.models.quotation import QuotationLine
from reservations.services.holds import HoldService
from reservations.services.owner_finance import owner_money_from_snapshot

if TYPE_CHECKING:
    from pricing.services import Quote

logger = structlog.get_logger(__name__)


class BookingService:
    """Create + initialise Booking rows."""

    @classmethod
    @transaction.atomic
    def create_from_quotation_line(
        cls,
        quotation_line: QuotationLine,
        terms_version: Any,
        payment_method: str = PaymentMethod.CARD.value,
        *,
        agent: Any = None,
        actor: Any = None,
    ) -> Booking:
        """Copy the line's pricing snapshot, build a Booking, release holds.

        Idempotent on `quotation_line`: a `QuotationLine` represents a
        single guest commitment, so a retry from the same accept-quotation
        webhook (or a double-clicked staff UI) returns the existing
        Booking instead of opening a second one. The hold release and
        initial transition are skipped in that case — both ran on the
        first call.

        The booking is created in DRAFT and immediately driven through
        either `booking.auto_accept()` or `booking.submit()` so the
        `booking_transitioned` signal fires for the initial step and a
        single `BookingEvent` row is written by `Booking._transition`.
        """
        existing = Booking.objects.filter(quotation_line=quotation_line).first()
        if existing is not None:
            # The retry contract only covers a live booking. Serving a
            # CANCELLED/EXPIRED/DECLINED one back as a fresh success would
            # resurrect a closed commitment — re-book via a new quotation.
            if existing.status in TERMINAL_BOOKING_STATUSES:
                raise TerminalBookingExists(
                    f"Booking {existing.reference} for this quotation line is "
                    f"{existing.status}; re-book via a new quotation."
                )
            return existing

        quotation = quotation_line.quotation
        property_ = quotation_line.property
        snapshot = dict(quotation_line.pricing_snapshot or {})

        # Quoting no longer auto-holds its dates, so another party may have
        # held the villa between quote and accept. Refuse to book over a
        # foreign live hold; the quotation's own line holds are excluded so
        # they never block their own conversion. Booking-vs-booking overlap
        # is still enforced by the Booking EXCLUDE constraint.
        HoldService.assert_no_foreign_hold(
            property=property_,
            date_from=quotation_line.date_from,
            date_to=quotation_line.date_to,
            quotation=quotation,
        )

        # The booking inherits the line's dates verbatim. Any changeover shift
        # already happened at pricing time and was persisted onto the line
        # (GAP-007), so there is nothing to re-validate or re-align here.
        requires_pre_approval = cls._requires_pre_approval(property_)
        balance_due_at = property_.balance_due_at(quotation_line.date_from)
        # BUG-020: the line total (net of the operator discount, or the manual
        # override figure) is the authority for what the guest pays. The
        # snapshot's `total` is the engine's pre-operator-discount figure —
        # net it here so every downstream reader of the booking snapshot
        # (owner money, payment schedule, Zoho financials) sees one number.
        total = cls._decimal(quotation_line.total)
        cls._net_snapshot_to_line_total(snapshot, total, quotation_line=quotation_line)

        # GAP-045 Unit 3d-A/C: `Quotation.person` is the authoritative, NOT-NULL
        # customer FK — read it directly and set it on both the Booking and its
        # LEAD BookingGuest below. The legacy `guest` leg is no longer persisted.
        person = quotation.person
        booking = Booking.objects.create(
            quotation_line=quotation_line,
            person=person,
            property=property_,
            date_from=quotation_line.date_from,
            date_to=quotation_line.date_to,
            adults=quotation_line.adults,
            children=quotation_line.children,
            # The line's currency, not a header one — the booking prices in
            # whatever the accepted option was priced in (GAP-014 / FG-001).
            currency=quotation_line.currency,
            pricing_snapshot=snapshot,
            rental_price=cls._decimal(snapshot.get("rate_subtotal", 0)),
            balance_due=total,
            balance_due_at=balance_due_at,
            agent=agent,
            terms_version=terms_version,
            terms_accepted_at=timezone.now(),
            payment_method=payment_method,
        )

        # Birth the LEAD `BookingGuest` row alongside the Booking. The
        # quotation's customer is the lead by definition — that is who accepted
        # the quote. Creating the row inside the same `transaction.atomic()`
        # keeps Booking + LEAD an indivisible pair: if either insert fails
        # both roll back, preserving the "every Booking has exactly one LEAD"
        # invariant the partial-unique constraint and pre_delete guard rely
        # on. `Booking.person` is already set above; the post_save sync signal
        # is idempotent (it excludes rows that already match), so the second
        # write is a no-op.
        BookingGuest.objects.create(
            booking=booking,
            person=person,
            role=BookingGuestRole.LEAD.value,
        )

        # Payments are scheduled out-of-band: the `auto_accept`/`submit`
        # transition below fires `booking_transitioned`, which a payments-side
        # receiver consumes to call `PaymentScheduler.create_for_booking` once
        # the booking reaches AWAITING_DEPOSIT. `reservations` must not import
        # `payments` directly (it sits below it in the import spine), so the
        # signal is the seam — see `payments/signals.py`.

        # Release competing holds for this property/date_range that we don't own.
        HoldService.release_for_quotation(quotation)

        transition_meta = {"quotation_line_id": quotation_line.pk}
        if requires_pre_approval:
            booking.submit(
                actor=actor,
                reason="Created from quotation line",
                meta=transition_meta,
            )
        else:
            booking.auto_accept(
                actor=actor,
                reason="Created from quotation line",
                meta=transition_meta,
            )

        logger.info(
            "booking.created",
            booking_id=booking.pk,
            reference=booking.reference,
            property_id=property_.pk,
            quotation_line_id=quotation_line.pk,
            requires_pre_approval=requires_pre_approval,
            booking_status=booking.status,
        )
        return booking

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _decimal(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        return Decimal(str(value)).quantize(Decimal("0.01"))

    @classmethod
    def reprice_snapshot(
        cls, quote: Quote, *, quotation_line: QuotationLine
    ) -> tuple[dict[str, Any], Decimal]:
        """Net a fresh engine quote for a booking being repriced.

        BUG-025: `Booking.modify_dates` / `modify_guests` re-run the engine
        and used to write `quote.breakdown` / `quote.total` verbatim, which
        dropped the operator discount netted in at conversion and billed the
        guest the discount back. This mirrors `price_line`
        (`services/quotations.py`): the engine figure is kept as `gross`, the
        line's `discount` is re-applied as the same absolute amount, floored
        at 0 (product decision 2026-09-17, provisional pending Q-028 #8), and
        the result is netted through `_net_snapshot_to_line_total` so the
        booking snapshot keeps the BUG-020 shape.

        Returns the netted snapshot (a copy — the engine's dict is untouched)
        and the guest total to write to `balance_due`.
        """
        snapshot = dict(quote.breakdown)
        gross = cls._decimal(quote.total)
        total = max(gross - quotation_line.discount, Decimal("0")).quantize(Decimal("0.01"))
        snapshot["gross"] = f"{gross:.2f}"
        cls._net_snapshot_to_line_total(snapshot, total, quotation_line=quotation_line)
        return snapshot, total

    @classmethod
    def _net_snapshot_to_line_total(
        cls, snapshot: dict[str, Any], total: Decimal, *, quotation_line: QuotationLine
    ) -> None:
        """Rewrite the engine snapshot's money so `total` is what the guest pays.

        BUG-020 / FG-018: `QuotationLine.pricing_snapshot["total"]` is the
        engine figure *before* the operator's line discount (kept beside it as
        `operator_discount`, `gross`), whereas `line.total` is the quoted
        price. On the booking snapshot the only consistent meaning of `total`
        is "net of everything", so it is overwritten with the line total and
        `net_to_owner` re-derived from it.

        The owner absorbs the operator discount (product decision 2026-09-02):
        `commission` and `tax` stay as the engine computed and
        `net_to_owner = total - commission - tax`. When the discount exceeds
        the owner's net that identity would go negative; rather than leave a
        commission larger than the guest pays (every reader — component
        splits, Zoho financials — assumes `total - commission - tax = net`),
        `tax` is clipped to `total`, `commission` to what remains, and
        `net_to_owner` floors at 0. A structlog warning
        (`booking.owner_net_floored`) records the clamp.

        Parsing goes through `owner_money_from_snapshot` so the same
        quantise/NaN rules apply as on the read side. If the snapshot's
        money does not parse, `total` is still rewritten and the stale
        engine `net_to_owner` dropped so no half-netted pair survives.

        Deliberately untouched: `commission_base` and
        `extras_non_commissionable_total` remain the engine's figures (they
        can exceed `total` on a discounted booking) — nothing reads them off
        a booking snapshot, and they document what commission was charged on.
        `rental_price` on the booking row likewise stays the engine
        `rate_subtotal` (accommodation subtotal, not the guest total).

        A manual-override line PATCHed after pricing keeps its stale engine
        snapshot; the same netting applies, using the stale commission/tax,
        and `operator_discount` is re-stamped from the line so the booking
        never shows a discount the operator has since zeroed. Whether
        commission should be charged on an operator-invented price is an
        open product question. An empty snapshot (manual line never priced)
        is left empty.
        """
        if not snapshot:
            return
        money = owner_money_from_snapshot({**snapshot, "total": f"{total:.2f}"})
        snapshot["total"] = f"{total:.2f}"
        snapshot["operator_discount"] = f"{quotation_line.discount:.2f}"
        if money is None:
            snapshot.pop("net_to_owner", None)
            logger.warning(
                "booking.snapshot_money_unparseable",
                quotation_line_id=quotation_line.pk,
                property_id=quotation_line.property_id,
            )
            return
        commission, tax = money["commission"], money["tax"]
        net = total - commission - tax
        if net < 0:
            logger.warning(
                "booking.owner_net_floored",
                quotation_line_id=quotation_line.pk,
                property_id=quotation_line.property_id,
                total=str(total),
                commission=str(commission),
                tax=str(tax),
            )
            tax = min(tax, total)
            commission = max(min(commission, total - tax), Decimal("0"))
            net = Decimal("0")
            snapshot["commission"] = f"{commission:.2f}"
            snapshot["tax"] = f"{tax:.2f}"
        snapshot["net_to_owner"] = f"{net:.2f}"

    @staticmethod
    def _requires_pre_approval(property_: Any) -> bool:
        settings_obj = getattr(property_, "settings", None)
        if settings_obj is None:
            return False
        return bool(settings_obj.bookings_require_pre_approval)
