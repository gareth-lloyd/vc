"""Booking, BookingHold, BookingEvent, BookingNote.

The Booking state machine lives in `06-availability.md`; its edges are
`BOOKING_ALLOWED_TRANSITIONS`. Every transition goes through
`core.transitions` (lock, guard, save, BookingEvent) and then fires the
`booking_transitioned` signal.
"""

from __future__ import annotations

import builtins
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeBoundary, RangeOperators
from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.utils import timezone

from core.exceptions import InvalidTransition, OverlappingBooking
from core.fields import DateRangeFunc
from core.models.base import AuditedModel, TimestampedModel
from core.refs import booking_reference, generate_reference
from core.transitions import transition
from properties.enums import DescriptionSection
from properties.models import PropertyDescription
from reservations.enums import (
    ACTIVE_BOOKING_STATUSES,
    BOOKING_ALLOWED_TRANSITIONS,
    CONFIRMED_BOOKING_STATUSES,
    OVERLAP_BLOCKING_BOOKING_STATUSES,
    TERMINAL_BOOKING_STATUSES,
    BookingHoldReason,
    BookingNoteKind,
    BookingNoteVisibility,
    BookingStatus,
    EnquirySource,
    EventSource,
    PaymentMethod,
)

if TYPE_CHECKING:
    from datetime import date as date_type

    from pricing.services import Quote


_OVERLAP_CONSTRAINT_NAME = "booking_no_overlap_blocking"

# Shared with HoldService._translate_overlap_violation, which maps this
# constraint's IntegrityError to HoldUnavailable.
HOLD_OVERLAP_CONSTRAINT_NAME = "bookinghold_no_overlap_live"


