"""`zoho_send_sample` — build synthetic data covering every enum-transmitting
Zoho Flow payload attribute, push it to the sample webhooks, then roll back.

Ops utility for exercising the GAP-081/082/085/088 payload contracts against
dedicated Zoho Flow sample endpoints so Ben can wire the Zoho-side field
mapping. Unlike a DB scan (which can only demonstrate whatever the local rows
happen to contain), this command *constructs* one synthetic graph inside a
single `transaction.atomic()` block, deterministically populating at least one
example of every attribute that transmits a closed enum (the *enum* axis) —
contact
preferred_method/status/kind/tags/agency + email/phone labels + both
relationship directions; villa status/channel + contact roles + org type +
room placement/floor/ensuite_type/access + bed size + feature service types;
enquiry contact_method/request_type/site_source/status/lead_status/lost_reason
+ note kinds; quote status; booking status/site_source/payment_method +
extras[].category (snapshot ExtraKind AND charge-only damage/credit) +
financials. It pushes each record through the SAME production pipeline as live
traffic (`ensure_pending_record` + a synchronous `push_sync_record`), reads the
resulting `SyncRecord` outcomes, then rolls the whole transaction back so the
dev DB stays clean. The HTTP POSTs to Zoho are the only surviving side effect.

Alongside that sits the *shape* axis (GAP-101): `--scenarios` selects named
generators from `_SCENARIOS`, each originating one awkward payload shape a
single graph cannot reach (a record pushed twice, a cancelled booking, a
discounted line, …). A scenario yields `(kind, objects)` steps and may mutate a
record between two yields — the yield is the push point. `baseline` (the
original single graph, and the only enum-axis carrier) is what a bare run
pushes; every other scenario is opt-in, so a bare run never floods the live
sample flows.

Sample webhook URLs are read from the environment (`ZOHO_SAMPLE_WEBHOOK_*`,
distinct from the `ZOHO_FLOW_WEBHOOK_*` dev settings so auto-push stays off
locally) and `override_settings`'d over `ZOHO_FLOW_WEBHOOKS` for the run, so
`webhook_url()` / `push_sync_record` transparently use them with zero change to
production dispatch code. A kind whose sample URL is unset is reported and
skipped, not failed.

This command lives in `seeding` (not `integrations`): the import-linter layers
contract forbids `integrations` importing reservations/properties/pricing, and
building the synthetic graph needs all three via their factories. `seeding` is
a root package outside the layers list, so it may import anything.

Known accepted side effects (all cleaned up / harmless): `PropertyFactory`
writes one `PropertyImage` media file that survives the DB rollback — the
command captures its storage path and deletes it in a `finally`. Sending the
synthetic quote fires the comms email signal (dev console backend — harmless
noise; the Communication rows roll back with everything else).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction
from django.test.utils import override_settings
from django.utils import timezone

from integrations.services.zoho_flow import (
    ZOHO_FLOW_KINDS,
    ensure_pending_record,
    get_zoho_spec,
    suppress_zoho_push,
)
from integrations.tasks import push_sync_record

if TYPE_CHECKING:
    from accounts.models import Person
    from pricing.models import Currency
    from properties.models.property import Property
    from reservations.models import Booking, Enquiry, Quotation, QuotationLine
    from reservations.models.terms import TermsVersion

# Sample-webhook env var per kind (see module docstring / .env). Deliberately
# distinct names from `ZOHO_FLOW_WEBHOOK_*` so dev/staging settings never pick
# these up — auto-push stays disabled while this command can still reach the
# live sample flows on demand.
_SAMPLE_ENV_VAR = {
    "contact": "ZOHO_SAMPLE_WEBHOOK_CONTACT",
    "villa": "ZOHO_SAMPLE_WEBHOOK_VILLA",
    "enquiry": "ZOHO_SAMPLE_WEBHOOK_ENQUIRY",
    "quote": "ZOHO_SAMPLE_WEBHOOK_QUOTE",
    "booking": "ZOHO_SAMPLE_WEBHOOK_BOOKING",
}

# Every generated name/label is prefixed so the records are unmistakable on the
# Zoho side and never confused with real data.
_TAG = "Synthetic Sample"


# One push: a kind plus the records to send under it. A scenario yields these
# in dependency order, so every nested RES_ID resolves against a record already
# sent. Yielding is the push point — a scenario may mutate a record between two
# yields, which is how re-push / status-transition shapes are originated.
PushStep = tuple[str, list[models.Model]]


@dataclass
class SampleContext:
    """Run-scoped state shared by every scenario in one invocation."""

    media_paths: list[str] = field(default_factory=list)


class Command(BaseCommand):
    help = (
        "Build synthetic data exercising every enum-transmitting Zoho Flow "
        "payload attribute (and, via --scenarios, awkward payload shapes), push "
        "each record to the ZOHO_SAMPLE_WEBHOOK_* endpoints through the "
        "production pipeline, then roll the data back."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Build the synthetic graph and print each payload as JSON "
            "without POSTing anything (still rolls back).",
        )
        parser.add_argument(
            "--kinds",
            help=f"Comma-separated subset of {','.join(ZOHO_FLOW_KINDS)} to push (default: all).",
        )
        parser.add_argument(
            "--scenarios",
            help="Comma-separated payload shapes to originate, or 'all' "
            f"(default: {','.join(_DEFAULT_SCENARIOS)}). Available: "
            f"{','.join(_SCENARIOS)}.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not getattr(settings, "SEED_DEV_ALLOWED", False):
            raise CommandError(
                "zoho_send_sample is disabled here (SEED_DEV_ALLOWED is False). "
                "It fabricates synthetic data and must never run against a "
                "production database."
            )

        kinds = self._resolve_kinds(options.get("kinds"))
        scenarios = self._resolve_scenarios(options.get("scenarios"))
        dry_run: bool = options["dry_run"]

        # Sample URLs from the environment; a kind with no URL is skipped (not
        # failed) — reported below. Dry-run needs no URLs at all.
        sample_urls = {kind: os.environ.get(_SAMPLE_ENV_VAR[kind], "") for kind in ZOHO_FLOW_KINDS}
        if not dry_run:
            self.stdout.write(
                "sample webhook URLs configured: "
                + ", ".join(f"{k}={bool(sample_urls[k])}" for k in ZOHO_FLOW_KINDS)
            )

        # Created before the try so a mid-build failure still reaps its media.
        ctx = SampleContext()
        try:
            # `override_settings` points the production dispatch code at the
            # sample endpoints for the duration of the run only.
            with override_settings(ZOHO_FLOW_WEBHOOKS=sample_urls):
                with transaction.atomic():
                    for name in scenarios:
                        # Suppress auto-enqueue for the whole scenario — build
                        # AND mutations. The service calls and the model saves
                        # between yields would otherwise bump their own (real)
                        # SyncRecords; we push explicitly and deliberately
                        # below, via `ensure_pending_record` + `push_sync_record`,
                        # both of which ignore suppression by design.
                        with suppress_zoho_push():
                            for kind, objects in _SCENARIOS[name](ctx):
                                if kind not in kinds:
                                    continue
                                if dry_run:
                                    self._dry_run_kind(name, kind, objects)
                                else:
                                    self._push_kind(name, kind, objects, sample_urls[kind])

                    # The POSTs already happened synchronously above; discard
                    # all the synthetic rows so the dev DB is untouched.
                    transaction.set_rollback(True)
        finally:
            for path in ctx.media_paths:
                if path and default_storage.exists(path):
                    default_storage.delete(path)

        self.stdout.write(self.style.SUCCESS("done — synthetic data rolled back; dev DB clean"))

    # ── options ────────────────────────────────────────────────────────────

    def _resolve_kinds(self, raw: str | None) -> tuple[str, ...]:
        if not raw:
            return ZOHO_FLOW_KINDS
        requested = tuple(k.strip() for k in raw.split(",") if k.strip())
        unknown = [k for k in requested if k not in ZOHO_FLOW_KINDS]
        if unknown:
            raise CommandError(
                f"Unknown kind(s) {unknown}; expected a subset of {list(ZOHO_FLOW_KINDS)}"
            )
        return requested

    def _resolve_scenarios(self, raw: str | None) -> tuple[str, ...]:
        """Parse `--scenarios`. Raises before any DB access, so a bad name is a
        cheap error rather than a rolled-back build."""
        requested = tuple(s.strip() for s in (raw or "").split(",") if s.strip())
        if not requested:  # unset, or separator-only ("," / " ") — same meaning
            return _DEFAULT_SCENARIOS
        # Validate BEFORE honouring `all`, so `--scenarios all,repsuh` reports the
        # typo instead of silently running everything.
        unknown = [s for s in requested if s != "all" and s not in _SCENARIOS]
        if unknown:
            raise CommandError(
                f"Unknown scenario(s) {unknown}; expected 'all' or a subset of {list(_SCENARIOS)}"
            )
        if "all" in requested:
            return tuple(_SCENARIOS)
        return requested

    # ── delivery ─────────────────────────────────────────────────────────

    def _push_kind(self, scenario: str, kind: str, objects: list[models.Model], url: str) -> None:
        if not url:
            self.stdout.write(f"[{scenario}/{kind}] sample webhook URL unset — skipped")
            return
        for obj in objects:
            record, _ = ensure_pending_record(obj)
            try:
                # Direct call (not .delay): synchronous, exact prod delivery
                # logic; runs on this connection so it sees the uncommitted
                # synthetic rows.
                push_sync_record(record.pk)
            except Exception as exc:  # report and continue to the next object
                self.stdout.write(f"[{scenario}/{kind}] pk={obj.pk} transport/5xx failure: {exc!r}")
            record.refresh_from_db()
            suffix = f" ({record.error_message})" if record.error_message else ""
            self.stdout.write(f"[{scenario}/{kind}] pk={obj.pk} -> {record.status}{suffix}")

    def _dry_run_kind(self, scenario: str, kind: str, objects: list[models.Model]) -> None:
        for obj in objects:
            spec = get_zoho_spec(obj._meta.model)
            assert spec is not None  # every pushed model is registered
            # Re-read exactly as `push_sync_record` does (it builds from
            # `record.target`, a fresh fetch). Building from the in-memory
            # instance would print a DIFFERENT payload wherever a scenario
            # mutated the row through a related object or a service call —
            # `--dry-run` has to show what the real push would send.
            payload = spec.build_payload(type(obj)._base_manager.get(pk=obj.pk))
            self.stdout.write(f"[{scenario}/{kind}] pk={obj.pk} payload:")
            self.stdout.write(json.dumps(payload, indent=2, default=str))


# ── scenarios ────────────────────────────────────────────────────────────


def _capture_media(ctx: SampleContext, villa: Property) -> None:
    """`PropertyFactory` writes a `PropertyImage` file that outlives the DB
    rollback — record its storage path so `handle`'s `finally` reaps it."""
    for img in villa.images.all():
        if img.image.name:
            ctx.media_paths.append(img.image.name)


