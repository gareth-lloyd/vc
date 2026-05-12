"""Reference-number generation for `Payment`, `Refund`, `SecurityDeposit`.

Mirrors `reservations.models._reference` — short, year-prefixed, unique-per-model.
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
    """Build a short reference like `P-2026-123456`.

    If `model` is provided, falls back to a UUID-suffix on collision.
    """
    year = timezone.now().year
    candidate = f"{prefix}-{year}-{_now_suffix()}"
    if model is None:
        return candidate
    if not model._default_manager.filter(reference=candidate).exists():
        return candidate
    return f"{prefix}-{year}-{_uuid_suffix()}"
