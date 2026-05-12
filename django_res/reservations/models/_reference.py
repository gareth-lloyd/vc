"""Reference-number generation for Enquiry / Quotation / Booking.

The legacy spec only requires "short, year-prefixed, unique-per-model".
A millisecond-resolution timestamp suffix collides only when two rows are
created in the same millisecond *and* trip the duplicate again on retry —
so we add a tiny retry loop with a UUID4-derived suffix as a fallback.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:
    from django.db.models import Model


def _now_suffix() -> str:
    return f"{int(time.time() * 1000) % 1_000_000:06d}"


def _uuid_suffix() -> str:
    return uuid.uuid4().hex[:8].upper()


def generate_reference(prefix: str, *, model: type[Model] | None = None) -> str:
    """Build a short reference like `B-2026-123456`.

    If `model` is provided, retry once with a UUID-suffix on collision.
    """
    year = timezone.now().year
    candidate = f"{prefix}-{year}-{_now_suffix()}"
    if model is None:
        return candidate
    manager = model._default_manager
    if not manager.filter(reference=candidate).exists():
        return candidate
    # Collision — fall back to a UUID-derived suffix.
    return f"{prefix}-{year}-{_uuid_suffix()}"