# ── shared scenario helpers ──────────────────────────────────────────────
# Used by the shape scenarios only. `baseline` deliberately builds its own,
# richer graph inline: it carries the enum axis and is pinned as a verbatim
# move of the original `_build_graph`, so it consumes none of these.

# `CurrencyFactory` and `CountryFactory` draw from process-global
# `factory.Iterator`s (`pricing/factories.py:44`, `properties/factories.py:165`)
# and ADVANCE them on every build, so with N scenarios in one run nobody can
# predict what a bare call returns — and the scenario that runs first silently
# re-denominates the ones after it. Every call site pins its values instead;
# `django_get_or_create` on `code` / `iso2` keeps that idempotent.
_CURRENCY_SPECS = {
    "GBP": ("Pound sterling", "£"),
    "EUR": ("Euro", "€"),
    "USD": ("US dollar", "$"),
}
_COUNTRY_SPECS = {
    "GB": ("GBR", "United Kingdom"),
    "FR": ("FRA", "France"),
    "ES": ("ESP", "Spain"),
}


def _scenario_tag(scenario: str) -> str:
    """Record prefix for one scenario, e.g. `"Synthetic Sample repush"`.

    Namespacing keeps ten scenarios' records apart in the CRM. `baseline` keeps
    the bare `_TAG`, so nothing Limitless has already mapped moves.
    """
    return f"{_TAG} {scenario}"


