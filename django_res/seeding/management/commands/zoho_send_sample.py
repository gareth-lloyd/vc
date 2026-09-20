"""`zoho_send_sample` — construct awkward synthetic records, push them to the
Zoho Flow sample webhooks through the production pipeline, then roll back.

Ops utility for exercising the GAP-081/082/085/088 payload contracts against
dedicated sample endpoints so Ben can wire the Zoho-side field mapping. Unlike
a DB scan — which can only demonstrate whatever the local rows happen to
contain — this command *constructs* what it needs, inside one
`transaction.atomic()` block that is rolled back at the end. The HTTP POSTs to
Zoho are the only surviving side effect.

The fixtures span two axes, and they are different questions.

**The enum axis — "is every value mapped?"** `baseline` populates at least one
example of every attribute that transmits a closed enum: contact
preferred_method/status/kind/tags/agency + email/phone labels + both
relationship directions; villa status/channel + contact roles + org type +
room placement/floor/ensuite_type/access + bed size + feature service types +
extras category/calc (GAP-102 catalogue);
enquiry contact_method/request_type/site_source/status/lead_status/lost_reason
+ note kinds; quote status; booking status/site_source/payment_method +
extras[].category (snapshot ExtraKind AND charge-only damage/credit) +
financials. `test_every_enum_transmitting_attribute_is_covered` pins this, and
it runs against `baseline` alone — keep it that way.

**The shape axis — "does the awkward case survive?" (GAP-101).** Enum coverage
says nothing about *structure*, and a single graph is structurally the simplest
instance of everything: one line, no discount, one currency, every record
pushed exactly once. Eleven of the highest-severity CHECK-001/003/004/005
findings were unreachable from it — insert-only semantics are not even
observable when nothing is ever pushed twice. So `--scenarios` selects named
generators from `_SCENARIOS`, each originating one shape:

    baseline             the enum-axis graph above (what a bare run pushes)
    repush               a villa + booking pushed twice, mutated in between
    status_transitions   enquiry/quote/booking pushed at each lifecycle stage
    multi_option_quote   three alternative lines, one selected
    discounted           a line with a real discount netted off its total
    mixed_currency       two lines in one quote, GBP and EUR
    sparse_financials    a manual line, so all eight owner figures are null
    anonymised_person    push, erase, push again — the second push sends nothing
    agency_only_contact  an agency contact with no personal name
    villa_churn          a villa that lost a room and changed manager
    out_of_order         a booking that arrives before its villa

A scenario is a generator, not a data structure: it yields `(kind, objects)`
steps, and the yield IS the push point, so it may mutate a record between two
yields. That is what makes push -> mutate -> push expressible at all. Whole
scenarios run inside `suppress_zoho_push()`; the explicit pushes still land
because `ensure_pending_record` / `push_sync_record` ignore suppression by
design.

Two rules when adding one. Every record must be prefixed `f"{_TAG} {name}"` so
the CRM stays legible and the scenario name is the shared vocabulary with
Limitless ("run `--scenarios repush,discounted` and read those records"). And
nothing may be drawn from a factory's process-global `factory.Iterator` —
currency, country and nightly rate are all pinned at every call site, because
an unpinned draw makes the records depend on how many scenarios ran first, and
silently moves `baseline`, which Limitless has already mapped.

Default is `baseline` only. `--scenarios all` is one flag away, but a bare run
must not fire ~60 POSTs at the live sample flows.

Sample webhook URLs are read from the environment (`ZOHO_SAMPLE_WEBHOOK_*`,
distinct from the `ZOHO_FLOW_WEBHOOK_*` dev settings so auto-push stays off
locally) and `override_settings`'d over `ZOHO_FLOW_WEBHOOKS` for the run, so
`webhook_url()` / `push_sync_record` transparently use them with zero change to
production dispatch code. A kind whose sample URL is unset is reported and
skipped, not failed.

Note what a run does NOT tell you: `push_sync_record` stamps `IN_SYNC` on any
2xx, and the Flow answers 2xx even when the CRM write it attempted failed
(GAP-097). This command makes the awkward inputs reachable; reading the outcome
is still a human opening the Zoho record.

This command lives in `seeding` (not `integrations`): the import-linter layers
contract forbids `integrations` importing reservations/properties/pricing, and
building the synthetic graph needs all three via their factories. `seeding` is
a root package outside the layers list, so it may import anything.

Known side effects: `PropertyFactory` writes a `PropertyImage` media file per
villa that survives the DB rollback — each is captured at the moment it is
written and deleted in a `finally`. Nothing else escapes: sending the synthetic
quote does fire the comms email signal, but `EmailService.send` dispatches via
`transaction.on_commit` (`comms/services.py:238-246`) and the rollback discards
those hooks, so no email is ever sent and the Communication rows roll back with
everything else.
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
    is_anonymized_person,
    suppress_zoho_push,
    with_provenance,
)
from integrations.tasks import push_sync_record

if TYPE_CHECKING:
    from accounts.models import Organisation, Person
    from pricing.models import Currency
    from properties.models.contacts import PropertyContactAssignment
    from properties.models.property import Property
    from properties.models.rooms import Room
    from reservations.models import Booking, Enquiry, Quotation, QuotationLine
    from reservations.models.terms import TermsVersion

# Sample-webhook env var per kind (see module docstring / .env). Deliberately
# distinct names from `ZOHO_FLOW_WEBHOOK_*` so dev/staging settings never pick
# these up — auto-push stays disabled while this command can still reach the
# live sample flows on demand.
_SAMPLE_ENV_VAR = {
    "organisation": "ZOHO_SAMPLE_WEBHOOK_ORGANISATION",
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
            if is_anonymized_person(obj):
                # `push_sync_record` would park this DISABLED and send nothing
                # (`tasks.py:77-82`). Printing the payload anyway would show the
                # exact opposite of what `anonymised_person` demonstrates — and
                # would put erased PII sentinels on screen.
                self.stdout.write(f"[{scenario}/{kind}] pk={obj.pk} -> DISABLED (not sent)")
                continue
            # Re-read exactly as `push_sync_record` does (it builds from
            # `record.target`, a fresh fetch). Building from the in-memory
            # instance would print a DIFFERENT payload wherever a scenario
            # mutated the row through a related object or a service call —
            # `--dry-run` has to show what the real push would send.
            # Same envelope `push_sync_record` sends (GAP-102), keyed on the
            # registry's `spec.kind` exactly as the task is — a dry run has no
            # SyncRecord, so `sync_record_id` is null. The body is the whole
            # story here; the wire also carries `X-Res-Env: <_meta.env>`.
            payload = with_provenance(
                spec.build_payload(type(obj)._base_manager.get(pk=obj.pk)), spec.kind, None
            )
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
# `RateBandFactory.nightly` is iterator-drawn too, and it propagates into every
# money figure downstream — the quote line total, the booking total, all eight
# GAP-085 financials. Pinned so those figures depend only on the scenario.
_NIGHTLY_RATE = Decimal("400.00")


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
    from properties.factories import PropertyFactory

    villa = cast(
        "Property",
        PropertyFactory(
            name=f"{tag} Villa",
            display_name=f"{tag} Villa",
            status=PropertyStatus.ACTIVE,
            channel=PropertyChannel.AGENT,
            region__country=_country("GB"),
        ),
    )
    # Capture the PropertyImage path at the point the file is written.
    _capture_media(ctx, villa)
    plan = RatePlanFactory(property=villa, currency=currency, name=f"{tag} rates")
    period = RatePeriodFactory(plan=plan, name=f"{tag} period")
    # `nightly` is another process-global iterator draw; pin it or every quote,
    # booking total and financials figure in the run depends on how many villas
    # were built before it.
    RateBandFactory(period=period, min_party=1, max_party=30, nightly=_NIGHTLY_RATE)
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
        DescriptionSection,
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
    from properties.models.descriptions import PropertyDescription
    from properties.models.features import Feature, PropertyFeature
    from properties.models.property import Property
    from properties.models.rooms import Room, RoomAttribute, RoomAttributeAssignment
    from properties.other_information_catalog import (
        OTHER_INFORMATION_CATEGORY_SLUG,
        sync_other_information_tags,
        tag_slug,
    )
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
    agency = cast(
        "Organisation",
        OrganisationFactory(
            name=f"{_TAG} Agency",
            org_type=OrgType.AGENCY,
            status=OrgStatus.ACTIVE,
            email="agency@synthetic.example",
            phone="+44 20 7000 0000",
            country=country,
            website_url="https://synthetic.example",
            notes=f"{_TAG} agency record.",
        ),
    )
    mgmt_org = cast(
        "Organisation",
        OrganisationFactory(
            name=f"{_TAG} Management Co",
            org_type=OrgType.MANAGEMENT_COMPANY,
            status=OrgStatus.ACTIVE,
        ),
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

    # GAP-091 "Other information": one catalog tag (rides `other_information.tags`,
    # NOT `features[]`) plus the free-text description. The catalog sync is
    # idempotent and rolls back with everything else.
    sync_other_information_tags()
    # Resolve the way the catalog does (legacy_id first, then slug): the sync
    # skips a row that exists under either key without rewriting it, so a
    # slug/category lookup could raise on a curated staging DB.
    pets_allowed = (
        Feature.objects.filter(legacy_id="128").first()
        or Feature.objects.filter(slug=tag_slug("Pets allowed")).first()
    )
    assert pets_allowed is not None, "sync_other_information_tags() guarantees this row"
    if pets_allowed.category.slug != OTHER_INFORMATION_CATEGORY_SLUG:
        raise CommandError(
            "the 'Pets allowed' tag has been moved out of the other-information "
            "category on this DB; the baseline scenario cannot exercise the block"
        )
    PropertyFeature.objects.create(property=villa, feature=pets_allowed, sort_order=3)
    PropertyDescription.objects.create(
        property=villa,
        section=DescriptionSection.OTHER_INFORMATION,
        body=f"{_TAG}: small dogs welcome by prior arrangement; no smoking indoors.",
    )

    # ── pricing (so the quote/booking price + snapshot extras) ─────────
    plan = RatePlanFactory(property=villa, currency=currency, name=f"{_TAG} rates")
    period = RatePeriodFactory(plan=plan, name=f"{_TAG} period")
    RateBandFactory(period=period, min_party=1, max_party=30, nightly=_NIGHTLY_RATE)
    # Two mandatory extras with distinct ExtraKinds — they ride the villa
    # push as its extras[] catalogue (GAP-102, so create them BEFORE the villa
    # yields) and the engine snapshots them into pricing_snapshot["extras"],
    # so booking extras[].category covers snapshot-sourced kinds. Currency
    # MUST equal the plan currency for the engine to apply them.
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

    # Organisations first (GAP-096): the contact and villa payloads below nest
    # these RES_IDs, so the Accounts must already exist for CHECK-001 /
    # CHECK-003 to verify a lookup rather than an inline create.
    yield ("organisation", [agency, mgmt_org])
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
    # Exactly one phone (the factory's own). `anonymize()` gives each email a
    # per-row sentinel but blanks EVERY phone to "", so a person holding two
    # numbers violates `unique_contact_phone` and cannot be erased at all —
    # BUG-024. Add a second phone here once that lands.
    person = _person(tag, "Erasure")

    yield ("contact", [person])  # delivered: full PII reaches the CRM

    person.anonymize()

    # Yielded exactly as before. The pipeline — not this command — is what
    # refuses; the push is reported `-> DISABLED` and no HTTP call is made.
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
    agency = cast(
        "Organisation",
        OrganisationFactory(
            name=f"{tag} Agency",
            org_type=OrgType.AGENCY,
            status=OrgStatus.ACTIVE,
            email="agency.only@synthetic.example",
        ),
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

    # The agency is pushed on its own endpoint first, so the contact's `agency`
    # block has a real Account to resolve against — the whole point of
    # CHECK-001 item 1 is whether the Flow links to it or re-creates it.
    yield ("organisation", [agency])
    yield ("contact", [person])


def _scenario_villa_churn(ctx: SampleContext) -> Iterator[PushStep]:
    """A villa that SHRINKS between pushes: a room deleted, the management
    company replaced.

    Every villa the sample flows have seen only ever grew. Two failures hide in
    that: a Flow that upserts subform rows without reconciling deletions leaves
    a phantom bedroom in the CRM forever (CHECK-003 item 3), and one that reads
    `contacts[role=management_company]` without honouring `end_date` can pick
    the superseded assignment (CHECK-003 item 2) — which is why the ended row is
    deliberately left on the wire rather than deleted.

    The replacement organisation is a *different* one, so
    `unique_active_role_org_assignment` (property, organisation, role) never
    collides; the outgoing row is end-dated and demoted first so
    `one_primary_per_role` stays satisfiable.
    """
    from accounts.enums import ContactRole, OrgStatus, OrgType
    from accounts.factories import OrganisationFactory
    from properties.factories import PropertyContactAssignmentFactory, RoomFactory

    tag = _scenario_tag("villa_churn")
    villa = _priceable_villa(ctx, tag, currency=_currency("GBP"))
    RoomFactory(property=villa, name=f"{tag} Main Suite")
    doomed_room = cast("Room", RoomFactory(property=villa, name=f"{tag} Annexe"))
    outgoing = cast(
        "Organisation",
        OrganisationFactory(
            name=f"{tag} Management Co (outgoing)",
            org_type=OrgType.MANAGEMENT_COMPANY,
            status=OrgStatus.ACTIVE,
        ),
    )
    outgoing_assignment = cast(
        "PropertyContactAssignment",
        PropertyContactAssignmentFactory(
            property=villa,
            organisation=outgoing,
            role=ContactRole.MANAGEMENT_COMPANY,
            is_primary=True,
        ),
    )

    yield ("organisation", [outgoing])
    yield ("villa", [villa])

    # `RoomBeds` and `RoomAttributeAssignment` CASCADE off Room, so this is a
    # clean delete — the villa simply has one fewer bedroom than last push.
    doomed_room.delete()

    incoming = cast(
        "Organisation",
        OrganisationFactory(
            name=f"{tag} Management Co (incoming)",
            org_type=OrgType.MANAGEMENT_COMPANY,
            status=OrgStatus.ACTIVE,
        ),
    )
    # Pushed BEFORE the second villa: both management companies exist as
    # Accounts, so picking the superseded assignment (CHECK-003 item 2) shows
    # up as the villa linked to the wrong one, not as a missing link.
    yield ("organisation", [incoming])
    outgoing_assignment.end_date = timezone.now().date()
    outgoing_assignment.is_primary = False
    outgoing_assignment.save(update_fields=["end_date", "is_primary", "updated_at"])
    PropertyContactAssignmentFactory(
        property=villa,
        organisation=incoming,
        role=ContactRole.MANAGEMENT_COMPANY,
        is_primary=True,
    )

    yield ("villa", [villa])


def _scenario_out_of_order(ctx: SampleContext) -> Iterator[PushStep]:
    """A booking that arrives BEFORE the villa it books.

    `limitless_insert_booking` COQLs Products by RES_ID and, on a miss, creates
    a stub villa from the thin `region` object the booking payload carries — no
    location, no capacity, no rooms, no features. That stub is a second-class
    Product the villa upsert then has to reconcile, and its duplicate-name
    branch is where a booking attached to the WRONG villa becomes reachable
    (CHECK-004 item 6). The stub path is a legitimate safety net; this scenario
    exists to show what it actually produces, and to give GAP-096's
    villa-before-booking ordering fix something concrete to be measured against.
    """
    tag = _scenario_tag("out_of_order")
    terms = _terms()
    villa = _priceable_villa(ctx, tag, currency=_currency("GBP"))
    person = _person(tag, "OutOfOrder")
    enquiry = _enquiry(tag, person, villa)
    quotation = _sent_quote(enquiry, terms, [_stay_option(enquiry, villa)])
    booking = _accepted_booking(quotation, _first_line(quotation), terms)

    # Deliberately inverted. Everything else in this command is dependency
    # ordered; this is the one place that isn't, and that is the whole point.
    yield ("booking", [booking])
    yield ("contact", [person])
    yield ("enquiry", [enquiry])
    yield ("quote", [quotation])
    yield ("villa", [villa])


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
    "villa_churn": _scenario_villa_churn,
    "out_of_order": _scenario_out_of_order,
}
_DEFAULT_SCENARIOS = ("baseline",)
