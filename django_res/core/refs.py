"""Short, year-prefixed, unique-per-model reference-number generator.

Used by Enquiry / Quotation / Booking / Payment / Refund / SecurityDeposit.
Collision retry uses a UUID4-derived suffix; a millisecond-resolution
timestamp on the happy path keeps refs short.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

from django.db import connection
from django.utils import timezone

if TYPE_CHECKING:
    from django.db.models import Model

# Name of the Postgres sequence backing `Quotation.number` (created in
# reservations migration 0012). Kept here so the runtime allocator and the
# high-water-mark sync share one literal; the migration repeats it with a
# comment (migrations must not import app runtime code).
QUOTATION_NUMBER_SEQ = "quotation_number_seq"

# `Quotation`'s db_table, as a literal. `core` is the foundation layer and
# may import no domain app (the import-linter `core`-foundation contract), so
# the high-water sync below cannot reach for `Quotation._meta.db_table`. The
# name is fixed by migration 0012's `OWNED BY reservations_quotation.number`.
QUOTATION_TABLE = "reservations_quotation"


def _now_suffix() -> str:
    return f"{int(time.time() * 1000) % 1_000_000:06d}"


def _uuid_suffix() -> str:
    return uuid.uuid4().hex[:8].upper()


def quotation_prefix() -> str:
    """Customer-facing quotation prefix (legacy `QVC`), overridable via settings."""
    from core.models.system_settings import SystemSettings

    return SystemSettings.get_solo().settings.get("quotation_no_prefix", "QVC")


def booking_prefix() -> str:
    """Customer-facing booking prefix (legacy `VC`), overridable via settings."""
    from core.models.system_settings import SystemSettings

    return SystemSettings.get_solo().settings.get("booking_no_prefix", "VC")


def next_quotation_number() -> int:
    """Atomically allocate the next quotation number from the Postgres sequence.

    `nextval` is concurrency-safe on its own; `Quotation.number`'s `unique`
    constraint is the backstop. The booking number is *carried forward* from
    the quotation (legacy parity), so only quotations draw from this sequence.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval(%s)", [QUOTATION_NUMBER_SEQ])
        row = cursor.fetchone()
    return int(row[0])


def quotation_reference(number: int) -> str:
    """Customer-facing quotation reference (`QVC{number}`, legacy parity)."""
    return f"{quotation_prefix()}{number}"


def booking_reference(
    number: int,
    *,
    model: type[Model],
    exclude_pk: int | None = None,
) -> str:
    """Carry the booking number forward from its quotation as `VC{number}`.

    The real flow is one quote → one booking, so `VC{number}` is unique by
    construction. Where it isn't — a legacy import where two bookings share a
    `QuotationNo`, or a re-derive — append a UUID suffix so the row is
    *preserved* rather than colliding on the unique `reference`. `exclude_pk`
    omits the row itself, so re-saving an existing booking keeps its reference.
    """
    candidate = f"{booking_prefix()}{number}"
    qs = model._default_manager.filter(reference=candidate)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        return f"{candidate}-{_uuid_suffix()}"
    return candidate


def sync_quotation_sequence() -> int:
    """Fast-forward `quotation_number_seq` past the highest imported number.

    Loaders set `Quotation.number` directly (preserving exact legacy digits),
    which does not advance the sequence. Without this, the first organic
    quotation after an import draws a low `nextval` that collides with an
    already-imported `QVC{n}`. Idempotent: `setval` to the current max is a
    no-op on re-run. Returns the new high-water value.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            # `QUOTATION_TABLE` is a trusted table-name literal, not user input.
            f"SELECT setval(%s, (SELECT COALESCE(MAX(number), 1) FROM {QUOTATION_TABLE}))",
            [QUOTATION_NUMBER_SEQ],
        )
        row = cursor.fetchone()
    return int(row[0])


def generate_reference(prefix: str, *, model: type[Model] | None = None) -> str:
    """Build a short reference like `B-2026-123456`.

    If `model` is provided, retry once with a UUID-derived suffix on collision.
    """
    year = timezone.now().year
    candidate = f"{prefix}-{year}-{_now_suffix()}"
    if model is None:
        return candidate
    if not model._default_manager.filter(reference=candidate).exists():
        return candidate
    return f"{prefix}-{year}-{_uuid_suffix()}"