def _currency(code: str) -> Currency:
    from pricing.factories import CurrencyFactory

    name, symbol = _CURRENCY_SPECS[code]
    return cast("Currency", CurrencyFactory(code=code, name=name, symbol=symbol))


def _country(iso2: str) -> Any:
    """Pin a country by ISO2, for the same reason as `_currency`."""
    from properties.factories import CountryFactory

    iso3, name = _COUNTRY_SPECS[iso2]
    return CountryFactory(iso2=iso2, iso3=iso3, name=name)


def _priceable_villa(ctx: SampleContext, tag: str, *, currency: Currency) -> Property:
    """Villa + one rate plan/period/band — the least the pricing engine needs
    to quote a stay. Baseline's villa also carries rooms, features, contacts and
    extras, none of which a *shape* scenario has any use for."""
    from pricing.factories import RateBandFactory, RatePeriodFactory, RatePlanFactory
    from properties.enums import PropertyChannel, PropertyStatus
    from properties.factories import CountryFactory, PropertyFactory

    villa = cast(
        "Property",
        PropertyFactory(
            name=f"{tag} Villa",
            display_name=f"{tag} Villa",
            status=PropertyStatus.ACTIVE,
            channel=PropertyChannel.AGENT,
            region__country=CountryFactory(),
        ),
    )
    # Capture the PropertyImage path at the point the file is written.
    _capture_media(ctx, villa)
    plan = RatePlanFactory(property=villa, currency=currency, name=f"{tag} rates")
    period = RatePeriodFactory(plan=plan, name=f"{tag} period")
    RateBandFactory(period=period, min_party=1, max_party=30)
    return villa


def _person(tag: str, last_name: str) -> Person:
    from accounts.factories import CustomerPersonFactory

    return cast(
        "Person",
        CustomerPersonFactory(
            first_name=tag,
            last_name=last_name,
            notes=f"{tag} contact.",
        ),
    )


def _terms() -> TermsVersion:
    from reservations.factories import TermsVersionFactory

    return cast("TermsVersion", TermsVersionFactory())


def _enquiry(tag: str, person: Person, villa: Property, **overrides: Any) -> Enquiry:
    from reservations.factories import EnquiryFactory

    return cast(
        "Enquiry",
        EnquiryFactory(
            person=person,
            property=villa,
            inbound_message=f"{tag} enquiry.",
            **overrides,
        ),
    )


def _stay_option(enquiry: Enquiry, villa: Property, **overrides: Any) -> dict[str, Any]:
    """One quotation-line spec matching the enquiry's dates."""
    if enquiry.date_from is None or enquiry.date_to is None:
        raise CommandError("Cannot quote an enquiry with no dates")
    option: dict[str, Any] = {
        "property": villa,
        "date_from": enquiry.date_from,
        "date_to": enquiry.date_to,
        "adults": 2,
        "children": 1,
    }
    option.update(overrides)
    return option


