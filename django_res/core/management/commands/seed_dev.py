"""`./manage.py seed_dev` — generate realistic dev/staging data.

Additive by design: every run appends a fresh batch. Uniqueness is carried by
a per-run token + `factory.Sequence`, so re-running never collides on a unique
constraint. The transactional graph (Enquiry -> Quotation -> Booking ->
Payment) is built through the real service layer so statuses, events, holds
and pricing snapshots are production-faithful.

Hard-blocked unless `settings.SEED_DEV_ALLOWED` is true (False in base/
production, True in dev/test/staging). `--i-understand` does NOT override the
production block — it only documents intent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, cast

import factory.random
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.factories import ContactEmailFactory, ContactPhoneFactory, UserFactory
from pricing.factories import (
    CurrencyFactory,
    DiscountFactory,
    ExtraFactory,
    RateCardFactory,
    RatePlanFactory,
    RateRuleFactory,
)
from properties.factories import PropertyFactory
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
        reports.append(
            self._stage(
                "bookings", lambda: self._make_bookings(n_bookings, properties, currency, terms)
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
        for _ in range(count):
            prop = PropertyFactory()
            plan = RatePlanFactory(property=prop, currency=currency)
            card = RateCardFactory(plan=plan)
            RateRuleFactory(card=card)
            DiscountFactory(property=prop)
            ExtraFactory(property=prop, currency=currency)
            sink.append(prop)
        return count

    def _make_bookings(self, count: int, properties: list[Any], currency: Any, terms: Any) -> int:
        if not properties:
            return 0
        expires_at = timezone.now() + timedelta(days=7)
        # Per-property date cursor keeps each stay's hold from overlapping the
        # previous one for the same villa.
        cursors: dict[int, date] = {}
        made = 0
        for i in range(count):
            prop = properties[i % len(properties)]
            start = cursors.get(prop.pk, date.today() + timedelta(days=21))
            date_from = start
            date_to = start + timedelta(days=7)
            cursors[prop.pk] = date_to + timedelta(days=7)  # gap before next stay

            guest = GuestFactory()
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
                booking = BookingService.create_from_quotation_line(line, terms_version=terms)
                self._populate_payments(booking)
                self._advance_status(booking, i)
            made += 1
        return made

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _populate_payments(booking: Any) -> None:
        from payments.services.payment_scheduler import PaymentScheduler
        from payments.services.security_deposit import SecurityDepositService

        PaymentScheduler.create_for_booking(booking)
        SecurityDepositService.create_for_booking(booking)

    @staticmethod
    def _advance_status(booking: Any, i: int) -> None:
        """Walk a fraction of bookings down their state machine so list/detail
        views and event timelines show variety instead of one status."""
        track = i % 6
        if track == 0:
            return  # stays AWAITING_DEPOSIT
        if track == 5:
            booking.cancel("Guest changed plans")
            return
        booking.record_deposit()
        if track == 1:
            return  # DEPOSIT_PAID
        booking.arm_balance()
        booking.record_balance()
        if track == 2:
            return  # BALANCE_PAID
        booking.check_in()
        if track == 3:
            return  # CHECKED_IN
        booking.check_out()  # track == 4 -> CHECKED_OUT

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
        header = ("stage", "created", "errors", "duration")
        rows: list[tuple[str | int, ...]] = [header]
        for r in reports:
            rows.append((r.stage, r.created, len(r.errors), f"{r.duration_s:.2f}s"))
        widths = [max(len(str(c)) for c in col) for col in zip(*rows, strict=True)]
        for idx, row in enumerate(rows):
            self.stdout.write("  ".join(str(c).ljust(w) for c, w in zip(row, widths, strict=True)))
            if idx == 0:
                self.stdout.write("  ".join("-" * w for w in widths))
        for r in reports:
            if r.errors:
                self.stdout.write(self.style.ERROR(f"\nErrors in {r.stage}:"))
                for message in r.errors:
                    self.stdout.write(f"  {message}")
