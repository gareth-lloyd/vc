"""GAP-045 D1 — Person.merge must dedupe reservation rows that carry person-scoped
unique constraints.

`Person.merge` walks `_meta.related_objects` and bulk-`.update()`s every reverse
FK from the source onto the target. Two reservation models gained person-scoped
unique constraints in 3d-A that a blind `.update()` does not respect:

* ``BookingGuest`` — ``(booking, person, role)``: if both Persons hold a row on
  the same booking+role, the update collides → ``IntegrityError``.
* ``GuestPreference`` — ``(person, preference_type, quotation)`` with a NULLABLE
  ``quotation``: two standing prefs (quotation NULL) of the same type do not trip
  the PG constraint (NULLs distinct), so a blind update silently duplicates them.

These rows only become mergeable via ``/contacts:merge`` once customer mirrors
are first-class (D2), so the collision is latent today — hence this unit hardens
the model before the API surface is opened. Lives in ``reservations`` (not
``accounts``) for natural access to the booking/preference factories;
``reservations -> accounts`` is a legal downward spine edge.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, cast

import pytest
from django.contrib.contenttypes.models import ContentType

from accounts.models import Person
from core.models import AuditLog
from reservations.enums import BookingGuestRole
from reservations.factories import GuestFactory, make_occupying_booking
from reservations.models import BookingGuest, GuestPreference, GuestPreferenceType

if TYPE_CHECKING:
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import Booking, Guest, TermsVersion

pytestmark = pytest.mark.django_db


def _persons() -> tuple[Person, Person]:
    source = Person.objects.create(first_name="Src", last_name="Person")
    target = Person.objects.create(first_name="Tgt", last_name="Person")
    return source, target


def _booking(
    property_: Property, gbp: Currency, terms: TermsVersion, *, offset_days: int = 30
) -> Booking:
    return make_occupying_booking(
        property=property_,
        guest=cast("Guest", GuestFactory()),
        currency=gbp,
        terms=terms,
        date_from=date.today() + timedelta(days=offset_days),
        date_to=date.today() + timedelta(days=offset_days + 7),
    )


def test_merge_drops_colliding_bookingguest(
    property_: Property, gbp: Currency, terms: TermsVersion
) -> None:
    """Both Persons are CO_TRAVELLER on the same booking — the collision the bare
    ``.update()`` would IntegrityError on. After merge the target keeps its row
    and the source's duplicate is dropped (target wins, like the channel arm).

    CO_TRAVELLER, not LEAD: ``bookingguest_one_lead_per_booking`` forbids a second
    LEAD on a booking, so a two-LEAD fixture would fail at row creation, before
    merge() ever runs.
    """
    booking = _booking(property_, gbp, terms)
    source, target = _persons()
    BookingGuest.objects.create(booking=booking, person=source, role=BookingGuestRole.CO_TRAVELLER)
    BookingGuest.objects.create(booking=booking, person=target, role=BookingGuestRole.CO_TRAVELLER)

    source.merge(target)

    assert not Person.objects.filter(pk=source.pk).exists()
    co = BookingGuest.objects.filter(booking=booking, role=BookingGuestRole.CO_TRAVELLER)
    assert co.count() == 1
    assert co.get().person_id == target.pk


def test_merge_moves_noncolliding_bookingguest(
    property_: Property, gbp: Currency, terms: TermsVersion
) -> None:
    """A source BookingGuest whose (booking, role) signature is NOT present on the
    target is moved, not dropped — proving ``role`` participates in the dedupe
    signature and non-colliding rows still migrate."""
    booking = _booking(property_, gbp, terms)
    source, target = _persons()
    BookingGuest.objects.create(booking=booking, person=target, role=BookingGuestRole.PAYER)
    BookingGuest.objects.create(booking=booking, person=source, role=BookingGuestRole.CO_TRAVELLER)

    source.merge(target)

    assert not Person.objects.filter(pk=source.pk).exists()
    moved = BookingGuest.objects.filter(
        booking=booking, person=target, role=BookingGuestRole.CO_TRAVELLER
    )
    assert moved.exists()
    assert BookingGuest.objects.filter(
        booking=booking, person=target, role=BookingGuestRole.PAYER
    ).exists()


def test_merge_dedupes_null_quotation_travel_preference() -> None:
    """Two standing travel prefs (quotation NULL) of the same type on the two
    Persons: the PG constraint treats the NULLs as distinct, so a blind update
    would leave the survivor with a silent duplicate. The dedupe (Python ``None``
    equality, stricter than the constraint) drops the source's duplicate."""
    pref_type = GuestPreferenceType.objects.create(name="Dietary")
    source, target = _persons()
    GuestPreference.objects.create(person=source, preference_type=pref_type)
    GuestPreference.objects.create(person=target, preference_type=pref_type)

    source.merge(target)

    survivors = GuestPreference.objects.filter(
        person=target, preference_type=pref_type, quotation__isnull=True
    )
    assert survivors.count() == 1
    assert not GuestPreference.objects.filter(person=source).exists()