def _sent_quote(
    enquiry: Enquiry,
    terms: TermsVersion,
    options: list[dict[str, Any]],
) -> Quotation:
    """DRAFT -> SENT quote off `enquiry`. SENT because that is the only status
    live traffic ever pushes from (`reservations/apps.py:268` registers the
    quote kind `auto_push=False`; `record_quote_sent` is the sole enqueue)."""
    from reservations.services.quotations import QuotationService

    quotation = QuotationService.create_from_enquiry(
        enquiry,
        options,
        terms_version=terms,
        expires_at=timezone.now() + timedelta(days=14),
    )
    quotation.send()
    return quotation


def _first_line(quotation: Quotation) -> QuotationLine:
    line = quotation.lines.first()
    if line is None:
        raise CommandError("QuotationService produced no lines")
    return line


def _accepted_booking(
    quotation: Quotation,
    line: QuotationLine,
    terms: TermsVersion,
) -> Booking:
    """Accept `line` (quote -> ACCEPTED, enquiry -> CONVERTED) and open the
    booking it commits to."""
    from reservations.enums import PaymentMethod
    from reservations.services.bookings import BookingService

    quotation.accept(line)
    return BookingService.create_from_quotation_line(
        line,
        terms_version=terms,
        payment_method=PaymentMethod.BANK_TRANSFER.value,
    )