def _is_overlap_violation(exc: IntegrityError) -> bool:
    """True iff `exc` came from the booking_no_overlap_blocking constraint.

    Prefers psycopg's `Diagnostic.constraint_name` (robust to message
    formatting, locale, deferred constraints). Falls back to a substring
    check on the rendered message for non-psycopg backends.
    """
    diag = getattr(getattr(exc, "__cause__", None), "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name == _OVERLAP_CONSTRAINT_NAME:
        return True
    return _OVERLAP_CONSTRAINT_NAME in str(exc)


class BookingQuerySet(models.QuerySet["Booking"]):
    def occupying(
        self,
        *,
        date_from: date_type,
        date_to: date_type,
        property: Any = None,
    ) -> BookingQuerySet:
        """Bookings that occupy `[date_from, date_to)` for availability reads.

        The single source of truth for "is this villa taken on these dates?",
        shared by the availability calendar (`AvailabilityService`) and
        catalogue search (`properties` filters) so the two can never drift on
        which bookings occupy a range. Pass `property` to scope to one villa;
        omit it for a cross-property sweep.

        A booking occupies the range unless it has reached a *terminal* state
        (`TERMINAL_BOOKING_STATUSES`). This deliberately includes `DRAFT`:
        a service-created booking is only ever `DRAFT` transiently inside its
        own creation transaction (never an observable resting state), but the
        legacy migration *rests* imported reservations in `DRAFT`
        (`data_migration.loaders.bookings`) to bypass the
        `booking_no_overlap_blocking` EXCLUDE constraint, which lets historical
        overlapping rows coexist. Those resting DRAFT rows are real occupancy
        and must show as taken.

        Note the deliberate asymmetry with `OVERLAP_BLOCKING_BOOKING_STATUSES`
        (the narrower set the DB constraint enforces on *writes*, which omits
        `DRAFT`): a migrated DRAFT booking *occupies* the calendar yet does not
        *block* a new insert at the DB level. That gap is what lets the
        migration load the legacy overlaps in the first place.
        """
        qs = self.exclude(status__in=TERMINAL_BOOKING_STATUSES).filter(
            date_from__lt=date_to,
            date_to__gt=date_from,
        )
        if property is not None:
            qs = qs.filter(property=property)
        return qs


def live_house_rules(property_id: int) -> str:
    """The property's current HOUSE_RULES body ("" when none/blank) — GAP-094.

    Whitespace-only bodies (a cleared editor) count as "no rules".
    """
    body = (
        PropertyDescription.objects.filter(
            property_id=property_id, section=DescriptionSection.HOUSE_RULES
        )
        .values_list("body", flat=True)
        .first()
        or ""
    )
    return body.strip()


def house_rules_stamp(property_id: int) -> dict[str, Any]:
    """The field values a confirming write stamps for GAP-094 house rules.

    One place for the invariant "no body → no timestamp": the `_transition`
    path (`Booking._house_rules_stamp`) and `make_occupying_booking` (which inserts
    straight into AWAITING_DEPOSIT) both go through here, so a blank
    `house_rules_snapshot` never carries a `house_rules_snapshot_at`.
    """
    body = live_house_rules(property_id)
    return {
        "house_rules_snapshot": body,
        "house_rules_snapshot_at": timezone.now() if body else None,
    }


class Booking(AuditedModel):
    """The reservation. Locked to a QuotationLine pricing snapshot at creation."""

    objects = BookingQuerySet.as_manager()

    reference = models.CharField(max_length=32, unique=True)
    quotation_line = models.ForeignKey(
        "reservations.QuotationLine",
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    # GAP-045: `person` is the authoritative customer FK.
    person = models.ForeignKey(
        "accounts.Person",
        on_delete=models.PROTECT,
        related_name="bookings_as_customer",
    )
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    date_from = models.DateField()
    date_to = models.DateField()
    adults = models.PositiveSmallIntegerField()
    children = models.PositiveSmallIntegerField(default=0)
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        related_name="+",
    )

    pricing_snapshot = models.JSONField(default=dict)
    rental_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    balance_due_at = models.DateField(null=True, blank=True)

    # GAP-087: per-booking deposit override. Non-null pins the deposit to this
    # exact figure (e.g. net of a cancellation carry-over credit) instead of the
    # property's payment-schedule policy; null follows policy. Honoured by
    # `PaymentScheduler` at both create and resync — see `set_deposit_override`.
    deposit_override_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    status = models.CharField(
        max_length=32,
        choices=BookingStatus.choices,
        default=BookingStatus.DRAFT,
    )

    agent = models.ForeignKey(
        "accounts.Person",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bookings_as_agent",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_bookings",
    )
    site_source = models.CharField(
        max_length=16,
        choices=EnquirySource.choices,
        default=EnquirySource.MAIN_WEBSITE,
    )

    terms_version = models.ForeignKey(
        "reservations.TermsVersion",
        on_delete=models.PROTECT,
        related_name="+",
    )
    terms_accepted_at = models.DateTimeField()
    # GAP-094: the property's HOUSE_RULES text as it stood when the booking
    # was confirmed (transition into AWAITING_DEPOSIT — the moment the contract
    # is issued). The contract renders this, never the live section, so later
    # property edits cannot rewrite an issued contract. Stamped once by the
    # two confirming transitions via `_house_rules_stamp`; "" doubles as
    # "no rules" and "not yet stamped" — there is no re-entry path today.
    house_rules_snapshot = models.TextField(blank=True, default="")
    # When `house_rules_snapshot` was stamped. Null with a non-empty body
    # means the body was *reconstructed* by the `0010` backfill from the
    # property's then-current rules — not what the guest agreed at
    # confirmation — and the contract says so (`house_rules_reconstructed`).
    house_rules_snapshot_at = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(
        max_length=16,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CARD,
    )

    cancel_reason = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)

    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["property", "status", "date_from"]),
            models.Index(fields=["status", "balance_due_at"]),
            models.Index(fields=["reference"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(date_from__lt=models.F("date_to")),
                name="booking_date_from_lt_date_to",
            ),
            models.CheckConstraint(
                condition=Q(cancelled_at__isnull=True) | Q(status=BookingStatus.CANCELLED.value),
                name="booking_cancelled_at_implies_cancelled_status",
            ),
            models.CheckConstraint(
                condition=Q(cancelled_at__isnull=False) | ~Q(status=BookingStatus.CANCELLED.value),
                name="booking_cancelled_status_requires_cancelled_at",
            ),
            models.CheckConstraint(
                condition=Q(archived_at__isnull=True) | Q(status__in=TERMINAL_BOOKING_STATUSES),
                name="booking_archived_at_requires_terminal_status",
            ),
            models.CheckConstraint(
                condition=Q(deposit_override_amount__isnull=True)
                | Q(deposit_override_amount__gte=0),
                name="booking_deposit_override_amount_non_negative",
            ),
            # A QuotationLine is a single guest commitment — exactly one
            # Booking. Backstops the service's `filter(...).first()`
            # idempotency pre-check, which is not race-proof on its own.
            models.UniqueConstraint(
                fields=["quotation_line"],
                name="booking_one_per_quotation_line",
            ),
            # Half-open '[)' bounds: date_to is checkout day, so a same-day
            # back-to-back turnover is legal. Only blocking-state bookings
            # hard-block dates at the DB layer (DRAFT rows still *occupy* the
            # calendar — see `occupying()`); editing
            # OVERLAP_BLOCKING_BOOKING_STATUSES will (correctly) surface as a
            # constraint diff in makemigrations against the migration's frozen
            # literals. `_is_overlap_violation` keys on this constraint's name.
            ExclusionConstraint(
                name=_OVERLAP_CONSTRAINT_NAME,
                expressions=[
                    ("property", RangeOperators.EQUAL),
                    (
                        DateRangeFunc("date_from", "date_to", RangeBoundary()),
                        RangeOperators.OVERLAPS,
                    ),
                ],
                condition=Q(status__in=OVERLAP_BLOCKING_BOOKING_STATUSES),
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.reference

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.reference:
            self.reference = self._derive_reference()
        super().save(*args, **kwargs)

    def _derive_reference(self) -> str:
        """Carry the booking number forward from its quotation (legacy parity).

        The legacy app rendered a booking as `VC{QuotationNo}` — same digits as
        the quotation's `QVC{QuotationNo}`, prefix swapped. We mirror that: the
        booking reference is derived from `quotation.number`, never an
        independent sequence.

        Two fallbacks: a quotation with no `number` (synthesised/interim legacy
        rows) yields a non-numeric sentinel rather than a bare `VC{int}`; a
        pre-existing collision on the derived reference appends a UUID suffix.
        The collision path is defensive only — the real flow is one quote → one
        booking, so the carry-forward value is unique by construction.
        """
        quotation = self.quotation_line.quotation
        if quotation.number is None:
            return generate_reference("VC-TMP", model=type(self))
        return booking_reference(quotation.number, model=type(self), exclude_pk=self.pk)

    # ------------------------------------------------------------------
    # Transition plumbing
    # ------------------------------------------------------------------
    def _transition(
        self,
        to: str,
        *,
        actor: Any = None,
        source: str = EventSource.USER.value,
        reason: str = "",
        extra_updates: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
        only_from: tuple[str, ...] | None = None,
    ) -> Booking:
        """Move through `BOOKING_ALLOWED_TRANSITIONS`, write a BookingEvent, signal.

        `core.transitions` locks and guards against current DB state, so a
        stale instance (double-click, webhook retry) loses with
        `InvalidTransition` and its in-memory state is restored. The signal
        fires once this method's own transaction block has exited.
        """
        # Local import to avoid the signal module pulling Booking at import time.
        from reservations.signals import booking_transitioned

        def record(from_status: str, to_status: str) -> None:
            BookingEvent.objects.create(
                booking=self,
                from_status=from_status,
                to_status=to_status,
                actor=actor,
                source=source,
                reason=reason,
                meta=meta or {},
            )

        try:
            prev = transition(
                self,
                to,
                table=BOOKING_ALLOWED_TRANSITIONS,
                extra_updates=extra_updates,
                record=record,
                only_from=only_from,
            )
        except IntegrityError as exc:
            if to in OVERLAP_BLOCKING_BOOKING_STATUSES and _is_overlap_violation(exc):
                raise OverlappingBooking(
                    f"Booking {self.reference}: cannot transition to {to!r}; "
                    f"another booking already holds {self.date_from}..{self.date_to} "
                    f"on property {self.property_id}"
                ) from exc
            raise
        booking_transitioned.send(
            sender=Booking,
            booking=self,
            from_status=prev,
            to_status=to,
            actor=actor,
            source=source,
        )
        return self

    def _write_event(
        self,
        *,
        actor: Any = None,
        source: str = EventSource.USER.value,
        reason: str = "",
        meta: dict[str, Any] | None = None,
    ) -> BookingEvent:
        """Write a non-transitional BookingEvent (`from_status == to_status`)."""
        return BookingEvent.objects.create(
            booking=self,
            from_status=self.status,
            to_status=self.status,
            actor=actor,
            source=source,
            reason=reason,
            meta=meta or {},
        )

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------
    def submit(
        self,
        *,
        actor: Any = None,
        reason: str = "",
        meta: dict[str, Any] | None = None,
    ) -> Booking:
        """DRAFT → PENDING_OWNER_APPROVAL."""
        return self._transition(
            BookingStatus.PENDING_OWNER_APPROVAL.value,
            actor=actor,
            source=EventSource.SYSTEM.value,
            reason=reason,
            meta=meta,
        )

    def _house_rules_stamp(self) -> dict[str, Any]:
        """`extra_updates` for a confirming transition (GAP-094).

        Snapshot the live house rules once; an already-stamped booking keeps
        what it has.
        """
        if self.house_rules_snapshot:
            return {}
        return house_rules_stamp(self.property_id)

    def has_been_confirmed(self) -> bool:
        """True when the booking has entered AWAITING_DEPOSIT at some point.

        The one authority for "confirmed" (GAP-094): the document generate
        guard and the detail serializer both call it. Currently-confirmed
        statuses answer without a query; otherwise the transition trail
        decides — every `_transition` writes a `BookingEvent`, so a
        CANCELLED or EXPIRED booking carries proof of the confirmation it
        came through. (The status leg also covers rows imported before that
        trail existed, which `reservations.0010` backfilled on the same two
        legs.)
        """
        if self.status in CONFIRMED_BOOKING_STATUSES:
            return True
        return BookingEvent.objects.filter(
            booking=self, to_status=BookingStatus.AWAITING_DEPOSIT.value
        ).exists()

    # `builtins.property`: the `property` FK shadows the decorator in the
    # class body (same workaround as `Enquiry`).
    @builtins.property
    def house_rules_reconstructed(self) -> bool:
        """True when the snapshot body was backfilled rather than agreed.

        The `0010` backfill wrote bodies with no timestamp; every genuine
        stamp carries one. A blank body is "no rules", not a reconstruction.
        """
        # `.strip()` mirrors the contract context: a whitespace-only body is
        # "no rules" there too, so it must not read as a reconstruction here.
        return bool(self.house_rules_snapshot.strip()) and self.house_rules_snapshot_at is None

    def auto_accept(
        self,
        *,
        actor: Any = None,
        reason: str = "",
        meta: dict[str, Any] | None = None,
    ) -> Booking:
        """DRAFT → AWAITING_DEPOSIT (when property auto-approves bookings)."""
        return self._transition(
            BookingStatus.AWAITING_DEPOSIT.value,
            actor=actor,
            source=EventSource.SYSTEM.value,
            reason=reason,
            meta=meta,
            extra_updates=self._house_rules_stamp(),
            # Owner-approval bookings must go through owner_approve.
            only_from=(BookingStatus.DRAFT.value,),
        )

    def owner_approve(self, *, actor: Any = None, reason: str = "") -> Booking:
        """PENDING_OWNER_APPROVAL → AWAITING_DEPOSIT."""
        return self._transition(
            BookingStatus.AWAITING_DEPOSIT.value,
            actor=actor,
            source=EventSource.OWNER.value,
            reason=reason,
            extra_updates=self._house_rules_stamp(),
            only_from=(BookingStatus.PENDING_OWNER_APPROVAL.value,),
        )

    def owner_decline(self, reason: str, *, actor: Any = None) -> Booking:
        """PENDING_OWNER_APPROVAL → DECLINED."""
        return self._transition(
            BookingStatus.DECLINED.value,
            actor=actor,
            source=EventSource.OWNER.value,
            reason=reason,
        )

    def record_deposit(self, payment: Any = None, *, actor: Any = None) -> Booking:
        """AWAITING_DEPOSIT → DEPOSIT_PAID."""
        return self._transition(
            BookingStatus.DEPOSIT_PAID.value,
            actor=actor,
            source=EventSource.WEBHOOK.value,
            meta={"payment_id": getattr(payment, "pk", None)},
        )

    def skip_deposit(self, *, actor: Any = None, reason: str = "deposit_not_required") -> Booking:
        """AWAITING_DEPOSIT → DEPOSIT_PAID (no deposit wanted, schedule advance)."""
        return self._transition(
            BookingStatus.DEPOSIT_PAID.value,
            actor=actor,
            source=EventSource.SYSTEM.value,
            reason=reason,
        )

    def arm_balance(self, *, actor: Any = None) -> Booking:
        """DEPOSIT_PAID → AWAITING_BALANCE (beat task)."""
        return self._transition(
            BookingStatus.AWAITING_BALANCE.value,
            actor=actor,
            source=EventSource.SYSTEM.value,
        )

    def record_balance(self, payment: Any = None, *, actor: Any = None) -> Booking:
        """AWAITING_BALANCE / DEPOSIT_PAID → BALANCE_PAID."""
        return self._transition(
            BookingStatus.BALANCE_PAID.value,
            actor=actor,
            source=EventSource.WEBHOOK.value,
            meta={"payment_id": getattr(payment, "pk", None)},
        )

    def check_in(self, *, actor: Any = None) -> Booking:
        """BALANCE_PAID → CHECKED_IN."""
        return self._transition(
            BookingStatus.CHECKED_IN.value,
            actor=actor,
        )

    def check_out(self, *, actor: Any = None) -> Booking:
        """CHECKED_IN → CHECKED_OUT.

        Same method whether called by ops or by the auto-completion beat
        task — both converge on `CHECKED_OUT`.
        """
        return self._transition(
            BookingStatus.CHECKED_OUT.value,
            actor=actor,
            source=EventSource.SYSTEM.value,
        )

    def cancel(self, reason: str, *, actor: Any = None) -> Booking:
        """Any non-terminal → CANCELLED."""
        return self._transition(
            BookingStatus.CANCELLED.value,
            actor=actor,
            reason=reason,
            extra_updates={"cancelled_at": timezone.now(), "cancel_reason": reason},
        )

    def expire(self, *, actor: Any = None) -> Booking:
        """AWAITING_DEPOSIT → EXPIRED (beat task; deposit window passed)."""
        return self._transition(
            BookingStatus.EXPIRED.value,
            actor=actor,
            source=EventSource.SYSTEM.value,
        )

    # ------------------------------------------------------------------
    # Non-transitional mutations
    # ------------------------------------------------------------------
    def _modify_allowed_states(self) -> tuple[str, ...]:
        return (
            BookingStatus.AWAITING_DEPOSIT.value,
            BookingStatus.DEPOSIT_PAID.value,
            BookingStatus.AWAITING_BALANCE.value,
            BookingStatus.BALANCE_PAID.value,
        )

    def _lock_for_update(self) -> None:
        """Take a row lock on this booking and reload its fields.

        `modify_dates` / `modify_guests` recompute pricing from the booking's
        own fields, so two concurrent calls can lost-update each other under
        Postgres' default `READ COMMITTED` (both read the old fields, both
        write — the later commit silently clobbers the earlier). Taking
        `SELECT … FOR UPDATE` on entry serialises the second caller behind the
        first; the reload makes `self` reflect the freshly-committed state
        before we re-price. One query both locks and refreshes (the locking
        select returns the fresh row). Must be called inside the method's
        `atomic` block.
        """
        self.refresh_from_db(from_queryset=Booking.objects.select_for_update())

    def _rerun_pricing(
        self,
        *,
        date_from: date_type,
        date_to: date_type,
        adults: int,
        children: int,
    ) -> Quote:
        """Re-run the PricingEngine for a candidate stay shape."""
        from pricing.services import PricingEngine

        party = adults + children
        # A booking is a contract, not an inquiry: never re-price it onto a
        # projected guide rate. If the new dates fall in a year with no confirmed
        # RatePlan, this raises NoRateAvailable and the modify is rejected rather
        # than silently overwriting balance_due with an unconfirmed figure.
        return PricingEngine.quote(
            property=self.property,
            date_from=date_from,
            date_to=date_to,
            party=party,
            currency=self.currency,
            allow_projection=False,
        )

    def _resync_payment_schedule(self) -> None:
        """Tell payments the booking total moved so it resizes the schedule.

        Legacy regenerated the deposit/balance schedule on every modify. We
        fire `booking_total_changed` — the same signal a charge-item write
        sends — rather than calling the scheduler directly, because the import
        spine forbids reservations → payments. The receiver runs
        `PaymentScheduler.resync_for_booking` inside this method's atomic
        block, so the re-priced booking and the resized rows commit together
        (and the resync is a no-op until a schedule exists).
        """
        # Local import to avoid the signal module pulling Booking at import time.
        from reservations.signals import booking_total_changed

        booking_total_changed.send(sender=Booking, booking=self)

    @transaction.atomic
    def modify_dates(
        self,
        date_from: date_type,
        date_to: date_type,
        *,
        actor: Any = None,
        reason: str = "",
    ) -> Booking:
        """Re-run pricing for new dates; preserves `status`."""
        self._lock_for_update()
        if self.status not in self._modify_allowed_states():
            raise InvalidTransition(
                self.status,
                self.status,
                allowed=list(self._modify_allowed_states()),
            )
        snapshot = {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "pricing_snapshot": self.pricing_snapshot,
            "rental_price": self.rental_price,
            "balance_due": self.balance_due,
        }
        old_from = self.date_from
        old_to = self.date_to
        old_snapshot = self.pricing_snapshot
        quote = self._rerun_pricing(
            date_from=date_from,
            date_to=date_to,
            adults=self.adults,
            children=self.children,
        )
        # BUG-025: re-net the engine figure against the line's operator
        # discount, as at conversion — never write the raw quote.
        from reservations.services.bookings import BookingService

        self.date_from = date_from
        self.date_to = date_to
        self.pricing_snapshot, self.balance_due = BookingService.reprice_snapshot(
            quote, quotation_line=self.quotation_line
        )
        self.rental_price = quote.rate_subtotal
        try:
            self.save(
                update_fields=[
                    "date_from",
                    "date_to",
                    "pricing_snapshot",
                    "rental_price",
                    "balance_due",
                    "updated_at",
                ]
            )
        except IntegrityError as exc:
            for field, value in snapshot.items():
                setattr(self, field, value)
            if _is_overlap_violation(exc):
                raise OverlappingBooking(
                    f"Booking {self.reference}: cannot move to "
                    f"{date_from}..{date_to}; another booking already holds those "
                    f"dates on property {self.property_id}"
                ) from exc
            raise
        self._write_event(
            actor=actor,
            reason=reason,
            meta={
                "from": [old_from.isoformat(), old_to.isoformat()],
                "to": [date_from.isoformat(), date_to.isoformat()],
                "from_snapshot": old_snapshot,
                "to_snapshot": self.pricing_snapshot,
            },
        )
        self._resync_payment_schedule()
        return self

    @transaction.atomic
    def modify_guests(
        self,
        adults: int,
        children: int,
        *,
        actor: Any = None,
        reason: str = "",
    ) -> Booking:
        """Re-run pricing for new party size; preserves `status`."""
        self._lock_for_update()
        allowed = (
            BookingStatus.DRAFT.value,
            BookingStatus.PENDING_OWNER_APPROVAL.value,
            BookingStatus.AWAITING_DEPOSIT.value,
            BookingStatus.DEPOSIT_PAID.value,
            BookingStatus.AWAITING_BALANCE.value,
            BookingStatus.BALANCE_PAID.value,
        )
        if self.status not in allowed:
            raise InvalidTransition(self.status, self.status, allowed=list(allowed))
        old_adults = self.adults
        old_children = self.children
        old_snapshot = self.pricing_snapshot
        quote = self._rerun_pricing(
            date_from=self.date_from,
            date_to=self.date_to,
            adults=adults,
            children=children,
        )
        # BUG-025: re-net against the line's operator discount (see modify_dates).
        from reservations.services.bookings import BookingService

        self.adults = adults
        self.children = children
        self.pricing_snapshot, self.balance_due = BookingService.reprice_snapshot(
            quote, quotation_line=self.quotation_line
        )
        self.rental_price = quote.rate_subtotal
        self.save(
            update_fields=[
                "adults",
                "children",
                "pricing_snapshot",
                "rental_price",
                "balance_due",
                "updated_at",
            ]
        )
        self._write_event(
            actor=actor,
            reason=reason,
            meta={
                "from": {"adults": old_adults, "children": old_children},
                "to": {"adults": adults, "children": children},
                "from_snapshot": old_snapshot,
                "to_snapshot": self.pricing_snapshot,
            },
        )
        self._resync_payment_schedule()
        return self

    def _deposit_override_allowed_states(self) -> tuple[str, ...]:
        """States in which the deposit is still unpaid, so an override is
        meaningful.

        Once the deposit settles (DEPOSIT_PAID onward) the resync never touches
        the committed row — an override there would silently reshape only the
        balance — so it is rejected. DRAFT / PENDING_OWNER_APPROVAL are admitted
        so an override set before approval is applied by `create_for_booking`
        when the schedule is first built.
        """
        return (
            BookingStatus.DRAFT.value,
            BookingStatus.PENDING_OWNER_APPROVAL.value,
            BookingStatus.AWAITING_DEPOSIT.value,
        )

    @transaction.atomic
    def set_deposit_override(
        self,
        amount: Decimal | None,
        *,
        actor: Any = None,
        reason: str = "",
    ) -> Booking:
        """Pin the deposit to `amount` (or clear it with `None`); preserves status.

        GAP-087: the durable home for a hand-tuned deposit (e.g. net of a
        cancellation carry-over credit). `None` reverts to property policy.
        Rejected once the deposit is settled. Fires the same
        `booking_total_changed` resync as the modify endpoints, so the deposit
        re-sizes (or is minted / reverted) in this atomic block. Non-negativity
        is enforced by the DB CHECK; the API layer rejects negatives up front.
        """
        self._lock_for_update()
        allowed = self._deposit_override_allowed_states()
        if self.status not in allowed:
            raise InvalidTransition(self.status, self.status, allowed=list(allowed))
        old = self.deposit_override_amount
        self.deposit_override_amount = amount
        self.save(update_fields=["deposit_override_amount", "updated_at"])
        self._write_event(
            actor=actor,
            reason=reason,
            meta={
                "from": str(old) if old is not None else None,
                "to": str(amount) if amount is not None else None,
            },
        )
        self._resync_payment_schedule()
        return self

    @transaction.atomic
    def archive(self, *, actor: Any = None) -> Booking:
        """Tidy terminal-state booking out of the default list."""
        if self.status not in TERMINAL_BOOKING_STATUSES:
            raise InvalidTransition(
                self.status,
                self.status,
                allowed=list(TERMINAL_BOOKING_STATUSES),
            )
        if self.is_archived:
            return self
        self.is_archived = True
        self.archived_at = timezone.now()
        self.save(update_fields=["is_archived", "archived_at", "updated_at"])
        self._write_event(actor=actor, meta={"archived": True})
        return self

    @transaction.atomic
    def restore(self, *, actor: Any = None) -> Booking:
        """Return an archived booking to the main list."""
        if not self.is_archived:
            return self
        self.is_archived = False
        self.archived_at = None
        self.save(update_fields=["is_archived", "archived_at", "updated_at"])
        self._write_event(actor=actor, meta={"archived": False})
        return self

    def send_confirmation_email(self, *, actor: Any = None) -> Booking:
        """Operator-triggered resend of the confirmation email.

        Writes a `BookingEvent` and fires `booking_confirmation_resend_requested`;
        the comms app handler looks up the latest `booking.confirmation`
        EmailLog for this booking and dispatches via `EmailService.resend`
        (or falls back to a fresh send when no prior log exists).

        The signal fires AFTER the event write commits so the audit trail
        survives any failure inside the comms handler — same pattern as
        `_transition`.
        """
        if self.status in TERMINAL_BOOKING_STATUSES:
            raise InvalidTransition(
                self.status,
                self.status,
                allowed=[s for s in BookingStatus.values if s not in TERMINAL_BOOKING_STATUSES],
            )
        from reservations.signals import booking_confirmation_resend_requested

        self._write_event(actor=actor, meta={"resent_confirmation": True})
        booking_confirmation_resend_requested.send(
            sender=Booking,
            booking=self,
            actor=actor,
        )
        return self


class BookingHold(AuditedModel):
    """Soft reservation while a quotation is open or a booking awaits deposit."""

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="holds",
    )
    quotation = models.ForeignKey(
        "reservations.Quotation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="holds",
    )
    # Precise line→hold link so a repriced/edited/deleted line can find and move
    # or release *its* hold. SET_NULL (not CASCADE): a deleted line's hold is
    # released explicitly first, and the released row is kept for history.
    quotation_line = models.ForeignKey(
        "reservations.QuotationLine",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="holds",
    )
    booking = models.ForeignKey(
        Booking,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="holds",
    )
    date_from = models.DateField()
    date_to = models.DateField()
    # NULL = never expires (owner / maintenance blocks). Quotation/booking holds
    # always carry a concrete expiry; `tasks.expire_holds` only reaps non-null rows.
    expires_at = models.DateTimeField(db_index=True, null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(
        max_length=32,
        choices=BookingHoldReason.choices,
        default=BookingHoldReason.MANUAL,
    )
    notes = models.TextField(blank=True, default="")
    # Migration metadata only (data_migration convention) — the availability
    # loader keys its imported legacy-unavailability blocks `avail-*` here.
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["property", "released_at", "expires_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(date_from__lt=models.F("date_to")),
                name="bookinghold_date_from_lt_date_to",
            ),
            models.CheckConstraint(
                condition=(
                    Q(quotation__isnull=False)
                    | Q(booking__isnull=False)
                    | Q(
                        reason__in=[
                            BookingHoldReason.OWNER_BLOCK,
                            BookingHoldReason.MAINTENANCE,
                            BookingHoldReason.MANUAL,
                        ]
                    )
                ),
                name="bookinghold_has_source_or_blocking_reason",
            ),
            # Half-open '[)' bounds (same-day turnover legal). Live = not yet
            # released; expiry is delegated to the application sweeper, which
            # sets released_at (Postgres rejects non-IMMUTABLE now() in an
            # index predicate). HoldService maps this constraint's name to
            # HoldUnavailable.
            ExclusionConstraint(
                name=HOLD_OVERLAP_CONSTRAINT_NAME,
                expressions=[
                    ("property", RangeOperators.EQUAL),
                    (
                        DateRangeFunc("date_from", "date_to", RangeBoundary()),
                        RangeOperators.OVERLAPS,
                    ),
                ],
                condition=Q(released_at__isnull=True),
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Hold #{self.pk} on property {self.property_id}"

    def is_live(self) -> bool:
        # A null `expires_at` means the hold never expires (owner/maintenance block).
        if self.released_at is not None:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()

    @classmethod
    def live_overlapping(
        cls,
        *,
        date_from: date_type,
        date_to: date_type,
        property: Any = None,
        exclude_ids: list[int] | None = None,
    ) -> Any:
        """Live (unreleased, unexpired) holds overlapping the range.

        The single source of truth for the hold-overlap predicate, shared by
        `HoldService`, the availability calendar (`AvailabilityService`) and
        catalogue search (`properties` filters). Pass `property` to scope to one
        villa; omit it for a cross-property sweep.
        """
        qs = cls.objects.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()),
            released_at__isnull=True,
            date_from__lt=date_to,
            date_to__gt=date_from,
        )
        if property is not None:
            qs = qs.filter(property=property)
        if exclude_ids:
            qs = qs.exclude(pk__in=exclude_ids)
        return qs


class BookingEvent(TimestampedModel):
    """Append-only audit row written by every transition."""

    booking = models.ForeignKey(
        Booking,
        on_delete=models.PROTECT,
        related_name="events",
    )
    from_status = models.CharField(max_length=32, choices=BookingStatus.choices)
    to_status = models.CharField(max_length=32, choices=BookingStatus.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    source = models.CharField(
        max_length=16,
        choices=EventSource.choices,
        default=EventSource.USER,
    )
    reason = models.CharField(max_length=255, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["booking", "created_at"]),
        ]
        ordering = ["created_at"]


class BookingNote(TimestampedModel):
    """Operator-authored note on a booking."""

    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="notes_collection",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    kind = models.CharField(
        max_length=16,
        choices=BookingNoteKind.choices,
        default=BookingNoteKind.GENERAL,
    )
    body = models.TextField()
    is_pinned = models.BooleanField(default=False)
    visibility = models.CharField(
        max_length=16,
        choices=BookingNoteVisibility.choices,
        default=BookingNoteVisibility.STAFF_ONLY,
    )

    class Meta:
        indexes = [
            models.Index(fields=["booking", "created_at"]),
            models.Index(fields=["booking", "kind"]),
        ]
        ordering = ["created_at"]


# Re-export for convenience; consumers can `from reservations.models.booking import …`.
__all__ = [
    "ACTIVE_BOOKING_STATUSES",
    "OVERLAP_BLOCKING_BOOKING_STATUSES",
    "Booking",
    "BookingEvent",
    "BookingHold",
    "BookingNote",
]
