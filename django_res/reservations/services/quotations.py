"""QuotationService — build a Quotation+lines from an Enquiry.

Quotations never place availability holds automatically — quoting is the
soft part of the sales process (legacy parity). Holds are a deliberate
operator action via `hold_line` / `release_line_hold`.
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import TYPE_CHECKING, Any, TypedDict

import structlog
from django.db import transaction
from rest_framework.exceptions import ValidationError

from pricing.models import Currency
from pricing.services import PricingEngine
from pricing.services.currency import quantise_money, resolve_property_currency
from reservations.enums import BookingHoldReason, EnquirySource, EnquiryStatus
from reservations.models.quotation import Quotation, QuotationLine
from reservations.services.holds import HoldService
from reservations.services.person_sync import person_for_guest

if TYPE_CHECKING:
    from reservations.models.booking import BookingHold
    from reservations.models.enquiry import Enquiry

logger = structlog.get_logger(__name__)


class QuotationLineInput(TypedDict, total=False):
    property: Any
    date_from: date_type
    date_to: date_type
    adults: int
    children: int
    notes: str
    is_manual: bool
    total: Decimal
    currency: Any


class QuotationService:
    """Orchestrate quotation creation off the back of an enquiry."""

    @classmethod
    def price_line(
        cls,
        quotation: Quotation,
        line: QuotationLine,
        *,
        currency: Currency | None = None,
    ) -> QuotationLine:
        """Run the PricingEngine for a line and persist its total + snapshot.

        The single source of truth for line pricing — both the
        enquiry-driven `create_from_enquiry` path and the API
        `QuotationLineViewSet` path funnel through here so a line is priced
        identically however it's created. Manual-override lines must not be
        passed in; the caller decides whether to reprice.

        `currency=None` prices in the rate plan's own currency (GAP-014) —
        right for first pricing. Repricing an existing line must PIN its
        currency: the engine then exact-matches it and a plan-currency switch
        fails loud (`NoRateAvailable`) instead of silently re-denominating a
        line the guest may already hold (mirrors FG-001's `modify_dates`).
        """
        party = line.adults + line.children
        quote = PricingEngine.quote(
            property=line.property,
            date_from=line.date_from,
            date_to=line.date_to,
            party=party,
            currency=currency,
        )
        line.currency = Currency.objects.get(code=quote.currency_code)
        gross = quantise_money(quote.total, line.currency)
        # Annotate the snapshot so the gross (pre-discount engine figure) and
        # the applied discount survive alongside the engine breakdown — the
        # stored `total` is the net the guest pays.
        snapshot = dict(quote.breakdown)
        snapshot["gross"] = f"{gross:.2f}"
        snapshot["discount"] = f"{line.discount:.2f}"
        line.pricing_snapshot = snapshot
        # Net the operator discount; never let a large discount drive the
        # quoted price negative (mirrors Booking's non-negative money intent).
        line.total = quantise_money(max(gross - line.discount, Decimal("0")), line.currency)
        # The engine may have nudged the arrival forward to the property's
        # changeover day (GAP-007). Persist the dates it actually priced so the
        # line, its hold, and any downstream booking stay coherent with the
        # snapshot; `changeover_shifted_from` in the snapshot carries the
        # original arrival for the "we moved your dates" note.
        line.date_from = quote.date_from
        line.date_to = quote.date_to
        line.save(
            update_fields=[
                "pricing_snapshot",
                "total",
                "currency",
                "date_from",
                "date_to",
                "updated_at",
            ]
        )
        return line

    @classmethod
    def seed_inclusions(cls, line: QuotationLine) -> QuotationLine:
        """Seed a freshly created line's blank `inclusions` from the winning
        plan's inclusion text (carried on the pricing snapshot).

        Legacy parity: ResService.cs:1241 seeded line inclusions from the
        season at item creation. Creation-time ONLY — never on reprice — so an
        operator who deliberately blanks the field doesn't have text
        resurrected by a date/party edit. Both creation paths (`add_line` and
        `create_from_enquiry`) call this after the initial `price_line`.
        """
        if line.inclusions:
            return line
        seeded = line.pricing_snapshot.get("inclusion") or ""
        if seeded:
            line.inclusions = seeded
            line.save(update_fields=["inclusions", "updated_at"])
        return line

    @classmethod
    @transaction.atomic
    def hold_line(cls, line: QuotationLine, *, actor: Any = None) -> BookingHold:
        """Place the operator-requested hold backing a quotation line.

        Holds are a deliberate, significant operator action — quotes alone
        never block availability (legacy parity: quoting is the soft part of
        the sales process). Idempotent: an already-held line returns its live
        hold. Expiry is the property's effective `hold_duration_hours`
        (`HoldService.place` default), deliberately decoupled from the
        quotation's `expires_at`. Raises `HoldUnavailable` if the dates
        collide with another live hold.
        """
        existing = line.holds.filter(released_at__isnull=True).first()
        if existing is not None:
            return existing
        hold = HoldService.place(
            property=line.property,
            date_from=line.date_from,
            date_to=line.date_to,
            reason=BookingHoldReason.QUOTATION_OPEN.value,
            quotation=line.quotation,
            quotation_line=line,
        )
        logger.info(
            "quotation_line.hold_placed",
            quotation_id=line.quotation_id,
            quotation_line_id=line.pk,
            hold_id=hold.pk,
            property_id=line.property_id,
            expires_at=hold.expires_at.isoformat() if hold.expires_at else None,
            actor_id=getattr(actor, "pk", None),
        )
        return hold

    @classmethod
    @transaction.atomic
    def release_line_hold(cls, line: QuotationLine, *, actor: Any = None) -> int:
        """Release a line's live hold(s); no-op (0) when none. Returns count."""
        released = HoldService.release_for_line(line)
        if released:
            logger.info(
                "quotation_line.hold_released",
                quotation_id=line.quotation_id,
                quotation_line_id=line.pk,
                released_count=released,
                actor_id=getattr(actor, "pk", None),
            )
        return released

    @classmethod
    @transaction.atomic
    def move_line_hold(cls, line: QuotationLine) -> BookingHold | None:
        """Relocate a held line's live hold to the line's current dates.

        The edit-path counterpart to `hold_line`: a date edit moves an
        existing hold (preserving its operator-set expiry) but NEVER places
        one — an un-held line stays un-held. Returns the moved hold, or None
        when the line has no live hold. Raises `HoldUnavailable` if the new
        dates collide with another live hold.
        """
        existing = line.holds.filter(released_at__isnull=True).first()
        if existing is None:
            return None
        return HoldService.move(
            existing,
            date_from=line.date_from,
            date_to=line.date_to,
        )

    @classmethod
    def default_line_currency(cls, property: Any) -> Currency:
        """Canonical line-currency default (GAP-014), or a 400."""
        currency = resolve_property_currency(property)
        if currency is None:
            raise ValidationError(
                {
                    "currency": [
                        "No currency resolvable for this property — supply one "
                        "or configure a rate plan / settings currency."
                    ]
                }
            )
        return currency

    @classmethod
    def add_line(cls, quotation: Quotation, data: dict[str, Any]) -> QuotationLine:
        """Create one line correctly: default currency, then price it.

        The single source of truth for API-shaped line creation —
        `QuotationLineViewSet.perform_create` and `create_with_lines` both
        funnel through here. `data` is `QuotationLineWriteSerializer`
        validated_data. No hold is placed — holds are a separate manual
        operator action (`hold_line`).

        An explicitly supplied currency is pinned: the engine exact-matches it
        (loud `NoRateAvailable` on a plan-currency mismatch); a defaulted one
        lets the plan's own currency win. Returns the priced row (re-read
        under `select_for_update`, per FG-006) so callers see the
        server-computed total / snapshot / shifted dates.
        """
        with transaction.atomic():
            supplied_currency = data.get("currency")
            create_kwargs = {**data, "quotation": quotation}
            if supplied_currency is None:
                create_kwargs["currency"] = cls.default_line_currency(data["property"])
            line = QuotationLine.objects.create(**create_kwargs)
            if not line.is_manual:
                locked = (
                    QuotationLine.objects.select_for_update()
                    .select_related("property", "quotation")
                    .get(pk=line.pk)
                )
                cls.price_line(quotation, locked, currency=supplied_currency)
                cls.seed_inclusions(locked)
                line = locked
            return line

    @classmethod
    @transaction.atomic
    def create_with_lines(
        cls,
        header: dict[str, Any],
        lines: list[dict[str, Any]],
    ) -> Quotation:
        """Atomic `POST /quotations` body: header + nested lines, all-or-nothing.

        The builder's save path. Unlike `create_from_enquiry` this never
        advances the enquiry — saving a draft is not sending; that transition
        belongs to `:send` / `:mark-manually-sent`. An agent-direct header
        (no enquiry) mints the minimal AGENT_PORTAL enquiry inside the same
        transaction, so a failed line rolls it back too.
        """
        # GAP-045 D3-1: `person` is the authoritative customer FK. The SPA sends
        # it directly (off `/contacts`); a transitional `guest` input still
        # derives the same Person via the mirror. Drop BOTH raw keys so neither
        # the legacy leg nor a duplicate `person=` kwarg reaches `create`.
        person = header.pop("person", None)
        guest = header.pop("guest", None)
        if person is None and guest is not None:
            person = person_for_guest(guest)
        if header.get("enquiry") is None:
            header = {
                **header,
                "enquiry": cls.minimal_enquiry_for(person, agent=header.get("agent")),
            }
        quotation = Quotation.objects.create(**header, person=person)
        for line_data in lines:
            cls.add_line(quotation, line_data)
        return quotation

    @classmethod
    @transaction.atomic
    def create_from_enquiry(
        cls,
        enquiry: Enquiry,
        lines: list[dict[str, Any]],
        *,
        terms_version: Any,
        expires_at: Any,
        guest: Any | None = None,
        agent: Any | None = None,
        actor: Any = None,
    ) -> Quotation:
        """Build Quotation + lines, run PricingEngine per line. No holds.

        Currency is per line (GAP-014): priced lines get the engine result's
        currency; a manual line takes the supplied one, defaulting via the
        canonical `resolve_property_currency` chain.
        """
        # A lost/converted enquiry is closed to new quotes — the workspace
        # suppresses the builder for these, but guard the service too so the
        # API rejects a direct POST (the old UI disabled the action via `isFinal`).
        if enquiry.status in (EnquiryStatus.LOST.value, EnquiryStatus.CONVERTED.value):
            raise ValidationError("Cannot quote a lost or converted enquiry.")

        resolved_guest = guest if guest is not None else enquiry.guest
        if resolved_guest is None:
            raise ValueError(
                "Quotation requires a Guest; pass `guest=` or capture one on the enquiry first."
            )

        quotation = Quotation.objects.create(
            enquiry=enquiry,
            # GAP-045 Unit 3d-C: persist only the unified Person FK (resolved from
            # the supplied/enquiry guest). Reading the guest INPUT here is
            # transitional — 3d-E removes the `enquiry.guest` leg entirely.
            person=person_for_guest(resolved_guest),
            agent=agent,
            terms_version=terms_version,
            expires_at=expires_at,
        )

        for line_input in lines:
            adults = int(line_input.get("adults", enquiry.adults))
            children = int(line_input.get("children", enquiry.children))
            is_manual = bool(line_input.get("is_manual", False))
            supplied_currency = line_input.get("currency")
            currency = supplied_currency or resolve_property_currency(line_input["property"])
            if currency is None:
                raise ValidationError(
                    "No currency resolvable for this property — configure a rate "
                    "plan, a settings currency, or seed EUR."
                )
            create_kwargs: dict[str, Any] = {
                "quotation": quotation,
                "property": line_input["property"],
                "date_from": line_input["date_from"],
                "date_to": line_input["date_to"],
                "adults": adults,
                "children": children,
                "currency": currency,
                "is_manual": is_manual,
                "notes": line_input.get("notes", ""),
            }
            # A manual line carries the operator-supplied total (or the model
            # default if none given); the engine must not stamp it.
            if is_manual and "total" in line_input:
                create_kwargs["total"] = line_input["total"]
            line = QuotationLine.objects.create(**create_kwargs)
            # Only non-manual lines are priced — mirror the API `_reprice`
            # guard so a manual line keeps its operator total either way.
            # An explicitly supplied currency is pinned (exact match, loud
            # failure); a defaulted one lets the plan's currency win.
            if not is_manual:
                cls.price_line(quotation, line, currency=supplied_currency)
                cls.seed_inclusions(line)

        # Move the enquiry forward. The service-layer path is the in-app
        # SMTP flow — manual-mark goes via the dedicated endpoint, never
        # through here — so the audit event is stamped accordingly.
        if enquiry.status not in (EnquiryStatus.QUOTED.value, EnquiryStatus.CONVERTED.value):
            from reservations.services.quotation_transmission import SEND_PATH_SMTP

            enquiry.quote_sent(quotation, send_path=SEND_PATH_SMTP, actor=actor)

        return quotation

    @classmethod
    def minimal_enquiry_for(cls, person: Any, *, agent: Any | None = None) -> Enquiry:
        """Auto-create a minimal Enquiry from a Person snapshot.

        The single mechanism behind "every quote has an enquiry" for
        agent-direct quotes that arrive with no enquiry (legacy
        `sp_quotationMaster @EnquireId=0` parity). Tagged via the existing
        `site_source=AGENT_PORTAL` so conversion reporting (per-Enquiry) can
        segment these. No sentinel, no nullable bridge, no forced capture step.

        GAP-045 D3-1: seeds the denormalised contact snapshot from the unified
        Person (name / primary email / primary phone / preferred method) — the
        Guest leg is gone.
        """
        from reservations.models.enquiry import Enquiry

        return Enquiry.objects.create(
            person=person,
            first_name=person.first_name,
            last_name=person.last_name,
            email=person.primary_email() or "",
            phone=person.primary_phone() or "",
            contact_method=person.preferred_method,
            agent=agent,
            site_source=EnquirySource.AGENT_PORTAL.value,
        )

    @classmethod
    @transaction.atomic
    def create_direct(
        cls,
        *,
        guest: Any,
        lines: list[dict[str, Any]],
        terms_version: Any,
        expires_at: Any,
        agent: Any | None = None,
        actor: Any = None,
    ) -> Quotation:
        """Agent-direct quote with no enquiry — auto-create one, then delegate."""
        enquiry = cls.minimal_enquiry_for(person_for_guest(guest), agent=agent)
        return cls.create_from_enquiry(
            enquiry,
            lines,
            terms_version=terms_version,
            expires_at=expires_at,
            guest=guest,
            agent=agent,
            actor=actor,
        )