def _scenario_baseline(ctx: SampleContext) -> Iterator[PushStep]:
    """The original single graph: one of everything, pushed exactly once in
    dependency order. Covers the enum axis (see the module docstring); this is
    what a bare `zoho_send_sample` run pushes."""
    from accounts.enums import (
        ContactRole,
        EmailLabel,
        OrgStatus,
        OrgType,
        PersonPreferredMethod,
        PersonRelationshipKind,
        PersonTag,
        PhoneLabel,
    )
    from accounts.factories import (
        CustomerPersonFactory,
        OrganisationFactory,
        PersonEmailFactory,
        PersonPhoneFactory,
        PersonRelationshipFactory,
    )

    # Model classes for `cast` — factory-boy factories are typed as the
    # factory class, not the produced instance (the established seed-stage
    # workaround, e.g. `seeding/_booking_helpers.py`).
    from accounts.models import Person
    from pricing.enums import ExtraKind
    from pricing.factories import (
        ExtraFactory,
        RateBandFactory,
        RatePeriodFactory,
        RatePlanFactory,
    )
    from properties.enums import (
        BedSize,
        EnsuiteType,
        FeatureServiceType,
        PropertyChannel,
        PropertyStatus,
        RoomAccess,
        RoomFloor,
        RoomPlacement,
    )
    from properties.factories import (
        FeatureFactory,
        PropertyContactAssignmentFactory,
        PropertyFactory,
        RoomAttributeFactory,
        RoomFactory,
    )
    from properties.models.features import Feature, PropertyFeature
    from properties.models.property import Property
    from properties.models.rooms import Room, RoomAttribute, RoomAttributeAssignment
    from reservations.enums import (
        ChargeCategory,
        ContactMethod,
        EnquiryLostReason,
        EnquiryNoteKind,
        EnquirySource,
        EnquiryStatus,
        LeadStatus,
        PaymentMethod,
    )
    from reservations.factories import (
        EnquiryFactory,
        EnquiryNoteFactory,
        TermsVersionFactory,
    )
    from reservations.models import Enquiry
    from reservations.services.bookings import BookingService
    from reservations.services.charges import ChargeItemService
    from reservations.services.quotations import QuotationService

    # Pinned, not iterator-drawn: `CurrencyFactory`/`CountryFactory` advance a
    # process-global `factory.Iterator`, so a shape scenario running first (the
    # `--scenarios` order is the operator's) would otherwise re-denominate and
    # re-locate baseline's records — exactly what must never move.
    currency = _currency("GBP")
    country = _country("GB")

    # ── organisations (nested inside contact/villa payloads) ───────────
    agency = OrganisationFactory(
        name=f"{_TAG} Agency",
        org_type=OrgType.AGENCY,
        status=OrgStatus.ACTIVE,
        email="agency@synthetic.example",
        phone="+44 20 7000 0000",
        country=country,
        website_url="https://synthetic.example",
        notes=f"{_TAG} agency record.",
    )
    mgmt_org = OrganisationFactory(
        name=f"{_TAG} Management Co",
        org_type=OrgType.MANAGEMENT_COMPANY,
        status=OrgStatus.ACTIVE,
    )

    # ── contacts (P1 with agency + rich labels/tags; P2 owner + PA) ────
    p1 = cast(
        Person,
        CustomerPersonFactory(
            title="Mr",
            first_name=_TAG,
            last_name="Principal",
            agency=agency,
            country=country,
            preferred_method=PersonPreferredMethod.PHONE,
            tags=[PersonTag.VIP.value, PersonTag.TRADE.value, PersonTag.PA.value],
            notes=f"{_TAG} principal contact.",
        ),
    )
    # Factory made a PRIMARY email + MOBILE phone; add a second label of
    # each so emails[].label / phones[].label cover >1 value.
    PersonEmailFactory(
        contact=p1,
        email="principal.work@synthetic.example",
        label=EmailLabel.WORK,
        is_primary=False,
    )
    PersonPhoneFactory(
        contact=p1,
        number="+44 20 7000 0001",
        label=PhoneLabel.HOME,
        is_primary=False,
    )
    p2 = cast(
        Person,
        CustomerPersonFactory(
            first_name=_TAG,
            last_name="PA",
            notes=f"{_TAG} PA / villa owner.",
        ),
    )
    # P1 → P2 as PA: pushing P1 exercises direction="out"/relation="PA";
    # pushing P2 exercises direction="in"/relation="Principal" (the inverse
    # display label).
    PersonRelationshipFactory(
        from_person=p1,
        to_person=p2,
        kind=PersonRelationshipKind.PA,
        note=f"{_TAG} relationship.",
    )

    # ── villa ──────────────────────────────────────────────────────────
    villa = cast(
        Property,
        PropertyFactory(
            name=f"{_TAG} Villa",
            display_name=f"{_TAG} Villa",
            status=PropertyStatus.ACTIVE,
            channel=PropertyChannel.AGENT,
            region__country=country,
        ),
    )
    # `PropertyFactory` writes the PropertyImage file HERE; capture it now so an
    # exception further down still reaps it (e.g. the CommandError below).
    _capture_media(ctx, villa)
    # Owner is a person; management company is an organisation (org is only
    # permitted for the MANAGEMENT_COMPANY role).
    PropertyContactAssignmentFactory(
        property=villa,
        contact=p2,
        role=ContactRole.OWNER,
        is_primary=True,
    )
    PropertyContactAssignmentFactory(
        property=villa,
        organisation=mgmt_org,
        role=ContactRole.MANAGEMENT_COMPANY,
        is_primary=False,
    )

    # Two rooms jointly cover placement / floor / ensuite_type / access;
    # room A also carries a sized double bed + a room attribute.
    room_a = cast(
        Room,
        RoomFactory(
            property=villa,
            name=f"{_TAG} Main Suite",
            placement=RoomPlacement.MAIN_HOUSE,
            floor=RoomFloor.GROUND,
            is_ensuite=True,
            ensuite_type=EnsuiteType.SHOWER,
            access=RoomAccess.INSIDE,
        ),
    )
    room_a.beds.double_size = BedSize.KING.value
    room_a.beds.save(update_fields=["double_size", "updated_at"])
    RoomFactory(
        property=villa,
        name=f"{_TAG} Guest Room",
        placement=RoomPlacement.GUEST_HOUSE,
        floor=RoomFloor.FIRST,
        is_ensuite=True,
        ensuite_type=EnsuiteType.BATH,
        access=RoomAccess.OUTSIDE,
    )
    sea_view = cast(
        RoomAttribute,
        RoomAttributeFactory(
            name=f"{_TAG} Sea view",
            slug="synthetic-sample-sea-view",
        ),
    )
    RoomAttributeAssignment.objects.create(
        room=room_a,
        attribute=sea_view,
        note=f"{_TAG} from the balcony.",
    )

    # Features across all three service types.
    for i, service_type in enumerate(
        (
            FeatureServiceType.AMENITY,
            FeatureServiceType.INCLUDED_SERVICE,
            FeatureServiceType.PAID_ADDON,
        )
    ):
        feature = cast(
            Feature,
            FeatureFactory(
                name=f"{_TAG} feature {service_type.value}",
                service_type=service_type,
            ),
        )
        PropertyFeature.objects.create(property=villa, feature=feature, sort_order=i)

    # ── pricing (so the quote/booking price + snapshot extras) ─────────
    plan = RatePlanFactory(property=villa, currency=currency, name=f"{_TAG} rates")
    period = RatePeriodFactory(plan=plan, name=f"{_TAG} period")
    RateBandFactory(period=period, min_party=1, max_party=30)
    # Two mandatory extras with distinct ExtraKinds — the engine snapshots
    # them into pricing_snapshot["extras"], so booking extras[].category
    # covers snapshot-sourced kinds. Currency MUST equal the plan currency
    # for the engine to apply them.
    ExtraFactory(
        property=villa,
        currency=currency,
        name=f"{_TAG} cleaning",
        kind=ExtraKind.CLEANING,
        is_mandatory=True,
    )
    ExtraFactory(
        property=villa,
        currency=currency,
        name=f"{_TAG} heating",
        kind=ExtraKind.HEATING,
        is_mandatory=True,
    )

    # ── enquiries ──────────────────────────────────────────────────────
    # E1: live, feeds the quote/booking; non-default enum values.
    e1 = cast(
        Enquiry,
        EnquiryFactory(
            person=p1,
            property=villa,
            contact_method=ContactMethod.EMAIL,
            site_source=EnquirySource.AGENT_PORTAL,
            lead_status=LeadStatus.HOT,
            inbound_message=f"{_TAG} enquiry message.",
        ),
    )
    for note_kind in (
        EnquiryNoteKind.GENERAL,
        EnquiryNoteKind.INTERNAL,
        EnquiryNoteKind.PREFERENCES,
    ):
        EnquiryNoteFactory(
            enquiry=e1,
            kind=note_kind,
            body=f"{_TAG} {note_kind.value} note.",
        )
    # E2: dead, so the payload covers status=dead + lost_reason.
    e2 = cast(
        Enquiry,
        EnquiryFactory(
            person=p2,
            property=villa,
            status=EnquiryStatus.DEAD,
            lost_reason=EnquiryLostReason.AVAILABILITY,
            lead_status=LeadStatus.DEAD,
            inbound_message=f"{_TAG} dead enquiry.",
        ),
    )

    # ── quote (from E1) ────────────────────────────────────────────────
    terms = TermsVersionFactory()
    quotation = QuotationService.create_from_enquiry(
        e1,
        [
            {
                "property": villa,
                "date_from": e1.date_from,
                "date_to": e1.date_to,
                "adults": 2,
                "children": 1,
            }
        ],
        terms_version=terms,
        expires_at=timezone.now() + timedelta(days=14),
    )
    line = quotation.lines.first()
    if line is None:
        raise CommandError("QuotationService produced no lines")
    quotation.send()  # DRAFT → SENT (the only status that pushes)

    # ── booking (accept the line, then build) ──────────────────────────
    quotation.accept(line)
    booking = BookingService.create_from_quotation_line(
        line,
        terms_version=terms,
        payment_method=PaymentMethod.BANK_TRANSFER.value,
    )
    # Distinct, non-default site_source so the attribute is demonstrated.
    booking.site_source = EnquirySource.EMAIL_INBOUND.value
    booking.save(update_fields=["site_source", "updated_at"])
    # Charge lines cover extras[].category from the charge source, incl. the
    # charge-only DAMAGE / CREDIT values. Keep the credit small so the
    # booking total stays non-negative (ChargeItemService._check_total).
    ChargeItemService.create(
        booking,
        label=f"{_TAG} damage charge",
        amount=Decimal("120.00"),
        category=ChargeCategory.DAMAGE.value,
        currency=currency,
    )
    ChargeItemService.create(
        booking,
        label=f"{_TAG} goodwill credit",
        amount=Decimal("-25.00"),
        category=ChargeCategory.CREDIT.value,
        currency=currency,
    )
    ChargeItemService.create(
        booking,
        label=f"{_TAG} extra clean",
        amount=Decimal("80.00"),
        category=ChargeCategory.CLEANING.value,
        currency=currency,
    )

    yield ("contact", [p1, p2])  # both persons → both relationship directions
    yield ("villa", [villa])
    yield ("enquiry", [e1, e2])
    yield ("quote", [quotation])
    yield ("booking", [booking])


