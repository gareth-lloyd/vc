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
    from properties.models.property import Property

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
            payload = spec.build_payload(obj)
            self.stdout.write(f"[{scenario}/{kind}] pk={obj.pk} payload:")
            self.stdout.write(json.dumps(payload, indent=2, default=str))


# ── scenarios ────────────────────────────────────────────────────────────


def _capture_media(ctx: SampleContext, villa: Property) -> None:
    """`PropertyFactory` writes a `PropertyImage` file that outlives the DB
    rollback — record its storage path so `handle`'s `finally` reaps it."""
    for img in villa.images.all():
        if img.image.name:
            ctx.media_paths.append(img.image.name)


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
        CurrencyFactory,
        ExtraFactory,
        RateBandFactory,
        RatePeriodFactory,
        RatePlanFactory,
    )
    from pricing.models import Currency
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
        CountryFactory,
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

    currency = cast(Currency, CurrencyFactory())  # GBP (first iterator)
    country = CountryFactory()  # GB (first iterator)

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


# Ordered registry: the `--scenarios` vocabulary, and the order `all` runs in.
# `baseline` first, so its records keep landing in the CRM exactly as Limitless
# already mapped them.
_SCENARIOS: dict[str, Callable[[SampleContext], Iterator[PushStep]]] = {
    "baseline": _scenario_baseline,
}
_DEFAULT_SCENARIOS = ("baseline",)
