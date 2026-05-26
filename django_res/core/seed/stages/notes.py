"""Operator notes on a fraction of bookings + enquiries.

Knob: `pct_notes` — fraction of each cohort that picks up a single note.
"""

from __future__ import annotations

from core.seed.context import SeedContext
from core.seed.registry import Stage, register
from reservations.enums import BookingNoteKind, BookingNoteVisibility, EnquiryNoteKind
from reservations.models.booking import BookingNote
from reservations.models.enquiry import EnquiryNote

_BOOKING_NOTES = [
    ("Guest requested early check-in", BookingNoteKind.GENERAL, BookingNoteVisibility.STAFF_ONLY),
    ("Owner confirmed welcome pack", BookingNoteKind.VILLA, BookingNoteVisibility.OWNER),
    (
        "Concierge: airport transfer booked",
        BookingNoteKind.CONCIERGE,
        BookingNoteVisibility.STAFF_ONLY,
    ),
    ("Allergic to nuts — notify chef", BookingNoteKind.INTERNAL, BookingNoteVisibility.STAFF_ONLY),
]

_ENQUIRY_NOTES = [
    ("Followed up by email", EnquiryNoteKind.GENERAL),
    ("Awaiting owner availability", EnquiryNoteKind.INTERNAL),
    ("Prefers ground-floor bedrooms", EnquiryNoteKind.PREFERENCES),
]


def _run(ctx: SeedContext) -> int:
    if ctx.knobs.pct_notes <= 0:
        return 0
    made = 0
    # Scope to bookings/enquiries this run created — additive reruns and
    # pre-existing fixture rows must not be silently annotated.
    n_bookings = int(len(ctx.booking_pks) * ctx.knobs.pct_notes)
    for pk in ctx.rng.sample(ctx.booking_pks, k=min(n_bookings, len(ctx.booking_pks))):
        body, kind, visibility = _BOOKING_NOTES[made % len(_BOOKING_NOTES)]
        BookingNote.objects.create(
            booking_id=pk,
            kind=kind,
            visibility=visibility,
            body=body,
        )
        made += 1
    n_enquiries = int(len(ctx.enquiry_pks) * ctx.knobs.pct_notes)
    e_made = 0
    for pk in ctx.rng.sample(ctx.enquiry_pks, k=min(n_enquiries, len(ctx.enquiry_pks))):
        e_body, e_kind = _ENQUIRY_NOTES[e_made % len(_ENQUIRY_NOTES)]
        EnquiryNote.objects.create(
            enquiry_id=pk,
            kind=e_kind,
            body=e_body,
        )
        e_made += 1
        made += 1
    return made


register(Stage(name="notes", run=_run, depends_on=("bookings", "orphan_enquiries")))