def _scenario_repush(ctx: SampleContext) -> Iterator[PushStep]:
    """Push the same villa and booking TWICE, mutated in between.

    Every other scenario — and every record the sample flows have ever been
    sent — is an insert. This is the only place an *update* is observable, and
    so the only way to tell an upsert from a duplicate: if the Flow inserts
    rather than upserts, the run leaves two villas and two bookings in the CRM
    instead of one of each, renamed. CHECK-004 item 1 / CHECK-005 item 3.
    """
    from reservations.enums import EnquirySource

    tag = _scenario_tag("repush")
    terms = _terms()
    villa = _priceable_villa(ctx, tag, currency=_currency("GBP"))
    person = _person(tag, "Repush")
    enquiry = _enquiry(tag, person, villa)
    quotation = _sent_quote(enquiry, terms, [_stay_option(enquiry, villa)])
    booking = _accepted_booking(quotation, _first_line(quotation), terms)

    # Full dependency chain first: the booking payload nests `enquiry.RES_ID`
    # and `quote.RES_ID`, and a Flow told to join records it has never seen
    # manufactures the dangling-reference noise `out_of_order` exists to
    # isolate — which would muddy the verdict this scenario is here to give.
    yield ("contact", [person])
    yield ("villa", [villa])
    yield ("enquiry", [enquiry])
    yield ("quote", [quotation])
    yield ("booking", [booking])

    # The same two records, changed. An unmutated re-push would prove nothing:
    # the CRM record would look identical either way. `name` moves as well as
    # `display_name` because the Flow maps `Name<-name` — a villa surfaced by
    # `Name` would otherwise look unchanged across both passes.
    villa.name = f"{tag} Villa (renamed)"
    villa.display_name = f"{tag} Villa (renamed)"
    villa.save(update_fields=["name", "display_name", "updated_at"])
    booking.site_source = EnquirySource.PHONE.value
    booking.save(update_fields=["site_source", "updated_at"])

    yield ("villa", [villa])
    yield ("booking", [booking])


