"""FilterSets for the reservations app collection endpoints."""

from __future__ import annotations

from typing import Any, cast

from django.db.models import Exists, OuterRef, Q, QuerySet
from django.db.models.expressions import Combinable
from django_filters import rest_framework as filters

from accounts.enums import PersonTag
from accounts.models import Person, PersonEmail
from reservations.enums import TERMINAL_BOOKING_STATUSES
from reservations.models import Booking, Enquiry, Quotation


class EnquiryFilter(filters.FilterSet):
    """Filter shape for `GET /enquiries`."""

    status = filters.CharFilter(field_name="status")
    lead_status = filters.CharFilter(field_name="lead_status")
    lost_reason = filters.CharFilter(field_name="lost_reason")
    site = filters.CharFilter(field_name="site_source")
    assigned_to = filters.CharFilter(method="filter_assigned_to")
    source = filters.CharFilter(field_name="site_source")
    created_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")
    q = filters.CharFilter(method="filter_q")

    class Meta:
        model = Enquiry
        fields = [
            "status",
            "lead_status",
            "lost_reason",
            "site",
            "assigned_to",
            "source",
            "created_after",
            "created_before",
            "q",
        ]

    def filter_assigned_to(
        self, queryset: QuerySet[Enquiry], _name: str, value: str
    ) -> QuerySet[Enquiry]:
        """Salesperson filter: a numeric user id (exact), or the `unassigned`
        sentinel for IS NULL (the dashboard's "— Unassigned —" option, which a
        plain NumberFilter can't express). Anything else is ignored."""
        if not value:
            return queryset
        if value == "unassigned":
            return queryset.filter(assigned_to__isnull=True)
        if value.isdigit():
            return queryset.filter(assigned_to_id=int(value))
        return queryset

    def filter_q(self, queryset: QuerySet[Enquiry], _name: str, value: str) -> QuerySet[Enquiry]:
        if not value:
            return queryset
        return queryset.filter(
            Q(reference__icontains=value)
            | Q(first_name__icontains=value)
            | Q(last_name__icontains=value)
            | Q(email__icontains=value)
            | Q(inbound_message__icontains=value)
        )


class QuotationFilter(filters.FilterSet):
    """Filter shape for `GET /quotations`."""

    status = filters.CharFilter(field_name="status")
    enquiry = filters.NumberFilter(field_name="enquiry_id")
    created_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")
    q = filters.CharFilter(method="filter_q")

    class Meta:
        model = Quotation
        fields = ["status", "enquiry", "created_after", "created_before", "q"]

    def filter_q(
        self, queryset: QuerySet[Quotation], _name: str, value: str
    ) -> QuerySet[Quotation]:
        if not value:
            return queryset
        # Mirrors BookingFilter.filter_q: customer search resolves from the
        # unified Person (GAP-045). `person__first_name`/`last_name` are
        # single-valued FK joins → safe in the OR. The person EMAIL lives in the
        # multi-valued PersonEmail child, so an OR'd join would multiply rows and
        # inflate the paginator COUNT (django_res/CLAUDE.md) — match it with a
        # scalar Exists() subquery, which adds no JOIN.
        person_email_match = PersonEmail.objects.filter(
            contact_id=OuterRef("person_id"), email__icontains=value
        )
        return queryset.filter(
            Q(reference__icontains=value)
            | Q(person__first_name__icontains=value)
            | Q(person__last_name__icontains=value)
            | Q(Exists(person_email_match))
        )


