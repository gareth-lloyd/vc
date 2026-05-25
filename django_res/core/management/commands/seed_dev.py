"""`./manage.py seed_dev` — generate realistic dev/staging data.

Additive by design: every run appends a fresh batch. Uniqueness is carried by
a per-run token + `factory.Sequence`, so re-running never collides on a unique
constraint. The transactional graph (Enquiry -> Quotation -> Booking ->
Payment) is built through the real service layer so statuses, events, holds
and pricing snapshots are production-faithful.

Three profiles are supported via `--profile`:

  happy  — every booking follows the conversion happy path; statuses span the
           five "everything is fine" terminal buckets via a modulo track plus
           an early-cancel bucket. Reproduces the pre-v2 seeder exactly so
           smoke tests stay deterministic.
  mixed  — default. Adds quotation lifecycle (SENT / EXPIRED / CANCELLED
           without booking), expired and declined bookings, concierge items,
           refunds, repeat guests + preferences, property archive/draft
           spread, and a temporal spread on booking dates so KPIs are
           populated every day of the dev calendar.
  chaos  — `mixed` with the dials cranked: more pre-approval, more refunds,
           wider repeat-guest pool, more property-status churn. For probing
           edge cases.

Hard-blocked unless `settings.SEED_DEV_ALLOWED` is true (False in base/
production, True in dev/test/staging). `--i-understand` does NOT override the
production block — it only documents intent.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import UTC, date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, cast

import factory.random
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.factories import ContactEmailFactory, ContactPhoneFactory, UserFactory
from core.console import render_table
from pricing.factories import (
    CurrencyFactory,
    DiscountFactory,
    ExtraFactory,
    RateCardFactory,
    RatePlanFactory,
    RateRuleFactory,
)
from properties.factories import RUN_TOKEN, PropertyFactory
from properties.services.lifecycle import PropertyLifecycleService
from reservations.factories import EnquiryFactory, GuestFactory, TermsVersionFactory
from reservations.models.enquiry import Enquiry
from reservations.models.terms import TermsVersion
from reservations.services.bookings import BookingService
from reservations.services.quotations import QuotationService

# Rows per stage for each scale preset.
_SCALES: dict[str, dict[str, int]] = {
    "small": {"properties": 5, "users": 4, "bookings": 8},
    "medium": {"properties": 20, "users": 8, "bookings": 40},
    "large": {"properties": 60, "users": 15, "bookings": 150},
}


class Profile(StrEnum):
    HAPPY = "happy"
    MIXED = "mixed"
    CHAOS = "chaos"


@dataclass(frozen=True)
class ProfileKnobs:
    """Per-profile dials. Fractions are 0.0-1.0 of their cohort."""

    name: str
    pct_pre_approval_property: float = 0.0
    pct_property_draft: float = 0.0
    pct_property_archived: float = 0.0
    # Of "quotation-only" attempts that never become bookings:
    pct_extra_quotation_per_booking: float = 0.0
    # Of bookings: extra non-happy lifecycle endings
    pct_booking_expires: float = 0.0
    pct_booking_pre_approval_declines: float = 0.0
    pct_booking_cancel_post_deposit: float = 0.0
    # Tier 2:
    pct_concierge: float = 0.0
    pct_refund_of_cancelled: float = 0.0
    pct_preference: float = 0.0
    # Enquiry-only paths (no quotation at all):
    pct_enquiry_lost_only: float = 0.0
    pct_enquiry_contacted_only: float = 0.0
    repeat_guest_pool_size: int = 0
    # Spread of booking date_from around today (±N days). 0 = legacy
    # (always near today). Larger = wider arrival calendar.
    booking_date_spread_days: int = 0


_PROFILES: dict[Profile, ProfileKnobs] = {
    Profile.HAPPY: ProfileKnobs(name="happy"),
    Profile.MIXED: ProfileKnobs(
        name="mixed",
        pct_pre_approval_property=0.15,
        pct_property_draft=0.05,
        pct_property_archived=0.05,
        pct_extra_quotation_per_booking=0.25,
        pct_booking_expires=0.06,
        pct_booking_pre_approval_declines=0.40,
        pct_booking_cancel_post_deposit=0.15,
        pct_concierge=0.30,
        # Refund the majority of refundable cancellations so every refund
        # state (REJECTED / APPROVED / FAILED / SUCCEEDED) is reachable in
        # any decent-sized run.
        pct_refund_of_cancelled=0.80,
        pct_preference=0.25,
        pct_enquiry_lost_only=0.10,
        pct_enquiry_contacted_only=0.10,
        repeat_guest_pool_size=4,
        booking_date_spread_days=180,
    ),
    Profile.CHAOS: ProfileKnobs(
        name="chaos",
        pct_pre_approval_property=0.30,
        pct_property_draft=0.08,
        pct_property_archived=0.08,
        pct_extra_quotation_per_booking=0.50,
        pct_booking_expires=0.12,
        pct_booking_pre_approval_declines=0.50,
        pct_booking_cancel_post_deposit=0.10,
        pct_concierge=0.50,
        pct_refund_of_cancelled=0.60,
        pct_preference=0.45,
        pct_enquiry_lost_only=0.20,
        pct_enquiry_contacted_only=0.15,
        repeat_guest_pool_size=8,
        booking_date_spread_days=365,
    ),
}


@dataclass
class StageReport:
    stage: str
    created: int = 0
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0


class Command(BaseCommand):
    help = "Generate realistic dev/staging data (additive, service-driven)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--scale",
            choices=sorted(_SCALES),
            default="small",
            help="Preset batch size (default: small).",
        )
        parser.add_argument(
            "--profile",
            choices=[p.value for p in Profile],
            default=Profile.MIXED.value,
            help=(
                "Data shape: happy (uniform success path), mixed (default — "
                "lifecycle variety, refunds, concierge, preferences), or "
                "chaos (mixed with dials cranked)."
            ),
        )
        parser.add_argument("--properties", type=int, default=None, help="Override property count.")
        parser.add_argument("--bookings", type=int, default=None, help="Override booking count.")
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Faker/factory random seed for reproducible batches.",
        )
        parser.add_argument(
            "--i-understand",
            action="store_true",
            help="Acknowledge this writes fake data. Does NOT bypass the production block.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not getattr(settings, "SEED_DEV_ALLOWED", False):
            raise CommandError(
                "seed_dev is disabled here (SEED_DEV_ALLOWED is False). It is "
                "intentionally never runnable in production."
            )

        if options["seed"] is not None:
            factory.random.reseed_random(options["seed"])
            random.seed(options["seed"])
            self._rng = random.Random(options["seed"])
        else:
            self._rng = random.Random()

        self._knobs = _PROFILES[Profile(options["profile"])]

        scale = _SCALES[options["scale"]]
        n_props = (
            options["properties"] if options["properties"] is not None else scale["properties"]
        )
        n_bookings = options["bookings"] if options["bookings"] is not None else scale["bookings"]
        n_users = scale["users"]

        reports: list[StageReport] = []
        currency = CurrencyFactory(spec=("GBP", "Pound sterling", "£"))
        # factory-boy is untyped; cast factory results to the model they build.
        terms = cast(TermsVersion, TermsVersionFactory())
        terms.publish()

        reports.append(self._stage("users", lambda: self._make_users(n_users)))
        properties: list[Any] = []
        reports.append(
            self._stage("properties", lambda: self._make_properties(n_props, currency, properties))
        )
        # Repeat-guest pool: a small set of guests reused across bookings.
        guest_pool: list[Any] = []
        if self._knobs.repeat_guest_pool_size > 0:
            for _ in range(self._knobs.repeat_guest_pool_size):
                guest_pool.append(GuestFactory())
        reports.append(
            self._stage(
                "bookings",
                lambda: self._make_bookings(n_bookings, properties, currency, terms, guest_pool),
            )
        )
        reports.append(
            self._stage(
                "extra_quotations",
                lambda: self._make_extra_quotations(
                    n_bookings, properties, currency, terms, guest_pool
                ),
            )
        )
        reports.append(
            self._stage(
                "orphan_enquiries",
                lambda: self._make_orphan_enquiries(properties, guest_pool),
            )
        )
        reports.append(
            self._stage(
                "concierge_items",
                lambda: self._make_concierge_items(currency),
            )
        )
        reports.append(self._stage("refunds", lambda: self._make_refunds()))
        reports.append(
            self._stage(
                "guest_preferences",
                lambda: self._make_guest_preferences(guest_pool),
            )
        )
        reports.append(
            self._stage(
                "property_lifecycle",
                lambda: self._spread_property_statuses(properties),
            )
        )

        self._print_summary(reports)

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------
    def _make_users(self, count: int) -> int:
        for _ in range(count):
            contact = ContactEmailFactory().contact
            ContactPhoneFactory(contact=contact)
            UserFactory()
        return count

    def _make_properties(self, count: int, currency: Any, sink: list[Any]) -> int:
        # Widen the rate-plan window when the profile spreads bookings further
        # than the factory default (today-30 .. today+400). Without this, the
        # earlier bookings under `--profile mixed/chaos` would fail with
        # `NoRateAvailable`.
        spread = self._knobs.booking_date_spread_days
        plan_kwargs: dict[str, Any] = {}
        rule_kwargs: dict[str, Any] = {}
        discount_kwargs: dict[str, Any] = {}
        if spread > 30:
            # +60 absorbs the per-property cursor walk: bookings on a
            # property in the +spread bucket can stack 14 days each.
            buffer = timedelta(days=spread + 60)
            plan_kwargs = {
                "effective_from": date.today() - buffer,
                "effective_to": date.today() + buffer,
            }
            rule_kwargs = {
                "date_from": date.today() - buffer,
                "date_to": date.today() + buffer,
            }
            discount_kwargs = {
                "valid_from": date.today() - buffer,
                "valid_to": date.today() + buffer,
            }
        for _ in range(count):
            # factory-boy is untyped; cast so mypy sees the post_generation
            # children (`.settings`, `.location`, etc.).
            prop = cast(Any, PropertyFactory())
            if self._rng.random() < self._knobs.pct_pre_approval_property:
                prop.settings.bookings_require_pre_approval = True
                prop.settings.save(update_fields=["bookings_require_pre_approval"])
            plan = RatePlanFactory(property=prop, currency=currency, **plan_kwargs)
            card = RateCardFactory(plan=plan)
            RateRuleFactory(card=card, **rule_kwargs)
            DiscountFactory(property=prop, **discount_kwargs)
            ExtraFactory(property=prop, currency=currency)
            sink.append(prop)
        return count

    def _make_bookings(
        self,
        count: int,
        properties: list[Any],
        currency: Any,
        terms: Any,
        guest_pool: list[Any],
    ) -> int:
        if not properties:
            return 0
        active_properties = [p for p in properties if p.status == "active"] or properties
        expires_at = timezone.now() + timedelta(days=7)
        # Per-property date cursor keeps each stay's hold from overlapping the
        # previous one for the same villa.
        cursors: dict[int, date] = {}
        made = 0
        for i in range(count):
            prop = active_properties[i % len(active_properties)]
            date_from = self._next_stay_start(prop, cursors, i)
            date_to = date_from + timedelta(days=7)
            cursors[prop.pk] = date_to + timedelta(days=7)  # gap before next stay

            guest = self._pick_guest(guest_pool)
            enquiry = cast(
                Enquiry,
                EnquiryFactory(guest=guest, property=prop, date_from=date_from, date_to=date_to),
            )
            with transaction.atomic():
                quotation = QuotationService.create_from_enquiry(
                    enquiry,
                    [
                        {
                            "property": prop,
                            "date_from": date_from,
                            "date_to": date_to,
                            "adults": 2,
                            "children": 1,
                        }
                    ],
                    currency=currency,
                    terms_version=terms,
                    expires_at=expires_at,
                )
                line = quotation.lines.first()
                if line is None:
                    raise RuntimeError("QuotationService produced no lines")
                quotation.send()
                # Pre-approval properties accept the quotation only after the
                # owner approves — otherwise an owner-declined booking would
                # leave the quotation falsely ACCEPTED.
                requires_pre_approval = bool(
                    cast(Any, prop.settings).effective("bookings_require_pre_approval")
                )
                if not requires_pre_approval:
                    quotation.accept(line)
                booking = BookingService.create_from_quotation_line(line, terms_version=terms)
                self._populate_payments(booking)
                self._advance_status(booking, i)
                # Only mark the enquiry CONVERTED for bookings that actually
                # opened — leave QUOTED for declined/still-pending bookings so
                # the enquiry's lifecycle doesn't lie.
                from reservations.enums import BookingStatus

                booking.refresh_from_db()
                if booking.status not in (
                    BookingStatus.DECLINED.value,
                    BookingStatus.PENDING_OWNER_APPROVAL.value,
                ):
                    enquiry.refresh_from_db()
                    enquiry.convert(quotation)
            made += 1
        return made

    def _make_extra_quotations(
        self,
        booking_count: int,
        properties: list[Any],
        currency: Any,
        terms: Any,
        guest_pool: list[Any],
    ) -> int:
        """Create quotations that never become bookings: some stay SENT, some
        expire, some get cancelled — the lifecycle the booking-path skips."""
        if not self._knobs.pct_extra_quotation_per_booking or not properties:
            return 0
        active_properties = [p for p in properties if p.status == "active"] or properties
        target = max(1, int(booking_count * self._knobs.pct_extra_quotation_per_booking))
        # Mod-3 buckets: stay SENT / EXPIRE / CANCEL.
        outcomes = ("sent", "expired", "cancelled")
        expires_at = timezone.now() + timedelta(days=7)
        made = 0
        for i in range(target):
            prop = active_properties[i % len(active_properties)]
            date_from = date.today() + timedelta(days=30 + i * 11)
            date_to = date_from + timedelta(days=5)
            guest = self._pick_guest(guest_pool)
            enquiry = cast(
                Enquiry,
                EnquiryFactory(guest=guest, property=prop, date_from=date_from, date_to=date_to),
            )
            with transaction.atomic():
                quotation = QuotationService.create_from_enquiry(
                    enquiry,
                    [
                        {
                            "property": prop,
                            "date_from": date_from,
                            "date_to": date_to,
                            "adults": 2,
                            "children": 0,
                        }
                    ],
                    currency=currency,
                    terms_version=terms,
                    expires_at=expires_at,
                )
                quotation.send()
                outcome = outcomes[i % len(outcomes)]
                if outcome == "expired":
                    quotation.expire()
                elif outcome == "cancelled":
                    quotation.cancel("Guest never replied")
                # else: stays SENT
            made += 1
        return made

    def _make_orphan_enquiries(self, properties: list[Any], guest_pool: list[Any]) -> int:
        """Enquiries that never get a quote: some CONTACTED only, some LOST."""
        if not properties:
            return 0
        active_properties = [p for p in properties if p.status == "active"] or properties
        # Tie volume to the configured pcts; floor at 1 when enabled.
        lost = (
            max(1, int(len(active_properties) * self._knobs.pct_enquiry_lost_only))
            if self._knobs.pct_enquiry_lost_only
            else 0
        )
        contacted = (
            max(1, int(len(active_properties) * self._knobs.pct_enquiry_contacted_only))
            if self._knobs.pct_enquiry_contacted_only
            else 0
        )
        made = 0
        for i in range(lost):
            prop = active_properties[i % len(active_properties)]
            enquiry = cast(
                Enquiry,
                EnquiryFactory(guest=self._pick_guest(guest_pool), property=prop),
            )
            enquiry.lose("No suitable match")
            made += 1
        for i in range(contacted):
            prop = active_properties[(i + 1) % len(active_properties)]
            enquiry = cast(
                Enquiry,
                EnquiryFactory(guest=self._pick_guest(guest_pool), property=prop),
            )
            enquiry.contact()
            made += 1
        return made

    def _make_concierge_items(self, currency: Any) -> int:
        """Attach concierge items to a fraction of confirmed bookings."""
        if not self._knobs.pct_concierge:
            return 0
        from reservations.enums import (
            BookingStatus,
            ConciergeStatus,
            ConciergeTier,
            ConciergeUnit,
        )
        from reservations.models.booking import Booking
        from reservations.models.concierge import BookingConciergeItem

        catalogue = [
            ("Airport transfer", ConciergeUnit.STAY, Decimal("150.00"), ConciergeTier.SIGNATURE),
            ("Daily housekeeping", ConciergeUnit.DAY, Decimal("80.00"), ConciergeTier.SIGNATURE),
            (
                "Private chef dinner",
                ConciergeUnit.EVENT,
                Decimal("400.00"),
                ConciergeTier.QUINTESSENTIAL,
            ),
            ("Yacht charter", ConciergeUnit.DAY, Decimal("1200.00"), ConciergeTier.QUINTESSENTIAL),
            ("Massage in-villa", ConciergeUnit.HOUR, Decimal("90.00"), ConciergeTier.SIGNATURE),
        ]
        eligible = list(
            Booking.objects.filter(
                status__in=(
                    BookingStatus.DEPOSIT_PAID.value,
                    BookingStatus.BALANCE_PAID.value,
                    BookingStatus.CHECKED_IN.value,
                    BookingStatus.CHECKED_OUT.value,
                )
            ).values_list("pk", flat=True)
        )
        target = int(len(eligible) * self._knobs.pct_concierge)
        outcome_statuses = (
            ConciergeStatus.REQUESTED.value,
            ConciergeStatus.CONFIRMED.value,
            ConciergeStatus.DELIVERED.value,
            ConciergeStatus.CANCELLED.value,
        )
        made = 0
        for pk in self._rng.sample(eligible, k=min(target, len(eligible))):
            booking = Booking.objects.get(pk=pk)
            for name, unit, price, tier in self._rng.sample(catalogue, k=min(2, len(catalogue))):
                BookingConciergeItem.objects.create(
                    booking=booking,
                    tier=tier.value,
                    name=name,
                    quantity=2 if unit == ConciergeUnit.DAY else 1,
                    unit=unit.value,
                    unit_price=price,
                    currency=currency,
                    status=outcome_statuses[made % len(outcome_statuses)],
                )
                made += 1
        return made

    def _make_refunds(self) -> int:
        """Drive refunds across the four interesting terminal outcomes.

        Sources two cohorts:
          * cancelled bookings with settled deposit/balance → `from_cancellation`
          * paid-up bookings (BALANCE_PAID / CHECKED_OUT) → small goodwill
            refunds via `RefundService.request`

        Combining both ensures we always have enough material to cycle through
        REJECTED / APPROVED / FAILED / SUCCEEDED even when only one cancellation
        landed with money on it.
        """
        if not self._knobs.pct_refund_of_cancelled:
            return 0
        from decimal import Decimal

        from payments.enums import (
            PaymentStatus,
            RefundPurposeTrack,
            RefundReasonCode,
            RefundStatus,
        )
        from payments.services.refund import RefundService
        from reservations.enums import BookingStatus
        from reservations.models.booking import Booking

        # Exclude bookings that already carry a Refund so additive reruns do
        # not double-refund the same booking (which would also bust the
        # balance-due / paid-out invariant the refund service relies on).
        refundable_cancelled = list(
            Booking.objects.filter(
                status=BookingStatus.CANCELLED.value,
                payments__status=PaymentStatus.SUCCEEDED.value,
            )
            .exclude(refunds__isnull=False)
            .distinct()
            .values_list("pk", flat=True)
        )
        paid_up = list(
            Booking.objects.filter(
                status__in=(
                    BookingStatus.BALANCE_PAID.value,
                    BookingStatus.CHECKED_OUT.value,
                )
            )
            .exclude(refunds__isnull=False)
            .values_list("pk", flat=True)
        )

        candidates: list[tuple[int, str]] = [
            (pk, "cancellation") for pk in refundable_cancelled
        ] + [(pk, "goodwill") for pk in paid_up]
        if not candidates:
            return 0
        target = max(1, int(len(candidates) * self._knobs.pct_refund_of_cancelled))
        chosen = self._rng.sample(candidates, k=min(target, len(candidates)))

        made = 0
        for i, (pk, source) in enumerate(chosen):
            booking = Booking.objects.select_related("currency", "property").get(pk=pk)
            if source == "cancellation":
                refund = RefundService.from_cancellation(
                    booking, reason="seed_dev cancellation", requested_by=None
                )
            else:
                refund = RefundService.request(
                    booking=booking,
                    amount=Decimal("25.00"),
                    currency=booking.currency,
                    purpose_track=RefundPurposeTrack.GOODWILL.value,
                    reason_code=RefundReasonCode.GOODWILL.value,
                    reason_notes="seed_dev goodwill gesture",
                )
            if refund is None:
                continue
            outcome = i % 4
            if outcome == 0:
                RefundService.reject(refund, actor=None, reason="Out-of-policy")
            elif outcome == 1:
                RefundService.approve(refund, actor=None)
                # Stays APPROVED — visible work-queue item for ops.
            elif outcome == 2:
                RefundService.approve(refund, actor=None)
                RefundService.execute(refund, actor=None)
                refund._transition(RefundStatus.FAILED.value, kind="seed_dev_failed")
            else:
                RefundService.approve(refund, actor=None)
                RefundService.execute(refund, actor=None)
                refund._transition(RefundStatus.SUCCEEDED.value, kind="seed_dev_succeeded")
            made += 1
        return made

    def _make_guest_preferences(self, guest_pool: list[Any]) -> int:
        """Attach typed preferences (bed type, dietary, etc.) to a slice of
        the guest pool."""
        if not self._knobs.pct_preference:
            return 0
        from reservations.models.preferences import GuestPreference, GuestPreferenceType

        # A small canonical menu; reuse rows on rerun via get_or_create.
        names = [
            "Twin beds preferred",
            "Vegetarian",
            "Allergic to nuts",
            "Cot required",
            "Pet-friendly",
            "Early arrival OK",
        ]
        types = [GuestPreferenceType.objects.get_or_create(name=name)[0] for name in names]
        # Operate on the whole guest pool plus a few freshly-seeded guests so
        # there are preferences attached to non-repeat guests too.
        from reservations.models.guest import Guest

        pool_pks = [g.pk for g in guest_pool]
        candidates = (
            list(Guest.objects.exclude(pk__in=pool_pks).values_list("pk", flat=True)[:50])
            + pool_pks
        )
        target = max(1, int(len(candidates) * self._knobs.pct_preference))
        chosen = self._rng.sample(candidates, k=min(target, len(candidates)))
        made = 0
        for pk in chosen:
            guest = Guest.objects.get(pk=pk)
            for pref_type in self._rng.sample(types, k=self._rng.randint(1, 2)):
                _, created = GuestPreference.objects.get_or_create(
                    guest=guest,
                    preference_type=pref_type,
                    quotation=None,
                    defaults={"notes": ""},
                )
                if created:
                    made += 1
        return made

    def _spread_property_statuses(self, properties: list[Any]) -> int:
        """Move a slice of properties into DRAFT / ARCHIVED to exercise the
        lifecycle states the rest of the system filters on."""
        if not properties:
            return 0
        if not (self._knobs.pct_property_draft or self._knobs.pct_property_archived):
            return 0
        # Pick from properties that have no live bookings to avoid breaking
        # active-overlap invariants — leave booking-bearing ones ACTIVE.
        from reservations.enums import ACTIVE_BOOKING_STATUSES
        from reservations.models.booking import Booking

        booking_props = set(
            Booking.objects.filter(status__in=ACTIVE_BOOKING_STATUSES).values_list(
                "property_id", flat=True
            )
        )
        candidates = [p for p in properties if p.pk not in booking_props]
        self._rng.shuffle(candidates)
        # Apply +1 floor when the knob is non-zero — otherwise tiny runs
        # (< 20 properties) silently produce zero non-ACTIVE properties.
        n_draft = (
            max(1, int(len(properties) * self._knobs.pct_property_draft))
            if self._knobs.pct_property_draft
            else 0
        )
        n_archived = (
            max(1, int(len(properties) * self._knobs.pct_property_archived))
            if self._knobs.pct_property_archived
            else 0
        )
        # Draft requires the property to be currently DRAFT or ARCHIVED to
        # *enter* ACTIVE; but to move ACTIVE → DRAFT we route via archive →
        # restore (lifecycle service rule).
        made = 0
        for prop in candidates[:n_archived]:
            PropertyLifecycleService.archive(prop)
            made += 1
        for prop in candidates[n_archived : n_archived + n_draft]:
            PropertyLifecycleService.archive(prop)
            PropertyLifecycleService.restore(prop)
            made += 1
        return made

    # ------------------------------------------------------------------
    # Per-booking helpers
    # ------------------------------------------------------------------
    def _next_stay_start(self, prop: Any, cursors: dict[int, date], i: int) -> date:
        """Return a sensible date_from for the next booking on `prop`.

        Honours the temporal-spread knob: distributes start dates across a
        symmetric window around today so dashboards see a populated calendar.
        Per-property cursor avoids overlap when multiple bookings land on the
        same villa.
        """
        spread = self._knobs.booking_date_spread_days
        if spread > 0 and prop.pk not in cursors:
            # First booking for this property: place each property in its
            # own time bucket across the spread window so the calendar
            # carries traffic on every side of today. Property pk drives the
            # bucket (mod 8) — independent of booking index, which keeps
            # the cursor walk within a single property bucket.
            bucket = prop.pk % 8
            offset = int((bucket / 7) * 2 * spread - spread)
            return date.today() + timedelta(days=offset)
        return cursors.get(prop.pk, date.today() + timedelta(days=21))

    def _pick_guest(self, guest_pool: list[Any]) -> Any:
        """Pick a guest: from the repeat pool with high probability, otherwise
        a fresh one. Empty pool → always fresh."""
        if guest_pool and self._rng.random() < 0.6:
            return self._rng.choice(guest_pool)
        return GuestFactory()

    def _populate_payments(self, booking: Any) -> None:
        from payments.services.payment_scheduler import PaymentScheduler
        from payments.services.security_deposit import SecurityDepositService

        # Pre-approval bookings sit before AWAITING_DEPOSIT — skip the
        # payment scaffolding; PaymentScheduler runs once they're approved.
        from reservations.enums import BookingStatus

        if booking.status == BookingStatus.PENDING_OWNER_APPROVAL.value:
            return
        PaymentScheduler.create_for_booking(booking)
        SecurityDepositService.create_for_booking(booking)

    @staticmethod
    def _mark_payment_paid(booking: Any, purpose: str) -> None:
        """Mark the scheduler-created Payment row for this booking+purpose as
        SUCCEEDED so downstream services that look up paid money (notably
        `RefundService.from_cancellation`) see realistic state."""
        from datetime import datetime

        from payments.enums import PaymentMethod, PaymentStatus
        from payments.models.payment import Payment

        payment = (
            Payment.objects.filter(
                booking=booking, purpose=purpose, status=PaymentStatus.PENDING.value
            )
            .order_by("pk")
            .first()
        )
        if payment is None:
            return
        payment.mark_paid(
            amount=payment.amount,
            paid_at=datetime.now(UTC),
            method=PaymentMethod.CARD.value,
            reference=f"SEED-{payment.pk}",
        )

    def _advance_status(self, booking: Any, i: int) -> None:
        """Walk a fraction of bookings down their state machine so list/detail
        views and event timelines show variety instead of one status."""
        from payments.enums import PaymentPurpose
        from reservations.enums import BookingStatus

        if booking.status == BookingStatus.PENDING_OWNER_APPROVAL.value:
            self._advance_pre_approval(booking, i)
            return

        # Optional non-happy endings — short-circuit before the modulo track.
        if self._knobs.pct_booking_expires and (i * 13) % 100 < int(
            self._knobs.pct_booking_expires * 100
        ):
            booking.expire()
            return

        track = i % 6
        if track == 0:
            return  # stays AWAITING_DEPOSIT
        if track == 5:
            booking.cancel("Guest changed plans")
            return
        booking.record_deposit()
        self._mark_payment_paid(booking, PaymentPurpose.DEPOSIT.value)
        if self._knobs.pct_booking_cancel_post_deposit and (i * 19) % 100 < int(
            self._knobs.pct_booking_cancel_post_deposit * 100
        ):
            booking.cancel("Plans changed after deposit")
            return
        if track == 1:
            return  # DEPOSIT_PAID
        booking.arm_balance()
        booking.record_balance()
        self._mark_payment_paid(booking, PaymentPurpose.BALANCE.value)
        if track == 2:
            return  # BALANCE_PAID
        booking.check_in()
        if track == 3:
            return  # CHECKED_IN
        booking.check_out()  # track == 4 -> CHECKED_OUT

    def _advance_pre_approval(self, booking: Any, i: int) -> None:
        """Resolve a PENDING_OWNER_APPROVAL booking via mod-3:

        * Some are owner_declined.
        * Some are approved and then run the happy track.
        * Some stay PENDING_OWNER_APPROVAL (operator queue).
        """
        from payments.enums import PaymentPurpose

        decline_threshold = int(self._knobs.pct_booking_pre_approval_declines * 100)
        if (i * 7) % 100 < decline_threshold:
            booking.owner_decline("Owner unavailable")
            return
        if i % 3 == 0:
            return  # leave PENDING_OWNER_APPROVAL — visible work queue
        booking.owner_approve()
        # The quotation was left SENT by _make_bookings — accept it now that
        # the owner has approved so the quotation lifecycle matches reality.
        line = booking.quotation_line
        line.quotation.accept(line)
        # Now AWAITING_DEPOSIT — set up payment scaffolding the parent path
        # skipped, then progress.
        self._populate_payments(booking)
        booking.record_deposit()
        self._mark_payment_paid(booking, PaymentPurpose.DEPOSIT.value)

    # ------------------------------------------------------------------
    # Stage/report scaffolding
    # ------------------------------------------------------------------
    def _stage(self, name: str, fn: Any) -> StageReport:
        report = StageReport(stage=name)
        started = time.monotonic()
        try:
            report.created = fn()
        except Exception as exc:
            report.errors.append(repr(exc))
        report.duration_s = time.monotonic() - started
        return report

    def _print_summary(self, reports: list[StageReport]) -> None:
        self.stdout.write(f"profile: {self._knobs.name} (run token: {RUN_TOKEN})")
        header = ("stage", "created", "errors", "duration")
        rows = [(r.stage, r.created, len(r.errors), f"{r.duration_s:.2f}s") for r in reports]
        self.stdout.write(render_table(header, rows))
        for r in reports:
            if r.errors:
                self.stdout.write(self.style.ERROR(f"\nErrors in {r.stage}:"))
                for message in r.errors:
                    self.stdout.write(f"  {message}")