def _scenario_status_transitions(ctx: SampleContext) -> Iterator[PushStep]:
    """Push the same quote and booking at each stage of their lifecycle.

    Both Flows currently hardcode the stage they write — `Quote_Stage:
    "Quoted"`, booking `Status: "Pending Booking"` — regardless of what the
    payload carries, so a record that visibly moves SENT -> ACCEPTED, or opens
    and then cancels, is the shape that makes the omission legible.
    CHECK-004 item 2 / CHECK-005 item 4.

    Two enquiries, not one: `create_from_enquiry` refuses a DEAD or CONVERTED
    enquiry (`quotations.py:299`) and `accept()` converts the parent
    (`models/quotation.py:194`), so the accepted quote and the cancelled quote
    cannot share a source enquiry.
    """
    # Tag == registry key, deliberately: the scenario name is the shared
    # verification vocabulary with Limitless ("run `--scenarios
    # status_transitions` and read those records"), so the name you type and
    # the prefix in the CRM must be the same string.
    tag = _scenario_tag("status_transitions")
    terms = _terms()
    villa = _priceable_villa(ctx, tag, currency=_currency("GBP"))
    person = _person(tag, "Transitions")

    yield ("contact", [person])
    yield ("villa", [villa])

    # Q1: SENT -> ACCEPTED, then the booking it opens -> CANCELLED.
    e1 = _enquiry(tag, person, villa)
    yield ("enquiry", [e1])  # NEW
    q1 = _sent_quote(e1, terms, [_stay_option(e1, villa)])
    yield ("enquiry", [e1])  # QUOTE_SENT — the stage the Flow hardcodes past
    yield ("quote", [q1])  # SENT
    booking = _accepted_booking(q1, _first_line(q1), terms)
    yield ("quote", [q1])  # ACCEPTED
    # `accept()` converts the enquiry through its OWN instance (`refresh_locked`
    # drops the cached FK), so `e1` is stale here — refresh or this yields NEW.
    e1.refresh_from_db()
    yield ("enquiry", [e1])  # CONVERTED
    yield ("booking", [booking])
    booking.cancel(f"{tag} cancelled after confirmation")
    yield ("booking", [booking])

    # Q2: SENT -> CANCELLED — the quote that never converts.
    e2 = _enquiry(tag, person, villa)
    yield ("enquiry", [e2])
    q2 = _sent_quote(e2, terms, [_stay_option(e2, villa)])
    yield ("quote", [q2])
    q2.cancel(f"{tag} withdrawn")
    yield ("quote", [q2])


def _scenario_multi_option_quote(ctx: SampleContext) -> Iterator[PushStep]:
    """One quotation carrying THREE alternative lines, one of them selected.

    Every quote the sample flows have seen has exactly one line, so the Flow's
    handling of alternatives is untested: which line drives the CRM Deal
    figures, and whether the unselected two are carried at all.
    CHECK-005 item 1.
    """
    tag = _scenario_tag("multi_option_quote")
    terms = _terms()
    villa_a = _priceable_villa(ctx, f"{tag} A", currency=_currency("GBP"))
    villa_b = _priceable_villa(ctx, f"{tag} B", currency=_currency("GBP"))
    person = _person(tag, "Options")
    enquiry = _enquiry(tag, person, villa_a)

    yield ("contact", [person])
    yield ("villa", [villa_a, villa_b])
    yield ("enquiry", [enquiry])

    # Two properties, three shapes: the guest is choosing between villas AND
    # between stay lengths, which is what a real alternative-options quote is.
    longer_stay = _stay_option(enquiry, villa_a)
    longer_stay["date_to"] = longer_stay["date_to"] + timedelta(days=7)
    quotation = _sent_quote(
        enquiry,
        terms,
        [_stay_option(enquiry, villa_a), longer_stay, _stay_option(enquiry, villa_b, adults=4)],
    )
    yield ("quote", [quotation])

    # `accept()` is what marks a line selected — there is no other path.
    booking = _accepted_booking(quotation, _first_line(quotation), terms)
    yield ("quote", [quotation])
    yield ("booking", [booking])


def _scenario_discounted(ctx: SampleContext) -> Iterator[PushStep]:
    """A quotation line with a real operator discount netted off its total.

    Every sample line so far has `discount: "0.00"`, so the CRM mapping for a
    discounted stay has never been exercised (CHECK-005 item 2). Repricing is
    what applies it: `price_line` stamps `pricing_snapshot["gross"]` and sets
    `total = gross - discount` (`quotations.py:83-89`).

    The booking is pushed deliberately, unasserted: BUG-020 copies the
    snapshot's GROSS onto the booking, so its `financials` block still shows
    the undiscounted figure. That divergence is the point — it is visible in
    the CRM side by side with the quote, rather than argued in a ticket.
    """
    from reservations.services.quotations import QuotationService

    tag = _scenario_tag("discounted")
    terms = _terms()
    villa = _priceable_villa(ctx, tag, currency=_currency("GBP"))
    person = _person(tag, "Discount")
    enquiry = _enquiry(tag, person, villa)

    yield ("contact", [person])
    yield ("villa", [villa])
    yield ("enquiry", [enquiry])

    quotation = _sent_quote(enquiry, terms, [_stay_option(enquiry, villa)])
    line = _first_line(quotation)
    line.discount = Decimal("250.00")
    line.save(update_fields=["discount", "updated_at"])
    # Pin the currency, as every reprice must (`quotations.py:64-68`).
    QuotationService.price_line(quotation, line, currency=line.currency)
    yield ("quote", [quotation])

    booking = _accepted_booking(quotation, line, terms)
    yield ("booking", [booking])


