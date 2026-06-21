"""demo_ical — seed and drive an end-to-end demo of the iCal feed import.

The iCal feature is *import-only*: `ICalIngestService` polls each active
`PropertyCalendarFeed.url` over real HTTP, coalesces the busy ranges, and writes
`OwnerBlock(source=ICAL)` rows that block availability. This command stands up a
self-contained demo property + owner so that whole path can be exercised by hand
against either a real OTA/Google `.ics` feed or a local fixture, and the result
inspected via the owner calendar API.

It is additive and idempotent (stable lookup keys, re-runnable) and guarded by
`settings.SEED_DEV_ALLOWED`, so it can never run in production. Actions compose
in a sensible order within a single invocation; with no action it defaults to a
poll.

    manage.py demo_ical --reset
    manage.py demo_ical --setup --owner-email demo.owner@example.com --owner-password demopass123
    manage.py demo_ical --add-feed --platform google --label "Owner cal" --feed-url "https://…/basic.ics"
    manage.py demo_ical --add-feed --platform google --label "Owner cal"  # uses DEMO_ICAL_FEED_URL
    manage.py demo_ical --poll
    manage.py demo_ical --inject-conflict quotation
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from integrations.ical.profiles import CalendarFeedPlatform

if TYPE_CHECKING:
    from properties.models import Property, PropertyCalendarFeed
    from reservations.services.ical_ingest import PropertyResult

# Stable handles so every action finds the same demo objects on re-run.
ORG_NAME = "iCal Demo Org"
# Stable slug for the demo property. `seed_dev` pre-seeds a property under this
# slug (the `ical_demo` stage) so the demo runs against realistic data on a
# seeded DB; on an empty DB (tests) `_demo_property` falls back to creating a
# minimal property under the same slug.
PROPERTY_SLUG = "ical-demo-villa"
REGION_SLUG = "ical-demo-region"
CATEGORY_SLUG = "ical-demo-category"
GROUP_NAME = "iCal Demo Group"
GUEST_EMAIL = "ical-demo-guest@example.com"
TERMS_VERSION = "ical-demo-terms"
DEFAULT_OWNER_EMAIL = "demo.owner@example.com"
# Demo-only credential; the command refuses to run unless SEED_DEV_ALLOWED.
DEFAULT_OWNER_PASSWORD = "demopass123"

_PLATFORMS = [p.value for p in CalendarFeedPlatform]


class Command(BaseCommand):
    help = "Seed and drive an end-to-end demo of the iCal feed import (dev/staging only)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--setup",
            action="store_true",
            help="Create/reuse the demo owner org, owner user, property and grant.",
        )
        parser.add_argument(
            "--add-feed",
            action="store_true",
            help="Attach an iCal feed to the demo property (needs --feed-url).",
        )
        parser.add_argument(
            "--feed-url",
            help="The iCal feed URL for --add-feed (defaults to settings.DEMO_ICAL_FEED_URL).",
        )
        parser.add_argument(
            "--platform",
            choices=_PLATFORMS,
            default=CalendarFeedPlatform.OTHER.value,
            help="Feed platform profile (default: other).",
        )
        parser.add_argument("--label", default="", help="Operator-friendly feed label.")
        parser.add_argument(
            "--poll",
            action="store_true",
            help="Poll the demo property's feeds and print the result (default action).",
        )
        parser.add_argument(
            "--inject-conflict",
            choices=["quotation", "booking"],
            help="Place a clashing hold/booking on an imported block's range, "
            "so the next --poll fires an ops conflict alert.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Hard-delete all demo data so the demo can re-run from clean.",
        )
        parser.add_argument(
            "--owner-email",
            default=DEFAULT_OWNER_EMAIL,
            help=f"Demo owner login email (default: {DEFAULT_OWNER_EMAIL}).",
        )
        parser.add_argument(
            "--owner-password",
            default=DEFAULT_OWNER_PASSWORD,
            help="Demo owner password (set via set_password).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.SEED_DEV_ALLOWED:
            raise CommandError(
                "demo_ical is blocked: SEED_DEV_ALLOWED is False "
                "(it must never touch a production database)."
            )

        did_action = False
        if options["reset"]:
            self._reset()
            did_action = True
        if options["setup"]:
            self._setup(options["owner_email"], options["owner_password"])
            did_action = True
        if options["add_feed"]:
            feed_url = options.get("feed_url") or settings.DEMO_ICAL_FEED_URL
            self._add_feed(feed_url, options["platform"], options["label"])
            did_action = True
        if options["inject_conflict"]:
            self._inject_conflict(options["inject_conflict"])
            did_action = True
        # Poll is the default action when nothing else (or --poll) is asked for.
        if options["poll"] or not did_action:
            self._poll()

    # --- actions -----------------------------------------------------------

    def _setup(self, owner_email: str, owner_password: str) -> None:
        from owners.enums import OwnerMembershipStatus
        from owners.models import OwnerMembership, OwnerOrganisation, OwnerOrgProperty

        prop = _demo_property()
        org, _ = OwnerOrganisation.objects.get_or_create(name=ORG_NAME)
        user = _demo_owner(owner_email, owner_password)
        OwnerMembership.objects.get_or_create(
            organisation=org,
            user=user,
            defaults={"status": OwnerMembershipStatus.ACTIVE.value},
        )
        OwnerOrgProperty.objects.get_or_create(organisation=org, property=prop)

        self.stdout.write(self.style.SUCCESS(f"Demo property #{prop.pk} ({prop.slug}) ready."))
        self.stdout.write(f"Owner login: {owner_email} / {owner_password}")
        self.stdout.write(
            "Inspect availability via the owner calendar API (BasicAuth):\n"
            f"  curl -u {owner_email}:{owner_password} \\\n"
            f'    "http://localhost:8000/api/v1/owner/properties/{prop.pk}/calendar'
            '?from=<YYYY-MM-DD>&to=<YYYY-MM-DD>"'
        )

    def _add_feed(self, feed_url: str | None, platform: str, label: str) -> None:
        from properties.models import PropertyCalendarFeed

        if not feed_url:
            raise CommandError(
                "--add-feed requires --feed-url (or set DEMO_ICAL_FEED_URL in the environment)."
            )
        prop = _require_demo_property()
        feed, created = PropertyCalendarFeed.objects.get_or_create(
            property=prop,
            url=feed_url,
            defaults={"platform": platform, "label": label or platform, "is_active": True},
        )
        verb = "Added" if created else "Reused"
        self.stdout.write(
            self.style.SUCCESS(f"{verb} feed #{feed.pk} ({feed.platform}) on property #{prop.pk}.")
        )

    def _poll(self) -> None:
        from properties.models import Property
        from reservations.services.ical_ingest import ICalIngestService

        prop = _require_demo_property()
        feeds = list(prop.calendar_feeds.filter(is_active=True))
        if not feeds:
            raise CommandError(
                "The demo property has no active feeds — run --add-feed --feed-url <ics> first."
            )

        results = ICalIngestService.run(properties=Property.objects.filter(pk=prop.pk))
        self._report_poll(prop, feeds, results)

    def _inject_conflict(self, kind: str) -> None:
        from reservations.enums import OwnerBlockSource, OwnerBlockStatus
        from reservations.models import OwnerBlock

        if not settings.OPS_EMAIL_RECIPIENTS:
            raise CommandError(
                "OPS_EMAIL_RECIPIENTS is empty, so the conflict alert email would be "
                "silently skipped. Set it first, e.g. "
                "OPS_EMAIL_RECIPIENTS=ops@villacollective.test."
            )

        prop = _require_demo_property()
        block = (
            OwnerBlock.objects.filter(
                property=prop,
                source=OwnerBlockSource.ICAL.value,
                status=OwnerBlockStatus.APPROVED.value,
            )
            .order_by("date_from")
            .first()
        )
        if block is None:
            raise CommandError("No imported block to clash with — run --poll against a feed first.")

        # Cancel the imported block so its hold releases the range; then plant the
        # clash there. The next --poll re-imports the same range and collides with
        # the clash, firing the ops alert (a live block would mask it as our own).
        from reservations.services.owner_block import OwnerBlockService

        OwnerBlockService.cancel(block, actor=None)
        if kind == "quotation":
            ref = _place_quotation_clash(prop, block.date_from, block.date_to)
        else:
            ref = _place_booking_clash(prop, block.date_from, block.date_to)

        self.stdout.write(
            self.style.SUCCESS(
                f"Planted a {kind} clash ({ref}) on {block.date_from}..{block.date_to}. "
                "Re-run --poll to fire the conflict alert."
            )
        )

    def _reset(self) -> None:
        deleted = _delete_demo_data()
        self.stdout.write(self.style.WARNING(f"Reset: removed {deleted} demo rows."))

    # --- reporting ---------------------------------------------------------

    def _report_poll(
        self,
        prop: Property,
        feeds: list[PropertyCalendarFeed],
        results: list[PropertyResult],
    ) -> None:
        from reservations.enums import OwnerBlockSource, OwnerBlockStatus
        from reservations.models import OwnerBlock

        result = results[0] if results else None
        self.stdout.write(self.style.SUCCESS(f"Polled property #{prop.pk} ({len(feeds)} feed(s)):"))
        for feed in feeds:
            feed.refresh_from_db()
            line = f"  feed #{feed.pk} [{feed.platform}] {feed.label or '—'}: {feed.last_status}"
            if feed.last_error:
                line += f" — {feed.last_error}"
            self.stdout.write(line)

        if result is None:
            self.stdout.write(self.style.WARNING("  (no result — property had no active feeds)"))
            return
        if result.skipped:
            self.stdout.write(
                self.style.WARNING("  reconcile skipped this run (a feed failed to fetch/parse).")
            )
        self.stdout.write(
            f"  created={result.created} cancelled={result.cancelled} "
            f"conflicts={result.conflicts} hold-overlaps-skipped={result.skipped_holds}"
        )

        blocks = list(
            OwnerBlock.objects.filter(property=prop, source=OwnerBlockSource.ICAL.value).order_by(
                "date_from"
            )
        )
        active = [b for b in blocks if b.status == OwnerBlockStatus.APPROVED.value]
        self.stdout.write(f"  imported blocks (APPROVED): {len(active)}")
        for b in active:
            nights = _nights_between(b.date_from, b.date_to)
            last_night = b.date_to - timedelta(days=1)
            noun = "night" if nights == 1 else "nights"
            # Inclusive nights, not the raw half-open [from, to): a block to the
            # 5th sleeps through the 4th and frees the 5th for a new arrival.
            self.stdout.write(
                f"    {b.date_from} - {last_night}  ({nights} {noun}, free from {b.date_to})  "
                f"key={b.idempotency_key}  «{b.notes}»"
            )

        if active:
            window_from = min(b.date_from for b in active)
            window_to = max(b.date_to for b in active)
            checkout_days = {b.date_to for b in active}
            self._print_calendar(prop, window_from, window_to, checkout_days)

    def _print_calendar(
        self,
        prop: Property,
        range_start: date,
        range_end: date,
        checkout_days: set[date],
    ) -> None:
        from reservations.services.availability import AvailabilityService

        cells = AvailabilityService.calendar(prop, range_start, range_end)
        self.stdout.write(f"  availability {range_start} … {range_end}:")
        for day, cell in sorted(cells.items()):
            if cell.available:
                # A block's exclusive date_to is its checkout morning: open and
                # bookable as a new arrival, even though it bounds a block.
                mark = "OPEN — checkout / available" if day in checkout_days else "OPEN"
            else:
                mark = f"BLOCKED ({cell.reason})"
            self.stdout.write(f"    {day:%Y-%m-%d} {day:%a}  {mark}")


# --- module-level helpers (shared by actions, easy to unit-test) -----------


def _nights_between(date_from: date, date_to: date) -> int:
    """Nights in the half-open range [date_from, date_to) — date_to is checkout."""
    return (date_to - date_from).days


def _demo_property() -> Property:
    """Return the property at PROPERTY_SLUG, creating a minimal one if absent.

    On a seeded DB the slug points at the `ical_demo` seed_dev property, so the
    demo runs against realistic data; on an empty DB (tests) this builds a
    self-contained property + geo/group graph under the same slug.
    """
    from properties.models import (
        Country,
        Property,
        PropertyCategory,
        PropertyGroup,
        Region,
    )

    country, _ = Country.objects.get_or_create(
        iso2="GB",
        defaults={"name": "United Kingdom", "iso3": "GBR"},
    )
    region, _ = Region.objects.get_or_create(
        slug=REGION_SLUG,
        defaults={"country": country, "name": "iCal Demo Region"},
    )
    category, _ = PropertyCategory.objects.get_or_create(
        slug=CATEGORY_SLUG,
        defaults={"name": "iCal Demo Villa"},
    )
    group, _ = PropertyGroup.objects.get_or_create(name=GROUP_NAME)
    prop, _ = Property.objects.get_or_create(
        slug=PROPERTY_SLUG,
        defaults={
            "name": "iCal Demo Villa",
            "display_name": "iCal Demo Villa",
            "category": category,
            "group": group,
            "region": region,
        },
    )
    return prop


def _require_demo_property() -> Property:
    from properties.models import Property

    try:
        return Property.objects.get(slug=PROPERTY_SLUG)
    except Property.DoesNotExist:
        raise CommandError("Demo property not found — run --setup first.") from None


def _demo_owner(email: str, password: str) -> Any:
    from accounts.models import User

    user, _ = User.objects.get_or_create(email=email)
    user.set_password(password)
    user.save()
    return user


def _demo_terms() -> Any:
    from reservations.models import TermsVersion

    terms, _ = TermsVersion.objects.get_or_create(
        version=TERMS_VERSION,
        defaults={"body_markdown": "**Demo terms**", "is_current": False},
    )
    return terms


def _demo_customer() -> Any:
    """Return the demo customer Person, creating it (with its PRIMARY email) on
    first run. GAP-045 D5-1: the demo customer is a CUSTOMER ``Person`` — Guest
    is retired."""
    from accounts.enums import PersonKind
    from accounts.models import Person, PersonEmail

    existing = PersonEmail.objects.filter(email=GUEST_EMAIL).select_related("contact").first()
    if existing is not None:
        return existing.contact
    person = Person.objects.create(
        first_name="Demo",
        last_name="Guest",
        kind=PersonKind.CUSTOMER.value,
    )
    PersonEmail.objects.create(contact=person, email=GUEST_EMAIL, is_primary=True)
    return person


def _demo_currency() -> Any:
    from pricing.models import Currency

    currency, _ = Currency.objects.get_or_create(
        code="GBP",
        defaults={"name": "Pound sterling", "symbol": "£"},
    )
    return currency


def _new_quotation() -> Any:
    from reservations.models import Enquiry, Quotation

    person = _demo_customer()
    return Quotation.objects.create(
        enquiry=Enquiry.objects.create(person=person),
        person=person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=_demo_terms(),
    )


def _place_quotation_clash(prop: Property, date_from: date, date_to: date) -> str:
    """Place an open-quotation hold over the range; returns the quotation ref."""
    from reservations.enums import BookingHoldReason
    from reservations.services.holds import HoldService

    quotation = _new_quotation()
    HoldService.place(
        property=prop,
        date_from=date_from,
        date_to=date_to,
        expires_at=timezone.now() + timedelta(days=7),
        reason=BookingHoldReason.QUOTATION_OPEN.value,
        quotation=quotation,
        notes="iCal demo conflict",
    )
    return quotation.reference


def _place_booking_clash(prop: Property, date_from: date, date_to: date) -> str:
    """Place a confirmed booking over the range; returns the booking ref.

    Built directly (not via BookingService) on purpose: the demo only needs an
    *occupying* booking to trip the conflict guard, not the full
    submit/auto-accept/payment-schedule lifecycle. The shared fabricator keeps
    that shape (and the LEAD BookingGuest invariant) in one place; --reset tears
    it down by relationship to the demo customer.
    """
    from reservations.factories import make_occupying_booking

    booking = make_occupying_booking(
        property=prop,
        person=_demo_customer(),
        currency=_demo_currency(),
        terms=_demo_terms(),
        date_from=date_from,
        date_to=date_to,
    )
    return booking.reference


def _delete_demo_data() -> int:
    """Hard-delete every demo row in dependency order. No soft delete (project rule).

    Everything is unwound by *relationship*, not by hardcoded keys, so it cleans
    up whatever the demo actually created — including a booking-clash booking and
    an owner created under a non-default --owner-email.
    """
    from django.db.models import Q

    from accounts.models import Person, User
    from owners.models import OwnerMembership, OwnerOrganisation, OwnerOrgProperty
    from pricing.models import RatePlan
    from properties.models import (
        Property,
        PropertyCategory,
        PropertyGroup,
        Region,
    )
    from reservations.models import (
        Booking,
        BookingHold,
        Enquiry,
        EnquiryEvent,
        OwnerBlock,
        OwnerBlockUpdate,
        OwnerBlockUpdateSeen,
        Quotation,
        QuotationLine,
    )

    total = 0
    with transaction.atomic():
        # GAP-045 D5-1: the demo customer is a CUSTOMER Person (Guest retired),
        # found by its PRIMARY email. Resolve its id(s) up front (materialised
        # before any delete touches their PersonEmail rows) and erase them last.
        demo_person_ids = list(
            Person.objects.filter(emails__email=GUEST_EMAIL).values_list("pk", flat=True)
        )
        # Person-first ownership predicate, reused at each teardown site so the
        # filters can never drift.
        demo_owned = Q(person_id__in=demo_person_ids)

        prop = Property.objects.filter(slug=PROPERTY_SLUG).first()
        if prop is not None:
            # When the demo runs against a pre-existing (seeded) property, only
            # the demo's own attachments are unwound; the property and its real
            # bookings/quotations/rate plans are left untouched. The aggressive
            # by-property teardown below only applies to a property this
            # command created itself.
            created_by_demo = prop.name == "iCal Demo Villa"

            from reservations.enums import OwnerBlockSource

            blocks = OwnerBlock.objects.filter(property=prop)
            if not created_by_demo:
                blocks = blocks.filter(source=OwnerBlockSource.ICAL.value)
            # OwnerBlock.property is PROTECT, and OwnerBlockUpdate.block PROTECTs
            # the block — so unwind updates (and their per-user seen rows) first.
            block_ids = list(blocks.values_list("pk", flat=True))
            # Each block's availability is enforced by its resulting BookingHold,
            # so the hold must go too or the dates stay blocked. (On the
            # created_by_demo path the property delete CASCADEs holds anyway.)
            hold_ids = [
                hid for hid in blocks.values_list("resulting_hold_id", flat=True) if hid is not None
            ]
            OwnerBlockUpdateSeen.objects.filter(update__block_id__in=block_ids).delete()
            OwnerBlockUpdate.objects.filter(block_id__in=block_ids).delete()
            total += OwnerBlock.objects.filter(pk__in=block_ids).delete()[0]
            total += BookingHold.objects.filter(pk__in=hold_ids).delete()[0]
            # Payment / Refund / SecurityDeposit / BookingEvent all PROTECT the
            # Booking, so clear them first — we don't care about any data on this
            # demo property. Reach them via Booking's reverse relations rather
            # than importing payments (reservations sits below payments in the
            # layering contract). Refund/SecurityDeposit SET_NULL each other and
            # against_payment, so deletion order among the money rows is free.
            demo_bookings = Booking.objects.filter(property=prop)
            if not created_by_demo:
                demo_bookings = demo_bookings.filter(demo_owned)
            for booking in demo_bookings:
                booking.refunds.all().delete()
                booking.security_deposits.all().delete()
                booking.payments.all().delete()
                booking.events.all().delete()
            # A booking-clash booking PROTECTs its quotation_line and property,
            # so it must go after; deleting the Booking CASCADEs its
            # BookingGuest rows (the LEAD guard permits the cascade path).
            total += demo_bookings.delete()[0]
            if created_by_demo:
                # RatePlan PROTECTs the property (and CASCADEs its RateCards).
                total += RatePlan.objects.filter(property=prop).delete()[0]
            # QuotationLine PROTECTs the property too. When tearing down a
            # demo-created property, delete every quotation with a line on it —
            # not just the demo guest's — since the property itself is going;
            # deleting the quotation CASCADEs its lines + holds. Demo-guest
            # quotations may have no line on the property yet, so union them in.
            quotation_ids: set[int] = set()
            if created_by_demo:
                quotation_ids.update(
                    QuotationLine.objects.filter(property=prop).values_list(
                        "quotation_id", flat=True
                    )
                )
            quotation_ids.update(Quotation.objects.filter(demo_owned).values_list("pk", flat=True))
            # Quotation.enquiry PROTECTs the enquiry until the quotation is gone,
            # so collect the candidate enquiries before deleting the quotations.
            enquiry_ids = {
                eid
                for eid in Quotation.objects.filter(pk__in=quotation_ids).values_list(
                    "enquiry_id", flat=True
                )
                if eid is not None
            }
            enquiry_ids.update(Enquiry.objects.filter(demo_owned).values_list("pk", flat=True))
            total += Quotation.objects.filter(pk__in=quotation_ids).delete()[0]
            # Only drop enquiries with no surviving quotation (another quotation
            # on a different property could still PROTECT one).
            orphan_enquiry_ids = [
                eid for eid in enquiry_ids if not Quotation.objects.filter(enquiry_id=eid).exists()
            ]
            # EnquiryEvent PROTECTs its enquiry; EnquiryNote CASCADEs. Clear the
            # events first so the orphaned enquiries can go.
            EnquiryEvent.objects.filter(enquiry_id__in=orphan_enquiry_ids).delete()
            total += Enquiry.objects.filter(pk__in=orphan_enquiry_ids).delete()[0]
            OwnerOrgProperty.objects.filter(property=prop).delete()
            if created_by_demo:
                # The command created this property — delete it outright
                # (CASCADEs its holds and calendar feeds).
                total += prop.delete()[0]
            else:
                # A pre-existing (seeded) property: strip only the demo feeds
                # and leave the property itself alone (demo holds went with
                # their quotations above).
                total += prop.calendar_feeds.all().delete()[0]

        # Erase the demo customer Person(s) (cascades their PersonEmail/
        # PersonPhone children). Resolved before any delete above.
        total += Person.objects.filter(pk__in=demo_person_ids).delete()[0]

        org = OwnerOrganisation.objects.filter(name=ORG_NAME).first()
        if org is not None:
            # Delete every member user (covers a custom --owner-email), then the
            # memberships, then the org.
            member_ids = list(
                OwnerMembership.objects.filter(organisation=org).values_list("user_id", flat=True)
            )
            OwnerMembership.objects.filter(organisation=org).delete()
            total += org.delete()[0]
            total += User.objects.filter(pk__in=member_ids).delete()[0]

        Region.objects.filter(slug=REGION_SLUG).delete()
        PropertyCategory.objects.filter(slug=CATEGORY_SLUG).delete()
        PropertyGroup.objects.filter(name=GROUP_NAME).delete()
    return total