class BookingFilter(filters.FilterSet):
    """Filter shape for `GET /bookings`."""

    status = filters.CharFilter(field_name="status")
    property = filters.NumberFilter(field_name="property_id")
    assigned_to = filters.NumberFilter(field_name="assigned_to_id")
    site = filters.CharFilter(field_name="site_source")
    check_in_after = filters.DateFilter(field_name="date_from", lookup_expr="gte")
    check_in_before = filters.DateFilter(field_name="date_from", lookup_expr="lte")
    check_out_after = filters.DateFilter(field_name="date_to", lookup_expr="gte")
    check_out_before = filters.DateFilter(field_name="date_to", lookup_expr="lte")
    exclude_terminal = filters.BooleanFilter(method="filter_exclude_terminal")
    q = filters.CharFilter(method="filter_q")

    class Meta:
        model = Booking
        fields: list[Any] = [
            "status",
            "property",
            "assigned_to",
            "site",
            "check_in_after",
            "check_in_before",
            "check_out_after",
            "check_out_before",
            "exclude_terminal",
            "q",
        ]

    def filter_exclude_terminal(
        self, queryset: QuerySet[Booking], _name: str, value: bool
    ) -> QuerySet[Booking]:
        if not value:
            return queryset
        return queryset.exclude(status__in=TERMINAL_BOOKING_STATUSES)

    def filter_q(self, queryset: QuerySet[Booking], _name: str, value: str) -> QuerySet[Booking]:
        if not value:
            return queryset
        # GAP-045 Unit 3d-3: customer search resolves solely from the unified
        # Person. `person__first_name`/`last_name` are single-valued FK joins →
        # safe in the OR. The person EMAIL lives in a multi-valued child table, so
        # an OR'd `person__emails__email` join would multiply rows and leak into
        # the paginator COUNT / StatusCountsMixin (django_res/CLAUDE.md). Match
        # it with a scalar `Exists()` subquery instead, which adds no JOIN.
        person_email_match = PersonEmail.objects.filter(
            contact_id=OuterRef("person_id"), email__icontains=value
        )
        return queryset.filter(
            Q(reference__icontains=value)
            | Q(person__first_name__icontains=value)
            | Q(person__last_name__icontains=value)
            | Q(Exists(person_email_match))
            | Q(property__name__icontains=value)
        )


def client_agent_capacity_expression() -> Combinable:
    """Boolean: the Person is *agent-capacity* — the Clients directory's "agent"
    axis (GAP-047 + GAP-053, which folds agents into Clients rather than giving
    them a separate page).

    True when the person:
      - belongs to an agency Organisation (GAP-046), OR
      - deals through a travel agent: any enquiry/quote/booking on which they are
        the client (`person`) *names* an `.agent` — the booking channel.

    A pure deal-`.agent` reference with no agency is intentionally NOT treated as
    agent-capacity (post-GAP-046 an agent carries an `agency`); that full-fidelity
    case is deferred. Scalar `EXISTS` per relation — incl. a self-correlated
    agency check — so no JOIN multiplies rows or the paginator COUNT. Single
    source of truth: `ClientListView`'s membership filter + `is_agent` annotation
    and `ClientFilterSet.capacity` all key on it, so they can't drift.
    """
    agent_deal = {"person": OuterRef("pk"), "agent__isnull": False}
    # `cast`: django-stubs types `Combinable.__or__` as `-> Q`, and the
    # self-correlated `Exists(Person…)` term makes mypy infer the whole OR as Q.
    # At runtime this is a `CombinedExpression` (a Combinable) — the boolean the
    # annotation/filter need. Cast to restore the true type.
    return cast(
        Combinable,
        Exists(Booking.objects.filter(**agent_deal))
        | Exists(Quotation.objects.filter(**agent_deal))
        | Exists(Enquiry.objects.filter(**agent_deal))
        | Exists(Person.objects.filter(pk=OuterRef("pk"), agency__isnull=False)),
    )


class ClientFilterSet(filters.FilterSet):
    """Filter shape for `GET /clients` (GAP-047 + GAP-053).

    - `capacity` partitions by agent-capacity — `agent` (belongs to an agency or
      deals through a travel agent) vs `direct`.
    - `repeat` (GAP-053 chip) keys on the derived >=1-booking flag.
    - `tags` (GAP-053 VIP/Trade chips) is the `Person.tags` overlap, mirroring
      `ContactFilterSet`.
    """

    status = filters.CharFilter(field_name="status")
    capacity = filters.ChoiceFilter(
        method="filter_capacity",
        choices=[("direct", "Direct"), ("agent", "Agent")],
    )
    # Keys on the `is_repeat_customer` annotation applied by ClientListView.
    repeat = filters.BooleanFilter(field_name="is_repeat_customer")
    tags = filters.CharFilter(method="filter_tags")

    class Meta:
        model = Person
        fields = ["status", "capacity", "repeat", "tags"]

    def filter_capacity(
        self, queryset: QuerySet[Person], _name: str, value: str
    ) -> QuerySet[Person]:
        if value not in ("agent", "direct"):
            return queryset
        is_agent = Q(client_agent_capacity_expression())
        return queryset.filter(is_agent if value == "agent" else ~is_agent)

    def filter_tags(self, queryset: QuerySet[Person], _name: str, value: str) -> QuerySet[Person]:
        # Mirror ContactFilterSet.filter_tags: ANY-of overlap, unknown tokens
        # ignored (don't 400 or silently empty the page).
        valid = {t.value for t in PersonTag}
        wanted = [tok for tok in (raw.strip() for raw in value.split(",")) if tok in valid]
        if not wanted:
            return queryset
        return queryset.filter(tags__overlap=wanted)