def _scenario_mixed_currency(ctx: SampleContext) -> Iterator[PushStep]:
    """One quotation whose two lines are denominated differently.

    A Quotation carries no header currency by design (GAP-014: currency is
    per line, and mixed quotes are expected, not normalised). Nothing has ever
    demonstrated that to the Flow, so a CRM mapping that reads "the quote's
    currency" off the first line is unfalsified. CHECK-005 item 5.
    """
    tag = _scenario_tag("mixed_currency")
    terms = _terms()
    villa_gbp = _priceable_villa(ctx, f"{tag} GBP", currency=_currency("GBP"))
    villa_eur = _priceable_villa(ctx, f"{tag} EUR", currency=_currency("EUR"))
    person = _person(tag, "Currencies")
    enquiry = _enquiry(tag, person, villa_gbp)

    yield ("contact", [person])
    yield ("villa", [villa_gbp, villa_eur])
    yield ("enquiry", [enquiry])

    # No `currency=` on either option: each line takes its own plan's currency.
    quotation = _sent_quote(
        enquiry,
        terms,
        [_stay_option(enquiry, villa_gbp), _stay_option(enquiry, villa_eur)],
    )
    yield ("quote", [quotation])


def _scenario_sparse_financials(ctx: SampleContext) -> Iterator[PushStep]:
    """A booking whose whole `financials` block is null.

    A manual quotation line is never priced, so `pricing_snapshot` stays `{}`
    (`quotations.py:344-350`), `create_from_quotation_line` copies that verbatim
    (`bookings.py:64`), and `owner_money_from_snapshot` returns None — every one
    of the eight GAP-085 figures lands null (`zoho_payload.py:265`). This is the
    shape the spreadsheet-imported historic bookings will arrive in, so it is
    the one the Flow most needs to survive rather than the fully-priced case.
    CHECK-004 item 5.
    """
    tag = _scenario_tag("sparse_financials")
    terms = _terms()
    currency = _currency("GBP")
    villa = _priceable_villa(ctx, tag, currency=currency)
    person = _person(tag, "Manual")
    enquiry = _enquiry(tag, person, villa)

    yield ("contact", [person])
    yield ("villa", [villa])
    yield ("enquiry", [enquiry])

    quotation = _sent_quote(
        enquiry,
        terms,
        [
            _stay_option(
                enquiry,
                villa,
                is_manual=True,
                total=Decimal("4500.00"),
                currency=currency,
            )
        ],
    )
    yield ("quote", [quotation])

    booking = _accepted_booking(quotation, _first_line(quotation), terms)
    yield ("booking", [booking])


def _scenario_anonymised_person(ctx: SampleContext) -> Iterator[PushStep]:
    """Push a contact, erase them, push again — and watch nothing happen.

    The only scenario that demonstrates an ABSENCE. `push_sync_record` parks an
    ANONYMIZED person's record DISABLED and never POSTs (`tasks.py:77-82`), so
    the second pass is silent and the CRM keeps the pre-erasure name, email and
    phone forever. Res is then *more* erased than Zoho, which is the whole of
    GAP-095 stated as an observation rather than an argument.

    Order matters: the person MUST be pushed before `anonymize()`, or both
    passes are silent and the scenario shows nothing.
    """
    tag = _scenario_tag("anonymised_person")
    # Exactly one email and one phone (the factory's own): `anonymize()` blanks
    # every channel in lockstep, and a second row of either kind collides on
    # `unique_contact_phone` / `unique_contact_email` the moment both are "".
    # Worth a ticket of its own — see the GAP-101 close-out.
    person = _person(tag, "Erasure")

    yield ("contact", [person])  # delivered: full PII reaches the CRM

    person.anonymize()

    # Yielded exactly as before. The pipeline — not this command — is what
    # refuses; the push is reported `-> disabled` and no HTTP call is made.
    yield ("contact", [person])


def _scenario_agency_only_contact(ctx: SampleContext) -> Iterator[PushStep]:
    """A contact who has an agency and no personal name of their own.

    GAP-029 made the name-OR-agency floor legal in res: a B2B contact may be
    nothing but their agency. Zoho's Contacts module makes `Last_Name`
    mandatory, so this payload is the one the Flow is most likely to have the
    CRM reject outright — and, per GAP-097, a rejection is currently invisible
    to us because the Flow still answers 2xx. CHECK-001 item 2.
    """
    from accounts.enums import OrgStatus, OrgType
    from accounts.factories import CustomerPersonFactory, OrganisationFactory

    tag = _scenario_tag("agency_only_contact")
    agency = OrganisationFactory(
        name=f"{tag} Agency",
        org_type=OrgType.AGENCY,
        status=OrgStatus.ACTIVE,
        email="agency.only@synthetic.example",
    )
    person = cast(
        "Person",
        CustomerPersonFactory(
            title="",
            first_name="",
            last_name="",
            agency=agency,
            notes=f"{tag} — booked under the agency, no personal name held.",
        ),
    )

    yield ("contact", [person])


# Ordered registry: the `--scenarios` vocabulary, and the order `all` runs in.
# `baseline` first, so its records keep landing in the CRM exactly as Limitless
# already mapped them.
_SCENARIOS: dict[str, Callable[[SampleContext], Iterator[PushStep]]] = {
    "baseline": _scenario_baseline,
    "repush": _scenario_repush,
    "status_transitions": _scenario_status_transitions,
    "multi_option_quote": _scenario_multi_option_quote,
    "discounted": _scenario_discounted,
    "mixed_currency": _scenario_mixed_currency,
    "sparse_financials": _scenario_sparse_financials,
    "anonymised_person": _scenario_anonymised_person,
    "agency_only_contact": _scenario_agency_only_contact,
}
_DEFAULT_SCENARIOS = ("baseline",)