def test_merge_keeps_distinct_preference_types() -> None:
    """Standing prefs of DIFFERENT types are distinct under the constraint and
    must both survive on the target — guards against over-dedup collapsing the
    signature to ``person`` alone."""
    t1 = GuestPreferenceType.objects.create(name="Dietary")
    t2 = GuestPreferenceType.objects.create(name="Bedding")
    source, target = _persons()
    GuestPreference.objects.create(person=source, preference_type=t1)
    GuestPreference.objects.create(person=target, preference_type=t2)

    source.merge(target)

    assert GuestPreference.objects.filter(person=target).count() == 2


def test_merge_keeps_null_and_quotation_scoped_preference(
    property_: Property, gbp: Currency, terms: TermsVersion
) -> None:
    """A standing pref (quotation NULL) and a quote-scoped pref (quotation set) of
    the same type are distinct — proving ``quotation`` participates in the
    signature, so NULL is not conflated with a real FK."""
    booking = _booking(property_, gbp, terms)
    quotation = booking.quotation_line.quotation
    pref_type = GuestPreferenceType.objects.create(name="Dietary")
    source, target = _persons()
    GuestPreference.objects.create(person=source, preference_type=pref_type)  # NULL
    GuestPreference.objects.create(person=target, preference_type=pref_type, quotation=quotation)

    source.merge(target)

    assert GuestPreference.objects.filter(person=target).count() == 2


def test_merge_audits_dropped_bookingguest_count_and_trail(
    property_: Property, gbp: Currency, terms: TermsVersion
) -> None:
    """With one moved + one dropped BookingGuest: the FG-016 ``__rewrites__``
    summary counts only the MOVED row, and the dropped row — which BookingGuest is
    a *tracked* model — still leaves a post_delete audit trail. A bulk
    ``queryset.delete()`` would have destroyed the tracked row with no trail
    (django_res/CLAUDE.md), so this pins the per-instance delete."""
    booking_move = _booking(property_, gbp, terms, offset_days=30)
    booking_drop = _booking(property_, gbp, terms, offset_days=60)
    source, target = _persons()
    # source's row on booking_drop collides with target's → dropped.
    BookingGuest.objects.create(
        booking=booking_drop, person=target, role=BookingGuestRole.CO_TRAVELLER
    )
    dropped = BookingGuest.objects.create(
        booking=booking_drop, person=source, role=BookingGuestRole.CO_TRAVELLER
    )
    # source's row on booking_move has no counterpart on target → moved.
    BookingGuest.objects.create(
        booking=booking_move, person=source, role=BookingGuestRole.CO_TRAVELLER
    )

    source.merge(target)

    person_ct = ContentType.objects.get_for_model(Person)
    deletion = next(
        r
        for r in AuditLog.objects.filter(content_type=person_ct, object_id=str(source.pk))
        if r.field_diffs.get("__deleted__")
    )
    assert deletion.field_diffs["__rewrites__"]["reservations.BookingGuest.person"] == 1

    bg_ct = ContentType.objects.get_for_model(BookingGuest)
    assert AuditLog.objects.filter(
        content_type=bg_ct, object_id=str(dropped.pk), field_diffs__has_key="__deleted__"
    ).exists()
